"""Validate execution messages without implementing or invoking a runner."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from sdlc_agents import (
    ErrorDetails, ExecutionRequest, ExecutionResult, ProjectContext, UsageMetrics,
)


@pytest.fixture
def result_data():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "run_id": "run-001", "project_id": "project-a",
        "agent_id": "foundation-probe", "agent_version": "0.1.0",
        "status": "succeeded", "started_at": started,
        "finished_at": started + timedelta(seconds=1), "duration_seconds": 1.0,
        "output": {"status": "ok"},
    }


def test_project_scoped_request_round_trip():
    context = ProjectContext(project_id="project-a", metadata={"language": "Java"})
    request = ExecutionRequest(project_id="project-a", agent_id="foundation-probe", inputs={}, context=context)
    assert ExecutionRequest.model_validate_json(request.model_dump_json()) == request


def test_context_project_mismatch_rejected():
    with pytest.raises(ValidationError, match="must match"):
        ExecutionRequest(project_id="a", agent_id="foundation-probe", inputs={}, context=ProjectContext(project_id="b"))


@pytest.mark.parametrize("model,data", [
    (ProjectContext, {}),
    (ProjectContext, {"project_id": " "}),
    (ProjectContext, {"project_id": "a", "revision": -1}),
    (ProjectContext, {"project_id": "a", "metadata": {"x": float("nan")}}),
    (ProjectContext, {"project_id": "a", "components": [{"x": (1, 2)}]}),
    (ExecutionRequest, {"agent_id": "probe", "inputs": {}}),
    (ExecutionRequest, {"project_id": "a", "agent_id": "probe", "inputs": {1: "x"}}),
    (UsageMetrics, {"tool_calls": -1}),
    (UsageMetrics, {"input_tokens": "2"}),
    (UsageMetrics, {"estimated_cost_usd": float("inf")}),
    (ErrorDetails, {"code": "FAIL", "message": " "}),
])
def test_invalid_message_fields(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_result_round_trip(result_data):
    result = ExecutionResult(**result_data)
    assert ExecutionResult.model_validate_json(result.model_dump_json()) == result
    assert result.usage.input_tokens is None
    assert result.usage.tool_calls == 0


@pytest.mark.parametrize("status", ["failed", "timed_out", "cancelled", "approval_required"])
def test_non_success_results_require_error(result_data, status):
    result_data.update(status=status, output=None)
    with pytest.raises(ValidationError):
        ExecutionResult(**result_data)
    result_data["error"] = ErrorDetails(code="TEST", message="Synthetic outcome")
    assert ExecutionResult(**result_data).status == status


@pytest.mark.parametrize("field,value", [
    ("status", "running"), ("run_id", ""), ("duration_seconds", -1.0),
    ("duration_seconds", float("nan")), ("started_at", datetime(2026, 1, 1)),
    ("finished_at", datetime(2025, 1, 1, tzinfo=timezone.utc)),
    ("output", None), ("output", {"x": {1, 2}}),
    ("error", ErrorDetails(code="FAIL", message="Synthetic error")),
])
def test_invalid_results(result_data, field, value):
    result_data[field] = value
    with pytest.raises(ValidationError):
        ExecutionResult(**result_data)


def test_project_context_defaults_are_independent():
    first = ProjectContext(project_id="a")
    second = ProjectContext(project_id="b")
    first.metadata["test"] = True
    assert second.metadata == {}


def test_unresolved_version_only_allowed_for_unsuccessful_results(result_data):
    result_data.pop("agent_version")
    with pytest.raises(ValidationError):
        ExecutionResult(**result_data)
    result_data.update(status="failed", output=None,
                       error=ErrorDetails(code="agent_not_found", message="Not found"))
    assert ExecutionResult(**result_data).agent_version is None
