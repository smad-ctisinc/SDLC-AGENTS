# Agent registry (Phase 2)

The registry reads portable agent definitions; it does not execute them. It reuses
`load_contract`, `AgentContract`, and `AgentDefinition` from Phase 1. No additional
dependencies are required.

## Usage

From the repository root after installing the package:

```python
from sdlc_agents import AgentRegistry, FileSystemAgentRegistry

registry: AgentRegistry = FileSystemAgentRegistry(["tests/fixtures/agents"])
metadata = registry.discover()
definition = registry.load("foundation-probe", version="0.1.0")
definition.contract.validate_input({"project_id": "example"})
summary = registry.get_metadata("foundation-probe")
assert registry.list_agents() == metadata
```

`AgentRegistry` is a typing protocol; `FileSystemAgentRegistry` is its concrete
filesystem implementation. None of these APIs depend on a CLI, runner, model
provider, MCP, or orchestration library.

## Discovery policy

- Pass one or more existing, distinct, non-overlapping roots. Relative roots are
  converted to absolute paths at construction, relative to the working directory.
- Discovery is one level deep. Every immediate subdirectory is an agent candidate
  and must contain regular files `agent.md` and `contract.yaml`. Empty roots return
  an empty list; empty candidate directories are errors.
- Directory names must satisfy the existing lowercase agent ID format and match
  the contract ID exactly. Hidden directories are not silently excluded.
- Ordinary files at a root, such as README.md, are ignored. Other files inside an
  agent directory are not interpreted or executed. The two required files alone
  define the agent.
- Every operation rescans and validates all roots. Any invalid candidate fails the
  operation, including when loading an unrelated valid agent. No partial result or
  previous successful snapshot is returned after failure.
- Discovery/listing returns `AgentMetadata` entries containing agent ID, version,
  contract version, description, capabilities, and absolute source directory.

## Version policy

Agent versions use Phase 1's numeric `major.minor.patch` format; version ranges,
prerelease suffixes, and aliases such as `latest` are unsupported. Contract format
version `"1"` is independent of the agent version. A valid agent version does not
imply compatibility with an execution implementation; that check belongs to a
future runtime, not this registry.

Multiple versions of the same agent ID can be supplied through different roots,
each containing a directory matching that ID. Duplicate `(agent_id, version)`
pairs are errors even if their content is identical. Root order gives no override
precedence.

`load(id, version)` and `get_metadata(id, version)` select an exact version. If a
version is omitted, exactly one version must exist; otherwise
`AmbiguousAgentVersionError` is raised. Missing IDs/versions raise
`AgentNotFoundError`. Both inherit `RegistryError`.

Listing order is agent ID, then numeric version components. This order is for
presentation only and never implies an automatic newest-version selection.

## Security and errors

The registry rejects symlinks and Windows reparse points (including junctions),
even when they point inside a root. Root ancestors, candidate directories, and
required files are checked. Lookup IDs and versions are validated before lookup
and are never used to construct arbitrary paths. Required files must be regular
files; instructions are bounded to 256 KiB and decoded as UTF-8 (BOM allowed).
The existing strict YAML loader enforces contract size, depth, duplicate-key,
schema, and version validation.

Markdown is returned as untrusted text. It cannot grant permissions or trigger
imports, shell commands, or tool execution. Consumers must retain this boundary.
Errors identify the failing path or category without including instruction or
contract payload excerpts. Applications may additionally redact filesystem paths
before presenting diagnostics outside the local environment.

Checks assume a stable local filesystem. They reject existing escapes but are
not an OS sandbox and cannot guarantee safety against a hostile process swapping
files between checking and opening. Keep configured roots under trusted ownership
and prevent concurrent writes during discovery. Descriptor-based platform-specific
isolation would be a separate enhancement. Results are fresh independent objects;
callers should revalidate after mutating nested models.

## Validation and next phase

Tests live in `tests/foundation/test_registry.py` and create only synthetic agents.
Native symlink tests skip explicitly where OS privileges prohibit link creation;
a simulated symlink-attribute check and real Windows junction tests cover the
rejection paths on Windows. Native POSIX symlink coverage still requires a host
that supports it. Python 3.11 syntax compatibility is checked separately from the
local Python 3.13 runtime tests.

Phase 3 policy/tool-broker work is documented in [tool-security-guide.md](tool-security-guide.md).
Agent execution integrations require separate approval. No registry operation executes an agent.
