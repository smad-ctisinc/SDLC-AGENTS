"""Policy and broker tests prove denial occurs before adapter invocation."""

import asyncio
import os
from pathlib import Path
import subprocess

import pytest

from sdlc_agents import load_contract
from sdlc_agents.security import AccessGrant, ProjectPolicy
from sdlc_agents.tools import ReadTextTool, ToolBroker, ToolCall

FIXTURE = Path(__file__).parents[1] / "fixtures/agents/foundation-probe/contract.yaml"


@pytest.fixture
def setup(tmp_path):
    contract = load_contract(FIXTURE)
    contract.tools.allowed = ["fs.read_text"]
    contract.permissions.filesystem.read = True
    contract.execution.max_tool_calls = 4
    policy = ProjectPolicy(project_id="a", source_root=tmp_path, allowed_tools=["fs.read_text"],
                           max_tool_calls=4)
    policy.permissions.filesystem.read = True
    grant = AccessGrant(project_id="a", allowed_tools=["fs.read_text"])
    grant.permissions.filesystem.read = True
    (tmp_path / "safe.txt").write_text("hello", encoding="utf-8")
    return contract, policy, grant


def broker_for(setup, adapters=None):
    contract, policy, grant = setup
    return ToolBroker(contract=contract, policy=policy, grant=grant, run_id="run-a",
                      adapters=[ReadTextTool()] if adapters is None else adapters)


def call(broker, path="safe.txt", **changes):
    fields = dict(project_id="a", run_id="run-a", tool_id="fs.read_text", arguments={"path": path})
    fields.update(changes)
    return asyncio.run(broker.call(ToolCall(**fields)))


class SpyTool(ReadTextTool):
    def __init__(self, outcome="ok"):
        self.calls = 0
        self.outcome = outcome

    async def invoke(self, arguments, context):
        self.calls += 1
        if self.outcome == "error":
            raise ValueError("TOP_SECRET adapter details")
        if self.outcome == "invalid":
            return {"unexpected": "TOP_SECRET"}
        if self.outcome == "cancel":
            raise asyncio.CancelledError
        if self.outcome == "timeout":
            await asyncio.sleep(2)
        return {"text": "spy"}


def test_read_only_success(setup):
    before = (setup[1].source_root / "safe.txt").read_bytes()
    broker = broker_for(setup)
    result = call(broker)
    assert result.status == "succeeded" and result.data == {"text": "hello"}
    assert (result.project_id, result.run_id, result.tool_id) == ("a", "run-a", "fs.read_text")
    assert broker.calls_used == 1
    assert (setup[1].source_root / "safe.txt").read_bytes() == before


@pytest.mark.parametrize("layer", [0, 1, 2])
@pytest.mark.parametrize("denial", ["permission", "allowlist"])
def test_each_authority_must_allow(setup, layer, denial):
    authority = setup[layer]
    if denial == "permission":
        authority.permissions.filesystem.read = False
    elif layer == 0:
        authority.tools.allowed = []
    else:
        authority.allowed_tools = []
    spy = SpyTool()
    broker = broker_for(setup, [spy])
    assert call(broker).error.code == "permission_denied"
    assert spy.calls == broker.calls_used == 0


def test_defaults_deny(setup):
    contract, policy, _ = setup
    broker = ToolBroker(contract=contract, policy=policy, grant=AccessGrant(project_id="a"),
                        run_id="run-a", adapters=[ReadTextTool()])
    assert call(broker).status == "denied"


@pytest.mark.parametrize("changes,code", [
    ({"project_id": "b"}, "scope_mismatch"),
    ({"run_id": "run-b"}, "scope_mismatch"),
    ({"tool_id": "fs.write"}, "unknown_tool"),
    ({"arguments": {"path": "safe.txt", "root": "/elsewhere"}}, "invalid_arguments"),
    ({"arguments": {"path": 12}}, "invalid_arguments"),
])
def test_denied_or_invalid_calls_never_dispatch(setup, changes, code):
    spy = SpyTool()
    broker = broker_for(setup, [spy])
    assert call(broker, **changes).error.code == code
    assert spy.calls == broker.calls_used == 0


@pytest.mark.parametrize("capability", ["filesystem.write", "network", "subprocess", "external_write"])
def test_unsupported_effects_never_dispatch(setup, capability):
    class UnsafeTool(SpyTool):
        @property
        def descriptor(self):
            descriptor = super().descriptor
            descriptor.required_capabilities = (capability,)
            return descriptor

    for authority in setup:
        authority.permissions.filesystem.write = True
        authority.permissions.network = True
        authority.permissions.subprocess = True
        authority.permissions.external_write = True
    spy = UnsafeTool()
    assert call(broker_for(setup, [spy])).error.code == "permission_denied"
    assert spy.calls == 0


def test_duplicate_tools_and_project_mismatch_rejected(setup):
    with pytest.raises(ValueError, match="Duplicate"):
        broker_for(setup, [ReadTextTool(), ReadTextTool()])
    setup[2].project_id = "other"
    with pytest.raises(ValueError, match="project IDs"):
        broker_for(setup)


