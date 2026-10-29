"""Authorize, validate, and mediate individual tool calls; not an agent runner."""

import asyncio
import os
from collections.abc import Sequence
from pathlib import Path
from threading import Lock

from pydantic import TypeAdapter

from ..contracts import AgentContract, PayloadValidationError, Text
from ..execution import ErrorDetails
from ..paths import check_path
from ..redaction import redact
from ..security import AccessGrant, PermissionDenied, ProjectPolicy, authorize_tool
from .base import ToolAccessError, ToolAdapter, ToolCall, ToolContext, ToolDescriptor, ToolResult




class ToolBroker:
    """One trusted composition per project/run, with independent call accounting.

    Construction snapshots all authority and descriptors. Create a new broker
    after authorization changes; no caller-supplied policy/context is dispatched.
    """

    def __init__(self, *, contract: AgentContract, policy: ProjectPolicy,
                 grant: AccessGrant, run_id: str, adapters: Sequence[ToolAdapter]) -> None:
        self._contract = AgentContract.model_validate(contract.model_dump(by_alias=True))
        self._policy = ProjectPolicy.model_validate(policy.model_dump())
        self._grant = AccessGrant.model_validate(grant.model_dump())
        self._run_id = TypeAdapter(Text).validate_python(run_id, strict=True)
        if self._policy.project_id != self._grant.project_id:
            raise ValueError("Policy and grant project IDs must match")
        root = Path(os.path.abspath(self._policy.source_root))
        check_path(root, directory=True)
        self._context = ToolContext(
            self._policy.project_id, self._run_id, root, self._policy.max_read_bytes,
            tuple(self._policy.excluded_patterns),
        )
        self._adapters: dict[str, tuple[ToolAdapter, ToolDescriptor]] = {}
        for adapter in adapters:
            descriptor = ToolDescriptor.model_validate(adapter.descriptor.model_dump(by_alias=True))
            if descriptor.tool_id in self._adapters:
                raise ValueError("Duplicate tool registration")
            self._adapters[descriptor.tool_id] = (adapter, descriptor)
        self._limit = min(self._contract.execution.max_tool_calls, self._policy.max_tool_calls)
        self._calls = 0
        self._closed = False
        self._lock = Lock()

    def close(self) -> None:
        """Reject new calls after a run completes; active calls are owned by runner."""
        with self._lock:
            self._closed = True

    def validate_contract_access(self) -> None:
        """Preflight declared tools without executing any adapter."""
        for tool_id in self._contract.tools.allowed:
            if tool_id not in self._adapters:
                raise PermissionDenied("Declared tool is not registered")
            authorize_tool(tool_id, self._adapters[tool_id][1].required_capabilities,
                           self._contract, self._policy, self._grant)

    @property
    def calls_used(self) -> int:
        with self._lock:
            return self._calls

    async def call(self, request: ToolCall) -> ToolResult:
        # Snapshot mutable input so concurrent callers cannot alter an admitted call.
        request = ToolCall.model_validate(request.model_dump())

        def error(status: str, code: str, message: str) -> ToolResult:
            return ToolResult(project_id=self._policy.project_id, run_id=self._run_id,
                              tool_id=request.tool_id, status=status,
                              error=ErrorDetails(code=code, message=message))

        if (request.project_id, request.run_id) != (self._policy.project_id, self._run_id):
            return error("denied", "scope_mismatch", "Tool call belongs to another project or run")
        registered = self._adapters.get(request.tool_id)
        if registered is None:
            return error("denied", "unknown_tool", "Tool is not registered")
        adapter, descriptor = registered
        try:
            authorize_tool(request.tool_id, descriptor.required_capabilities,
                           self._contract, self._policy, self._grant)
        except PermissionDenied:
            return error("denied", "permission_denied", "Tool access is not authorized")
        try:
            descriptor.inputs.validate_payload(request.arguments)
        except PayloadValidationError:
            return error("failed", "invalid_arguments", "Arguments do not satisfy the tool schema")
        with self._lock:
            if self._closed:
                return error("denied", "run_closed", "Run has completed")
            exhausted = self._calls >= self._limit
            if not exhausted:
                self._calls += 1
        if exhausted:
            return error("denied", "budget_exhausted", "Tool call limit reached")
        try:
            data = await asyncio.wait_for(
                adapter.invoke(request.arguments, self._context),
                timeout=self._contract.execution.timeout_seconds,
            )
            descriptor.outputs.validate_payload(data)
            data = redact(data, tuple(sorted(self._policy.secret_values, key=len, reverse=True)))
            descriptor.outputs.validate_payload(data)
        except ToolAccessError:
            return error("denied", "resource_denied", "Resource is unavailable under the project policy")
        except TimeoutError:
            return error("failed", "tool_timeout", "Tool call exceeded its timeout")
        except Exception:
            # Never expose adapter exception strings, which may contain secrets.
            return error("failed", "tool_failed", "Tool failed or returned invalid output")
        return ToolResult(project_id=self._policy.project_id, run_id=self._run_id,
                          tool_id=request.tool_id, status="succeeded", data=data)
