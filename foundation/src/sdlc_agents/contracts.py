"""Version-one portable contracts and JSON payload validation.

These models declare requirements, not authorization. A future runtime must
intersect requested permissions with host policy and explicit user grants.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
AgentId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", max_length=64)]
AgentVersion = Annotated[str, StringConstraints(pattern=r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")]
PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
DIALECT = "https://json-schema.org/draft/2020-12/schema"


class ContractModel(BaseModel):
    """Reject typos and coercion instead of silently changing a contract."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_assignment=True)


class AgentIdentity(ContractModel):
    id: AgentId
    version: AgentVersion
    description: Text
    responsibilities: list[Text] = Field(min_length=1)
    capabilities: list[Text] = Field(min_length=1)


def _check_inline_schema(value: Any) -> None:
    """Version one reserves reference keywords and supports inline schemas only.

    This deliberately applies throughout the schema document, including examples.
    It avoids hidden filesystem/network dependencies during payload validation.
    """
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Schema object keys must be strings")
        if {"$ref", "$dynamicRef", "$recursiveRef"}.intersection(value):
            raise ValueError("Contract version 1 requires inline schemas; references are unsupported")
        if "$schema" in value and value["$schema"] != DIALECT:
            raise ValueError("Only JSON Schema Draft 2020-12 is supported")
        for child in value.values():
            _check_inline_schema(child)
    elif isinstance(value, list):
        for child in value:
            _check_inline_schema(child)


class PayloadSchema(ContractModel):
    # Avoid shadowing BaseModel.schema; preserve the portable YAML key via alias.
    json_schema: dict[str, Any] = Field(alias="schema")

    @field_validator("json_schema", mode="before")
    @classmethod
    def validate_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(value, dict) or not _is_json_value(value):
                raise ValueError("Schema must contain only JSON-native values")
            _check_inline_schema(value)
            Draft202012Validator.check_schema(value)
        except (TypeError, ValueError, RecursionError, SchemaError) as exc:
            raise ValueError("Invalid schema: use finite JSON values and an inline Draft 2020-12 schema") from exc
        if value.get("type") != "object":
            raise ValueError("The payload schema must declare type: object")
        return value

    def validate_payload(self, payload: object) -> None:
        """Validate without coercing values or exposing payload data in errors.

        JSON Schema 'format' is annotation-only in version one. Use structural
        constraints such as pattern, enum, and required for enforced rules.
        """
        if not _is_json_value(payload):
            raise PayloadValidationError("Payload must contain only finite JSON values")
        error = next(Draft202012Validator(self.json_schema).iter_errors(payload), None)
        if error is not None:
            # Do not interpolate jsonschema's message: it can include secrets.
            raise PayloadValidationError(f"Payload does not satisfy schema rule: {error.validator}")


def _is_json_value(value: object) -> bool:
    """Require JSON-native types, including string keys; reject cycles and NaN."""
    try:
        encoded = json.dumps(value, allow_nan=False)
        decoded = json.loads(encoded)
        return _same_json_types(value, decoded)
    except (TypeError, ValueError, RecursionError):
        return False


def _same_json_types(original: object, decoded: object) -> bool:
    if type(original) is not type(decoded):
        return False
    if isinstance(original, dict):
        return all(isinstance(key, str) and _same_json_types(item, decoded[key]) for key, item in original.items())
    if isinstance(original, list):
        return all(_same_json_types(left, right) for left, right in zip(original, decoded))
    return True


class PayloadValidationError(ValueError):
    """A payload failed validation; messages intentionally omit payload values."""


class ToolRequirements(ContractModel):
    allowed: list[Text] = Field(default_factory=list)

    @field_validator("allowed")
    @classmethod
    def unique_tools(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Allowed tool identifiers must be unique")
        return value


class FilesystemPermissions(ContractModel):
    read: bool = False
    write: bool = False


class Permissions(ContractModel):
    filesystem: FilesystemPermissions = Field(default_factory=FilesystemPermissions)
    network: bool = False
    subprocess: bool = False
    external_write: bool = False


class ExecutionLimits(ContractModel):
    timeout_seconds: PositiveInt
    max_tool_calls: NonNegativeInt = 0
    max_model_calls: NonNegativeInt = 0


class ErrorHandling(ContractModel):
    # Retry semantics need runtime support before a contract may request them.
    retry_policy: Literal["none"] = "none"


class Observability(ContractModel):
    tags: list[Text] = Field(default_factory=list)
    record_payloads: Literal[False] = False


class AgentContract(ContractModel):
    """Portable requirements shared by all future execution environments.

    Use model_validate() for parsed YAML; model_dump(by_alias=True) to export.
    Nested collections are mutable: revalidate after programmatic edits before
    treating a modified contract as trusted input.
    """

    contract_version: Literal["1"]
    agent: AgentIdentity
    inputs: PayloadSchema
    outputs: PayloadSchema
    tools: ToolRequirements = Field(default_factory=ToolRequirements)
    permissions: Permissions = Field(default_factory=Permissions)
    execution: ExecutionLimits
    errors: ErrorHandling = Field(default_factory=ErrorHandling)
    observability: Observability = Field(default_factory=Observability)

    def validate_input(self, payload: object) -> None:
        self.inputs.validate_payload(payload)

    def validate_output(self, payload: object) -> None:
        self.outputs.validate_payload(payload)


class AgentDefinition(ContractModel):
    """Portable Markdown instructions paired with a validated contract.

    No callable, module path, provider, or execution implementation is attached.
    The filesystem registry loads instructions and pairs them with the contract.
    """

    instructions: Text
    contract: AgentContract
