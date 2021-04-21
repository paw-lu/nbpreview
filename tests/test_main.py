"""Test cases for the __main__ module."""
import pathlib
import tempfile
import textwrap
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generator
from typing import Mapping
from typing import Optional
from typing import Union
from unittest.mock import Mock

import nbformat
import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from nbformat.notebooknode import NotebookNode
from pytest_mock import MockFixture
from typer import testing
from typer.testing import CliRunner

import nbpreview
from nbpreview.__main__ import app


@pytest.fixture(autouse=True)
def mock_isatty(mocker: MockFixture, request: FixtureRequest) -> Union[None, Mock]:
    """Make the CLI act as if running in a terminal."""
    if "no_atty_mock" not in request.keywords:
        mock: Mock = mocker.patch(
            "nbpreview.__main__.sys.stdout.isatty", return_value=True
        )
        return mock
    else:
        return None


@pytest.fixture(autouse=True)
def patch_env(monkeypatch: MonkeyPatch) -> None:
    """Patch environmental variables that affect tests."""
    for environment_variable in (
        "TERM",
        "NO_COLOR",
        "PAGER",
        "NBPREVIEW_THEME",
        "NBPREVIEW_PLAIN",
    ):
        monkeypatch.delenv(environment_variable, raising=False)


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


@pytest.fixture
def write_notebook(
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode],
    temp_file: Callable[[Optional[str]], str],
) -> Callable[[Union[Dict[str, Any], None]], str]:
    """Fixture for generating notebook files."""

    def _write_notebook(cell: Union[Dict[str, Any], None]) -> str:
        """Writes a notebook file.

        Args:
            cell (Union[Dict[str, Any], None]): The cell of the notebook
                to render

        Returns:
            str: The path of the notebook file.
        """
        notebook_node = make_notebook(cell)
        notebook_path = temp_file(nbformat.writes(notebook_node))
        return notebook_path

    return _write_notebook


def test_main_succeeds(
    runner: CliRunner,
    write_notebook: Callable[[Union[Dict[str, Any], None]], str],
) -> None:
    """It exits with a status code of zero with a valid file."""
    notebook_path = write_notebook(None)
    result = runner.invoke(app, [notebook_path])
    assert result.exit_code == 0


@pytest.mark.parametrize("option", ("--version", "-V"))
def test_version(runner: CliRunner, option: str) -> None:
    """It returns the version number."""
    result = runner.invoke(app, [option])
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


def test_render_notebook(
    runner: CliRunner,
    write_notebook: Callable[[Union[Dict[str, Any], None]], str],
) -> None:
    """It renders a notebook."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    notebook_path = write_notebook(code_cell)
    result = runner.invoke(app, [notebook_path])
    expected_output = textwrap.dedent(
        """\
         ╭─────────────────────────────────────────────────────────────────────────╮
    [2]: │ def foo(x: float, y: float) -> float:                                   │
         │     return x + y                                                        │
         ╰─────────────────────────────────────────────────────────────────────────╯
    """
    )
    assert result.output == expected_output


@pytest.mark.parametrize(
    "option, env",
    (("--plain", None), ("-p", None), (None, {"NBPREVIEW_PLAIN": "TRUE"})),
)
def test_force_plain(
    option: Optional[str],
    env: Optional[Mapping[str, str]],
    runner: CliRunner,
    write_notebook: Callable[[Union[Dict[str, Any], None]], str],
) -> None:
    """It renders in plain format when flag or env is specified."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    notebook_path = write_notebook(code_cell)
    args = ([option] if option is not None else []) + [notebook_path]
    result = runner.invoke(
        app,
        args=args,
        env=env,
    )
    expected_output = (
        "def foo(x: float, y: float) -> float:                         "
        "                  \n    return x + y                          "
        "                                      \n"
    )
    assert result.output == expected_output


@pytest.mark.no_atty_mock
def test_automatic_plain(
    runner: CliRunner,
    write_notebook: Callable[[Union[Dict[str, Any], None]], str],
) -> None:
    """It renders in plain format automatically when not in terminal."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    notebook_path = write_notebook(code_cell)
    result = runner.invoke(
        app,
        args=[notebook_path],
    )
    expected_output = (
        "def foo(x: float, y: float) -> float:                         "
        "                  \n    return x + y                          "
        "                                      \n"
    )
    assert result.output == expected_output
