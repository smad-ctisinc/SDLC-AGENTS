"""Local execution through synthetic definitions and explicit trusted factories."""

import asyncio
from pathlib import Path

import pytest
import yaml

from sdlc_agents import (
    AccessGrant, ExecutionRequest, FileSystemAgentRegistry, LocalAgentRunner,
    ProjectContext, ProjectPolicy, ReadTextTool,
)
from sdlc_agents.providers import FakeProvider, ModelRequest, ModelResponse, ProviderDescriptor
from sdlc_agents.runtime import RunFailure
from sdlc_agents.testing import FakeExecutor

FIXTURE = Path(__file__).parents[1] / "fixtures/agents/foundation-probe"
OUTPUT = {"project_id": "p", "status": "ok"}


@pytest.fixture
def setup(tmp_path):
    directory = tmp_path / "agents/foundation-probe"
    directory.mkdir(parents=True)
    for name in ("agent.md", "contract.yaml"):
        (directory / name).write_bytes((FIXTURE / name).read_bytes())
    project = tmp_path / "project"
    project.mkdir()
    policy = ProjectPolicy(project_id="p", source_root=project)
    grant = AccessGrant(project_id="p")
    return directory, policy, grant


def change_contract(setup, edit):
    path = setup[0] / "contract.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(data)
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


def make_runner(setup, factory=lambda: FakeExecutor(OUTPUT), **kwargs):
    directory, policy, grant = setup
    return LocalAgentRunner(
        registry=FileSystemAgentRegistry([directory.parent]),
        executors={("foundation-probe", "0.1.0"): factory},
        policies={"p": policy}, grants={"p": grant}, **kwargs,
    )


def request(**kwargs):
    return ExecutionRequest(**dict(project_id="p", agent_id="foundation-probe",
                                   inputs={"project_id": "p"}) | kwargs)


def run(runner, **kwargs):
    return asyncio.run(runner.run(request(**kwargs)))


def enable_model(setup, limit=2):
    change_contract(setup, lambda data: data["execution"].update(max_model_calls=limit))
    setup[1].max_model_calls = limit
    setup[1].allowed_providers = ["fake"]
    setup[2].allowed_providers = ["fake"]


def fake_provider():
    return FakeProvider(ModelResponse(content=OUTPUT, input_tokens=3, output_tokens=4, estimated_cost_usd=0.0))


def enable_tool(setup):
    def edit(data):
        data["tools"]["allowed"] = ["fs.read_text"]
        data["permissions"]["filesystem"]["read"] = True
        data["execution"]["max_tool_calls"] = 1
    change_contract(setup, edit)
    for authority in setup[1:]:
        authority.allowed_tools = ["fs.read_text"]
        authority.permissions.filesystem.read = True
    setup[1].max_tool_calls = 1


def test_success_identity_metadata_and_bounded_records(setup):
    runner = make_runner(setup, record_limit=1)
    first, second = run(runner), run(runner)
    assert first.status == second.status == "succeeded"
    assert first.output == OUTPUT
    assert first.run_id != second.run_id
    assert first.agent_version == "0.1.0" and len(first.definition_digest) == 64
    assert first.started_at.tzinfo is not None and first.finished_at >= first.started_at
    assert first.duration_seconds >= 0
    assert first.usage.model_calls == first.usage.tool_calls == 0
    assert len(runner.records()) == 1 and runner.records()[0].run_id == second.run_id
    assert "output" not in runner.records()[0].model_dump()
    runner.records()[0].usage.tool_calls = 999
    assert runner.records()[0].usage.tool_calls == 0


@pytest.mark.parametrize("fields,code", [
    ({"agent_id": "missing"}, "agent_not_found"),
    ({"agent_version": "9.0.0"}, "agent_not_found"),
    ({"project_id": "unknown"}, "project_not_configured"),
    ({"inputs": {}}, "invalid_input"),
])
def test_preflight_failure_never_constructs_executor(setup, fields, code):
    def forbidden():
        pytest.fail("Executor must not be constructed")
    result = run(make_runner(setup, forbidden), **fields)
    assert result.status == "failed" and result.error.code == code
    if code == "agent_not_found":
        assert result.agent_version is None


