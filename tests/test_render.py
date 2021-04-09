"""Test cases for render."""
import io
import sys
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional

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
        cell: Dict[str, Any],
        plain: bool = False,
        no_wrap: bool = False,
    ) -> str:
        """Callable types."""
        ...


def split_string(string: str, sub_length: int = 30) -> List[str]:
    """Split a string into subsections less than or equal to new length.

    Args:
        string (str): The long string to split up.
        sub_length (int): The maximum length of the subsections.
            Defaults to 56.

    Returns:
        List[str]: The string split into sections.
    """
    string_length = len(string)
    return [
        string[begin : begin + sub_length]
        for begin in range(0, string_length, sub_length)
    ]


@pytest.fixture()
def rich_console() -> Console:
    """Fixture that returns Rich console."""
    con = console.Console(
        file=io.StringIO(),
        width=80,
        color_system="truecolor",
        legacy_windows=False,
    )
    return con


@pytest.fixture()
def rich_output(
    rich_console: Console,
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode],
) -> Callable[..., str]:
    """Fixture returning a function that returns the rendered output.

    Args:
        rich_console (Console): Pytest fixture that returns a rich
            console.
        make_notebook (Callable[[Optional[Dict[str, Any]]], NotebookNode]):
            A fixture that creates a notebook node.

    Returns:
        Callable[..., str]: The output generating function.
    """

    def _rich_output(
        cell: Dict[str, Any],
        plain: bool = False,
        no_wrap: bool = False,
    ) -> str:
        """Return the rendered output of a notebook containing the cell.

        Args:
            cell (Dict[str, Any]): The cell of the notebook to render.
            plain (bool): Whether to render the notebook in a
                plain style, with no boxes or decorations. Defaults to
                False.
            no_wrap (bool): Disable word wrapping. Defaults to False.

        Returns:
            str: The rich output as a string.
        """
        notebook_node = make_notebook(cell)
        notebook = render.Notebook(notebook_node, plain=plain)
        rich_console.print(notebook, no_wrap=no_wrap)
        output: str = rich_console.file.getvalue()  # type: ignore[attr-defined]
        return output

    return _rich_output


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
        "                   \n \x1b[1mdolor"
        "\x1b[0m \x1b[3msit\x1b[0m \x1b[97;40mamet\x1b"
        "[0m                           "
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
        "\x1b[38;5;247m    \x1b[0m ╭─────────"
        "──────────────────────────────"
        "──────────────────────────────"
        "────╮\n\x1b[38;5;247m[2]:\x1b[0m │ \x1b["
        "94;49mdef\x1b[0m\x1b[49m \x1b[0m\x1b[92;49"
        "mfoo\x1b[0m\x1b[49m(\x1b[0m\x1b[49mx\x1b[0m\x1b["
        "49m:\x1b[0m\x1b[49m \x1b[0m\x1b[96;49mfloa"
        "t\x1b[0m\x1b[49m,\x1b[0m\x1b[49m \x1b[0m\x1b[49m"
        "y\x1b[0m\x1b[49m:\x1b[0m\x1b[49m \x1b[0m\x1b[96;"
        "49mfloat\x1b[0m\x1b[49m)\x1b[0m\x1b[49m \x1b["
        "0m\x1b[49m-\x1b[0m\x1b[49m>\x1b[0m\x1b[49m \x1b["
        "0m\x1b[96;49mfloat\x1b[0m\x1b[49m:\x1b[0m "
        "                              "
        "    │\n     │ \x1b[49m    \x1b[0m\x1b[94"
        ";49mreturn\x1b[0m\x1b[49m \x1b[0m\x1b[49mx"
        "\x1b[0m\x1b[49m \x1b[0m\x1b[49m+\x1b[0m\x1b[49m "
        "\x1b[0m\x1b[49my\x1b[0m                "
        "                              "
        "          │\n     ╰────────────"
        "──────────────────────────────"
        "──────────────────────────────"
        "─╯\n"
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
        "\x1b[38;5;247m    \x1b[0m ╭─────────"
        "─────╮\n\x1b[38;5;247m[3]:\x1b[0m │ \x1b"
        "[49m%%\x1b[0m\x1b[94;49mbash\x1b[0m    "
        "   │\n     │ \x1b[96;49mecho\x1b[0m\x1b["
        "49m \x1b[0m\x1b[33;49m'lorep'\x1b[0m │\n"
        "     │              │\n     ╰──"
        "────────────╯\n"
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
        "\x1b[38;5;247m    \x1b[0m ╭─────────"
        "──────────────────────────────"
        "──────────────────────────────"
        "────╮\n\x1b[38;5;247m[3]:\x1b[0m │ \x1b["
        "49m%%time\x1b[0m\x1b[49mit\x1b[0m      "
        "                              "
        "                            │\n"
        "     │ \x1b[94;49mdef\x1b[0m\x1b[49m \x1b["
        "0m\x1b[92;49mfoo\x1b[0m\x1b[49m(\x1b[0m\x1b[4"
        "9mx\x1b[0m\x1b[49m:\x1b[0m\x1b[49m \x1b[0m\x1b[9"
        "6;49mfloat\x1b[0m\x1b[49m,\x1b[0m\x1b[49m "
        "\x1b[0m\x1b[49my\x1b[0m\x1b[49m:\x1b[0m\x1b[49m "
        "\x1b[0m\x1b[96;49mfloat\x1b[0m\x1b[49m)\x1b[0"
        "m\x1b[49m \x1b[0m\x1b[49m-\x1b[0m\x1b[49m>\x1b[0"
        "m\x1b[49m \x1b[0m\x1b[96;49mfloat\x1b[0m\x1b["
        "49m:\x1b[0m                      "
        "             │\n     │ \x1b[49m   "
        " \x1b[0m\x1b[94;49mreturn\x1b[0m\x1b[49m \x1b"
        "[0m\x1b[49mx\x1b[0m\x1b[49m \x1b[0m\x1b[49m+\x1b"
        "[0m\x1b[49m \x1b[0m\x1b[49my\x1b[0m       "
        "                              "
        "                   │\n     ╰───"
        "──────────────────────────────"
        "──────────────────────────────"
        "──────────╯\n"
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
