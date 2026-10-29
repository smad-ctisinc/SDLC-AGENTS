"""Deterministic executor for synthetic tests; never selected by agent name."""

from copy import deepcopy
from typing import Any

from .contracts import AgentDefinition, _is_json_value
from .providers import ModelRequest
from .runtime import ExecutionContext


class FakeExecutor:
    """Return configured data, or request a response from the mediated provider."""

    def __init__(self, output: dict[str, Any] | None = None, *, prompt: str | None = None) -> None:
        if (output is None) == (prompt is None):
            raise ValueError("Supply exactly one of output or prompt")
        if output is not None and (not isinstance(output, dict) or not _is_json_value(output)):
            raise ValueError("Fake output must be a JSON object")
        self._output = deepcopy(output)
        self._prompt = prompt

    async def execute(self, definition: AgentDefinition, inputs: dict[str, Any],
                      context: ExecutionContext) -> dict[str, Any]:
        if self._prompt is not None:
            response = await context.generate(ModelRequest(prompt=self._prompt))
            return response.content
        return deepcopy(self._output)
