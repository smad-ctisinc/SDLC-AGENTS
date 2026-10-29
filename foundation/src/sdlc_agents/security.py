"""Deny-by-default policy for trusted, run-scoped tool composition."""

from pathlib import Path
from typing import Literal

from pydantic import Field

from .contracts import AgentContract, ContractModel, NonNegativeInt, Permissions, Text

Capability = Literal["filesystem.read", "filesystem.write", "network", "subprocess", "external_write"]


class AccessGrant(ContractModel):
    """Host-supplied record of authorization, never constructed from agent text."""

    project_id: Text
    allowed_tools: list[Text] = Field(default_factory=list)
    allowed_providers: list[Text] = Field(default_factory=list)
    permissions: Permissions = Field(default_factory=Permissions)


class ProjectPolicy(AccessGrant):
    """Host policy controls source root, additive exclusions, and resource limits."""

    source_root: Path
    max_tool_calls: NonNegativeInt = 0
    max_model_calls: NonNegativeInt = 0
    max_read_bytes: int = Field(default=256 * 1024, gt=0, le=16 * 1024 * 1024)
    excluded_patterns: list[Text] = Field(default_factory=list)
    secret_values: list[Text] = Field(default_factory=list, repr=False)


class PermissionDenied(ValueError):
    """A tool or capability was not authorized by every authority."""


def authorize_tool(
    tool_id: str,
    required: tuple[Capability, ...],
    contract: AgentContract,
    policy: ProjectPolicy,
    grant: AccessGrant,
) -> None:
    """Intersect explicit allowlists and capabilities; permissions never escalate.

    Phase 3 supports only read capabilities. Writes and other effects stay denied
    even if every layer requests them, until an approval/execution design exists.
    """
    if grant.project_id != policy.project_id:
        raise PermissionDenied("Project authorization mismatch")
    if any(tool_id not in allowed for allowed in (
        contract.tools.allowed, policy.allowed_tools, grant.allowed_tools
    )):
        raise PermissionDenied("Tool is not allowed by all authorization layers")
    if not required or any(capability != "filesystem.read" for capability in required):
        raise PermissionDenied("Tool capability is unsupported in this phase")
    if not all(permissions.filesystem.read for permissions in (
        contract.permissions, policy.permissions, grant.permissions
    )):
        raise PermissionDenied("Filesystem read permission is not granted by all layers")
