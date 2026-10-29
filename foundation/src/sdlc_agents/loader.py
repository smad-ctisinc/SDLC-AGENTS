"""Load one explicitly selected contract; no discovery or execution."""

from pathlib import Path

import yaml
from yaml.events import AliasEvent
from yaml.nodes import MappingNode

from .contracts import AgentContract

MAX_CONTRACT_BYTES = 256 * 1024
MAX_YAML_DEPTH = 64


class ContractLoadError(ValueError):
    """Safe diagnostic for a contract that could not be read or validated."""


class _ContractLoader(yaml.SafeLoader):
    """Reject ambiguous keys and aliases instead of silently overwriting values."""

    def __init__(self, stream):
        super().__init__(stream)
        self._depth = 0

    def compose_node(self, parent, index):
        if self.check_event(AliasEvent):
            raise ContractLoadError("YAML aliases are unsupported in contracts")
        self._depth += 1
        try:
            if self._depth > MAX_YAML_DEPTH:
                raise ContractLoadError("Contract YAML exceeds the nesting limit")
            return super().compose_node(parent, index)
        finally:
            self._depth -= 1

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, MappingNode):
            raise ContractLoadError("Expected a YAML mapping")
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ContractLoadError("Contract mapping keys must be strings")
            if key in result:
                raise ContractLoadError("Duplicate YAML mapping key")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def load_contract(path: str | Path) -> AgentContract:
    """Read bounded UTF-8 YAML and return a validated, provider-neutral contract.

    The caller selects and authorizes the path. This is not a filesystem policy
    layer. Messages omit file contents, including Pydantic/YAML input excerpts.
    """
    try:
        with Path(path).open("rb") as stream:
            content = stream.read(MAX_CONTRACT_BYTES + 1)
    except OSError:
        raise ContractLoadError("Cannot read contract file") from None
    if len(content) > MAX_CONTRACT_BYTES:
        raise ContractLoadError("Contract exceeds the 256 KiB size limit")
    try:
        definition = yaml.load(content.decode("utf-8-sig"), Loader=_ContractLoader)
        if not isinstance(definition, dict):
            raise ContractLoadError("Contract root must be a mapping")
        return AgentContract.model_validate(definition)
    except ContractLoadError:
        raise
    except (ValueError, OverflowError, yaml.YAMLError, RecursionError):
        raise ContractLoadError("Invalid contract encoding, YAML, or contract fields") from None
