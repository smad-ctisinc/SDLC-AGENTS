"""Host loads persisted context explicitly; execution never persists implicitly."""

import asyncio
from pathlib import Path

from sdlc_agents import (
    ExecutionRequest, FileSystemAgentRegistry, JsonContextStore,
    LocalAgentRunner, ProjectContext, ProjectPolicy,
)


def test_saved_context_flows_into_runner_without_implicit_writes(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    store = JsonContextStore(state, writable=True)
    store.save(ProjectContext(project_id="example", metadata={"language": "Java"}), expected_revision=0)
    before = next(state.glob("*.json")).read_bytes()

    class ContextExecutor:
        async def execute(self, definition, inputs, context):
            snapshot = context.project_context
            assert snapshot.project_id == "example" and snapshot.revision == 1
            assert snapshot.metadata == {"language": "Java"}
            snapshot.metadata["language"] = "Python"
            assert context.project_context.metadata == {"language": "Java"}
            return {"project_id": "example", "status": "ok"}

    runner = LocalAgentRunner(
        registry=FileSystemAgentRegistry([Path(__file__).parents[1] / "fixtures/agents"]),
        executors={("foundation-probe", "0.1.0"): ContextExecutor},
        policies={"example": ProjectPolicy(project_id="example", source_root=project)},
    )
    result = asyncio.run(runner.run(ExecutionRequest(
        project_id="example", agent_id="foundation-probe", inputs={"project_id": "example"},
        context=store.read("example"),
    )))
    assert result.status == "succeeded"
    assert next(state.glob("*.json")).read_bytes() == before
    assert list(project.iterdir()) == []
    record = runner.records()[0]
    store.save_run_record(record)
    assert JsonContextStore(state).read_run_record("example", result.run_id) == record
    assert store.read("example").revision == 1