def test_invalid_definition_and_missing_binding(setup):
    (setup[0] / "agent.md").write_text("", encoding="utf-8")
    assert run(make_runner(setup)).error.code == "definition_invalid"
    (setup[0] / "agent.md").write_text("Synthetic", encoding="utf-8")
    runner = LocalAgentRunner(registry=FileSystemAgentRegistry([setup[0].parent]),
                             executors={}, policies={"p": setup[1]})
    assert run(runner).error.code == "executor_unavailable"


def test_factory_failure_is_sanitized(setup):
    def broken():
        raise RuntimeError("TOP_SECRET")
    result = run(make_runner(setup, broken))
    assert result.status == "failed" and result.error.code == "executor_failed"
    assert "TOP_SECRET" not in result.model_dump_json()


def test_invalid_output_cannot_weaken_contract(setup):
    class Mutator:
        async def execute(self, definition, inputs, context):
            definition.contract.outputs.json_schema.clear()
            inputs.clear()
            return {"secret": "TOP_SECRET"}
    result = run(make_runner(setup, Mutator))
    assert result.error.code == "invalid_output"
    assert "TOP_SECRET" not in result.model_dump_json()


@pytest.mark.parametrize("layer,status,code", [
    (1, "failed", "permission_denied"), (2, "approval_required", "approval_required"),
])
def test_permission_preflight(setup, layer, status, code):
    enable_tool(setup)
    setup[layer].permissions.filesystem.read = False
    result = run(make_runner(setup, adapters=[ReadTextTool()]))
    assert result.status == status and result.error.code == code
    assert result.usage.tool_calls == 0


def test_unsupported_permissions_and_unregistered_tools(setup):
    change_contract(setup, lambda data: data["permissions"].update(network=True))
    assert run(make_runner(setup)).error.code == "unsupported_permission"
    change_contract(setup, lambda data: data["permissions"].update(network=False))
    enable_tool(setup)
    assert run(make_runner(setup)).error.code == "permission_denied"


def test_tool_calls_are_mediated_and_counted(setup):
    enable_tool(setup)
    (setup[1].source_root / "file.txt").write_text("safe", encoding="utf-8")
    class Reader:
        async def execute(self, definition, inputs, context):
            data = await context.call_tool("fs.read_text", {"path": "file.txt"})
            assert data == {"text": "safe"}
            return OUTPUT
    result = run(make_runner(setup, Reader, adapters=[ReadTextTool()]))
    assert result.status == "succeeded" and result.usage.tool_calls == 1


def test_tool_budget_exhaustion_fails_run(setup):
    enable_tool(setup)
    (setup[1].source_root / "file.txt").write_text("safe", encoding="utf-8")
    class Reader:
        async def execute(self, definition, inputs, context):
            for _ in range(2):
                await context.call_tool("fs.read_text", {"path": "file.txt"})
            return OUTPUT
    result = run(make_runner(setup, Reader, adapters=[ReadTextTool()]))
    assert result.error.code == "budget_exhausted" and result.usage.tool_calls == 1


def test_fake_provider_and_usage(setup):
    enable_model(setup)
    result = run(make_runner(setup, lambda: FakeExecutor(prompt="Synthetic prompt"),
                             provider_factory=fake_provider))
    assert result.status == "succeeded" and result.output == OUTPUT
    assert result.usage.model_calls == 1
    assert result.usage.input_tokens == 3 and result.usage.output_tokens == 4


