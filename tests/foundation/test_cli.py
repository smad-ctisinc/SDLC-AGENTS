import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from sdlc_agents.cli import app

ROOT = Path(__file__).parents[1] / 'fixtures/agents'
runner = CliRunner()


def test_help_and_listing():
    assert runner.invoke(app, ['--help']).exit_code == 0
    args = ['list', '--agent-root', str(ROOT)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)[0]['agent_id'] == 'foundation-probe'
    assert result.stdout == runner.invoke(app, args).stdout


def test_validate():
    result = runner.invoke(app, ['validate', 'foundation-probe', '--agent-root', str(ROOT), '--version', '0.1.0'])
    assert result.exit_code == 0
    assert json.loads(result.stdout)['version'] == '0.1.0'


@pytest.mark.parametrize('identity', ['../outside', 'missing', 'INVALID'])
def test_bad_identity(identity):
    result = runner.invoke(app, ['validate', identity, '--agent-root', str(ROOT)])
    assert result.exit_code == 2
    assert json.loads(result.stderr) == {'error': 'invalid_registry'}


def run_args(tmp_path):
    request = tmp_path / 'request.json'
    request.write_text(json.dumps({'project_id': 'example', 'agent_id': 'foundation-probe', 'inputs': {'project_id': 'example'}}))
    output = tmp_path / 'output.json'
    output.write_text(json.dumps({'project_id': 'example', 'status': 'ok'}))
    return ['run', '--agent-root', str(ROOT), '--request', str(request), '--fake-output', str(output), '--project-root', str(tmp_path), '--executor', 'fake']


def test_run_success_is_read_only(tmp_path):
    args = run_args(tmp_path)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data['status'] == 'succeeded'
    assert data['usage']['model_calls'] == data['usage']['tool_calls'] == 0
    assert data['output'] == {'project_id': 'example', 'status': 'ok'}
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_invalid_output_is_execution_failure(tmp_path):
    args = run_args(tmp_path)
    (tmp_path / 'output.json').write_text('{}')
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert json.loads(result.stdout)['status'] == 'failed'


@pytest.mark.parametrize('content', ['{"secret":"private",', '{"a":1,"a":2}', '{"a":NaN}', '[]', '{"unknown":"private"}', '[' * 2000, ' ' * (1024 * 1024 + 1)], ids=['malformed', 'duplicate', 'nonfinite', 'array', 'unknown', 'deep', 'oversized'])
def test_bad_request_is_safe(tmp_path, content):
    args = run_args(tmp_path)
    (tmp_path / 'request.json').write_text(content)
    result = runner.invoke(app, args)
    assert result.exit_code == 2
    assert json.loads(result.stderr) == {'error': 'invalid_input'}
    assert 'private' not in result.output


def test_executor_must_be_explicit(tmp_path):
    args = run_args(tmp_path)
    assert runner.invoke(app, args[:-2]).exit_code == 2
    assert runner.invoke(app, args[:-1] + ['real']).exit_code == 2


def test_registry_error_and_empty_root(tmp_path):
    result = runner.invoke(app, ['list', '--agent-root', str(tmp_path)])
    assert result.exit_code == 0 and json.loads(result.stdout) == []
    (tmp_path / 'bad-agent').mkdir()
    assert runner.invoke(app, ['list', '--agent-root', str(tmp_path)]).exit_code == 2


def test_multiple_roots_require_explicit_version(tmp_path):
    import shutil
    other = tmp_path / 'other'
    shutil.copytree(ROOT, other)
    contract = other / 'foundation-probe/contract.yaml'
    contract.write_text(contract.read_text().replace('0.1.0', '0.2.0'))
    roots = ['--agent-root', str(ROOT), '--agent-root', str(other)]
    result = runner.invoke(app, ['list', *roots])
    assert [x['version'] for x in json.loads(result.stdout)] == ['0.1.0', '0.2.0']
    assert runner.invoke(app, ['validate', 'foundation-probe', *roots]).exit_code == 2
    assert runner.invoke(app, ['validate', 'foundation-probe', *roots, '--version', '0.2.0']).exit_code == 0


def test_permissions_are_not_granted_by_cli(tmp_path):
    import shutil
    args = run_args(tmp_path)
    other = tmp_path / 'agents'
    shutil.copytree(ROOT, other)
    contract = other / 'foundation-probe/contract.yaml'
    contract.write_text(contract.read_text().replace('network: false', 'network: true'))
    args[2] = str(other)
    result = runner.invoke(app, args)
    assert result.exit_code == 1
    assert json.loads(result.stdout)['error']['code'] == 'unsupported_permission'


def test_module_entrypoint():
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-m', 'sdlc_agents', 'list', '--agent-root', str(ROOT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]['agent_id'] == 'foundation-probe'


@pytest.mark.parametrize('command', [[], ['list'], ['validate'], ['run']])
def test_all_command_help(command):
    result = runner.invoke(app, [*command, '--help'])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize('command', [['list'], ['validate', 'foundation-probe']])
def test_oversized_yaml_integer_safe_cli_error(tmp_path, command):
    directory = tmp_path / 'foundation-probe'
    directory.mkdir()
    (directory / 'agent.md').write_text('synthetic')
    (directory / 'contract.yaml').write_text('contract_version: ' + '9' * 5000)
    result = runner.invoke(app, [*command, '--agent-root', str(tmp_path)])
    assert result.exit_code == 2
    assert json.loads(result.stderr) == {'error': 'invalid_registry'}
    assert '99999' not in result.output
