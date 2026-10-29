
# Step 01.8 — Foundation Phase 6: CLI & End-to-End Testing

You are implementing Phase 6 of the SDLC Multi-Agent Platform Foundation.

Current branch: feature/agent-foundation

## Context

Completed:

- Phase 1: Packaging and Contracts
- Phase 2: Agent Registry
- Phase 3: Security and Tool Broker
- Phase 4: Agent Runner and Fake Provider
- Phase 5: Context and Execution Storage

Before implementation:

1. Read AGENTS.md and CLAUDE.md.
2. Read docs/architecture/master-architecture.md.
3. Read docs/architecture/registry-guide.md.
4. Read docs/architecture/tool-security-guide.md.
5. Read docs/architecture/runner-guide.md.
6. Read docs/architecture/context-storage-guide.md.
7. Inspect existing models, registry, runner, security, and storage interfaces.
8. Reuse existing implementations and preserve backward compatibility.

## Objective

Deliver a usable local CLI and complete end-to-end tests for the SDLC Agent Foundation.

## 1. CLI

Implement a Typer-based CLI using the existing Python package.

Proposed commands:

- sdlc-agents --help
- sdlc-agents agents list
- sdlc-agents agents validate
- sdlc-agents agents show AGENT_ID
- sdlc-agents run AGENT_ID --project PROJECT_ID
- sdlc-agents runs list --project PROJECT_ID
- sdlc-agents runs show RUN_ID --project PROJECT_ID
- sdlc-agents context list --project PROJECT_ID
- sdlc-agents context show CONTEXT_KEY --project PROJECT_ID

Adjust exact command syntax to existing models where necessary.

## 2. CLI Configuration

Support:

- Configurable agent roots
- Configurable project storage directory
- Explicit project ID
- Agent version selection
- JSON input files
- Human-readable output
- Optional JSON output
- Environment variable configuration where appropriate

Configuration precedence must be documented.

Do not silently grant permissions based on configuration defaults.

## 3. Agent Execution

Connect the CLI to the existing registry, runner, trusted executor binding, security policy, and optional run-record storage.

Requirements:

- Execute foundation-probe through the CLI.
- Validate JSON inputs against agent contracts.
- Require explicit executor registration.
- Do not load executable code from agent definitions.
- Deny unapproved tool access.
- Do not enable real LLM calls.
- Return meaningful process exit codes.
- Display structured execution status and sanitized errors.

Use the existing synthetic fixture for the initial end-to-end flow.

## 4. Run History and Context

Provide read-only commands for:

- Listing persisted runs
- Viewing sanitized run metadata
- Listing project context keys
- Viewing approved context metadata

Avoid printing raw sensitive data or unrestricted context payloads by default.

## 5. End-to-End Tests

Test the complete pipeline:

CLI
→ Registry
→ Contract Validation
→ Security Policy
→ Runner
→ Trusted Fake Executor
→ Output Validation
→ Run Record Storage

Cover:

- Successful execution
- Invalid input
- Unknown agent
- Missing executor binding
- Unauthorized operations
- Invalid project ID
- Version selection
- Storage failure
- Persisted run retrieval
- Context isolation
- JSON output
- Exit codes

Use temporary directories and synthetic fixtures.

## 6. Cross-Platform Compatibility

Test on Windows where available.

Ensure:

- Paths work on Windows and Linux.
- CLI does not depend on Bash.
- No global Python dependencies.
- Python 3.11+ compatibility.
- Symlink/junction security behavior remains tested.

Document Windows PowerShell and Linux/macOS usage.

## 7. Documentation

Update:

- README.md
- Foundation architecture documentation
- CLI usage guide
- Installation instructions
- Troubleshooting instructions

Include an end-to-end example that a new developer can run locally.

## 8. Acceptance Criteria

1. CLI installs successfully.
2. CLI discovers and validates synthetic agents.
3. foundation-probe runs successfully from the terminal.
4. Execution results are structured and sanitized.
5. Run history can be retrieved after a new process starts.
6. Project context remains isolated.
7. No real provider or external API calls are required.
8. All existing tests remain passing.
9. Editable and wheel installation tests pass.
10. CLI end-to-end tests pass.

## Constraints

Do not implement:

- Real Project Discovery Agent
- Real OpenAI/Anthropic integrations
- LangGraph
- RAG
- AWS
- Jira/Bitbucket integrations
- Untrusted plugin execution
- Automatic repository modification

## Execution Rules

- Work only on feature/agent-foundation.
- Do not switch branches.
- Do not commit or push.
- Do not modify unrelated files.
- Use the existing virtual environment.
- Implement Phase 6 only.
- Run the full test suite.
- Report changed files, tests, skips, limitations, and design decisions.
- Stop after Phase 6 and wait for approval.

Proceed with Phase 6 implementation.
