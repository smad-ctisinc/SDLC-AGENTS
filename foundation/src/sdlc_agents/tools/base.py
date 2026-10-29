"""Provider-independent tool messages and adapter protocol."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, field_validator, model_validator
from typing import Self

from ..contracts import ContractModel, PayloadSchema, Text, _is_json_value
from ..execution import ErrorDetails
from ..security import Capability


class ToolDescriptor(ContractModel):
    tool_id: Text
    required_capabilities: tuple[Capability, ...] = Field(min_length=1)
    inputs: PayloadSchema
    outputs: PayloadSchema


class ToolCall(ContractModel):
    project_id: Text
    run_id: Text
    tool_id: Text
    arguments: dict[str, Any]

    @field_validator("arguments", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if not _is_json_value(value):
            raise ValueError("Tool arguments must contain finite JSON values")
        return value


class ToolResult(ContractModel):
    project_id: Text
    run_id: Text
    tool_id: Text
    status: Literal["succeeded", "denied", "failed"]
    data: dict[str, Any] | None = None
    error: ErrorDetails | None = None

    @field_validator("data", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if value is not None and not _is_json_value(value):
            raise ValueError("Tool results must contain finite JSON values")
        return value

    @model_validator(mode="after")
    def check_outcome(self) -> Self:
        if self.status == "succeeded":
            if self.data is None or self.error is not None:
                raise ValueError("Successful tool results require data and no error")
        elif self.data is not None or self.error is None:
            raise ValueError("Unsuccessful tool results require error details and no data")
        return self


@dataclass(frozen=True)
class ToolContext:
    """Broker-created scope. Never accept this context from untrusted callers."""

    project_id: str
    run_id: str
    source_root: Path
    max_read_bytes: int
    excluded_patterns: tuple[str, ...]


class ToolAdapter(Protocol):
    @property
    def descriptor(self) -> ToolDescriptor: ...

    async def invoke(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]: ...


class ToolAccessError(ValueError):
    """Built-in adapter refused an unsafe path or excluded resource."""
