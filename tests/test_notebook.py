"""Test cases for render."""
import io
import itertools
import json
import pathlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from typing import Callable
from typing import ContextManager
from typing import Dict
from typing import Generator
from typing import Optional
from typing import Tuple
from typing import Union
from unittest.mock import Mock

import httpx
import nbformat
import pytest
from _pytest.config import _PluggyPlugin
from nbformat import NotebookNode
from pytest_mock import MockerFixture
from rich import console
from rich.console import Console

from nbpreview import notebook


if sys.version_info >= (3, 8):
    from typing import Literal
    from typing import Protocol
else:  # pragma: no cover
    from typing_extensions import Literal
    from typing_extensions import Protocol


class RichOutput(Protocol):
    """Typing protocol for _rich_output."""

    def __call__(
        self,
        cell: Union[Dict[str, Any], None],
        plain: bool = False,
        no_wrap: bool = False,
        unicode: Optional[bool] = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        hyperlinks: bool = True,
        hide_hyperlink_hints: bool = False,
        images: Optional[bool] = None,
        image_drawing: Optional[Literal["block"]] = None,
    ) -> str:
        """Callable types."""
        ...


def split_string(
    string: str, sub_length: int = 40, copy: bool = False
) -> Tuple[str, ...]:
    """Split a string into subsections less than or equal to new length.

    Args:
        string (str): The long string to split up.
        sub_length (int): The maximum length of the subsections.
            Defaults to 56.
        copy (bool): Copy output to clipboard.

    Returns:
        Tuple[str]: The string split into sections.
    """
    string_length = len(string)
    split = tuple(
        string[begin : begin + sub_length]
        for begin in range(0, string_length, sub_length)
    )
    if copy is True:
        subprocess.run("/usr/bin/pbcopy", text=True, input=str(split))  # noqa: S603
    return split


@pytest.fixture
def parse_link_filepath() -> Callable[[str], Path]:
    """Return a helper function for parsing filepaths from links."""

    def _parse_link_filepath(output: str) -> Path:
        """Extract the filepaths of hyperlinks in outputs."""
        path_re = re.compile(r"(?:file://)(.+)(?:\x1b\\\x1b)")
        link_filepath_match = re.search(path_re, output)
        if link_filepath_match is not None:
            link_filepath = link_filepath_match.group(1)
            return pathlib.Path(link_filepath)
        else:
            raise ValueError("No hyperlink filepath found in output.")

    return _parse_link_filepath


@pytest.fixture
def rich_console() -> Console:
    """Fixture that returns Rich console."""
    con = console.Console(
        file=io.StringIO(),
        width=80,
        height=120,
        color_system="truecolor",
        legacy_windows=False,
        force_terminal=True,
    )
    return con


@pytest.fixture
def rich_output(
    rich_console: Console,
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode],
) -> RichOutput:
    """Fixture returning a function that returns the rendered output.

    Args:
        rich_console (Console): Pytest fixture that returns a rich
            console.
        make_notebook (Callable[[Optional[Dict[str, Any]]], NotebookNode]):
            A fixture that creates a notebook node.

    Returns:
        RichOutput: The output generating function.
    """

    def _rich_output(
        cell: Union[Dict[str, Any], None],
        plain: Optional[bool] = None,
        no_wrap: Optional[bool] = None,
        unicode: Optional[bool] = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        hyperlinks: bool = True,
        hide_hyperlink_hints: bool = False,
        images: Optional[bool] = None,
        image_drawing: Optional[Literal["block"]] = None,
    ) -> str:
        """Render the notebook containing the cell."""
        notebook_node = make_notebook(cell)
        rendered_notebook = notebook.Notebook(
            notebook_node,
            plain=plain,
            unicode=unicode,
            hide_output=hide_output,
            nerd_font=nerd_font,
            files=files,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
            images=images,
            image_drawing=image_drawing,
        )
        rich_console.print(rendered_notebook, no_wrap=no_wrap)
        output: str = rich_console.file.getvalue()  # type: ignore[attr-defined]
        return output

    return _rich_output


@pytest.fixture
def get_tempfile_path() -> Callable[[str], Path]:
    """Fixture for function that returns the tempfile path."""

    def _get_tempfile_path(suffix: str) -> Path:
        """Return tempfile path.

        Args:
            suffix (str): The suffix of the file.

        Returns:
            Path: The tempfile path.
        """
        prefix = tempfile.template
        file_path = pathlib.Path(tempfile.gettempdir()) / pathlib.Path(
            f"{prefix}nbpreview_link_file"
        ).with_suffix(suffix)
        return file_path

    return _get_tempfile_path


@pytest.fixture
def mock_tempfile_file(
    mocker: MockerFixture, get_tempfile_path: Callable[[str], Path]
) -> Generator[Mock, None, None]:
    """Control where tempfile will write to."""
    tempfile_path = get_tempfile_path("")
    tempfile_stem = tempfile_path.stem
    tempfile_base_name = tempfile_stem[3:]
    tempfile_parent = tempfile_path.parent
    mock = mocker.patch("tempfile._get_candidate_names")
    mock.return_value = (
        f"{tempfile_base_name}{file_suffix}" for file_suffix in itertools.count()
    )
    yield mock
    tempfiles = tempfile_parent.glob(f"{tempfile_stem}*")
    for file in tempfiles:
        file.unlink()


@pytest.fixture
def remove_link_ids() -> Callable[[str], str]:
    """Remove link ids from rendered hyperlinks."""

    def _remove_link_ids(render: str) -> str:
        re_link_ids = re.compile(r"id=[\d\.\-]*?;")
        subsituted_render = re_link_ids.sub("id=0;", render)
        return subsituted_render

    return _remove_link_ids


def test_automatic_plain(
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode]
) -> None:
    """It automatically renders in plain format when not a terminal."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "%%bash\necho 'lorep'",
    }
    con = console.Console(
        file=io.StringIO(),
        width=80,
        color_system="truecolor",
        legacy_windows=False,
        force_terminal=False,
    )
    notebook_node = make_notebook(code_cell)
    rendered_notebook = notebook.Notebook(notebook_node)
    con.print(rendered_notebook)
    output = con.file.getvalue()  # type: ignore[attr-defined]
    assert output == (
        "\x1b[49m%%\x1b[0m\x1b[94;49mbash\x1b[0m      "
        "\n\x1b[96;49mecho\x1b[0m\x1b[49m \x1b[0m\x1b[33;49m'lorep'\x1b"
        "[0m\n            \n"
    )


def test_notebook_markdown_cell(rich_output: RichOutput) -> None:
    """It renders a markdown cell."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "### Lorep ipsum\n\n**dolor** _sit_ `amet`",
    }
    output = rich_output(markdown_cell)
    expected_output = (
        "                              "
        "     \x1b[1mLorep ipsum\x1b[0m      "
        "                            \n "
        "                              "
        "                              "
        "                   \n  \x1b[1mdolo"
        "r\x1b[0m \x1b[3msit\x1b[0m \x1b[97;40mamet"
        "\x1b[0m                          "
        "                              "
        "        \n"
    )
    assert output == expected_output


def test_notebook_code_cell(rich_output: RichOutput) -> None:
    """It renders a code cell."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    output = rich_output(code_cell)
    expected_output = (
        "     ╭────────────────────────"
        "──────────────────────────────"
        "───────────────────╮\n\x1b[38;5;24"
        "7m[2]:\x1b[0m │ \x1b[94;49mdef\x1b[0m\x1b["
        "49m \x1b[0m\x1b[92;49mfoo\x1b[0m\x1b[49m(\x1b"
        "[0m\x1b[49mx\x1b[0m\x1b[49m:\x1b[0m\x1b[49m \x1b"
        "[0m\x1b[96;49mfloat\x1b[0m\x1b[49m,\x1b[0m"
        "\x1b[49m \x1b[0m\x1b[49my\x1b[0m\x1b[49m:\x1b[0m"
        "\x1b[49m \x1b[0m\x1b[96;49mfloat\x1b[0m\x1b[4"
        "9m)\x1b[0m\x1b[49m \x1b[0m\x1b[49m-\x1b[0m\x1b[4"
        "9m>\x1b[0m\x1b[49m \x1b[0m\x1b[96;49mfloat"
        "\x1b[0m\x1b[49m:\x1b[0m                "
        "                   │\n     │ \x1b["
        "49m    \x1b[0m\x1b[94;49mreturn\x1b[0m\x1b"
        "[49m \x1b[0m\x1b[49mx\x1b[0m\x1b[49m \x1b[0m\x1b"
        "[49m+\x1b[0m\x1b[49m \x1b[0m\x1b[49my\x1b[0m "
        "                              "
        "                         │\n   "
        "  ╰───────────────────────────"
        "──────────────────────────────"
        "────────────────╯\n"
    )
    assert output == expected_output


def test_notebook_magic_code_cell(rich_output: RichOutput) -> None:
    """It renders a code cell in a language specified by cell magic."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "%%bash\necho 'lorep'",
    }
    expected_output = (
        "     ╭──────────────╮\n\x1b[38;5;2"
        "47m[3]:\x1b[0m │ \x1b[49m%%\x1b[0m\x1b[94;"
        "49mbash\x1b[0m       │\n     │ \x1b[9"
        "6;49mecho\x1b[0m\x1b[49m \x1b[0m\x1b[33;49"
        "m'lorep'\x1b[0m │\n     │         "
        "     │\n     ╰──────────────╯\n"
    )
    output = rich_output(code_cell)
    assert output == expected_output


def test_notebook_raw_cell(rich_output: RichOutput) -> None:
    """It renders a raw cell as plain text."""
    code_cell = {
        "cell_type": "raw",
        "id": "emotional-amount",
        "metadata": {},
        "source": "Lorep ipsum",
    }
    expected_output = " ╭─────────────╮\n │ Lorep ipsum │\n ╰─────────────╯\n"

    output = rich_output(code_cell)
    assert output == expected_output


def test_notebook_non_syntax_magic_code_cell(rich_output: RichOutput) -> None:
    """It uses the default highlighting when magic is not a syntax."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "%%timeit\ndef foo(x: float, y: float) -> float:\n    return x + y",
    }
    expected_output = (
        "     ╭────────────────────────"
        "──────────────────────────────"
        "───────────────────╮\n\x1b[38;5;24"
        "7m[3]:\x1b[0m │ \x1b[49m%%time\x1b[0m\x1b["
        "49mit\x1b[0m                     "
        "                              "
        "             │\n     │ \x1b[94;49m"
        "def\x1b[0m\x1b[49m \x1b[0m\x1b[92;49mfoo\x1b["
        "0m\x1b[49m(\x1b[0m\x1b[49mx\x1b[0m\x1b[49m:\x1b["
        "0m\x1b[49m \x1b[0m\x1b[96;49mfloat\x1b[0m\x1b"
        "[49m,\x1b[0m\x1b[49m \x1b[0m\x1b[49my\x1b[0m\x1b"
        "[49m:\x1b[0m\x1b[49m \x1b[0m\x1b[96;49mflo"
        "at\x1b[0m\x1b[49m)\x1b[0m\x1b[49m \x1b[0m\x1b[49"
        "m-\x1b[0m\x1b[49m>\x1b[0m\x1b[49m \x1b[0m\x1b[96"
        ";49mfloat\x1b[0m\x1b[49m:\x1b[0m       "
        "                            │\n"
        "     │ \x1b[49m    \x1b[0m\x1b[94;49mre"
        "turn\x1b[0m\x1b[49m \x1b[0m\x1b[49mx\x1b[0m\x1b["
        "49m \x1b[0m\x1b[49m+\x1b[0m\x1b[49m \x1b[0m\x1b["
        "49my\x1b[0m                      "
        "                              "
        "    │\n     ╰──────────────────"
        "──────────────────────────────"
        "─────────────────────────╯\n"
    )
    output = rich_output(code_cell)
    assert output == expected_output


def test_notebook_plain_code_cell(rich_output: RichOutput) -> None:
    """It renders a code cell with plain formatting."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    output = rich_output(code_cell, plain=True)
    expected_output = (
        "\x1b[94;49mdef\x1b[0m\x1b[49m \x1b[0m\x1b[92;"
        "49mfoo\x1b[0m\x1b[49m(\x1b[0m\x1b[49mx\x1b[0m"
        "\x1b[49m:\x1b[0m\x1b[49m \x1b[0m\x1b[96;49mfl"
        "oat\x1b[0m\x1b[49m,\x1b[0m\x1b[49m \x1b[0m\x1b[4"
        "9my\x1b[0m\x1b[49m:\x1b[0m\x1b[49m \x1b[0m\x1b[9"
        "6;49mfloat\x1b[0m\x1b[49m)\x1b[0m\x1b[49m "
        "\x1b[0m\x1b[49m-\x1b[0m\x1b[49m>\x1b[0m\x1b[49m "
        "\x1b[0m\x1b[96;49mfloat\x1b[0m\x1b[49m:\x1b[0"
        "m                             "
        "              \n\x1b[49m    \x1b[0m\x1b["
        "94;49mreturn\x1b[0m\x1b[49m \x1b[0m\x1b[49"
        "mx\x1b[0m\x1b[49m \x1b[0m\x1b[49m+\x1b[0m\x1b[49"
        "m \x1b[0m\x1b[49my\x1b[0m              "
        "                              "
        "                    \n"
    )
    assert output == expected_output


