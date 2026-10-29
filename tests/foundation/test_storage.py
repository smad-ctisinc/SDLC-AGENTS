"""Host-managed persistence, evidence integrity, and revision conflict behavior."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from sdlc_agents import (
    ContextNotFoundError, ContextStoreError, JsonContextStore, Observation,
    ProjectContext, Provenance, ReadOnlyStoreError, RevisionConflictError,
    SourceReference, StoreBusyError,
    RecordAlreadyExistsError, RunRecord, UsageMetrics,
)


def evidence_context(project="p"):
    return ProjectContext(
        project_id=project, metadata={"technology": "Python"},
        components=[{"name": "api", "technology": "HTTP"}],
        source_references=[SourceReference(source_id="source-1", path="src/app.py",
                                           content_sha256="a" * 64, start_line=1, end_line=4)],
        observations=[Observation(observation_id="observation-1", statement="Defines a route",
                                  classification="verified", source_ids=["source-1"],
                                  provenance=Provenance(agent_id="foundation-probe", agent_version="0.1.0",
                                                        run_id="test-run", recorded_at=datetime.now(timezone.utc)))],
    )


def test_create_read_update_and_no_caller_mutation(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    original = evidence_context()
    saved = store.save(original, expected_revision=0)
    assert original.revision == 0 and saved.revision == 1
    assert store.read("p") == saved
    assert JsonContextStore(tmp_path).read("p") == saved
    saved.metadata["new"] = True
    updated = store.save(saved, expected_revision=1)
    assert saved.revision == 1 and updated.revision == 2
    assert store.read("p").metadata["new"] is True
    assert not list(tmp_path.glob("*.lock")) and not list(tmp_path.glob("*.tmp"))


def test_read_only_and_missing_context_do_not_write(tmp_path):
    store = JsonContextStore(tmp_path)
    with pytest.raises(ContextNotFoundError):
        store.read("p")
    with pytest.raises(ReadOnlyStoreError):
        store.save(ProjectContext(project_id="p"), expected_revision=0)
    assert list(tmp_path.iterdir()) == []
    with pytest.raises(ContextStoreError):
        JsonContextStore(tmp_path / "not-created")
    assert list(tmp_path.iterdir()) == []


def test_revision_conflicts_preserve_stored_state(tmp_path):
    first = JsonContextStore(tmp_path, writable=True)
    second = JsonContextStore(tmp_path, writable=True)
    saved = first.save(ProjectContext(project_id="p"), expected_revision=0)
    stale = second.read("p")
    first.save(saved, expected_revision=1)
    with pytest.raises(RevisionConflictError):
        second.save(stale, expected_revision=1)
    with pytest.raises(RevisionConflictError):
        first.save(saved, expected_revision=2)
    with pytest.raises(RevisionConflictError):
        first.save(ProjectContext(project_id="new", revision=1), expected_revision=1)
    assert first.read("p").revision == 2


@pytest.mark.parametrize("expected", [-1, True, "0", None])
def test_invalid_expected_revision(tmp_path, expected):
    with pytest.raises(RevisionConflictError):
        JsonContextStore(tmp_path, writable=True).save(ProjectContext(project_id="p"), expected_revision=expected)
    assert list(tmp_path.iterdir()) == []


def test_project_isolation_and_opaque_ids(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    for project in ("../outside", r"C:\\absolute", "ordinary"):
        store.save(ProjectContext(project_id=project, metadata={"id": project}), expected_revision=0)
    for project in ("../outside", r"C:\\absolute", "ordinary"):
        assert store.read(project).metadata == {"id": project}
    paths = list(tmp_path.iterdir())
    assert len(paths) == 3 and all(path.suffix == ".json" and len(path.stem) == 64 for path in paths)


@pytest.mark.parametrize("content", [b"broken", b"[]", b"{}", b"\xff", b'{"x":NaN}', b'{"x":1,"x":2}'])
def test_corrupt_json_is_not_overwritten(tmp_path, content):
    store = JsonContextStore(tmp_path, writable=True)
    saved = store.save(ProjectContext(project_id="p"), expected_revision=0)
    path = next(tmp_path.glob("*.json"))
    path.write_bytes(content)
    with pytest.raises(ContextStoreError):
        store.read("p")
    with pytest.raises(ContextStoreError):
        store.save(saved, expected_revision=1)
    assert path.read_bytes() == content


@pytest.mark.parametrize("change", ["storage_version", "schema_version", "identity", "revision", "unknown"])
def test_invalid_stored_envelope(tmp_path, change):
    store = JsonContextStore(tmp_path, writable=True)
    store.save(ProjectContext(project_id="p"), expected_revision=0)
    path = next(tmp_path.glob("*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    if change == "storage_version":
        data["storage_version"] = "99"
    elif change == "schema_version":
        data["context"]["schema_version"] = "99"
    elif change == "identity":
        data["context"]["project_id"] = "other"
    elif change == "revision":
        data["context"]["revision"] = 0
    else:
        data["unexpected"] = True
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContextStoreError):
        store.read("p")


@pytest.mark.parametrize("failure", ["replace", "fsync"])
def test_interrupted_write_preserves_previous_snapshot(tmp_path, monkeypatch, failure):
    store = JsonContextStore(tmp_path, writable=True)
    saved = store.save(ProjectContext(project_id="p"), expected_revision=0)
    path = next(tmp_path.glob("*.json"))
    before = path.read_bytes()
    saved.metadata["changed"] = True
    def fail(*args, **kwargs):
        raise OSError("TOP_SECRET internal error")
    monkeypatch.setattr(f"sdlc_agents.storage.json_store.os.{failure}", fail)
    with pytest.raises(ContextStoreError) as caught:
        store.save(saved, expected_revision=1)
    assert "TOP_SECRET" not in str(caught.value)
    assert path.read_bytes() == before
    assert len(list(tmp_path.iterdir())) == 1


def test_reader_sees_complete_old_then_new_snapshot(tmp_path, monkeypatch):
    store = JsonContextStore(tmp_path, writable=True)
    saved = store.save(ProjectContext(project_id="p"), expected_revision=0)
    original = os.replace
    observed = []
    def replace(source, target):
        observed.append(store.read("p").revision)
        original(source, target)
        observed.append(store.read("p").revision)
    monkeypatch.setattr("sdlc_agents.storage.json_store.os.replace", replace)
    store.save(saved, expected_revision=1)
    assert observed == [1, 2]


def test_concurrent_writers_do_not_lose_updates(tmp_path):
    def save():
        try:
            return JsonContextStore(tmp_path, writable=True).save(ProjectContext(project_id="p"), expected_revision=0)
        except (RevisionConflictError, StoreBusyError) as error:
            return error
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: save(), range(2)))
    assert sum(isinstance(item, ProjectContext) for item in outcomes) == 1
    assert JsonContextStore(tmp_path).read("p").revision == 1


def test_lock_excludes_a_second_process(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    _, key = store._identity("p")
    script = '''
import sys
from sdlc_agents import JsonContextStore, ProjectContext, StoreBusyError
try:
    JsonContextStore(sys.argv[1], writable=True).save(ProjectContext(project_id="p"), expected_revision=0)
except StoreBusyError:
    sys.exit(0)
sys.exit(1)
'''
    with store._writer_lock(key):
        result = subprocess.run([sys.executable, "-c", script, str(tmp_path)], capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert list(tmp_path.iterdir()) == []


def test_other_project_can_write_while_one_is_locked(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    _, key = store._identity("p")
    with store._writer_lock(key):
        assert store.save(ProjectContext(project_id="other"), expected_revision=0).revision == 1
        with pytest.raises(StoreBusyError):
            store.save(ProjectContext(project_id="p"), expected_revision=0)


def test_size_limits(tmp_path):
    store = JsonContextStore(tmp_path, writable=True, max_bytes=1024)
    with pytest.raises(ContextStoreError, match="size limit"):
        store.save(ProjectContext(project_id="p", metadata={"x": "x" * 1024}), expected_revision=0)
    store.save(ProjectContext(project_id="p"), expected_revision=0)
    next(tmp_path.glob("*.json")).write_bytes(b"x" * 1025)
    with pytest.raises(ContextStoreError, match="size limit"):
        store.read("p")


def test_hard_link_state_rejected(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    store.save(ProjectContext(project_id="p"), expected_revision=0)
    os.link(next(tmp_path.glob("*.json")), tmp_path / "alias")
    with pytest.raises(ContextStoreError):
        store.read("p")


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
def test_junction_root_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    assert result.returncode == 0
    try:
        with pytest.raises(ContextStoreError):
            JsonContextStore(link, writable=True)
    finally:
        link.rmdir()


@pytest.mark.parametrize("path", ["../escape", "/absolute", "a/../b", r"C:\\source", "a//b"])
def test_evidence_paths_are_relative(path):
    with pytest.raises(ValidationError):
        SourceReference(source_id="source", path=path, content_sha256="a" * 64)


@pytest.mark.parametrize("change", ["duplicate_source", "duplicate_observation", "dangling", "duplicate_reference", "empty_reference", "classification", "digest", "lines"])
def test_invalid_evidence_is_rejected(change):
    data = evidence_context().model_dump()
    if change == "duplicate_source":
        data["source_references"] *= 2
    elif change == "duplicate_observation":
        data["observations"] *= 2
    elif change in ("dangling", "duplicate_reference", "empty_reference"):
        data["observations"][0]["source_ids"] = {"dangling": ["missing"], "duplicate_reference": ["source-1", "source-1"], "empty_reference": []}[change]
    elif change == "classification":
        data["observations"][0]["classification"] = "certain"
    elif change == "digest":
        data["source_references"][0]["content_sha256"] = "not-a-digest"
    else:
        data["source_references"][0].update(start_line=4, end_line=1)
    with pytest.raises(ValidationError):
        ProjectContext.model_validate(data)


def test_revalidate_mutated_snapshot_on_save(tmp_path):
    snapshot = evidence_context()
    snapshot.observations[0].source_ids.append("missing")
    with pytest.raises(ContextStoreError):
        JsonContextStore(tmp_path, writable=True).save(snapshot, expected_revision=0)
    assert list(tmp_path.iterdir()) == []


def test_run_record_round_trip_duplicate_and_project_isolation(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    now = datetime.now(timezone.utc)
    record = RunRecord(project_id="p", run_id="run", agent_id="foundation-probe", agent_version="0.1.0",
                       definition_digest="a" * 64, status="succeeded", started_at=now, finished_at=now,
                       duration_seconds=0.0, error_code=None, usage=UsageMetrics())
    with pytest.raises(ReadOnlyStoreError):
        JsonContextStore(tmp_path).save_run_record(record)
    assert store.save_run_record(record) == record
    assert store.read_run_record("p", "run") == record
    with pytest.raises(RecordAlreadyExistsError):
        store.save_run_record(record)
    with pytest.raises(ContextNotFoundError):
        store.read_run_record("other", "run")
    other = RunRecord.model_validate(record.model_dump() | {"project_id": "other"})
    store.save_run_record(other)
    assert store.read_run_record("other", "run") == other
    assert len(list(tmp_path.glob("run-*.json"))) == 2
    data = json.loads(next(tmp_path.glob("run-*.json")).read_text(encoding="utf-8"))
    assert not {"output", "inputs", "prompt", "error"}.intersection(data["record"])


def test_run_record_identity_and_shape_validated(tmp_path):
    store = JsonContextStore(tmp_path, writable=True)
    now = datetime.now(timezone.utc)
    record = RunRecord(project_id="p", run_id="run", agent_id="foundation-probe", agent_version=None,
                       definition_digest=None, status="failed", started_at=now, finished_at=now,
                       duration_seconds=0.0, error_code="agent_not_found", usage=UsageMetrics())
    store.save_run_record(record)
    path = next(tmp_path.glob("run-*.json"))
    data = json.loads(path.read_text(encoding="utf-8"))
    data["record"]["run_id"] = "different"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContextStoreError, match="identity"):
        store.read_run_record("p", "run")
    data["record"]["output"] = {"secret": "unwanted payload"}
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ContextStoreError):
        store.read_run_record("p", "run")
