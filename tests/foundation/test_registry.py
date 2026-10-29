"""Registry behavior using synthetic definitions; no agent execution."""

import os
from pathlib import Path
import subprocess
import stat
from types import SimpleNamespace

import pytest
import yaml

from sdlc_agents import (
    AgentNotFoundError, AmbiguousAgentVersionError, FileSystemAgentRegistry, RegistryError,
)
from sdlc_agents.registry import MAX_INSTRUCTIONS_BYTES

FIXTURES = Path(__file__).parents[1] / "fixtures/agents"


def make_agent(root, name="foundation-probe", version="0.1.0"):
    directory = root / name
    directory.mkdir(parents=True)
    data = yaml.safe_load((FIXTURES / "foundation-probe/contract.yaml").read_text(encoding="utf-8"))
    data["agent"].update(id=name, version=version)
    (directory / "contract.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (directory / "agent.md").write_text("# Synthetic instructions", encoding="utf-8")
    return directory


def test_discover_and_load_fixture():
    registry = FileSystemAgentRegistry([FIXTURES])
    metadata = registry.discover()
    assert len(metadata) == 1
    assert metadata[0].agent_id == "foundation-probe"
    assert metadata[0].contract_version == "1"
    assert metadata[0].capabilities == ("foundation.probe",)
    assert registry.get_metadata("foundation-probe") == metadata[0]
    assert registry.list_agents() == metadata
    definition = registry.load("foundation-probe", "0.1.0")
    definition.contract.validate_input({"project_id": "test"})
    assert "Foundation Probe" in definition.instructions


def test_multiple_roots_and_deterministic_listing(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    make_agent(first, "zeta")
    make_agent(first, "alpha", "1.10.0")
    make_agent(second, "alpha", "1.2.0")
    registry = FileSystemAgentRegistry([second, first])
    assert [(item.agent_id, item.version) for item in registry.list_agents()] == [
        ("alpha", "1.2.0"), ("alpha", "1.10.0"), ("zeta", "0.1.0"),
    ]
    assert registry.discover() == FileSystemAgentRegistry([first, second]).discover()
    for method in (registry.load, registry.get_metadata):
        with pytest.raises(AmbiguousAgentVersionError):
            method("alpha")
    assert registry.load("alpha", "1.10.0").contract.agent.version == "1.10.0"


def test_duplicate_identity_rejected(tmp_path):
    for name in ("first", "second"):
        make_agent(tmp_path / name)
    with pytest.raises(RegistryError, match="Duplicate agent identity"):
        FileSystemAgentRegistry([tmp_path / "first", tmp_path / "second"]).discover()


@pytest.mark.parametrize("filename", ["agent.md", "contract.yaml"])
def test_missing_required_file(tmp_path, filename):
    directory = make_agent(tmp_path)
    (directory / filename).unlink()
    with pytest.raises(RegistryError, match="Missing or inaccessible"):
        FileSystemAgentRegistry([tmp_path]).discover()


@pytest.mark.parametrize("content", ["broken: [", "contract_version: '9'", "[]", "", "!!python/object/apply:os.system ['echo unsafe']"])
def test_invalid_yaml(tmp_path, content):
    directory = make_agent(tmp_path)
    (directory / "contract.yaml").write_text(content, encoding="utf-8")
    with pytest.raises(RegistryError, match="Invalid contract"):
        FileSystemAgentRegistry([tmp_path]).load("foundation-probe")


@pytest.mark.parametrize("field,value", [("contract_version", "9"), ("version", "latest"), ("version", "1.0"), ("id", "other-agent")])
def test_invalid_versions_and_id_mismatch(tmp_path, field, value):
    directory = make_agent(tmp_path)
    path = directory / "contract.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if field == "contract_version":
        data[field] = value
    else:
        data["agent"][field] = value
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(RegistryError):
        FileSystemAgentRegistry([tmp_path]).discover()


@pytest.mark.parametrize("name", ["BadName", "invalid_name", ".hidden", "has space"])
def test_invalid_directory_names(tmp_path, name):
    make_agent(tmp_path, name)
    with pytest.raises(RegistryError, match="Invalid agent directory name"):
        FileSystemAgentRegistry([tmp_path]).discover()


def test_empty_root_and_non_agent_files(tmp_path):
    registry = FileSystemAgentRegistry([tmp_path])
    assert registry.discover() == []
    (tmp_path / "README.md").write_text("Root documentation", encoding="utf-8")
    assert registry.list_agents() == []
    (tmp_path / "empty-agent").mkdir()
    with pytest.raises(RegistryError):
        registry.discover()


@pytest.mark.parametrize("agent_id,version", [("../outside", None), ("/absolute", None), (r"..\outside", None), ("probe", "../1.0.0"), ("probe", ">=1.0.0")])
def test_lookup_traversal_rejected(tmp_path, agent_id, version):
    with pytest.raises(RegistryError, match="Invalid agent ID or version"):
        FileSystemAgentRegistry([tmp_path]).load(agent_id, version)


def test_unknown_identity(tmp_path):
    make_agent(tmp_path)
    registry = FileSystemAgentRegistry([tmp_path])
    with pytest.raises(AgentNotFoundError):
        registry.load("missing")
    with pytest.raises(AgentNotFoundError):
        registry.load("foundation-probe", "9.0.0")


def test_invalid_root_configuration(tmp_path):
    for roots in ([], str(tmp_path), [tmp_path / "missing"], [tmp_path, tmp_path]):
        with pytest.raises(RegistryError):
            FileSystemAgentRegistry(roots)
    child = tmp_path / "child"
    child.mkdir()
    with pytest.raises(RegistryError, match="non-overlapping"):
        FileSystemAgentRegistry([tmp_path, child])


@pytest.mark.parametrize("content", [b" \n", b"\xff", b"x" * (MAX_INSTRUCTIONS_BYTES + 1)], ids=["empty", "encoding", "oversized"])
def test_invalid_instructions(tmp_path, content):
    directory = make_agent(tmp_path)
    (directory / "agent.md").write_bytes(content)
    with pytest.raises(RegistryError):
        FileSystemAgentRegistry([tmp_path]).discover()


def test_no_execution_and_returned_objects_are_isolated(tmp_path):
    directory = make_agent(tmp_path)
    marker = tmp_path / "executed"
    code = f"from pathlib import Path; Path({str(marker)!r}).touch()"
    (directory / "agent.py").write_text(code, encoding="utf-8")
    (directory / "agent.md").write_text(code, encoding="utf-8")
    registry = FileSystemAgentRegistry([tmp_path])
    definition = registry.load("foundation-probe")
    assert definition.instructions == code
    definition.contract.agent.id = "changed"
    assert registry.load("foundation-probe").contract.agent.id == "foundation-probe"
    assert not marker.exists()


def test_refresh_fails_instead_of_serving_stale_or_partial_results(tmp_path):
    make_agent(tmp_path)
    registry = FileSystemAgentRegistry([tmp_path])
    assert len(registry.discover()) == 1
    (tmp_path / "broken").mkdir()
    for method in (registry.discover, registry.list_agents, lambda: registry.load("foundation-probe")):
        with pytest.raises(RegistryError):
            method()


def create_link(link, target, directory):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        if os.name != "nt":
            raise
        pytest.skip(f"OS does not permit test symlinks: {exc}")


@pytest.mark.parametrize("kind", ["root", "agent", "instructions", "contract", "internal", "broken"])
def test_symlink_rejected(tmp_path, kind):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    directory = make_agent(root)
    external = make_agent(outside)
    if kind == "root":
        link = tmp_path / "root-link"
        create_link(link, root, True)
        with pytest.raises(RegistryError, match="Links and reparse"):
            FileSystemAgentRegistry([link])
        return
    if kind in ("agent", "broken", "internal"):
        target = external if kind == "agent" else directory if kind == "internal" else outside / "missing"
        create_link(root / "linked", target, True)
    else:
        name = "agent.md" if kind == "instructions" else "contract.yaml"
        (directory / name).unlink()
        create_link(directory / name, external / name, False)
    with pytest.raises(RegistryError, match="Links and reparse"):
        FileSystemAgentRegistry([root]).discover()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction behavior")
@pytest.mark.parametrize("as_root", [False, True])
def test_windows_junction_rejected(tmp_path, as_root):
    root = tmp_path / "root"
    root.mkdir()
    target = tmp_path / "outside"
    target.mkdir()
    link = root / "junction"
    completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    try:
        with pytest.raises(RegistryError, match="Links and reparse"):
            FileSystemAgentRegistry([link if as_root else root]).discover()
    finally:
        link.rmdir()  # Remove the junction itself, never its target.


def test_symlink_attribute_rejected_without_os_privileges(tmp_path, monkeypatch):
    directory = make_agent(tmp_path)
    selected = directory / "agent.md"
    original = Path.lstat

    def lstat(path, *args, **kwargs):
        if path == selected:
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    with pytest.raises(RegistryError, match="Links and reparse"):
        FileSystemAgentRegistry([tmp_path]).discover()
