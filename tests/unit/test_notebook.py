"""Test cases for render."""
import dataclasses
import io
import json
import os
import pathlib
import re
import textwrap
from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any, ContextManager, Protocol
from unittest.mock import Mock

import httpx
import nbformat
import pytest
from _pytest.config import _PluggyPlugin
from _pytest.monkeypatch import MonkeyPatch
from nbformat import NotebookNode
from pytest_mock import MockerFixture
from pytest_snapshot.plugin import Snapshot
from rich import console

from nbpreview import notebook
from nbpreview.component.content.output.result.drawing import ImageDrawing


class RichOutput(Protocol):
    """Typing protocol for _rich_notebook_output."""

    def __call__(
        self,
        cell: dict[str, Any] | None,
        plain: bool = False,
        theme: str = "material",
        no_wrap: bool = False,
        unicode: bool | None = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        negative_space: bool = True,
        hyperlinks: bool = True,
        hide_hyperlink_hints: bool = False,
        images: bool | None = None,
        image_drawing: ImageDrawing | None = None,
        color: bool | None = None,
        relative_dir: Path | None = None,
        line_numbers: bool = False,
        code_wrap: bool = False,
    ) -> str:  # pragma: no cover
        """Callable types."""
        ...


@pytest.fixture
def adjust_for_fallback() -> Callable[[str, int], str]:
    """Fixture to automatically adjust expected outputs for fallback."""

    def _adjust_for_fallback(rendered_output: str, newlines: int) -> str:
        """Add fallback text to end of output if import succeeds."""
        fallback_text = newlines * f"{' ':>80}\n" + (
            "      \x1b[38;2;187;134"
            ";252mImage                              "
            "                                       \x1b"
            "[0m\n"
        )
        adjusted_output = rendered_output + fallback_text
        return adjusted_output

    return _adjust_for_fallback


@dataclasses.dataclass
class LinkFilePathNotFoundError(Exception):
    """No hyperlink filepath found in output."""

    def __post_init__(
        self,
    ) -> None:  # pragma: no cover
        """Constructor."""
        super().__init__("No hyperlink filepath found in output")


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
        # pragma: no cover
        raise LinkFilePathNotFoundError

    return _parse_link_filepath


@pytest.fixture
def rich_notebook_output(
    rich_console: Callable[[Any, bool | None], str],
    make_notebook: Callable[[dict[str, Any] | None], NotebookNode],
) -> RichOutput:
    """Fixture returning a function that returns the rendered output.

    Args:
        rich_console (Callable[[Any, Union[bool, None]], str]): Pytest
            fixture that returns a rich console.
        make_notebook (Callable[[Optional[Dict[str, Any]]], NotebookNode]):
            A fixture that creates a notebook node.

    Returns:
        RichOutput: The output generating function.
    """

    def _rich_notebook_output(
        cell: dict[str, Any] | None,
        plain: bool | None = None,
        theme: str = "material",
        no_wrap: bool | None = None,
        unicode: bool | None = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        negative_space: bool = True,
        hyperlinks: bool = True,
        hide_hyperlink_hints: bool = False,
        images: bool | None = None,
        image_drawing: ImageDrawing | None = None,
        color: bool | None = None,
        relative_dir: Path | None = None,
        line_numbers: bool = False,
        code_wrap: bool = False,
    ) -> str:
        """Render the notebook containing the cell."""
        notebook_node = make_notebook(cell)
        rendered_notebook = notebook.Notebook(
            notebook_node,
            theme=theme,
            plain=plain,
            unicode=unicode,
            hide_output=hide_output,
            nerd_font=nerd_font,
            files=files,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
            images=images,
            image_drawing=image_drawing,
            color=color,
            negative_space=negative_space,
            relative_dir=relative_dir,
            line_numbers=line_numbers,
            code_wrap=code_wrap,
        )
        output = rich_console(rendered_notebook, no_wrap)
        return output

    return _rich_notebook_output


