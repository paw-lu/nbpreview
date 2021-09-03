"""Test cases for the __main__ module."""
import pathlib
import shlex
import sys
import tempfile
import textwrap
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generator
from typing import IO
from typing import Iterable
from typing import Mapping
from typing import Optional
from typing import Union

import nbformat
import pytest
from _pytest.monkeypatch import MonkeyPatch
from click.testing import Result
from nbformat.notebooknode import NotebookNode
from typer import testing
from typer.testing import CliRunner

import nbpreview
from nbpreview.__main__ import app

if sys.version_info >= (3, 8):
    from typing import Protocol
else:
    from typing_extensions import Protocol


class RunCli(Protocol):
    """Typing protocol for run_cli."""

    def __call__(
        self,
        cell: Optional[Dict[str, Any]] = None,
        args: Optional[Union[str, Iterable[str]]] = None,
        input: Optional[Union[bytes, str, IO[Any]]] = None,
        env: Optional[Mapping[str, str]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> Result:
        """Callable types."""
        ...


@pytest.fixture(autouse=True)
def patch_env(monkeypatch: MonkeyPatch) -> None:
    """Patch environmental variables that affect tests."""
    for environment_variable in (
        "TERM",
        "NO_COLOR",
        "PAGER",
        "NBPREVIEW_PLAIN",
        "NBPREVIEW_THEME",
        "NBPREVIEW_UNICODE",
        "NBPREVIEW_WIDTH",
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


@pytest.fixture
def run_cli(
    runner: CliRunner,
    write_notebook: Callable[[Union[Dict[str, Any], None]], str],
) -> RunCli:
    """Fixture for running the cli against a notebook file."""

    def _run_cli(
        cell: Optional[Dict[str, Any]] = None,
        args: Optional[Union[str, Iterable[str]]] = None,
        input: Optional[Union[bytes, str, IO[Any]]] = None,
        env: Optional[Mapping[str, str]] = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> Result:
        r"""Runs the CLI against a notebook file.

        Args:
            cell (Optional[Dict[str, Any]], optional): The cell to add
                to the notebook file. Defaults to None.
            args (Optional[Union[str, Iterable[str]]]): The extra
                arguments to invoke. By default --width=80 and
                --unicode are included.
            input (Optional[Union[bytes, Text, IO[Any]]]): The input
                data. By default None.
            env (Optional[Mapping[str, str]]): The environmental
                overrides. By default None.
            catch_exceptions (bool): Whether to catch exceptions.
            color (bool): Whether the output should contain color codes.
            **extra (Any): Extra arguments to pass.

        Returns:
            Result: The result from running the CLI command against the
                notebook.
        """
        notebook_path = write_notebook(cell)
        if isinstance(args, str):
            args = shlex.split(args)
        default_args = ["--decorated", "--unicode", "--width=80", notebook_path]
        full_args = [*args, *default_args] if args is not None else default_args
        result = runner.invoke(
            app,
            args=full_args,
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **extra,
        )
        return result

    return _run_cli


def test_main_succeeds(run_cli: RunCli) -> None:
    """It exits with a status code of zero with a valid file."""
    result = run_cli()
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


def test_render_notebook(run_cli: RunCli) -> None:
    """It renders a notebook."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    result = run_cli(code_cell)
    expected_output = textwrap.dedent(
        """\
         ╭─────────────────────────────────────────────────────────────────────────╮
    [2]: │ def foo(x: float, y: float) -> float:                                   │
         │     return x + y                                                        │
         ╰─────────────────────────────────────────────────────────────────────────╯
    """
    )
    assert result.output == expected_output


def test_render_markdown(run_cli: RunCli) -> None:
    """It renders a markdown cell."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "Lorep",
    }
    result = run_cli(markdown_cell)
    assert result.output == (
        "  Lorep                                                    "
        "                     \n"
    )


@pytest.mark.parametrize(
    "args, env",
    (("--plain", None), ("-p", None), (None, {"NBPREVIEW_PLAIN": "TRUE"})),
)
def test_force_plain(
    args: Optional[str],
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
    result = runner.invoke(
        app, args=["--unicode", "--width=80", notebook_path], env=env
    )
    expected_output = (
        "def foo(x: float, y: float) -> float:                         "
        "                  \n    return x + y                          "
        "                                      \n"
    )
    assert result.output == expected_output
