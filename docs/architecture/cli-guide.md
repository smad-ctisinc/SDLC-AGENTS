# Foundation CLI (Phase 6)

The CLI composes existing registry, contract, and runner services. It uses Typer;
core services never import the CLI. Install into the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\sdlc-agents.exe --help
```

`python -m sdlc_agents` is equivalent to the installed `sdlc-agents` command.
On Linux/macOS use `.venv/bin/python` and `.venv/bin/sdlc-agents`.
Paths are relative to the current working directory. Definition roots are always
explicit, repeatable with `--agent-root`, and are not bundled in the wheel.

## End-to-end synthetic example

Run from the checkout root in PowerShell. Use a temporary directory for example
request files; no application files or persisted context are changed by the CLI.

```powershell
.\.venv\Scripts\python.exe -m sdlc_agents list --agent-root tests/fixtures/agents
.\.venv\Scripts\python.exe -m sdlc_agents validate foundation-probe --agent-root tests/fixtures/agents --version 0.1.0
$demoRoot = Join-Path ([System.IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $demoRoot | Out-Null
'{"project_id":"example","agent_id":"foundation-probe","inputs":{"project_id":"example"}}' | Set-Content (Join-Path $demoRoot 'request.json') -Encoding utf8
'{"project_id":"example","status":"ok"}' | Set-Content (Join-Path $demoRoot 'output.json') -Encoding utf8
.\.venv\Scripts\python.exe -m sdlc_agents run --agent-root tests/fixtures/agents --request (Join-Path $demoRoot 'request.json') --fake-output (Join-Path $demoRoot 'output.json') --project-root $demoRoot --executor fake
```

The result is a JSON ExecutionResult with generated run ID, project/agent identity,
resolved version, definition digest, status, timing, output, and usage. Expected
status is `succeeded`, output status is `ok`, and model/tool usage is zero.
Example request files remain in the displayed temporary directory for inspection.

## Commands and errors

- `list`: validates all roots and prints a deterministic JSON metadata array.
- `validate AGENT_ID`: resolves and validates a definition, printing metadata.
  Use `--version` when an ID has multiple versions; there is no implicit latest.
- `run`: requires request JSON, synthetic output JSON, project directory, explicit
  roots and `--executor fake`. Request `agent_version` selects an exact version.
  Optional project context can be embedded in the ExecutionRequest JSON.

Exit code 0 means success; 1 means a completed non-success execution with a JSON
result on stdout; 2 means invalid arguments/configuration/input. Application
errors use a safe JSON error code on stderr; Typer usage errors use its standard
text diagnostics. No raw validation exceptions or payload excerpts are printed.
Registry errors intentionally use a generic code; use the library API for detailed
trusted diagnostics. Results contain caller-supplied output: stdout is not a safe
place for secrets. Listing includes definition descriptions and local paths.

JSON files must contain objects, be UTF-8 (optional BOM), and be at most 1 MiB.
Duplicate keys, non-finite values, invalid requests, and unsafe file paths are
rejected. Source directories and all inputs must be stable, trusted local paths;
path checks are not a sandbox against hostile concurrent filesystem changes.

## Extension boundaries

Fake execution returns explicitly supplied output through normal input/output
validation and runner permission checks. It does not interpret Markdown, call a
model, infer correct output, or constitute an actual SDLC agent. All capabilities
remain denied; declarations in contracts cannot grant access. No executable
module names, shell commands, plugins, or provider bindings are loaded from data.

The CLI does not persist context or run records. For explicit host-managed storage,
see [context storage](context-storage-guide.md). Future providers/executors should
be composed through existing typed interfaces with reviewed policy and grants;
introducing real execution or configuration loading requires a separate design.
Codex and Claude can invoke this same CLI or use the Python API while retaining
shared portable definitions and thin assistant-specific wrappers.

## Verification

Run `python -m pytest` in the virtual environment. CLI tests use
[Typer's CliRunner](https://typer.tiangolo.com/tutorial/testing/), alongside existing
contract, registry, security, runner, storage, and integration tests. Build and
install a wheel into a separate virtual environment and run tests outside the
checkout to check package discovery and entry points. Runtime verification on
Python 3.11 remains a CI task when that interpreter is available.

Phase 6 completes the planned foundation sequence. Actual SDLC agents, real
providers, orchestration, RAG, and cloud integrations remain separately approved
future work.