def test_automatic_plain(
    make_notebook: Callable[[dict[str, Any] | None], NotebookNode],
    snapshot_with_dir: Snapshot,
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
    output_file = io.StringIO()
    con = console.Console(
        file=output_file,
        width=80,
        color_system="truecolor",
        legacy_windows=False,
        force_terminal=False,
    )
    notebook_node = make_notebook(code_cell)
    rendered_notebook = notebook.Notebook(notebook_node, theme="material")
    con.print(rendered_notebook)
    output = output_file.getvalue()
    snapshot_with_dir.assert_match(output, "test_automatic_plain.txt")


def test_julia_syntax() -> None:
    """It highlights Julia code."""
    julia_notebook = {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": 2,
                "id": "925471a9-c56e-4e04-8e46-276d62ce00e2",
                "metadata": {},
                "outputs": [
                    {
                        "data": {
                            "text/plain": "printx (generic function with 1 method)"
                        },
                        "execution_count": 2,
                        "metadata": {},
                        "output_type": "execute_result",
                    }
                ],
                "source": (
                    "function printx(x)\n"
                    '    println("x = $x")\n'
                    "    return nothing\n"
                    "end"
                ),
            }
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Julia 1.7.2",
                "language": "julia",
                "name": "julia-1.7",
            },
            "language_info": {
                "file_extension": ".jl",
                "mimetype": "application/julia",
                "name": "julia",
                "version": "1.7.2",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    julia_notebook_node = nbformat.from_dict(  # type: ignore[no-untyped-call]
        julia_notebook
    )
    output_file = io.StringIO()
    con = console.Console(
        file=output_file,
        width=80,
        color_system="truecolor",
        legacy_windows=False,
        force_terminal=False,
    )
    rendered_notebook = notebook.Notebook(julia_notebook_node, theme="material")
    con.print(rendered_notebook)
    output = output_file.getvalue()
    expected_output = (
        "\x1b[38;2;187;128;179;49mfunction\x1b[0m\x1b[38;2"
        ";238;255;255;49m \x1b[0m\x1b[38;2;238;255;255;"
        "49mprintx\x1b[0m\x1b[38;2;137;221;255;49m(\x1b[0m"
        "\x1b[38;2;238;255;255;49mx\x1b[0m\x1b[38;2;137;22"
        "1;255;49m)\x1b[0m                          "
        "                                    \n\x1b[3"
        "8;2;238;255;255;49m    \x1b[0m\x1b[38;2;238;25"
        "5;255;49mprintln\x1b[0m\x1b[38;2;137;221;255;4"
        '9m(\x1b[0m\x1b[38;2;195;232;141;49m"\x1b[0m\x1b[38;2'
        ";195;232;141;49mx = \x1b[0m\x1b[38;2;137;221;2"
        '55;49m$x\x1b[0m\x1b[38;2;195;232;141;49m"\x1b[0m\x1b'
        "[38;2;137;221;255;49m)\x1b[0m              "
        "                                        "
        "     \n\x1b[38;2;238;255;255;49m    \x1b[0m\x1b[38"
        ";2;187;128;179;49mreturn\x1b[0m\x1b[38;2;238;2"
        "55;255;49m \x1b[0m\x1b[38;2;130;170;255;49mnot"
        "hing\x1b[0m                                "
        "                              \n\x1b[38;2;18"
        "7;128;179;49mend\x1b[0m                    "
        "                                        "
        "                 \n                      "
        "                                        "
        "                  \nprintx (generic funct"
        "ion with 1 method)                      "
        "                   \n"
    )
    assert output == expected_output


def test_notebook_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "### Lorep ipsum\n\n**dolor** _sit_ `amet`",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_notebook_markdown_cell.txt")


def test_notebook_latex_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with latex equations."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "### Lorep ipsum\nLorep ipsum doret $\\gamma$ su\n"
        "\n\n$$\ny = \\alpha + \\beta x\n$$\n\nsu ro\n",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_notebook_latex_markdown_cell.txt")


def test_notebook_latex_and_table_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with latex equations and tables."""
    source = textwrap.dedent(
        """\
        # Lorep ipsum

        Hey

        |  a  |  b  |  c  |
        | --- | --- | --- |
        |  1  |  2  |  3  |

        $$
        X \\sim \\mathcal{N}(\\mu,\\,\\sigma^{2})\
        $$

        Hear

        |  a  |  b  |  c  |
        | --- | --- | --- |
        |  1  |  2  |  3  |

        Ehse

        $$
        rmse = \\sqrt{(\frac{1}{n})\\sum_{i=1}^{n}(y_{i} - x_{i})^{2}}
        $$

        Fin
    """
    )
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": source,
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(
        output, "test_notebook_latex_and_table_markdown_cell.txt"
    )


def test_image_link_markdown_cell_request_error(
    rich_notebook_output: RichOutput,
    mocker: MockerFixture,
    remove_link_ids: Callable[[str], str],
) -> None:
    """It falls back to rendering a message if RequestError occurs."""
    mock = mocker.patch("httpx.get", side_effect=httpx.RequestError("Mock"))
    mock.return_value.content = (
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "outline_article_white_48dp.png")
    ).read_bytes()
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Azores](https://github.com/paw-lu/nbpreview/tests/"
        "assets/outline_article_white_48dp.png)",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="braille")
    expected_output = (
        "  \x1b]8;id=724062;https://github.com/paw-l"
        "u/nbpreview/tests/assets/outline_article_white_48dp.png"
        "\x1b\\\x1b[94m🌐 Click "
        "to view Azores\x1b[0m\x1b]8;;\x1b\\               "
        "                                        "
        "\n                                       "
        "                                        "
        " \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_image_link_markdown_cell(
    rich_notebook_output: RichOutput,
    mocker: MockerFixture,
    remove_link_ids: Callable[[str], str],
    expected_output: str,
) -> None:
    """It renders a markdown cell with an image."""
    mock = mocker.patch("httpx.get")
    mock.return_value.content = (
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "outline_article_white_48dp.png")
    ).read_bytes()
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Azores](https://github.com/paw-lu/nbpreview/tests"
        "/assets/outline_article_white_48dp.png)",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="character")
    assert remove_link_ids(output) == expected_output


def test_image_markdown_cell(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    expected_output: str,
) -> None:
    """It renders a markdown cell with an image."""
    image_path = os.fsdecode(
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "outline_article_white_48dp.png")
    )
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"![Azores]({image_path})",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="braille")
    assert remove_link_ids(output) == expected_output


def test_image_path_expansion_markdown_cell(
    rich_notebook_output: RichOutput,
    remove_link_ids: Callable[[str], str],
    monkeypatch: MonkeyPatch,
    tempfile_path: Path,
) -> None:
    """It renders a markdown cell with an image."""
    monkeypatch.setenv("HOME", "/Users/user")
    monkeypatch.setenv("USERPROFILE", "C:\\Users\\username")  # Windows
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![image_link](~/path/image.png)",
    }
    output = rich_notebook_output(markdown_cell)
    file_path = pathlib.Path("~/path/image.png").expanduser()
    expected_output = (
        f"  \x1b]8;id=609045;file://{file_path}"
        "\x1b\\\x1b[94m🖼 Click to view image_li"
        "nk\x1b[0m\x1b]8;;\x1b\\                           "
        "                         \n              "
        "                                        "
        "                          \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_image_path_failed_expansion_markdown_cell(
    rich_notebook_output: RichOutput,
    remove_link_ids: Callable[[str], str],
    monkeypatch: MonkeyPatch,
    tempfile_path: Path,
) -> None:
    """It keeps the image path if it fails to expand it."""
    monkeypatch.setenv("HOME", "~~~")
    monkeypatch.setenv("USERPROFILE", "~~~")  # Windows
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![image_link](~/path/image.png)",
    }
    output = rich_notebook_output(markdown_cell)
    file_path = pathlib.Path("~/path/image.png")
    expected_output = (
        f"  \x1b]8;id=717109;file://{file_path}\x1b"
        "\\\x1b[94m🖼 Click to view image_link\x1b[0m\x1b]8;"
        ";\x1b\\                                     "
        "               \n                        "
        "                                        "
        "                \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_image_markdown_cell_no_drawing(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It renders a markdown cell with an image and skips drawing."""
    image_path = os.fsdecode(
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "outline_article_white_48dp.png")
    )
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"![Azores]({image_path})",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="braille", images=False)
    expected_output = (
        f"  \x1b]8;id=378979;file://{image_path}\x1b\\\x1b[94m"
        "🖼 Click to view Azores\x1b[0m\x1b]8;;\x1b\\       "
        "                                        "
        "         \n                              "
        "                                        "
        "          \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_code_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with code."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "```python\nfor i in range(20):\n    print(i)\n```",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_code_markdown_cell.txt")


def test_table_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with tables."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": """# Hey buddy

*did you hear the news?*

 ```python
for i in range(20):
    print(i)
```

| aaa | bbbb **ccc** |
| --- | --- |
| 111 **222** 333 | 222 |
| susu | lulu|

- so there you are
- words

| ddd | `eeee` fff |
| --- | --- |

| | |
--- | ---
sus | *spect*

rak
     """,
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_table_markdown_cell.txt")


def test_heading_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with headings."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "# Heading 1\n## Heading 2\n### Heading 3\n#### Heading 4\n",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_heading_markdown_cell.txt")


def test_wide_heading_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It reduced the padding if the heading is long."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "# " + "A" * 80,
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_wide_heading_markdown_cell.txt")


def test_ruler_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with a ruler."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "Section 1\n\n---\n\nsection 2\n",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_ruler_markdown_cell.txt")


def test_bullet_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with bullets."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "- Item 1\n- Item 2\n  - Item 3\n",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_bullet_markdown_cell.txt")


def test_number_markdown_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a markdown cell with numbers."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "1. Item 1\n2. Item 2\n3. Item 3\n",
    }
    output = rich_notebook_output(markdown_cell)
    snapshot_with_dir.assert_match(output, "test_number_markdown_cell.txt")


def test_image_file_link_not_image_markdown_cell(
    rich_notebook_output: RichOutput, remove_link_ids: Callable[[str], str]
) -> None:
    """It does not render an image link when file is not an image."""
    bad_path = pathlib.Path(__file__).parent / pathlib.Path("assets", "bad_image.xyz")
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![This is a weird file extension]" f"({bad_path})",
    }
    output = rich_notebook_output(markdown_cell, images=True)
    expected_output = (
        f"  \x1b]8;id=228254;file://{bad_path}\x1b\\\x1b[94m🖼 Click to "
        "view This is a weird file extension\x1b[0m\x1b]8;;\x1b\\       "
        "                         \n              "
        "                                        "
        "                          \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_image_file_link_bad_extension_markdown_cell(
    rich_notebook_output: RichOutput, remove_link_ids: Callable[[str], str]
) -> None:
    """It does not render an image link when extension is unknown."""
    bad_extension_path = __file__
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"![This isn't even a image]({bad_extension_path})",
    }
    output = rich_notebook_output(markdown_cell, images=True)
    expected_output = (
        f"  \x1b]8;id=467471;file://{bad_extension_path}\x1b\\\x1b"
        "[94m🖼 Click"
        " to view This isn't even a image\x1b[0m\x1b]8;;\x1b\\"
        "                  "
        "                     \n                  "
        "                                        "
        "                      \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_image_file_link_not_exist_markdown_cell(
    rich_notebook_output: RichOutput, remove_link_ids: Callable[[str], str]
) -> None:
    """It does not render an image link when the file does not exist."""
    project_dir = pathlib.Path().resolve()
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![This image does not exist](i_do_not_exists.xyz)",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  \x1b]8;"
        f"id=179352;file://{project_dir / 'i_do_not_exists.xyz'}"
        "\x1b\\\x1b[94m🖼 Click to view This image does not "
        "exist\x1b[0m\x1b]8;;\x1b\\                        "
        "             \n                          "
        "                                        "
        "              \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_notebook_code_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a code cell."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    output = rich_notebook_output(code_cell)
    snapshot_with_dir.assert_match(output, "test_notebook_code_cell.txt")


def test_notebook_magic_code_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a code cell in a language specified by cell magic."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "%%bash\necho 'lorep'",
    }
    output = rich_notebook_output(code_cell)
    snapshot_with_dir.assert_match(output, "test_notebook_magic_code_cell.txt")


