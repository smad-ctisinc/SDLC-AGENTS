"""Per-run mediated services and the executor interface; no agent business logic."""

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable
from threading import Lock
from typing import Any, Protocol, TypeVar

from .context import ProjectContext
from .contracts import AgentDefinition
from .execution import UsageMetrics
from .providers import LLMProvider, ModelRequest, ModelResponse
from .redaction import redact
from .tools import ToolBroker, ToolCall

T = TypeVar("T")


class RunFailure(ValueError):
    """Controlled execution failure. Only code is used in public diagnostics."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class ExecutionContext:
    """Fresh mediated services per run; closed when the executor finishes.

    Trusted executors must await calls and cooperate with cancellation. This is
    not an isolation boundary for arbitrary Python or unmanaged background tasks.
    """

    def __init__(self, *, project_id: str, run_id: str, deadline: float,
                 project_context: ProjectContext | None, broker: ToolBroker,
                 provider: LLMProvider | None, max_model_calls: int,
                 secret_values: tuple[str, ...]) -> None:
        self.project_id = project_id
        self.run_id = run_id
        self.deadline = deadline
        self._project_context = project_context.model_copy(deep=True) if project_context else None
        self._broker = broker
        self._provider = provider
        self._max_model_calls = max_model_calls
        self._secret_values = secret_values
        self._model_calls = 0
        self._responses: list[UsageMetrics] = []
        self._pending: set[asyncio.Task] = set()
        self._closed = False
        self._lock = Lock()

    @property
    def project_context(self) -> ProjectContext | None:
        return self._project_context.model_copy(deep=True) if self._project_context else None

    def _check_active(self) -> None:
        if self._closed:
            raise RunFailure("run_closed")
        if time.monotonic() >= self.deadline:
            raise TimeoutError

    async def _await_call(self, operation: Awaitable[T]) -> T:
        task = asyncio.create_task(operation)
        self._pending.add(task)
        try:
            return await asyncio.wait_for(task, max(0, self.deadline - time.monotonic()))
        finally:
            self._pending.discard(task)

    async def call_tool(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._check_active()
        result = await self._await_call(self._broker.call(ToolCall(
            project_id=self.project_id, run_id=self.run_id, tool_id=tool_id, arguments=arguments,
        )))
        if result.status != "succeeded":
            raise RunFailure(result.error.code)
        return result.data

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self._check_active()
        if self._provider is None:
            raise RunFailure("provider_unavailable")
        request = ModelRequest.model_validate(request.model_dump())
        request.prompt = redact(request.prompt, self._secret_values)
        with self._lock:
            if self._model_calls >= self._max_model_calls:
                raise RunFailure("model_budget_exhausted")
            self._model_calls += 1
        response = await self._await_call(self._provider.generate(request))
        response = ModelResponse.model_validate(response.model_dump())
        self._responses.append(UsageMetrics(input_tokens=response.input_tokens,
                                            output_tokens=response.output_tokens,
                                            estimated_cost_usd=response.estimated_cost_usd))
        if self.accounting_failed:
            raise RunFailure("usage_accounting_failed")
        response.content = redact(response.content, self._secret_values)
        return response

    @property
    def accounting_failed(self) -> bool:
        """Known costs must be representable, even when other calls failed."""
        return not math.isfinite(sum(response.estimated_cost_usd or 0.0
                                     for response in self._responses))

    @property
    def usage(self) -> UsageMetrics:
        def total(field: str):
            if len(self._responses) != self._model_calls:
                return None
            values = [getattr(response, field) for response in self._responses]
            if any(value is None for value in values):
                return None
            result = sum(values)
            return None if isinstance(result, float) and not math.isfinite(result) else result

        return UsageMetrics(model_calls=self._model_calls, tool_calls=self._broker.calls_used,
                            input_tokens=total("input_tokens"), output_tokens=total("output_tokens"),
                            estimated_cost_usd=total("estimated_cost_usd"))

    async def close(self) -> None:
        self._closed = True
        self._broker.close()
        pending = tuple(self._pending)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


class AgentExecutor(Protocol):
    async def execute(self, definition: AgentDefinition, inputs: dict[str, Any],
                      context: ExecutionContext) -> dict[str, Any]: ...
