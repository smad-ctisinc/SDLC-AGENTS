# Project context storage (Phase 5)

Phase 5 adds typed evidence/provenance and explicit host-managed JSON persistence.
`JsonContextStore` implements the `ContextStore` and `RunRecordStore` protocols.
It stores project snapshots and sanitized run metadata without importing runner
services. It does not grant agents filesystem-write permissions or add RAG,
vector search, cloud storage, or a CLI.

## Example

This example uses temporary state storage, separate from any target application:

```python
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from sdlc_agents import (
    JsonContextStore, Observation, ProjectContext, Provenance, SourceReference,
)

with TemporaryDirectory() as directory:
    store = JsonContextStore(Path(directory), writable=True)
    snapshot = ProjectContext(
        project_id="example",
        metadata={"language": "Python"},
        source_references=[SourceReference(
            source_id="source-1", path="src/example.py",
            content_sha256=sha256(b"synthetic example").hexdigest(),
            start_line=1, end_line=1,
        )],
        observations=[Observation(
            observation_id="finding-1", statement="Synthetic observation",
            classification="inferred", source_ids=["source-1"],
            provenance=Provenance(
                agent_id="foundation-probe", agent_version="0.1.0",
                run_id="example-run", recorded_at=datetime.now(timezone.utc),
            ),
        )],
    )
    saved = store.save(snapshot, expected_revision=0)
    assert snapshot.revision == 0  # caller-owned object was not changed
    assert saved.revision == 1
    loaded = store.read("example")
    assert loaded == saved
    loaded.metadata["module_count"] = 1
    updated = store.save(loaded, expected_revision=loaded.revision)
    assert updated.revision == 2
```

The source reference is illustrative metadata: the store never reads or verifies
`src/example.py`. Producers must provide accurate digests and statements.

## API and project isolation

- `read(project_id) -> ProjectContext` returns a fresh validated snapshot or raises
  `ContextNotFoundError`. It never creates an empty project implicitly.
- `save(snapshot, expected_revision=...) -> ProjectContext` writes a complete
  snapshot and returns its new revision. It does not merge fields.
- `save_run_record(record) -> RunRecord` persists sanitized metadata for a unique
  project/run pair. Existing records raise `RecordAlreadyExistsError`, including
  identical resubmissions; no record is overwritten.
- `read_run_record(project_id, run_id) -> RunRecord` validates the envelope and
  requested identities. Missing records raise `ContextNotFoundError`.

Constructors require an existing root directory. Reading is the default;
`writable=True` is an explicit trusted-host configuration decision. Host code
must create and authorize the state root, normally outside the target source
tree. The store is not a multi-user authorization service: possession of the
store object allows its configured operations on projects in that root.

Project/run IDs are normalized using the existing non-empty text model, then
hashed with SHA-256. IDs are never used as directory paths. Files are:

```text
<state-root>/
  <project-hash>.json
  run-<project-hash>-<run-hash>.json
  <identity-key>.lock                 # only while a writer owns the lock
  .<identity-key>.<random>.tmp         # only while preparing a replacement
```

Context files and run-record files have distinct prefixes. Stored project/run
identities are checked against the requested IDs on every read. Hashing filenames
prevents traversal; it does not anonymize or encrypt document contents.

## Versions and optimistic updates

The disk envelope uses `storage_version: "1"`. Project data uses
`schema_version: "1"`, independently of contract and agent versions. Unknown
versions and unknown fields fail validation. Revision is an integer counter owned
by storage, not a schema or agent version.

An absent context is revision zero. Creation requires both `snapshot.revision == 0`
and `expected_revision == 0`, returning revision 1. Subsequent saves require the
snapshot revision, expected revision, and current disk revision to agree. A stale
save raises `RevisionConflictError` without modifying the committed document.
Reload, reconcile changes in host code, and explicitly retry; the store performs
no automatic conflict resolution.

The same project cannot have concurrent writers: an exclusive per-identity lock
file serializes writers across threads, processes, and separate store instances.
Lock contention raises `StoreBusyError` immediately; it does not wait or retry.
Different projects and different run records can be written independently. There
is no distributed transaction or transaction across a context and its run record.