def test_notebook_raw_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a raw cell as plain text."""
    code_cell = {
        "cell_type": "raw",
        "id": "emotional-amount",
        "metadata": {},
        "source": "Lorep ipsum",
    }
    expected_output = " ╭─────────────╮\n │ Lorep ipsum │\n ╰─────────────╯\n"

    output = rich_notebook_output(code_cell)
    assert output == expected_output


def test_notebook_non_syntax_magic_code_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It uses the default highlighting when magic is not a syntax."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "%%timeit\ndef foo(x: float, y: float) -> float:\n    return x + y",
    }
    output = rich_notebook_output(code_cell)
    snapshot_with_dir.assert_match(
        output, "test_notebook_non_syntax_magic_code_cell.txt"
    )


def test_notebook_plain_code_cell(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a code cell with plain formatting."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    output = rich_notebook_output(code_cell, plain=True)
    snapshot_with_dir.assert_match(output, "test_notebook_plain_code_cell.txt")


def test_render_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(output, "test_render_dataframe.txt")


def test_render_wide_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It enforces a minimum width when rendering wide DataFrame."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 5,
        "id": "8159273d-c026-41eb-9ce1-d65eee43d996",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        "<div>\n"
                        "<style scoped>\n"
                        "    .dataframe tbody tr th:only-of-type {\n"
                        "        vertical-align: middle;\n"
                        "    }\n"
                        "\n"
                        "    .dataframe tbody tr th {\n"
                        "        vertical-align: top;\n"
                        "    }\n"
                        "\n"
                        "    .dataframe thead th {\n"
                        "        text-align: right;\n"
                        "    }\n"
                        "</style>\n"
                        '<table border="1" class="dataframe">\n'
                        "  <thead>\n"
                        '    <tr style="text-align: right;">\n'
                        "      <th></th>\n"
                        "      <th>column_a</th>\n"
                        "      <th>column_b</th>\n"
                        "      <th>column_c</th>\n"
                        "      <th>column_d</th>\n"
                        "      <th>column_e</th>\n"
                        "      <th>column_f</th>\n"
                        "      <th>column_g</th>\n"
                        "      <th>column_h</th>\n"
                        "      <th>column_i</th>\n"
                        "      <th>column_j</th>\n"
                        "      <th>column_k</th>\n"
                        "      <th>column_l</th>\n"
                        "      <th>column_m</th>\n"
                        "      <th>column_n</th>\n"
                        "      <th>column_o</th>\n"
                        "      <th>column_p</th>\n"
                        "    </tr>\n"
                        "  </thead>\n"
                        "  <tbody>\n"
                        "    <tr>\n"
                        "      <th>0</th>\n"
                        "      <td>0.224255</td>\n"
                        "      <td>0.955221</td>\n"
                        "      <td>0.118847</td>\n"
                        "      <td>0.915454</td>\n"
                        "      <td>0.227949</td>\n"
                        "      <td>0.217764</td>\n"
                        "      <td>0.274089</td>\n"
                        "      <td>0.647812</td>\n"
                        "      <td>0.597965</td>\n"
                        "      <td>0.730008</td>\n"
                        "      <td>0.138971</td>\n"
                        "      <td>0.990093</td>\n"
                        "      <td>0.606002</td>\n"
                        "      <td>0.49736</td>\n"
                        "      <td>0.249054</td>\n"
                        "      <td>0.782283</td>\n"
                        "    </tr>\n"
                        "  </tbody>\n"
                        "</table>\n"
                        "</div>"
                    ),
                    "text/plain": (
                        "   column_a  column_b  column_c  column_d"
                        "  column_e  column_f  column_g  \\\n"
                        "0  0.224255  0.955221  0.118847  0.915454"
                        "  0.227949  0.217764  0.274089   \n"
                        "\n"
                        "   column_h column_i  column_j  column_k"
                        "  column_l  column_m  column_n  \\\n"
                        "0  0.647812  0.597965  0.730008  0.138971"
                        "  0.990093  0.606002   0.49736   \n"
                        "\n"
                        "   column_o  column_p  \n"
                        "0  0.249054  0.782283  "
                    ),
                },
                "execution_count": 5,
                "metadata": {},
                "output_type": "execute_result",
            }
        ],
        "source": "",
    }
    output = rich_notebook_output(code_cell)
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[5]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[5]:\x1b[0m  "
        f"\x1b]8;id=757847;file://{tempfile_path}0.html"
        "\x1b\\\x1b[94m🌐 Click to view"
        " HTML\x1b[0m\x1b]8;;\x1b\\                        "
        "                             \n          "
        "                                        "
        "                              \n\x1b[38;5;24"
        "7m[5]:\x1b[0m   \x1b[1m \x1b[0m   \x1b[1mcol…\x1b[0m   "
        "\x1b[1mcol…\x1b[0m   \x1b[1mcol…\x1b[0m   \x1b[1mcol…\x1b["
        "0m   \x1b[1mcol…\x1b[0m   \x1b[1mcol…\x1b[0m   \x1b[1mc"
        "ol…\x1b[0m   \x1b[1mcol…\x1b[0m   \x1b[1mcol…\x1b[0m   "
        "\x1b[1mcol…\x1b[0m  \n      ───────────────────"
        "────────────────────────────────────────"
        "───────────────\n       \x1b[1m0\x1b[0m   0.2… "
        "  0.9…   0.1…   0.9…   0.2…   0.2…   0.2"
        "…   0.6…   0.5…   0.7…  \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_only_header_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It renders a DataFrame with only headers."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        "<div>\\n<style scoped>\\n    .dataframe tb"
                        "ody tr th:only-of-type {\\n        vertic"
                        "al-align: middle;\\n    }\\n\\n    .datafra"
                        "me tbody tr th {\\n        vertical-align"
                        ": top;\\n    }\\n\\n    .dataframe thead tr"
                        " th {\\n        text-align: left;\\n    }\\"
                        "n\\n    .dataframe thead tr:last-of-type "
                        "th {\\n        text-align: right;\\n    }\\"
                        'n</style>\\n<table border="1" class="data'
                        'frame">\\n  <thead>\\n    <tr>\\n      <th>'
                        'Model:</th>\\n      <th colspan="2" halig'
                        'n="left">Decision Tree</th>\\n      <th c'
                        'olspan="2" halign="left">Regression</th>'
                        '\\n      <th colspan="2" halign="left">Ra'
                        "ndom</th>\\n    </tr>\\n    <tr>\\n      <t"
                        "h>Predicted:</th>\\n      <th>Tumour</th>"
                        "\\n      <th>Non-Tumour</th>\\n      <th>T"
                        "umour</th>\\n      <th>Non-Tumour</th>\\n "
                        "     <th>Tumour</th>\\n      <th>Non-Tumo"
                        "ur</th>\\n    </tr>\\n    <tr>\\n      <th>"
                        "Actual Label:</th>\\n      <th></th>\\n   "
                        "   <th></th>\\n      <th></th>\\n      <th"
                        "></th>\\n      <th></th>\\n      <th></th>"
                        "\\n    </tr>\\n  </thead>\\n  <tbody>\\n  </"
                        "tbody>\\n</table>\\n</div>"
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
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        f"\x1b]8;id=360825;file://{tempfile_path}0.html\x1b\\\x1b"
        "[94m🌐 Click to view"
        " HTML\x1b[0m\x1b]8;;\x1b\\                        "
        "                             \n          "
        "                                        "
        "                              \n\x1b[38;5;24"
        "7m[2]:\x1b[0m   \x1b[1m   Model:\x1b[0m          "
        "  \x1b[1m Decision\x1b[0m            \x1b[1mRegre"
        "ssi…\x1b[0m            \x1b[1m   Random\x1b[0m \n "
        "                           \x1b[1m     Tree"
        "\x1b[0m                                    "
        "       \n       \x1b[1mPredicte…\x1b[0m   \x1b[1mT"
        "umour\x1b[0m   \x1b[1mNon-Tumo…\x1b[0m   \x1b[1mTumo"
        "ur\x1b[0m   \x1b[1mNon-Tumo…\x1b[0m   \x1b[1mTumour\x1b"
        "[0m   \x1b[1mNon-Tumo…\x1b[0m \n       \x1b[1m   A"
        "ctual\x1b[0m   \x1b[1m      \x1b[0m   \x1b[1m       "
        "  \x1b[0m   \x1b[1m      \x1b[0m   \x1b[1m         \x1b"
        "[0m   \x1b[1m      \x1b[0m   \x1b[1m         \x1b[0m"
        " \n       \x1b[1m   Label:\x1b[0m              "
        "                                        "
        "          \n      ───────────────────────"
        "────────────────────────────────────────"
        "───────────\n                            "
        "                                        "
        "            \n"
    )
    output = rich_notebook_output(code_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_mistagged_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It doesn't detect a DataFrame when it is not a table."""
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
                        "ext-align: right;\n    }\n</style>\n<not-a-table "
                        'border="1" class="dataframe">\n  <thead>\n'
                        "    <tr>\n      <th>Model:</th>\n      <th"
                        ' colspan="2" halign="left">Decision Tree'
                        '</th>\n      <th colspan="2" halign="left'
                        '">Regression</th>\n      <th colspan="2" '
                        'halign="left">Random</th>\n    </tr>\n    '
                        "<tr>\n      <th>Predicted:</th>\n      <th"
                        ">Tumour</th>\n      <th>Non-Tumour</th>\n "
                        "     <th>Tumour</th>\n      <th>Non-Tumou"
                        "r</th>\n      <th>Tumour</th>\n      <th>N"
                        "on-Tumour</th>\n    </tr>\n    <tr>\n      "
                        "<th>Actual Label:</th>\n      <th></th>\n "
                        "     <th></th>\n      <th></th>\n      <th"
                        "></th>\n      <th></th>\n      <th></th>\n "
                        "   </tr>\n  </thead>\n  <tbody>\n    <tr>\n "
                        "     <th>Tumour (Positive)</th>\n      <t"
                        "d>38.0</td>\n      <td>2.0</td>\n      <td"
                        ">18.0</td>\n      <td>22.0</td>\n      <td"
                        ">21</td>\n      <td>NaN</td>\n    </tr>\n  "
                        "  <tr>\n      <th>Non-Tumour (Negative)</"
                        "th>\n      <td>19.0</td>\n      <td>439.0<"
                        "/td>\n      <td>6.0</td>\n      <td>452.0<"
                        "/td>\n      <td>226</td>\n      <td>232.0<"
                        "/td>\n    </tr>\n  </tbody>\n</not-a-table>\n</div"
                        ">"
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
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        f"\x1b]8;id=806532;file://{tempfile_path}0.html\x1b\\\x1b"
        "[94m🌐 Click to view"
        " HTML\x1b[0m\x1b]8;;\x1b\\                        "
        "                             \n          "
        "                                        "
        "                              \n\x1b[38;5;24"
        "7m[2]:\x1b[0m  lorep              hey      "
        "          bye                           "
        "      \n      ipsum               hi very"
        "_long_word  hi                          "
        "       \n      first second third        "
        "                                        "
        "        \n      bar   one    1       1   "
        "           2   4                        "
        "         \n                   10      3  "
        "            4  -1                       "
        "          \n            three  3       3 "
        "             4  -1                      "
        "           \n      foo   one    1       3"
        "              4  -1                     "
        "            \n"
    )
    output = rich_notebook_output(code_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_multiindex_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It renders a multiindex DataFrame."""
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
                        "    <tr>\n      <th>Model:</th>\n      <th"
                        ' colspan="2" halign="left">Decision Tree'
                        '</th>\n      <th colspan="2" halign="left'
                        '">Regression</th>\n      <th colspan="2" '
                        'halign="left">Random</th>\n    </tr>\n    '
                        "<tr>\n      <th>Predicted:</th>\n      <th"
                        ">Tumour</th>\n      <th>Non-Tumour</th>\n "
                        "     <th>Tumour</th>\n      <th>Non-Tumou"
                        "r</th>\n      <th>Tumour</th>\n      <th>N"
                        "on-Tumour</th>\n    </tr>\n    <tr>\n      "
                        "<th>Actual Label:</th>\n      <th></th>\n "
                        "     <th></th>\n      <th></th>\n      <th"
                        "></th>\n      <th></th>\n      <th></th>\n "
                        "   </tr>\n  </thead>\n  <tbody>\n    <tr>\n "
                        "     <th>Tumour (Positive)</th>\n      <t"
                        "d>38.0</td>\n      <td>2.0</td>\n      <td"
                        ">18.0</td>\n      <td>22.0</td>\n      <td"
                        ">21</td>\n      <td>NaN</td>\n    </tr>\n  "
                        "  <tr>\n      <th>Non-Tumour (Negative)</"
                        "th>\n      <td>19.0</td>\n      <td>439.0<"
                        "/td>\n      <td>6.0</td>\n      <td>452.0<"
                        "/td>\n      <td>226</td>\n      <td>232.0<"
                        "/td>\n    </tr>\n  </tbody>\n</table>\n</div"
                        ">"
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
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        f"\x1b]8;id=888128;file://{tempfile_path}0.html\x1b\\\x1b"
        "[94m🌐 Click to view"
        " HTML\x1b[0m\x1b]8;;\x1b\\                        "
        "                             \n          "
        "                                        "
        "                              \n\x1b[38;5;24"
        "7m[2]:\x1b[0m   \x1b[1m   Model:\x1b[0m          "
        "  \x1b[1m Decision\x1b[0m            \x1b[1mRegre"
        "ssi…\x1b[0m            \x1b[1m   Random\x1b[0m \n "
        "                           \x1b[1m     Tree"
        "\x1b[0m                                    "
        "       \n       \x1b[1mPredicte…\x1b[0m   \x1b[1mT"
        "umour\x1b[0m   \x1b[1mNon-Tumo…\x1b[0m   \x1b[1mTumo"
        "ur\x1b[0m   \x1b[1mNon-Tumo…\x1b[0m   \x1b[1mTumour\x1b"
        "[0m   \x1b[1mNon-Tumo…\x1b[0m \n       \x1b[1m   A"
        "ctual\x1b[0m   \x1b[1m      \x1b[0m   \x1b[1m       "
        "  \x1b[0m   \x1b[1m      \x1b[0m   \x1b[1m         \x1b"
        "[0m   \x1b[1m      \x1b[0m   \x1b[1m         \x1b[0m"
        " \n       \x1b[1m   Label:\x1b[0m              "
        "                                        "
        "          \n      ───────────────────────"
        "────────────────────────────────────────"
        "───────────\n       \x1b[1m   Tumour\x1b[0m    "
        " 38.0         2.0     18.0        22.0  "
        "     21         NaN \n       \x1b[1m(Positiv"
        "…\x1b[0m                                   "
        "                             \n       \x1b[1"
        "mNon-Tumo…\x1b[0m     19.0       439.0     "
        " 6.0       452.0      226       232.0 \n "
        "      \x1b[1m(Negativ…\x1b[0m                 "
        "                                        "
        "       \n"
    )
    output = rich_notebook_output(code_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_styled_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a styled DataFrame."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        '<style type="text/css">\n#T_7cafb_ td:hov'
                        "er {\n  background-color: #ffffb3;\n}\n#T_7"
                        "cafb_ .index_name {\n  font-style: italic"
                        ";\n  color: darkgrey;\n  font-weight: norm"
                        "al;\n}\n#T_7cafb_ th:not(.index_name) {\n  "
                        "background-color: #000066;\n  color: whit"
                        "e;\n}\n#T_7cafb_ .true {\n  background-colo"
                        "r: #e6ffe6;\n}\n#T_7cafb_ .false {\n  backg"
                        "round-color: #ffe6e6;\n}\n</style>\n<table "
                        'id="T_7cafb_">\n  <thead>\n    <tr>\n      '
                        '<th class="index_name level0" >Model:</t'
                        'h>\n      <th class="col_heading level0 c'
                        'ol0" colspan="2">Decision Tree</th>\n    '
                        '  <th class="col_heading level0 col2" co'
                        'lspan="2">Regression</th>\n    </tr>\n    '
                        '<tr>\n      <th class="index_name level1"'
                        ' >Predicted:</th>\n      <th class="col_h'
                        'eading level1 col0" >Tumour</th>\n      <'
                        'th class="col_heading level1 col1" >Non-'
                        'Tumour</th>\n      <th class="col_heading'
                        ' level1 col2" >Tumour</th>\n      <th cla'
                        'ss="col_heading level1 col3" >Non-Tumour'
                        "</th>\n    </tr>\n    <tr>\n      <th class"
                        '="index_name level0" >Actual Label:</th>'
                        '\n      <th class="blank col0" >&nbsp;</t'
                        'h>\n      <th class="blank col1" >&nbsp;<'
                        '/th>\n      <th class="blank col2" >&nbsp'
                        ';</th>\n      <th class="blank col3" >&nb'
                        "sp;</th>\n    </tr>\n  </thead>\n  <tbody>\n"
                        '    <tr>\n      <th id="T_7cafb_level0_ro'
                        'w0" class="row_heading level0 row0" >Tum'
                        'our (Positive)</th>\n      <td id="T_7caf'
                        'b_row0_col0" class="data row0 col0 true '
                        '" >38</td>\n      <td id="T_7cafb_row0_co'
                        'l1" class="data row0 col1 false " >2</td'
                        '>\n      <td id="T_7cafb_row0_col2" class'
                        '="data row0 col2 true " >18</td>\n      <'
                        'td id="T_7cafb_row0_col3" class="data ro'
                        'w0 col3 false " >22</td>\n    </tr>\n    <'
                        'tr>\n      <th id="T_7cafb_level0_row1" c'
                        'lass="row_heading level0 row1" >Non-Tumo'
                        'ur (Negative)</th>\n      <td id="T_7cafb'
                        '_row1_col0" class="data row1 col0 false '
                        '" >19</td>\n      <td id="T_7cafb_row1_co'
                        'l1" class="data row1 col1 true " >439</t'
                        'd>\n      <td id="T_7cafb_row1_col2" clas'
                        's="data row1 col2 false " >6</td>\n      '
                        '<td id="T_7cafb_row1_col3" class="data r'
                        'ow1 col3 true " >452</td>\n    </tr>\n  </'
                        "tbody>\n</table>\n"
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(output, "test_render_styled_dataframe.txt")


def test_render_missing_column_name_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame with a missing column index name."""
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
                        "    <tr>\n      <th></th>\n      <th>lorep"
                        "</th>\n      <th>hey</th>\n      <th>sup</"
                        "th>\n      <th>bye</th>\n    </tr>\n    <tr"
                        ">\n      <th>hey</th>\n      <th></th>\n   "
                        "   <th></th>\n      <th></th>\n      <th><"
                        "/th>\n    </tr>\n  </thead>\n  <tbody>\n    "
                        "<tr>\n      <th>3</th>\n      <th>1</th>\n "
                        "     <td>1</td>\n      <td>4</td>\n      <"
                        "td>6</td>\n    </tr>\n    <tr>\n      <th>4"
                        "</th>\n      <th>1</th>\n      <td>2</td>\n"
                        "      <td>5</td>\n      <td>7</td>\n    </"
                        "tr>\n  </tbody>\n</table>\n</div>"
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(
        output, "test_render_missing_column_name_dataframe.txt"
    )


def test_render_missing_index_name_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame with a missing index index name."""
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
                        "    }\n\n    .dataframe thead th {\n       "
                        " text-align: right;\n    }\n</style>\n<tabl"
                        'e border="1" class="dataframe">\n  <thead'
                        '>\n    <tr style="text-align: right;">\n  '
                        "    <th></th>\n      <th></th>\n      <th>"
                        "a</th>\n      <th>b</th>\n      <th>c</th>"
                        "\n    </tr>\n    <tr>\n      <th></th>\n    "
                        "  <th>hey</th>\n      <th></th>\n      <th"
                        "></th>\n      <th></th>\n    </tr>\n  </the"
                        "ad>\n  <tbody>\n    <tr>\n      <th>3</th>\n"
                        "      <th>1</th>\n      <td>1</td>\n      "
                        "<td>4</td>\n      <td>6</td>\n    </tr>\n  "
                        "  <tr>\n      <th>4</th>\n      <th>1</th>"
                        "\n      <td>2</td>\n      <td>5</td>\n     "
                        " <td>7</td>\n    </tr>\n  </tbody>\n</table"
                        ">\n</div>"
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(
        output, "test_render_missing_index_name_dataframe.txt"
    )


def test_render_missing_last_index_name_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame with missing lasst index index name."""
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
                        "    }\n\n    .dataframe thead th {\n       "
                        " text-align: right;\n    }\n</style>\n<tabl"
                        'e border="1" class="dataframe">\n  <thead'
                        '>\n    <tr style="text-align: right;">\n  '
                        "    <th></th>\n      <th></th>\n      <th>"
                        "a</th>\n      <th>b</th>\n      <th>c</th>"
                        "\n    </tr>\n    <tr>\n      <th>hey</th>\n "
                        "     <th></th>\n      <th></th>\n      <th"
                        "></th>\n      <th></th>\n    </tr>\n  </the"
                        "ad>\n  <tbody>\n    <tr>\n      <th>3</th>\n"
                        "      <th>1</th>\n      <td>1</td>\n      "
                        "<td>4</td>\n      <td>6</td>\n    </tr>\n  "
                        "  <tr>\n      <th>4</th>\n      <th>1</th>"
                        "\n      <td>2</td>\n      <td>5</td>\n     "
                        " <td>7</td>\n    </tr>\n  </tbody>\n</table"
                        ">\n</div>"
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(
        output, "test_render_missing_last_index_name_dataframe.txt"
    )


def test_render_plain_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame as normal when plain is True."""
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
    output = remove_link_ids(rich_notebook_output(code_cell, plain=True))
    snapshot_with_dir.assert_match(output, "test_render_plain_dataframe.txt")


def test_render_uneven_columns_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It renders a DataFrame with missing columns."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        """
                        <style type="text/css">
  \n</style
>\n
<table id="T_aba0a_">
  \n
  <thead>
    \n
    <tr>
      \n
      <th class="index_name level0">Model:</th>
      \n
      <th class="col_heading level0 col0" colspan="2">Decision Tree</th>
      \n
      <th class="col_heading level0 col2" colspan="2">Regression</th>
      \n
    </tr>
    \n
    <tr>
      \n
      <th class="col_heading level1 col0">Tumour</th>
      \n
      <th class="col_heading level1 col1">Non-Tumour</th>
      \n
      <th class="col_heading level1 col2">Tumour</th>
      \n
      <th class="col_heading level1 col3">Non-Tumour</th>
      \n
    </tr>
    \n
    <tr>
      \n
      <th class="index_name level0">Actual Label:</th>
      \n
      <th class="blank col0">&nbsp;</th>
      \n
      <th class="blank col1">&nbsp;</th>
      \n
      <th class="blank col2">&nbsp;</th>
      \n
      <th class="blank col3">&nbsp;</th>
      \n
    </tr>
    \n
  </thead>
  \n
  <tbody>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row0" class="row_heading level0 row0">
        Tumour (Positive)
      </th>
      \n
      <td id="T_aba0a_row0_col0" class="data row0 col0">38</td>
      \n
      <td id="T_aba0a_row0_col1" class="data row0 col1">2</td>
      \n
      <td id="T_aba0a_row0_col2" class="data row0 col2">18</td>
      \n
      <td id="T_aba0a_row0_col3" class="data row0 col3">22</td>
      \n
    </tr>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row1" class="row_heading level0 row1">
        Non-Tumour (Negative)
      </th>
      \n
      <td id="T_aba0a_row1_col0" class="data row1 col0">19</td>
      \n
      <td id="T_aba0a_row1_col1" class="data row1 col1">439</td>
      \n
      <td id="T_aba0a_row1_col2" class="data row1 col2">6</td>
      \n
      <td id="T_aba0a_row1_col3" class="data row1 col3">452</td>
      \n
    </tr>
    \n
  </tbody>
  \n
</table>
\n

                        """
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
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[2]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n\x1b[38;5;247m[2]:\x1b[0m  "
        f"\x1b]8;id=635975;file://{tempfile_path}0.html\x1b\\\x1b"
        "[94m🌐 Click to view"
        " HTML\x1b[0m\x1b]8;;\x1b\\                        "
        "                             \n          "
        "                                        "
        "                              \n\x1b[38;5;24"
        "7m[2]:\x1b[0m   \x1b[1m           Model:\x1b[0m  "
        "              \x1b[1mDecision Tree\x1b[0m     "
        "           \x1b[1mRegression\x1b[0m \n       \x1b["
        "1m           Tumour\x1b[0m   \x1b[1mNon-Tumour"
        "\x1b[0m   \x1b[1m       Tumour\x1b[0m   \x1b[1mNon-T"
        "umour\x1b[0m              \n       \x1b[1m    A"
        "ctual Label:\x1b[0m   \x1b[1m          \x1b[0m   "
        "\x1b[1m             \x1b[0m   \x1b[1m          \x1b["
        "0m   \x1b[1m          \x1b[0m \n      ─────────"
        "────────────────────────────────────────"
        "─────────────────────────\n       \x1b[1mTum"
        "our (Positive)\x1b[0m           38         "
        "      2           18           22 \n     "
        "  \x1b[1m       Non-Tumour\x1b[0m           19"
        "             439            6          4"
        "52 \n       \x1b[1m       (Negative)\x1b[0m    "
        "                                        "
        "            \n"
    )
    output = rich_notebook_output(code_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_no_columns_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame with missing columns."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        """
<style type="text/css">
  \n</style
>\n
<table id="T_aba0a_">
  \n
  <thead>
  </thead>
  \n
  <tbody>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row0" class="row_heading level0 row0">
        Tumour (Positive)
      </th>
      \n
      <td id="T_aba0a_row0_col0" class="data row0 col0">38</td>
      \n
      <td id="T_aba0a_row0_col1" class="data row0 col1">2</td>
      \n
      <td id="T_aba0a_row0_col2" class="data row0 col2">18</td>
      \n
      <td id="T_aba0a_row0_col3" class="data row0 col3">22</td>
      \n
    </tr>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row1" class="row_heading level0 row1">
        Non-Tumour (Negative)
      </th>
      \n
      <td id="T_aba0a_row1_col0" class="data row1 col0">19</td>
      \n
      <td id="T_aba0a_row1_col1" class="data row1 col1">439</td>
      \n
      <td id="T_aba0a_row1_col2" class="data row1 col2">6</td>
      \n
      <td id="T_aba0a_row1_col3" class="data row1 col3">452</td>
      \n
    </tr>
    \n
  </tbody>
  \n
</table>
\n
                        """
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(output, "test_render_no_columns_dataframe.txt")


def test_render_uneven_data_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame with non square data."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        """
<style type="text/css">
  \n</style
>\n
<table id="T_aba0a_">
  \n
  <thead>
  </thead>
  \n
  <tbody>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row0" class="row_heading level0 row0">
        Tumour (Positive)
      </th>
      \n
      <td id="T_aba0a_row0_col1" class="data row0 col1">2</td>
      \n
      <td id="T_aba0a_row0_col2" class="data row0 col2">18</td>
      \n
      <td id="T_aba0a_row0_col3" class="data row0 col3">22</td>
      \n
    </tr>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row1" class="row_heading level0 row1">
        Non-Tumour (Negative)
      </th>
      \n
      <td id="T_aba0a_row1_col0" class="data row1 col0">19</td>
      \n
      <td id="T_aba0a_row1_col1" class="data row1 col1">439</td>
      \n
      <td id="T_aba0a_row1_col2" class="data row1 col2">6</td>
      \n
      <td id="T_aba0a_row1_col3" class="data row1 col3">452</td>
      \n
    </tr>
    \n
  </tbody>
  \n
</table>
\n
                        """
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(output, "test_render_uneven_data_dataframe.txt")


def test_render_uneven_index_dataframe(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a DataFrame with uneven index names."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "mighty-oasis",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": (
                        """
<style type="text/css">
  \n</style
>\n
<table id="T_aba0a_">
  \n
  <thead>
  </thead>
  \n
  <tbody>
    \n
    <tr>
      \n
      <td id="T_aba0a_row0_col1" class="data row0 col1">2</td>
      \n
      <td id="T_aba0a_row0_col2" class="data row0 col2">18</td>
      \n
      <td id="T_aba0a_row0_col3" class="data row0 col3">22</td>
      \n
    </tr>
    \n
    <tr>
      \n
      <th id="T_aba0a_level0_row1" class="row_heading level0 row1">
        Non-Tumour (Negative)
      </th>
      \n
      <td id="T_aba0a_row1_col0" class="data row1 col0">19</td>
      \n
      <td id="T_aba0a_row1_col1" class="data row1 col1">439</td>
      \n
      <td id="T_aba0a_row1_col2" class="data row1 col2">6</td>
      \n
      <td id="T_aba0a_row1_col3" class="data row1 col3">452</td>
      \n
    </tr>
    \n
  </tbody>
  \n
</table>
\n

                        """
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
    output = remove_link_ids(rich_notebook_output(code_cell))
    snapshot_with_dir.assert_match(output, "test_render_uneven_index_dataframe.txt")


def test_render_result(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(output_cell)
    snapshot_with_dir.assert_match(output, "test_render_result.txt")


def test_render_unknown_data_format(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(output_cell)
    snapshot_with_dir.assert_match(output, "test_render_unknown_data_format.txt")


def test_render_error_no_traceback(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(traceback_cell)
    snapshot_with_dir.assert_match(output, "test_render_error_no_traceback.txt")


def test_render_markdown_output(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(markdown_output_cell)
    snapshot_with_dir.assert_match(output, "test_render_markdown_output.txt")


def test_render_unknown_display_data(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(unknown_display_data_cell)
    snapshot_with_dir.assert_match(output, "test_render_unknown_display_data.txt")


def test_render_json_output(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(json_output_cell)
    snapshot_with_dir.assert_match(output, "test_render_json_output.txt")


def test_render_latex_output(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(latex_output_cell)
    assert expected_output == output


def test_render_invalid_latex_output(rich_notebook_output: RichOutput) -> None:
    """It renders invalid LaTeX output."""
    latex_output_cell = {
        "cell_type": "code",
        "execution_count": 15,
        "id": "sapphire-harmony",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/latex": r"garbledmess \sef{}",
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
        "                  \n       garbledmess   "
        "                                        "
        "                   \n"
    )
    output = rich_notebook_output(latex_output_cell)
    assert expected_output == output


def test_render_latex_output_no_unicode(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(latex_output_cell, unicode=False)
    assert expected_output == output


def test_render_text_display_data(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(text_display_data_cell)
    snapshot_with_dir.assert_match(output, "test_render_text_display_data.txt")


def test_pdf_emoji_output(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(pdf_output_cell, unicode=True)
    assert output == expected_output


def test_pdf_nerd_output(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(pdf_output_cell, nerd_font=True)
    assert output == expected_output


def test_pdf_no_unicode_no_nerd(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(pdf_output_cell, unicode=False, nerd_font=False)
    snapshot_with_dir.assert_match(output, "test_pdf_no_unicode_no_nerd.txt")


def test_vega_output(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
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
    output = rich_notebook_output(
        vega_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    output = remove_link_ids(output)
    snapshot_with_dir.assert_match(output, "test_vega_output.txt")


def test_invalid_vega_output(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a hyperlink to an invalid Vega plot."""
    vega_output_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "metadata": {"tags": []},
        "outputs": [
            {
                "data": {
                    "application/vnd.vega.v5+json": {
                        "invalid": "no",
                    },
                },
                "metadata": {},
                "output_type": "display_data",
            }
        ],
        "source": "",
    }
    output = rich_notebook_output(
        vega_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    output = remove_link_ids(output)
    snapshot_with_dir.assert_match(output, "test_invalid_vega_output.txt")


def test_vegalite_output(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    adjust_for_fallback: Callable[[str, int], str],
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
        "                  \n      \x1b]8;id=304082;f"
        f"ile://{tempfile_path}0.h"
        "tml\x1b\\\x1b[94m\uf080 Click to view Vega chart\x1b[0m"
        "\x1b]8;;\x1b\\                                 "
        "               \n"
    )
    adjusted_expected_output = adjust_for_fallback(expected_output, 1)
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    assert remove_link_ids(output) == remove_link_ids(adjusted_expected_output)


def test_vegalite_output_no_hints(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    adjust_for_fallback: Callable[[str, int], str],
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
        "                  \n      \x1b]8;id=90200;fi"
        f"le://{tempfile_path}0.ht"
        "ml\x1b\\\x1b[94m\uf080 \x1b[0m\x1b]8;;\x1b\\                  "
        "                                        "
        "              \n"
    )
    adjusted_expected_output = adjust_for_fallback(expected_output, 1)
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=True,
    )
    assert remove_link_ids(output) == remove_link_ids(adjusted_expected_output)


