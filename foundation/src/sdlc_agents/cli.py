"""Explicit, read-only CLI composition for foundation validation and fake runs."""

import asyncio
import json
from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

from .execution import ExecutionRequest
from .paths import check_path
from .registry import FileSystemAgentRegistry, RegistryError
from .runner import LocalAgentRunner
from .security import ProjectPolicy
from .testing import FakeExecutor

app = typer.Typer(no_args_is_help=True, add_completion=False,
                  pretty_exceptions_enable=False,
                  help="Portable foundation tools. Execution is synthetic only.")
Roots = Annotated[list[Path], typer.Option("--agent-root", help="Explicit definition root; repeatable.")]
MAX_JSON_BYTES = 1024 * 1024


class ExecutorChoice(str, Enum):
    fake = "fake"


def _fail(code: str) -> None:
    typer.echo(json.dumps({"error": code}), err=True)
    raise typer.Exit(2)


def _registry(roots: list[Path]) -> FileSystemAgentRegistry:
    return FileSystemAgentRegistry(roots)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Non-finite value")


def _json_file(path: Path) -> dict:
    path = path.absolute()
    check_path(path, directory=False)
    with path.open("rb") as stream:
        data = stream.read(MAX_JSON_BYTES + 1)
    check_path(path, directory=False)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("Document too large")
    value = json.loads(data.decode("utf-8-sig"), object_pairs_hook=_unique,
                       parse_constant=_constant)
    if not isinstance(value, dict):
        raise ValueError("Expected object")
    return value


@app.command("list")
def list_agents(agent_root: Roots) -> None:
    """Validate every definition and print deterministic metadata as JSON."""
    try:
        metadata = _registry(agent_root).list_agents()
    except RegistryError:
        _fail("invalid_registry")
    typer.echo(json.dumps([item.model_dump(mode="json") for item in metadata]))


@app.command()
def validate(agent_id: str, agent_root: Roots,
             version: Annotated[str | None, typer.Option()] = None) -> None:
    """Validate and resolve one definition; ambiguous versions are errors."""
    try:
        metadata = _registry(agent_root).get_metadata(agent_id, version)
    except RegistryError:
        _fail("invalid_registry")
    typer.echo(metadata.model_dump_json())


@app.command()
def run(agent_root: Roots,
        request: Annotated[Path, typer.Option(help="ExecutionRequest JSON file.")],
        fake_output: Annotated[Path, typer.Option(help="Synthetic output JSON object.")],
        project_root: Annotated[Path, typer.Option(help="Existing project directory.")],
        executor: Annotated[ExecutorChoice, typer.Option(help="Explicit synthetic execution selection.")]) -> None:
    """Run schema-checked fake output through the lifecycle with all access denied."""
    if executor != ExecutorChoice.fake:
        _fail("unsupported_executor")
    try:
        message = ExecutionRequest.model_validate_json(json.dumps(_json_file(request)))
        output = _json_file(fake_output)
        project_root = project_root.absolute()
        check_path(project_root, directory=True)
        registry = _registry(agent_root)
        definition = registry.load(message.agent_id, message.agent_version)
        identity = (definition.contract.agent.id, definition.contract.agent.version)
        runner = LocalAgentRunner(
            registry=registry, executors={identity: lambda: FakeExecutor(output)},
            policies={message.project_id: ProjectPolicy(
                project_id=message.project_id, source_root=project_root)},
        )
    except RegistryError:
        _fail("invalid_registry")
    except (ValueError, OSError, RecursionError):
        _fail("invalid_input")
    result = asyncio.run(runner.run(message))
    typer.echo(result.model_dump_json())
    if result.status != "succeeded":
        raise typer.Exit(1)
