"""Native symlink coverage: Linux must execute these checks, never skip them."""

import asyncio
import hashlib
import os

import pytest
from typer.testing import CliRunner

from sdlc_agents import JsonContextStore, ContextStoreError, ProjectContext
from sdlc_agents.cli import app
from sdlc_agents.tools import ReadTextTool
from sdlc_agents.tools.base import ToolAccessError, ToolContext


def link_to(link, target, directory=False):
    try:
        link.symlink_to(target, target_is_directory=directory)
    except OSError:
        if os.name != "nt":
            raise
        pytest.skip("Windows symlink privileges unavailable")


@pytest.mark.parametrize("kind", ["root", "file", "parent", "broken"])
def test_storage_symlink_denied(tmp_path, kind):
    root = tmp_path / "state"
    root.mkdir()
    store = JsonContextStore(root, writable=True)
    store.save(ProjectContext(project_id="p"), expected_revision=0)
    path = root / (hashlib.sha256(b"p").hexdigest() + ".json")
    if kind in ("root", "parent"):
        link = tmp_path / "alias"
        link_to(link, root if kind == "root" else tmp_path, True)
        with pytest.raises(ContextStoreError):
            JsonContextStore(link if kind == "root" else link / "state")
    else:
        target = tmp_path / "outside.json"
        if kind == "file":
            target.write_bytes(path.read_bytes())
        path.unlink()
        link_to(path, target)
        with pytest.raises(ContextStoreError):
            store.read("p")
        with pytest.raises(ContextStoreError):
            store.save(ProjectContext(project_id="p"), expected_revision=0)


@pytest.mark.parametrize("directory", [False, True])
def test_read_tool_symlink_escape_denied(tmp_path, directory):
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("private")
    link_to(project / "alias", outside if directory else outside / "secret.txt", directory)
    context = ToolContext("p", "r", project, 1024, ())
    with pytest.raises(ToolAccessError):
        asyncio.run(ReadTextTool().invoke(
            {"path": "alias/secret.txt" if directory else "alias"}, context))


def test_cli_request_symlink_denied(tmp_path):
    target = tmp_path / "private.json"
    target.write_text('{"secret":"private"}')
    link = tmp_path / "request.json"
    link_to(link, target)
    result = CliRunner().invoke(app, [
        "run", "--agent-root", str(tmp_path), "--project-root", str(tmp_path),
        "--request", str(link), "--fake-output", str(target), "--executor", "fake",
    ])
    assert result.exit_code == 2
    assert "invalid_input" in result.stderr and "private" not in result.output