def test_vegalite_output_no_nerd_font(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    adjust_for_fallback: Callable[[str, int], str],
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
        "                  \n      \x1b]8;id=2129;fil"
        f"e://{tempfile_path}0.htm"
        "l\x1b\\\x1b[94m📊 Click to view Vega chart\x1b[0m\x1b]"
        "8;;\x1b\\                                   "
        "            \n"
    )
    adjusted_expected_output = adjust_for_fallback(expected_output, 1)
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    assert remove_link_ids(output) == remove_link_ids(adjusted_expected_output)


def test_vegalite_output_no_nerd_font_no_unicode(
    rich_notebook_output: RichOutput,
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
        "                  \n      \x1b]8;id=16281372"
        f"55.127551-234092;file://{tempfile_path}0.html\x1b\\\x1b[94mClick to vie"
        "w Vega chart\x1b[0m\x1b]8;;\x1b\\                 "
        "                                 \n"
        "                                                              "
        "                  \n      \x1b[38;2;187;134;252mImage         "
        "                                                            "
        "\x1b[0m\n"
    )
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output_no_files(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
    adjust_for_fallback: Callable[[str, int], str],
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
        "                  \n"
    )
    adjusted_expected_output = adjust_for_fallback(expected_output, 1)
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=False,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=True,
    )

    tempfile_directory = tempfile_path.parent
    for file in tempfile_directory.glob(
        f"{tempfile_path.stem}*.html"
    ):  # pragma: no cover
        assert not file.exists()
    assert remove_link_ids(output) == remove_link_ids(adjusted_expected_output)