@pytest.mark.parametrize("failure,expected", [
    ("no_factory", "provider_unavailable"), ("host", "permission_denied"),
    ("grant", "approval_required"), ("zero_budget", "model_budget_exhausted"),
    ("remote", "remote_provider_unsupported"),
])
def test_model_preflight(setup, failure, expected):
    enable_model(setup)
    factory = fake_provider
    if failure == "no_factory":
        factory = None
    elif failure == "host":
        setup[1].allowed_providers = []
    elif failure == "grant":
        setup[2].allowed_providers = []
    elif failure == "zero_budget":
        setup[1].max_model_calls = 0
    else:
        class Remote(FakeProvider):
            @property
            def descriptor(self):
                return ProviderDescriptor(provider_id="fake", requires_network=True)
        factory = lambda: Remote(ModelResponse(content=OUTPUT))
    result = run(make_runner(setup, provider_factory=factory))
    assert result.error.code == expected and result.usage.model_calls == 0


def test_concurrent_model_budget(setup):
    enable_model(setup, limit=1)
    class Parallel:
        async def execute(self, definition, inputs, context):
            results = await asyncio.gather(*(context.generate(ModelRequest(prompt="test"))
                                             for _ in range(3)), return_exceptions=True)
            assert sum(isinstance(item, RunFailure) for item in results) == 2
            return OUTPUT
    result = run(make_runner(setup, Parallel, provider_factory=fake_provider))
    assert result.status == "succeeded" and result.usage.model_calls == 1


def test_provider_failure_keeps_unknown_usage(setup):
    enable_model(setup)
    class Broken(FakeProvider):
        async def generate(self, request):
            raise RuntimeError("TOP_SECRET")
    result = run(make_runner(setup, lambda: FakeExecutor(prompt="test"),
                             provider_factory=lambda: Broken(ModelResponse(content=OUTPUT))))
    assert result.status == "failed" and result.usage.model_calls == 1
    assert result.usage.input_tokens is None
    assert "TOP_SECRET" not in result.model_dump_json()


def test_deadline_and_closed_context(setup):
    change_contract(setup, lambda data: data["execution"].update(timeout_seconds=1))
    captured = []
    class Slow:
        async def execute(self, definition, inputs, context):
            captured.append(context)
            await asyncio.sleep(3)
            return OUTPUT
    result = run(make_runner(setup, Slow))
    assert result.status == "timed_out"
    with pytest.raises(RunFailure, match="run_closed"):
        asyncio.run(captured[0].generate(ModelRequest(prompt="late")))


def test_external_cancellation_returns_result_and_record(setup):
    async def scenario():
        started = asyncio.Event()
        class Waiting:
            async def execute(self, definition, inputs, context):
                started.set()
                await asyncio.sleep(10)
                return OUTPUT
        runner = make_runner(setup, Waiting)
        task = asyncio.create_task(runner.run(request()))
        await started.wait()
        task.cancel()
        result = await task
        assert runner.records()[0].status == "cancelled"
        return result
    assert asyncio.run(scenario()).status == "cancelled"


def test_concurrent_projects_context_and_budgets_are_isolated(setup):
    enable_model(setup, limit=1)
    policy_b = setup[1].model_copy(deep=True)
    policy_b.project_id = "b"
    grant_b = setup[2].model_copy(deep=True)
    grant_b.project_id = "b"
    contexts = []
    class ContextExecutor:
        async def execute(self, definition, inputs, context):
            contexts.append(context)
            assert context.project_context.project_id == context.project_id
            await context.generate(ModelRequest(prompt="test"))
            return {"project_id": context.project_id, "status": "ok"}
    runner = LocalAgentRunner(registry=FileSystemAgentRegistry([setup[0].parent]),
                             executors={("foundation-probe", "0.1.0"): ContextExecutor},
                             policies={"p": setup[1], "b": policy_b},
                             grants={"p": setup[2], "b": grant_b}, provider_factory=fake_provider)
    async def scenario():
        return await asyncio.gather(*(runner.run(request(project_id=project,
            context=ProjectContext(project_id=project))) for project in ("p", "b")))
    results = asyncio.run(scenario())
    assert all(result.status == "succeeded" and result.usage.model_calls == 1 for result in results)
    assert {result.output["project_id"] for result in results} == {"p", "b"}
    assert contexts[0] is not contexts[1]


