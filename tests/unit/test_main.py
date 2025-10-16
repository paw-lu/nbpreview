"""Test cases for the __main__ module."""

import collections
import functools
import itertools
import json
import operator
import os
import pathlib
import platform
import shlex
import tempfile
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping
from pathlib import Path
from typing import IO, Any, Protocol
from unittest.mock import Mock

import nbformat
import pytest
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from click import testing
from click.testing import CliRunner, Result
from nbformat.notebooknode import NotebookNode
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot
from rich import console

import nbpreview
from nbpreview import __main__


class RunCli(Protocol):
    """Typing protocol for run_cli."""

    def __call__(
        self,
        cell: dict[str, Any] | None = None,
        args: str | Iterable[str] | None = None,
        input: bytes | str | IO[Any] | None = None,
        env: Mapping[str, str] | None = None,
        catch_exceptions: bool = True,
        color: bool = False,
        **extra: Any,
    ) -> Result:  # pragma: no cover
        """Callable types."""
        ...


@pytest.fixture
def notebook_path() -> Path:
    """Return path of example test notebook."""
    notebook_path = pathlib.Path(__file__).parent / pathlib.Path(
        "assets", "notebook.ipynb"
    )
    return notebook_path


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
def runner(monkeypatch: pytest.MonkeyPatch) -> CliRunner:
    """Fixture for invoking command-line interfaces."""
    return testing.CliRunner(
        env={"NBPREVIEW_NO_COLOR": "true", "NO_COLOR": "true", "TERM": "dumb"}
    )


@pytest.fixture
def temp_file() -> Generator[Callable[[str | None], str], None, None]:
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

    def _named_temp_file(text: str | None = None) -> str:
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
    make_notebook: Callable[[dict[str, Any] | None], NotebookNode],
    temp_file: Callable[[str | None], str],
) -> Callable[[dict[str, Any] | None], str]:
    """Fixture for generating notebook files."""

    def _write_notebook(cell: dict[str, Any] | None) -> str:
        """Writes a notebook file.

        Args:
            cell (Union[Dict[str, Any], None]): The cell of the notebook
                to render

        Returns:
            str: The path of the notebook file.
        """
        notebook_node = make_notebook(cell)
        notebook_path = temp_file(
            nbformat.writes(notebook_node)  # type: ignore[no-untyped-call]
        )
        return notebook_path

    return _write_notebook


