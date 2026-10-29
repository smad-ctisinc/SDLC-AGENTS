
# Step 01.4 — Implement Foundation Phase 2: Agent Registry

You are implementing Phase 2 of the SDLC Multi-Agent Platform Foundation.

Current branch: feature/agent-foundation

## Context

Phase 1 is complete:

- Python packaging configured.
- Pydantic contract models implemented.
- Strict YAML and JSON Schema validation implemented.
- Provider-independent AgentDefinition implemented.
- 110 tests passed.

Before implementing:

1. Read AGENTS.md and CLAUDE.md.
2. Read docs/architecture/master-architecture.md.
3. Inspect the existing Phase 1 models and validation utilities.
4. Reuse existing implementations rather than duplicating logic.

## Objective

Implement a reusable Agent Registry that discovers, validates, loads, and lists agent definitions.

## Requirements

### 1. Agent Discovery

Discover agents from explicitly configured directories.

Expected agent structure:

agents/
  agent-name/
    agent.md
    contract.yaml

Support configurable search roots, including test fixture directories.

Do not hardcode agent names.

### 2. Agent Loading

Implement methods equivalent to:

- discover()
- list_agents()
- load(agent_id, version=None)
- get_metadata(agent_id)

Reuse existing AgentDefinition and contract validation models.

### 3. Validation

Validate:

- Required agent files.
- YAML contract structure.
- Agent ID and directory naming.
- Supported contract versions.
- Agent version compatibility.
- Duplicate agent identities.
- Malformed definitions.

Do not silently ignore invalid definitions.

### 4. Versioning

Support explicit agent versions.

If multiple versions are supported, use a documented deterministic resolution policy.

Do not automatically select versions using ambiguous ordering.

### 5. Security

- Restrict discovery to configured roots.
- Prevent path traversal.
- Reject symlink/junction escapes.
- Do not execute code found in agent definitions.
- Treat agent.md as untrusted content.
- Do not load arbitrary Python modules or shell commands from contracts.

### 6. Registry Interface

Define a typed registry interface.

Keep the registry independent of:

- CLI
- LLM providers
- Agent runner
- LangGraph
- MCP implementations

### 7. Tests

Create tests under tests/foundation/.

Cover:

- Successful discovery
- Successful loading
- Invalid YAML
- Missing files
- Duplicate IDs
- Unsupported versions
- Invalid agent names
- Empty directories
- Path traversal
- Symlink handling
- Multiple configured roots
- Deterministic listing

Use synthetic agent fixtures only.

## Acceptance Criteria

1. Registry discovers valid synthetic agents.
2. Registry loads and validates contracts.
3. Registry returns structured agent metadata.
4. Invalid definitions produce clear errors.
5. Registry does not execute agent code.
6. All existing Phase 1 tests continue passing.
7. New registry tests pass.
8. Editable and wheel installation remain functional.

## Constraints

Do not implement:

- Agent execution runner
- Tool broker
- LLM provider integrations
- Project Discovery Agent
- LangGraph
- RAG
- AWS integrations

## Execution Rules

- Work only on feature/agent-foundation.
- Do not switch branches.
- Do not commit or push.
- Do not modify unrelated files.
- Use the existing virtual environment.
- Implement Phase 2 only.
- Run all relevant tests.
- Report changed files, test results, limitations, and architectural decisions.
- Stop after Phase 2 and wait for approval.

Proceed with Phase 2 implementation.
