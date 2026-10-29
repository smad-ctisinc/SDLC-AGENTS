"""Bounded JSON snapshots, optimistic revisions, and atomic local replacement."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from typing import Literal, Protocol

from pydantic import AwareDatetime, TypeAdapter, ValidationError

from ..context import ProjectContext
from ..contracts import ContractModel, Text
from ..execution import RunRecord
from ..paths import PathSafetyError, check_path


class ContextStoreError(ValueError):
    """Safe storage diagnostic without persisted data or raw exception text."""


class ContextNotFoundError(ContextStoreError):
    pass


class RevisionConflictError(ContextStoreError):
    pass


class StoreBusyError(ContextStoreError):
    pass


class ReadOnlyStoreError(ContextStoreError):
    pass


class RecordAlreadyExistsError(ContextStoreError):
    pass


class StoredContext(ContractModel):
    storage_version: Literal["1"]
    updated_at: AwareDatetime
    context: ProjectContext


class StoredRunRecord(ContractModel):
    storage_version: Literal["1"]
    record: RunRecord


class ContextStore(Protocol):
    def read(self, project_id: str) -> ProjectContext: ...
    def save(self, snapshot: ProjectContext, *, expected_revision: int) -> ProjectContext: ...


class RunRecordStore(Protocol):
    def read_run_record(self, project_id: str, run_id: str) -> RunRecord: ...
    def save_run_record(self, record: RunRecord) -> RunRecord: ...


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContextStoreError("Duplicate JSON key in stored context")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ContextStoreError("Non-finite JSON values are unsupported")


class JsonContextStore:
    """Read-only by default; root must be explicitly created by trusted host code.

    Missing state is revision zero. First save requires expected_revision=0 and
    returns revision 1. Every subsequent save replaces one entire project snapshot.
    """

    def __init__(self, root: str | Path, *, writable: bool = False,
                 max_bytes: int = 4 * 1024 * 1024) -> None:
        if type(writable) is not bool or type(max_bytes) is not int or not 1 <= max_bytes <= 64 * 1024 * 1024:
            raise ContextStoreError("Invalid storage configuration")
        self._root = Path(os.path.abspath(root))
        self._writable = writable
        self._max_bytes = max_bytes
        self._check_root()

    def _check_root(self) -> None:
        try:
            check_path(self._root, directory=True)
        except PathSafetyError:
            raise ContextStoreError("Storage root must be an existing safe directory") from None

    def _identity(self, project_id: str) -> tuple[str, str]:
        try:
            normalized = TypeAdapter(Text).validate_python(project_id, strict=True)
        except ValidationError:
            raise ContextStoreError("Invalid project ID") from None
        try:
            return normalized, hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        except UnicodeEncodeError:
            raise ContextStoreError("Project ID must be valid UTF-8 text") from None

    def _check_file(self, path: Path) -> None:
        try:
            check_path(path, self._root, directory=False)
            if path.stat().st_nlink != 1:
                raise ContextStoreError("Hard-linked state files are unsupported")
        except (PathSafetyError, OSError):
            raise ContextStoreError("Stored context path is unsafe or inaccessible") from None

    def _read_document(self, path: Path, model):
        self._check_root()
        if not os.path.lexists(path):
            raise ContextNotFoundError("No stored document exists for this identity")
        self._check_file(path)
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(descriptor, "rb") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
                    raise ContextStoreError("Stored context must be a regular unshared file")
                content = stream.read(self._max_bytes + 1)
            if len(content) > self._max_bytes:
                raise ContextStoreError("Stored context exceeds the size limit")
            # The first parse rejects ambiguities/non-finite numbers; Pydantic's
            # JSON mode then validates strict typed data and ISO datetime values.
            json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object,
                       parse_constant=_invalid_constant)
            stored = model.model_validate_json(content)
        except (OSError, UnicodeError, ValueError, RecursionError) as exc:
            if isinstance(exc, ContextStoreError):
                raise
            raise ContextStoreError("Stored context is unreadable or invalid") from None
        return stored

    def _read(self, project_id: str, path: Path) -> ProjectContext:
        stored = self._read_document(path, StoredContext)
        if stored.context.project_id != project_id or stored.context.revision < 1:
            raise ContextStoreError("Stored project identity or revision is invalid")
        return stored.context

    def read(self, project_id: str) -> ProjectContext:
        project_id, key = self._identity(project_id)
        return self._read(project_id, self._root / f"{key}.json")

    @contextmanager
    def _writer_lock(self, key: str):
        lock_path = self._root / f"{key}.lock"
        self._check_root()
        try:
            descriptor = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            raise StoreBusyError("Project writer lock already exists") from None
        except OSError:
            raise ContextStoreError("Cannot acquire project writer lock") from None
        try:
            os.close(descriptor)
            yield
        finally:
            # Stable, trusted directory ownership is required, as for registry.
            try:
                self._check_root()
                self._check_file(lock_path)
                lock_path.unlink()
            except (ContextStoreError, OSError):
                # Preserve the primary outcome; a leftover lock fails closed.
                pass

    def save(self, snapshot: ProjectContext, *, expected_revision: int) -> ProjectContext:
        if not self._writable:
            raise ReadOnlyStoreError("Storage writes were not enabled by the host")
        if type(expected_revision) is not int or expected_revision < 0:
            raise RevisionConflictError("Expected revision must be a nonnegative integer")
        if not isinstance(snapshot, ProjectContext):
            raise ContextStoreError("Expected a ProjectContext snapshot")
        try:
            snapshot = ProjectContext.model_validate(snapshot.model_dump())
        except (ValidationError, ValueError, RecursionError):
            raise ContextStoreError("Context snapshot failed validation") from None
        if snapshot.revision != expected_revision:
            raise RevisionConflictError("Snapshot revision must equal expected revision")
        project_id, key = self._identity(snapshot.project_id)
        path = self._root / f"{key}.json"
        with self._writer_lock(key):
            try:
                try:
                    revision = self._read(project_id, path).revision
                except ContextNotFoundError:
                    revision = 0
                if revision != expected_revision:
                    raise RevisionConflictError("Stored revision changed; reload before saving")
                snapshot.revision = revision + 1
                envelope = StoredContext(storage_version="1", updated_at=datetime.now(timezone.utc), context=snapshot)
                content = (envelope.model_dump_json(indent=2) + "\n").encode("utf-8")
                self._replace_bytes(path, content, key)
                return snapshot
            except OSError:
                raise ContextStoreError("Could not atomically save project context") from None

    def _replace_bytes(self, path: Path, content: bytes, key: str) -> None:
        """Called only under the matching writer lock."""
        if len(content) > self._max_bytes:
            raise ContextStoreError("Context exceeds the configured size limit")
        temporary: Path | None = None
        try:
            self._check_root()
            descriptor, name = tempfile.mkstemp(prefix=f".{key}.", suffix=".tmp", dir=self._root)
            temporary = Path(name)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            self._check_root()
            if os.path.lexists(path):
                self._check_file(path)
            os.replace(temporary, path)
            temporary = None
        except OSError:
            raise ContextStoreError("Could not atomically save project state") from None
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass  # An orphan temp is never interpreted as committed state.

    def save_run_record(self, record: RunRecord) -> RunRecord:
        """Persist metadata explicitly; never overwrite an existing project/run pair."""
        if not self._writable:
            raise ReadOnlyStoreError("Storage writes were not enabled by the host")
        if not isinstance(record, RunRecord):
            raise ContextStoreError("Expected a RunRecord metadata object")
        try:
            record = RunRecord.model_validate(record.model_dump())
        except (ValidationError, ValueError, RecursionError):
            raise ContextStoreError("Run record failed validation") from None
        _, project_key = self._identity(record.project_id)
        _, run_key = self._identity(record.run_id)
        key = f"run-{project_key}-{run_key}"
        path = self._root / f"{key}.json"
        with self._writer_lock(key):
            if os.path.lexists(path):
                raise RecordAlreadyExistsError("A record already exists for this project and run")
            content = (StoredRunRecord(storage_version="1", record=record).model_dump_json(indent=2) + "\n").encode("utf-8")
            self._replace_bytes(path, content, key)
        return record

    def read_run_record(self, project_id: str, run_id: str) -> RunRecord:
        project_id, project_key = self._identity(project_id)
        run_id, run_key = self._identity(run_id)
        path = self._root / f"run-{project_key}-{run_key}.json"
        record = self._read_document(path, StoredRunRecord).record
        if (record.project_id, record.run_id) != (project_id, run_id):
            raise ContextStoreError("Stored run identity does not match the request")
        return record