def test_render_dataframe(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a DataFrame."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        "<div>\n<style scoped>\n    .dataframe tbod"
                        "y tr th:only-of-type {\n        vertical-"
                        "align: middle;\n    }\n\n    .dataframe tbo"
                        "dy tr th {\n        vertical-align: top;\n"
                        "    }\n\n    .dataframe thead tr th {\n    "
                        "    text-align: left;\n    }\n\n    .datafr"
                        "ame thead tr:last-of-type th {\n        t"
                        "ext-align: right;\n    }\n</style>\n<table "
                        'border="1" class="dataframe">\n  <thead>\n'
                        "    <tr>\n      <th></th>\n      <th></th>"
                        "\n      <th>lorep</th>\n      <th colspan="
                        '"2" halign="left">hey</th>\n      <th>bye'
                        "</th>\n    </tr>\n    <tr>\n      <th></th>"
                        "\n      <th></th>\n      <th>ipsum</th>\n  "
                        "    <th>hi</th>\n      <th>very_long_word"
                        "</th>\n      <th>hi</th>\n    </tr>\n    <t"
                        "r>\n      <th>first</th>\n      <th>second"
                        "</th>\n      <th>third</th>\n      <th></t"
                        "h>\n      <th></th>\n      <th></th>\n    <"
                        "/tr>\n  </thead>\n  <tbody>\n    <tr>\n     "
                        ' <th rowspan="3" valign="top">bar</th>\n '
                        '     <th rowspan="2" valign="top">one</t'
                        "h>\n      <th>1</th>\n      <td>1</td>\n   "
                        "   <td>2</td>\n      <td>4</td>\n    </tr>"
                        "\n    <tr>\n      <th>10</th>\n      <td>3<"
                        "/td>\n      <td>4</td>\n      <td>-1</td>\n"
                        "    </tr>\n    <tr>\n      <th>three</th>\n"
                        "      <th>3</th>\n      <td>3</td>\n      "
                        "<td>4</td>\n      <td>-1</td>\n    </tr>\n "
                        "   <tr>\n      <th>foo</th>\n      <th>one"
                        "</th>\n      <th>1</th>\n      <td>3</td>\n"
                        "      <td>4</td>\n      <td>-1</td>\n    <"
                        "/tr>\n  </tbody>\n</table>\n</div>"
                    ),
                    "text/plain": (
                        "lorep              hey                by"
                        "e\nipsum               hi very_long_word "
                        " hi\nfirst second third                  "
                        "     \nbar   one    1       1            "
                        "  2   4\n             10      3          "
                        "    4  -1\n      three  3       3        "
                        "      4  -1\nfoo   one    1       3      "
                        "        4  -1"
                    ),
                },
                "execution_count": 2,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        "\x1b]8;id=1627258210.84976-39532;"
        f"file://{tempfile_path}2.html\x1b\\\x1b[94"
        "m🌐 Click to view HTML\x1b[0m\x1b]8;;\x1b\\        "
        "                                        "
        "     \n                                  "
        "                                        "
        "      \n\x1b[38;5;247m[2]:\x1b[0m   \x1b[1m     \x1b["
        "0m   \x1b[1m      \x1b[0m   \x1b[1mlorep\x1b[0m     "
        "   \x1b[1m           hey\x1b[0m   \x1b[1mbye\x1b[0m "
        "                      \n       \x1b[1m     \x1b"
        "[0m   \x1b[1m      \x1b[0m   \x1b[1mipsum\x1b[0m   \x1b"
        "[1mhi\x1b[0m   \x1b[1mvery_long_word\x1b[0m   \x1b[1"
        "m hi\x1b[0m                       \n       \x1b"
        "[1mfirst\x1b[0m   \x1b[1msecond\x1b[0m   \x1b[1mthir"
        "d\x1b[0m   \x1b[1m  \x1b[0m   \x1b[1m              \x1b"
        "[0m   \x1b[1m   \x1b[0m                       "
        "\n      ─────────────────────────────────"
        "───────────────────                     "
        " \n       \x1b[1m  bar\x1b[0m   \x1b[1m   one\x1b[0m "
        "  \x1b[1m    1\x1b[0m    1                2   "
        "  4                       \n             "
        "           \x1b[1m   10\x1b[0m    3           "
        "     4    -1                       \n    "
        "           \x1b[1m three\x1b[0m   \x1b[1m    3\x1b[0"
        "m    3                4    -1           "
        "            \n       \x1b[1m  foo\x1b[0m   \x1b[1m"
        "   one\x1b[0m   \x1b[1m    1\x1b[0m    3         "
        "       4    -1                       \n"
    )
    output = rich_output(code_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_plain_dataframe(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a DataFrame in a plain style."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        "<div>\n<style scoped>\n    .dataframe tbod"
                        "y tr th:only-of-type {\n        vertical-"
                        "align: middle;\n    }\n\n    .dataframe tbo"
                        "dy tr th {\n        vertical-align: top;\n"
                        "    }\n\n    .dataframe thead tr th {\n    "
                        "    text-align: left;\n    }\n\n    .datafr"
                        "ame thead tr:last-of-type th {\n        t"
                        "ext-align: right;\n    }\n</style>\n<table "
                        'border="1" class="dataframe">\n  <thead>\n'
                        "    <tr>\n      <th></th>\n      <th></th>"
                        "\n      <th>lorep</th>\n      <th colspan="
                        '"2" halign="left">hey</th>\n      <th>bye'
                        "</th>\n    </tr>\n    <tr>\n      <th></th>"
                        "\n      <th></th>\n      <th>ipsum</th>\n  "
                        "    <th>hi</th>\n      <th>very_long_word"
                        "</th>\n      <th>hi</th>\n    </tr>\n    <t"
                        "r>\n      <th>first</th>\n      <th>second"
                        "</th>\n      <th>third</th>\n      <th></t"
                        "h>\n      <th></th>\n      <th></th>\n    <"
                        "/tr>\n  </thead>\n  <tbody>\n    <tr>\n     "
                        ' <th rowspan="3" valign="top">bar</th>\n '
                        '     <th rowspan="2" valign="top">one</t'
                        "h>\n      <th>1</th>\n      <td>1</td>\n   "
                        "   <td>2</td>\n      <td>4</td>\n    </tr>"
                        "\n    <tr>\n      <th>10</th>\n      <td>3<"
                        "/td>\n      <td>4</td>\n      <td>-1</td>\n"
                        "    </tr>\n    <tr>\n      <th>three</th>\n"
                        "      <th>3</th>\n      <td>3</td>\n      "
                        "<td>4</td>\n      <td>-1</td>\n    </tr>\n "
                        "   <tr>\n      <th>foo</th>\n      <th>one"
                        "</th>\n      <th>1</th>\n      <td>3</td>\n"
                        "      <td>4</td>\n      <td>-1</td>\n    <"
                        "/tr>\n  </tbody>\n</table>\n</div>"
                    ),
                    "text/plain": (
                        "lorep              hey                by"
                        "e\nipsum               hi very_long_word "
                        " hi\nfirst second third                  "
                        "     \nbar   one    1       1            "
                        "  2   4\n             10      3          "
                        "    4  -1\n      three  3       3        "
                        "      4  -1\nfoo   one    1       3      "
                        "        4  -1"
                    ),
                },
                "execution_count": 2,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "                                        "
        "                                        "
        "\n                                       "
        "                                        "
        " \n\x1b]8;id=1627258290.675266-113809;file:/"
        f"/{tempfile_path}1.html\x1b\\"
        "\x1b[94m🌐 Click to view HTML\x1b[0m\x1b]8;;\x1b\\    "
        "                                        "
        "               \n                        "
        "                                        "
        "                \nlorep              hey "
        "               bye                      "
        "                 \nipsum               hi"
        " very_long_word  hi                     "
        "                  \nfirst second third   "
        "                                        "
        "                   \nbar   one    1      "
        " 1              2   4                   "
        "                    \n             10    "
        "  3              4  -1                  "
        "                     \n      three  3    "
        "   3              4  -1                 "
        "                      \nfoo   one    1   "
        "    3              4  -1                "
        "                       \n"
    )
    output = rich_output(code_cell, plain=True)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_stderr_stream(rich_output: RichOutput) -> None:
    """It renders the stderr stream."""
    stderr_cell = {
        "cell_type": "code",
        "execution_count": 5,
        "id": "impressed-canadian",
        "metadata": {},
        "outputs": [
            {
                "name": "stderr",
                "output_type": "stream",
                "text": "<ipython-input-5-bc08279b5148>:2: UserWarning: Lorep\n"
                ' warnings.warn("Lorep")\n',
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[5]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b[38;5;237;48;5"
        ";174m<ipython-input-5-bc08279b5148>:2: U"
        "serWarning: Lorep                      \x1b"
        "[0m\n      \x1b[38;5;237;48;5;174m warnings."
        'warn("Lorep")                           '
        "                        \x1b[0m\n      \x1b[38;"
        "5;237;48;5;174m                         "
        "                                        "
        "         \x1b[0m\n"
    )
    output = rich_output(stderr_cell)
    assert output == expected_output


def test_render_stream_stdout(rich_output: RichOutput) -> None:
    """It renders stdout."""
    stdout_cell = {
        "cell_type": "code",
        "execution_count": 6,
        "id": "underlying-merit",
        "metadata": {},
        "outputs": [{"name": "stdout", "output_type": "stream", "text": "Lorep\n"}],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[6]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      Lorep          "
        "                                        "
        "                   \n                    "
        "                                        "
        "                    \n"
    )
    output = rich_output(stdout_cell)
    assert output == expected_output


def test_render_error_traceback(rich_output: RichOutput) -> None:
    """It renders the traceback from an error."""
    traceback_cell = {
        "cell_type": "code",
        "execution_count": 7,
        "id": "brave-sheep",
        "metadata": {},
        "outputs": [
            {
                "ename": "ZeroDivisionError",
                "evalue": "division by zero",
                "output_type": "error",
                "traceback": [
                    "\x1b[1;31m----------------------------------------"
                    "-----------------------------------\x1b[0m",
                    "\x1b[1;31mZeroDivisionError\x1b[0m                "
                    "         Traceback (most recent call last)",
                    "\x1b[1;32m<ipython-input-7-9e1622b385b6>\x1b[0m in"
                    " \x1b[0;36m<module>\x1b[1;34m\x1b[0m\n\x1b[1;32m--"
                    "--> 1\x1b[1;33m \x1b[1;36m1\x1b[0m\x1b[1;33m/\x1b["
                    "0m\x1b[1;36m0\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m"
                    "\x1b[0m\x1b[0m\n\x1b[0m",
                    "\x1b[1;31mZeroDivisionError\x1b[0m: division by zero",
                ],
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[7]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b[49m\x1b[1;31m---"
        "----------------------------------------"
        "------------------------…\x1b[0m\n      \x1b[49"
        "m\x1b[1;31mZeroDivisionError\x1b[0m           "
        "              Traceback (most recent…\x1b[0"
        "m\n      \x1b[49m\x1b[1;32m<ipython-input-7-9e1"
        "622b385b6>\x1b[0m in \x1b[0;36m<module>\x1b[1;34m"
        "\x1b[0m\x1b[0m        \n      \x1b[49m\x1b[1;32m---->"
        " 1\x1b[1;33m \x1b[1;36m1\x1b[0m\x1b[1;33m/\x1b[0m\x1b[1;36"
        "m0\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\x1b[0m   \n"
        "      \x1b[49m\x1b[0m\x1b[0m                     "
        "                                        "
        "          \n      \x1b[49m\x1b[1;31mZeroDivisio"
        "nError\x1b[0m: division by zero\x1b[0m        "
        "                      \n"
    )
    output = rich_output(traceback_cell)
    assert output == expected_output


def test_render_result(rich_output: RichOutput) -> None:
    """It renders a result."""
    output_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "intense-middle",
        "metadata": {},
        "outputs": [
            {
                "data": {"text/plain": "3"},
                "execution_count": 2,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        "3                                       "
        "                                  \n"
    )
    output = rich_output(output_cell)
    assert output == expected_output


def test_render_unknown_data_format(rich_output: RichOutput) -> None:
    """It passes on rendering an unknown data format."""
    output_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "intense-middle",
        "metadata": {},
        "outputs": [
            {
                "data": {"unknown_format": "3"},
                "execution_count": 2,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n"
    )
    output = rich_output(output_cell)
    assert output == expected_output


def test_render_error_no_traceback(rich_output: RichOutput) -> None:
    """It skips rendering an error with no traceback."""
    traceback_cell = {
        "cell_type": "code",
        "execution_count": 7,
        "id": "brave-sheep",
        "metadata": {},
        "outputs": [
            {
                "ename": "ZeroDivisionError",
                "evalue": "division by zero",
                "output_type": "error",
                "traceback": [],
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[7]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n                     "
        "                                        "
        "                   \n"
    )
    output = rich_output(traceback_cell)
    assert output == expected_output


def test_render_markdown_output(rich_output: RichOutput) -> None:
    """It renders a markdown output."""
    markdown_output_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "declared-stevens",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/markdown": "**Lorep** _ipsum_\n",
                    "text/plain": "<IPython.core.display.Markdown object>",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "%%markdown\n**Lorep** _ipsum_",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │ \x1b[49m%%\x1b[0m\x1b[94;4"
        "9mmarkdown\x1b[0m                          "
        "                                    │\n  "
        "   │ \x1b[49m**Lorep**\x1b[0m\x1b[49m \x1b[0m\x1b[49m_i"
        "psum_\x1b[0m                               "
        "                        │\n     │        "
        "                                        "
        "                         │\n     ╰───────"
        "────────────────────────────────────────"
        "──────────────────────────╯\n            "
        "                                        "
        "                            \n      \x1b[1mL"
        "orep\x1b[0m \x1b[3mipsum\x1b[0m                  "
        "                                        "
        "     \n"
    )
    output = rich_output(markdown_output_cell)
    assert output == expected_output


def test_render_unknown_display_data(rich_output: RichOutput) -> None:
    """It skips rendering an unknown data display type."""
    unknown_display_data_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "declared-stevens",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "unknown_data_type": "**Lorep** _ipsum_\n",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n"
    )
    output = rich_output(unknown_display_data_cell)
    assert output == expected_output


def test_render_json_output(rich_output: RichOutput) -> None:
    """It renders a JSON output."""
    json_output_cell = {
        "cell_type": "code",
        "execution_count": 1,
        "id": "behind-authentication",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "application/json": {"one": 1, "three": {"a": "b"}, "two": 2},
                    "text/plain": "<IPython.core.display.JSON object>",
                },
                "execution_count": 1,
                "metadata": {"application/json": {"expanded": False, "root": "root"}},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[1]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[1]:\x1b[0m  "
        '\x1b[49m{\x1b[0m\x1b[94;49m"one"\x1b[0m\x1b[49m:\x1b[0m\x1b[4'
        "9m \x1b[0m\x1b[94;49m1\x1b[0m\x1b[49m,\x1b[0m\x1b[49m \x1b[0m"
        '\x1b[94;49m"three"\x1b[0m\x1b[49m:\x1b[0m\x1b[49m \x1b[0m\x1b'
        '[49m{\x1b[0m\x1b[94;49m"a"\x1b[0m\x1b[49m:\x1b[0m\x1b[49m '
        '\x1b[0m\x1b[33;49m"b"\x1b[0m\x1b[49m},\x1b[0m\x1b[49m \x1b[0m'
        '\x1b[94;49m"two"\x1b[0m\x1b[49m:\x1b[0m\x1b[49m \x1b[0m\x1b[9'
        "4;49m2\x1b[0m\x1b[49m}\x1b[0m                    "
        "             \n"
    )
    output = rich_output(json_output_cell)
    assert output == expected_output


def test_render_latex_output(rich_output: RichOutput) -> None:
    """It renders LaTeX output."""
    latex_output_cell = {
        "cell_type": "code",
        "execution_count": 15,
        "id": "sapphire-harmony",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/latex": "$$\n\\alpha \\sim \\text{Normal}"
                    " \\\\\n\\beta \\sim \\text{Normal} \\\\\n\\epsilon"
                    " \\sim \\text{Half-Cauchy} \\\\\n\\mu = \\alpha +"
                    " X\\beta \\\\\ny \\sim \\text{Normal}(\\mu, \\epsilon)\n$$\n",
                    "text/plain": "<IPython.core.display.Latex object>",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "      ╭─────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[15]:\x1b[0m │                 "
        "                                        "
        "               │\n      ╰────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n                     "
        "                                        "
        "                   \n                    "
        "                                        "
        "                    \n           α∼Normal"
        "                                        "
        "                     \n           β∼Norma"
        "l                                       "
        "                      \n           ϵ∼Half"
        "-Cauchy                                 "
        "                       \n           μ = α"
        " + Xβ                                   "
        "                        \n           y ∼N"
        "ormal(μ, ϵ)                             "
        "                         \n              "
        "                                        "
        "                          \n             "
        "                                        "
        "                           \n"
    )
    output = rich_output(latex_output_cell)
    assert expected_output == output


def test_render_latex_output_no_unicode(rich_output: RichOutput) -> None:
    """It does not render LaTeX output if unicode is False."""
    latex_output_cell = {
        "cell_type": "code",
        "execution_count": 15,
        "id": "sapphire-harmony",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/latex": "$$\n\\alpha \\sim \\text{Normal}"
                    " \\\\\n\\beta \\sim \\text{Normal} \\\\\n\\epsilon"
                    " \\sim \\text{Half-Cauchy} \\\\\n\\mu = \\alpha +"
                    " X\\beta \\\\\ny \\sim \\text{Normal}(\\mu, \\epsilon)\n$$\n",
                    "text/plain": "<IPython.core.display.Latex object>",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "      ╭─────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[15]:\x1b[0m │                 "
        "                                        "
        "               │\n      ╰────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n       <IPython.core."
        "display.Latex object>                   "
        "                   \n"
    )
    output = rich_output(latex_output_cell, unicode=False)
    assert expected_output == output


def test_render_text_display_data(rich_output: RichOutput) -> None:
    """It renders text display data."""
    text_display_data_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "declared-stevens",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/plain": "Lorep ipsum",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      Lorep ipsum    "
        "                                        "
        "                   \n"
    )
    output = rich_output(text_display_data_cell)
    assert output == expected_output


def test_pdf_emoji_output(rich_output: RichOutput) -> None:
    """It renders an emoji for PDF output."""
    pdf_output_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "declared-stevens",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "application/pdf": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      📄              "
        "                                        "
        "                  \n"
    )
    output = rich_output(pdf_output_cell, unicode=True)
    assert output == expected_output


def test_pdf_nerd_output(rich_output: RichOutput) -> None:
    """It renders a nerd font icon for PDF output."""
    pdf_output_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "declared-stevens",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "application/pdf": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \uf1c1              "
        "                                        "
        "                   \n"
    )
    output = rich_output(pdf_output_cell, nerd_font=True)
    assert output == expected_output


def test_pdf_no_unicode_no_nerd(rich_output: RichOutput) -> None:
    """It does not render a PDF icon if no nerd font or unicode."""
    pdf_output_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "declared-stevens",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "application/pdf": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n"
    )
    output = rich_output(pdf_output_cell, nerd_font=False, unicode=False)
    assert output == expected_output


def test_vega_output(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a hyperlink to a rendered Vega plot."""
    vega_output_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vega.v5+json": {
                        "$schema": "https://vega.github.io/schema/vega/v5.0.json",
                        "axes": [
                            {"orient": "bottom", "scale": "xscale"},
                            {"orient": "left", "scale": "yscale"},
                        ],
                        "data": [
                            {
                                "name": "table",
                                "values": [
                                    {"amount": 28, "category": "A"},
                                    {"amount": 55, "category": "B"},
                                    {"amount": 43, "category": "C"},
                                    {"amount": 91, "category": "D"},
                                    {"amount": 81, "category": "E"},
                                    {"amount": 53, "category": "F"},
                                    {"amount": 19, "category": "G"},
                                    {"amount": 87, "category": "H"},
                                ],
                            }
                        ],
                        "height": 200,
                        "marks": [
                            {
                                "encode": {
                                    "enter": {
                                        "width": {"band": 1, "scale": "xscale"},
                                        "x": {"field": "category", "scale": "xscale"},
                                        "y": {"field": "amount", "scale": "yscale"},
                                        "y2": {"scale": "yscale", "value": 0},
                                    },
                                    "hover": {"fill": {"value": "red"}},
                                    "update": {"fill": {"value": "steelblue"}},
                                },
                                "from": {"data": "table"},
                                "type": "rect",
                            },
                            {
                                "encode": {
                                    "enter": {
                                        "align": {"value": "center"},
                                        "baseline": {"value": "bottom"},
                                        "fill": {"value": "#333"},
                                    },
                                    "update": {
                                        "fillOpacity": [
                                            {"test": "datum === tooltip", "value": 0},
                                            {"value": 1},
                                        ],
                                        "text": {"signal": "tooltip.amount"},
                                        "x": {
                                            "band": 0.5,
                                            "scale": "xscale",
                                            "signal": "tooltip.category",
                                        },
                                        "y": {
                                            "offset": -2,
                                            "scale": "yscale",
                                            "signal": "tooltip.amount",
                                        },
                                    },
                                },
                                "type": "text",
                            },
                        ],
                        "padding": 5,
                        "scales": [
                            {
                                "domain": {"data": "table", "field": "category"},
                                "name": "xscale",
                                "padding": 0.05,
                                "range": "width",
                                "round": True,
                                "type": "band",
                            },
                            {
                                "domain": {"data": "table", "field": "amount"},
                                "name": "yscale",
                                "nice": True,
                                "range": "height",
                            },
                        ],
                        "signals": [
                            {
                                "name": "tooltip",
                                "on": [
                                    {"events": "rect:mouseover", "update": "datum"},
                                    {"events": "rect:mouseout", "update": "{}"},
                                ],
                                "value": {},
                            }
                        ],
                        "width": 400,
                    },
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[3]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=16281369"
        f"58.012196-350876;file://{tempfile_path}2.html\x1b\\\x1b[94m\uf080"
        " Click to v"
        "iew Vega chart\x1b[0m\x1b]8;;\x1b\\               "
        "                                 \n"
    )
    output = rich_output(
        vega_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a hyperlink to a rendered Vega plot."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=304082;f"
        f"ile://{tempfile_path}2.h"
        "tml\x1b\\\x1b[94m\uf080 Click to view Vega chart\x1b[0m"
        "\x1b]8;;\x1b\\                                 "
        "               \n                        "
        "                                        "
        "                \n      \x1b[38;2;187;134;25"
        "2mImage                                 "
        "                                    \x1b[0m"
        "\n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output_no_hints(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a hyperlink to a Vega plot without hints."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=90200;fi"
        f"le://{tempfile_path}2.ht"
        "ml\x1b\\\x1b[94m\uf080 \x1b[0m\x1b]8;;\x1b\\                  "
        "                                        "
        "              \n                         "
        "                                        "
        "               \n      \x1b[38;2;187;134;252"
        "mImage                                  "
        "                                   \x1b[0m\n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=True,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output_no_nerd_font(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a hyperlink to a Vega plot without nerd fonts."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=2129;fil"
        f"e://{tempfile_path}2.htm"
        "l\x1b\\\x1b[94m📊 Click to view Vega chart\x1b[0m\x1b]"
        "8;;\x1b\\                                   "
        "            \n                           "
        "                                        "
        "             \n      \x1b[38;2;187;134;252mI"
        "mage                                    "
        "                                 \x1b[0m\n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output_no_nerd_font_no_unicode(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a hyperlink to plot without nerd fonts or unicode."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=16281372"
        f"55.127551-234092;file://{tempfile_path}2.html\x1b\\\x1b[94mClick to vie"
        "w Vega chart\x1b[0m\x1b]8;;\x1b\\                 "
        "                                 \n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output_no_files(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a message representing a Vega plot."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {},
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      📊 Vega chart   "
        "                                        "
        "                  \n                     "
        "                                        "
        "                   \n      \x1b[38;2;187;134"
        ";252mImage                              "
        "                                       \x1b"
        "[0m\n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=False,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=True,
    )
    tempfile_path = get_tempfile_path("")
    tempfile_directory = tempfile_path.parent
    for file in tempfile_directory.glob(f"{tempfile_path.stem}*.html"):
        assert not file.exists()
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_write_vega_output(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    parse_link_filepath: Callable[[str], Path],
) -> None:
    """It writes the Vega plot to a file."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_contents = (
        '<html>\n<head>\n    <script src="https://c'
        'dn.jsdelivr.net/npm/vega@5"></script>\n  '
        '  <script src="https://cdn.jsdelivr.net/'
        'npm/vega-lite@5"></script>\n    <script s'
        'rc="https://cdn.jsdelivr.net/npm/vega-em'
        'bed@6"></script>\n    <script src="https:'
        "//cdn.jsdelivr.net/gh/koaning/justcharts"
        '/justcharts.js"></script>\n    <title>Veg'
        "a chart</title>\n</head>\n<body>\n    <vega"
        'chart style="width: 100%">\n        {"$sc'
        'hema": "https://vega.github.io/schema/ve'
        'ga-lite/v4.json", "data": {"values": [{"'
        'a": "A", "b": 28}, {"a": "B", "b": 55}, '
        '{"a": "C", "b": 43}, {"a": "D", "b": 91}'
        ', {"a": "E", "b": 81}, {"a": "F", "b": 5'
        '3}, {"a": "G", "b": 19}, {"a": "H", "b":'
        ' 87}, {"a": "I", "b": 52}]}, "descriptio'
        'n": "A simple bar chart with embedded da'
        'ta.", "encoding": {"x": {"field": "a", "'
        'type": "ordinal"}, "y": {"field": "b", "'
        'type": "quantitative"}}, "mark": "bar"}\n'
        "    </vegachart>\n</body>\n<html></html>\n<"
        "/html>"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    tempfile_path = parse_link_filepath(output)
    file_contents = tempfile_path.read_text()
    assert file_contents == expected_contents


def test_vega_no_icon_no_message(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders subject text when no icons or messages are used."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=16281373"
        f"35.10625-550844;file://{tempfile_path}2.html\x1b\\\x1b[94mVega"
        " chart\x1b[0"
        "m\x1b]8;;\x1b\\                                "
        "                                \n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=True,
        unicode=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vega_no_hyperlink(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders the file path when no hyperlinks are allowed."""
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vegalite.v4+json": {
                        "$schema": "https://vega.github.io/schema/vega-lite/v4.json",
                        "data": {
                            "values": [
                                {"a": "A", "b": 28},
                                {"a": "B", "b": 55},
                                {"a": "C", "b": 43},
                                {"a": "D", "b": 91},
                                {"a": "E", "b": 81},
                                {"a": "F", "b": 53},
                                {"a": "G", "b": 19},
                                {"a": "H", "b": 87},
                                {"a": "I", "b": 52},
                            ]
                        },
                        "description": "A simple bar chart with embedded data.",
                        "encoding": {
                            "x": {"field": "a", "type": "ordinal"},
                            "y": {"field": "b", "type": "quantitative"},
                        },
                        "mark": "bar",
                    },
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = f"📊 {get_tempfile_path('')}2.html"
    line_width = 80 - 6
    wrapped_file_path = "\n".join(
        [f"{'':>6}{tempfile_path[:line_width - 1]:<73}"]
        + [
            f"{'':>6}{tempfile_path[i: i + line_width]:<74}"
            for i in range(line_width - 1, len(tempfile_path), line_width)
        ]
    )
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        f"                  \n{wrapped_file_path}\n"
        f"{'':<80}\n"
        "      \x1b[38;2;187;13"
        "4;252mImage                             "
        "                                        "
        "\x1b[0m\n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=False,
        hide_hyperlink_hints=True,
        unicode=True,
    )
    assert output.rstrip() == expected_output.rstrip()


def test_vega_url(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    mocker: MockerFixture,
    parse_link_filepath: Callable[[str], Path],
) -> None:
    """It pulls the JSON data from the URL and writes to file."""
    mock = mocker.patch("httpx.get")
    mock.return_value.text = json.dumps(
        {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "description": "A simple bar chart with embedded data.",
            "data": {
                "values": [
                    {"a": "A", "b": 28},
                    {"a": "B", "b": 55},
                    {"a": "C", "b": 43},
                    {"a": "D", "b": 91},
                    {"a": "E", "b": 81},
                    {"a": "F", "b": 53},
                    {"a": "G", "b": 19},
                    {"a": "H", "b": 87},
                    {"a": "I", "b": 52},
                ]
            },
            "mark": "bar",
            "encoding": {
                "x": {"field": "a", "type": "nominal", "axis": {"labelAngle": 0}},
                "y": {"field": "b", "type": "quantitative"},
            },
        }
    )
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vega.v5+json": "https://raw.githubusercontent.com/"
                    "vega/vega/master/docs/examples/bar-chart.vg.json",
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_contents = (
        '<html>\n<head>\n    <script src="https://c'
        'dn.jsdelivr.net/npm/vega@5"></script>\n  '
        '  <script src="https://cdn.jsdelivr.net/'
        'npm/vega-lite@5"></script>\n    <script s'
        'rc="https://cdn.jsdelivr.net/npm/vega-em'
        'bed@6"></script>\n    <script src="https:'
        "//cdn.jsdelivr.net/gh/koaning/justcharts"
        '/justcharts.js"></script>\n    <title>Veg'
        "a chart</title>\n</head>\n<body>\n    <vega"
        'chart style="width: 100%">\n        {"$sc'
        'hema": "https://vega.github.io/schema/ve'
        'ga-lite/v5.json", "description": "A simp'
        'le bar chart with embedded data.", "data'
        '": {"values": [{"a": "A", "b": 28}, {"a"'
        ': "B", "b": 55}, {"a": "C", "b": 43}, {"'
        'a": "D", "b": 91}, {"a": "E", "b": 81}, '
        '{"a": "F", "b": 53}, {"a": "G", "b": 19}'
        ', {"a": "H", "b": 87}, {"a": "I", "b": 5'
        '2}]}, "mark": "bar", "encoding": {"x": {'
        '"field": "a", "type": "nominal", "axis":'
        ' {"labelAngle": 0}}, "y": {"field": "b",'
        ' "type": "quantitative"}}}\n    </vegacha'
        "rt>\n</body>\n<html></html>\n</html>"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    tempfile_path = parse_link_filepath(output)
    file_contents = tempfile_path.read_text()
    mock.assert_called_with(
        url="https://raw.githubusercontent.com"
        "/vega/vega/master/docs/examples/bar-chart.vg.json"
    )
    assert file_contents == expected_contents


def test_vega_url_request_error(
    rich_output: RichOutput,
    mocker: MockerFixture,
) -> None:
    """It fallsback to rendering a message if there is a RequestError."""
    mocker.patch("httpx.get", side_effect=httpx.RequestError("Mock"))
    vegalite_output_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vega.v5+json": "https://raw.githubusercontent.com/"
                    "vega/vega/master/docs/examples/bar-chart.vg.json",
                    "image/png": "",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[3]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      Vega chart     "
        "                                        "
        "                   \n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    assert output == expected_output


def test_render_html(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders HTML output."""
    html_cell = {
        "cell_type": "code",
        "execution_count": 7,
        "id": "43e39858-6416-4dc8-9d7e-7905127e7452",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": " <head>\n"
                    "        <title>Example</title>\n    </head>\n    "
                    "<body>\n        <p><strong>Lorep</strong> "
                    "<em>Ipsum</em> </p>\n    </body>\n",
                    "text/plain": "<IPython.core.display.HTML object>",
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[7]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=16281375"
        f"06.111208-917276;file://{tempfile_path}2.html\x1b\\\x1b[94m🌐 Click to v"
        "iew HTML\x1b[0m\x1b]8;;\x1b\\                     "
        "                                \n       "
        "                                        "
        "                                 \n      "
        "\x1b[1mLorep\x1b[0m \x1b[3mIpsum\x1b[0m             "
        "                                        "
        "          \n"
    )
    output = rich_output(html_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_unknown_data_type(rich_output: RichOutput) -> None:
    """It skips rendering an unknown output type."""
    unknown_data_type = {
        "cell_type": "code",
        "execution_count": 11,
        "id": "intense-middle",
        "metadata": {},
        "outputs": [
            {
                "data": {"unkown_data_type": "3"},
                "execution_count": 2,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    output = rich_output(unknown_data_type)
    expected_output = (
        "      ╭─────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[11]:\x1b[0m │                 "
        "                                        "
        "               │\n      ╰────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n"
    )
    assert output == expected_output


def test_render_image_link(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
    disable_capture: ContextManager[_PluggyPlugin],
) -> None:
    """It renders a link to an image."""
    image_cell = {
        "cell_type": "code",
        "execution_count": 1,
        "id": "43e39858-6416-4dc8-9d7e-7905127e7452",
        "metadata": {},
        "outputs": [
            {
                "data": {"text/plain": "<AxesSubplot:>"},
                "execution_count": 1,
                "metadata": {},
                "output_type": "execute_result",
            },
            {
                "data": {
                    "image/png": "iVBORw0KGgoAAAANSUhEUgAAAX4AAAEDCAYAAAAyZm"
                    "/jAAAAOXRFWHRTb2Z0"
                    "d2FyZQBNYXRwbG90bGliIHZlcnNpb24zLjQuMiwgaHR0cHM6Ly9tYXRwbG90"
                    "bGliLm9yZy8rg+JYAAAACXBIWXMAAAsTAAALEwEAmpwYAAATJElEQVR4nO3d"
                    "f5DcdX3H8edl90IoiTgoN+Q8PEVSRmtFS4EO2hktMsUqNs7YiFW0paYg/gBl"
                    "eGuniFOtxX7iD8RftS1Oa7Hi+LtmtAgIZRwoTtMiaEXG0SQcARck/AgkcLe3"
                    "/WMPejn3bveyn9vbvc/zMZO52e998sn7dZm88t3vfm9vqNFoIEkqx6rlHkCS"
                    "1FsWvyQVxuKXpMJY/JJUGItfkgozKMXfGLRf9Xq9sWPHjka9Xl/2WcxrZjMX"
                    "m7mlQSn+gTM9Pb3fx5WutLxg5lKsxMwWvyQVxuKXpMJY/JJUGItfkgpj8UtS"
                    "YaqdLIqINwLvAQ4HbgL+LKV0x5w1pwAfA9YD3wPOTCndk3dcSVK32p7xR8Rx"
                    "wBbgD4GnAjuAS+asWQN8AXgrcARwL/D+zLNKkjLo5Iz/mcBHU0o/AoiIzwGf"
                    "nrPmRGBnSum7M2suBb6ea8h6vT5w99BOTU3t93GlKy0vmLkUg5x5eHi45fG2"
                    "xZ9S+vKcQy8Erp9zbD3wi1mP76J55p/FxMRErq16rlarLfcIPVVaXjBzKQYx"
                    "8/j4eMvjHV3jf1xE/BbwFuD4OZ9aA9RnPZ4CVi9m74WMjY0N5Bl/rVZjZGSE"
                    "anVRX+aBVFpeMLOZB1fHKSLi6cBXgT9JKd0959OPztmrQrP8s6hUKlQqlVzb"
                    "9VS1Wp336dZKVFpeMHMpVlLmjm7njIhDga3AhSmla1osuQs4ctbj9cDc/xwk"
                    "SX2g7Rl/RAwDXwH+JaV0+TzLbgKOiIjTgCtp3t1zZbYpJUnZdHKp5xXAycDv"
                    "RMR7Zx3/K+APUkovSSntjYjTgUuBz9F88fdPs08rSQW5/fbb+drXvsbDDz/M"
                    "s571LF7zmtewZs2arvcdajTmfcvmfjIQQ842OTnJrl27GB0dXTHXBRdSWl4w"
                    "80rM/LPvT7H1/fvY99D/V06jMc1jjz7G6oNWMzTU/ZsdrFk3xCves4ajTlj4"
                    "vPvBBx/kQx/6EGeddRYjIyNcdtllbNiwgZNPPnkxf9xQq4Mr4yVqScrg6kv2"
                    "ccvWyRafqQLTM7+6d/CThjjq8wvX78EHH8y5557LU57yFACOOeYY7rknz5sh"
                    "WPySNOOl561h30Ms+Rn/S887qO264eFhbrvtNm688UYefPBBpqamOPbYY7v+"
                    "88Hil6QnHHVClbd/c+1+x5qXt+5ndPTJPb28tWPHDq677jo2b97M4YcfzvXX"
                    "X8/dd+e5WdJ355SkPvTII48wPDzMunXreOihh7j99tuzfSOrZ/yS1IeOOeYY"
                    "br31Vi6++GIOPfRQjj76aB544IEse1v8ktSHVq1axaZNm9i0aVP+vbPvKEnq"
                    "axa/JBXG4pekwlj8klQYi1+SCmPxS1JhLH5JKozFL0mFsfglqQ/dd999XHjh"
                    "hUuyt8UvSYWx+CWpML5XjyT1qUajwTe+8Q1uvvlm1q1bx6ZNmxgbG+t6X4tf"
                    "kmZ8/977eP8tP+ahqaknjjWmGzz62KMc9OOfM7Sq5U8yXJR11Srved6zOeGp"
                    "h7VdOzk5ydjYGKeddho33HADV1xxBeeffz5DQ93NYfFL0oxLfvxTtt453w87"
                    "2ZPtz3nS8DCf/90T2q5bvXo1xx13HAAnnXQSV111Fffdd98TP47xQFn8kjTj"
                    "vGcfzUOTk63P+FcflO2M/7xnH73o37dq1SoOOeQQ9uzZY/FLUi4nPPUwvvl7"
                    "L9zvWPNHL+5idHS0pz96ca7p6Wn27NnD2rVr2y9uw7t6JKlPPfbYY2zbto3p"
                    "6WluuOEGDj30UA47rP1rA+14xi9JfWrt2rXccccdbN26lXXr1vHa17626xd2"
                    "weKXpL502GGHcdFFFwGwcePGrHt7qUeSCmPxS1JhLH5JKozFL0mFsfglqTAd"
                    "3dUTEWuB04HNwDkppW0t1rwReB+wDtgKnJVS2ptxVklSBm3P+GdKfztwCrAB"
                    "+JWbSCPimcClwCuAI4GnAe/MOagkKY9Ozvj3AhtSSrsjYvs8a54N3JZSuhUg"
                    "Ir4CvDjLhEC9Xmd6ejrXdj0xNfNeH1Oz3vNjJSstL5i5FIOceb63mGhb/Cml"
                    "OrC7zbL/Bo6MiGOBnwKvBL6+uBHnNzExkWurnqvVass9Qk+VlhfMXIpBzDw+"
                    "Pt7yeJbv3E0p3R0RW4CbgWlgG/DZHHsDjI2NDeQZf61WY2RkhGp15X+DdGl5"
                    "wcxmHlxZUkTEccA7aF7y2Q58BPgE8Oc59q9UKlQqlRxb9Vy1Wl3Wd/TrtdLy"
                    "gplLsZIy57qd82TgmpTSbSmlfcAnaV7ukST1mVzPW34AnBMR48CdwOuBWzLt"
                    "LUnK6IDP+CNiY0RcDpBSuhL4FPA94F7gBTTv+Zck9ZmhRqOx3DN0YiCGnK1f"
                    "fmpPr5SWF8xs5oHQ8s37fcsGSSqMxS9JhbH4JakwFr8kFcbil6TCWPySVBiL"
                    "X5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlj8klQYi1+SCmPxS1Jh"
                    "LH5JKozFL0mFsfglqTAWvyQVxuKXpMJY/JJUGItfkgpj8UtSYSx+SSqMxS9J"
                    "hbH4JakwFr8kFcbil6TCVDtZFBFrgdOBzcA5KaVt86x7J3A2cGdK6SXZppQk"
                    "ZdO2+GdKfztwDbABGJpn3V8CrwI2AbfkG1GSlFMnZ/x7gQ0ppd0Rsb3Vgog4"
                    "GDgfeEFKaUfG+QCo1+tMT0/n3nZJTU1N7fdxpSstL5i5FIOceXh4uOXxtsWf"
                    "UqoDu9ss+23gIeCSiDgJ2AacmVK6e5FztjQxMZFjm2VRq9WWe4SeKi0vmLkU"
                    "g5h5fHy85fGOrvF3YAwYAT5D87WAjwOX0rzs0/3mY2MDecZfq9UYGRmhWs31"
                    "Ze5fpeUFM5t5cOVKsQr4j5TSvwNExBbgpkx7U6lUqFQqubbrqWq1Ou/TrZWo"
                    "tLxg5lKspMy5bufcCTx9zrF6pr0lSRnlOuP/T2BNRJwBXEHzhd7vZNpbkpTR"
                    "AZ/xR8TGiLgcIKU0CWwE3gbcA4wC78gxoCQpr6FGo7HcM3RiIIacbXJykl27"
                    "djE6OrpirgsupLS8YGYzD4SW33flWzZIUmEsfkkqjMUvSYWx+CWpMBa/JBXG"
                    "4pekwlj8klQYi1+SCmPxS1JhLH5JKozFL0mFsfglqTAWvyQVxuKXpMJY/JJU"
                    "GItfkgpj8UtSYSx+SSqMxS9JhbH4JakwFr8kFcbil6TCWPySVBiLX5IKY/FL"
                    "UmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlQ7WRQRa4HTgc3AOSmlbQusfQPw"
                    "z8DhKaV7s0wpScqmbfHPlP524BpgAzC0wNonA+/NNJskaQl0csa/F9iQUtod"
                    "EdvbrP0A8A/Axd0ONlu9Xmd6ejrnlktuampqv48rXWl5wcylGOTMw8PDLY+3"
                    "Lf6UUh3Y3W5dRBwHvBh4AZmLf2JiIud2PVWr1ZZ7hJ4qLS+YuRSDmHl8fLzl"
                    "8Y6u8bcTEauATwHnppQei4gc2z5hbGxsIM/4a7UaIyMjVKtZvsx9rbS8YGYz"
                    "D65cKTYDO1NKV2fabz+VSoVKpbIUWy+5arU679Otlai0vGDmUqykzLlu5zwX"
                    "eGVE7IuIfTPHJiLiJZn2lyRlkuWMP6X0nNmPI6IBjHk7pyT1nwM+44+IjRFx"
                    "ec5hJElLb6jRaCz3DJ0YiCFnm5ycZNeuXYyOjq6Y64ILKS0vmNnMA6Hl9135"
                    "lg2SVBiLX5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlj8klQYi1+S"
                    "CmPxS1JhLH5JKozFL0mFsfglqTAWvyQVxuKXpMJY/JJUGItfkgpj8UtSYSx+"
                    "SSqMxS9JhbH4JakwFr8kFcbil6TCWPySVBiLX5IKY/FLUmEsfkkqjMUvSYWp"
                    "drIoItYCpwObgXNSSttarHkX8BZgHXA18KaU0gMZZ5UkZdD2jH+m9LcDpwAb"
                    "gKEWa14FnAm8CHgacAhwUc5BJUl5dHLGvxfYkFLaHRHb51nzNOCDKaWdABHx"
                    "BeA1eUaEer3O9PR0ru16Ympqar+PK11pecHMpRjkzMPDwy2Pty3+lFId2N1m"
                    "zSfmHHohcH2nw7UzMTGRa6ueq9Vqyz1CT5WWF8xcikHMPD4+3vJ4R9f4FyMi"
                    "Xg68BHhHrj3HxsYG8oy/VqsxMjJCtZr9y9x3SssLZjbz4MqaIiKeD3wGODWl"
                    "tDfXvpVKhUqlkmu7nqpWq/M+3VqJSssLZi7FSsqc7XbOiDgS+BpwRkrph7n2"
                    "lSTllaX4I+JQYCvw7pTStTn2lCQtjQO+1BMRG4FXp5ReT/NWzt8ELouIy2Yt"
                    "e15K6WfdjShJymmo0Wgs9wydGIghZ5ucnGTXrl2Mjo6umOuCCyktL5jZzAPh"
                    "V77vCnzLBkkqjsUvSYWx+CWpMBa/JBXG4pekwlj8klQYi1+SCmPxS1JhLH5J"
                    "KozFL0mFsfglqTAWvyQVxuKXpMJY/JJUGItfkgpj8UtSYSx+SSqMxS9JhbH4"
                    "JakwFr8kFcbil6TCWPySVBiLX5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG"
                    "4pekwlj8klSYaieLImItcDqwGTgnpbStxZozgPcCTwa+BZydUnok36iSpBza"
                    "nvHPlP524BRgAzDUYs0ocCnwKmAcOAJ4e85BJUl5dHLGvxfYkFLaHRHb51lz"
                    "CnBtSulWgIj4NHAe8MEcQ9brdaanp3Ns1TNTU1P7fVzpSssLZi7FIGceHh5u"
                    "ebxt8aeU6sDuNsvWA7+Y9fgummf9WUxMTOTaqudqtdpyj9BTpeUFM5diEDOP"
                    "j4+3PN7RNf4OrAHqsx5PAQdl2puxsbGBPOOv1WqMjIxQreb6Mvev0vKCmc08"
                    "uHKleHTOXhVgMtPeVCoVKpVKru16qlqtzvt0ayUqLS+YuRQrKXOu2znvAo6c"
                    "9Xg9cHemvSVJGeU6478K+HhEHA/8CDgbuDLT3pKkjA74jD8iNkbE5QAppTuB"
                    "NwNfBHbSfAbw4SwTSpKyGmo0Gss9QycGYsjZJicn2bVrF6OjoyvmuuBCSssL"
                    "ZjbzQPiV77sC37JBkopj8UtSYfr+ptSIWH3BBRcs9xiLNjU1xf3338/q1atX"
                    "zL2/CyktL5jZzP1vy5Ytvw5sTyk9Nvv4IKR4xpYtW5Z7BkkaRD8BjgFun31w"
                    "EIp/O83BJUmLt33ugUG5q0eSlIkv7kpSYSx+SSqMxS9JhbH4JakwFr8kFcbi"
                    "l6TCWPySVBiLX5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwgzC+/H3"
                    "rYg4A3gv8GTgW8DZKaVHDmRdRHwWOCGl9NwlHrsr3WaOiHXApcDLgWngH1NK"
                    "F/Zm+s5FxCnAx4D1wPeAM1NK93S6JiICeCuwGvhX4IKUUr13CRavm8wRUQX+"
                    "FvhjYBj4KvCWlNJkDyMsWrd/z7PWXARESmltTwbvkmf8BygiRmkW2KuAceAI"
                    "4O0Hsi4iTgJevcQjdy1T5r8G1gHPBE4A3hARpy358IsQEWuAL9As7iOAe4H3"
                    "d7omIk4E3ga8CHgucDLwRz0a/4B0m5lm3hNo5j0GOA44uxezH6gMmR9fcxTN"
                    "/APD4j9wpwDXppRuTSk9DHwaeNli10VEBfgkcHEPZu5WjsyHAB9IKT2cUtoJ"
                    "XEX//YS1E4GdKaXvppQepfmf2NycC605FfhSSmlnSule4J9a/P5+023mpwB/"
                    "k1L6ZUrpl8DX6b+/17m6zfy4S4EPL/m0GXmp58CtB34x6/FdNM8IFrvubcD/"
                    "ADcCr8s8Y25dZ04pvenxgzP/6Z0IfCb7pN3pJOdCa9YDP5/zuVMzz5hbV5lb"
                    "XK57IfDZzDPm1u3fMxGxETgYuALou0uW87H425gppx1zDt8BXAnMvmY7BRzU"
                    "Yos1862LiPXAecDxwG/kmbh7S5l5jg8AP0gpff/Ap10SreZfvYg1nebvJ91m"
                    "fkJEnE3zmd2XMs+YW1eZI+LXgC3AK5dwxiVh8bcx84Lc2NzjEfEX7P/1qwCt"
                    "Xsh6dIF1HwG2zLw4lmfgDJY48+N7vYnmWfCLup13CbSaf2oRa9rm70PdZgYg"
                    "Ik4F3gWclFLq9x/o3W3m9wBfTyn9OCKesVRDLgWv8R+4u4AjZz1eD9zd6bqZ"
                    "s/1XAx+OiH3Ad4DnRMS+mTPuftRV5scfRMTvA+8GXpZS2rMEc3ark5wLren0"
                    "69RPus1MRDwf+HvgFSmlu5ZmzKy6zfx24G0z/35/Ahwy8+/3qCWaNxvP+A/c"
                    "VcDHI+J44Ec072C4stN1M/8whh9fFBEvBj7R57dzdpUZICKOBf6OZun3aznc"
                    "BBwxc7fRlTTv6Jibc6E13wb+LSI+CtwHvJH+f/Gvq8wRMQZ8GXhdSulHPZu6"
                    "O11lTikd8viimTP+H3o75wqXUroTeDPwRWAnzTODD0PzBZ+IuLzdukGTKfP7"
                    "aF5G+q+I2DPz6yc9DdJGSmkvcDqQaL6wdzjNW/OPj4hrF1oz87mbgA8B1wH/"
                    "C1xN817+vtVtZuAC4BnAt2f9ve7p42evOTIPrKFGo98vw0mScvKMX5IKY/FL"
                    "UmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlj8klSY/wPTNSCZbt4GgAAAAABJ"
                    "RU5ErkJggg==\n",
                    "text/plain": "<Figure size 432x288 with 1 Axes>",
                },
                "metadata": {"needs_background": "light"},
                "output_type": "display_data",
            },
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    with disable_capture:
        output = rich_output(image_cell, images=True, image_drawing="block")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[1]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[1]:\x1b[0m  "
        "<AxesSubplot:>                          "
        "                                  \n     "
        "                                        "
        "                                   \n    "
        f"  \x1b]8;id=646742;file://{tempfile_path}2.png"
        "\x1b\\\x1b[94m🖼 Click to vie"
        "w Image\x1b[0m\x1b]8;;\x1b\\                      "
        "                               \n        "
        "                                        "
        "                                \n      \x1b"
        "[39;49m███████\x1b[0m\x1b[38;2;255;255;255;49m"
        "█████████\x1b[0m\x1b[38;2;247;247;247;48;2;255"
        ";255;255m▄\x1b[0m\x1b[38;2;253;253;253;48;2;25"
        "5;255;255m▄\x1b[0m\x1b[38;2;255;255;255;49m███"
        "██████\x1b[0m\x1b[38;2;253;253;253;48;2;255;25"
        "5;255m▄\x1b[0m\x1b[38;2;249;249;249;48;2;255;2"
        "55;255m▄\x1b[0m\x1b[38;2;255;255;255;49m██████"
        "████\x1b[0m\x1b[38;2;249;249;249;48;2;255;255;"
        "255m▄\x1b[0m\x1b[38;2;252;252;252;48;2;255;255"
        ";255m▄\x1b[0m\x1b[38;2;255;255;255;49m████████"
        "██\x1b[0m\x1b[38;2;247;247;247;48;2;255;255;25"
        "5m▄\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b"
        "[0m\x1b[38;2;252;252;252;48;2;255;255;255m▄"
        "\x1b[0m\x1b[38;2;249;249;249;48;2;255;255;255m"
        "▄\x1b[0m\x1b[38;2;255;255;255;49m████████\x1b[0m\x1b"
        "[38;2;255;255;255;48;2;0;0;0m▄\x1b[0m \n    "
        "  \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;114;114;11"
        "4;48;2;121;121;121m▄\x1b[0m\x1b[38;2;117;117;1"
        "17;48;2;115;115;115m▄\x1b[0m\x1b[38;2;116;116;"
        "116;48;2;118;118;118m▄\x1b[0m\x1b[38;2;116;116"
        ";116;48;2;115;115;115m▄\x1b[0m\x1b[38;2;0;0;0;"
        "49m██\x1b[0m\x1b[38;2;249;249;249;48;2;255;255"
        ";255m▄▄\x1b[0m\x1b[38;2;251;251;251;48;2;255;2"
        "55;255m▄\x1b[0m\x1b[38;2;250;250;250;48;2;255;"
        "255;255m▄▄▄▄▄▄\x1b[0m\x1b[38;2;244;244;244;48;"
        "2;250;250;250m▄\x1b[0m\x1b[38;2;249;249;249;48"
        ";2;255;255;255m▄\x1b[0m\x1b[38;2;250;250;250;4"
        "8;2;255;255;255m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;"
        "248;248;48;2;255;255;255m▄\x1b[0m\x1b[38;2;245"
        ";245;245;48;2;251;251;251m▄\x1b[0m\x1b[38;2;25"
        "0;250;250;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0"
        "m\x1b[38;2;245;245;245;48;2;251;251;251m▄\x1b["
        "0m\x1b[38;2;248;248;248;48;2;254;254;254m▄\x1b"
        "[0m\x1b[38;2;250;250;250;48;2;255;255;255m▄"
        "▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;244;244;244;48;2;249"
        ";249;249m▄\x1b[0m\x1b[38;2;250;250;250;48;2;25"
        "5;255;255m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;250;249;25"
        "0;48;2;255;255;255m▄\x1b[0m\x1b[38;2;239;234;2"
        "47;48;2;255;255;254m▄\x1b[0m\x1b[38;2;235;229;"
        "244;48;2;252;253;251m▄\x1b[0m\x1b[38;2;240;234"
        ";249;48;2;255;255;255m▄▄\x1b[0m\x1b[38;2;241;2"
        "36;249;48;2;255;255;255m▄\x1b[0m\x1b[38;2;250;"
        "249;250;48;2;255;255;255m▄\x1b[0m\x1b[38;2;248"
        ";248;247;48;2;255;255;255m▄\x1b[0m\x1b[38;2;24"
        "2;242;242;48;2;255;255;255m▄\x1b[0m\x1b[38;2;2"
        "52;252;252;48;2;255;255;255m▄\x1b[0m\x1b[38;2;"
        "250;250;250;48;2;251;251;251m▄\x1b[0m\x1b[38;2"
        ";255;255;255;49m█\x1b[0m \n      \x1b[38;2;0;0;"
        "0;49m█\x1b[0m\x1b[38;2;0;0;0;48;2;115;115;115m"
        "▄\x1b[0m\x1b[38;2;0;0;0;48;2;114;114;114m▄\x1b[0m"
        "\x1b[38;2;0;0;0;48;2;117;117;117m▄\x1b[0m\x1b[38;"
        "2;0;0;0;48;2;109;109;109m▄\x1b[0m\x1b[38;2;0;0"
        ";0;49m██\x1b[0m\x1b[38;2;255;255;255;49m██████"
        "███\x1b[0m\x1b[38;2;248;248;248;49m█\x1b[0m\x1b[38;2"
        ";253;253;253;49m█\x1b[0m\x1b[38;2;255;255;255;"
        "49m█████████\x1b[0m\x1b[38;2;253;253;253;49m█\x1b"
        "[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;255"
        ";255;255;49m██████████\x1b[0m\x1b[38;2;249;249"
        ";249;49m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m"
        "\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[38"
        ";2;247;247;247;49m█\x1b[0m\x1b[38;2;255;255;25"
        "5;49m█████████\x1b[0m\x1b[38;2;255;255;255;48;"
        "2;251;248;255m▄\x1b[0m\x1b[38;2;254;255;252;48"
        ";2;194;157;247m▄\x1b[0m\x1b[38;2;252;253;249;4"
        "8;2;185;143;244m▄\x1b[0m\x1b[38;2;255;255;255;"
        "48;2;189;147;248m▄\x1b[0m\x1b[38;2;255;255;255"
        ";48;2;188;146;248m▄\x1b[0m\x1b[38;2;255;255;25"
        "5;48;2;196;159;249m▄\x1b[0m\x1b[38;2;255;255;2"
        "55;48;2;252;249;255m▄\x1b[0m\x1b[38;2;250;250;"
        "250;48;2;237;238;237m▄\x1b[0m\x1b[38;2;241;241"
        ";241;48;2;203;203;203m▄\x1b[0m\x1b[38;2;255;25"
        "5;255;49m███\x1b[0m \n      \x1b[38;2;0;0;0;49m"
        "███████\x1b[0m\x1b[38;2;255;255;255;49m███████"
        "██\x1b[0m\x1b[38;2;248;248;248;49m█\x1b[0m\x1b[38;2;"
        "253;253;253;49m█\x1b[0m\x1b[38;2;255;255;255;4"
        "9m█████████\x1b[0m\x1b[38;2;253;253;253;49m█\x1b["
        "0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;255;"
        "255;255;49m██████████\x1b[0m\x1b[38;2;249;249;"
        "249;49m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b"
        "[38;2;255;255;255;49m██████████\x1b[0m\x1b[38;"
        "2;247;247;247;49m█\x1b[0m\x1b[38;2;255;255;255"
        ";49m█████████\x1b[0m\x1b[38;2;249;253;253;48;2"
        ";255;255;255m▄\x1b[0m\x1b[38;2;178;226;228;48;"
        "2;255;254;254m▄\x1b[0m\x1b[38;2;166;220;223;48"
        ";2;255;252;251m▄\x1b[0m\x1b[38;2;171;224;228;4"
        "8;2;255;255;255m▄\x1b[0m\x1b[38;2;170;224;227;"
        "48;2;255;255;255m▄\x1b[0m\x1b[38;2;180;228;231"
        ";48;2;255;255;255m▄\x1b[0m\x1b[38;2;250;254;25"
        "4;48;2;255;255;255m▄\x1b[0m\x1b[38;2;232;231;2"
        "31;48;2;252;252;252m▄\x1b[0m\x1b[38;2;219;219;"
        "219;48;2;255;255;255m▄\x1b[0m\x1b[38;2;255;255"
        ";255;49m███\x1b[0m \n      \x1b[38;2;0;0;0;49m█"
        "\x1b[0m\x1b[38;2;127;127;127;48;2;0;0;0m▄\x1b[0m\x1b"
        "[38;2;115;115;115;48;2;0;0;0m▄\x1b[0m\x1b[38;2"
        ";120;120;120;48;2;0;0;0m▄\x1b[0m\x1b[38;2;127;"
        "127;127;48;2;0;0;0m▄\x1b[0m\x1b[38;2;0;0;0;49m"
        "██\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0"
        "m\x1b[38;2;248;248;248;49m█\x1b[0m\x1b[38;2;253;2"
        "53;253;49m█\x1b[0m\x1b[38;2;255;255;255;49m███"
        "██████\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[3"
        "8;2;249;249;249;49m█\x1b[0m\x1b[38;2;255;255;2"
        "55;49m██████████\x1b[0m\x1b[38;2;249;249;249;4"
        "9m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2"
        ";255;255;255;49m██████████\x1b[0m\x1b[38;2;247"
        ";247;247;49m█\x1b[0m\x1b[38;2;255;255;255;49m█"
        "████████\x1b[0m\x1b[38;2;255;255;255;48;2;252;"
        "254;254m▄\x1b[0m\x1b[38;2;255;253;253;48;2;211"
        ";237;239m▄\x1b[0m\x1b[38;2;254;251;250;48;2;20"
        "2;233;234m▄\x1b[0m\x1b[38;2;255;255;255;48;2;2"
        "08;238;240m▄\x1b[0m\x1b[38;2;255;255;255;48;2;"
        "207;238;239m▄\x1b[0m\x1b[38;2;255;255;255;48;2"
        ";213;240;241m▄\x1b[0m\x1b[38;2;255;255;255;48;"
        "2;252;254;255m▄\x1b[0m\x1b[38;2;255;255;255;48"
        ";2;238;238;238m▄\x1b[0m\x1b[38;2;255;255;255;4"
        "8;2;219;219;219m▄\x1b[0m\x1b[38;2;255;255;255;"
        "49m███\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b"
        "[38;2;102;102;102;48;2;115;115;115m▄\x1b[0m"
        "\x1b[38;2;122;122;122;48;2;114;114;114m▄\x1b[0"
        "m\x1b[38;2;119;119;119;48;2;115;115;115m▄\x1b["
        "0m\x1b[38;2;117;117;117;49m█\x1b[0m\x1b[38;2;0;0;"
        "0;49m██\x1b[0m\x1b[38;2;255;255;255;48;2;249;2"
        "49;249m▄\x1b[0m\x1b[38;2;255;255;255;48;2;247;"
        "247;247m▄\x1b[0m\x1b[38;2;255;255;255;48;2;248"
        ";248;248m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;248;248;4"
        "8;2;242;242;242m▄\x1b[0m\x1b[38;2;253;253;253;"
        "48;2;246;246;246m▄\x1b[0m\x1b[38;2;255;255;255"
        ";48;2;248;248;248m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;25"
        "3;253;253;48;2;246;246;246m▄\x1b[0m\x1b[38;2;2"
        "49;249;249;48;2;243;243;243m▄\x1b[0m\x1b[38;2;"
        "255;255;255;48;2;248;248;248m▄▄▄▄▄▄▄▄▄▄\x1b"
        "[0m\x1b[38;2;249;249;249;48;2;243;243;243m▄"
        "\x1b[0m\x1b[38;2;252;252;252;48;2;245;245;245m"
        "▄\x1b[0m\x1b[38;2;255;255;255;48;2;248;248;248"
        "m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;247;48;2;2"
        "42;242;242m▄\x1b[0m\x1b[38;2;255;255;255;48;2;"
        "248;248;248m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;252;252"
        ";252;48;2;245;245;245m▄\x1b[0m\x1b[38;2;249;24"
        "9;249;48;2;243;243;243m▄\x1b[0m\x1b[38;2;255;2"
        "55;255;48;2;248;248;248m▄▄▄▄▄▄\x1b[0m\x1b[38;2"
        ";255;255;255;48;2;250;250;250m▄\x1b[0m\x1b[38;"
        "2;255;255;255;48;2;246;246;246m▄\x1b[0m\x1b[38"
        ";2;255;255;255;49m█\x1b[0m \n      \x1b[38;2;0;"
        "0;0;49m███████\x1b[0m\x1b[38;2;255;255;255;49m"
        "█████████\x1b[0m\x1b[38;2;248;248;248;49m█\x1b[0m"
        "\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;255;25"
        "5;255;49m█████████\x1b[0m\x1b[38;2;253;253;253"
        ";49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38"
        ";2;255;255;255;49m██████████\x1b[0m\x1b[38;2;2"
        "49;249;249;49m█\x1b[0m\x1b[38;2;252;252;252;49"
        "m█\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b["
        "0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[38;2;255;"
        "255;255;49m██████████\x1b[0m\x1b[38;2;252;252;"
        "252;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b"
        "[38;2;255;255;255;49m█████████\x1b[0m \n    "
        "  \x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[38;2;255;"
        "255;255;49m█████████\x1b[0m\x1b[38;2;248;248;2"
        "48;49m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b["
        "38;2;255;255;255;49m█████████\x1b[0m\x1b[38;2;"
        "253;253;253;49m█\x1b[0m\x1b[38;2;249;249;249;4"
        "9m█\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b"
        "[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;252"
        ";252;252;49m█\x1b[0m\x1b[38;2;255;255;255;49m█"
        "█████████\x1b[0m\x1b[38;2;247;247;247;49m█\x1b[0m"
        "\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[38"
        ";2;252;252;252;49m█\x1b[0m\x1b[38;2;249;249;24"
        "9;49m█\x1b[0m\x1b[38;2;255;255;255;49m████████"
        "█\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2"
        ";116;116;116;48;2;85;85;85m▄\x1b[0m\x1b[38;2;1"
        "19;119;119;48;2;170;170;170m▄\x1b[0m\x1b[38;2;"
        "117;117;117;48;2;127;127;127m▄\x1b[0m\x1b[38;2"
        ";119;119;119;48;2;127;127;127m▄\x1b[0m\x1b[38;"
        "2;0;0;0;49m██\x1b[0m\x1b[38;2;249;249;249;48;2"
        ";255;255;255m▄\x1b[0m\x1b[38;2;247;247;247;48;"
        "2;255;255;255m▄\x1b[0m\x1b[38;2;249;249;249;48"
        ";2;255;255;255m▄\x1b[0m\x1b[38;2;248;248;248;4"
        "8;2;255;255;255m▄▄▄▄▄▄\x1b[0m\x1b[38;2;243;243"
        ";243;48;2;248;248;248m▄\x1b[0m\x1b[38;2;247;24"
        "7;247;48;2;253;253;253m▄\x1b[0m\x1b[38;2;248;2"
        "48;248;48;2;255;255;255m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[3"
        "8;2;247;247;247;48;2;253;253;253m▄\x1b[0m\x1b["
        "38;2;243;243;243;48;2;249;249;249m▄\x1b[0m\x1b"
        "[38;2;248;248;248;48;2;255;255;255m▄▄▄▄▄"
        "▄▄▄▄▄\x1b[0m\x1b[38;2;243;243;243;48;2;249;249"
        ";249m▄\x1b[0m\x1b[38;2;246;246;246;48;2;252;25"
        "2;252m▄\x1b[0m\x1b[38;2;248;248;248;48;2;255;2"
        "55;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;242;242;242;"
        "48;2;247;247;247m▄\x1b[0m\x1b[38;2;248;248;248"
        ";48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;2"
        "46;246;246;48;2;252;252;252m▄\x1b[0m\x1b[38;2;"
        "243;243;243;48;2;249;249;249m▄\x1b[0m\x1b[38;2"
        ";248;248;248;48;2;255;255;255m▄▄▄▄▄▄\x1b[0m"
        "\x1b[38;2;251;251;251;48;2;255;255;255m▄\x1b[0"
        "m\x1b[38;2;247;247;247;48;2;255;255;255m▄\x1b["
        "0m\x1b[38;2;255;255;255;49m█\x1b[0m \n      \x1b[3"
        "8;2;0;0;0;49m█\x1b[0m\x1b[38;2;0;0;0;48;2;127;"
        "127;127m▄\x1b[0m\x1b[38;2;0;0;0;48;2;116;116;1"
        "16m▄\x1b[0m\x1b[38;2;0;0;0;48;2;118;118;118m▄\x1b"
        "[0m\x1b[38;2;0;0;0;48;2;114;114;114m▄\x1b[0m\x1b["
        "38;2;0;0;0;49m██\x1b[0m\x1b[38;2;255;255;255;4"
        "9m█\x1b[0m\x1b[38;2;255;255;255;48;2;253;253;2"
        "53m▄\x1b[0m\x1b[38;2;255;255;255;48;2;254;254;"
        "254m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;248;248;48;2;2"
        "47;247;247m▄\x1b[0m\x1b[38;2;253;253;253;48;2;"
        "252;252;252m▄\x1b[0m\x1b[38;2;255;255;255;48;2"
        ";254;254;254m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;253;253"
        ";253;48;2;252;252;252m▄\x1b[0m\x1b[38;2;249;24"
        "9;249;48;2;248;248;248m▄\x1b[0m\x1b[38;2;255;2"
        "55;255;48;2;254;254;254m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b["
        "38;2;249;249;249;48;2;248;248;248m▄\x1b[0m\x1b"
        "[38;2;252;252;252;48;2;251;251;251m▄\x1b[0m"
        "\x1b[38;2;255;255;255;48;2;254;254;254m▄▄▄▄"
        "▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;247;48;2;246;24"
        "6;246m▄\x1b[0m\x1b[38;2;255;255;255;48;2;254;2"
        "54;254m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;252;252;252;"
        "48;2;251;251;251m▄\x1b[0m\x1b[38;2;249;249;249"
        ";48;2;248;248;248m▄\x1b[0m\x1b[38;2;255;255;25"
        "5;48;2;254;254;254m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;255"
        ";255;255;48;2;253;253;253m▄\x1b[0m\x1b[38;2;25"
        "5;255;255;49m█\x1b[0m \n      \x1b[38;2;0;0;0;4"
        "9m███████\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "████\x1b[0m\x1b[38;2;248;248;248;49m█\x1b[0m\x1b[38;"
        "2;253;253;253;49m█\x1b[0m\x1b[38;2;255;255;255"
        ";49m█████████\x1b[0m\x1b[38;2;253;253;253;49m█"
        "\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;25"
        "5;255;255;49m██████████\x1b[0m\x1b[38;2;249;24"
        "9;249;49m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0"
        "m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[3"
        "8;2;247;247;247;49m█\x1b[0m\x1b[38;2;255;255;2"
        "55;49m██████████\x1b[0m\x1b[38;2;252;252;252;4"
        "9m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2"
        ";255;255;255;49m█████████\x1b[0m \n      \x1b[3"
        "8;2;0;0;0;49m███████\x1b[0m\x1b[38;2;255;255;2"
        "55;49m█████████\x1b[0m\x1b[38;2;248;248;248;49"
        "m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;"
        "255;255;255;49m█████████\x1b[0m\x1b[38;2;253;2"
        "53;253;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b["
        "0m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b["
        "38;2;249;249;249;49m█\x1b[0m\x1b[38;2;252;252;"
        "252;49m█\x1b[0m\x1b[38;2;255;255;255;49m██████"
        "████\x1b[0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[38;"
        "2;255;255;255;49m██████████\x1b[0m\x1b[38;2;25"
        "2;252;252;49m█\x1b[0m\x1b[38;2;249;249;249;49m"
        "█\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0m"
        " \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;111;"
        "111;111;48;2;120;120;120m▄\x1b[0m\x1b[38;2;113"
        ";113;113;48;2;118;118;118m▄\x1b[0m\x1b[38;2;11"
        "5;115;115;48;2;116;116;116m▄\x1b[0m\x1b[38;2;1"
        "16;116;116;48;2;113;113;113m▄\x1b[0m\x1b[38;2;"
        "0;0;0;49m██\x1b[0m\x1b[38;2;249;249;249;48;2;2"
        "55;255;255m▄\x1b[0m\x1b[38;2;249;249;249;48;2;"
        "251;251;251m▄\x1b[0m\x1b[38;2;250;250;250;48;2"
        ";252;252;252m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;244;244;2"
        "44;48;2;246;246;246m▄\x1b[0m\x1b[38;2;248;248;"
        "248;48;2;250;250;250m▄\x1b[0m\x1b[38;2;250;250"
        ";250;48;2;252;252;252m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;"
        "2;248;248;248;48;2;250;250;250m▄\x1b[0m\x1b[38"
        ";2;245;245;245;48;2;246;246;246m▄\x1b[0m\x1b[3"
        "8;2;250;250;250;48;2;252;252;252m▄▄▄▄▄▄▄"
        "▄▄▄\x1b[0m\x1b[38;2;245;245;245;48;2;246;246;2"
        "46m▄\x1b[0m\x1b[38;2;247;247;247;48;2;249;249;"
        "249m▄\x1b[0m\x1b[38;2;250;250;250;48;2;252;252"
        ";252m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;243;243;243;48"
        ";2;245;245;245m▄\x1b[0m\x1b[38;2;250;250;250;4"
        "8;2;252;252;252m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247"
        ";247;247;48;2;249;249;249m▄\x1b[0m\x1b[38;2;24"
        "5;245;245;48;2;246;246;246m▄\x1b[0m\x1b[38;2;2"
        "50;250;250;48;2;252;252;252m▄▄▄▄▄▄\x1b[0m\x1b["
        "38;2;252;252;252;48;2;253;253;253m▄\x1b[0m\x1b"
        "[38;2;248;248;248;48;2;251;251;251m▄\x1b[0m"
        "\x1b[38;2;255;255;255;49m█\x1b[0m \n      \x1b[38;"
        "2;0;0;0;49m█\x1b[0m\x1b[38;2;0;0;0;48;2;127;12"
        "7;127m▄▄\x1b[0m\x1b[38;2;0;0;0;48;2;109;109;10"
        "9m▄\x1b[0m\x1b[38;2;0;0;0;48;2;95;95;95m▄\x1b[0m\x1b"
        "[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;255;255;255;"
        "49m█████████\x1b[0m\x1b[38;2;248;248;248;49m█\x1b"
        "[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;255"
        ";255;255;49m█████████\x1b[0m\x1b[38;2;253;253;"
        "253;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b"
        "[38;2;255;255;255;49m██████████\x1b[0m\x1b[38;"
        "2;249;249;249;49m█\x1b[0m\x1b[38;2;252;252;252"
        ";49m█\x1b[0m\x1b[38;2;255;255;255;49m█████████"
        "█\x1b[0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[38;2;2"
        "55;255;255;49m██████████\x1b[0m\x1b[38;2;252;2"
        "52;252;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b["
        "0m\x1b[38;2;255;255;255;49m█████████\x1b[0m \n "
        "     \x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[38;2;2"
        "55;255;255;49m█████████\x1b[0m\x1b[38;2;248;24"
        "8;248;49m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0"
        "m\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b[38"
        ";2;253;253;253;49m█\x1b[0m\x1b[38;2;249;249;24"
        "9;49m█\x1b[0m\x1b[38;2;255;255;255;49m████████"
        "██\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;"
        "252;252;252;49m█\x1b[0m\x1b[38;2;255;255;255;4"
        "9m██████████\x1b[0m\x1b[38;2;247;247;247;49m█\x1b"
        "[0m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b"
        "[38;2;252;252;252;49m█\x1b[0m\x1b[38;2;249;249"
        ";249;49m█\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "████\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[3"
        "8;2;127;127;127;48;2;0;0;0m▄\x1b[0m\x1b[38;2;1"
        "13;113;113;48;2;0;0;0m▄\x1b[0m\x1b[38;2;122;12"
        "2;122;48;2;0;0;0m▄\x1b[0m\x1b[38;2;120;120;120"
        ";48;2;0;0;0m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b"
        "[38;2;255;255;255;49m█\x1b[0m\x1b[38;2;253;253"
        ";253;48;2;255;255;255m▄\x1b[0m\x1b[38;2;254;25"
        "4;254;48;2;255;255;255m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2"
        ";247;247;247;48;2;248;248;248m▄\x1b[0m\x1b[38;"
        "2;252;252;252;48;2;253;253;253m▄\x1b[0m\x1b[38"
        ";2;254;254;254;48;2;255;255;255m▄▄▄▄▄▄▄▄"
        "▄\x1b[0m\x1b[38;2;252;252;252;48;2;253;253;253"
        "m▄\x1b[0m\x1b[38;2;248;248;248;48;2;249;249;24"
        "9m▄\x1b[0m\x1b[38;2;254;254;254;48;2;255;255;2"
        "55m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;248;248;48;2"
        ";249;249;249m▄\x1b[0m\x1b[38;2;251;251;251;48;"
        "2;252;252;252m▄\x1b[0m\x1b[38;2;254;254;254;48"
        ";2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;246;"
        "246;246;48;2;247;247;247m▄\x1b[0m\x1b[38;2;254"
        ";254;254;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m"
        "\x1b[38;2;251;251;251;48;2;252;252;252m▄\x1b[0"
        "m\x1b[38;2;248;248;248;48;2;249;249;249m▄\x1b["
        "0m\x1b[38;2;254;254;254;48;2;255;255;255m▄▄"
        "▄▄▄▄▄\x1b[0m\x1b[38;2;253;253;253;48;2;255;255"
        ";255m▄\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0m \n "
        "     \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;170;170"
        ";170;48;2;114;114;114m▄\x1b[0m\x1b[38;2;120;12"
        "0;120;48;2;117;117;117m▄\x1b[0m\x1b[38;2;114;1"
        "14;114;48;2;119;119;119m▄\x1b[0m\x1b[38;2;120;"
        "120;120;48;2;117;117;117m▄\x1b[0m\x1b[38;2;0;0"
        ";0;49m██\x1b[0m\x1b[38;2;255;255;255;48;2;249;"
        "249;249m▄\x1b[0m\x1b[38;2;255;255;255;48;2;247"
        ";247;247m▄\x1b[0m\x1b[38;2;255;255;255;48;2;24"
        "8;248;248m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;248;248;"
        "48;2;243;243;243m▄\x1b[0m\x1b[38;2;253;253;253"
        ";48;2;247;247;247m▄\x1b[0m\x1b[38;2;255;255;25"
        "5;48;2;248;248;248m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;2"
        "53;253;253;48;2;246;246;246m▄\x1b[0m\x1b[38;2;"
        "249;249;249;48;2;243;243;243m▄\x1b[0m\x1b[38;2"
        ";255;255;255;48;2;248;248;248m▄▄▄▄▄▄▄▄▄▄"
        "\x1b[0m\x1b[38;2;249;249;249;48;2;243;243;243m"
        "▄\x1b[0m\x1b[38;2;252;252;252;48;2;246;246;246"
        "m▄\x1b[0m\x1b[38;2;255;255;255;48;2;248;248;24"
        "8m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;247;48;2;"
        "242;242;242m▄\x1b[0m\x1b[38;2;255;255;255;48;2"
        ";248;248;248m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;252;25"
        "2;252;48;2;246;246;246m▄\x1b[0m\x1b[38;2;249;2"
        "49;249;48;2;243;243;243m▄\x1b[0m\x1b[38;2;255;"
        "255;255;48;2;248;248;248m▄▄▄▄▄▄\x1b[0m\x1b[38;"
        "2;255;255;255;48;2;250;250;250m▄\x1b[0m\x1b[38"
        ";2;255;255;255;48;2;247;247;247m▄\x1b[0m\x1b[3"
        "8;2;255;255;255;49m█\x1b[0m \n      \x1b[38;2;0"
        ";0;0;49m███████\x1b[0m\x1b[38;2;255;255;255;49"
        "m█████████\x1b[0m\x1b[38;2;248;248;248;49m█\x1b[0"
        "m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;255;2"
        "55;255;49m█████████\x1b[0m\x1b[38;2;253;253;25"
        "3;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[3"
        "8;2;255;255;255;49m██████████\x1b[0m\x1b[38;2;"
        "249;249;249;49m█\x1b[0m\x1b[38;2;252;252;252;4"
        "9m█\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b"
        "[0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[38;2;255"
        ";255;255;49m██████████\x1b[0m\x1b[38;2;252;252"
        ";252;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m"
        "\x1b[38;2;255;255;255;49m█████████\x1b[0m \n   "
        "   \x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[38;2;255"
        ";255;255;49m█████████\x1b[0m\x1b[38;2;248;248;"
        "248;49m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b"
        "[38;2;255;255;255;49m█████████\x1b[0m\x1b[38;2"
        ";253;253;253;49m█\x1b[0m\x1b[38;2;249;249;249;"
        "49m█\x1b[0m\x1b[38;2;255;255;255;49m██████████"
        "\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;25"
        "2;252;252;49m█\x1b[0m\x1b[38;2;255;255;255;49m"
        "██████████\x1b[0m\x1b[38;2;247;247;247;49m█\x1b[0"
        "m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[3"
        "8;2;252;252;252;49m█\x1b[0m\x1b[38;2;249;249;2"
        "49;49m█\x1b[0m\x1b[38;2;255;255;255;49m███████"
        "██\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;"
        "2;116;116;116;48;2;127;127;127m▄▄▄\x1b[0m\x1b["
        "38;2;118;118;118;48;2;127;127;127m▄\x1b[0m\x1b"
        "[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;249;249;249;"
        "48;2;255;255;255m▄\x1b[0m\x1b[38;2;248;248;248"
        ";48;2;255;255;255m▄\x1b[0m\x1b[38;2;249;249;24"
        "9;48;2;255;255;255m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;243"
        ";243;243;48;2;248;248;248m▄\x1b[0m\x1b[38;2;24"
        "7;247;247;48;2;253;253;253m▄\x1b[0m\x1b[38;2;2"
        "49;249;249;48;2;255;255;255m▄▄▄▄▄▄▄▄▄\x1b[0"
        "m\x1b[38;2;247;247;247;48;2;253;253;253m▄\x1b["
        "0m\x1b[38;2;244;244;244;48;2;249;249;249m▄\x1b"
        "[0m\x1b[38;2;249;249;249;48;2;255;255;255m▄"
        "▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;244;244;244;48;2;249"
        ";249;249m▄\x1b[0m\x1b[38;2;246;246;246;48;2;25"
        "2;252;252m▄\x1b[0m\x1b[38;2;249;249;249;48;2;2"
        "55;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;242;242;"
        "242;48;2;247;247;247m▄\x1b[0m\x1b[38;2;249;249"
        ";249;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38"
        ";2;246;246;246;48;2;252;252;252m▄\x1b[0m\x1b[3"
        "8;2;244;244;244;48;2;249;249;249m▄\x1b[0m\x1b["
        "38;2;249;249;249;48;2;255;255;255m▄▄▄▄▄▄"
        "\x1b[0m\x1b[38;2;251;251;251;48;2;255;255;255m"
        "▄\x1b[0m\x1b[38;2;247;247;247;48;2;255;255;255"
        "m▄\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0m \n     "
        " \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;0;0;0;48;2;"
        "113;113;113m▄\x1b[0m\x1b[38;2;0;0;0;48;2;120;1"
        "20;120m▄\x1b[0m\x1b[38;2;0;0;0;48;2;118;118;11"
        "8m▄\x1b[0m\x1b[38;2;0;0;0;48;2;117;117;117m▄\x1b["
        "0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;205;205;2"
        "05;48;2;255;255;255m▄\x1b[0m\x1b[38;2;211;211;"
        "211;48;2;255;255;255m▄\x1b[0m\x1b[38;2;210;210"
        ";210;48;2;255;255;255m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;"
        "206;206;206;48;2;255;255;255m▄\x1b[0m\x1b[38;2"
        ";209;209;209;48;2;255;255;255m▄\x1b[0m\x1b[38;"
        "2;210;210;210;48;2;255;255;255m▄▄▄▄▄▄▄▄▄"
        "\x1b[0m\x1b[38;2;209;209;209;48;2;255;255;255m"
        "▄\x1b[0m\x1b[38;2;206;206;206;48;2;255;255;255"
        "m▄\x1b[0m\x1b[38;2;210;210;210;48;2;255;255;25"
        "5m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;206;206;206;48;2;"
        "255;255;255m▄\x1b[0m\x1b[38;2;209;209;209;48;2"
        ";255;255;255m▄\x1b[0m\x1b[38;2;210;210;210;48;"
        "2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;204;2"
        "04;204;48;2;255;255;255m▄\x1b[0m\x1b[38;2;210;"
        "210;210;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b"
        "[38;2;209;209;209;48;2;255;255;255m▄\x1b[0m"
        "\x1b[38;2;206;206;206;48;2;255;255;255m▄\x1b[0"
        "m\x1b[38;2;210;210;210;48;2;255;255;255m▄▄▄"
        "▄▄▄\x1b[0m\x1b[38;2;211;211;211;48;2;255;255;2"
        "55m▄\x1b[0m\x1b[38;2;206;206;206;48;2;255;255;"
        "255m▄\x1b[0m\x1b[38;2;127;127;127;48;2;255;255"
        ";255m▄\x1b[0m \n      \x1b[38;2;0;0;0;49m██████"
        "████████████████████████████████████████"
        "███████████████████████████\x1b[0m \n      \x1b"
        "[38;2;0;0;0;49m█████████████\x1b[0m\x1b[38;2;1"
        "02;102;102;48;2;0;0;0m▄\x1b[0m\x1b[38;2;117;11"
        "7;117;48;2;127;127;127m▄\x1b[0m\x1b[38;2;118;1"
        "18;118;48;2;116;116;116m▄\x1b[0m\x1b[38;2;119;"
        "119;119;48;2;127;127;127m▄\x1b[0m\x1b[38;2;116"
        ";116;116;48;2;119;119;119m▄\x1b[0m\x1b[38;2;11"
        "5;115;115;48;2;121;121;121m▄\x1b[0m\x1b[38;2;1"
        "17;117;117;48;2;115;115;115m▄\x1b[0m\x1b[38;2;"
        "0;0;0;49m█████\x1b[0m\x1b[38;2;113;113;113;48;"
        "2;0;0;0m▄\x1b[0m\x1b[38;2;114;114;114;48;2;119"
        ";119;119m▄\x1b[0m\x1b[38;2;118;118;118;49m█\x1b[0"
        "m\x1b[38;2;118;118;118;48;2;120;120;120m▄\x1b["
        "0m\x1b[38;2;116;116;116;48;2;120;120;120m▄\x1b"
        "[0m\x1b[38;2;118;118;118;48;2;115;115;115m▄"
        "\x1b[0m\x1b[38;2;102;102;102;48;2;127;127;127m"
        "▄\x1b[0m\x1b[38;2;0;0;0;49m█████\x1b[0m\x1b[38;2;120"
        ";120;120;48;2;115;115;115m▄\x1b[0m\x1b[38;2;11"
        "7;117;117;48;2;115;115;115m▄\x1b[0m\x1b[38;2;1"
        "17;117;117;48;2;121;121;121m▄\x1b[0m\x1b[38;2;"
        "118;118;118;48;2;112;112;112m▄\x1b[0m\x1b[38;2"
        ";117;117;117;48;2;115;115;115m▄\x1b[0m\x1b[38;"
        "2;127;127;127;48;2;0;0;0m▄\x1b[0m\x1b[38;2;0;0"
        ";0;49m██████\x1b[0m\x1b[38;2;115;115;115;48;2;"
        "122;122;122m▄\x1b[0m\x1b[38;2;115;115;115;48;2"
        ";109;109;109m▄\x1b[0m\x1b[38;2;115;115;115;49m"
        "█\x1b[0m\x1b[38;2;115;115;115;48;2;112;112;112"
        "m▄\x1b[0m\x1b[38;2;112;112;112;48;2;121;121;12"
        "1m▄\x1b[0m\x1b[38;2;0;0;0;49m██████\x1b[0m\x1b[38;2;"
        "106;106;106;48;2;127;127;127m▄\x1b[0m\x1b[38;2"
        ";118;118;118;48;2;112;112;112m▄\x1b[0m\x1b[38;"
        "2;119;119;119;48;2;111;111;111m▄\x1b[0m\x1b[38"
        ";2;118;118;118;48;2;115;115;115m▄\x1b[0m\x1b[3"
        "8;2;116;116;116;48;2;121;121;121m▄\x1b[0m\x1b["
        "38;2;112;112;112;48;2;109;109;109m▄\x1b[0m\x1b"
        "[38;2;0;0;0;49m███████\x1b[0m \n      \x1b[38;2"
        ";0;0;0;49m██████████████\x1b[0m\x1b[38;2;0;0;0"
        ";48;2;170;170;170m▄\x1b[0m\x1b[38;2;0;0;0;48;2"
        ";120;120;120m▄▄\x1b[0m\x1b[38;2;0;0;0;48;2;112"
        ";112;112m▄▄\x1b[0m\x1b[38;2;0;0;0;48;2;127;127"
        ";127m▄\x1b[0m\x1b[38;2;0;0;0;49m██████\x1b[0m\x1b[38"
        ";2;0;0;0;48;2;119;119;119m▄▄\x1b[0m\x1b[38;2;0"
        ";0;0;48;2;115;115;115m▄\x1b[0m\x1b[38;2;0;0;0;"
        "48;2;120;120;120m▄▄\x1b[0m\x1b[38;2;0;0;0;48;2"
        ";127;127;127m▄\x1b[0m\x1b[38;2;0;0;0;49m█████\x1b"
        "[0m\x1b[38;2;0;0;0;48;2;115;115;115m▄\x1b[0m\x1b["
        "38;2;0;0;0;48;2;120;120;120m▄\x1b[0m\x1b[38;2;"
        "0;0;0;48;2;117;117;117m▄\x1b[0m\x1b[38;2;0;0;0"
        ";48;2;119;119;119m▄\x1b[0m\x1b[38;2;0;0;0;48;2"
        ";115;115;115m▄\x1b[0m\x1b[38;2;0;0;0;49m██████"
        "█\x1b[0m\x1b[38;2;0;0;0;48;2;112;112;112m▄\x1b[0m"
        "\x1b[38;2;0;0;0;48;2;113;113;113m▄\x1b[0m\x1b[38;"
        "2;0;0;0;48;2;115;115;115m▄\x1b[0m\x1b[38;2;0;0"
        ";0;48;2;121;121;121m▄▄\x1b[0m\x1b[38;2;0;0;0;4"
        "9m██████\x1b[0m\x1b[38;2;0;0;0;48;2;127;127;12"
        "7m▄\x1b[0m\x1b[38;2;0;0;0;48;2;120;120;120m▄\x1b["
        "0m\x1b[38;2;0;0;0;48;2;110;110;110m▄\x1b[0m\x1b[3"
        "8;2;0;0;0;48;2;115;115;115m▄\x1b[0m\x1b[38;2;0"
        ";0;0;48;2;117;117;117m▄\x1b[0m\x1b[38;2;0;0;0;"
        "48;2;113;113;113m▄\x1b[0m\x1b[38;2;0;0;0;49m██"
        "█████\x1b[0m \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_image_link_no_image(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
    disable_capture: ContextManager[_PluggyPlugin],
) -> None:
    """It renders a link to an image."""
    image_cell = {
        "cell_type": "code",
        "execution_count": 1,
        "id": "43e39858-6416-4dc8-9d7e-7905127e7452",
        "metadata": {},
        "outputs": [
            {
                "data": {"text/plain": "<AxesSubplot:>"},
                "execution_count": 1,
                "metadata": {},
                "output_type": "execute_result",
            },
            {
                "data": {
                    "image/png": "iVBORw0KGgoAAAANSUhEUgAAAX4AAAEDCAYAAAAyZm"
                    "/jAAAAOXRFWHRTb2Z0"
                    "d2FyZQBNYXRwbG90bGliIHZlcnNpb24zLjQuMiwgaHR0cHM6Ly9tYXRwbG90"
                    "bGliLm9yZy8rg+JYAAAACXBIWXMAAAsTAAALEwEAmpwYAAATJElEQVR4nO3d"
                    "f5DcdX3H8edl90IoiTgoN+Q8PEVSRmtFS4EO2hktMsUqNs7YiFW0paYg/gBl"
                    "eGuniFOtxX7iD8RftS1Oa7Hi+LtmtAgIZRwoTtMiaEXG0SQcARck/AgkcLe3"
                    "/WMPejn3bveyn9vbvc/zMZO52e998sn7dZm88t3vfm9vqNFoIEkqx6rlHkCS"
                    "1FsWvyQVxuKXpMJY/JJUGItfkgozKMXfGLRf9Xq9sWPHjka9Xl/2WcxrZjMX"
                    "m7mlQSn+gTM9Pb3fx5WutLxg5lKsxMwWvyQVxuKXpMJY/JJUGItfkgpj8UtS"
                    "YaqdLIqINwLvAQ4HbgL+LKV0x5w1pwAfA9YD3wPOTCndk3dcSVK32p7xR8Rx"
                    "wBbgD4GnAjuAS+asWQN8AXgrcARwL/D+zLNKkjLo5Iz/mcBHU0o/AoiIzwGf"
                    "nrPmRGBnSum7M2suBb6ea8h6vT5w99BOTU3t93GlKy0vmLkUg5x5eHi45fG2"
                    "xZ9S+vKcQy8Erp9zbD3wi1mP76J55p/FxMRErq16rlarLfcIPVVaXjBzKQYx"
                    "8/j4eMvjHV3jf1xE/BbwFuD4OZ9aA9RnPZ4CVi9m74WMjY0N5Bl/rVZjZGSE"
                    "anVRX+aBVFpeMLOZB1fHKSLi6cBXgT9JKd0959OPztmrQrP8s6hUKlQqlVzb"
                    "9VS1Wp336dZKVFpeMHMpVlLmjm7njIhDga3AhSmla1osuQs4ctbj9cDc/xwk"
                    "SX2g7Rl/RAwDXwH+JaV0+TzLbgKOiIjTgCtp3t1zZbYpJUnZdHKp5xXAycDv"
                    "RMR7Zx3/K+APUkovSSntjYjTgUuBz9F88fdPs08rSQW5/fbb+drXvsbDDz/M"
                    "s571LF7zmtewZs2arvcdajTmfcvmfjIQQ842OTnJrl27GB0dXTHXBRdSWl4w"
                    "80rM/LPvT7H1/fvY99D/V06jMc1jjz7G6oNWMzTU/ZsdrFk3xCves4ajTlj4"
                    "vPvBBx/kQx/6EGeddRYjIyNcdtllbNiwgZNPPnkxf9xQq4Mr4yVqScrg6kv2"
                    "ccvWyRafqQLTM7+6d/CThjjq8wvX78EHH8y5557LU57yFACOOeYY7rknz5sh"
                    "WPySNOOl561h30Ms+Rn/S887qO264eFhbrvtNm688UYefPBBpqamOPbYY7v+"
                    "88Hil6QnHHVClbd/c+1+x5qXt+5ndPTJPb28tWPHDq677jo2b97M4YcfzvXX"
                    "X8/dd+e5WdJ355SkPvTII48wPDzMunXreOihh7j99tuzfSOrZ/yS1IeOOeYY"
                    "br31Vi6++GIOPfRQjj76aB544IEse1v8ktSHVq1axaZNm9i0aVP+vbPvKEnq"
                    "axa/JBXG4pekwlj8klQYi1+SCmPxS1JhLH5JKozFL0mFsfglqQ/dd999XHjh"
                    "hUuyt8UvSYWx+CWpML5XjyT1qUajwTe+8Q1uvvlm1q1bx6ZNmxgbG+t6X4tf"
                    "kmZ8/977eP8tP+ahqaknjjWmGzz62KMc9OOfM7Sq5U8yXJR11Srved6zOeGp"
                    "h7VdOzk5ydjYGKeddho33HADV1xxBeeffz5DQ93NYfFL0oxLfvxTtt453w87"
                    "2ZPtz3nS8DCf/90T2q5bvXo1xx13HAAnnXQSV111Fffdd98TP47xQFn8kjTj"
                    "vGcfzUOTk63P+FcflO2M/7xnH73o37dq1SoOOeQQ9uzZY/FLUi4nPPUwvvl7"
                    "L9zvWPNHL+5idHS0pz96ca7p6Wn27NnD2rVr2y9uw7t6JKlPPfbYY2zbto3p"
                    "6WluuOEGDj30UA47rP1rA+14xi9JfWrt2rXccccdbN26lXXr1vHa17626xd2"
                    "weKXpL502GGHcdFFFwGwcePGrHt7qUeSCmPxS1JhLH5JKozFL0mFsfglqTAd"
                    "3dUTEWuB04HNwDkppW0t1rwReB+wDtgKnJVS2ptxVklSBm3P+GdKfztwCrAB"
                    "+JWbSCPimcClwCuAI4GnAe/MOagkKY9Ozvj3AhtSSrsjYvs8a54N3JZSuhUg"
                    "Ir4CvDjLhEC9Xmd6ejrXdj0xNfNeH1Oz3vNjJSstL5i5FIOceb63mGhb/Cml"
                    "OrC7zbL/Bo6MiGOBnwKvBL6+uBHnNzExkWurnqvVass9Qk+VlhfMXIpBzDw+"
                    "Pt7yeJbv3E0p3R0RW4CbgWlgG/DZHHsDjI2NDeQZf61WY2RkhGp15X+DdGl5"
                    "wcxmHlxZUkTEccA7aF7y2Q58BPgE8Oc59q9UKlQqlRxb9Vy1Wl3Wd/TrtdLy"
                    "gplLsZIy57qd82TgmpTSbSmlfcAnaV7ukST1mVzPW34AnBMR48CdwOuBWzLt"
                    "LUnK6IDP+CNiY0RcDpBSuhL4FPA94F7gBTTv+Zck9ZmhRqOx3DN0YiCGnK1f"
                    "fmpPr5SWF8xs5oHQ8s37fcsGSSqMxS9JhbH4JakwFr8kFcbil6TCWPySVBiL"
                    "X5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlj8klQYi1+SCmPxS1Jh"
                    "LH5JKozFL0mFsfglqTAWvyQVxuKXpMJY/JJUGItfkgpj8UtSYSx+SSqMxS9J"
                    "hbH4JakwFr8kFcbil6TCVDtZFBFrgdOBzcA5KaVt86x7J3A2cGdK6SXZppQk"
                    "ZdO2+GdKfztwDbABGJpn3V8CrwI2AbfkG1GSlFMnZ/x7gQ0ppd0Rsb3Vgog4"
                    "GDgfeEFKaUfG+QCo1+tMT0/n3nZJTU1N7fdxpSstL5i5FIOceXh4uOXxtsWf"
                    "UqoDu9ss+23gIeCSiDgJ2AacmVK6e5FztjQxMZFjm2VRq9WWe4SeKi0vmLkU"
                    "g5h5fHy85fGOrvF3YAwYAT5D87WAjwOX0rzs0/3mY2MDecZfq9UYGRmhWs31"
                    "Ze5fpeUFM5t5cOVKsQr4j5TSvwNExBbgpkx7U6lUqFQqubbrqWq1Ou/TrZWo"
                    "tLxg5lKspMy5bufcCTx9zrF6pr0lSRnlOuP/T2BNRJwBXEHzhd7vZNpbkpTR"
                    "AZ/xR8TGiLgcIKU0CWwE3gbcA4wC78gxoCQpr6FGo7HcM3RiIIacbXJykl27"
                    "djE6OrpirgsupLS8YGYzD4SW33flWzZIUmEsfkkqjMUvSYWx+CWpMBa/JBXG"
                    "4pekwlj8klQYi1+SCmPxS1JhLH5JKozFL0mFsfglqTAWvyQVxuKXpMJY/JJU"
                    "GItfkgpj8UtSYSx+SSqMxS9JhbH4JakwFr8kFcbil6TCWPySVBiLX5IKY/FL"
                    "UmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlQ7WRQRa4HTgc3AOSmlbQusfQPw"
                    "z8DhKaV7s0wpScqmbfHPlP524BpgAzC0wNonA+/NNJskaQl0csa/F9iQUtod"
                    "EdvbrP0A8A/Axd0ONlu9Xmd6ejrnlktuampqv48rXWl5wcylGOTMw8PDLY+3"
                    "Lf6UUh3Y3W5dRBwHvBh4AZmLf2JiIud2PVWr1ZZ7hJ4qLS+YuRSDmHl8fLzl"
                    "8Y6u8bcTEauATwHnppQei4gc2z5hbGxsIM/4a7UaIyMjVKtZvsx9rbS8YGYz"
                    "D65cKTYDO1NKV2fabz+VSoVKpbIUWy+5arU679Otlai0vGDmUqykzLlu5zwX"
                    "eGVE7IuIfTPHJiLiJZn2lyRlkuWMP6X0nNmPI6IBjHk7pyT1nwM+44+IjRFx"
                    "ec5hJElLb6jRaCz3DJ0YiCFnm5ycZNeuXYyOjq6Y64ILKS0vmNnMA6Hl9135"
                    "lg2SVBiLX5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlj8klQYi1+S"
                    "CmPxS1JhLH5JKozFL0mFsfglqTAWvyQVxuKXpMJY/JJUGItfkgpj8UtSYSx+"
                    "SSqMxS9JhbH4JakwFr8kFcbil6TCWPySVBiLX5IKY/FLUmEsfkkqjMUvSYWp"
                    "drIoItYCpwObgXNSSttarHkX8BZgHXA18KaU0gMZZ5UkZdD2jH+m9LcDpwAb"
                    "gKEWa14FnAm8CHgacAhwUc5BJUl5dHLGvxfYkFLaHRHb51nzNOCDKaWdABHx"
                    "BeA1eUaEer3O9PR0ru16Ympqar+PK11pecHMpRjkzMPDwy2Pty3+lFId2N1m"
                    "zSfmHHohcH2nw7UzMTGRa6ueq9Vqyz1CT5WWF8xcikHMPD4+3vJ4R9f4FyMi"
                    "Xg68BHhHrj3HxsYG8oy/VqsxMjJCtZr9y9x3SssLZjbz4MqaIiKeD3wGODWl"
                    "tDfXvpVKhUqlkmu7nqpWq/M+3VqJSssLZi7FSsqc7XbOiDgS+BpwRkrph7n2"
                    "lSTllaX4I+JQYCvw7pTStTn2lCQtjQO+1BMRG4FXp5ReT/NWzt8ELouIy2Yt"
                    "e15K6WfdjShJymmo0Wgs9wydGIghZ5ucnGTXrl2Mjo6umOuCCyktL5jZzAPh"
                    "V77vCnzLBkkqjsUvSYWx+CWpMBa/JBXG4pekwlj8klQYi1+SCmPxS1JhLH5J"
                    "KozFL0mFsfglqTAWvyQVxuKXpMJY/JJUGItfkgpj8UtSYSx+SSqMxS9JhbH4"
                    "JakwFr8kFcbil6TCWPySVBiLX5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG"
                    "4pekwlj8klSYaieLImItcDqwGTgnpbStxZozgPcCTwa+BZydUnok36iSpBza"
                    "nvHPlP524BRgAzDUYs0ocCnwKmAcOAJ4e85BJUl5dHLGvxfYkFLaHRHb51lz"
                    "CnBtSulWgIj4NHAe8MEcQ9brdaanp3Ns1TNTU1P7fVzpSssLZi7FIGceHh5u"
                    "ebxt8aeU6sDuNsvWA7+Y9fgummf9WUxMTOTaqudqtdpyj9BTpeUFM5diEDOP"
                    "j4+3PN7RNf4OrAHqsx5PAQdl2puxsbGBPOOv1WqMjIxQreb6Mvev0vKCmc08"
                    "uHKleHTOXhVgMtPeVCoVKpVKru16qlqtzvt0ayUqLS+YuRQrKXOu2znvAo6c"
                    "9Xg9cHemvSVJGeU6478K+HhEHA/8CDgbuDLT3pKkjA74jD8iNkbE5QAppTuB"
                    "NwNfBHbSfAbw4SwTSpKyGmo0Gss9QycGYsjZJicn2bVrF6OjoyvmuuBCSssL"
                    "ZjbzQPiV77sC37JBkopj8UtSYfr+ptSIWH3BBRcs9xiLNjU1xf3338/q1atX"
                    "zL2/CyktL5jZzP1vy5Ytvw5sTyk9Nvv4IKR4xpYtW5Z7BkkaRD8BjgFun31w"
                    "EIp/O83BJUmLt33ugUG5q0eSlIkv7kpSYSx+SSqMxS9JhbH4JakwFr8kFcbi"
                    "l6TCWPySVBiLX5IKY/FLUmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwgzC+/H3"
                    "rYg4A3gv8GTgW8DZKaVHDmRdRHwWOCGl9NwlHrsr3WaOiHXApcDLgWngH1NK"
                    "F/Zm+s5FxCnAx4D1wPeAM1NK93S6JiICeCuwGvhX4IKUUr13CRavm8wRUQX+"
                    "FvhjYBj4KvCWlNJkDyMsWrd/z7PWXARESmltTwbvkmf8BygiRmkW2KuAceAI"
                    "4O0Hsi4iTgJevcQjdy1T5r8G1gHPBE4A3hARpy358IsQEWuAL9As7iOAe4H3"
                    "d7omIk4E3ga8CHgucDLwRz0a/4B0m5lm3hNo5j0GOA44uxezH6gMmR9fcxTN"
                    "/APD4j9wpwDXppRuTSk9DHwaeNli10VEBfgkcHEPZu5WjsyHAB9IKT2cUtoJ"
                    "XEX//YS1E4GdKaXvppQepfmf2NycC605FfhSSmlnSule4J9a/P5+023mpwB/"
                    "k1L6ZUrpl8DX6b+/17m6zfy4S4EPL/m0GXmp58CtB34x6/FdNM8IFrvubcD/"
                    "ADcCr8s8Y25dZ04pvenxgzP/6Z0IfCb7pN3pJOdCa9YDP5/zuVMzz5hbV5lb"
                    "XK57IfDZzDPm1u3fMxGxETgYuALou0uW87H425gppx1zDt8BXAnMvmY7BRzU"
                    "Yos1862LiPXAecDxwG/kmbh7S5l5jg8AP0gpff/Ap10SreZfvYg1nebvJ91m"
                    "fkJEnE3zmd2XMs+YW1eZI+LXgC3AK5dwxiVh8bcx84Lc2NzjEfEX7P/1qwCt"
                    "Xsh6dIF1HwG2zLw4lmfgDJY48+N7vYnmWfCLup13CbSaf2oRa9rm70PdZgYg"
                    "Ik4F3gWclFLq9x/o3W3m9wBfTyn9OCKesVRDLgWv8R+4u4AjZz1eD9zd6bqZ"
                    "s/1XAx+OiH3Ad4DnRMS+mTPuftRV5scfRMTvA+8GXpZS2rMEc3ark5wLren0"
                    "69RPus1MRDwf+HvgFSmlu5ZmzKy6zfx24G0z/35/Ahwy8+/3qCWaNxvP+A/c"
                    "VcDHI+J44Ec072C4stN1M/8whh9fFBEvBj7R57dzdpUZICKOBf6OZun3aznc"
                    "BBwxc7fRlTTv6Jibc6E13wb+LSI+CtwHvJH+f/Gvq8wRMQZ8GXhdSulHPZu6"
                    "O11lTikd8viimTP+H3o75wqXUroTeDPwRWAnzTODD0PzBZ+IuLzdukGTKfP7"
                    "aF5G+q+I2DPz6yc9DdJGSmkvcDqQaL6wdzjNW/OPj4hrF1oz87mbgA8B1wH/"
                    "C1xN817+vtVtZuAC4BnAt2f9ve7p42evOTIPrKFGo98vw0mScvKMX5IKY/FL"
                    "UmEsfkkqjMUvSYWx+CWpMBa/JBXG4pekwlj8klSY/wPTNSCZbt4GgAAAAABJ"
                    "RU5ErkJggg==\n",
                    "text/plain": "<Figure size 432x288 with 1 Axes>",
                },
                "metadata": {"needs_background": "light"},
                "output_type": "display_data",
            },
        ],
        "source": "",
    }
    tempfile_path = get_tempfile_path("")
    with disable_capture:
        output = rich_output(image_cell, images=False)
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[1]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[1]:\x1b[0m  "
        "<AxesSubplot:>                          "
        "                                  \n     "
        "                                        "
        "                                   \n    "
        f"  \x1b]8;id=236660;file://{tempfile_path}2.png"
        "\x1b\\\x1b[94m🖼 Click to vie"
        "w Image\x1b[0m\x1b]8;;\x1b\\                      "
        "                               \n        "
        "                                        "
        "                                \n      <"
        "Figure size 432x288 with 1 Axes>        "
        "                                 \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_svg_link(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a link to an image."""
    svg_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "1a2e22b6-ae2b-4c0c-a8db-ec0c0ea1227b",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "image/svg+xml": (
                        '<?xml version="1.0" encoding="UTF-8" sta'
                        'ndalone="no"?>\n<!DOCTYPE svg PUBLIC "-//'
                        'W3C//DTD SVG 1.1//EN"\n "http://www.w3.or'
                        'g/Graphics/SVG/1.1/DTD/svg11.dtd">\n<!-- '
                        "Generated by graphviz version 2.47.2 (20"
                        "210527.0053)\n -->\n<!-- Pages: 1 -->\n<svg"
                        ' width="514pt" height="44pt"\n viewBox="0'
                        '.00 0.00 513.94 44.00" xmlns="http://www'
                        '.w3.org/2000/svg" xmlns:xlink="http://ww'
                        'w.w3.org/1999/xlink">\n<g id="graph0" cla'
                        'ss="graph" transform="scale(1 1) rotate('
                        '0) translate(4 40)">\n<polygon fill="whit'
                        'e" stroke="transparent" points="-4,4 -4,'
                        '-40 509.94,-40 509.94,4 -4,4"/>\n<!-- A -'
                        '->\n<g id="node1" class="node">\n<title>A<'
                        '/title>\n<ellipse fill="none" stroke="bla'
                        'ck" cx="53.95" cy="-18" rx="53.89" ry="1'
                        '8"/>\n<text text-anchor="middle" x="53.95'
                        '" y="-14.3" font-family="Times,serif" fo'
                        'nt-size="14.00">King Arthur</text>\n</g>\n'
                        '<!-- B -->\n<g id="node2" class="node">\n<'
                        'title>B</title>\n<ellipse fill="none" str'
                        'oke="black" cx="215.95" cy="-18" rx="90.'
                        '18" ry="18"/>\n<text text-anchor="middle"'
                        ' x="215.95" y="-14.3" font-family="Times'
                        ',serif" font-size="14.00">Sir Bedevere t'
                        'he Wise</text>\n</g>\n<!-- L -->\n<g id="no'
                        'de3" class="node">\n<title>L</title>\n<ell'
                        'ipse fill="none" stroke="black" cx="414.'
                        '95" cy="-18" rx="90.98" ry="18"/>\n<text '
                        'text-anchor="middle" x="414.95" y="-14.3'
                        '" font-family="Times,serif" font-size="1'
                        '4.00">Sir Lancelot the Brave</text>\n</g>'
                        "\n</g>\n</svg>\n"
                    ),
                    "text/plain": "<graphviz.dot.Digraph at 0x108eb9430>",
                },
                "execution_count": 2,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    output = rich_output(svg_cell)
    tempfile_path = get_tempfile_path("")
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        f"\x1b]8;id=1627259094.976956-618609;file://{tempfile_path}2.svg"
        "\x1b\\\x1b[9"
        "4m🖼 Click to view Image\x1b[0m\x1b]8;;\x1b\\      "
        "                                        "
        "       \n                                "
        "                                        "
        "        \n\x1b[38;5;247m[2]:\x1b[0m  <graphviz."
        "dot.Digraph at 0x108eb9430>             "
        "                        \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_unknown_language() -> None:
    """It sets the language to Python when it cannot be parsed."""
    notebook_node = nbformat.from_dict(
        {
            "cells": [],
            "metadata": {},
            "nbformat": 4,
            "nbformat_minor": 5,
        }
    )
    rendered_notebook = notebook.Notebook(notebook_node)
    expected_output = "python"
    acutal_output = rendered_notebook.language
    assert acutal_output == expected_output
