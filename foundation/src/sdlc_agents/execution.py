"""Execution message contracts, independent of any runner or provider SDK."""

from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, ConfigDict, Field, field_validator, model_validator

from .context import ProjectContext
from .contracts import AgentId, AgentVersion, ContractModel, NonNegativeInt, Text, _is_json_value

NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]
RunStatus = Literal["succeeded", "failed", "timed_out", "cancelled", "approval_required"]


class ExecutionRequest(ContractModel):
    """Inputs remain separate from project identity and shared context.

    A future runner must validate inputs against the selected agent contract.
    """

    project_id: Text
    agent_id: AgentId
    agent_version: AgentVersion | None = None
    inputs: dict[str, Any]
    context: ProjectContext | None = None

    @field_validator("inputs", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if not _is_json_value(value):
            raise ValueError("Inputs must contain only finite JSON values")
        return value

    @model_validator(mode="after")
    def check_project_scope(self) -> Self:
        if self.context is not None and self.context.project_id != self.project_id:
            raise ValueError("Request and context project_id must match")
        return self


class ErrorDetails(ContractModel):
    """Callers must sanitize messages/details before constructing this object."""

    code: Text
    message: Text
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if not _is_json_value(value):
            raise ValueError("Error details must contain only finite JSON values")
        return value


class UsageMetrics(ContractModel):
    """None means unavailable; zero means measured and no usage occurred."""

    model_calls: NonNegativeInt = 0
    tool_calls: NonNegativeInt = 0
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    estimated_cost_usd: NonNegativeFloat | None = None


class ExecutionResult(ContractModel):
    """Final outcome of one invocation, not an in-progress execution state.

    Duration is measured elapsed time (preferably monotonic), not derived from
    wall-clock timestamps. This avoids false precision if the system clock moves.
    """

    model_config = ConfigDict(frozen=True)

    run_id: Text
    project_id: Text
    agent_id: AgentId
    agent_version: AgentVersion | None = None
    definition_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    status: RunStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime
    duration_seconds: NonNegativeFloat
    output: dict[str, Any] | None = None
    error: ErrorDetails | None = None
    usage: UsageMetrics = Field(default_factory=UsageMetrics)

    @field_validator("output", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if value is not None and not _is_json_value(value):
            raise ValueError("Output must contain only finite JSON values")
        return value

    @model_validator(mode="after")
    def check_outcome(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at must not precede started_at")
        if self.status == "succeeded":
            if self.output is None or self.error is not None or self.agent_version is None:
                raise ValueError("Successful results require output, a resolved version, and no error")
        elif self.error is None or self.output is not None:
            raise ValueError("Non-success results require error details and no output")
        return self


class RunRecord(ContractModel):
    """Execution metadata only; no inputs, outputs, prompts, or exceptions."""

    model_config = ConfigDict(frozen=True)
    run_id: Text
    project_id: Text
    agent_id: AgentId
    agent_version: AgentVersion | None
    definition_digest: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None
    status: RunStatus
    started_at: AwareDatetime
    finished_at: AwareDatetime
    duration_seconds: NonNegativeFloat
    error_code: Text | None
    usage: UsageMetrics

    @model_validator(mode="after")
    def valid_metadata(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("Record end timestamp precedes start")
        if self.status == "succeeded":
            if self.agent_version is None or self.error_code is not None:
                raise ValueError("Successful records require a resolved version and no error")
        elif self.error_code is None:
            raise ValueError("Unsuccessful records require an error code")
        return self

