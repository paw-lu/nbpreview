"""Test cases for render."""
import io
import json
import os
import pathlib
import re
import sys
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generator
from typing import Optional
from typing import Tuple
from typing import Union
from unittest.mock import Mock

import httpx
import pytest
from nbformat import NotebookNode
from pytest_mock import MockerFixture
from rich import console
from rich.console import Console

from nbpreview import notebook


if sys.version_info >= (3, 8):
    from typing import Protocol
else:  # pragma: no cover
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
    ) -> str:
        """Callable types."""
        ...


def split_string(string: str, sub_length: int = 40) -> Tuple[str, ...]:
    """Split a string into subsections less than or equal to new length.

    Args:
        string (str): The long string to split up.
        sub_length (int): The maximum length of the subsections.
            Defaults to 56.

    Returns:
        Tuple[str]: The string split into sections.
    """
    string_length = len(string)
    return tuple(
        string[begin : begin + sub_length]
        for begin in range(0, string_length, sub_length)
    )


@pytest.fixture()
def rich_console() -> Console:
    """Fixture that returns Rich console."""
    con = console.Console(
        file=io.StringIO(),
        width=80,
        color_system="truecolor",
        legacy_windows=False,
        force_terminal=True,
    )
    return con


@pytest.fixture()
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
    ) -> str:
        """Return the rendered output of a notebook containing the cell.

        Args:
            cell (Union[Dict[str, Any], None]): The cell of the notebook to render.
            plain (bool): Whether to render the notebook in a
                plain style, with no boxes or decorations. Defaults to
                False.
            no_wrap (bool): Disable word wrapping. Defaults to False.
            unicode (bool): Whether to render using unicode characters.
            hide_output (bool): Do not render the notebook outputs. By
                default False.
            nerd_font (bool): Use nerd fonts when appropriate. By default
                False.
            files (bool): Create files when needed to render HTML content.
            hyperlinks (bool): Whether to use hyperlinks. If false will
                explicitly print out path.
            hide_hyperlink_hints (bool): Hide text hints of when content is
                clickable.

        Returns:
            str: The rich output as a string.
        """
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
        )
        rich_console.print(rendered_notebook, no_wrap=no_wrap)
        output: str = rich_console.file.getvalue()  # type: ignore[attr-defined]
        return output

    return _rich_output


@pytest.fixture
def tempfile_path() -> Path:
    """Create the path for the temp file."""
    file_path = pathlib.Path(__file__).parent / pathlib.Path("link_file.html")
    return file_path


@pytest.fixture
def mock_tempfile_file(
    mocker: MockerFixture, tempfile_path: Path
) -> Generator[Mock, None, None]:
    """Control where tempfile will write to."""
    fd = os.open(tempfile_path, flags=2818, mode=0o600)
    mock = mocker.patch("tempfile._mkstemp_inner")
    mock.return_value = (fd, str(tempfile_path))
    yield mock
    tempfile_path.unlink()


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


def test_render_dataframe(rich_output: RichOutput) -> None:
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
    expected_output = (
        "     ╭────────────────────────"
        "──────────────────────────────"
        "───────────────────╮\n\x1b[38;5;24"
        "7m[2]:\x1b[0m │                  "
        "                              "
        "                         │\n   "
        "  ╰───────────────────────────"
        "──────────────────────────────"
        "────────────────╯\n            "
        "                              "
        "                              "
        "        \n\x1b[38;5;247m[2]:\x1b[0m  "
        " \x1b[1m     \x1b[0m   \x1b[1m      \x1b[0"
        "m   \x1b[1mlorep\x1b[0m        \x1b[1m "
        "          hey\x1b[0m   \x1b[1mbye\x1b[0"
        "m                       \n     "
        "  \x1b[1m     \x1b[0m   \x1b[1m      \x1b["
        "0m   \x1b[1mipsum\x1b[0m   \x1b[1mhi\x1b[0"
        "m   \x1b[1mvery_long_word\x1b[0m   \x1b"
        "[1m hi\x1b[0m                    "
        "   \n       \x1b[1mfirst\x1b[0m   \x1b[1"
        "msecond\x1b[0m   \x1b[1mthird\x1b[0m   "
        "\x1b[1m  \x1b[0m   \x1b[1m             "
        " \x1b[0m   \x1b[1m   \x1b[0m           "
        "            \n      ───────────"
        "──────────────────────────────"
        "───────────                   "
        "   \n       \x1b[1m  bar\x1b[0m   \x1b[1"
        "m   one\x1b[0m   \x1b[1m    1\x1b[0m   "
        " 1                2     4     "
        "                  \n           "
        "             \x1b[1m   10\x1b[0m    "
        "3                4    -1      "
        "                 \n            "
        "   \x1b[1m three\x1b[0m   \x1b[1m    3\x1b"
        "[0m    3                4    -"
        "1                       \n     "
        "  \x1b[1m  foo\x1b[0m   \x1b[1m   one\x1b["
        "0m   \x1b[1m    1\x1b[0m    3       "
        "         4    -1              "
        "         \n"
    )
    output = rich_output(code_cell)
    assert output == expected_output