def test_write_vega_output(
    rich_notebook_output: RichOutput,
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
    output = rich_notebook_output(
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
    rich_notebook_output: RichOutput,
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
        "                  \n      \x1b]8;id=16281373"
        f"35.10625-550844;file://{tempfile_path}0.html\x1b\\\x1b[94mVega"
        " chart\x1b[0"
        "m\x1b]8;;\x1b\\                                "
        "                                \n"
        "                                                              "
        "                  \n      \x1b[38;2;187;134;252mImage         "
        "                                                            "
        "\x1b[0m\n"
    )
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=True,
        unicode=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vega_no_hyperlink(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    tempfile_path: Path,
    adjust_for_fallback: Callable[[str, int], str],
    snapshot_with_dir: Snapshot,
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
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=False,
        hide_hyperlink_hints=True,
        unicode=True,
    )
    snapshot_with_dir.assert_match(output, "test_vega_no_hyperlink.txt")


def test_vega_url(
    rich_notebook_output: RichOutput,
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
    output = rich_notebook_output(
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
    rich_notebook_output: RichOutput,
    mocker: MockerFixture,
    snapshot_with_dir: Snapshot,
) -> None:
    """It falls back to rendering a message if there is a RequestError."""
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
    output = rich_notebook_output(vegalite_output_cell)
    snapshot_with_dir.assert_match(output, "test_vega_url_request_error.txt")


def test_render_html(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
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
        f"06.111208-917276;file://{tempfile_path}0.html\x1b\\\x1b[94m🌐 Click to v"
        "iew HTML\x1b[0m\x1b]8;;\x1b\\                     "
        "                                \n       "
        "                                        "
        "                                 \n      "
        "\x1b[1mLorep\x1b[0m \x1b[3mIpsum\x1b[0m             "
        "                                        "
        "          \n"
    )
    output = rich_notebook_output(html_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_html_table(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
) -> None:
    """It renders an HTML table."""
    html_cell = {
        "cell_type": "code",
        "execution_count": 7,
        "id": "43e39858-6416-4dc8-9d7e-7905127e7452",
        "metadata": {},
        "outputs": [
            {
                "data": {
                    "text/html": """\
<table>
  <tr>
    <th>Company</th>
    <th>Contact</th>
    <th>Country</th>
  </tr>
  <tr>
    <td>Alfreds Futterkiste</td>
    <td>Maria Anders</td>
    <td>Germany</td>
  </tr>
  <tr>
    <td>Centro comercial Moctezuma</td>
    <td>Francisco Chang</td>
    <td>Mexico</td>
  </tr>
</table>
                    """,
                    "text/plain": "<IPython.core.display.HTML object>",
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
        "\n\x1b[38;5;247m[7]:\x1b[0m │                  "
        "                                        "
        "               │\n     ╰─────────────────"
        "────────────────────────────────────────"
        "────────────────╯\n                      "
        "                                        "
        "                  \n      \x1b]8;id=58222;fi"
        f"le://{tempfile_path}0.ht"
        "ml\x1b\\\x1b[94m🌐 Click to view HTML\x1b[0m\x1b]8;;\x1b\\"
        "                                        "
        "             \n                          "
        "                                        "
        "              \n                         "
        "                                        "
        "               \n       \x1b[1mCompany\x1b[0m  "
        "                \x1b[1mContact\x1b[0m         "
        "         \x1b[1mCountry\x1b[0m                "
        "\n      ─────────────────────────────────"
        "────────────────────────────────────────"
        "─\n       Alfreds Futterkiste      Maria "
        "Anders             Germany              "
        "  \n       Centro comercial         Franc"
        "isco Chang          Mexico              "
        "   \n       Moctezuma                    "
        "                                        "
        "    \n                                   "
        "                                        "
        "     \n"
    )
    output = rich_notebook_output(html_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_unknown_data_type(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
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
    output = rich_notebook_output(unknown_data_type)
    snapshot_with_dir.assert_match(output, "test_render_unknown_data_type.txt")


def test_render_block_image(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    disable_capture: ContextManager[_PluggyPlugin],
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a block drawing of an image."""
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

    with disable_capture:
        output = rich_notebook_output(image_cell, images=True, image_drawing="block")
    output = remove_link_ids(output)
    snapshot_with_dir.assert_match(output, "test_render_block_image.txt")


def test_render_invalid_block_image(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    disable_capture: ContextManager[_PluggyPlugin],
    tempfile_path: Path,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders a fallback when image is invalid."""
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
                    "image/png": "bad_image_data\n",
                    "text/plain": "<Figure size 432x288 with 1 Axes>",
                },
                "metadata": {"needs_background": "light"},
                "output_type": "display_data",
            },
        ],
        "source": "",
    }

    with disable_capture:
        output = rich_notebook_output(image_cell, images=True, image_drawing="block")
    output = remove_link_ids(output)
    snapshot_with_dir.assert_match(output, "test_render_invalid_block_image.txt")


def test_invalid_image_drawing(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
) -> None:
    """It fallsback to text when failing to draw image."""
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
                    "image/png": "ib45",
                    "text/plain": "<Figure size 432x288 with 1 Axes>",
                },
                "metadata": {"needs_background": "light"},
                "output_type": "display_data",
            },
        ],
        "source": "",
    }
    output = rich_notebook_output(
        image_cell, images=True, image_drawing="character", files=False
    )
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
        "  🖼 Image                               "
        "                                    \n   "
        "                                        "
        "                                     \n  "
        "    \x1b[38;2;187;134;252m<Figure size 432x"
        "288 with 1 Axes>                        "
        "                 \x1b[0m\n"
    )
    assert output == expected_output


