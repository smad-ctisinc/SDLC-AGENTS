# Local agent runner (Phase 4)

Phase 4 implements a local execution lifecycle using the registry, portable
definitions, policy, and tool broker. It includes typed executor/provider
interfaces and configurable deterministic fakes. No real provider SDK, actual
SDLC agent, orchestration engine, implicit state persistence or CLI is included. Phase 5 provides explicit host-managed
[context storage](context-storage-guide.md).

## Run the synthetic fixture

Use the installed project virtual environment and run from the repository root:

```python
import asyncio
from pathlib import Path

from sdlc_agents import (
    ExecutionRequest, FileSystemAgentRegistry, LocalAgentRunner, ProjectPolicy,
)
from sdlc_agents.testing import FakeExecutor

runner = LocalAgentRunner(
    registry=FileSystemAgentRegistry(["tests/fixtures/agents"]),
    executors={
        ("foundation-probe", "0.1.0"): lambda: FakeExecutor(
            output={"project_id": "example", "status": "ok"}
        ),
    },
    policies={"example": ProjectPolicy(project_id="example", source_root=Path.cwd())},
)
result = asyncio.run(runner.run(ExecutionRequest(
    project_id="example", agent_id="foundation-probe",
    agent_version="0.1.0", inputs={"project_id": "example"},
)))
assert result.status == "succeeded"
assert result.output == {"project_id": "example", "status": "ok"}
assert runner.records()[0].run_id == result.run_id
```

The fixture requires no permissions or model/tool calls, so a default-deny policy
is sufficient. FakeExecutor returns a configured JSON object, not agent-specific
business logic. Matching project ID in input/output is the chosen executor's
responsibility; the runner enforces the project scope of its services and context.

## Interfaces and explicit binding

`AgentRunner` is the async `run(ExecutionRequest) -> ExecutionResult` protocol.
`LocalAgentRunner` is its local implementation. Trusted host code binds exact
`(agent_id, agent_version)` tuples to zero-argument executor factories. The runner
constructs a fresh executor per run. Agent YAML cannot name Python imports,
factories, shell commands, or provider SDKs. Unbound resolved versions fail with
`executor_unavailable`; there is no fallback to another version.

`AgentExecutor.execute(definition, inputs, context)` receives independent copies
of portable definitions and validated inputs. `ExecutionContext` provides:

- `project_id`, `run_id`, monotonic `deadline`, and a copied project context.
- `await call_tool(tool_id, arguments)` through the run's broker.
- `await generate(ModelRequest(prompt=...))` through a budgeted provider session.

Tool failure/denial raises controlled `RunFailure` when called through the
execution context. Trusted executors may deliberately handle failures; otherwise
they become failed run results. Do not obtain direct adapters/providers from
agent instructions or bypass these mediated services.

## Local fake provider

The `providers` package defines `LLMProvider`, `ProviderDescriptor`, `ModelRequest`,
and `ModelResponse`. `FakeProvider` returns a configured structured response with
optional token/cost metrics. It performs no networking and does not infer tokens.

To exercise model calls in synthetic tests or a future approved definition:

1. Declare a positive `execution.max_model_calls` in the contract.
2. Set positive `ProjectPolicy.max_model_calls` and list `"fake"` in the policy's
   `allowed_providers`.
3. List `"fake"` in the matching project's `AccessGrant.allowed_providers`.
4. Supply `provider_factory=lambda: FakeProvider(ModelResponse(...))` and an
   executor that calls `context.generate(...)`. `FakeExecutor(prompt="...")`
   provides that deterministic test path.

The effective model budget is the minimum of host and contract limits. Every
admitted call reserves budget before awaiting the provider, including failures
and cancellations. Concurrent calls share the per-run budget. Defaults allow no
model calls. Missing user authorization produces `approval_required`; host denial
produces a failed result. Remote providers are rejected even when network access
is requested. Provider factories and descriptors are trusted host configuration;
constructors must be side-effect-free. Only the generate method is mediated.

