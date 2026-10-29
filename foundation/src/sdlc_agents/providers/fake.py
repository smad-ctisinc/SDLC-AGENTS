"""A local configured response for deterministic foundation tests and examples."""

from .base import ModelRequest, ModelResponse, ProviderDescriptor


class FakeProvider:
    def __init__(self, response: ModelResponse) -> None:
        self._response = ModelResponse.model_validate(response.model_dump())

    @property
    def descriptor(self) -> ProviderDescriptor:
        return ProviderDescriptor(provider_id="fake", requires_network=False)

    async def generate(self, request: ModelRequest) -> ModelResponse:
        ModelRequest.model_validate(request.model_dump())
        return self._response.model_copy(deep=True)
