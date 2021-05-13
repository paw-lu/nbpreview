"""Test cases for render."""
import io
import sys
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import Union

import pytest
from nbformat import NotebookNode
from rich import console
from rich.console import Console

from nbpreview import render

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

        Returns:
            str: The rich output as a string.
        """
        notebook_node = make_notebook(cell)
        notebook = render.Notebook(
            notebook_node,
            plain=plain,
            unicode=unicode,
            hide_output=hide_output,
            nerd_font=nerd_font,
        )
        rich_console.print(notebook, no_wrap=no_wrap)
        output: str = rich_console.file.getvalue()  # type: ignore[attr-defined]
        return output

    return _rich_output


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
    notebook = render.Notebook(notebook_node)
    con.print(notebook)
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