## Lifecycle and outcomes

1. Snapshot and validate the request, generate a UUID run ID, and start clocks.
2. Select the project's policy/grant, resolve the agent through the registry, and
   verify the returned identity matches the request.
3. Hash the normalized definition, validate input, and preflight permissions.
4. Resolve an exact executor binding, construct the broker and permitted local
   provider, and create isolated per-run services.
5. Execute within the contract deadline; validate and redact output, then validate
   the redacted output again.
6. Close services and cancel pending mediated calls. Return the result and retain
   a sanitized metadata record.

Results include project/run/agent identity, resolved version, SHA-256
`definition_digest`, status, UTC-aware timestamps, monotonic elapsed duration,
output or sanitized error, and usage metrics. If definition resolution fails,
`agent_version` and `definition_digest` are `None`; successful results still
require a resolved version. The digest identifies normalized contract/instructions,
not a filesystem signature or proof of trust. End timestamps are clamped to the
start time if the wall clock moves backwards; duration uses the monotonic clock.

Outcomes are `succeeded`, `failed`, `timed_out`, `cancelled`, or `approval_required`.
Examples of error codes include `agent_not_found`, `ambiguous_version`,
`invalid_input`, `invalid_output`, `permission_denied`, `executor_unavailable`,
`model_budget_exhausted`, and `execution_timeout`. Exceptions from executors or
providers do not expose raw messages. A malformed request object raises model
validation errors before creating a run. Invalid agent input returns a failed
run result without constructing its executor.

External task cancellation, once the runner has started, is deliberately converted
to a `cancelled` result after cleanup. Callers must inspect the returned status;
they should not expect `CancelledError` propagation from this runner API. A task
cancelled before its coroutine begins cannot produce a record. No retries or
durable pause/resume are implemented. `approval_required` is a final outcome;
trusted host code may authorize and submit a new run later.

## Usage and metadata records

Tool calls come from the broker's admitted-call counter; model calls come from
the per-run provider counter. Token counts and estimated USD costs are aggregated
only when available for every admitted model call. If a call fails or returns
unknown usage, the relevant total is `None`, not an invented zero. No-call totals
are zero. Fake-provider metrics are supplied test values, not measurements of a
real model. Error responses never include partial output.

`records()` returns deep copies of completed `RunRecord` metadata in completion
order. Records omit inputs, outputs, prompts, exception text, and source paths.
The default retention limit is 1,000 completed runs, configurable with
`record_limit`. Records are volatile and disappear when the runner is discarded.
The method is for trusted host code and is not an access-controlled multi-user
API. Phase 5 provides explicit host persistence through `JsonContextStore.save_run_record`.

## Limits and trust boundaries

Host configuration is snapshotted when constructing a runner. Changing an external
policy object does not revoke an existing runner's authority. Host code must stop
using the old runner and cancel active tasks when changing authorization. Every
run creates new brokers and budgets; context calls after completion fail closed.
Registry results, request context, inputs, and executor-facing definitions are
copied to prevent accidental cross-run mutation.

Timeouts and cancellation are cooperative, not process isolation. Synchronous
registry/filesystem I/O can block the event loop. Registry loading counts toward
elapsed deadline checks but cannot be interrupted mid-call. Trusted executors and
providers must honor cancellation, avoid unmanaged background work, and not
perform effects outside mediated services. Cleanup can take longer than the
deadline if an adapter ignores cancellation. Closed services reject subsequent
calls, but cannot sandbox arbitrary Python or undo already completed reads.

Redaction is shared with Phase 3 and is best effort. It runs on model prompts,
model responses, and final outputs; output schemas are rechecked after redaction.
Use exclusions and known secret values, and continue to treat all repository and
model content as untrusted data.

## Next phase

Phase 5 context storage is implemented; see [context-storage-guide.md](context-storage-guide.md).
Phase 6 CLI work requires separate approval. Real providers, actual SDLC agents,
cloud infrastructure, RAG, and orchestration remain unimplemented.