@pytest.mark.parametrize("layer", [0, 1])
def test_concurrent_budget_reservations(setup, layer):
    if layer == 0:
        setup[0].execution.max_tool_calls = 1
    else:
        setup[1].max_tool_calls = 1
    spy = SpyTool()
    broker = broker_for(setup, [spy])

    async def requests():
        return await asyncio.gather(*(broker.call(ToolCall(
            project_id="a", run_id="run-a", tool_id="fs.read_text", arguments={"path": "safe.txt"}
        )) for _ in range(8)))

    outcomes = asyncio.run(requests())
    assert sum(item.status == "succeeded" for item in outcomes) == 1
    assert sum(item.error is not None and item.error.code == "budget_exhausted" for item in outcomes) == 7
    assert spy.calls == broker.calls_used == 1


@pytest.mark.parametrize("outcome", ["error", "invalid", "timeout"])
def test_failures_are_sanitized_and_consume_budget(setup, outcome):
    setup[0].execution.timeout_seconds = 1
    spy = SpyTool(outcome)
    broker = broker_for(setup, [spy])
    result = call(broker)
    assert result.status == "failed"
    assert "TOP_SECRET" not in result.model_dump_json()
    assert broker.calls_used == 1


def test_cancellation_propagates_and_consumes_budget(setup):
    broker = broker_for(setup, [SpyTool("cancel")])
    with pytest.raises(asyncio.CancelledError):
        call(broker)
    assert broker.calls_used == 1


def test_policy_mutation_does_not_escalate(setup):
    setup[2].permissions.filesystem.read = False
    broker = broker_for(setup)
    setup[2].permissions.filesystem.read = True
    assert call(broker).status == "denied"


@pytest.mark.parametrize("path", ["../safe.txt", "a/../safe.txt", "/safe.txt", "C:/safe.txt", r"..\safe.txt", "file:stream", "NUL", "dir/CON.txt", "safe.txt ", "a//b", "./safe.txt", "CONIN$", "COM¹", "a?b", "foo\nbar"])
def test_unsafe_paths_denied(setup, path):
    result = call(broker_for(setup), path)
    assert result.status == "denied" and result.error.code == "resource_denied"


@pytest.mark.parametrize("path", [".env", ".ENV.production", ".aws/config", "nested/private.key", "credentials.json", ".git/config"])
def test_sensitive_files_excluded(setup, path):
    target = setup[1].source_root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("TOP_SECRET", encoding="utf-8")
    result = call(broker_for(setup), path)
    assert result.status == "denied"
    assert "TOP_SECRET" not in result.model_dump_json()


def test_additive_exclusions_and_redaction(setup):
    policy = setup[1]
    policy.excluded_patterns = ["safe.txt"]
    assert call(broker_for(setup)).status == "denied"
    policy.excluded_patterns = []
    policy.secret_values = ["sensitive-value"]
    (policy.source_root / "safe.txt").write_text("password = hidden\nother: sensitive-value", encoding="utf-8")
    result = call(broker_for(setup))
    assert "hidden" not in result.data["text"]
    assert "sensitive-value" not in result.data["text"]
    assert "[REDACTED]" in result.data["text"]


def test_bearer_and_private_key_redaction(setup):
    (setup[1].source_root / "safe.txt").write_text(
        "Bearer TOP_SECRET\n-----BEGIN RSA PRIVATE KEY-----\nKEY_DATA\n-----END RSA PRIVATE KEY-----",
        encoding="utf-8",
    )
    result = call(broker_for(setup))
    assert result.status == "succeeded"
    assert "TOP_SECRET" not in result.data["text"]
    assert "KEY_DATA" not in result.data["text"]


@pytest.mark.parametrize("content", [b"123456", b"\xff", b"a\x00b"])
def test_oversized_or_binary_content_rejected(setup, content):
    setup[1].max_read_bytes = 5
    (setup[1].source_root / "safe.txt").write_bytes(content)
    assert call(broker_for(setup)).status == "failed"


def test_hardlink_denied(setup):
    root = setup[1].source_root
    os.link(root / "safe.txt", root / "alias.txt")
    assert call(broker_for(setup), "alias.txt").status == "denied"


def test_project_roots_are_isolated(setup, tmp_path):
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_b / "safe.txt").write_text("project b", encoding="utf-8")
    broker_a = broker_for(setup)
    setup[1].source_root = root_b
    setup[1].project_id = setup[2].project_id = "b"
    broker_b = broker_for(setup)
    assert call(broker_a).data == {"text": "hello"}
    assert call(broker_b, project_id="b").data == {"text": "project b"}
    assert call(broker_a, project_id="b").status == "denied"


@pytest.mark.skipif(os.name != "nt", reason="Windows junction test")
def test_junction_escape_denied(setup, tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file.txt").write_text("TOP_SECRET", encoding="utf-8")
    setup[1].source_root = root
    link = root / "linked"
    completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
    assert completed.returncode == 0
    try:
        assert call(broker_for(setup), "linked/file.txt").status == "denied"
    finally:
        link.rmdir()
