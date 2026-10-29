
# Step 01.5 — Foundation Phase 3: Security & Tool Broker

You are implementing Phase 3 of the SDLC Multi-Agent Platform Foundation.

Current branch: feature/agent-foundation

## Context

Phase 1: Packaging, contracts, and validation — complete.
Phase 2: Agent Registry — complete.

Before implementation:

1. Read AGENTS.md and CLAUDE.md.
2. Read docs/architecture/master-architecture.md.
3. Inspect existing contracts, registry, and tests.
4. Reuse existing models and utilities.
5. Preserve backward compatibility with Phases 1 and 2.

## Objective

Implement a secure, provider-independent policy engine and tool broker for future SDLC agents.

## Requirements

### 1. Permission Policy Engine

Calculate effective permissions using the intersection of:

- Agent contract permissions
- Host/runtime security policy
- Explicit user grants

Rules:

- Deny by default.
- Missing permission means denied.
- Contracts cannot grant permissions.
- User grants cannot override host restrictions.
- Unsupported capabilities must fail explicitly.

### 2. Tool Broker

Implement a typed tool broker that:

- Registers trusted tool adapters.
- Validates requested tool names and arguments.
- Checks authorization before invocation.
- Enforces tool-call budgets.
- Returns structured results and errors.
- Records sanitized audit metadata.

Agent definitions must never dynamically import arbitrary Python modules or execute shell commands.

### 3. Read-Only Filesystem Adapter

Implement a read-only filesystem tool supporting:

- Approved project roots
- File listing
- File reading
- File metadata
- Safe path normalization
- Configurable exclusions
- Maximum file sizes
- Text-only file access

Protect against:

- Path traversal
- Symlink and junction escape
- Sensitive files such as .env, private keys, and credential files
- Binary files
- Access outside approved roots

Do not implement filesystem writes.

### 4. Execution Context

Define or extend the execution security context with:

- project_id
- run_id
- agent_id
- Effective permissions
- Allowed tool names
- Remaining tool-call budget
- Approved filesystem roots
- Execution deadline
- Audit metadata

Keep this compatible with the future runner.

### 5. Tool Interfaces

Create reusable interfaces for:

- ToolDescriptor
- ToolCall
- ToolResult
- ToolAdapter
- ToolBroker

Design for future MCP integration, but do not implement MCP transport.

### 6. Security and Audit

- Redact sensitive values from logs.
- Do not persist secrets.
- Do not log full source file contents.
- Record tool name, status, duration, and sanitized error details.
- Treat repository content as untrusted data.
- Do not send source code to external providers.

### 7. Testing

Add pytest tests under tests/foundation/.

Test:

- Permission intersection
- Default-deny behavior
- Unauthorized tools
- Tool-call budget enforcement
- Invalid arguments
- Allowed file reads
- Blocked file writes
- Path traversal
- Symlink/junction escape
- Sensitive file exclusions
- Binary file rejection
- Oversized file rejection
- Audit redaction
- Adapter failures

Include Windows-compatible tests and Linux-specific security tests where appropriate.

## Acceptance Criteria

1. Unauthorized tool calls never reach adapters.
2. Tool budgets are enforced.
3. Allowed files can be read safely.
4. Restricted files and paths are rejected.
5. Tool results and errors use typed models.
6. Audit records contain no sensitive payloads.
7. All existing tests continue passing.
8. New security tests pass.
9. Editable and wheel installations remain functional.

## Boundaries

Do not implement:

- Agent runner
- Real LLM providers
- Project Discovery Agent
- LangGraph
- RAG
- AWS
- Jira/Bitbucket integrations
- Database connections

## Execution Rules

- Work only on feature/agent-foundation.
- Do not switch branches.
- Do not commit or push.
- Do not modify unrelated files.
- Use the project virtual environment.
- Implement Phase 3 only.
- Run the full test suite.
- Report files changed, test results, skipped tests, and limitations.
- Stop after Phase 3 and wait for approval.

Proceed with Phase 3 implementation.