def test_render_plain_dataframe(rich_output: RichOutput) -> None:
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
    expected_output = (
        "                              "
        "                              "
        "                    \n         "
        "                              "
        "                              "
        "           \nlorep             "
        " hey                bye       "
        "                              "
        "  \nipsum               hi very"
        "_long_word  hi                "
        "                       \nfirst "
        "second third                  "
        "                              "
        "              \nbar   one    1 "
        "      1              2   4    "
        "                              "
        "     \n             10      3  "
        "            4  -1             "
        "                          \n   "
        "   three  3       3           "
        "   4  -1                      "
        "                 \nfoo   one   "
        " 1       3              4  -1 "
        "                              "
        "        \n"
    )
    output = rich_output(code_cell, plain=True)
    assert output == expected_output


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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b[48;5;174m<ipython-input-5-bc08279b5148"
        ">:2: UserWarning: Lorep                 "
        "     \x1b[0m\n      \x1b[48;5;174m warnings.war"
        'n("Lorep")                              '
        "                     \x1b[0m\n      \x1b[48;5;1"
        "74m                                     "
        "                                     \x1b[0"
        "m\n"
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
        "     ╭────────────────────────"
        "──────────────────────────────"
        "───────────────────╮\n\x1b[38;5;24"
        "7m[6]:\x1b[0m │                  "
        "                              "
        "                         │\n   "
        "  ╰───────────────────────────"
        "──────────────────────────────"
        "────────────────╯\n            "
        "                              "
        "                              "
        "        \n\x1b[38;5;247m    \x1b[0m  "
        "Lorep                         "
        "                              "
        "              \n               "
        "                              "
        "                              "
        "     \n"
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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b[49m\x1b[1;31m----------------------------"
        "---------------------------------------…"
        "\x1b[0m\n                                   "
        "                                        "
        "     \n\x1b[38;5;247m    \x1b[0m  \x1b[49m\x1b[1;31mZ"
        "eroDivisionError\x1b[0m                    "
        "     Traceback (most recent…\x1b[0m\n       "
        "                                        "
        "                                 \n\x1b[38;5"
        ";247m    \x1b[0m  \x1b[49m\x1b[1;32m<ipython-inpu"
        "t-7-9e1622b385b6>\x1b[0m in \x1b[0;36m<module>"
        "\x1b[1;34m\x1b[0m\x1b[0m        \n      \x1b[49m\x1b[1;3"
        "2m----> 1\x1b[1;33m \x1b[1;36m1\x1b[0m\x1b[1;33m/\x1b[0"
        "m\x1b[1;36m0\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\x1b"
        "[0m   \n      \x1b[49m\x1b[0m\x1b[0m              "
        "                                        "
        "                 \n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b[49m\x1b[1;31mZeroDivisionError\x1b[0m: divis"
        "ion by zero\x1b[0m                         "
        "     \n"
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
        "────────────────╯\n"
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
        "                            \n\x1b[38;5;247m"
        "    \x1b[0m  \x1b[1mLorep\x1b[0m \x1b[3mipsum\x1b[0m   "
        "                                        "
        "                    \n"
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
        "                  \n\x1b[38;5;247m     \x1b[0m "
        "                                        "
        "                                  \n     "
        "                                        "
        "                                   \n    "
        "       α∼Normal                         "
        "                                    \n   "
        "        β∼Normal                        "
        "                                     \n  "
        "         ϵ∼Half-Cauchy                  "
        "                                      \n "
        "          μ = α + Xβ                    "
        "                                       \n"
        "           y ∼Normal(μ, ϵ)              "
        "                                        "
        "\n                                       "
        "                                        "
        " \n                                      "
        "                                        "
        "  \n"
    )
    output = rich_output(latex_output_cell)
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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "Lorep ipsum                             "
        "                                  \n"
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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "📄                                       "
        "                                 \n"
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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\uf1c1                                       "
        "                                  \n"
    )
    output = rich_output(pdf_output_cell, nerd_font=True)
    assert output == expected_output


def test_vega_output(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[3]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b]8;id=1621482145.367022-895901;file://"
        f"{tempfile_path}\x1b\\\x1b[94m\uf080 Click to v"
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
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b]8;id=1621207824.060063-456106;file://"
        f"{tempfile_path}\x1b\\\x1b[94m\uf080 Click to v"
        "iew Vega chart\x1b[0m\x1b]8;;\x1b\\               "
        "                                 \n"
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
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b]8;id=1621211531.6504052-691935;file://"
        f"{tempfile_path}\x1b\\\x1b[94m\uf080 \x1b[0m\x1b]8;;"
        "\x1b\\                                      "
        "                                  \n"
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
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b]8;id=1621208043.989405-275090;file://"
        f"{tempfile_path}\x1b\\\x1b[94m📊 Click to v"
        "iew Vega chart\x1b[0m\x1b]8;;\x1b\\               "
        "                                \n"
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
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b]8;id=1621208210.565259-404317;file://"
        f"{tempfile_path}\x1b\\\x1b[94mClick to vie"
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
    tempfile_path: Path,
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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "📊 Vega chart                            "
        "                                 \n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=False,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=True,
    )
    assert not tempfile_path.read_text()
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_write_vega_output(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    tempfile_path: Path,
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
    rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    file_contents = tempfile_path.read_text()
    assert file_contents == expected_contents


def test_vega_no_icon_no_message(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "\x1b]8;id=1621214780.000055-278457;file://"
        f"{tempfile_path}\x1b\\\x1b[94mVega chart\x1b["
        "0m\x1b]8;;\x1b\\                               "
        "                                 \n"
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
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
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
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        f"📊 {tempfile_path}         \n"
    )
    output = rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=False,
        hide_hyperlink_hints=True,
        unicode=True,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vega_url(
    rich_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    mocker: MockerFixture,
    tempfile_path: Path,
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
    rich_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
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
        "                  \n\x1b[38;5;247m    \x1b[0m  "
        "Vega chart                              "
        "                                  \n"
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
