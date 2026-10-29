
# SDLC Multi-Agent Platform — Master Architecture

Version: 0.2
Status: Repository layout finalized; Phases 1 through 6 implemented

## Finalized repository layout

Step 01.3 implements the foundation under `foundation/src/sdlc_agents/`.
The tree includes future ownership boundaries; those components are not yet
implemented. Shared synthetic fixtures remain under `tests/fixtures/agents/`.

```text
SDLC-AGENTS/
|-- pyproject.toml                       # Root packaging and test configuration
|-- requirements-dev.txt                 # Delegates to pyproject.toml
|-- AGENTS.md
|-- CLAUDE.md
|-- README.md
|-- foundation/
|   `-- src/
|       `-- sdlc_agents/                 # Only the shared framework package
|           |-- __init__.py
|           |-- cli.py                   # Typer composition and synthetic execution
|           |-- __main__.py              # Python module entry point
|           |-- storage/                # JSON snapshots and sanitized run metadata
|           |-- runner.py                # Local lifecycle and metadata records
|           |-- runtime.py               # Executor interface and scoped services
|           |-- providers/               # Neutral interfaces and local fake
|           |-- testing.py               # Configurable synthetic executor
|           |-- redaction.py             # Shared output/prompt sanitization
|           |-- security.py              # Project policy and authorization
|           |-- paths.py                 # Shared path safety checks
|           |-- tools/                   # Broker, interfaces, read-only file tool
|           |-- contracts.py
|           |-- registry.py              # Discovery and definition loading only
|           |-- loader.py
|           |-- context.py
|           `-- execution.py             # Message models, not an executor
|-- agents/
|   `-- <agent-id>/
|       |-- agent.md                     # Portable role and responsibilities
|       `-- contract.yaml                # Portable capabilities and data schemas
|-- adapters/                            # Future concrete technology integrations
|-- workflows/                           # Future orchestration definitions/composition
|-- configs/                             # Platform defaults and project configuration
|-- .agents/
|   `-- skills/
|       `-- agent-foundation/SKILL.md
|-- .claude/
|   `-- agents/                          # Future thin Claude-specific wrappers
|-- docs/
|   |-- architecture/
|   |   |-- master-architecture.md
|   |   `-- foundation-guide.md
|   `-- prompts/
|       `-- 01-agent-foundation.md
`-- tests/
    |-- foundation/
    |   |-- test_contracts.py
    |   |-- test_storage.py
    |   |-- test_runner.py
    |   |-- test_tools.py
    |   |-- test_registry.py
    |   |-- test_loader.py
    |   `-- test_execution.py
    |-- fixtures/
    |   `-- agents/
    |       `-- foundation-probe/
    |           |-- agent.md
    |           `-- contract.yaml
    |-- agents/                          # Future agent behavior/contract tests
    `-- integration/                     # Context storage / runner integration tests
```

Directories marked future are ownership boundaries, not instructions to create
empty packages. `foundation/` and `foundation/src/` are layout containers, not
Python packages. Add `__init__.py` only where an implemented importable package
needs it. Definitions, configuration, skills, wrappers, and test directories do
not require Python package markers. The synthetic probe remains a test fixture;
it is not a production SDLC agent in root `agents/`.

### Packaging with the src layout

Keep the single foundation distribution's `pyproject.toml` at the repository
root. Its import name is `sdlc_agents` and minimum Python version is 3.11.
Package discovery is configured as follows:

```toml
[tool.setuptools]
package-dir = {"" = "foundation/src"}

