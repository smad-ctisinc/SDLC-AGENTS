"""Guard the approved dependency direction using installed source modules."""

import ast
from pathlib import Path

import sdlc_agents
from sdlc_agents.execution import RunRecord
from sdlc_agents.runner import RunRecord as LegacyRunRecord


def test_run_record_import_compatibility():
    assert sdlc_agents.RunRecord is RunRecord is LegacyRunRecord


def test_foundation_dependency_boundaries():
    root = Path(sdlc_agents.__file__).parent
    models = {'contracts', 'context', 'execution'}
    services = {'runner', 'runtime', 'registry', 'loader', 'storage', 'tools', 'cli', 'testing'}
    for path in root.rglob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or '']
            else:
                continue
            for module in modules:
                top = module.split('.')[0]
                assert top not in {'agents', 'adapters', 'workflows', 'langgraph', 'openai', 'anthropic', 'boto3'}, (path, module)
                if path.stem in models:
                    assert top not in services, (path, module)
                if path.name != 'cli.py' and path.name != '__main__.py':
                    assert top not in {'cli', 'typer'}, (path, module)
                if 'storage' in path.relative_to(root).parts:
                    assert top not in {'runner', 'runtime'}, (path, module)
