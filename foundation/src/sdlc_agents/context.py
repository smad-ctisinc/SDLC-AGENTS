"""Project-scoped context and source-grounded observations, independent of storage."""

from pathlib import PurePosixPath, PureWindowsPath
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .contracts import AgentId, AgentVersion, ContractModel, NonNegativeInt, PositiveInt, Text, _is_json_value


class SourceReference(ContractModel):
    """Evidence location and digest supplied by the producer, not read by storage."""

    source_id: Text
    path: Text
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    source_revision: Text | None = None
    start_line: PositiveInt | None = None
    end_line: PositiveInt | None = None

    @field_validator("path")
    @classmethod
    def relative_path(cls, value: str) -> str:
        if (PurePosixPath(value).is_absolute() or PureWindowsPath(value).drive
                or "\\" in value or ":" in value or "\x00" in value
                or any(part in ("", ".", "..") for part in value.split("/"))):
            raise ValueError("Source paths must be project-relative slash paths")
        return value

    @model_validator(mode="after")
    def line_range(self) -> Self:
        if self.end_line is not None and (self.start_line is None or self.end_line < self.start_line):
            raise ValueError("End line requires a start line and must not precede it")
        return self


class Provenance(ContractModel):
    agent_id: AgentId
    agent_version: AgentVersion
    run_id: Text
    recorded_at: AwareDatetime


class Observation(ContractModel):
    observation_id: Text
    statement: Text
    classification: Literal["verified", "inferred"]
    source_ids: list[Text] = Field(min_length=1)
    provenance: Provenance


class ProjectContext(ContractModel):
    """Portable JSON knowledge snapshot scoped to exactly one project.

    Storage owns revisions; producers own evidence and epistemic classification.
    Identifiers are opaque values, not paths or authorization grants.
    """

    project_id: Text
    schema_version: Literal["1"] = "1"
    revision: NonNegativeInt = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
    components: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    source_references: list[SourceReference] = Field(default_factory=list)

    @field_validator("metadata", "components", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if not _is_json_value(value):
            raise ValueError("Context must contain only finite JSON values")
        return value

    @model_validator(mode="after")
    def evidence_integrity(self) -> Self:
        sources = [source.source_id for source in self.source_references]
        observations = [item.observation_id for item in self.observations]
        if len(sources) != len(set(sources)) or len(observations) != len(set(observations)):
            raise ValueError("Source and observation IDs must be unique within a project")
        for item in self.observations:
            if len(item.source_ids) != len(set(item.source_ids)) or not set(item.source_ids).issubset(sources):
                raise ValueError("Observation evidence must name unique existing source references")
        return self