## Typed evidence and provenance

`ProjectContext` preserves extensible JSON `metadata` and `components`, and now
uses typed `source_references` and `observations`:

| Model | Required information |
| --- | --- |
| `SourceReference` | Unique source ID, project-relative slash path, SHA-256 content digest; optional source revision and line range |
| `Observation` | Unique observation ID, statement, `verified` or `inferred` classification, non-empty source ID list, provenance |
| `Provenance` | Producer agent ID/version, run ID, timezone-aware recorded timestamp |

Observation references must resolve within the same snapshot; duplicate IDs,
duplicate evidence links, missing references, malformed digests, invalid line
ranges, and unsafe reference paths are rejected. A start line may stand alone;
an end line requires a start line and cannot precede it.

`verified` records a producer's assertion, not an independent verification by
storage. Storage does not open source files, compare digests to a repository,
verify a referenced run exists, or decide whether a source is stale. Host/agent
analysis must make those decisions using the recorded evidence. Metadata and
component dictionaries do not automatically gain verified status.

Earlier in-memory arbitrary dictionaries in these two evidence collections must
be converted to the typed fields before saving; they are not silently migrated.
Empty evidence lists remain valid. No legacy persisted format existed before
this phase, and no automatic disk migration is introduced.

## Atomic writes and failure behavior

Under the identity lock, the store checks the current revision, validates a fresh
copy of the snapshot, writes a uniquely named temporary file in the same directory,
flushes and fsyncs it, then uses `os.replace` to commit it atomically. Readers use
only the final filename. They see a complete old/new snapshot, or a clear error
if concurrent replacement conflicts with platform path/open checks.

Failures before replacement leave previous committed bytes unchanged. Temporary
files and locks are cleaned up during normal failure handling. A process crash
can leave orphaned temporary files and a stale lock; these are never interpreted
as committed data, and a stale lock blocks writes. There is deliberately no
automatic stale-lock stealing. Recovery requires trusted host verification that
no writer is active before removing the specific stale lock/orphan files.
If lock cleanup itself fails after a successful commit, the committed result is
preserved and later writes fail closed until the lock is recovered.

This is local-filesystem atomic replacement, not a universal power-loss durability
guarantee. Parent-directory fsync, distributed filesystem locking, journaling,
historical revisions, and automatic backup/recovery are not implemented.

## Security and limits

Shared path checks reject symlinks, Windows junctions/reparse points, unsafe root
ancestors, and non-regular state files. Hard-linked state files are rejected.
Existing corrupt or mismatched-identity documents cannot be overwritten through
normal save operations. Reads and writes are bounded (default 4 MiB per document,
configurable up to 64 MiB). Duplicate JSON keys, non-finite values, malformed JSON,
invalid UTF-8, unsupported versions, and invalid typed data fail closed. Errors
omit persisted content and raw filesystem/validation exception text.

State roots must be owned by trusted host code and stable while in use. These
checks are not an OS sandbox against hostile concurrent path replacement.
Temporary and lock files request owner-only permissions on POSIX; Windows access
depends on the root's ACL. State is not encrypted. Store only sanitized knowledge;
there is no automatic content redaction because rewriting provenance, IDs, or
evidence can corrupt their meaning. Sanitize content before constructing models.

## Runner integration

Host code passes `store.read(project_id)` as `ExecutionRequest.context`. The runner
and executor receive copies; execution does not automatically modify the stored
snapshot. Host code may explicitly save reviewed context changes with the observed
revision. This host persistence is separate from the broker's denied file-write
capability.

Runner records remain in-memory until host code calls
`store.save_run_record(record)` on a completed `runner.records()` entry. The shared
`RunRecord` model is now defined in `execution.py` and remains available from its
previous public imports. Stored records contain identity, timing, status, digest,
error code, and usage metadata only—no inputs, outputs, prompts, or exception text.

Tests cover schema/provenance validation, round trips, project isolation, immutable
run records, revision conflicts, cross-process locks, interrupted writes, corrupt
files, size limits, unsafe paths, and explicit integration with the runner.
Phase 6 adds the [CLI and end-to-end documentation](cli-guide.md).
