"""Test cases for the __main__ module."""
import pathlib

import pytest
import typer.testing
from typer.testing import CliRunner

import nbpreview
from nbpreview.__main__ import app


@pytest.fixture
def runner() -> CliRunner:
    """Fixture for invoking command-line interfaces."""
    return typer.testing.CliRunner()


@pytest.fixture
def notebook() -> str:
    """Fixture for returning an example notebook."""
    return str(pathlib.Path(__file__).parent / pathlib.Path("notebook.ipynb"))


def test_main_succeeds(runner: CliRunner, notebook: str) -> None:
    """It exits with a status code of zero with a valid file."""
    result = runner.invoke(app, [notebook])
    assert result.exit_code == 0


def test_version(runner: CliRunner) -> None:
    """It returns the version number."""
    result = runner.invoke(app, ["--version"])
    assert result.stdout == f"nbpreview {nbpreview.__version__}\n"


def test_exit_invalid_file_status(runner: CliRunner) -> None:
    """It exits with a status code of 1 when fed an invalid file."""
    invalid_file = str(
        (pathlib.Path(__file__).parent / pathlib.Path("__init__.py")).resolve()
    )
    result = runner.invoke(app, [invalid_file])
    assert result.exit_code == 1


def test_exit_invalid_file_output(runner: CliRunner) -> None:
    """It outputs a message when fed an invalid file."""
    invalid_file = str(
        (pathlib.Path(__file__).parent / pathlib.Path("__init__.py")).resolve()
    )
    result = runner.invoke(app, [invalid_file])
    assert result.output == f"{invalid_file} is not a valid \nJupyter Notebook path.\n"
