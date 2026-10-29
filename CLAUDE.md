
# Claude Code — SDLC Agents

This repository implements a reusable, technology-agnostic SDLC Multi-Agent Platform.

## Shared Instructions

Read and follow `AGENTS.md` for the primary repository instructions.

Read `docs/architecture/master-architecture.md` when making architectural decisions.

## Compatibility Requirements

- Keep reusable agent definitions independent of Claude-specific functionality.
- Do not duplicate agent business logic in `.claude/agents/`.
- Use portable Markdown and YAML contracts.
- Use provider adapters for model-specific behavior.
- Keep the platform compatible with OpenAI Codex and future AI providers.

## Development Rules

- Follow the implementation and security rules in `AGENTS.md`.
- Do not change Git branches, commit, or push without approval.
- Propose architecture changes before implementation.
- Execute only the requested phase.
- Wait for approval before proceeding to the next phase.