def test_render_image_link_no_image(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
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

    with disable_capture:
        output = rich_notebook_output(image_cell, images=False)
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
        f"  \x1b]8;id=236660;file://{tempfile_path}0.png"
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
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    tempfile_path: Path,
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
    output = rich_notebook_output(svg_cell)

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
        f"\x1b]8;id=1627259094.976956-618609;file://{tempfile_path}0.svg"
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
    notebook_node = nbformat.from_dict(  # type: ignore[no-untyped-call]
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


def test_skip_unknown_cell_type(rich_notebook_output: RichOutput) -> None:
    """It skips rendering a cell if the type is not known."""
    markdown_cell = {
        "cell_type": "unknown",
        "id": "academic-bride",
        "metadata": {},
        "source": "### Lorep ipsum\n\n**dolor** _sit_ `amet`",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = ""
    assert output == expected_output


def test_skip_no_cell_type(rich_notebook_output: RichOutput) -> None:
    """It skips rendering a cell if there is not cell type."""
    markdown_cell = {
        "metadata": {"no"},
        "source": "### Lorep ipsum\n\n**dolor** _sit_ `amet`",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = ""
    assert output == expected_output


def test_image_link_not_image(
    rich_notebook_output: RichOutput,
    mocker: MockerFixture,
    remove_link_ids: Callable[[str], str],
) -> None:
    """It falls back to skipping drawing if content is not an image."""
    mock = mocker.patch("httpx.get")
    mock.return_value.content = "Bad image"
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Azores](https://github.com/paw-lu/nbpreview/tests"
        "/assets/outline_article_white_48dp.png)",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="character")
    expected_output = (
        "  \x1b]8;id=246597;https://github.com/paw-l"
        "u/nbpreview/tests/assets/outline_article"
        "_white_48dp.png\x1b\\\x1b[94m🌐 Click to view Az"
        "ores\x1b[0m\x1b]8;;\x1b\\                         "
        "                              \n         "
        "                                        "
        "                               \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_relative_dir_markdown_link(
    rich_notebook_output: RichOutput,
    remove_link_ids: Callable[[str], str],
) -> None:
    """It adds a path prefix to the image hyperlink."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Test image](image.png)",
    }
    relative_dir = pathlib.Path("/", "Users", "test")
    output = rich_notebook_output(
        markdown_cell, relative_dir=relative_dir, hyperlinks=True
    )
    expected_output = (
        "  \x1b]8;id=835649;"
        f"file://{relative_dir.resolve() / 'image.png'}\x1b\\\x1b"
        "[94m🖼 Click to view Test image\x1b[0m\x1b]8;;\x1b"
        "\\                                       "
        "             \n                          "
        "                                        "
        "              \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_notebook_code_line_numbers(
    rich_notebook_output: RichOutput, snapshot_with_dir: Snapshot
) -> None:
    """It renders a code cell with line numbers."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 2,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "def foo(x: float, y: float) -> float:\n    return x + y",
    }
    output = rich_notebook_output(code_cell, line_numbers=True)
    snapshot_with_dir.assert_match(output, "test_notebook_code_line_numbers.txt")


def test_notebook_line_numbers_magic_code_cell(
    rich_notebook_output: RichOutput,
    snapshot_with_dir: Snapshot,
) -> None:
    """It renders line numbers in a code cell with language magic."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "%%bash\necho 'lorep'",
    }
    output = rich_notebook_output(code_cell, line_numbers=True)
    snapshot_with_dir.assert_match(
        output, "test_notebook_line_numbers_magic_code_cell.txt"
    )


def test_code_wrap(rich_notebook_output: RichOutput) -> None:
    """It wraps code when narrow."""
    code_cell = {
        "cell_type": "code",
        "execution_count": 3,
        "id": "emotional-amount",
        "metadata": {},
        "outputs": [],
        "source": "non_monkeys ="
        ' [animal for animal in get_animals("mamals") if animal != "monkey"]',
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[3]:\x1b[0m │ \x1b[38;2;238;255;25"
        "5;49mnon_monkeys\x1b[0m\x1b[38;2;238;255;255;4"
        "9m \x1b[0m\x1b[38;2;137;221;255;49m=\x1b[0m\x1b[38;2"
        ";238;255;255;49m \x1b[0m\x1b[38;2;137;221;255;"
        "49m[\x1b[0m\x1b[38;2;238;255;255;49manimal\x1b[0m"
        "\x1b[38;2;238;255;255;49m \x1b[0m\x1b[38;2;187;12"
        "8;179;49mfor\x1b[0m\x1b[38;2;238;255;255;49m \x1b"
        "[0m\x1b[38;2;238;255;255;49manimal\x1b[0m\x1b[38;"
        "2;238;255;255;49m \x1b[0m\x1b[3;38;2;137;221;2"
        "55;49min\x1b[0m\x1b[38;2;238;255;255;49m \x1b[0m\x1b"
        "[38;2;238;255;255;49mget_animals\x1b[0m\x1b[38"
        ";2;137;221;255;49m(\x1b[0m\x1b[38;2;195;232;14"
        '1;49m"\x1b[0m\x1b[38;2;195;232;141;49mmamals\x1b['
        '0m\x1b[38;2;195;232;141;49m"\x1b[0m\x1b[38;2;137;'
        "221;255;49m)\x1b[0m\x1b[38;2;238;255;255;49m \x1b"
        "[0m\x1b[38;2;187;128;179;49mif\x1b[0m\x1b[38;2;23"
        "8;255;255;49m \x1b[0m\x1b[38;2;238;255;255;49m"
        "animal\x1b[0m\x1b[38;2;238;255;255;49m \x1b[0m\x1b[3"
        "8;2;137;221;255;49m!=\x1b[0m\x1b[38;2;238;255;"
        "255;49m \x1b[0m │\n     │ \x1b[38;2;195;232;141"
        ';49m"\x1b[0m\x1b[38;2;195;232;141;49mmonkey\x1b[0'
        'm\x1b[38;2;195;232;141;49m"\x1b[0m\x1b[38;2;137;2'
        "21;255;49m]\x1b[0m                         "
        "                                      │\n"
        "     ╰──────────────────────────────────"
        "───────────────────────────────────────╯"
        "\n"
    )
    output = rich_notebook_output(code_cell, code_wrap=True)
    assert output == expected_output


def test_html_encoded_image_link_text(
    rich_console: Callable[[Any, bool | None], str],
    expected_output: str,
    remove_link_ids: Callable[[str], str],
    mock_tempfile_file: Generator[Mock, None, None],
) -> None:
    """It extracts an encoded image from an HTML link."""
    notebook_path = pathlib.Path(__file__).parent / pathlib.Path(
        "assets", "link_encoded_image.ipynb"
    )
    nbpreview_notebook = notebook.Notebook.from_file(notebook_path)
    output = rich_console(nbpreview_notebook, False)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_long_path(
    rich_notebook_output: RichOutput,
    remove_link_ids: Callable[[str], str],
    snapshot_with_dir: Snapshot,
) -> None:
    """It skips attempting to render an image if path is too long."""
    file_path = pathlib.Path("/", "user") / ("a" * 1_000)
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"![]({file_path.as_posix()})",
    }
    output = rich_notebook_output(markdown_cell)
    output = remove_link_ids(output)
    snapshot_with_dir.assert_match(output, "test_long_path.txt")


@pytest.mark.parametrize(
    "bad_reference", ["data:image/png;unknown,abc123", "data:unknown;base64,abc123"]
)
def test_unknown_data_link(
    bad_reference: str, rich_notebook_output: RichOutput,
    snapshot_with_dir: Snapshot,
) -> None:
    """It does not decode the data link if it is not identified."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"hey\n\n![Test image]({bad_reference})" "\n\nthere\n**hello**\n",
    }
    output = rich_notebook_output(markdown_cell, hyperlinks=True)
    # Use different snapshot files for each parameter to handle different outputs
    snapshot_name = (
        f"test_unknown_data_link_"
        f"{bad_reference.replace(':', '_').replace(';', '_').replace(',', '_')}.txt"
    )
    snapshot_with_dir.assert_match(output, snapshot_name)


def test_bad_data_link_encode(rich_notebook_output: RichOutput) -> None:
    """It skips rendering the encoded image on a failed decode."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "hey\n\n![Test image](data:image/png;base64,abc123)"
        "\n\nthere\n**hello**\n",
    }
    output = rich_notebook_output(markdown_cell, hyperlinks=True)
    expected_output = (
        "  hey                                   "
        "                                        "
        "\n                                       "
        "                                        "
        " \n                                      "
        "                                        "
        "  \n                                     "
        "                                        "
        "   \n  there \x1b[1mhello\x1b[0m               "
        "                                        "
        "            \n"
    )
    assert output == expected_output