def test_output_redaction_and_record_payload_exclusion(setup):
    setup[1].secret_values = ["TOP_SECRET"]
    runner = make_runner(setup, lambda: FakeExecutor({"project_id": "TOP_SECRET", "status": "ok"}))
    result = run(runner)
    assert result.output["project_id"] == "[REDACTED]"
    assert "TOP_SECRET" not in runner.records()[0].model_dump_json()


def test_redacted_output_must_still_satisfy_schema(setup):
    setup[1].secret_values = ["ok"]
    result = run(make_runner(setup))
    assert result.status == "failed" and result.error.code == "invalid_output"
    assert result.output is None


def test_exact_version_binding_and_ambiguous_registry(setup, tmp_path):
    other = tmp_path / "other/foundation-probe"
    other.mkdir(parents=True)
    (other / "agent.md").write_text("Synthetic version 2", encoding="utf-8")
    data = yaml.safe_load((setup[0] / "contract.yaml").read_text(encoding="utf-8"))
    data["agent"]["version"] = "2.0.0"
    (other / "contract.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    runner = LocalAgentRunner(registry=FileSystemAgentRegistry([setup[0].parent, other.parent]),
                             executors={("foundation-probe", "0.1.0"): lambda: FakeExecutor(OUTPUT)},
                             policies={"p": setup[1]})
    ambiguous = run(runner)
    assert ambiguous.error.code == "ambiguous_version" and ambiguous.agent_version is None
    assert run(runner, agent_version="0.1.0").status == "succeeded"
    assert run(runner, agent_version="2.0.0").error.code == "executor_unavailable"


def test_policy_snapshot_and_closed_tool_broker(setup):
    enable_tool(setup)
    captured = []
    class Capture:
        async def execute(self, definition, inputs, context):
            captured.append(context)
            return OUTPUT
    runner = make_runner(setup, Capture, adapters=[ReadTextTool()])
    setup[1].permissions.filesystem.read = False
    assert run(runner).status == "succeeded"  # authority was snapshotted at construction
    with pytest.raises(RunFailure, match="run_closed"):
        asyncio.run(captured[0].call_tool("fs.read_text", {"path": "late.txt"}))


def test_provider_request_is_redacted_and_usage_accumulates(setup):
    enable_model(setup)
    setup[1].secret_values = ["TOP_SECRET"]
    seen = []
    class Observe(FakeProvider):
        async def generate(self, request):
            seen.append(request.prompt)
            return await super().generate(request)
    class Twice:
        async def execute(self, definition, inputs, context):
            for _ in range(2):
                response = await context.generate(ModelRequest(prompt="value TOP_SECRET"))
            return response.content
    result = run(make_runner(setup, Twice, provider_factory=lambda: Observe(
        ModelResponse(content=OUTPUT, input_tokens=3, output_tokens=4, estimated_cost_usd=0.0))))
    assert result.status == "succeeded" and seen == ["value [REDACTED]"] * 2
    assert result.usage.input_tokens == 6 and result.usage.output_tokens == 8


def test_run_closes_pending_mediated_calls(setup):
    enable_model(setup)
    async def scenario():
        started, cancelled = asyncio.Event(), asyncio.Event()
        children = []
        class Waiting(FakeProvider):
            async def generate(self, request):
                started.set()
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.set()
        class Background:
            async def execute(self, definition, inputs, context):
                children.append(asyncio.create_task(context.generate(ModelRequest(prompt="test"))))
                await started.wait()
                return OUTPUT
        runner = make_runner(setup, Background, provider_factory=lambda: Waiting(ModelResponse(content=OUTPUT)))
        result = await runner.run(request())
        await asyncio.gather(*children, return_exceptions=True)
        assert cancelled.is_set()
        assert result.usage.model_calls == 1 and result.usage.input_tokens is None
        return result
    assert asyncio.run(scenario()).status == "succeeded"


