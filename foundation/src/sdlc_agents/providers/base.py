"""Minimal structured model interface, independent of any provider SDK."""

from typing import Any, Protocol

from pydantic import field_validator

from ..contracts import ContractModel, NonNegativeInt, Text, _is_json_value
from ..execution import NonNegativeFloat


class ProviderDescriptor(ContractModel):
    provider_id: Text
    requires_network: bool = True


class ModelRequest(ContractModel):
    prompt: Text


class ModelResponse(ContractModel):
    content: dict[str, Any]
    input_tokens: NonNegativeInt | None = None
    output_tokens: NonNegativeInt | None = None
    estimated_cost_usd: NonNegativeFloat | None = None

    @field_validator("content", mode="before")
    @classmethod
    def require_json(cls, value: Any) -> Any:
        if not _is_json_value(value):
            raise ValueError("Provider content must contain finite JSON values")
        return value


class LLMProvider(Protocol):
    @property
    def descriptor(self) -> ProviderDescriptor: ...

    async def generate(self, request: ModelRequest) -> ModelResponse: ...
