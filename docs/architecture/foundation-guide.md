# Foundation guide

## Repository layout

Framework code lives in `foundation/src/sdlc_agents/`; foundation tests live in
`tests/foundation/`. Synthetic definitions remain in `tests/fixtures/agents/`.
Root `agents/` is reserved for future portable SDLC definitions. See the
[master architecture](master-architecture.md#finalized-repository-layout) for
adapter, workflow, configuration, and assistant integration boundaries.

## Current scope

Phase 1 implements package installation, portable contract models, payload
validation, a single-file YAML loader, project-scoped message models, and synthetic
test fixtures. Phase 2 adds discovery and loading through the
[agent registry](registry-guide.md). Phase 3 adds the
[permission policy and tool broker](tool-security-guide.md). Phase 4 adds a
[local runner with fake executor/provider support](runner-guide.md). Phase 5 adds
[project context and run-metadata storage](context-storage-guide.md). Real providers
and actual SDLC agents remain deferred.

Python 3.11 or newer is required. Development currently uses Python 3.13.0.
Compatibility with other Python versions is declared, but must be verified in a
future CI matrix before claiming tested support for every version.

## Set up and test

Run from the repository root in PowerShell:

```powershell
python -m venv .venv                  # Only if the environment does not exist
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pip check
```

Activation is optional because these commands select the environment directly.
On macOS/Linux, use `.venv/bin/python` instead. `requirements-dev.txt` is an
alternative installation entry point; dependency declarations live only in
`pyproject.toml`. Dependency ranges are not a reproducible lockfile.

## Read the code in this order

1. `tests/fixtures/agents/foundation-probe/agent.md`: the synthetic role.
2. Its `contract.yaml`: the portable data format.
3. `foundation/src/sdlc_agents/contracts.py`: typed sections and validation boundaries.
4. `foundation/src/sdlc_agents/loader.py`: explicit single-file loading, without discovery.
5. `foundation/src/sdlc_agents/context.py` and `execution.py`: shared data contracts only.
6. `tests/foundation/test_contracts.py`, `test_loader.py`, and `test_execution.py`: working
   examples and expected failures.

The installed import is `sdlc_agents`, even though its source lives under `foundation/src/`.
No provider SDK, IDE, or orchestration library is required.

## Validate a contract and payload

After installing the package, this Python example works from the repository root:

```python
from sdlc_agents import load_contract, PayloadValidationError

contract = load_contract("tests/fixtures/agents/foundation-probe/contract.yaml")
contract.validate_input({"project_id": "example"})
contract.validate_output({"project_id": "example", "status": "ok"})

# Preserve the portable `schema` key when serializing.
portable_data = contract.model_dump(by_alias=True)

try:
    contract.validate_input({"project_id": 42})
except PayloadValidationError as error:
    print(error)  # Rule name only; payload values are omitted.
```

This demonstrates validation, not execution. Matching an output project ID to the
input ID is an executor responsibility; independent schemas cannot enforce that
cross-payload relationship.

## Load a contract safely

`load_contract(path)` accepts one explicitly selected UTF-8 YAML file, including
UTF-8 with a BOM. It rejects files larger than 256 KiB, nesting deeper than 64
levels, duplicate keys at any level, non-string mapping keys, aliases, unsafe YAML
tags, multiple documents, and invalid contracts. Errors use `ContractLoadError`
and omit input excerpts. It neither discovers agents nor loads execution code.

The caller is responsible for authorizing the selected path. Path containment,
symlink rules, and approved roots belong to the future registry/security layers.

## Project-scoped execution messages

These models describe data exchanged by future integrations; they do not run
anything. All are independent of Claude, Codex, and provider SDKs.

```python
from sdlc_agents import ExecutionRequest, ProjectContext

request = ExecutionRequest(
    project_id="example",
    agent_id="foundation-probe",
    inputs={"project_id": "example"},
    context=ProjectContext(project_id="example", metadata={"language": "Java"}),
)
contract.validate_input(request.inputs)
```

`ExecutionRequest` requires `project_id`, `agent_id`, and JSON inputs. Agent version
and context are optional. If context is supplied, its project ID must match the
request. IDs are opaque identifiers, not filesystem paths or authorization.

`ProjectContext` contains project ID, revision, metadata, components, observations,
and source references. Metadata and component records remain extensible JSON
dictionaries; source references and observations now use typed evidence and
provenance models. See the Phase 5 guide for persistence and revision rules.

`ExecutionResult` requires run/project/agent identity and, for successful runs, a resolved agent version,
status, timezone-aware start/end timestamps, and nonnegative finite duration in
seconds. Status is one of `succeeded`, `failed`, `timed_out`, `cancelled`, or
`approval_required`. This is a final invocation outcome, not running state.
Successful results require an output object and no error; all other outcomes
require error details and no output. Partial outputs are not supported yet.

`ErrorDetails` carries a code, sanitized message, retryable flag, and JSON details.
The retryable flag describes an error; it does not authorize automatic retries.
`UsageMetrics` carries model/tool call counts, input/output tokens, and optional
estimated USD cost. Unavailable token/cost measurements are `None`, not zero.

Duration should come from a monotonic clock; it need not exactly equal wall-clock
timestamp subtraction. End timestamps cannot precede start timestamps. The local
runner clamps backwards wall-clock end timestamps and measures duration monotonically.

Use `model_dump_json()` and `model_validate_json()` for portable message round
trips. JSON timestamps use ISO 8601; Python construction requires aware `datetime`
objects. The Phase 4 runner validates inputs/outputs against the selected
contract and checks request/result identity consistency. Resolution failures have
no resolved agent version; resolved definitions also carry a SHA-256 digest.

## Portable agent definitions

`AgentDefinition` pairs non-empty Markdown `instructions` with an `AgentContract`.
It contains no callable or provider SDK binding. The fixture combines `agent.md`
and `contract.yaml`; the Phase 2 registry loads the complete pair.

## Contract fields

| Section | Meaning |
| --- | --- |
| `contract_version` | Quoted string `"1"`; format version, independent of the agent version |
| `agent` | Lowercase hyphenated ID, numeric `major.minor.patch` version, description, responsibilities, capabilities |
| `inputs.schema` / `outputs.schema` | Inline JSON Schema Draft 2020-12; root must declare `type: object` |
| `tools.allowed` | Exact tool identifiers requested by the agent; defaults to an empty list |
| `permissions` | Requested filesystem, network, subprocess, and external-write capabilities; all default to false |
| `execution` | Required positive timeout; nonnegative model/tool call budgets default to zero |
| `errors` | Only `retry_policy: none` is supported in version 1 |
| `observability` | Tags and `record_payloads: false`; raw payload logging is unsupported |

Unknown contract fields are errors, including nested fields. Numeric strings and
string booleans are not coerced. Use quoted versions, numeric limits, and YAML
`true`/`false` booleans. Payloads must contain only JSON-native values: no dates,
sets, tuples, non-string object keys, cycles, NaN, or infinity.

Schemas support structural JSON Schema constraints, including nested properties,
arrays, required fields, enum, and composition. `format` is annotation-only; it
does not enforce email/date formats. Use explicit constraints where required.
Version 1 reserves `$ref`, `$dynamicRef`, and `$recursiveRef` throughout schema
documents, including examples, so schemas must be entirely inline. Other dialects
are rejected. Supporting references later requires explicit resolution and trust
rules rather than implicit network fetching.

## Extend the foundation

For a future approved agent:

1. Create `agents/<agent-id>/agent.md` and `contract.yaml` using the fixture as a
   structural example, not as executable business logic.
2. Describe responsibilities and boundaries in Markdown. Put machine-readable
   schemas, limits, and requested capabilities in YAML.
3. Add tests for representative valid and invalid input/output payloads.
4. Register execution behavior only after the registry and runtime phases exist.

For a new contract field, add it to the smallest relevant model, choose a safe
default or make it required, document the semantics, and test acceptance and
rejection. Never loosen `extra="forbid"` merely to accept an undeclared field.
Breaking format changes require an explicit version/migration decision; do not
silently reinterpret version 1. Agent versions change independently.

Provider/tool configuration belongs in future adapters, not agent contracts.
Keep assistant-specific wrappers thin and reference the shared portable files.
Do not add LangGraph, cloud, or enterprise dependencies to implement a contract.

## Trust boundaries and limitations

- These contracts declare permissions; they do not enforce filesystem access or
  grant authorization. The Phase 3 broker enforces host policy for each mediated tool call.
- Nested model collections remain mutable. Revalidate serialized data after
  programmatic changes before using it as a trusted contract.
- Payload error messages omit data, but raw Pydantic/YAML exceptions can include
  input values. Do not log untrusted exception details as public diagnostics.
- The YAML loader bounds size/depth and rejects ambiguous constructs. The Phase 2
  registry authorizes configured roots and rejects duplicate agent identities.
- Resource limits for schema complexity and malicious regexes are future runtime
  concerns. This validator is not an isolation boundary for hostile code/data.

## Next phases

2. Registry: implemented; see [registry-guide.md](registry-guide.md).
3. Policy and tool broker: implemented; see [tool-security-guide.md](tool-security-guide.md).
4. Runner: implemented; see [runner-guide.md](runner-guide.md).
5. JSON context store: implemented; see [context-storage-guide.md](context-storage-guide.md).
6. CLI and end-to-end documentation: implemented; see [cli-guide.md](cli-guide.md).

Each phase needs approval and its own tests. Project Discovery remains a separate
agent milestone after foundation approval.

## Library references

- [Pydantic models](https://docs.pydantic.dev/latest/concepts/models/)
- [JSON Schema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/)
- [Setuptools package discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html)
