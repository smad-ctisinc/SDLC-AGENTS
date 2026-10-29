
# SDLC Multi-Agent Platform — Repository Instructions

## Project Purpose

Build a reusable, technology-agnostic SDLC Multi-Agent Platform.

The platform must support:

- OpenAI Codex
- Claude Code
- GitHub Copilot (future)
- Independent agents
- Multi-agent orchestration
- Local and future AWS-hosted execution

## Architecture Principles

1. Agent definitions must be independent of LLM providers.
2. Support multiple programming languages, frameworks, and databases.
3. Separate agent logic, orchestration, tools, and provider adapters.
4. Use reusable agent contracts with Markdown and YAML.
5. Support MCP-based and native tool integrations.
6. Maintain shared project knowledge across agents.
7. Follow security-first and least-privilege principles.
8. Prefer local execution before cloud deployment.
9. Keep all components modular, extensible, and testable.
10. Avoid unnecessary dependencies.

## Technology Stack

Preferred technologies:

- Python 3.11+
- Pydantic
- YAML
- pytest
- Typer for CLI
- LangGraph for future orchestration
- MCP for external tool integration
- AWS for future hosting

Do not introduce LangGraph, RAG, or AWS dependencies during the foundation phase unless explicitly approved.

## Development Guidelines

- Read `docs/architecture/master-architecture.md` when making architectural decisions.
- Follow the task instructions under `docs/prompts/`.
- Inspect existing code before making changes.
- Do not modify unrelated files.
- Do not switch Git branches without approval.
- Do not commit or push without approval.
- Never expose credentials or secrets.
- Use read-only operations by default.
- Write unit tests for implemented functionality.
- Explain architectural trade-offs before introducing new frameworks.

## Implementation Rules

- Work incrementally.
- Propose the design before implementation.
- Wait for explicit approval before creating implementation files.
- Run tests after each implementation phase.
- Report modified files, tests, and remaining tasks.

## Current Development Phase

Foundation architecture and shared contracts.

Do not implement individual SDLC agents until the foundation is approved.
