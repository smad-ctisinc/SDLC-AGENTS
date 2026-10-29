"""Behavioral tests for the portable contract boundary; no network or model calls."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from sdlc_agents import AgentContract, AgentDefinition, PayloadValidationError

FIXTURE = Path(__file__).parents[1] / "fixtures/agents/foundation-probe/contract.yaml"


@pytest.fixture
def definition():
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def test_valid_contract_and_payloads(definition):
    contract = AgentContract.model_validate(definition)
    contract.validate_input({"project_id": "example"})
    contract.validate_output({"project_id": "example", "status": "ok"})
    assert AgentContract.model_validate(contract.model_dump(by_alias=True)) == contract


@pytest.mark.parametrize("payload", [{}, {"project_id": ""}, {"project_id": 123}, {"project_id": "x", "extra": True}])
def test_invalid_input(definition, payload):
    with pytest.raises(PayloadValidationError):
        AgentContract.model_validate(definition).validate_input(payload)


@pytest.mark.parametrize("payload", [{"project_id": "x"}, {"project_id": "x", "status": "failed"}])
def test_invalid_output(definition, payload):
    with pytest.raises(PayloadValidationError):
        AgentContract.model_validate(definition).validate_output(payload)


@pytest.mark.parametrize("section,key,value", [
    (None, "contract_version", "2"),
    (None, "contract_version", 1),
    (None, "unexpected", True),
    ("agent", "id", "Bad ID"),
    ("agent", "version", "latest"),
    ("agent", "responsibilities", []),
    ("agent", "capabilities", [" "]),
    ("permissions", "network", "false"),
    ("permissions", "netwrok", True),
    ("execution", "timeout_seconds", 0),
    ("execution", "timeout_seconds", True),
    ("execution", "max_tool_calls", -1),
    ("execution", "max_model_calls", "3"),
    ("errors", "retry_policy", "automatic"),
    ("observability", "record_payloads", True),
    ("tools", "allowed", ["fs.read", "fs.read"]),
])
def test_invalid_contract_fields(definition, section, key, value):
    target = definition if section is None else definition[section]
    target[key] = value
    with pytest.raises(ValidationError):
        AgentContract.model_validate(definition)


@pytest.mark.parametrize("field", ["contract_version", "agent", "inputs", "outputs", "execution"])
def test_required_sections(definition, field):
    del definition[field]
    with pytest.raises(ValidationError):
        AgentContract.model_validate(definition)


def test_default_permissions_and_budgets_deny_access(definition):
    for field in ("permissions", "tools", "errors", "observability"):
        del definition[field]
    definition["execution"] = {"timeout_seconds": 30}
    contract = AgentContract.model_validate(definition)
    assert contract.permissions.model_dump() == {
        "filesystem": {"read": False, "write": False},
        "network": False, "subprocess": False, "external_write": False,
    }
    assert contract.tools.allowed == []
    assert contract.execution.max_tool_calls == contract.execution.max_model_calls == 0
    assert contract.observability.record_payloads is False


@pytest.mark.parametrize("schema", [
    {"type": "not-a-type"},
    {"type": "array"},
    {"type": "object", "required": "project_id"},
    {"type": "object", "$ref": "https://example.com/schema"},
    {"type": "object", "properties": {"x": {"$ref": "#/definitions/x"}}},
    {"type": "object", "$schema": "http://json-schema.org/draft-07/schema#"},
    {"type": "object", "default": float("nan")},
])
@pytest.mark.parametrize("section", ["inputs", "outputs"])
def test_invalid_or_unsupported_schemas(definition, schema, section):
    definition[section]["schema"] = schema
    with pytest.raises(ValidationError):
        AgentContract.model_validate(definition)


def test_nested_schema_constraints(definition):
    definition["inputs"]["schema"] = {
        "type": "object", "required": ["modules"],
        "properties": {"modules": {"type": "array", "minItems": 1,
            "items": {"type": "object", "required": ["name"],
                "properties": {"name": {"type": "string", "minLength": 1}}}}},
    }
    contract = AgentContract.model_validate(definition)
    contract.validate_input({"modules": [{"name": "api"}]})
    with pytest.raises(PayloadValidationError):
        contract.validate_input({"modules": [{"name": 1}]})


@pytest.mark.parametrize("payload", [{1: "x"}, {"x": float("inf")}, {"x": (1, 2)}, {"x": {1, 2}}])
def test_non_json_payloads_rejected(definition, payload):
    definition["inputs"]["schema"] = {"type": "object"}
    with pytest.raises(PayloadValidationError):
        AgentContract.model_validate(definition).validate_input(payload)


def test_cyclic_payload_rejected(definition):
    payload = {}
    payload["cycle"] = payload
    with pytest.raises(PayloadValidationError):
        AgentContract.model_validate(definition).validate_input(payload)


def test_error_message_does_not_include_payload(definition):
    with pytest.raises(PayloadValidationError) as error:
        AgentContract.model_validate(definition).validate_output({"project_id": "x", "status": "SECRET_VALUE"})
    assert "SECRET_VALUE" not in str(error.value)


def test_validation_does_not_mutate_input(definition):
    before = deepcopy(definition)
    AgentContract.model_validate(definition)
    assert definition == before


def test_agent_version_is_independent_of_contract_version(definition):
    definition["agent"]["version"] = "2.7.1"
    contract = AgentContract.model_validate(definition)
    assert contract.contract_version == "1"
    assert contract.agent.version == "2.7.1"


def test_portable_definition_round_trip(definition):
    agent = AgentDefinition(
        instructions=FIXTURE.with_name("agent.md").read_text(encoding="utf-8"),
        contract=AgentContract.model_validate(definition),
    )
    assert AgentDefinition.model_validate_json(agent.model_dump_json(by_alias=True)) == agent


@pytest.mark.parametrize("instructions", ["", " ", None])
def test_empty_agent_instructions_rejected(definition, instructions):
    with pytest.raises(ValidationError):
        AgentDefinition(instructions=instructions, contract=AgentContract.model_validate(definition))


@pytest.mark.parametrize("permissions", [
    {"filesystem": {"read": "true"}},
    {"filesystem": {"write": 1}},
    {"filesystem": {"execute": True}},
    {"network": None},
    {"external_write": "yes"},
])
def test_invalid_nested_permissions(definition, permissions):
    definition["permissions"] = permissions
    with pytest.raises(ValidationError):
        AgentContract.model_validate(definition)


@pytest.mark.parametrize('bad', [(1, 2), {1, 2}, b'bytes', {1: 'value'}, float('nan'), float('inf'), -float('inf')])
@pytest.mark.parametrize('field', ['default', 'examples', 'x-annotation'])
def test_schema_nested_annotations_reject_non_json_values(bad, field):
    from sdlc_agents.contracts import PayloadSchema
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PayloadSchema.model_validate({'schema': {'type': 'object', field: [{'nested': bad}]}})


@pytest.mark.parametrize('root', [True, [], b'{}', None])
def test_schema_requires_object_before_validation(root):
    from sdlc_agents.contracts import PayloadSchema
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PayloadSchema.model_validate({'schema': root})


def test_json_native_schema_annotation_roundtrip():
    from sdlc_agents.contracts import PayloadSchema
    data = {'schema': {'type': 'object', 'default': {'nested': [None, True, 1, 1.5, 'text', {}]}}}
    schema = PayloadSchema.model_validate(data)
    assert schema.model_dump(by_alias=True) == data
    assert PayloadSchema.model_validate_json(schema.model_dump_json(by_alias=True)) == schema
