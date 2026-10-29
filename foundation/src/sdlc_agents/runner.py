"""Local execution lifecycle using explicit trusted bindings and scoped services."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from threading import Lock
from typing import Protocol
from uuid import uuid4

from .contracts import AgentContract, AgentDefinition, PayloadValidationError
from .execution import ErrorDetails, ExecutionRequest, ExecutionResult, RunRecord, UsageMetrics
from .providers import LLMProvider, ProviderDescriptor
from .redaction import redact
from .registry import AgentNotFoundError, AgentRegistry, AmbiguousAgentVersionError, RegistryError
from .runtime import AgentExecutor, ExecutionContext, RunFailure
from .security import AccessGrant, PermissionDenied, ProjectPolicy
from .tools import ToolAdapter, ToolBroker




class AgentRunner(Protocol):
    async def run(self, request: ExecutionRequest) -> ExecutionResult: ...


def _preflight(contract: AgentContract, policy: ProjectPolicy, grant: AccessGrant) -> None:
    requested = contract.permissions
    if requested.filesystem.write or requested.network or requested.subprocess or requested.external_write:
        raise RunFailure("unsupported_permission")
    if requested.filesystem.read and not policy.permissions.filesystem.read:
        raise RunFailure("permission_denied")
    if not set(contract.tools.allowed).issubset(policy.allowed_tools):
        raise RunFailure("permission_denied")
    if (requested.filesystem.read and not grant.permissions.filesystem.read
            or not set(contract.tools.allowed).issubset(grant.allowed_tools)):
        raise RunFailure("approval_required")


class LocalAgentRunner:
    """Reuse one runner across projects; instantiate fresh executors per run.

    Bindings map exact (agent ID, version) pairs to factories. Contracts never
    select imports. Factories, executors, adapters, and providers must be trusted.
    """

    def __init__(self, *, registry: AgentRegistry,
                 executors: Mapping[tuple[str, str], Callable[[], AgentExecutor]],
                 policies: Mapping[str, ProjectPolicy],
                 grants: Mapping[str, AccessGrant] | None = None,
                 adapters: Sequence[ToolAdapter] = (),
                 provider_factory: Callable[[], LLMProvider] | None = None,
                 record_limit: int = 1000) -> None:
        if type(record_limit) is not int or record_limit < 1:
            raise ValueError("record_limit must be a positive integer")
        self._registry = registry
        self._executors = dict(executors)
        self._policies = {key: ProjectPolicy.model_validate(value.model_dump()) for key, value in policies.items()}
        self._grants = {key: AccessGrant.model_validate(value.model_dump()) for key, value in (grants or {}).items()}
        for mapping in (self._policies, self._grants):
            if any(key != value.project_id for key, value in mapping.items()):
                raise ValueError("Configuration keys must match their project IDs")
        self._adapters = tuple(adapters)
        self._provider_factory = provider_factory
        self._records: deque[RunRecord] = deque(maxlen=record_limit)
        self._record_lock = Lock()

    def records(self) -> list[RunRecord]:
        with self._record_lock:
            return [record.model_copy(deep=True) for record in self._records]

    async def run(self, request: ExecutionRequest) -> ExecutionResult:
        # Malformed API messages raise validation errors before a run exists.
        request = ExecutionRequest.model_validate(request.model_dump())
        run_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        started = time.monotonic()
        resolved_version = None
        digest = None
        context = None
        broker = None
        output = None
        status = "failed"
        error = None
        stage = "initialization_failed"
        try:
            policy = self._policies.get(request.project_id)
            if policy is None:
                raise RunFailure("project_not_configured")
            grant = self._grants.get(request.project_id, AccessGrant(project_id=request.project_id))
            stage = "definition_invalid"
            loaded = self._registry.load(request.agent_id, request.agent_version)
            definition = AgentDefinition.model_validate(loaded.model_dump(by_alias=True))
            contract = definition.contract
            if contract.agent.id != request.agent_id or (
                request.agent_version is not None and request.agent_version != contract.agent.version
            ):
                raise RunFailure("identity_mismatch")
            resolved_version = contract.agent.version
            digest = hashlib.sha256(json.dumps(
                definition.model_dump(by_alias=True), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")).hexdigest()
            try:
                contract.validate_input(request.inputs)
            except PayloadValidationError:
                raise RunFailure("invalid_input") from None
            _preflight(contract, policy, grant)
            factory = self._executors.get((request.agent_id, resolved_version))
            if factory is None:
                raise RunFailure("executor_unavailable")
            deadline = started + contract.execution.timeout_seconds
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            async with asyncio.timeout(remaining):
                stage = "tool_configuration_invalid"
                broker = ToolBroker(contract=contract, policy=policy, grant=grant,
                                    run_id=run_id, adapters=self._adapters)
                broker.validate_contract_access()
                provider = None
                if contract.execution.max_model_calls > 0:
                    if policy.max_model_calls == 0:
                        raise RunFailure("model_budget_exhausted")
                    if self._provider_factory is None:
                        raise RunFailure("provider_unavailable")
                    stage = "provider_configuration_invalid"
                    provider = self._provider_factory()
                    descriptor = ProviderDescriptor.model_validate(provider.descriptor.model_dump())
                    if descriptor.requires_network:
                        raise RunFailure("remote_provider_unsupported")
                    if descriptor.provider_id not in policy.allowed_providers:
                        raise RunFailure("permission_denied")
                    if descriptor.provider_id not in grant.allowed_providers:
                        raise RunFailure("approval_required")
                context = ExecutionContext(
                    project_id=request.project_id, run_id=run_id, deadline=deadline,
                    project_context=request.context, broker=broker, provider=provider,
                    max_model_calls=min(contract.execution.max_model_calls, policy.max_model_calls),
                    secret_values=tuple(sorted(policy.secret_values, key=len, reverse=True)),
                )
                stage = "executor_failed"
                executor = factory()
                # Executors receive copies; mutations cannot weaken final validation.
                candidate = await executor.execute(
                    definition.model_copy(deep=True), request.model_copy(deep=True).inputs, context
                )
                if time.monotonic() >= deadline:
                    raise TimeoutError
                stage = "invalid_output"
                contract.validate_output(candidate)
                candidate = redact(candidate, tuple(sorted(policy.secret_values, key=len, reverse=True)))
                contract.validate_output(candidate)
                if time.monotonic() >= deadline:
                    raise TimeoutError
                output = candidate
                status = "succeeded"
        except AgentNotFoundError:
            error = ErrorDetails(code="agent_not_found", message="Agent ID or version was not found")
        except AmbiguousAgentVersionError:
            error = ErrorDetails(code="ambiguous_version", message="Specify an explicit agent version")
        except RegistryError:
            error = ErrorDetails(code="definition_invalid", message="Agent discovery or validation failed")
        except RunFailure as exc:
            # Only known codes escape; never echo arbitrary executor exception text.
            allowed = {"project_not_configured", "unsupported_permission", "permission_denied",
                       "approval_required", "executor_unavailable", "provider_unavailable",
                       "remote_provider_unsupported", "model_budget_exhausted", "invalid_input",
                       "identity_mismatch", "budget_exhausted", "resource_denied", "unknown_tool",
                       "scope_mismatch", "invalid_arguments", "tool_failed", "tool_timeout", "run_closed", "usage_accounting_failed"}
            code = exc.code if exc.code in allowed else "execution_failed"
            status = "approval_required" if code == "approval_required" else "failed"
            error = ErrorDetails(code=code, message="Execution could not complete under the current configuration")
        except PermissionDenied:
            error = ErrorDetails(code="permission_denied", message="Declared tool access was denied")
        except TimeoutError:
            status = "timed_out"
            error = ErrorDetails(code="execution_timeout", message="Execution exceeded its deadline")
        except asyncio.CancelledError:
            status = "cancelled"
            error = ErrorDetails(code="execution_cancelled", message="Execution was cancelled")
        except Exception:
            error = ErrorDetails(code=stage, message="Execution failed validation or a trusted component failed")
        finally:
            if context is not None:
                await context.close()
            elif broker is not None:
                broker.close()
        finished_at = max(started_at, datetime.now(timezone.utc))
        usage = context.usage if context is not None else UsageMetrics()
        # Also detect overflow when the executor catches a call failure.
        if context is not None and context.accounting_failed:
            status, output = "failed", None
            error = ErrorDetails(code="usage_accounting_failed",
                                 message="Execution usage could not be represented safely")
        result = ExecutionResult(
            run_id=run_id, project_id=request.project_id, agent_id=request.agent_id,
            agent_version=resolved_version, definition_digest=digest, status=status,
            started_at=started_at, finished_at=finished_at,
            duration_seconds=max(0.0, time.monotonic() - started), output=output, error=error,
            usage=usage,
        )
        record = RunRecord(**result.model_dump(exclude={"output", "error"}),
                           error_code=result.error.code if result.error else None)
        with self._record_lock:
            self._records.append(record)
        return result
