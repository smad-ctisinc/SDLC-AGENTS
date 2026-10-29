# SDLC-AGENTS

The goal of this project is to create SDLC agents. ChatGPT guides the work by providing implementation prompts and step-by-step instructions to use in this repository.

## Current implementation

Phase 1 provides an installable Python 3.11+ package, validated portable agent
contracts, a contract YAML loader, JSON input/output validation, project-scoped
request/context models, execution result models, and tests. Phases 2 through 5 add
the registry, permission-controlled tools, and a local runner with deterministic
fake implementations plus explicit JSON context storage. No actual SDLC agents or real providers are included.
Source is in `foundation/src/sdlc_agents/`, tests are in
`tests/foundation/`, and synthetic definitions are in `tests/fixtures/agents/`.

See the [foundation guide](docs/architecture/foundation-guide.md) for setup,
working examples, contract fields, extension instructions, and remaining phases.

From the repository root, using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
```

## Which file should contain what?

| File | Purpose | Recommendation |
| --- | --- | --- |
| `AGENTS.md` | Instructions Codex reads for repository work | Create now |
| `CLAUDE.md` | Instructions Claude Code reads | Create now |
| `docs/architecture/master-architecture.md` | Overall architecture and roadmap | Create now |
| `docs/prompts/01-agent-foundation.md` | Full agent-foundation implementation prompt provided by ChatGPT | Put the implementation prompt here |
| `.agents/skills/*/SKILL.md` | Reusable skills invoked by compatible assistants | Create when needed |
| `.claude/agents/*.md` | Claude-specific subagent definitions | Create later |

A prompt file is not automatically an agent. A prompt describes a task, whereas an agent definition describes a reusable role, its responsibilities, tools, and execution boundaries.

## Agent registry (Phase 2)

The registry discovers, validates, lists, and loads portable definitions from
explicit roots. It does not execute agents. See the [registry guide](docs/architecture/registry-guide.md)
for API examples, version selection, and security boundaries.

## Permission policy and tools (Phase 3)

The run-scoped tool broker enforces contract, host policy, and user grants before
invoking a trusted adapter. The built-in `fs.read_text` tool provides bounded,
read-only project file access. See the [tool security guide](docs/architecture/tool-security-guide.md)
for setup, extension boundaries, and limitations.

## Local runner (Phase 4)

The local runner executes explicitly bound trusted executors with validated
inputs/outputs, isolated per-run budgets, deadlines, and sanitized metadata.
Only deterministic fake provider/executor implementations are included. See the
[runner guide](docs/architecture/runner-guide.md) for a runnable synthetic example.

## Project context storage (Phase 5)

The JSON store provides project isolation, typed evidence/provenance, revision
checks, atomic snapshot updates, and explicit persistence of sanitized run metadata.
It is read-only unless enabled by trusted host code. See the
[context storage guide](docs/architecture/context-storage-guide.md) for examples and recovery limits.

## Foundation CLI (Phase 6)

Use `python -m sdlc_agents --help` or the installed `sdlc-agents` command.
The CLI lists and validates portable definitions and runs explicit synthetic
fixtures. See the [CLI guide](docs/architecture/cli-guide.md) for a complete example,
exit codes, and extension boundaries. Real providers and SDLC agents remain deferred.
