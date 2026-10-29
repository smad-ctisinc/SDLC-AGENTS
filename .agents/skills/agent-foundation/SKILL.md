---
name: agent-foundation
description: Create or refine portable SDLC agent definitions and their shared framework in this repository. Use when building the foundation of an SDLC agent.
---

# Agent Foundation

Read the project instructions and relevant requirements in `docs/architecture/master-architecture.md` and `docs/prompts/01-agent-foundation.md` before implementing an agent. Empty documents do not establish architecture decisions.

Place portable agent definitions in `agents/`, shared framework code in `foundation/src/sdlc_agents/`, and foundation tests in `tests/foundation/` with shared synthetic fixtures in `tests/fixtures/agents/`. Keep Claude-specific subagent configuration in `.claude/agents/`.

For each agent, define its purpose, inputs, outputs, tool dependencies, and failure behavior based on the requested scope. Record shared architecture decisions in `docs/architecture/master-architecture.md` when implementation establishes them.