@pytest.fixture
def run_cli(
    runner: CliRunner,
    write_notebook: Callable[[dict[str, Any] | None], str],
) -> RunCli:
    """Fixture for running the cli against a notebook file."""

    def _run_cli(
        cell: dict[str, Any] | None = None,
        args: str | Iterable[str] | None = None,
        input: bytes | str | IO[Any] | None = None,
        env: Mapping[str, str] | None = None,
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
        default_args = [
            "--decorated",
            "--unicode",
            "--width=80",
            "--theme=material",
            notebook_path,
        ]
        full_args = [*args, *default_args] if args is not None else default_args
        result = runner.invoke(
            __main__.typer_click_object,
            args=full_args,
            input=input,
            env=env,
            catch_exceptions=catch_exceptions,
            color=color,
            **extra,
        )
        return result

    return _run_cli


@pytest.fixture
def mock_stdin_tty(mocker: MockerFixture) -> Iterator[Mock]:
    """Fixture yielding mock stdin acting like a TTY."""
    return mocker.patch("nbpreview.__main__.stdin.isatty", return_value=True)  # type: ignore[no-any-return]


@pytest.fixture
def mock_stdout_tty(mocker: MockerFixture) -> Iterator[Mock]:
    """Fixture yielding mock stdout acting like a TTY."""
    return mocker.patch("nbpreview.__main__.stdout.isatty", return_value=True)  # type: ignore[no-any-return]


@pytest.fixture
def cli_arg(
    runner: CliRunner,
    notebook_path: Path,
    mock_terminal: Mock,
    remove_link_ids: Callable[[str], str],
    mock_tempfile_file: Mock,
    mock_stdin_tty: Mock,
    mock_stdout_tty: Mock,
) -> Callable[..., str]:
    """Return function that applies arguments to cli."""

    def _cli_arg(
        *args: str | None,
        truecolor: bool = False,
        paging: bool | None = False,
        material_theme: bool = True,
        images: bool = True,
        **kwargs: str | None,
    ) -> str:
        """Apply given arguments to cli.

        Args:
            *args (Union[str, None]): The extra arguments to pass to the
                command.
            truecolor (bool): Whether to pass
                '--color-system=truecolor' option. By default True.
            paging (Union[bool, None]): Whether to pass '--paging' or
                '--no-paging' option. By default False, which
                corresponds to '--no-paging'.
            material_theme (bool): Whether to set the theme to
                'material'. By default True.
            images (bool): Whether to pass '--images'. By default True.
            **kwargs (Union[str, None]): Environmental variables to set.
                Will be uppercased.

        Returns:
            str: The output of the invoked command.
        """
        cleaned_args = [arg for arg in args if arg is not None]
        upper_kwargs = runner.env | {
            name.upper(): value for name, value in kwargs.items() if value is not None
        }
        cli_args = [os.fsdecode(notebook_path), *cleaned_args]
        if images:
            cli_args.append("--images")
        if material_theme:
            cli_args.append("--theme=material")
        if truecolor:
            cli_args.append("--color-system=truecolor")
        if paging is True:
            cli_args.append("--paging")
        elif paging is False:
            cli_args.append("--no-paging")

        result = runner.invoke(
            __main__.typer_click_object,
            args=cli_args,
            color=False,
            env=upper_kwargs,
        )
        output = remove_link_ids(result.output)
        return output

    return _cli_arg


@pytest.fixture
def test_cli(
    cli_arg: Callable[..., str],
    remove_link_ids: Callable[[str], str],
    expected_output: str,
) -> Callable[..., None]:
    """Return fixture that tests expected argument output."""

    def _test_cli(
        *args: str | None,
        truecolor: bool = False,
        paging: bool | None = False,
        material_theme: bool = True,
        images: bool = True,
        **kwargs: str | None,
    ) -> None:
        """Tests expected argument output.

        Args:
            *args (Union[str, None]): The extra arguments to pass to the
                command.
            truecolor (bool): Whether to pass '--color-system=truecolor'
                option. By default True.
            paging (Union[bool, None]): Whether to pass '--paging' or
                '--no-paging' option. By default False, which
                corresponds to '--no-paging'.
            material_theme (bool): Whether to set the theme to
                'material'. By default True.
            images (bool): Whether to pass '--images'. By default True.
            **kwargs (Union[str, None]): Environmental variables to set.
                Will be uppercased.
        """
        output = cli_arg(
            *args,
            truecolor=truecolor,
            paging=paging,
            material_theme=material_theme,
            images=images,
            **kwargs,
        )
        assert output == remove_link_ids(expected_output)

    return _test_cli


@pytest.fixture
def test_cli_snapshot(
    cli_arg: Callable[..., str],
    remove_link_ids: Callable[[str], str],
    request: FixtureRequest,
    snapshot_with_dir: Snapshot,
) -> Callable[..., None]:
    """Return fixture that tests output using snapshots."""

    def _test_cli_snapshot(
        *args: str | None,
        truecolor: bool = False,
        paging: bool | None = False,
        material_theme: bool = True,
        images: bool = True,
        **kwargs: str | None,
    ) -> None:
        """Tests expected argument output using snapshots.

        Args:
            *args (Union[str, None]): The extra arguments to pass to the
                command.
            truecolor (bool): Whether to pass '--color-system=truecolor'
                option. By default True.
            paging (Union[bool, None]): Whether to pass '--paging' or
                '--no-paging' option. By default False, which
                corresponds to '--no-paging'.
            material_theme (bool): Whether to set the theme to
                'material'. By default True.
            images (bool): Whether to pass '--images'. By default True.
            **kwargs (Union[str, None]): Environmental variables to set.
                Will be uppercased.
        """
        output = cli_arg(
            *args,
            truecolor=truecolor,
            paging=paging,
            material_theme=material_theme,
            images=images,
            **kwargs,
        )
        test_name = request.node.name
        snapshot_with_dir.assert_match(remove_link_ids(output), f"{test_name}.txt")

    return _test_cli_snapshot


def test_no_duplicate_parameter_names() -> None:
    """It has only unique parameter names."""
    cli_parameters = __main__.typer_click_object.params
    all_options = itertools.chain(
        *(
            option_getter(parameter)
            for parameter in cli_parameters
            for option_getter in [
                operator.attrgetter("opts"),
                operator.attrgetter("secondary_opts"),
            ]
        )
    )
    option_count = collections.Counter(all_options)
    assert max(option_count.values()) == 1


def test_main_succeeds(run_cli: RunCli) -> None:
    """It exits with a status code of zero with a valid file."""
    result = run_cli()
    assert result.exit_code == 0


@pytest.mark.parametrize("option", ("--version", "-V"))
def test_version(runner: CliRunner, option: str) -> None:
    """It returns the version number."""
    result = runner.invoke(__main__.typer_click_object, [option])
    assert result.stdout == f"nbpreview {nbpreview.__version__}\n"


def test_exit_invalid_file_status(
    runner: CliRunner, temp_file: Callable[[str | None], str]
) -> None:
    """It exits with a status code of 2 when fed an invalid file."""
    invalid_path = temp_file(None)
    result = runner.invoke(__main__.typer_click_object, [invalid_path])
    assert result.exit_code == 2


def test_exit_invalid_file_output(
    runner: CliRunner,
    temp_file: Callable[[str | None], str],
    snapshot_with_dir: Snapshot,
) -> None:
    """It outputs a message when fed an invalid file."""
    invalid_path = temp_file(None)
    result = runner.invoke(__main__.typer_click_object, [invalid_path])
    output = result.output
    snapshot_with_dir.assert_match(output[:4], "test_exit_invalid_file_output.txt")


def test_render_notebook(run_cli: RunCli, snapshot_with_dir: Snapshot) -> None:
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
    snapshot_with_dir.assert_match(result.output, "test_render_notebook.txt")


def test_render_notebook_option(run_cli: RunCli, snapshot_with_dir: Snapshot) -> None:
    """It respects cli options."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    result = run_cli(code_cell, args="--color --color-system=256")
    output = result.output
    snapshot_with_dir.assert_match(output, "test_render_notebook_option.txt")


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
    "arg, env",
    (("--plain", None), ("-p", None), (None, {"NBPREVIEW_PLAIN": "TRUE"})),
)
def test_force_plain(
    arg: str | None,
    env: Mapping[str, str] | None,
    runner: CliRunner,
    write_notebook: Callable[[dict[str, Any] | None], str],
    snapshot_with_dir: Snapshot,
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
    args = ["--unicode", "--width=80", notebook_path]
    if arg is not None:
        args = [arg] + args
    result = runner.invoke(__main__.typer_click_object, args=args, env=env)
    snapshot_with_dir.assert_match(result.output, "test_force_plain.txt")


def test_raise_no_source(
    runner: CliRunner,
    temp_file: Callable[[str | None], str],
    make_notebook_dict: Callable[[dict[str, Any] | None], dict[str, Any]],
    snapshot_with_dir: Snapshot,
) -> None:
    """It returns an error message if there is no source."""
    no_source_cell = {
        "cell_type": "code",
        "outputs": [],
    }
    notebook_dict = make_notebook_dict(no_source_cell)
    notebook_path = temp_file(json.dumps(notebook_dict))
    result = runner.invoke(__main__.typer_click_object, args=[notebook_path])
    output = result.output
    # Only compare the prefix to avoid path-specific differences
    snapshot_with_dir.assert_match(output[:80], "test_raise_no_source.txt")


def test_raise_no_output(
    runner: CliRunner,
    temp_file: Callable[[str | None], str],
    make_notebook_dict: Callable[[dict[str, Any] | None], dict[str, Any]],
    snapshot_with_dir: Snapshot,
) -> None:
    """It returns an error message if no output in a code cell."""
    no_source_cell = {"cell_type": "code", "source": ["x = 1\n"]}
    notebook_dict = make_notebook_dict(no_source_cell)
    notebook_path = temp_file(json.dumps(notebook_dict))
    result = runner.invoke(__main__.typer_click_object, args=[notebook_path])
    output = result.output
    # Only compare the prefix to avoid path-specific differences
    snapshot_with_dir.assert_match(output[:80], "test_raise_no_output.txt")


@pytest.fixture
def mock_pygment_styles(mocker: MockerFixture) -> Iterator[Mock]:
    """Mock pygment styles.

    Control the styles outputted here so that test does not break every
    time pygments adds or removes a style
    """
    return mocker.patch(  # type: ignore[no-any-return]
        "nbpreview.option_values.styles.get_all_styles",
        return_value=(style for style in ("material", "monokai", "zenburn")),
    )


@pytest.fixture
def mock_terminal(mocker: MockerFixture) -> Iterator[Mock]:
    """Mock a modern terminal."""
    terminal_console = functools.partial(
        console.Console,
        color_system="truecolor",
        force_terminal=True,
        width=100,
        no_color=True,
        legacy_windows=False,
        force_jupyter=False,
    )
    return mocker.patch("nbpreview.__main__.console.Console", new=terminal_console)  # type: ignore[no-any-return]


def test_default_color_system_auto(
    runner: CliRunner,
    mocker: MockerFixture,
    notebook_path: Path,
) -> None:
    """Its default value is 'auto'."""
    mock = mocker.patch("nbpreview.__main__.console.Console")
    runner.invoke(
        __main__.typer_click_object, args=[os.fsdecode(notebook_path)], color=False
    )
    # console.Console is called multiple times, first time should be
    # console representing terminal
    assert mock.call_args_list[0].kwargs["color_system"] == "auto"


def test_list_themes(
    runner: CliRunner,
    mocker: MockerFixture,
    mock_terminal: Mock,
    mock_pygment_styles: Mock,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders an example of all available themes."""
    result = runner.invoke(
        __main__.typer_click_object,
        args=["--list-themes"],
        color=False,
    )
    output = result.output
    snapshot_with_dir.assert_match(output, "test_list_themes.txt")


@pytest.mark.parametrize("option_name", ("--list-themes", "--lt"))
def test_list_themes_no_terminal(
    option_name: str, runner: CliRunner, mock_pygment_styles: Mock
) -> None:
    """It lists all themes with no preview when not a terminal."""
    result = runner.invoke(
        __main__.typer_click_object, args=[option_name], env={"TTY_COMPATIBLE": "0"}
    )
    output = result.output
    expected_output = (
        "material\nmonokai\nzenburn\nlight / ansi_light\ndark / ansi_dark\n"
    )
    assert output == expected_output


def test_render_notebook_file(test_cli_snapshot: Callable[..., None]) -> None:
    """It renders a notebook file."""
    test_cli_snapshot()


@pytest.mark.parametrize(
    "option_name, theme, env",
    (
        ("--theme", "light", None),
        ("-t", "dark", None),
        ("-t", "monokai", None),
        (None, None, "default"),
    ),
)
def test_change_theme_notebook_file(
    option_name: str | None,
    theme: str | None,
    env: str | None,
    test_cli_snapshot: Callable[..., None],
) -> None:
    """It changes the theme of the notebook."""
    args: list[str | None]
    args = (
        [option_name, theme]
        if theme is not None and option_name is not None
        else [None]
    )
    test_cli_snapshot(*args, nbpreview_theme=env, material_theme=False)


@pytest.mark.parametrize(
    "option_name, env", (("--hide-output", None), ("-h", None), (None, "1"))
)
def test_hide_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It hides the output of a notebook file."""
    test_cli_snapshot(option_name, nbpreview_hide_output=env)


@pytest.mark.parametrize(
    "option_name, env", (("--plain", None), ("-p", None), (None, "1"))
)
def test_plain_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It renders a notebook in a plain format."""
    test_cli_snapshot(option_name, nbpreview_plain=env)


@pytest.mark.parametrize(
    "option_name, env",
    (
        ("--unicode", None),
        ("-u", None),
        ("--no-unicode", None),
        ("-x", None),
        (None, "0"),
    ),
)
def test_unicode_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It renders a notebook with and without unicode characters."""
    test_cli_snapshot(option_name, nbpreview_unicode=env)


@pytest.mark.parametrize(
    "option_name, env",
    (("--nerd-font", None), ("-n", None), (None, "1")),
)
def test_nerd_font_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It renders a notebook with nerd font characters."""
    test_cli_snapshot(option_name, nbpreview_nerd_font=env)


@pytest.mark.parametrize(
    "option_name, env",
    (("--no-files", None), ("-l", None), (None, "1")),
)
def test_files_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It does not write temporary files if options are specified."""
    test_cli_snapshot(option_name, nbpreview_no_files=env)


@pytest.mark.parametrize(
    "option_name, env",
    (("--positive-space", None), ("-s", None), (None, "1")),
)
def test_positive_space_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It draws images in positive space if options are specified."""
    test_cli_snapshot(
        option_name, "--image-drawing=character", nbpreview_positive_space=env
    )


@pytest.mark.parametrize(
    "option_name, env",
    (
        ("--hyperlinks", None),
        ("-k", None),
        (None, "1"),
        ("--no-hyperlinks", None),
        ("-r", None),
        (None, "0"),
    ),
)
def test_hyperlinks_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It includes or excludes hyperlinks depending on options."""
    test_cli_snapshot(option_name, nbpreview_hyperlinks=env)


@pytest.mark.parametrize(
    "option_name, env",
    (
        ("--hide-hyperlink-hints", None),
        ("-y", None),
        (None, "1"),
    ),
)
def test_hyperlink_hints_output_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It does not render hints to click the hyperlinks."""
    test_cli_snapshot(option_name, nbpreview_hide_hyperlink_hints=env)


@pytest.mark.parametrize(
    "option_name, env",
    [
        ("--no-images", None),
        ("-e", None),
        ("--images", None),
        ("-i", None),
        (None, None),
        (None, "1"),
        (None, "0"),
    ],
)
def test_image_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It does not draw images when specified."""
    test_cli_snapshot(option_name, nbpreview_images=env, images=False)


def test_no_color_no_image(test_cli_snapshot: Callable[..., None]) -> None:
    """By default images will not render if no color."""
    test_cli_snapshot("--no-color", images=False)


@pytest.mark.parametrize(
    "option_name, drawing_type, env",
    (
        ("--image-drawing", "braille", None),
        ("--id", "character", None),
        (None, None, "braille"),
        ("--image-drawing", "block", None),
    ),
)
def test_image_drawing_notebook_file(
    option_name: str | None,
    drawing_type: str | None,
    env: str | None,
    test_cli_snapshot: Callable[..., None],
) -> None:
    """It draws images only when option is set."""
    arg = (
        f"{option_name}={drawing_type}"
        if option_name is not None and drawing_type is not None
        else None
    )
    test_cli_snapshot(
        arg,
        nbpreview_image_drawing=env,
    )


@pytest.mark.parametrize(
    "option_name, drawing_type",
    [("--image-drawing", "braille"), ("--image-drawing", "block")],
)
def test_render_narrow_notebook(
    option_name: str, drawing_type: str, test_cli_snapshot: Callable[..., None]
) -> None:
    """It renders a notebook when the width is small."""
    test_cli_snapshot(f"{option_name}={drawing_type}", "--width=4")


@pytest.mark.parametrize(
    "option_name, env_name, env_value",
    (
        ("--color", None, None),
        ("-c", None, None),
        ("--no-color", None, None),
        ("-o", None, None),
        (None, "NBPREVIEW_COLOR", "0"),
        (None, "NO_COLOR", "1"),
        (None, "NBPREVIEW_NO_COLOR", "true"),
        (None, "TERM", "dumb"),
    ),
)
def test_color_notebook_file(
    option_name: str | None,
    env_name: str | None,
    env_value: str | None,
    test_cli_snapshot: Callable[..., None],
) -> None:
    """It does not use color when specified."""
    if env_name is not None:
        test_cli_snapshot(option_name, **{env_name: env_value})
    else:
        test_cli_snapshot(option_name)


@pytest.mark.parametrize(
    "option_name, color_system, env_value",
    (
        ("--color-system", "standard", None),
        ("--color-system", "none", None),
        ("--cs", "256", None),
        (None, None, "windows"),
    ),
)
def test_color_system_notebook_file(
    option_name: str | None,
    color_system: str | None,
    env_value: str | None,
    test_cli_snapshot: Callable[..., None],
) -> None:
    """It uses different color systems depending on option value."""
    arg = (
        f"{option_name}={color_system}"
        if option_name is not None and color_system is not None
        else None
    )
    test_cli_snapshot(arg, truecolor=False, nbpreview_color_system=env_value)


@pytest.mark.parametrize(
    "option_name, env",
    (("--line-numbers", None), ("-m", None), (None, "1")),
)
def test_line_numbers_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It renders a notebook file with line numbers."""
    test_cli_snapshot(option_name, nbpreview_line_numbers=env)


@pytest.mark.parametrize(
    "option_name, env",
    (("--code-wrap", None), ("-q", None), (None, "1")),
)
def test_code_wrap_notebook_file(
    option_name: str | None, env: str | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It renders a notebook file with line numbers."""
    test_cli_snapshot(option_name, nbpreview_code_wrap=env)


@pytest.mark.parametrize("paging", [True, None])
def test_paging_notebook_stdout_file(
    paging: bool | None, test_cli_snapshot: Callable[..., None]
) -> None:
    """It simply prints the text when not in a terminal."""
    test_cli_snapshot("--color", paging=paging)


@pytest.fixture
def echo_via_pager_mock(mocker: MockerFixture) -> Iterator[Mock]:
    """Return a mock for click.echo_via_pager."""
    return mocker.patch("nbpreview.__main__.click.echo_via_pager")  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    "option_name, code_lines, is_expected_called",
    (
        ("--no-paging", 300, False),
        ("--paging", 1, True),
        ("-g", 50, True),
        ("-f", 400, False),
        ("", 500, True),
        ("", 2, False),
    ),
)
def test_automatic_paging_notebook(
    run_cli: RunCli,
    mock_terminal: Mock,
    echo_via_pager_mock: Mock,
    option_name: str,
    code_lines: int,
    is_expected_called: bool,
    mock_stdin_tty: Mock,
    mock_stdout_tty: Mock,
) -> None:
    """It uses the pager only when notebook is long or forced."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "[i for i in range(20)]\n" * code_lines,
    }
    run_cli(code_cell, option_name, env={"TERM": "xterm"})
    assert echo_via_pager_mock.called is is_expected_called


@pytest.mark.parametrize(
    "option_name, color", (("--color", True), ("--no-color", False), (None, None))
)
def test_color_passed_to_pager(
    cli_arg: Callable[..., str],
    echo_via_pager_mock: Mock,
    mock_terminal: Mock,
    option_name: str | None,
    color: bool | None,
) -> None:
    """It passes the color arg value to the pager."""
    cli_arg(
        option_name,
        paging=True,
        term="xterm",
        no_color="false",
        nbpreview_no_color="false",
    )
    color_arg = echo_via_pager_mock.call_args[1]["color"]
    assert color_arg == color


@pytest.mark.parametrize("file_argument", [None, "-"])
def test_render_stdin(
    file_argument: None | str,
    runner: CliRunner,
    notebook_path: Path,
    mock_tempfile_file: Mock,
    mock_terminal: Mock,
    remove_link_ids: Callable[[str], str],
    snapshot_with_dir: Snapshot,
    request: FixtureRequest,
) -> None:
    """It treats stdin as a file's text and renders a notebook."""
    stdin = notebook_path.read_text()
    args = ["--color-system=truecolor", "--no-images", "--theme=material"]
    if file_argument is not None:
        args.append(file_argument)
    result = runner.invoke(__main__.typer_click_object, args=args, input=stdin)
    output = result.output
    test_name = request.node.name
    snapshot_with_dir.assert_match(remove_link_ids(output), f"{test_name}.txt")


def test_stdin_cwd_path(
    runner: CliRunner,
    make_notebook: Callable[[dict[str, Any] | None], NotebookNode],
    remove_link_ids: Callable[[str], str],
    mock_terminal: Mock,
) -> None:
    """It uses the current working the directory when using stdin."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Test image](image.png)",
    }
    notebook_nodes = make_notebook(markdown_cell)
    notebook_stdin = nbformat.writes(notebook_nodes)  # type: ignore[no-untyped-call]
    current_working_directory = pathlib.Path.cwd()
    result = runner.invoke(
        __main__.typer_click_object,
        args=["--color-system=truecolor", "--no-images", "--theme=material"],
        input=notebook_stdin,
        env={"TERM": "xterm", "NBPREVIEW_NO_COLOR": "false"},
    )
    output = result.output
    expected_output = (
        f"  \x1b]8;id=230279;file://{current_working_directory.resolve() / 'image.png'}"
        "\x1b\\🖼 Click to view Test image\x1b]8;;\x1b\\"
        "                                                    \n"
        "                                                            "
        "                    \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_multiple_files(
    runner: CliRunner,
    write_notebook: Callable[[dict[str, Any] | None], str],
    notebook_path: Path,
    mock_terminal: Mock,
    snapshot_with_dir: Snapshot,
    temp_file: Callable[[str | None], str],
) -> None:
    """It renders multiple files."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    # Use temp_file instead of write_notebook to get consistent path for snapshot
    import nbformat

    notebook_node_dict = {
        "cells": [code_cell],
        "metadata": {},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_json = nbformat.writes(nbformat.from_dict(notebook_node_dict))  # type: ignore[no-untyped-call]
    code_notebook_path = temp_file(notebook_json)

    result = runner.invoke(
        __main__.typer_click_object,
        args=[
            code_notebook_path,
            code_notebook_path,
            "--color-system=truecolor",
            "--theme=material",
        ],
    )
    output = result.output
    # Replace dynamic path with a placeholder
    import re

    output = re.sub(r"┏━ /.*?/tmp[^ ]+ ", "┏━ TEMPFILE ", output)
    snapshot_with_dir.assert_match(output, "test_multiple_files.txt")


def test_multiple_files_long_path() -> None:
    """It shortens the title to the filename if the path is long."""
    path = pathlib.Path("very", "long", "path")
    output = __main__._create_file_title(path, width=7)
    expected_output = "path"
    assert output == expected_output


def test_file_and_stdin(
    runner: CliRunner,
    write_notebook: Callable[[dict[str, Any] | None], str],
    notebook_path: Path,
    mock_terminal: Mock,
    snapshot_with_dir: Snapshot,
    normalize_paths: Callable[[str], str],
) -> None:
    """It renders both a file and stdin."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    code_notebook_path = write_notebook(code_cell)
    stdin = pathlib.Path(code_notebook_path).read_text()
    result = runner.invoke(
        __main__.typer_click_object,
        args=["--color-system=truecolor", "--theme=material", code_notebook_path, "-"],
        input=stdin,
    )
    output = normalize_paths(result.output)
    snapshot_with_dir.assert_match(output, "test_file_and_stdin.txt")


def test_multiple_files_plain(
    runner: CliRunner,
    write_notebook: Callable[[dict[str, Any] | None], str],
    mock_terminal: Mock,
    snapshot_with_dir: Snapshot,
    normalize_paths: Callable[[str], str],
) -> None:
    """It does not draw a border around files when in plain mode."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    code_notebook_path = write_notebook(code_cell)
    result = runner.invoke(
        __main__.typer_click_object,
        args=[
            "--color-system=truecolor",
            "--plain",
            "--theme=material",
            code_notebook_path,
            code_notebook_path,
        ],
    )
    output = normalize_paths(result.output)
    snapshot_with_dir.assert_match(output, "test_multiple_files_plain.txt")


def test_multiple_files_all_fail(
    runner: CliRunner, temp_file: Callable[[str | None], str]
) -> None:
    """It exists with a status code of 2 when fed invalid files."""
    invalid_path = temp_file(None)
    result = runner.invoke(__main__.typer_click_object, [invalid_path, invalid_path])
    assert result.exit_code == 2


def test_multiple_files_all_fail_message(
    runner: CliRunner,
    temp_file: Callable[[str | None], str],
    snapshot_with_dir: Snapshot,
    normalize_paths: Callable[[str], str],
) -> None:
    """It exists with a status code of 2 when fed invalid files."""
    invalid_path = temp_file(None)
    result = runner.invoke(__main__.typer_click_object, [invalid_path, invalid_path])
    output = normalize_paths(result.output)
    snapshot_with_dir.assert_match(output, "test_multiple_files_all_fail_message.txt")


def test_multiple_files_some_fail(
    runner: CliRunner,
    write_notebook: Callable[[dict[str, Any] | None], str],
    notebook_path: Path,
    mock_terminal: Mock,
    snapshot_with_dir: Snapshot,
    normalize_paths: Callable[[str], str],
) -> None:
    """It still renders valid files when some are invalid."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    code_notebook_path = write_notebook(code_cell)
    invalid_file_path = os.fsdecode(pathlib.Path(__file__))
    result = runner.invoke(
        __main__.typer_click_object,
        args=[
            "--color-system=truecolor",
            "--theme=material",
            code_notebook_path,
            invalid_file_path,
        ],
    )
    output = normalize_paths(result.output)
    snapshot_with_dir.assert_match(output, "test_multiple_files_some_fail.txt")


def test_help(runner: CliRunner, snapshot_with_dir: Snapshot) -> None:
    """It returns a help message when prompted."""
    result = runner.invoke(__main__.typer_click_object, args=["--help"])
    output = result.output
    # Only compare the first 300 characters to avoid version-specific differences
    snapshot_with_dir.assert_match(output[:300], "test_help.txt")


@pytest.mark.skipif(
    platform.system() == "Windows", reason="Does not colorize on Windows terminals."
)
def test_color_help(runner: CliRunner, snapshot_with_dir: Snapshot) -> None:
    """It colors the help message when prompted."""
    result = runner.invoke(__main__.typer_click_object, args=["--help"], color=False)
    output = result.output
    # Only compare the first 300 characters to avoid version-specific differences
    snapshot_with_dir.assert_match(output[:300], "test_color_help.txt")
