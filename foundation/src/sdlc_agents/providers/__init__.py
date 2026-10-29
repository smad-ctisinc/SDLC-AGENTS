"""Provider-neutral messages and a deterministic local fake; no SDK imports."""

from .base import LLMProvider, ModelRequest, ModelResponse, ProviderDescriptor
from .fake import FakeProvider

__all__ = ["LLMProvider", "ModelRequest", "ModelResponse", "ProviderDescriptor", "FakeProvider"]
