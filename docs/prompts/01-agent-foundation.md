
# Task 01 — Design the SDLC Agent Foundation

## Role

You are a Principal AI Platform Architect and Senior Python Engineer.

Your task is to design the initial foundation for the SDLC Multi-Agent Platform.

## Required Context

Before starting:

1. Read `AGENTS.md`.
2. Read `docs/architecture/master-architecture.md`.
3. Inspect the existing repository structure.
4. Identify any existing implementations or configurations.

## Objective

Design a minimal, extensible framework for reusable SDLC agents.

The framework must support independent agents today and multi-agent orchestration in the future.

## Architecture Requirements

### 1. Portable Agent Definitions

Design reusable agent definitions using:

- agent.md
- contract.yaml

Contracts must define:

- Agent identity and version
- Capabilities
- Required inputs
- Output schema
- Allowed tools
- Permissions
- Execution timeout
- Error handling

### 2. Agent Registry

Design a registry that can:

- Discover available agents
- Load agent definitions
- Validate contracts
- Return agent metadata

### 3. Agent Runner

Design an execution interface that:

- Accepts an agent ID and input
- Loads the agent contract
- Validates permissions
- Executes the agent
- Returns structured output
- Records execution metadata

### 4. LLM Provider Abstraction

Design an interface supporting:

- OpenAI
- Anthropic
- Future providers

Do not tightly couple agent logic to any specific model SDK.

### 5. Tool Abstraction

Design interfaces for:

- Filesystem
- Git
- MCP tools
- Future Jira, Bitbucket, and database integrations

### 6. Shared Context

Design interfaces for:

- Project metadata
- Component inventory
- Architecture knowledge
- Source references
- Future RAG integration

Use JSON-based local storage initially.

### 7. IDE Compatibility

Explain how:

- Codex uses `AGENTS.md`
- Claude Code uses `CLAUDE.md`
- Both can reference shared portable agent definitions
- Future tools can integrate without rewriting the agents

### 8. Security

Design:

- Read-only execution defaults
- Tool permission enforcement
- Sensitive file exclusions
- Path safety
- Secret redaction
- Human approval boundaries

### 9. Testing

Define a testing strategy using pytest.

Include contract validation, registry, runner, permissions, and adapter testing.

## Expected Deliverables

Provide:

1. Proposed repository directory structure.
2. Explanation of each major component.
3. Sample agent contract YAML.
4. Python interface definitions.
5. Agent execution lifecycle.
6. Claude/Codex compatibility approach.
7. Foundation implementation sequence.
8. Architectural risks and trade-offs.

## Constraints

- Use Python 3.11+.
- Prefer Pydantic, YAML, Typer, and pytest.
- Keep the design simple and extensible.
- Do not implement Project Discovery yet.
- Do not implement LangGraph, RAG, AWS, or enterprise integrations yet.
- Do not add unnecessary dependencies.

## Execution Instructions

IMPORTANT:

1. Perform architecture analysis only.
2. Do not create, modify, or delete files.
3. Do not install dependencies.
4. Do not change Git branches.
5. Do not commit or push.
6. Present the proposed architecture and implementation plan.
7. Wait for my approval before writing code.

Start with the architecture proposal only.
