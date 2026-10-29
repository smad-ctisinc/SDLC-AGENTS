
# Step 01.7 — Foundation Phase 5: Context & Execution Storage

You are implementing Phase 5 of the SDLC Multi-Agent Platform Foundation.

Current branch: feature/agent-foundation

## Context

Completed:

- Phase 1: Contracts and packaging
- Phase 2: Agent Registry
- Phase 3: Security and Tool Broker
- Phase 4: Agent Runner and Fake Provider

Before implementation:

1. Read AGENTS.md and CLAUDE.md.
2. Read docs/architecture/master-architecture.md.
3. Inspect existing execution context, run results, runner, and security models.
4. Reuse existing interfaces and validation utilities.
5. Preserve backward compatibility.

## Objective

Implement project-scoped context persistence and sanitized execution history using provider-independent storage interfaces and local JSON implementations.

## 1. Storage Interfaces

Define typed interfaces:

- ContextStore
- RunRecordStore

Do not couple agents or the runner to a specific storage backend.

Use asynchronous interfaces where appropriate.

## 2. Project Context Store

Implement:

- read(project_id, context_key)
- save(project_id, context_key, data, expected_revision)
- list_keys(project_id)

Requirements:

- Strict project isolation
- Optimistic revision checking
- Structured context metadata
- Schema/version information
- Creation and update timestamps
- Provenance including originating agent/run where available
- Configurable storage directory
- Deterministic serialization

Do not store raw secrets or unrestricted source-code dumps.

## 3. Run Record Store

Implement:

- save_run(run_record)
- get_run(project_id, run_id)
- list_runs(project_id, filters, pagination)

Persist sanitized execution metadata:

- run_id
- project_id
- agent_id and version
- definition digest
- status
- timestamps and duration
- tool-call count
- model-call count
- token usage where available
- sanitized error metadata

Do not persist full prompts, source files, credentials, or sensitive tool payloads.

## 4. Local JSON Storage

Implement filesystem-backed JSON storage for the MVP.

Requirements:

- Atomic writes using temporary files and replacement
- Safe project ID and context key handling
- Path traversal prevention
- Symlink/junction escape protection
- Restrictive file permissions where supported
- Consistent serialization
- Clear corruption and I/O errors
- No unsafe deserialization

Document that the MVP assumes a trusted local process and does not provide a hardened multi-tenant storage boundary.

## 5. Revision Handling

Support optimistic concurrency:

- New context starts at a documented revision.
- Updates require the expected current revision.
- Conflicting updates fail explicitly.
- No silent overwrites.

Document limitations of concurrent writers across processes.

## 6. Runner Integration

Integrate persistence with the Phase 4 runner through optional injected interfaces.

Requirements:

- Existing in-memory execution remains supported.
- Persist final run records when a store is configured.
- Do not persist unsanitized executor outputs.
- Storage errors must be visible and handled according to a documented policy.
- Do not turn a successful execution into a silently successful persistence failure.
- Keep execution and persistence responsibilities separate.

Do not implement automatic context injection into LLM prompts.

## 7. Security and Redaction

- Reuse Phase 3 redaction utilities.
- Do not persist secret-bearing request payloads.
- Do not persist raw source content.
- Prevent cross-project context and run access.
- Limit record sizes.
- Validate identifiers before filesystem access.
- Treat stored content as untrusted when reloaded.

## 8. Testing

Add pytest tests under tests/foundation/.

Test:

- Context creation and reading
- Context updates
- Revision conflicts
- Project isolation
- Missing context keys
- Listing keys
- Run record persistence
- Run history retrieval
- Filtering and pagination
- Invalid identifiers
- Path traversal
- Symlink/junction escape
- Corrupted JSON
- Atomic write behavior
- Storage failures
- Runner integration
- Redaction and sensitive-data handling

Use temporary directories for tests.

## 9. Acceptance Criteria

1. Project context survives process restarts.
2. Run records survive process restarts.
3. Cross-project access is denied.
4. Revision conflicts are detected.
5. Run history can be retrieved by project.
6. Existing runner behavior remains compatible.
7. No raw secrets or source payloads are persisted.
8. All Phase 1–4 tests continue passing.
9. Editable and wheel installation tests pass.

## Constraints

Do not implement:

- Project Discovery Agent
- Real LLM providers
- LangGraph
- RAG/vector databases
- PostgreSQL, DynamoDB, or S3 adapters
- AWS integrations
- CLI commands (Phase 6)

## Execution Rules

- Work only on feature/agent-foundation.
- Do not switch branches.
- Do not commit or push.
- Do not modify unrelated files.
- Use the project virtual environment.
- Implement Phase 5 only.
- Run the full test suite.
- Report changed files, test results, limitations, and design decisions.
- Stop after Phase 5 and wait for approval.

Proceed with Phase 5 implementation.
