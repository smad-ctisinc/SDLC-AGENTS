# Permission policy and tools (Phase 3)

Phase 3 adds individual tool-call mediation, not an agent execution runner.
`ToolBroker` accepts trusted adapter instances and is bound to one project, one
run, one agent contract, and an authorization snapshot. The only built-in tool is
`fs.read_text`. No new dependencies are required.

## Example

Run this Python example from the repository root in the installed virtual
environment. It adjusts the synthetic contract in memory; it does not modify the
fixture or create a real SDLC agent.

```python
import asyncio
from pathlib import Path

from sdlc_agents import (
    AccessGrant, ProjectPolicy, ReadTextTool, ToolBroker, ToolCall, load_contract,
)

contract = load_contract("tests/fixtures/agents/foundation-probe/contract.yaml")
contract.tools.allowed = ["fs.read_text"]
contract.permissions.filesystem.read = True
contract.execution.max_tool_calls = 2

# These records must come from trusted host configuration and user authorization.
policy = ProjectPolicy(
    project_id="example", source_root=Path.cwd(),
    allowed_tools=["fs.read_text"], max_tool_calls=2,
    permissions={"filesystem": {"read": True}},
)
grant = AccessGrant(
    project_id="example", allowed_tools=["fs.read_text"],
    permissions={"filesystem": {"read": True}},
)
broker = ToolBroker(contract=contract, policy=policy, grant=grant,
                    run_id="example-run", adapters=[ReadTextTool()])
result = asyncio.run(broker.call(ToolCall(
    project_id="example", run_id="example-run", tool_id="fs.read_text",
    arguments={"path": "README.md"},
)))
assert result.status == "succeeded"
assert broker.calls_used == 1
```

## Authorization and lifecycle

The contract, host project policy, and user grant must all allow the exact tool
ID and every required capability. Defaults permit no tools or reads. Phase 3
supports only the `filesystem.read` capability; filesystem writes, external
writes, subprocesses, and network access are denied even if requested by every
layer. An agent cannot approve its own actions. User approval UI, durable approval
records, write tools, and revocation orchestration are not implemented.

Construct policies, grants, and adapters in trusted host code, never from model
output or repository instructions. The broker revalidates and snapshots those
models and tool descriptors at construction. Later mutation of caller-owned
models does not alter authorization. To change or revoke policy, trusted host
code must stop dispatching on the old broker; creation of a new broker alone does
not invalidate the old one.

Use one broker for the lifetime of a run. Creating a new broker for each call
would reset its budget. Calls must match the bound project and run IDs. Agent
identity and version are bound through the contract, not selected per tool call.
The source root is host-selected and cannot be supplied in tool arguments. An
immutable tool context is constructed internally; future adapters receive it
through the typed `ToolAdapter` protocol.

## Validation, budgets, and results

The broker checks scope, registration, permissions, and the tool's input JSON
Schema before calling the adapter. Output schemas reuse Phase 1 validation.
Call limits are the minimum of the contract and host limits; atomic reservation
prevents concurrent calls from exceeding the budget. Admission consumes one call,
including calls that later fail, time out, are cancelled, or reject a path. Calls
rejected before admission consume none. No retries occur automatically.

Adapters are awaited with the contract timeout applied per tool call. This is a
cooperative async timeout, not a hard process deadline; synchronous filesystem
I/O can block the event loop. The Phase 4 runner adds an overall run deadline. Cancellation propagates without refunding the reserved call.

`ToolResult` carries project/run/tool identity, status, either JSON data or
sanitized error details. Status is `succeeded`, `denied`, or `failed`. Error codes
distinguish scope mismatch, unknown tool, permission denial, invalid arguments,
budget exhaustion, resource denial, timeout, and adapter/output failures. Adapter
exception text and file contents are never included in diagnostics. Malformed
message objects fail model validation before dispatch; do not expose raw Pydantic
errors to untrusted clients.

## Filesystem boundaries

`fs.read_text` reads a regular UTF-8 file using a project-relative forward-slash
path. It rejects absolute paths, drive/UNC paths, traversal, empty/dot components,
alternate data streams, Windows device names, and ambiguous Windows filenames.
It rejects symlinks, reparse points/junctions, and hard-linked files. Root ancestor
checks are shared with the registry in `paths.py`; no registry dependency is
introduced into the tool layer.

Default exclusions cover `.git`, cloud/SSH credential directories, `.env*`, common
credential/secret filenames, and private-key/keystore suffixes. Host
`excluded_patterns` add exclusions but cannot remove defaults. Patterns match
case-insensitively against the entire relative path or individual components.
There is no write, shell, arbitrary import, directory traversal, or recursive
listing operation.

Reads default to 256 KiB and may be configured up to 16 MiB. Oversized files fail
instead of being truncated. Invalid UTF-8 and NUL-containing binary files fail.
File identity and link counts are checked when opening. As with the registry,
these checks are not an OS sandbox: trusted ownership and a stable filesystem are
required. Concurrent hostile path changes, mount changes, or unreliable network
filesystem identity semantics need stronger platform-specific isolation.

## Redaction and adapter trust

Before returning data, the broker masks host-supplied `secret_values`, common
password/token/key assignments, bearer tokens, and PEM private-key blocks. Output
is schema-validated again after redaction; incompatible output fails closed.
The broker does not log arguments, file contents, or exception text.

Redaction is best effort, can over-redact, and cannot recognize every secret.
Use exclusions and known secret values rather than treating pattern matching as a
data-loss-prevention guarantee. Returned file contents remain untrusted text and
cannot grant additional permissions.

Adapter code itself must be trusted. Python protocols and capability declarations
cannot constrain malicious in-process code; a falsely declared adapter could
perform effects outside the broker. Host code registers adapters explicitly; the
broker never imports implementation names from contracts. Agent callers should
receive only the broker, not direct adapter references or trusted contexts.
Technology-specific future adapters remain in root `adapters/`; the generic
filesystem primitive belongs to the shared foundation.

## Tests and remaining work

`tests/foundation/test_tools.py` covers authorization intersections, pre-dispatch
denial, project/run isolation, snapshot behavior, concurrent budgets, errors,
cancellation, timeout, path attacks, exclusions, hard links, junctions, bounded
reads, redaction, and unchanged source contents. Existing registry tests cover
shared symlink checks; native symlink cases skip where OS privileges forbid them.

Phase 4 is implemented; see [runner-guide.md](runner-guide.md). Phase 3
does not introduce providers, CLI, cloud, orchestration, persistent context, or
any actual SDLC agent.