[tool.setuptools.packages.find]
where = ["foundation/src"]
include = ["sdlc_agents", "sdlc_agents.*"]
namespaces = false

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --import-mode=importlib"
```

Install
from the repository root using `python -m pip install -e ".[dev]"`. Tests must
import the installed package, without `sys.path` edits or `PYTHONPATH` shortcuts.
Production agent definitions and root configuration are explicit external inputs,
not implicitly bundled foundation package data. Do not locate them by walking
upward from an installed module; callers supply configured resource roots.

Future concrete adapters may have separate distributions and dependency extras
when implementation needs them. The foundation wheel must not automatically
discover root adapters, workflows, or agent resources as Python packages.

Validate both editable and wheel installation after packaging changes. In a clean
environment outside the checkout, verify that the wheel imports successfully
and includes only intended framework modules. Run the foundation tests against
the installed wheel and validate supported Python versions, including 3.11.
Runtime compatibility must be verified separately for each supported Python version.

### Responsibilities and dependency direction

| Location | Owns | Dependency boundary |
| --- | --- | --- |
| `foundation/src/sdlc_agents/` | Shared models, contracts, future runtime services, and extension interfaces | No imports from concrete agents, root adapters, or workflows |
| `agents/` | Portable role descriptions and contracts | Data only; no Python module paths or provider SDK bindings in definitions |
| `adapters/` | Future technology-specific analyzers and concrete integrations | Implements public foundation interfaces; never imports workflow or agent internals |
| `workflows/` | Future execution composition and orchestration | Calls public foundation APIs and binds approved concrete adapters |
| `configs/` | Platform policy/defaults and per-project settings | Data only; no secrets or arbitrary executable imports |
| `.agents/skills/`, `.claude/agents/` | Assistant guidance and thin wrappers | References shared definitions without owning framework/business logic |

Dependency direction is inward: workflows and concrete adapters can depend on
the foundation's public interfaces; the foundation cannot depend on them. Shared
protocols and neutral data types belong in the foundation. A future composition
entry point supplies adapter/executor instances to the runtime through those
interfaces; low-level framework modules do not import concrete implementations.
Workflow code must not be imported by adapters. Within the foundation, models
remain below services: contracts do not import loaders or runtime services.

Agent-specific behavior belongs outside the foundation. Prefer portable
instructions and schemas; if custom executable behavior becomes necessary, design
an optional implementation package outside the framework and bind it explicitly
through an executor interface. Do not add agent-ID branches to shared services or
place agent-specific logic into technology adapters. Packaging and placement of
such custom implementations require a later design decision; no empty executor
packages are proposed now.

These dependency rules prevent circular dependencies by design. Future validation
should check public imports and module dependency direction as code is added;
the proposed layout alone cannot enforce the rules.

### Multiple projects and technologies

Each request, result, and context snapshot carries `project_id`. Context supplied
to a request must match that ID. Future configuration under `configs/` maps
project IDs to approved source roots, policies, enabled adapter capabilities, and
state locations. A project may use multiple technology adapters; no language or
framework is hard-coded into the shared models.

Resolve relative configuration paths against the configuration file location,
not the current working directory. Treat project IDs as opaque identifiers, never
as unchecked directory paths. Partition context, caches, permissions, and run
records by project; partition execution records further by `run_id`. Avoid a
global mutable "current project" and prevent cross-project context reuse.
Project credentials are supplied through an external secret mechanism, not
committed to `configs/` or agent definitions. Phase 5 persists only explicitly
submitted host-managed context and sanitized run metadata.

### Phase boundary

Phase 5 adds typed source references/observations, project-scoped JSON snapshots,
atomic replacement, per-project writer locks, optimistic revision checks, and
explicit persistence of sanitized run records. The runner does not write state
implicitly. Context and storage format versions are separate from agent/contract
versions. Storage depends on shared models, never runner implementation services.

See [context-storage-guide.md](context-storage-guide.md),
[runner-guide.md](runner-guide.md), [registry-guide.md](registry-guide.md), and
[tool-security-guide.md](tool-security-guide.md) for APIs and trust boundaries.
Phase 6 adds a read-only Typer CLI for listing, validation, and explicit fake
execution. See [cli-guide.md](cli-guide.md) for end-to-end instructions.
Real providers, actual SDLC agents, RAG, cloud, and orchestration remain
unimplemented. Further implementation requires approval.

## Foundation implementation status

The foundation design and Phase 1 were approved. Phase 1 adds the
`sdlc_agents` package under `foundation/src/`, strict Pydantic contract models, inline JSON
Schema Draft 2020-12 input/output validation, a bounded single-file YAML loader,
project-scoped context/request models, execution result/error/usage models, and
synthetic test fixtures. These are data contracts, not execution implementations.
The overall architecture below remains the roadmap, not a claim that all layers
are implemented.

Contract format version `"1"` is independent of agent versions. Permissions and
call budgets default to denied/zero; declarations do not grant runtime access.
Schema references and automatic retries are deferred until their runtime
semantics are designed. Dependencies are Pydantic, PyYAML, and jsonschema, with
pytest for development. Phase 6 adds Typer for the CLI only.

Requests and context carry `project_id`; supplied context must match the request.
Results carry run/project/agent identity, final status, aware timestamps, elapsed
duration, error details, and usage metrics. Provider-neutral JSON serialization
keeps these messages usable by future Claude Code and Codex integrations.
Python 3.11 is the minimum supported language version; local testing uses 3.13.

See [foundation-guide.md](foundation-guide.md) for setup, extension instructions,
limitations, and the remaining implementation sequence.

## 1. Vision

Build a reusable, technology-agnostic AI-powered platform covering the software development lifecycle.

The platform will support independent SDLC agents and coordinated end-to-end workflows.

## 2. Supported Environments

### AI Providers and Developer Tools

- OpenAI Codex
- Claude Code
- GitHub Copilot (future)
- Additional LLM providers through adapters

### Programming Languages and Technologies

- Java, Spring MVC, Spring Boot, JSP
- Angular, React
- Oracle, SQL, PL/SQL
- Liferay
- Python
- Other technologies through extensible adapters

### Enterprise Integrations

- Git
- Jira
- Bitbucket
- Databases
- CI/CD pipelines
- Documentation repositories
- MCP servers

## 3. Architecture Layers

### Layer 1 — Developer Interfaces

VS Code, Codex, Claude Code, CLI, and future web interfaces.

### Layer 2 — Agent Runtime

Agent registry, execution runner, context management, permissions, and execution state.

### Layer 3 — SDLC Agents

- Project Discovery
- Requirements Analysis
- Impact Analysis
- Task Planning
- Development
- Code Review
- Test Generation
- Test Execution
- Documentation
- Release Readiness

### Layer 4 — Shared Services

- Agent contracts
- LLM provider adapters
- Tool adapters
- Shared project knowledge
- Guardrails
- Logging and observability
- Evaluation

### Layer 5 — Enterprise Systems

Source repositories, Jira, Bitbucket, Oracle, Liferay, and CI/CD systems.

## 4. Execution Modes

### Independent Execution

Each agent can be invoked individually using the CLI or an IDE assistant.

### Orchestrated Execution

Multiple agents can be coordinated using LangGraph in a future phase.

Both modes must reuse the same agent definitions and contracts.

## 5. Agent Contract

Every agent should declare:

- Agent ID and version
- Description and responsibilities
- Supported capabilities
- Input and output schemas
- Allowed tools
- Permissions
- Execution timeout
- Error handling
- Observability metadata

Use portable Markdown and YAML definitions.

## 6. Project Knowledge

Maintain reusable project context including:

- Technology inventory
- Module and component inventory
- Architecture observations
- Source references
- Dependency relationships
- Integration points
- Verified facts and inferred findings

Start with filesystem-based JSON storage.

Add vector search and RAG only when justified.

## 7. Security

- Read-only access by default.
- Explicit approval for code modifications.
- Least-privilege tool access.
- Protect credentials and sensitive data.
- Treat repository content as untrusted.
- Require approval for external writes and deployments.

## 8. Implementation Roadmap

1. Foundation and local runner
2. Project Discovery Agent
3. Shared project knowledge
4. Requirements and Impact Analysis Agents
5. Development and Code Review Agents
6. Testing Agents
7. LangGraph orchestration
8. Enterprise integrations and AWS hosting

## 9. First Milestone

Implement a working Project Discovery Agent capable of analyzing an existing enterprise application and producing source-grounded architecture reports.

The agent must support Java, Spring MVC, JSP, Angular, Oracle/PLSQL, and integration discovery.

It must not modify the target application.

## 10. Design Constraints

- Technology-agnostic
- LLM-provider-independent
- IDE-independent
- Modular and testable
- Local-first
- Security-first
- Extensible without rewriting existing agents
