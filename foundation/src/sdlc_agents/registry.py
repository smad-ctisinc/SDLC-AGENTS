"""Read-only discovery of portable definitions from explicit filesystem roots."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from pydantic import ConfigDict, TypeAdapter, ValidationError

from .contracts import AgentDefinition, AgentId, AgentVersion, ContractModel, Text
from .loader import ContractLoadError, load_contract
from .paths import PathSafetyError, check_path

MAX_INSTRUCTIONS_BYTES = 256 * 1024
_ID = TypeAdapter(AgentId)
_VERSION = TypeAdapter(AgentVersion)


class RegistryError(ValueError):
    """Invalid configuration, unsafe path, or malformed agent definition."""


class AgentNotFoundError(RegistryError):
    """No definition matches the requested identity/version."""


class AmbiguousAgentVersionError(RegistryError):
    """An explicit version is required for an ID with multiple versions."""


class AgentMetadata(ContractModel):
    """Immutable registry summary without instructions or implementation bindings."""

    model_config = ConfigDict(frozen=True)
    agent_id: AgentId
    version: AgentVersion
    contract_version: Text
    description: Text
    capabilities: tuple[str, ...]
    source_directory: Path


class AgentRegistry(Protocol):
    """Public interface independent of execution, providers, and user interfaces."""

    def discover(self) -> list[AgentMetadata]: ...
    def list_agents(self) -> list[AgentMetadata]: ...
    def load(self, agent_id: str, version: str | None = None) -> AgentDefinition: ...
    def get_metadata(self, agent_id: str, version: str | None = None) -> AgentMetadata: ...


def _checked_path(path: Path, root: Path | None = None, *, directory: bool) -> None:
    try:
        check_path(path, root, directory=directory)
    except PathSafetyError as exc:
        raise RegistryError(str(exc)) from None


class FileSystemAgentRegistry:
    """Rescan on every operation; never expose partial or stale discovery state.

    Each immediate root subdirectory is a candidate and must match its contract
    ID. Different versions of one ID can live in different roots. Duplicate
    (ID, version) pairs are errors. Omitted versions resolve only a unique match.
    """

    def __init__(self, search_roots: Sequence[str | Path]) -> None:
        if isinstance(search_roots, (str, bytes, Path)) or not search_roots:
            raise RegistryError("Provide a non-empty sequence of search roots")
        roots = tuple(Path(os.path.abspath(root)) for root in search_roots)
        for root in roots:
            _checked_path(root, directory=True)
        for index, root in enumerate(roots):
            for other in roots[:index]:
                if root.is_relative_to(other) or other.is_relative_to(root):
                    raise RegistryError("Search roots must be distinct and non-overlapping")
        self._roots = tuple(sorted(roots, key=str))

    def _scan(self) -> dict[tuple[str, str], tuple[AgentMetadata, AgentDefinition]]:
        entries: dict[tuple[str, str], tuple[AgentMetadata, AgentDefinition]] = {}
        for root in self._roots:
            _checked_path(root, directory=True)
            try:
                children = sorted(root.iterdir(), key=lambda path: path.name)
                for child in children:
                    # Check even ignored root files so links cannot hide candidates.
                    _checked_path(child, root, directory=child.is_dir())
                    if not child.is_dir():
                        continue
                    try:
                        _ID.validate_python(child.name, strict=True)
                    except ValidationError:
                        raise RegistryError(f"Invalid agent directory name: {child}") from None
                    contract_path = child / "contract.yaml"
                    instructions_path = child / "agent.md"
                    _checked_path(contract_path, root, directory=False)
                    _checked_path(instructions_path, root, directory=False)
                    try:
                        contract = load_contract(contract_path)
                    except ContractLoadError as exc:
                        raise RegistryError(f"Invalid contract at {contract_path}: {exc}") from None
                    if contract.agent.id != child.name:
                        raise RegistryError(f"Agent ID must match directory name: {child}")
                    with instructions_path.open("rb") as stream:
                        content = stream.read(MAX_INSTRUCTIONS_BYTES + 1)
                    if len(content) > MAX_INSTRUCTIONS_BYTES:
                        raise RegistryError(f"Agent instructions exceed 256 KiB: {instructions_path}")
                    try:
                        definition = AgentDefinition(
                            instructions=content.decode("utf-8-sig"), contract=contract
                        )
                    except (UnicodeError, ValidationError):
                        raise RegistryError(f"Invalid or empty UTF-8 instructions: {instructions_path}") from None
                    _checked_path(contract_path, root, directory=False)
                    _checked_path(instructions_path, root, directory=False)
                    identity = (contract.agent.id, contract.agent.version)
                    if identity in entries:
                        raise RegistryError(f"Duplicate agent identity {identity[0]}@{identity[1]}")
                    metadata = AgentMetadata(
                        agent_id=identity[0], version=identity[1],
                        contract_version=contract.contract_version,
                        description=contract.agent.description,
                        capabilities=tuple(contract.agent.capabilities),
                        source_directory=child,
                    )
                    entries[identity] = (metadata, definition)
            except OSError:
                raise RegistryError(f"Cannot read agent definitions under root: {root}") from None
        return entries

    def discover(self) -> list[AgentMetadata]:
        entries = self._scan()
        # Numeric version sorting is presentation only, never version selection.
        keys = sorted(entries, key=lambda key: (key[0], tuple(map(int, key[1].split('.')))))
        return [entries[key][0] for key in keys]

    def list_agents(self) -> list[AgentMetadata]:
        return self.discover()

    def _select(self, agent_id: str, version: str | None) -> tuple[AgentMetadata, AgentDefinition]:
        try:
            _ID.validate_python(agent_id, strict=True)
            if version is not None:
                _VERSION.validate_python(version, strict=True)
        except ValidationError:
            raise RegistryError("Invalid agent ID or version; use an ID and exact major.minor.patch version") from None
        entries = self._scan()
        matches = [entry for (name, ver), entry in entries.items()
                   if name == agent_id and (version is None or ver == version)]
        if not matches:
            raise AgentNotFoundError("Requested agent ID/version was not found")
        if len(matches) != 1:
            raise AmbiguousAgentVersionError("Multiple agent versions found; specify an exact version")
        return matches[0]

    def load(self, agent_id: str, version: str | None = None) -> AgentDefinition:
        return self._select(agent_id, version)[1]

    def get_metadata(self, agent_id: str, version: str | None = None) -> AgentMetadata:
        return self._select(agent_id, version)[0]