@pytest.mark.parametrize('swallow', [False, True])
def test_cost_overflow_is_terminal_and_recorded(setup, tmp_path, swallow):
    from sdlc_agents import JsonContextStore
    enable_model(setup)
    enable_tool(setup)

    class OverflowExecutor:
        async def execute(self, definition, inputs, context):
            await context.call_tool('fs.read_text', {'path': 'safe.txt'})
            await context.generate(ModelRequest(prompt='synthetic'))
            try:
                await context.generate(ModelRequest(prompt='synthetic'))
            except RunFailure:
                if not swallow:
                    raise
            return OUTPUT

    (setup[1].source_root / 'safe.txt').write_text('synthetic')
    runner = make_runner(setup, factory=OverflowExecutor, adapters=[ReadTextTool()],
        provider_factory=lambda: FakeProvider(ModelResponse(content=OUTPUT, input_tokens=2,
            output_tokens=3, estimated_cost_usd=1e308)))
    result = run(runner)
    assert result.status == 'failed' and result.output is None
    assert result.error.code == 'usage_accounting_failed'
    assert result.project_id == 'p' and result.agent_id == 'foundation-probe'
    assert result.run_id and result.finished_at >= result.started_at
    assert result.duration_seconds >= 0
    assert result.usage.model_calls == 2 and result.usage.tool_calls == 1
    assert result.usage.input_tokens == 4 and result.usage.output_tokens == 6
    assert result.usage.estimated_cost_usd is None
    record, = runner.records()
    assert record.run_id == result.run_id and record.usage == result.usage
    assert record.status == 'failed' and record.error_code == result.error.code
    state = tmp_path / 'state'
    state.mkdir()
    store = JsonContextStore(state, writable=True)
    assert list(state.iterdir()) == []
    store.save_run_record(record)
    assert store.read_run_record('p', result.run_id) == record


@pytest.mark.parametrize('cost', [None, 0.0, 0.25, 5e307])
def test_representable_cost_totals_remain_successful(setup, cost):
    enable_model(setup)

    class Twice:
        async def execute(self, definition, inputs, context):
            await context.generate(ModelRequest(prompt='synthetic'))
            await context.generate(ModelRequest(prompt='synthetic'))
            return OUTPUT

    runner = make_runner(setup, factory=Twice,
        provider_factory=lambda: FakeProvider(ModelResponse(content=OUTPUT, estimated_cost_usd=cost)))
    result = run(runner)
    assert result.status == 'succeeded'
    assert result.usage.model_calls == 2
    assert result.usage.estimated_cost_usd == (None if cost is None else 2 * cost)
    assert runner.records()[0].usage == result.usage


def test_overflow_cannot_be_hidden_by_a_later_failed_model_call(setup):
    enable_model(setup, limit=3)

    class Provider(FakeProvider):
        calls = 0
        async def generate(self, request):
            self.calls += 1
            if self.calls == 3:
                raise ValueError('private provider details')
            return await super().generate(request)

    class CatchFailures:
        async def execute(self, definition, inputs, context):
            for _ in range(3):
                try:
                    await context.generate(ModelRequest(prompt='synthetic'))
                except (RunFailure, ValueError):
                    pass
            return OUTPUT

    runner = make_runner(setup, factory=CatchFailures,
        provider_factory=lambda: Provider(ModelResponse(content=OUTPUT, estimated_cost_usd=1e308)))
    result = run(runner)
    assert result.status == 'failed' and result.error.code == 'usage_accounting_failed'
    assert result.usage.model_calls == 3 and result.usage.estimated_cost_usd is None
    assert 'private' not in result.model_dump_json()
    assert runner.records()[0].run_id == result.run_id
