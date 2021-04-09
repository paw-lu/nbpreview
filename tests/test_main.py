"""Test cases for the __main__ module."""
import pathlib
import tempfile
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generator
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


@pytest.fixture
def temp_file() -> Generator[Callable[[Optional[str]], str], None, None]:
    """Fixture that returns function to create temporary file.

    This is used in place of NamedTemporaryFile as a contex manager
    because of the inability to read from an open file created on
    Windows.

    Yields:
        Generator[Callable[[Optional[str]], str]: Function to create
            tempfile that is delted at teardown.
    """
    file = tempfile.NamedTemporaryFile(delete=False)
    file_name = file.name
    tempfile_path = pathlib.Path(file_name)

    def _named_temp_file(text: Optional[str] = None) -> str:
        """Create a temporary file.

        Args:
            text (Optional[str], optional): The text to fill the file
                with. Defaults to None, which creates a blank file.

        Returns:
            str: The path of the temporary file.
        """
        if text is not None:
            tempfile_path.write_text(text)
        file.close()
        return file_name

    yield _named_temp_file
    tempfile_path.unlink()


def test_main_succeeds(
    runner: CliRunner,
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode],
    temp_file: Callable[[Optional[str]], str],
) -> None:
    """It exits with a status code of zero with a valid file."""
    notebook_node = make_notebook(None)
    notebook_path = temp_file(nbformat.writes(notebook_node))
    result = runner.invoke(app, [notebook_path])
    assert result.exit_code == 0


def test_version(runner: CliRunner) -> None:
    """It returns the version number."""
    result = runner.invoke(app, ["--version"])
    assert result.stdout == f"nbpreview {nbpreview.__version__}\n"


def test_exit_invalid_file_status(
    runner: CliRunner,
    temp_file: Callable[[Optional[str]], str],
) -> None:
    """It exits with a status code of 1 when fed an invalid file."""
    invalid_path = temp_file(None)
    result = runner.invoke(app, [invalid_path])
    assert result.exit_code == 1


def test_exit_invalid_file_output(
    runner: CliRunner,
    temp_file: Callable[[Optional[str]], str],
) -> None:
    """It outputs a message when fed an invalid file."""
    invalid_path = temp_file(None)
    result = runner.invoke(app, [invalid_path])
    assert (
        result.output.replace("\n", "")
        == f"{invalid_path} is not a valid Jupyter Notebook path."
    )
