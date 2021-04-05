"""Test cases for the __main__ module."""
import pathlib
import tempfile
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional

import nbformat
import pytest
from nbformat.notebooknode import NotebookNode
from typer import testing
from typer.testing import CliRunner

import nbpreview
from nbpreview.__main__ import app


@pytest.fixture
def runner() -> CliRunner:
    """Fixture for invoking command-line interfaces."""
    return testing.CliRunner()


def test_main_succeeds(
    runner: CliRunner,
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode],
) -> None:
    """It exits with a status code of zero with a valid file."""
    with tempfile.NamedTemporaryFile() as notebook_file:
        notebook_path = notebook_file.name
        notebook_node = make_notebook(None)
        pathlib.Path(notebook_file.name).write_text(nbformat.writes(notebook_node))
        result = runner.invoke(app, [notebook_path])
        assert result.exit_code == 0


def test_version(runner: CliRunner) -> None:
    """It returns the version number."""
    result = runner.invoke(app, ["--version"])
    assert result.stdout == f"nbpreview {nbpreview.__version__}\n"


def test_exit_invalid_file_status(runner: CliRunner) -> None:
    """It exits with a status code of 1 when fed an invalid file."""
    with tempfile.NamedTemporaryFile() as invalid_file:
        invalid_path = invalid_file.name
        result = runner.invoke(app, [invalid_path])
        assert result.exit_code == 1


def test_exit_invalid_file_output(runner: CliRunner) -> None:
    """It outputs a message when fed an invalid file."""
    with tempfile.NamedTemporaryFile() as invalid_file:
        invalid_path = invalid_file.name
        result = runner.invoke(app, [invalid_path])
        assert (
            result.output.replace("\n", "")
            == f"{invalid_path} is not a valid Jupyter Notebook path."
        )
