
# Step 01.6 — Foundation Phase 4: Agent Runner & Fake Provider

You are implementing Phase 4 of the SDLC Multi-Agent Platform Foundation.

Current branch: feature/agent-foundation

## Context

Completed:

- Phase 1: Packaging, contracts, and validation
- Phase 2: Agent Registry
- Phase 3: Security Policy Engine and Tool Broker

Before implementation:

1. Read AGENTS.md and CLAUDE.md.
2. Read docs/architecture/master-architecture.md.
3. Inspect existing contracts, registry, policy engine, tool broker, and tests.
4. Reuse existing models and utilities.
5. Preserve backward compatibility.

## Objective

Implement a reusable, asynchronous Agent Runner capable of executing trusted agent executors through validated contracts and enforced permissions.

Implement a fake LLM provider for deterministic testing.

## 1. Agent Runner

Implement a typed asynchronous runner supporting:

- run(request) -> RunResult
- Agent resolution through the existing registry
- Input schema validation
- Trusted executor resolution
- Effective permission calculation
- Execution context creation
- Tool broker integration
- Execution timeout handling
- Cancellation handling
- Output schema validation
- Structured execution results
- Sanitized error reporting

Do not allow agent contracts to specify arbitrary Python imports, shell commands, or executable paths.

## 2. Trusted Executor Interface

Implement an AgentExecutor protocol with:

- AgentDefinition
- Validated inputs
- ExecutionContext
- Structured execution output

Create a trusted executor registry or explicit executor mapping.

Executors must be registered by the host application.

An agent contract cannot register or authorize its own executor.

## 3. Synthetic Foundation Executor

Implement a deterministic foundation-probe executor.

Input example:

{
  "project_id": "sample-project"
}

Output example:

{
  "project_id": "sample-project",
  "status": "ok"
}

Use the existing foundation-probe contract fixture.

Do not implement any real SDLC agent yet.

## 4. Fake LLM Provider

Define a provider-independent LLMProvider interface.

Implement a fake provider that:

- Returns predefined responses
- Supports deterministic test scenarios
- Tracks model-call usage
- Simulates provider failures
- Simulates timeout and cancellation behavior
- Does not make network calls

Do not integrate actual OpenAI or Anthropic SDKs yet.

## 5. Execution Context

Reuse or extend the existing execution context.

Include:

- project_id
- run_id
- agent_id and version
- Effective permissions
- Approved tools
- Tool-call budget
- Model-call budget
- Deadline
- Cancellation state
- Sanitized execution metadata

Avoid duplicating existing Phase 3 security context models.

## 6. Execution Lifecycle

Implement:

1. Load agent definition.
2. Validate contract and input.
3. Resolve trusted executor.
4. Calculate effective permissions.
5. Create execution context.
6. Execute agent within configured limits.
7. Route tool calls through the existing broker.
8. Validate output against the contract.
9. Return structured RunResult.

Use explicit statuses:

- succeeded
- failed
- timed_out
- cancelled
- approval_required

Only return approval_required when an actual approval requirement is detected.

## 7. Security

- Deny unauthorized tools.
- Enforce existing project policies.
- Do not bypass the tool broker.
- Do not expose secrets in errors.
- Do not log full source content.
- Do not send data to external LLM providers.
- Do not perform arbitrary subprocess execution.
- Enforce model-call budgets through a mediated provider interface.
- Ensure timeouts and cancellation do not permit further broker calls.

Do not claim hard process isolation; trusted executors remain in-process.

## 8. Observability

Capture:

- run_id
- project_id
- agent_id
- agent version
- Definition digest
- Start and end timestamps
- Execution duration
- Final status
- Tool-call count
- Model-call count
- Token usage when available
- Sanitized error details

Keep telemetry independent of any specific observability vendor.

## 9. Tests

Add pytest tests under tests/foundation/.

Test:

- Successful execution
- Unknown agent
- Unknown executor
- Invalid inputs
- Invalid outputs
- Permission denial
- Unauthorized tool calls
- Tool-call budget exhaustion
- Model-call budget exhaustion
- Executor failures
- Provider failures
- Timeouts
- Cancellation
- Concurrent independent runs
- Result metadata correctness
- Error redaction

Ensure existing Phase 1–3 tests remain passing.

## 10. Acceptance Criteria

1. foundation-probe executes successfully through the Agent Runner.
2. Agent Registry and Phase 3 security controls are reused.
3. Inputs and outputs are validated.
4. Unauthorized operations are denied.
5. Timeouts, cancellation, and errors produce structured results.
6. Fake provider works without external API calls.
7. No real LLM SDK is required.
8. All existing and new tests pass.
9. Editable and wheel installation tests pass.

## Constraints

Do not implement:

- Project Discovery Agent
- Real LLM provider integrations
- LangGraph
- RAG/vector databases
- Jira/Bitbucket integrations
- AWS
- Persistent execution storage
- CLI execution commands (Phase 6)

## Execution Rules

- Work only on feature/agent-foundation.
- Do not switch branches.
- Do not commit or push.
- Do not modify unrelated files.
- Use the existing virtual environment.
- Implement Phase 4 only.
- Run the full test suite.
- Report changed files, tests, limitations, and design decisions.
- Stop after Phase 4 and wait for approval.

Proceed with Phase 4 implementation.
