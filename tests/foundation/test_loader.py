"""Single-file contract loading, including ambiguous and unsafe YAML inputs."""

from pathlib import Path

import pytest

from sdlc_agents import ContractLoadError, load_contract
from sdlc_agents.loader import MAX_CONTRACT_BYTES

FIXTURE = Path(__file__).parents[1] / "fixtures/agents/foundation-probe/contract.yaml"


def test_load_fixture():
    contract = load_contract(FIXTURE)
    assert contract.agent.id == "foundation-probe"
    contract.validate_input({"project_id": "demo"})


def test_utf8_bom_supported(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8-sig")
    assert load_contract(path).contract_version == "1"


@pytest.mark.parametrize("content", [
    b"", b"null", b"[]", b"invalid: [", b"\xff",
    b"contract_version: '2'", b"contract_version: '1'\ncontract_version: '1'",
    b"agent:\n  id: first\n  id: second",
    b"x: &x {a: b}\ny: *x", b"x: &x [*x]",
    b"1: value", b"[a, b]: value", b"---\na: b\n---\nc: d",
    b"!!python/object/apply:os.system ['echo forbidden']",
    b"x: " + b"[" * 70 + b"0" + b"]" * 70,
])
def test_invalid_yaml_is_rejected(tmp_path, content):
    path = tmp_path / "contract.yaml"
    path.write_bytes(content)
    with pytest.raises(ContractLoadError):
        load_contract(path)


def test_oversized_yaml_rejected(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_bytes(b" " * (MAX_CONTRACT_BYTES + 1))
    with pytest.raises(ContractLoadError, match="size limit"):
        load_contract(path)


def test_unreadable_file(tmp_path):
    with pytest.raises(ContractLoadError, match="Cannot read"):
        load_contract(tmp_path / "missing.yaml")


def test_diagnostics_omit_sensitive_input(tmp_path):
    path = tmp_path / "contract.yaml"
    path.write_text("contract_version: SECRET_VALUE", encoding="utf-8")
    with pytest.raises(ContractLoadError) as caught:
        load_contract(path)
    assert "SECRET_VALUE" not in str(caught.value)


def test_invalid_contract_schema_rejected(tmp_path):
    path = tmp_path / "contract.yaml"
    text = FIXTURE.read_text(encoding="utf-8").replace("type: object", "type: unknown")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ContractLoadError):
        load_contract(path)


def test_oversized_integer_conversion_is_sanitized(tmp_path):
    import sys
    from sdlc_agents import ContractLoadError, FileSystemAgentRegistry, RegistryError
    limit = sys.get_int_max_str_digits()
    directory = tmp_path / 'foundation-probe'
    directory.mkdir()
    (directory / 'agent.md').write_text('synthetic')
    path = directory / 'contract.yaml'
    path.write_text('contract_version: ' + '9' * 5000)
    with pytest.raises(ContractLoadError) as caught:
        load_contract(path)
    assert '99999' not in str(caught.value)
    assert caught.value.__suppress_context__
    with pytest.raises(RegistryError):
        FileSystemAgentRegistry([tmp_path]).discover()
    assert sys.get_int_max_str_digits() == limit
