"""Test cases for render."""
import dataclasses
import io
import itertools
import json
import os
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
from typing import Literal
from typing import Optional
from typing import Protocol
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

from nbpreview import notebook


class RichOutput(Protocol):
    """Typing protocol for _rich_notebook_output."""

    def __call__(
        self,
        cell: Union[Dict[str, Any], None],
        plain: bool = False,
        no_wrap: bool = False,
        unicode: Optional[bool] = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        negative_space: bool = True,
        hyperlinks: bool = True,
        hide_hyperlink_hints: bool = False,
        images: Optional[bool] = None,
        image_drawing: Optional[Literal["block", "character", "braille"]] = None,
        color: Optional[bool] = None,
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
        if "terminedia" in sys.modules:
            adjusted_output = rendered_output + fallback_text
        else:
            adjusted_output = rendered_output
        return adjusted_output

    return _adjust_for_fallback


@dataclasses.dataclass
class LinkFilePathNotFoundError(Exception):
    """No hyperlink filepath found in output."""

    def __post_init__(
        self,
    ) -> None:
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
        else:
            raise LinkFilePathNotFoundError()

    return _parse_link_filepath


@pytest.fixture
def rich_notebook_output(
    rich_console: Callable[[Any, Union[bool, None]], str],
    make_notebook: Callable[[Optional[Dict[str, Any]]], NotebookNode],
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
        cell: Union[Dict[str, Any], None],
        plain: Optional[bool] = None,
        no_wrap: Optional[bool] = None,
        unicode: Optional[bool] = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        negative_space: bool = True,
        hyperlinks: bool = True,
        hide_hyperlink_hints: bool = False,
        images: Optional[bool] = None,
        image_drawing: Optional[Literal["block", "character", "braille"]] = None,
        color: Optional[bool] = None,
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
            color=color,
            negative_space=negative_space,
        )
        output = rich_console(rendered_notebook, no_wrap)
        return output

    return _rich_notebook_output


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
    """Create function to remove link ids from rendered hyperlinks."""

    def _remove_link_ids(render: str) -> str:
        """Remove link ids from rendered hyperlinks."""
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


def test_notebook_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a markdown cell."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "### Lorep ipsum\n\n**dolor** _sit_ `amet`",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "                                        "
        "                                        "
        "\n  \x1b[1;38;2;3;218;197m### \x1b[0m\x1b[1;38;2;3"
        ";218;197mLorep ipsum\x1b[0m\x1b[1;38;2;3;218;1"
        "97m                                     "
        "                          \x1b[0m\n         "
        "                                        "
        "                               \n  \x1b[1mdo"
        "lor\x1b[0m \x1b[3msit\x1b[0m \x1b[97;40mamet\x1b[0m    "
        "                                        "
        "                    \n"
    )
    assert output == expected_output


def test_image_link_markdown_cell_request_error(
    rich_notebook_output: RichOutput,
    mocker: MockerFixture,
    remove_link_ids: Callable[[str], str],
) -> None:
    """It falls back to rendering a message if RequestError occurs."""
    mock = mocker.patch("httpx.get", side_effect=httpx.RequestError("Mock"))
    mock.return_value.content = (
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "ferdinand-stohr-ig8oMCxMOTY-unsplash.jpg")
    ).read_bytes()
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Azores](https://github.com/paw-lu/nbpreview/tests/"
        "assets/ferdinand-stohr-ig8oMCxMOTY-unsplash.jpg)",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="braille")
    expected_output = (
        "  \x1b]8;id=724062;https://github.com/paw-l"
        "u/nbpreview/tests/assets/ferdinand-stohr"
        "-ig8oMCxMOTY-unsplash.jpg\x1b\\\x1b[94m🌐 Click "
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
) -> None:
    """It renders a markdown cell with an image."""
    mock = mocker.patch("httpx.get")
    mock.return_value.content = (
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "ferdinand-stohr-ig8oMCxMOTY-unsplash.jpg")
    ).read_bytes()
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![Azores](https://github.com/paw-lu/nbpreview/tests"
        "/assets/ferdinand-stohr-ig8oMCxMOTY-unsplash.jpg)",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="braille")
    expected_output = (
        "  \x1b]8;id=598830;https://github.com/paw-l"
        "u/nbpreview/tests/assets/ferdinand-stohr"
        "-ig8oMCxMOTY-unsplash.jpg\x1b\\\x1b[94m🌐 Click "
        "to view Azores\x1b[0m\x1b]8;;\x1b\\               "
        "                                        "
        "\n                                       "
        "                                        "
        " \n  \x1b[38;2;157;175;189m⣿\x1b[0m\x1b[38;2;171;1"
        "83;199m⣿\x1b[0m\x1b[38;2;158;170;186m⣿\x1b[0m\x1b[38"
        ";2;188;194;208m⣿\x1b[0m\x1b[38;2;216;219;234m⣿"
        "\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;226;2"
        "29;244m⣿\x1b[0m\x1b[38;2;225;228;243m⣿\x1b[0m\x1b[38"
        ";2;223;226;241m⣿\x1b[0m\x1b[38;2;224;227;242m⣿"
        "\x1b[0m\x1b[38;2;225;227;242m⣿\x1b[0m\x1b[38;2;180;1"
        "96;211m⣿\x1b[0m\x1b[38;2;211;223;235m⣿\x1b[0m\x1b[38"
        ";2;223;225;237m⣿\x1b[0m\x1b[38;2;223;226;241m⣿"
        "\x1b[0m\x1b[38;2;200;203;218m⣿\x1b[0m\x1b[38;2;194;2"
        "00;214m⣿\x1b[0m\x1b[38;2;189;195;209m⣿\x1b[0m\x1b[38"
        ";2;187;195;206m⣿\x1b[0m\x1b[38;2;194;198;210m⣿"
        "\x1b[0m\x1b[38;2;132;168;184m⣿\x1b[0m\x1b[38;2;224;2"
        "27;242m⣿\x1b[0m\x1b[38;2;224;227;242m⣿\x1b[0m\x1b[38"
        ";2;224;227;242m⣿\x1b[0m\x1b[38;2;220;223;238m⣿"
        "\x1b[0m\x1b[38;2;205;212;228m⣿\x1b[0m\x1b[38;2;167;1"
        "83;196m⣿\x1b[0m\x1b[38;2;200;206;218m⣿\x1b[0m\x1b[38"
        ";2;168;191;205m⣿\x1b[0m\x1b[38;2;131;162;182m⣿"
        "\x1b[0m\x1b[38;2;116;151;173m⣿\x1b[0m\x1b[38;2;203;2"
        "12;227m⣿\x1b[0m\x1b[38;2;223;229;245m⣿\x1b[0m\x1b[38"
        ";2;226;225;239m⣿\x1b[0m\x1b[38;2;204;220;233m⣿"
        "\x1b[0m\x1b[38;2;152;168;183m⣿\x1b[0m\x1b[38;2;225;2"
        "27;242m⣿\x1b[0m\x1b[38;2;223;226;241m⣿\x1b[0m\x1b[38"
        ";2;224;227;242m⣿\x1b[0m\x1b[38;2;222;225;240m⣿"
        "\x1b[0m\x1b[38;2;222;225;240m⣿\x1b[0m\x1b[38;2;219;2"
        "22;237m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38"
        ";2;219;222;237m⣿\x1b[0m\x1b[38;2;219;222;237m⣿"
        "\x1b[0m\x1b[38;2;220;223;238m⣿\x1b[0m\x1b[38;2;219;2"
        "22;237m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38"
        ";2;219;222;237m⣿\x1b[0m\x1b[38;2;219;222;237m⣿"
        "\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;219;2"
        "22;237m⣿\x1b[0m\x1b[38;2;215;218;233m⣿\x1b[0m\x1b[38"
        ";2;213;216;231m⣿\x1b[0m\x1b[38;2;193;196;211m⣿"
        "\x1b[0m\x1b[38;2;173;179;193m⣿\x1b[0m\x1b[38;2;197;2"
        "03;217m⣿\x1b[0m\x1b[38;2;186;194;207m⣿\x1b[0m\x1b[38"
        ";2;194;202;215m⣿\x1b[0m\x1b[38;2;219;222;237m⣿"
        "\x1b[0m\x1b[38;2;217;220;235m⣿\x1b[0m\x1b[38;2;215;2"
        "18;233m⣿\x1b[0m\x1b[38;2;210;209;227m⣿\x1b[0m\x1b[38"
        ";2;172;184;198m⣿\x1b[0m\x1b[38;2;161;170;187m⣿"
        "\x1b[0m\x1b[38;2;163;172;189m⣿\x1b[0m\x1b[38;2;180;1"
        "86;200m⣿\x1b[0m\x1b[38;2;197;199;214m⣿\x1b[0m\x1b[38"
        ";2;206;209;224m⣿\x1b[0m\x1b[38;2;212;215;230m⣿"
        "\x1b[0m\x1b[38;2;209;212;227m⣿\x1b[0m\x1b[38;2;201;2"
        "04;219m⣿\x1b[0m\x1b[38;2;205;208;223m⣿\x1b[0m\x1b[38"
        ";2;192;198;212m⣿\x1b[0m\x1b[38;2;85;107;120m⣿\x1b"
        "[0m\x1b[38;2;73;95;108m⣿\x1b[0m\x1b[38;2;101;120;"
        "134m⣿\x1b[0m\x1b[38;2;115;134;148m⣿\x1b[0m\n  \x1b[38"
        ";2;197;204;222m⣿\x1b[0m\x1b[38;2;197;204;222m⣿"
        "\x1b[0m\x1b[38;2;188;197;214m⣿\x1b[0m\x1b[38;2;193;1"
        "99;213m⣿\x1b[0m\x1b[38;2;158;177;194m⣿\x1b[0m\x1b[38"
        ";2;151;170;187m⣿\x1b[0m\x1b[38;2;136;157;174m⣿"
        "\x1b[0m\x1b[38;2;139;167;181m⣿\x1b[0m\x1b[38;2;156;1"
        "72;187m⣿\x1b[0m\x1b[38;2;184;196;212m⣿\x1b[0m\x1b[38"
        ";2;217;220;237m⣿\x1b[0m\x1b[38;2;222;221;239m⣿"
        "\x1b[0m\x1b[38;2;211;214;229m⣿\x1b[0m\x1b[38;2;200;2"
        "03;218m⣿\x1b[0m\x1b[38;2;226;229;244m⣿\x1b[0m\x1b[38"
        ";2;224;227;242m⣿\x1b[0m\x1b[38;2;225;228;243m⣿"
        "\x1b[0m\x1b[38;2;224;227;242m⣿\x1b[0m\x1b[38;2;198;2"
        "05;221m⣿\x1b[0m\x1b[38;2;182;194;208m⣿\x1b[0m\x1b[38"
        ";2;224;227;242m⣿\x1b[0m\x1b[38;2;225;228;243m⣿"
        "\x1b[0m\x1b[38;2;222;225;240m⣿\x1b[0m\x1b[38;2;214;2"
        "22;233m⣿\x1b[0m\x1b[38;2;191;207;220m⣿\x1b[0m\x1b[38"
        ";2;170;193;207m⣿\x1b[0m\x1b[38;2;213;225;241m⣿"
        "\x1b[0m\x1b[38;2;204;207;222m⣿\x1b[0m\x1b[38;2;207;2"
        "15;228m⣿\x1b[0m\x1b[38;2;169;191;205m⣿\x1b[0m\x1b[38"
        ";2;142;179;195m⣿\x1b[0m\x1b[38;2;171;193;204m⣿"
        "\x1b[0m\x1b[38;2;174;186;200m⣿\x1b[0m\x1b[38;2;179;1"
        "88;203m⣿\x1b[0m\x1b[38;2;208;211;228m⣿\x1b[0m\x1b[38"
        ";2;207;210;225m⣿\x1b[0m\x1b[38;2;183;191;204m⣿"
        "\x1b[0m\x1b[38;2;199;205;219m⣿\x1b[0m\x1b[38;2;182;1"
        "88;202m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38"
        ";2;224;227;242m⣿\x1b[0m\x1b[38;2;220;223;238m⣿"
        "\x1b[0m\x1b[38;2;222;225;240m⣿\x1b[0m\x1b[38;2;223;2"
        "26;241m⣿\x1b[0m\x1b[38;2;221;224;239m⣿\x1b[0m\x1b[38"
        ";2;220;223;238m⣿\x1b[0m\x1b[38;2;219;222;237m⣿"
        "\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;220;2"
        "23;238m⣿\x1b[0m\x1b[38;2;222;221;237m⣿\x1b[0m\x1b[38"
        ";2;227;226;242m⣿\x1b[0m\x1b[38;2;217;220;235m⣿"
        "\x1b[0m\x1b[38;2;220;223;238m⣿\x1b[0m\x1b[38;2;217;2"
        "20;235m⣿\x1b[0m\x1b[38;2;220;223;238m⣿\x1b[0m\x1b[38"
        ";2;216;222;238m⣿\x1b[0m\x1b[38;2;181;190;205m⣿"
        "\x1b[0m\x1b[38;2;202;211;226m⣿\x1b[0m\x1b[38;2;177;1"
        "83;199m⣿\x1b[0m\x1b[38;2;217;220;235m⣿\x1b[0m\x1b[38"
        ";2;178;192;203m⣿\x1b[0m\x1b[38;2;208;214;228m⣿"
        "\x1b[0m\x1b[38;2;211;224;233m⣿\x1b[0m\x1b[38;2;52;69"
        ";77m⣿\x1b[0m\x1b[38;2;66;93;104m⣿\x1b[0m\x1b[38;2;80"
        ";107;118m⣿\x1b[0m\x1b[38;2;127;146;161m⣿\x1b[0m\x1b["
        "38;2;123;146;160m⣿\x1b[0m\x1b[38;2;83;107;119m"
        "⣿\x1b[0m\x1b[38;2;97;116;130m⣿\x1b[0m\x1b[38;2;152;1"
        "64;178m⣿\x1b[0m\x1b[38;2;151;163;177m⣿\x1b[0m\x1b[38"
        ";2;172;185;201m⣿\x1b[0m\x1b[38;2;120;138;152m⣿"
        "\x1b[0m\x1b[38;2;149;156;172m⣿\x1b[0m\x1b[38;2;179;1"
        "86;202m⣿\x1b[0m\x1b[38;2;162;175;191m⣿\x1b[0m\x1b[38"
        ";2;163;176;192m⣿\x1b[0m\n  \x1b[38;2;204;210;22"
        "4m⣿\x1b[0m\x1b[38;2;211;217;231m⣿\x1b[0m\x1b[38;2;21"
        "0;211;229m⣿\x1b[0m\x1b[38;2;189;190;208m⣿\x1b[0m\x1b"
        "[38;2;201;204;219m⣿\x1b[0m\x1b[38;2;210;213;22"
        "8m⡿\x1b[0m\x1b[38;2;218;222;234m⣿\x1b[0m\x1b[38;2;20"
        "4;210;222m⣿\x1b[0m\x1b[38;2;214;221;231m⣻\x1b[0m\x1b"
        "[38;2;95;102;112m⣿\x1b[0m\x1b[38;2;47;60;69m⣿\x1b"
        "[0m\x1b[38;2;74;86;100m⣿\x1b[0m\x1b[38;2;208;218;"
        "230m⣛\x1b[0m\x1b[38;2;200;206;220m⣿\x1b[0m\x1b[38;2;"
        "201;198;215m⣿\x1b[0m\x1b[38;2;195;192;209m⢿\x1b[0"
        "m\x1b[38;2;200;197;216m⣿\x1b[0m\x1b[38;2;213;205;"
        "226m⣿\x1b[0m\x1b[38;2;194;200;214m⣿\x1b[0m\x1b[38;2;"
        "193;199;213m⣿\x1b[0m\x1b[38;2;213;216;231m⣿\x1b[0"
        "m\x1b[38;2;214;217;232m⣿\x1b[0m\x1b[38;2;209;212;"
        "227m⣿\x1b[0m\x1b[38;2;216;219;234m⣿\x1b[0m\x1b[38;2;"
        "227;230;245m⣿\x1b[0m\x1b[38;2;226;230;242m⣿\x1b[0"
        "m\x1b[38;2;197;210;226m⣿\x1b[0m\x1b[38;2;180;197;"
        "213m⣿\x1b[0m\x1b[38;2;210;222;236m⣿\x1b[0m\x1b[38;2;"
        "227;229;244m⣿\x1b[0m\x1b[38;2;226;228;243m⣿\x1b[0"
        "m\x1b[38;2;228;230;245m⣿\x1b[0m\x1b[38;2;225;227;"
        "242m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;"
        "224;227;242m⣿\x1b[0m\x1b[38;2;223;226;241m⣿\x1b[0"
        "m\x1b[38;2;225;228;243m⣿\x1b[0m\x1b[38;2;225;228;"
        "243m⣿\x1b[0m\x1b[38;2;204;207;222m⣿\x1b[0m\x1b[38;2;"
        "202;208;224m⣿\x1b[0m\x1b[38;2;200;206;222m⣿\x1b[0"
        "m\x1b[38;2;209;215;229m⣿\x1b[0m\x1b[38;2;215;221;"
        "235m⣿\x1b[0m\x1b[38;2;198;204;220m⣿\x1b[0m\x1b[38;2;"
        "204;213;228m⣿\x1b[0m\x1b[38;2;195;202;218m⣿\x1b[0"
        "m\x1b[38;2;210;217;233m⣿\x1b[0m\x1b[38;2;203;212;"
        "227m⣿\x1b[0m\x1b[38;2;164;178;191m⣿\x1b[0m\x1b[38;2;"
        "141;168;185m⣿\x1b[0m\x1b[38;2;148;166;186m⣿\x1b[0"
        "m\x1b[38;2;173;186;203m⣿\x1b[0m\x1b[38;2;188;195;"
        "211m⣿\x1b[0m\x1b[38;2;154;170;183m⣿\x1b[0m\x1b[38;2;"
        "180;186;202m⣿\x1b[0m\x1b[38;2;181;193;205m⣿\x1b[0"
        "m\x1b[38;2;213;210;227m⣿\x1b[0m\x1b[38;2;202;208;"
        "222m⣿\x1b[0m\x1b[38;2;203;209;223m⣿\x1b[0m\x1b[38;2;"
        "217;219;234m⣿\x1b[0m\x1b[38;2;216;219;234m⣿\x1b[0"
        "m\x1b[38;2;213;216;231m⣿\x1b[0m\x1b[38;2;201;204;"
        "221m⣿\x1b[0m\x1b[38;2;188;195;211m⣿\x1b[0m\x1b[38;2;"
        "170;178;197m⣿\x1b[0m\x1b[38;2;157;170;187m⣿\x1b[0"
        "m\x1b[38;2;149;168;185m⣿\x1b[0m\x1b[38;2;97;129;1"
        "42m⣿\x1b[0m\x1b[38;2;76;105;119m⣿\x1b[0m\x1b[38;2;90"
        ";119;133m⣿\x1b[0m\x1b[38;2;73;96;110m⣿\x1b[0m\x1b[38"
        ";2;72;95;109m⣿\x1b[0m\x1b[38;2;75;97;110m⣿\x1b[0m"
        "\x1b[38;2;83;101;111m⣿\x1b[0m\x1b[38;2;113;145;15"
        "8m⣿\x1b[0m\x1b[38;2;97;129;142m⣿\x1b[0m\x1b[38;2;112"
        ";138;151m⣿\x1b[0m\x1b[38;2;132;149;165m⣿\x1b[0m\n "
        " \x1b[38;2;48;75;84m⣿\x1b[0m\x1b[38;2;66;90;100m⣿"
        "\x1b[0m\x1b[38;2;91;108;118m⣿\x1b[0m\x1b[38;2;108;12"
        "4;140m⣿\x1b[0m\x1b[38;2;90;112;123m⣿\x1b[0m\x1b[38;2"
        ";91;113;124m⢿\x1b[0m\x1b[38;2;87;109;120m⣿\x1b[0m"
        "\x1b[38;2;165;188;194m⣿\x1b[0m\x1b[38;2;70;89;96m"
        "⣿\x1b[0m\x1b[38;2;96;114;128m⣿\x1b[0m\x1b[38;2;88;11"
        "6;128m⣿\x1b[0m\x1b[38;2;77;119;131m⣿\x1b[0m\x1b[38;2"
        ";65;113;127m⣿\x1b[0m\x1b[38;2;58;121;138m⣿\x1b[0m"
        "\x1b[38;2;66;116;139m⣿\x1b[0m\x1b[38;2;23;69;85m⣿"
        "\x1b[0m\x1b[38;2;87;123;137m⣻\x1b[0m\x1b[38;2;108;14"
        "0;153m⣿\x1b[0m\x1b[38;2;89;132;139m⣿\x1b[0m\x1b[38;2"
        ";79;99;110m⣿\x1b[0m\x1b[38;2;201;211;221m⣿\x1b[0m"
        "\x1b[38;2;209;215;229m⣿\x1b[0m\x1b[38;2;220;226;2"
        "40m⣿\x1b[0m\x1b[38;2;210;213;228m⣿\x1b[0m\x1b[38;2;2"
        "19;222;237m⣿\x1b[0m\x1b[38;2;219;228;243m⣿\x1b[0m"
        "\x1b[38;2;191;207;222m⣿\x1b[0m\x1b[38;2;189;212;2"
        "28m⣿\x1b[0m\x1b[38;2;224;220;234m⣿\x1b[0m\x1b[38;2;2"
        "10;215;235m⣿\x1b[0m\x1b[38;2;179;223;234m⣿\x1b[0m"
        "\x1b[38;2;96;143;151m⣿\x1b[0m\x1b[38;2;142;166;17"
        "6m⣿\x1b[0m\x1b[38;2;104;120;136m⣿\x1b[0m\x1b[38;2;12"
        "9;151;165m⣿\x1b[0m\x1b[38;2;136;153;171m⣿\x1b[0m\x1b"
        "[38;2;95;114;131m⣿\x1b[0m\x1b[38;2;100;123;139"
        "m⣿\x1b[0m\x1b[38;2;99;139;149m⣻\x1b[0m\x1b[38;2;17;8"
        "3;97m⣓\x1b[0m\x1b[38;2;12;99;116m⣟\x1b[0m\x1b[38;2;1"
        "1;86;107m⣻\x1b[0m\x1b[38;2;0;67;93m⡾\x1b[0m\x1b[38;2"
        ";7;75;98m⣉\x1b[0m\x1b[38;2;5;77;99m⠀\x1b[0m\x1b[38;2"
        ";2;80;93m⠀\x1b[0m\x1b[38;2;4;93;109m⣙\x1b[0m\x1b[38;"
        "2;6;85;100m⢋\x1b[0m\x1b[38;2;4;73;89m⠑\x1b[0m\x1b[38"
        ";2;2;73;93m⡂\x1b[0m\x1b[38;2;4;73;89m⢈\x1b[0m\x1b[38"
        ";2;1;68;85m⣉\x1b[0m\x1b[38;2;15;77;92m⣹\x1b[0m\x1b[3"
        "8;2;20;64;77m⣭\x1b[0m\x1b[38;2;67;101;111m⢏\x1b[0"
        "m\x1b[38;2;73;84;90m⢿\x1b[0m\x1b[38;2;53;64;70m⡝\x1b"
        "[0m\x1b[38;2;48;59;63m⠛\x1b[0m\x1b[38;2;52;64;64m"
        "⢀\x1b[0m\x1b[38;2;22;29;35m⣈\x1b[0m\x1b[38;2;25;36;4"
        "0m⣭\x1b[0m\x1b[38;2;40;49;56m⣭\x1b[0m\x1b[38;2;65;71"
        ";83m⣉\x1b[0m\x1b[38;2;29;38;53m⠛\x1b[0m\x1b[38;2;183"
        ";192;207m⠿\x1b[0m\x1b[38;2;180;191;211m⢿\x1b[0m\x1b["
        "38;2;144;171;178m⢿\x1b[0m\x1b[38;2;220;224;235"
        "m⣿\x1b[0m\x1b[38;2;209;211;224m⣿\x1b[0m\x1b[38;2;155"
        ";168;187m⣿\x1b[0m\x1b[38;2;115;142;159m⣿\x1b[0m\x1b["
        "38;2;173;189;204m⣿\x1b[0m\x1b[38;2;166;183;199"
        "m⣿\x1b[0m\x1b[38;2;130;147;163m⣿\x1b[0m\x1b[38;2;176"
        ";194;206m⣿\x1b[0m\x1b[38;2;149;167;179m⣿\x1b[0m\x1b["
        "38;2;180;187;203m⣿\x1b[0m\x1b[38;2;185;191;207"
        "m⣿\x1b[0m\n  \x1b[38;2;53;87;97m⣶\x1b[0m\x1b[38;2;49;"
        "94;100m⣼\x1b[0m\x1b[38;2;48;91;100m⣿\x1b[0m\x1b[38;2"
        ";96;132;144m⣻\x1b[0m\x1b[38;2;140;164;166m⣿\x1b[0"
        "m\x1b[38;2;163;174;180m⢿\x1b[0m\x1b[38;2;177;189;"
        "201m⣿\x1b[0m\x1b[38;2;169;186;196m⣿\x1b[0m\x1b[38;2;"
        "84;111;120m⣿\x1b[0m\x1b[38;2;98;128;139m⣿\x1b[0m\x1b"
        "[38;2;89;121;132m⣿\x1b[0m\x1b[38;2;64;100;114m"
        "⣿\x1b[0m\x1b[38;2;49;85;97m⣿\x1b[0m\x1b[38;2;95;131;"
        "143m⣿\x1b[0m\x1b[38;2;72;116;127m⣿\x1b[0m\x1b[38;2;6"
        "0;118;132m⣿\x1b[0m\x1b[38;2;57;119;134m⣿\x1b[0m\x1b["
        "38;2;54;113;129m⣿\x1b[0m\x1b[38;2;33;112;125m⣿"
        "\x1b[0m\x1b[38;2;56;132;146m⣿\x1b[0m\x1b[38;2;105;17"
        "1;187m⣿\x1b[0m\x1b[38;2;26;139;135m⣿\x1b[0m\x1b[38;2"
        ";12;122;135m⣿\x1b[0m\x1b[38;2;106;173;192m⣿\x1b[0"
        "m\x1b[38;2;43;131;153m⣿\x1b[0m\x1b[38;2;32;143;15"
        "0m⣿\x1b[0m\x1b[38;2;111;142;170m⣿\x1b[0m\x1b[38;2;35"
        ";134;153m⣿\x1b[0m\x1b[38;2;82;160;173m⣿\x1b[0m\x1b[3"
        "8;2;59;120;141m⣿\x1b[0m\x1b[38;2;66;148;159m⣿\x1b"
        "[0m\x1b[38;2;49;107;129m⣿\x1b[0m\x1b[38;2;51;107;"
        "124m⣿\x1b[0m\x1b[38;2;54;116;131m⣿\x1b[0m\x1b[38;2;8"
        "5;144;158m⣿\x1b[0m\x1b[38;2;37;103;115m⣿\x1b[0m\x1b["
        "38;2;58;120;133m⣿\x1b[0m\x1b[38;2;55;104;118m⣿"
        "\x1b[0m\x1b[38;2;49;96;106m⣿\x1b[0m\x1b[38;2;79;115;"
        "131m⢿\x1b[0m\x1b[38;2;78;107;121m⣿\x1b[0m\x1b[38;2;8"
        "3;109;122m⣿\x1b[0m\x1b[38;2;69;106;114m⣿\x1b[0m\x1b["
        "38;2;73;116;133m⣏\x1b[0m\x1b[38;2;45;122;140m⣶"
        "\x1b[0m\x1b[38;2;118;139;156m⢶\x1b[0m\x1b[38;2;37;81"
        ";92m⣿\x1b[0m\x1b[38;2;114;147;156m⣥\x1b[0m\x1b[38;2;"
        "104;122;132m⣴\x1b[0m\x1b[38;2;84;105;122m⣥\x1b[0m"
        "\x1b[38;2;61;92;110m⣠\x1b[0m\x1b[38;2;47;75;79m⣼\x1b"
        "[0m\x1b[38;2;65;88;94m⣍\x1b[0m\x1b[38;2;44;67;75m"
        "⢤\x1b[0m\x1b[38;2;51;74;82m⣋\x1b[0m\x1b[38;2;83;106;"
        "114m⠋\x1b[0m\x1b[38;2;50;73;81m⡉\x1b[0m\x1b[38;2;31;"
        "50;56m⠄\x1b[0m\x1b[38;2;46;66;67m⡉\x1b[0m\x1b[38;2;4"
        "7;65;75m⢫\x1b[0m\x1b[38;2;57;75;79m⢍\x1b[0m\x1b[38;2"
        ";43;61;65m⡈\x1b[0m\x1b[38;2;31;45;54m⢁\x1b[0m\x1b[38"
        ";2;45;74;70m⣤\x1b[0m\x1b[38;2;57;90;83m⣶\x1b[0m\x1b["
        "38;2;88;113;109m⣤\x1b[0m\x1b[38;2;34;59;56m⣑\x1b["
        "0m\x1b[38;2;28;40;40m⠮\x1b[0m\x1b[38;2;48;73;70m⣿"
        "\x1b[0m\x1b[38;2;134;152;156m⢽\x1b[0m\x1b[38;2;65;74"
        ";81m⢍\x1b[0m\x1b[38;2;71;80;87m⡛\x1b[0m\x1b[38;2;33;"
        "51;61m⣩\x1b[0m\x1b[38;2;17;49;60m⠻\x1b[0m\x1b[38;2;1"
        "6;53;62m⣛\x1b[0m\x1b[38;2;29;61;72m⣻\x1b[0m\x1b[38;2"
        ";26;62;76m⣟\x1b[0m\x1b[38;2;42;78;92m⣛\x1b[0m\n  \x1b"
        "[38;2;58;86;87m⣮\x1b[0m\x1b[38;2;110;134;138m⢭"
        "\x1b[0m\x1b[38;2;50;69;75m⣯\x1b[0m\x1b[38;2;165;194;"
        "190m⣿\x1b[0m\x1b[38;2;111;147;133m⣿\x1b[0m\x1b[38;2;"
        "158;186;163m⣾\x1b[0m\x1b[38;2;76;95;91m⣿\x1b[0m\x1b["
        "38;2;118;136;136m⣾\x1b[0m\x1b[38;2;167;182;175"
        "m⡿\x1b[0m\x1b[38;2;171;184;167m⣿\x1b[0m\x1b[38;2;192"
        ";206;191m⣿\x1b[0m\x1b[38;2;136;157;148m⣿\x1b[0m\x1b["
        "38;2;38;74;86m⣟\x1b[0m\x1b[38;2;43;83;93m⣋\x1b[0m"
        "\x1b[38;2;40;77;85m⣿\x1b[0m\x1b[38;2;38;95;102m⣿\x1b"
        "[0m\x1b[38;2;59;105;118m⣟\x1b[0m\x1b[38;2;146;175"
        ";183m⣿\x1b[0m\x1b[38;2;207;227;228m⣿\x1b[0m\x1b[38;2"
        ";200;201;203m⣿\x1b[0m\x1b[38;2;216;209;199m⢿\x1b["
        "0m\x1b[38;2;208;212;213m⣿\x1b[0m\x1b[38;2;184;203"
        ";210m⣿\x1b[0m\x1b[38;2;76;111;113m⣿\x1b[0m\x1b[38;2;"
        "109;129;140m⣿\x1b[0m\x1b[38;2;171;152;154m⣿\x1b[0"
        "m\x1b[38;2;190;195;191m⣿\x1b[0m\x1b[38;2;182;193;"
        "185m⣾\x1b[0m\x1b[38;2;155;161;151m⣿\x1b[0m\x1b[38;2;"
        "185;192;185m⣿\x1b[0m\x1b[38;2;190;201;193m⣿\x1b[0"
        "m\x1b[38;2;61;88;83m⣿\x1b[0m\x1b[38;2;156;180;184"
        "m⣿\x1b[0m\x1b[38;2;64;108;119m⣿\x1b[0m\x1b[38;2;58;8"
        "7;93m⣿\x1b[0m\x1b[38;2;152;181;185m⣿\x1b[0m\x1b[38;2"
        ";68;98;96m⣷\x1b[0m\x1b[38;2;102;127;132m⣿\x1b[0m\x1b"
        "[38;2;62;87;92m⢻\x1b[0m\x1b[38;2;42;66;76m⣿\x1b[0"
        "m\x1b[38;2;40;64;66m⣿\x1b[0m\x1b[38;2;95;124;119m"
        "⣷\x1b[0m\x1b[38;2;88;112;99m⣾\x1b[0m\x1b[38;2;99;122"
        ";116m⣟\x1b[0m\x1b[38;2;41;64;58m⣻\x1b[0m\x1b[38;2;12"
        "9;154;148m⣿\x1b[0m\x1b[38;2;118;144;131m⣷\x1b[0m\x1b"
        "[38;2;160;180;153m⢿\x1b[0m\x1b[38;2;188;191;16"
        "2m⣶\x1b[0m\x1b[38;2;172;180;167m⣭\x1b[0m\x1b[38;2;13"
        "2;140;129m⣿\x1b[0m\x1b[38;2;175;189;174m⣿\x1b[0m\x1b"
        "[38;2;129;143;130m⣿\x1b[0m\x1b[38;2;118;142;12"
        "8m⠿\x1b[0m\x1b[38;2;95;124;106m⡿\x1b[0m\x1b[38;2;51;"
        "71;62m⢓\x1b[0m\x1b[38;2;54;60;56m⡷\x1b[0m\x1b[38;2;6"
        "0;74;74m⣘\x1b[0m\x1b[38;2;58;73;76m⣹\x1b[0m\x1b[38;2"
        ";59;76;83m⠜\x1b[0m\x1b[38;2;37;56;63m⣔\x1b[0m\x1b[38"
        ";2;30;49;56m⡊\x1b[0m\x1b[38;2;37;56;62m⠍\x1b[0m\x1b["
        "38;2;47;62;69m⢤\x1b[0m\x1b[38;2;49;60;66m⠅\x1b[0m"
        "\x1b[38;2;45;56;58m⢍\x1b[0m\x1b[38;2;54;69;74m⡹\x1b["
        "0m\x1b[38;2;34;52;40m⠿\x1b[0m\x1b[38;2;160;156;14"
        "4m⠿\x1b[0m\x1b[38;2;172;171;143m⢿\x1b[0m\x1b[38;2;14"
        "9;159;125m⣾\x1b[0m\x1b[38;2;90;106;95m⣷\x1b[0m\x1b[3"
        "8;2;134;159;153m⢶\x1b[0m\x1b[38;2;112;138;127m"
        "⠷\x1b[0m\x1b[38;2;24;48;34m⣛\x1b[0m\x1b[38;2;100;124"
        ";108m⣳\x1b[0m\x1b[38;2;101;112;104m⣚\x1b[0m\x1b[38;2"
        ";101;117;104m⣑\x1b[0m\n  \x1b[38;2;62;70;55m⢿\x1b["
        "0m\x1b[38;2;73;76;65m⣿\x1b[0m\x1b[38;2;126;133;12"
        "6m⣿\x1b[0m\x1b[38;2;132;145;138m⣷\x1b[0m\x1b[38;2;81"
        ";102;95m⣺\x1b[0m\x1b[38;2;67;87;86m⣻\x1b[0m\x1b[38;2"
        ";109;130;135m⣬\x1b[0m\x1b[38;2;96;116;127m⣯\x1b[0"
        "m\x1b[38;2;182;182;184m⠵\x1b[0m\x1b[38;2;194;199;"
        "176m⢥\x1b[0m\x1b[38;2;57;66;63m⣶\x1b[0m\x1b[38;2;201"
        ";206;186m⣾\x1b[0m\x1b[38;2;132;129;114m⣶\x1b[0m\x1b["
        "38;2;189;214;185m⣿\x1b[0m\x1b[38;2;118;126;105"
        "m⣽\x1b[0m\x1b[38;2;167;172;150m⣿\x1b[0m\x1b[38;2;227"
        ";226;208m⣿\x1b[0m\x1b[38;2;183;191;170m⣿\x1b[0m\x1b["
        "38;2;167;179;165m⣿\x1b[0m\x1b[38;2;155;180;161"
        "m⣿\x1b[0m\x1b[38;2;163;183;171m⣿\x1b[0m\x1b[38;2;102"
        ";123;126m⣿\x1b[0m\x1b[38;2;188;203;196m⣮\x1b[0m\x1b["
        "38;2;202;210;195m⣿\x1b[0m\x1b[38;2;195;203;192"
        "m⣿\x1b[0m\x1b[38;2;175;190;187m⣿\x1b[0m\x1b[38;2;113"
        ";135;133m⣯\x1b[0m\x1b[38;2;116;130;139m⣿\x1b[0m\x1b["
        "38;2;183;200;190m⣿\x1b[0m\x1b[38;2;143;157;160"
        "m⣿\x1b[0m\x1b[38;2;220;230;231m⣷\x1b[0m\x1b[38;2;231"
        ";236;232m⣿\x1b[0m\x1b[38;2;209;210;202m⣷\x1b[0m\x1b["
        "38;2;192;192;182m⣿\x1b[0m\x1b[38;2;207;207;197"
        "m⣿\x1b[0m\x1b[38;2;93;105;95m⣿\x1b[0m\x1b[38;2;55;70"
        ";75m⣏\x1b[0m\x1b[38;2;78;89;91m⣿\x1b[0m\x1b[38;2;207"
        ";210;203m⡿\x1b[0m\x1b[38;2;205;196;189m⡿\x1b[0m\x1b["
        "38;2;199;189;188m⡿\x1b[0m\x1b[38;2;88;95;88m⣿\x1b"
        "[0m\x1b[38;2;187;191;190m⣿\x1b[0m\x1b[38;2;201;19"
        "7;185m⣷\x1b[0m\x1b[38;2;177;168;153m⠾\x1b[0m\x1b[38;"
        "2;26;39;29m⠯\x1b[0m\x1b[38;2;128;145;127m⡷\x1b[0m"
        "\x1b[38;2;129;134;127m⠿\x1b[0m\x1b[38;2;149;160;1"
        "54m⣹\x1b[0m\x1b[38;2;138;147;126m⣿\x1b[0m\x1b[38;2;4"
        "6;59;65m⠑\x1b[0m\x1b[38;2;103;126;116m⣿\x1b[0m\x1b[3"
        "8;2;102;128;117m⣾\x1b[0m\x1b[38;2;57;82;79m⢏\x1b["
        "0m\x1b[38;2;34;45;51m⡁\x1b[0m\x1b[38;2;76;87;91m⡌"
        "\x1b[0m\x1b[38;2;71;83;83m⡸\x1b[0m\x1b[38;2;56;67;63"
        "m⡩\x1b[0m\x1b[38;2;43;54;50m⡄\x1b[0m\x1b[38;2;59;69;"
        "68m⡥\x1b[0m\x1b[38;2;55;62;70m⣈\x1b[0m\x1b[38;2;48;5"
        "7;56m⠉\x1b[0m\x1b[38;2;45;55;57m⠐\x1b[0m\x1b[38;2;52"
        ";62;64m⠑\x1b[0m\x1b[38;2;58;69;71m⡀\x1b[0m\x1b[38;2;"
        "53;61;64m⠀\x1b[0m\x1b[38;2;52;58;58m⠒\x1b[0m\x1b[38;"
        "2;64;74;73m⢖\x1b[0m\x1b[38;2;50;62;62m⠒\x1b[0m\x1b[3"
        "8;2;50;58;60m⣂\x1b[0m\x1b[38;2;42;51;56m⠈\x1b[0m\x1b"
        "[38;2;35;45;46m⠉\x1b[0m\x1b[38;2;116;122;118m⠅"
        "\x1b[0m\x1b[38;2;44;54;55m⠈\x1b[0m\x1b[38;2;40;50;49"
        "m⠽\x1b[0m\x1b[38;2;50;60;59m⠛\x1b[0m\x1b[38;2;53;60;"
        "66m⢛\x1b[0m\x1b[38;2;195;204;203m⣿\x1b[0m\n  \x1b[38;"
        "2;136;144;129m⣿\x1b[0m\x1b[38;2;218;220;206m⣷\x1b"
        "[0m\x1b[38;2;221;221;209m⣿\x1b[0m\x1b[38;2;140;14"
        "5;141m⣿\x1b[0m\x1b[38;2;108;116;118m⣿\x1b[0m\x1b[38;"
        "2;36;44;29m⣯\x1b[0m\x1b[38;2;222;223;209m⣿\x1b[0m"
        "\x1b[38;2;205;207;206m⣷\x1b[0m\x1b[38;2;78;91;84m"
        "⠥\x1b[0m\x1b[38;2;127;140;133m⢥\x1b[0m\x1b[38;2;177;"
        "186;181m⣿\x1b[0m\x1b[38;2;170;179;178m⠿\x1b[0m\x1b[3"
        "8;2;137;137;147m⢿\x1b[0m\x1b[38;2;187;188;193m"
        "⣿\x1b[0m\x1b[38;2;181;182;177m⣿\x1b[0m\x1b[38;2;234;"
        "233;239m⣿\x1b[0m\x1b[38;2;211;211;211m⣿\x1b[0m\x1b[3"
        "8;2;203;208;204m⣾\x1b[0m\x1b[38;2;163;174;170m"
        "⣿\x1b[0m\x1b[38;2;120;140;129m⣿\x1b[0m\x1b[38;2;167;"
        "178;180m⣿\x1b[0m\x1b[38;2;209;220;204m⣿\x1b[0m\x1b[3"
        "8;2;193;195;192m⣿\x1b[0m\x1b[38;2;149;149;149m"
        "⣿\x1b[0m\x1b[38;2;194;203;186m⣿\x1b[0m\x1b[38;2;208;"
        "210;196m⣿\x1b[0m\x1b[38;2;114;129;110m⣿\x1b[0m\x1b[3"
        "8;2;157;164;146m⣯\x1b[0m\x1b[38;2;175;182;166m"
        "⣿\x1b[0m\x1b[38;2;123;146;128m⣿\x1b[0m\x1b[38;2;182;"
        "192;183m⣿\x1b[0m\x1b[38;2;156;172;169m⣿\x1b[0m\x1b[3"
        "8;2;214;224;223m⣿\x1b[0m\x1b[38;2;166;176;177m"
        "⣿\x1b[0m\x1b[38;2;58;68;69m⠛\x1b[0m\x1b[38;2;36;50;5"
        "0m⣏\x1b[0m\x1b[38;2;53;66;72m⣛\x1b[0m\x1b[38;2;19;31"
        ";31m⢫\x1b[0m\x1b[38;2;162;172;171m⡷\x1b[0m\x1b[38;2;"
        "119;137;137m⣽\x1b[0m\x1b[38;2;87;98;100m⣷\x1b[0m\x1b"
        "[38;2;98;107;112m⣿\x1b[0m\x1b[38;2;78;94;93m⣷\x1b"
        "[0m\x1b[38;2;70;85;78m⣿\x1b[0m\x1b[38;2;84;100;90"
        "m⢷\x1b[0m\x1b[38;2;122;135;126m⣺\x1b[0m\x1b[38;2;79;"
        "93;80m⡯\x1b[0m\x1b[38;2;87;99;99m⠪\x1b[0m\x1b[38;2;7"
        "4;91;85m⣮\x1b[0m\x1b[38;2;38;51;42m⠚\x1b[0m\x1b[38;2"
        ";52;65;56m⢹\x1b[0m\x1b[38;2;92;107;86m⢽\x1b[0m\x1b[3"
        "8;2;81;92;84m⣿\x1b[0m\x1b[38;2;107;136;116m⣿\x1b["
        "0m\x1b[38;2;120;145;123m⣷\x1b[0m\x1b[38;2;176;182"
        ";178m⣿\x1b[0m\x1b[38;2;37;55;43m⣿\x1b[0m\x1b[38;2;76"
        ";101;72m⣿\x1b[0m\x1b[38;2;3;35;14m⣟\x1b[0m\x1b[38;2;"
        "41;64;46m⣻\x1b[0m\x1b[38;2;113;138;99m⣶\x1b[0m\x1b[3"
        "8;2;88;109;92m⣶\x1b[0m\x1b[38;2;93;113;88m⡦\x1b[0"
        "m\x1b[38;2;39;45;41m⠀\x1b[0m\x1b[38;2;50;59;56m⢀\x1b"
        "[0m\x1b[38;2;45;58;49m⠠\x1b[0m\x1b[38;2;44;61;51m"
        "⢸\x1b[0m\x1b[38;2;101;125;93m⣤\x1b[0m\x1b[38;2;115;1"
        "30;87m⣾\x1b[0m\x1b[38;2;31;41;32m⡔\x1b[0m\x1b[38;2;1"
        "08;121;112m⡗\x1b[0m\x1b[38;2;37;50;41m⣐\x1b[0m\x1b[3"
        "8;2;41;47;43m⣀\x1b[0m\x1b[38;2;49;55;55m⠂\x1b[0m\x1b"
        "[38;2;44;49;52m⠀\x1b[0m\x1b[38;2;28;33;36m⠀\x1b[0"
        "m\x1b[38;2;46;51;47m⣭\x1b[0m\x1b[38;2;61;68;61m⠖\x1b"
        "[0m\n  \x1b[38;2;38;36;39m⣟\x1b[0m\x1b[38;2;111;12"
        "0;99m⢻\x1b[0m\x1b[38;2;125;133;135m⡟\x1b[0m\x1b[38;2"
        ";120;121;123m⢟\x1b[0m\x1b[38;2;125;127;116m⣿\x1b["
        "0m\x1b[38;2;119;117;104m⣷\x1b[0m\x1b[38;2;160;157"
        ";140m⣿\x1b[0m\x1b[38;2;103;104;86m⣿\x1b[0m\x1b[38;2;"
        "164;172;159m⣯\x1b[0m\x1b[38;2;97;108;102m⣰\x1b[0m"
        "\x1b[38;2;64;71;63m⣾\x1b[0m\x1b[38;2;111;117;117m"
        "⡿\x1b[0m\x1b[38;2;110;118;120m⣿\x1b[0m\x1b[38;2;76;8"
        "4;86m⣿\x1b[0m\x1b[38;2;94;103;98m⡿\x1b[0m\x1b[38;2;1"
        "49;160;143m⣿\x1b[0m\x1b[38;2;69;85;72m⡞\x1b[0m\x1b[3"
        "8;2;127;139;127m⡟\x1b[0m\x1b[38;2;107;128;113m"
        "⣿\x1b[0m\x1b[38;2;180;186;172m⣿\x1b[0m\x1b[38;2;171;"
        "178;160m⣿\x1b[0m\x1b[38;2;183;182;162m⢿\x1b[0m\x1b[3"
        "8;2;189;186;181m⡿\x1b[0m\x1b[38;2;195;199;200m"
        "⣿\x1b[0m\x1b[38;2;103;106;97m⡿\x1b[0m\x1b[38;2;177;1"
        "77;167m⠿\x1b[0m\x1b[38;2;50;59;64m⢯\x1b[0m\x1b[38;2;"
        "49;65;54m⣝\x1b[0m\x1b[38;2;65;82;66m⣿\x1b[0m\x1b[38;"
        "2;162;172;147m⣷\x1b[0m\x1b[38;2;199;203;188m⣿\x1b"
        "[0m\x1b[38;2;189;190;172m⣿\x1b[0m\x1b[38;2;144;14"
        "7;136m⣟\x1b[0m\x1b[38;2;73;91;77m⣾\x1b[0m\x1b[38;2;1"
        "47;162;155m⣷\x1b[0m\x1b[38;2;56;77;80m⢻\x1b[0m\x1b[3"
        "8;2;96;111;116m⣿\x1b[0m\x1b[38;2;47;57;66m⣟\x1b[0"
        "m\x1b[38;2;41;50;55m⣫\x1b[0m\x1b[38;2;162;175;184"
        "m⣿\x1b[0m\x1b[38;2;34;44;43m⣟\x1b[0m\x1b[38;2;65;74;"
        "71m⣿\x1b[0m\x1b[38;2;89;105;94m⣿\x1b[0m\x1b[38;2;89;"
        "106;100m⣿\x1b[0m\x1b[38;2;117;134;124m⣿\x1b[0m\x1b[3"
        "8;2;112;129;119m⡏\x1b[0m\x1b[38;2;57;78;71m⡯\x1b["
        "0m\x1b[38;2;55;79;66m⡽\x1b[0m\x1b[38;2;62;79;73m⣝"
        "\x1b[0m\x1b[38;2;43;60;54m⠉\x1b[0m\x1b[38;2;75;91;91"
        "m⠭\x1b[0m\x1b[38;2;163;173;185m⣿\x1b[0m\x1b[38;2;119"
        ";121;100m⣿\x1b[0m\x1b[38;2;87;100;82m⣿\x1b[0m\x1b[38"
        ";2;96;111;114m⣿\x1b[0m\x1b[38;2;33;47;47m⠿\x1b[0m"
        "\x1b[38;2;46;57;53m⠿\x1b[0m\x1b[38;2;173;184;178m"
        "⢻\x1b[0m\x1b[38;2;224;231;223m⣿\x1b[0m\x1b[38;2;230;"
        "229;245m⣿\x1b[0m\x1b[38;2;192;185;177m⣿\x1b[0m\x1b[3"
        "8;2;111;117;105m⣷\x1b[0m\x1b[38;2;57;68;60m⣯\x1b["
        "0m\x1b[38;2;113;120;130m⣏\x1b[0m\x1b[38;2;41;47;4"
        "7m⣙\x1b[0m\x1b[38;2;99;114;107m⣶\x1b[0m\x1b[38;2;20;"
        "24;33m⠈\x1b[0m\x1b[38;2;49;59;60m⡻\x1b[0m\x1b[38;2;6"
        "0;69;64m⢺\x1b[0m\x1b[38;2;130;140;129m⡿\x1b[0m\x1b[3"
        "8;2;187;195;198m⠿\x1b[0m\x1b[38;2;50;59;56m⣿\x1b["
        "0m\x1b[38;2;93;103;94m⣻\x1b[0m\x1b[38;2;157;166;1"
        "61m⣷\x1b[0m\x1b[38;2;69;85;75m⣇\x1b[0m\x1b[38;2;34;5"
        "0;37m⢥\x1b[0m\x1b[38;2;45;57;45m⣗\x1b[0m\x1b[38;2;24"
        "3;251;236m⣿\x1b[0m\n  \x1b[38;2;35;142;162m⣿\x1b[0"
        "m\x1b[38;2;77;166;184m⣯\x1b[0m\x1b[38;2;110;175;1"
        "97m⣿\x1b[0m\x1b[38;2;104;179;202m⣭\x1b[0m\x1b[38;2;9"
        "1;183;204m⣿\x1b[0m\x1b[38;2;82;177;197m⣿\x1b[0m\x1b["
        "38;2;88;176;198m⣿\x1b[0m\x1b[38;2;56;155;174m⣯"
        "\x1b[0m\x1b[38;2;90;183;200m⣿\x1b[0m\x1b[38;2;148;19"
        "1;210m⣿\x1b[0m\x1b[38;2;103;186;200m⣿\x1b[0m\x1b[38;"
        "2;80;176;192m⣯\x1b[0m\x1b[38;2;17;140;158m⣬\x1b[0"
        "m\x1b[38;2;43;155;177m⣿\x1b[0m\x1b[38;2;71;156;17"
        "6m⣿\x1b[0m\x1b[38;2;59;118;132m⣿\x1b[0m\x1b[38;2;63;"
        "110;126m⣿\x1b[0m\x1b[38;2;186;200;211m⣿\x1b[0m\x1b[3"
        "8;2;115;130;125m⢿\x1b[0m\x1b[38;2;53;68;61m⣣\x1b["
        "0m\x1b[38;2;162;164;153m⣭\x1b[0m\x1b[38;2;102;108"
        ";106m⣼\x1b[0m\x1b[38;2;18;23;26m⣷\x1b[0m\x1b[38;2;48"
        ";53;57m⢟\x1b[0m\x1b[38;2;127;129;124m⣥\x1b[0m\x1b[38"
        ";2;105;108;89m⣾\x1b[0m\x1b[38;2;70;79;60m⣿\x1b[0m"
        "\x1b[38;2;60;71;63m⣟\x1b[0m\x1b[38;2;70;93;75m⣿\x1b["
        "0m\x1b[38;2;96;123;104m⣿\x1b[0m\x1b[38;2;63;101;7"
        "8m⣭\x1b[0m\x1b[38;2;87;115;93m⣿\x1b[0m\x1b[38;2;81;1"
        "09;94m⣿\x1b[0m\x1b[38;2;170;181;175m⣿\x1b[0m\x1b[38;"
        "2;110;121;107m⣿\x1b[0m\x1b[38;2;156;154;139m⣿\x1b"
        "[0m\x1b[38;2;189;188;170m⣷\x1b[0m\x1b[38;2;180;18"
        "9;172m⢯\x1b[0m\x1b[38;2;92;110;114m⣽\x1b[0m\x1b[38;2"
        ";151;164;173m⣿\x1b[0m\x1b[38;2;195;196;200m⣿\x1b["
        "0m\x1b[38;2;161;163;178m⣿\x1b[0m\x1b[38;2;127;134"
        ";140m⡿\x1b[0m\x1b[38;2;213;234;229m⢷\x1b[0m\x1b[38;2"
        ";181;170;178m⣷\x1b[0m\x1b[38;2;183;177;179m⣽\x1b["
        "0m\x1b[38;2;190;183;199m⣷\x1b[0m\x1b[38;2;157;154"
        ";163m⣾\x1b[0m\x1b[38;2;147;160;169m⣶\x1b[0m\x1b[38;2"
        ";182;184;196m⡯\x1b[0m\x1b[38;2;122;124;136m⣿\x1b["
        "0m\x1b[38;2;156;165;174m⠿\x1b[0m\x1b[38;2;179;190"
        ";194m⣽\x1b[0m\x1b[38;2;46;53;59m⣯\x1b[0m\x1b[38;2;16"
        "3;178;181m⣿\x1b[0m\x1b[38;2;156;167;171m⡿\x1b[0m\x1b"
        "[38;2;95;108;116m⠿\x1b[0m\x1b[38;2;29;42;50m⠙\x1b"
        "[0m\x1b[38;2;41;54;62m⠛\x1b[0m\x1b[38;2;99;106;11"
        "4m⣹\x1b[0m\x1b[38;2;134;139;145m⡽\x1b[0m\x1b[38;2;83"
        ";97;98m⡿\x1b[0m\x1b[38;2;167;168;170m⠭\x1b[0m\x1b[38"
        ";2;29;41;41m⠙\x1b[0m\x1b[38;2;168;170;183m⠻\x1b[0"
        "m\x1b[38;2;191;193;206m⣿\x1b[0m\x1b[38;2;168;169;"
        "161m⣝\x1b[0m\x1b[38;2;40;49;44m⣳\x1b[0m\x1b[38;2;97;"
        "101;104m⣿\x1b[0m\x1b[38;2;38;49;43m⡿\x1b[0m\x1b[38;2"
        ";152;157;161m⣿\x1b[0m\x1b[38;2;156;161;165m⣿\x1b["
        "0m\x1b[38;2;128;139;143m⣿\x1b[0m\x1b[38;2;191;201"
        ";202m⡻\x1b[0m\x1b[38;2;158;167;174m⣿\x1b[0m\x1b[38;2"
        ";39;32;40m⣗\x1b[0m\x1b[38;2;106;115;120m⡶\x1b[0m\x1b"
        "[38;2;96;106;108m⣿\x1b[0m\n  \x1b[38;2;100;178;"
        "200m⣿\x1b[0m\x1b[38;2;114;186;210m⣿\x1b[0m\x1b[38;2;"
        "107;183;206m⣿\x1b[0m\x1b[38;2;103;179;202m⣿\x1b[0"
        "m\x1b[38;2;95;180;200m⣿\x1b[0m\x1b[38;2;97;182;20"
        "2m⣿\x1b[0m\x1b[38;2;103;183;206m⣿\x1b[0m\x1b[38;2;10"
        "2;187;208m⣿\x1b[0m\x1b[38;2;88;183;205m⣿\x1b[0m\x1b["
        "38;2;100;188;208m⣿\x1b[0m\x1b[38;2;107;192;212"
        "m⣿\x1b[0m\x1b[38;2;113;191;213m⣿\x1b[0m\x1b[38;2;120"
        ";189;205m⣿\x1b[0m\x1b[38;2;128;193;211m⣿\x1b[0m\x1b["
        "38;2;143;194;213m⣿\x1b[0m\x1b[38;2;151;198;214"
        "m⣿\x1b[0m\x1b[38;2;166;199;218m⣿\x1b[0m\x1b[38;2;166"
        ";202;216m⣿\x1b[0m\x1b[38;2;166;200;210m⣿\x1b[0m\x1b["
        "38;2;164;200;212m⣿\x1b[0m\x1b[38;2;163;200;209"
        "m⣿\x1b[0m\x1b[38;2;143;190;210m⣾\x1b[0m\x1b[38;2;140"
        ";197;214m⣷\x1b[0m\x1b[38;2;97;186;202m⣯\x1b[0m\x1b[3"
        "8;2;112;181;196m⣭\x1b[0m\x1b[38;2;83;151;164m⣽"
        "\x1b[0m\x1b[38;2;37;104;121m⣾\x1b[0m\x1b[38;2;21;71;"
        "82m⣟\x1b[0m\x1b[38;2;17;49;60m⣛\x1b[0m\x1b[38;2;35;6"
        "5;73m⣛\x1b[0m\x1b[38;2;55;84;92m⣹\x1b[0m\x1b[38;2;27"
        ";52;48m⢋\x1b[0m\x1b[38;2;106;118;118m⣼\x1b[0m\x1b[38"
        ";2;112;124;120m⢽\x1b[0m\x1b[38;2;54;71;61m⠻\x1b[0"
        "m\x1b[38;2;92;107;88m⡯\x1b[0m\x1b[38;2;82;97;90m⣛"
        "\x1b[0m\x1b[38;2;120;127;109m⢿\x1b[0m\x1b[38;2;96;10"
        "3;85m⡿\x1b[0m\x1b[38;2;157;161;147m⢻\x1b[0m\x1b[38;2"
        ";203;210;192m⡿\x1b[0m\x1b[38;2;189;195;181m⡾\x1b["
        "0m\x1b[38;2;128;133;126m⣿\x1b[0m\x1b[38;2;161;145"
        ";155m⣿\x1b[0m\x1b[38;2;152;148;163m⣿\x1b[0m\x1b[38;2"
        ";164;169;172m⣿\x1b[0m\x1b[38;2;244;233;241m⣿\x1b["
        "0m\x1b[38;2;180;204;204m⣟\x1b[0m\x1b[38;2;151;148"
        ";155m⣿\x1b[0m\x1b[38;2;89;109;108m⣟\x1b[0m\x1b[38;2;"
        "179;190;192m⣿\x1b[0m\x1b[38;2;171;187;202m⣿\x1b[0"
        "m\x1b[38;2;56;62;60m⣟\x1b[0m\x1b[38;2;101;109;112"
        "m⡿\x1b[0m\x1b[38;2;78;81;86m⡫\x1b[0m\x1b[38;2;203;21"
        "1;213m⠞\x1b[0m\x1b[38;2;239;243;246m⠻\x1b[0m\x1b[38;"
        "2;175;176;178m⢽\x1b[0m\x1b[38;2;51;46;50m⣿\x1b[0m"
        "\x1b[38;2;33;42;49m⣿\x1b[0m\x1b[38;2;136;129;137m"
        "⣿\x1b[0m\x1b[38;2;139;140;145m⡿\x1b[0m\x1b[38;2;105;"
        "108;113m⣿\x1b[0m\x1b[38;2;170;160;169m⣿\x1b[0m\x1b[3"
        "8;2;69;69;81m⣿\x1b[0m\x1b[38;2;75;80;84m⣿\x1b[0m\x1b"
        "[38;2;103;102;107m⣿\x1b[0m\x1b[38;2;154;158;16"
        "1m⠿\x1b[0m\x1b[38;2;91;94;99m⢻\x1b[0m\x1b[38;2;131;1"
        "34;139m⣿\x1b[0m\x1b[38;2;106;120;123m⣻\x1b[0m\x1b[38"
        ";2;96;101;104m⣿\x1b[0m\x1b[38;2;88;96;98m⣏\x1b[0m"
        "\x1b[38;2;117;118;122m⣬\x1b[0m\x1b[38;2;151;149;1"
        "62m⣽\x1b[0m\x1b[38;2;38;41;50m⣷\x1b[0m\x1b[38;2;140;"
        "143;150m⣭\x1b[0m\x1b[38;2;186;195;202m⡿\x1b[0m\n  "
        "\x1b[38;2;74;174;198m⣿\x1b[0m\x1b[38;2;74;172;197"
        "m⣿\x1b[0m\x1b[38;2;92;185;203m⣿\x1b[0m\x1b[38;2;102;"
        "182;205m⣿\x1b[0m\x1b[38;2;101;176;199m⣿\x1b[0m\x1b[3"
        "8;2;84;175;193m⣿\x1b[0m\x1b[38;2;82;182;198m⣿\x1b"
        "[0m\x1b[38;2;87;175;195m⣿\x1b[0m\x1b[38;2;98;179;"
        "208m⣿\x1b[0m\x1b[38;2;100;181;210m⣿\x1b[0m\x1b[38;2;"
        "99;185;210m⣿\x1b[0m\x1b[38;2;96;181;202m⣿\x1b[0m\x1b"
        "[38;2;107;185;207m⣿\x1b[0m\x1b[38;2;112;187;20"
        "8m⣿\x1b[0m\x1b[38;2;116;187;205m⣿\x1b[0m\x1b[38;2;12"
        "5;177;198m⣿\x1b[0m\x1b[38;2;139;195;210m⣿\x1b[0m\x1b"
        "[38;2;135;193;207m⣿\x1b[0m\x1b[38;2;149;195;21"
        "1m⣿\x1b[0m\x1b[38;2;148;194;210m⣿\x1b[0m\x1b[38;2;14"
        "3;195;209m⣿\x1b[0m\x1b[38;2;144;197;215m⣿\x1b[0m\x1b"
        "[38;2;142;195;213m⣿\x1b[0m\x1b[38;2;141;190;20"
        "5m⣿\x1b[0m\x1b[38;2;151;200;215m⣿\x1b[0m\x1b[38;2;15"
        "4;198;211m⣿\x1b[0m\x1b[38;2;156;202;218m⣿\x1b[0m\x1b"
        "[38;2;153;202;217m⣿\x1b[0m\x1b[38;2;149;200;21"
        "9m⣿\x1b[0m\x1b[38;2;130;202;226m⣿\x1b[0m\x1b[38;2;14"
        "1;199;219m⣿\x1b[0m\x1b[38;2;134;204;216m⣿\x1b[0m\x1b"
        "[38;2;124;192;205m⣿\x1b[0m\x1b[38;2;106;199;21"
        "6m⣿\x1b[0m\x1b[38;2;115;198;214m⣿\x1b[0m\x1b[38;2;12"
        "0;189;204m⣿\x1b[0m\x1b[38;2;109;191;212m⣷\x1b[0m\x1b"
        "[38;2;105;181;204m⣶\x1b[0m\x1b[38;2;67;178;198"
        "m⣾\x1b[0m\x1b[38;2;80;181;201m⣥\x1b[0m\x1b[38;2;31;5"
        "4;68m⣤\x1b[0m\x1b[38;2;36;50;59m⣀\x1b[0m\x1b[38;2;43"
        ";55;67m⣩\x1b[0m\x1b[38;2;44;62;74m⣿\x1b[0m\x1b[38;2;"
        "69;90;93m⣛\x1b[0m\x1b[38;2;49;63;66m⣿\x1b[0m\x1b[38;"
        "2;80;97;104m⣿\x1b[0m\x1b[38;2;147;163;163m⣿\x1b[0"
        "m\x1b[38;2;38;54;51m⣟\x1b[0m\x1b[38;2;12;32;41m⣃\x1b"
        "[0m\x1b[38;2;69;98;116m⣳\x1b[0m\x1b[38;2;112;159;"
        "177m⣮\x1b[0m\x1b[38;2;82;133;154m⣽\x1b[0m\x1b[38;2;1"
        "26;169;186m⣮\x1b[0m\x1b[38;2;60;132;147m⣭\x1b[0m\x1b"
        "[38;2;70;120;145m⣯\x1b[0m\x1b[38;2;65;138;155m"
        "⣧\x1b[0m\x1b[38;2;78;141;159m⣦\x1b[0m\x1b[38;2;80;15"
        "3;168m⣤\x1b[0m\x1b[38;2;71;128;148m⣥\x1b[0m\x1b[38;2"
        ";94;154;165m⣾\x1b[0m\x1b[38;2;81;152;170m⣼\x1b[0m"
        "\x1b[38;2;56;127;149m⣦\x1b[0m\x1b[38;2;78;124;139"
        "m⣬\x1b[0m\x1b[38;2;89;126;144m⣝\x1b[0m\x1b[38;2;81;1"
        "29;143m⣵\x1b[0m\x1b[38;2;79;126;146m⣦\x1b[0m\x1b[38;"
        "2;38;79;97m⣤\x1b[0m\x1b[38;2;86;137;154m⣶\x1b[0m\x1b"
        "[38;2;17;51;60m⣺\x1b[0m\x1b[38;2;40;72;93m⣽\x1b[0"
        "m\x1b[38;2;77;118;136m⣭\x1b[0m\x1b[38;2;35;56;75m"
        "⣍\x1b[0m\x1b[38;2;29;39;51m⣉\x1b[0m\x1b[38;2;22;25;4"
        "0m⣉\x1b[0m\x1b[38;2;27;33;47m⠛\x1b[0m\x1b[38;2;28;35"
        ";45m⣋\x1b[0m\x1b[38;2;0;8;23m⢑\x1b[0m\n  \x1b[38;2;43"
        ";168;196m⣿\x1b[0m\x1b[38;2;32;157;185m⣿\x1b[0m\x1b[3"
        "8;2;65;176;203m⣿\x1b[0m\x1b[38;2;38;156;186m⣿\x1b"
        "[0m\x1b[38;2;38;166;193m⣿\x1b[0m\x1b[38;2;39;167;"
        "194m⣿\x1b[0m\x1b[38;2;33;157;181m⣿\x1b[0m\x1b[38;2;4"
        "3;167;191m⣿\x1b[0m\x1b[38;2;55;170;197m⣿\x1b[0m\x1b["
        "38;2;70;176;202m⣿\x1b[0m\x1b[38;2;78;180;205m⣿"
        "\x1b[0m\x1b[38;2;76;178;203m⣿\x1b[0m\x1b[38;2;68;177"
        ";200m⣿\x1b[0m\x1b[38;2;73;177;202m⣿\x1b[0m\x1b[38;2;"
        "70;176;198m⣿\x1b[0m\x1b[38;2;73;175;198m⣿\x1b[0m\x1b"
        "[38;2;89;188;211m⣿\x1b[0m\x1b[38;2;100;188;210"
        "m⣿\x1b[0m\x1b[38;2;116;197;218m⣿\x1b[0m\x1b[38;2;111"
        ";186;209m⣿\x1b[0m\x1b[38;2;120;193;212m⣿\x1b[0m\x1b["
        "38;2;109;182;201m⣿\x1b[0m\x1b[38;2;118;195;213"
        "m⣿\x1b[0m\x1b[38;2;136;199;217m⣿\x1b[0m\x1b[38;2;146"
        ";204;224m⣿\x1b[0m\x1b[38;2;133;193;217m⣿\x1b[0m\x1b["
        "38;2;118;191;210m⣿\x1b[0m\x1b[38;2;116;193;213"
        "m⠿\x1b[0m\x1b[38;2;116;193;213m⣿\x1b[0m\x1b[38;2;106"
        ";193;212m⣿\x1b[0m\x1b[38;2;93;188;208m⣿\x1b[0m\x1b[3"
        "8;2;86;186;202m⣿\x1b[0m\x1b[38;2;93;188;206m⣿\x1b"
        "[0m\x1b[38;2;88;185;201m⣿\x1b[0m\x1b[38;2;102;187"
        ";207m⣿\x1b[0m\x1b[38;2;82;184;206m⣿\x1b[0m\x1b[38;2;"
        "63;180;197m⣿\x1b[0m\x1b[38;2;95;199;224m⣿\x1b[0m\x1b"
        "[38;2;82;185;204m⣿\x1b[0m\x1b[38;2;87;192;211m"
        "⣿\x1b[0m\x1b[38;2;84;181;198m⣿\x1b[0m\x1b[38;2;118;1"
        "89;207m⣿\x1b[0m\x1b[38;2;112;185;200m⣿\x1b[0m\x1b[38"
        ";2;138;201;219m⣿\x1b[0m\x1b[38;2;139;188;205m⣿"
        "\x1b[0m\x1b[38;2;134;186;208m⣿\x1b[0m\x1b[38;2;146;1"
        "93;213m⣿\x1b[0m\x1b[38;2;129;182;198m⣿\x1b[0m\x1b[38"
        ";2;133;186;202m⣿\x1b[0m\x1b[38;2;150;196;212m⣿"
        "\x1b[0m\x1b[38;2;144;190;206m⣿\x1b[0m\x1b[38;2;138;1"
        "89;206m⣿\x1b[0m\x1b[38;2;121;177;192m⣿\x1b[0m\x1b[38"
        ";2;116;181;201m⣿\x1b[0m\x1b[38;2;107;179;201m⣿"
        "\x1b[0m\x1b[38;2;96;173;193m⣿\x1b[0m\x1b[38;2;92;170"
        ";190m⣿\x1b[0m\x1b[38;2;81;168;185m⣿\x1b[0m\x1b[38;2;"
        "74;166;181m⣿\x1b[0m\x1b[38;2;79;159;182m⣿\x1b[0m\x1b"
        "[38;2;59;160;178m⣿\x1b[0m\x1b[38;2;61;158;177m"
        "⣿\x1b[0m\x1b[38;2;69;168;189m⣿\x1b[0m\x1b[38;2;84;16"
        "6;187m⣿\x1b[0m\x1b[38;2;62;151;167m⣿\x1b[0m\x1b[38;2"
        ";92;167;188m⣿\x1b[0m\x1b[38;2;71;159;179m⣿\x1b[0m"
        "\x1b[38;2;95;163;184m⣿\x1b[0m\x1b[38;2;77;152;173"
        "m⣿\x1b[0m\x1b[38;2;76;154;174m⣿\x1b[0m\x1b[38;2;88;1"
        "59;181m⣿\x1b[0m\x1b[38;2;77;152;173m⣿\x1b[0m\x1b[38;"
        "2;55;142;161m⣿\x1b[0m\x1b[38;2;69;147;169m⣿\x1b[0"
        "m\x1b[38;2;58;143;164m⣿\x1b[0m\x1b[38;2;69;147;17"
        "0m⣿\x1b[0m\x1b[38;2;67;144;164m⣿\x1b[0m\x1b[38;2;64;"
        "145;164m⣿\x1b[0m\n  \x1b[38;2;10;147;179m⣿\x1b[0m\x1b"
        "[38;2;14;148;177m⣿\x1b[0m\x1b[38;2;5;144;173m⣿"
        "\x1b[0m\x1b[38;2;16;151;181m⣿\x1b[0m\x1b[38;2;14;149"
        ";181m⣿\x1b[0m\x1b[38;2;11;146;178m⣿\x1b[0m\x1b[38;2;"
        "14;155;182m⣿\x1b[0m\x1b[38;2;15;156;183m⣿\x1b[0m\x1b"
        "[38;2;21;160;189m⣿\x1b[0m\x1b[38;2;21;160;189m"
        "⣿\x1b[0m\x1b[38;2;12;152;177m⣿\x1b[0m\x1b[38;2;24;16"
        "8;192m⣿\x1b[0m\x1b[38;2;21;165;189m⣿\x1b[0m\x1b[38;2"
        ";23;163;188m⣿\x1b[0m\x1b[38;2;34;175;195m⣿\x1b[0m"
        "\x1b[38;2;24;169;188m⣿\x1b[0m\x1b[38;2;55;175;199"
        "m⣿\x1b[0m\x1b[38;2;52;164;186m⣿\x1b[0m\x1b[38;2;53;1"
        "70;190m⣿\x1b[0m\x1b[38;2;72;179;199m⣿\x1b[0m\x1b[38;"
        "2;80;179;200m⣿\x1b[0m\x1b[38;2;67;167;190m⣿\x1b[0"
        "m\x1b[38;2;87;183;199m⡿\x1b[0m\x1b[38;2;162;154;1"
        "43m⠿\x1b[0m\x1b[38;2;47;67;56m⢫\x1b[0m\x1b[38;2;35;5"
        "5;44m⣁\x1b[0m\x1b[38;2;80;85;63m⠑\x1b[0m\x1b[38;2;87"
        ";71;37m⢶\x1b[0m\x1b[38;2;59;54;34m⣺\x1b[0m\x1b[38;2;"
        "58;79;74m⣫\x1b[0m\x1b[38;2;86;72;37m⣽\x1b[0m\x1b[38;"
        "2;123;125;104m⢿\x1b[0m\x1b[38;2;15;162;178m⣿\x1b["
        "0m\x1b[38;2;37;186;206m⣿\x1b[0m\x1b[38;2;37;173;1"
        "97m⣿\x1b[0m\x1b[38;2;26;171;198m⣿\x1b[0m\x1b[38;2;27"
        ";171;198m⣿\x1b[0m\x1b[38;2;32;178;203m⣿\x1b[0m\x1b[3"
        "8;2;26;166;189m⣿\x1b[0m\x1b[38;2;37;173;189m⣿\x1b"
        "[0m\x1b[38;2;66;161;181m⣿\x1b[0m\x1b[38;2;83;180;"
        "197m⣿\x1b[0m\x1b[38;2;107;175;198m⣿\x1b[0m\x1b[38;2;"
        "113;188;209m⣿\x1b[0m\x1b[38;2;106;181;202m⣿\x1b[0"
        "m\x1b[38;2;98;173;196m⣿\x1b[0m\x1b[38;2;110;185;2"
        "08m⣿\x1b[0m\x1b[38;2;107;178;196m⣿\x1b[0m\x1b[38;2;1"
        "06;177;195m⣿\x1b[0m\x1b[38;2;95;174;191m⣿\x1b[0m\x1b"
        "[38;2;98;177;194m⣿\x1b[0m\x1b[38;2;92;173;192m"
        "⣿\x1b[0m\x1b[38;2;85;170;191m⣿\x1b[0m\x1b[38;2;70;15"
        "7;177m⣿\x1b[0m\x1b[38;2;70;173;188m⣿\x1b[0m\x1b[38;2"
        ";68;163;185m⣿\x1b[0m\x1b[38;2;53;157;182m⣿\x1b[0m"
        "\x1b[38;2;47;155;181m⣿\x1b[0m\x1b[38;2;33;147;173"
        "m⣿\x1b[0m\x1b[38;2;26;152;174m⣿\x1b[0m\x1b[38;2;38;1"
        "64;187m⣿\x1b[0m\x1b[38;2;21;143;167m⣿\x1b[0m\x1b[38;"
        "2;8;134;159m⣿\x1b[0m\x1b[38;2;25;144;168m⣿\x1b[0m"
        "\x1b[38;2;25;146;165m⣿\x1b[0m\x1b[38;2;9;138;159m"
        "⣿\x1b[0m\x1b[38;2;11;143;158m⣿\x1b[0m\x1b[38;2;44;15"
        "6;180m⣿\x1b[0m\x1b[38;2;20;122;144m⣿\x1b[0m\x1b[38;2"
        ";1;110;130m⣿\x1b[0m\x1b[38;2;37;141;166m⣿\x1b[0m\x1b"
        "[38;2;42;137;165m⣿\x1b[0m\x1b[38;2;19;125;147m"
        "⣿\x1b[0m\x1b[38;2;18;119;139m⣿\x1b[0m\x1b[38;2;39;14"
        "1;166m⣿\x1b[0m\x1b[38;2;29;131;156m⣿\x1b[0m\x1b[38;2"
        ";7;107;130m⣿\x1b[0m\x1b[38;2;2;107;128m⣿\x1b[0m\n "
        " \x1b[38;2;17;135;165m⣿\x1b[0m\x1b[38;2;12;133;16"
        "2m⣿\x1b[0m\x1b[38;2;18;147;178m⣿\x1b[0m\x1b[38;2;17;"
        "146;177m⣿\x1b[0m\x1b[38;2;14;143;174m⣿\x1b[0m\x1b[38"
        ";2;0;121;152m⣿\x1b[0m\x1b[38;2;4;133;164m⣿\x1b[0m"
        "\x1b[38;2;5;134;165m⣿\x1b[0m\x1b[38;2;9;139;173m⣿"
        "\x1b[0m\x1b[38;2;10;149;180m⣿\x1b[0m\x1b[38;2;6;141;"
        "173m⣿\x1b[0m\x1b[38;2;4;139;171m⣿\x1b[0m\x1b[38;2;10"
        ";141;171m⣿\x1b[0m\x1b[38;2;2;133;163m⣿\x1b[0m\x1b[38"
        ";2;6;147;177m⣿\x1b[0m\x1b[38;2;3;146;176m⣿\x1b[0m"
        "\x1b[38;2;13;164;181m⣿\x1b[0m\x1b[38;2;0;158;206m"
        "⣿\x1b[0m\x1b[38;2;14;166;151m⣿\x1b[0m\x1b[38;2;98;45"
        ";51m⡿\x1b[0m\x1b[38;2;163;153;141m⠯\x1b[0m\x1b[38;2;"
        "196;194;171m⣵\x1b[0m\x1b[38;2;167;171;148m⠶\x1b[0"
        "m\x1b[38;2;155;157;154m⠿\x1b[0m\x1b[38;2;127;132;"
        "110m⢧\x1b[0m\x1b[38;2;41;50;45m⠎\x1b[0m\x1b[38;2;62;"
        "69;77m⠀\x1b[0m\x1b[38;2;17;21;30m⠀\x1b[0m\x1b[38;2;3"
        "6;40;49m⠀\x1b[0m\x1b[38;2;47;49;46m⠛\x1b[0m\x1b[38;2"
        ";41;46;49m⢟\x1b[0m\x1b[38;2;106;105;87m⣿\x1b[0m\x1b["
        "38;2;94;93;75m⣿\x1b[0m\x1b[38;2;23;27;26m⣿\x1b[0m"
        "\x1b[38;2;46;58;36m⡿\x1b[0m\x1b[38;2;108;168;158m"
        "⣿\x1b[0m\x1b[38;2;7;168;197m⣿\x1b[0m\x1b[38;2;15;165"
        ";198m⣿\x1b[0m\x1b[38;2;19;163;189m⣿\x1b[0m\x1b[38;2;"
        "14;154;177m⣿\x1b[0m\x1b[38;2;42;174;195m⣿\x1b[0m\x1b"
        "[38;2;47;166;186m⣿\x1b[0m\x1b[38;2;70;179;199m"
        "⣿\x1b[0m\x1b[38;2;73;169;193m⣿\x1b[0m\x1b[38;2;81;18"
        "1;204m⣿\x1b[0m\x1b[38;2;76;179;198m⣿\x1b[0m\x1b[38;2"
        ";62;172;189m⣿\x1b[0m\x1b[38;2;74;179;201m⣿\x1b[0m"
        "\x1b[38;2;69;174;196m⣿\x1b[0m\x1b[38;2;60;170;187"
        "m⣿\x1b[0m\x1b[38;2;48;160;180m⣿\x1b[0m\x1b[38;2;39;1"
        "59;184m⣿\x1b[0m\x1b[38;2;33;153;178m⣿\x1b[0m\x1b[38;"
        "2;34;160;183m⣿\x1b[0m\x1b[38;2;23;149;172m⣿\x1b[0"
        "m\x1b[38;2;10;142;163m⣿\x1b[0m\x1b[38;2;7;139;160"
        "m⣿\x1b[0m\x1b[38;2;4;134;156m⣿\x1b[0m\x1b[38;2;0;126"
        ";149m⣿\x1b[0m\x1b[38;2;22;140;166m⣿\x1b[0m\x1b[38;2;"
        "17;135;161m⣿\x1b[0m\x1b[38;2;7;125;151m⣿\x1b[0m\x1b["
        "38;2;0;122;140m⣿\x1b[0m\x1b[38;2;6;125;145m⣿\x1b["
        "0m\x1b[38;2;8;130;153m⣿\x1b[0m\x1b[38;2;10;132;15"
        "5m⣿\x1b[0m\x1b[38;2;5;123;149m⣿\x1b[0m\x1b[38;2;15;1"
        "25;152m⣿\x1b[0m\x1b[38;2;8;116;142m⣿\x1b[0m\x1b[38;2"
        ";5;113;139m⣿\x1b[0m\x1b[38;2;5;111;135m⣿\x1b[0m\x1b["
        "38;2;11;117;141m⣿\x1b[0m\x1b[38;2;0;110;133m⣿\x1b"
        "[0m\x1b[38;2;18;120;145m⣿\x1b[0m\x1b[38;2;20;118;"
        "143m⣿\x1b[0m\x1b[38;2;14;119;141m⣿\x1b[0m\x1b[38;2;1"
        "7;123;145m⣿\x1b[0m\x1b[38;2;0;98;121m⣿\x1b[0m\n  \x1b"
        "[38;2;12;127;156m⣿\x1b[0m\x1b[38;2;8;129;156m⣿"
        "\x1b[0m\x1b[38;2;13;128;157m⣿\x1b[0m\x1b[38;2;0;110;"
        "139m⣿\x1b[0m\x1b[38;2;6;125;159m⣿\x1b[0m\x1b[38;2;0;"
        "111;145m⣿\x1b[0m\x1b[38;2;0;121;152m⣿\x1b[0m\x1b[38;"
        "2;19;114;142m⡿\x1b[0m\x1b[38;2;210;209;214m⠿\x1b["
        "0m\x1b[38;2;49;126;146m⢿\x1b[0m\x1b[38;2;7;136;16"
        "8m⣿\x1b[0m\x1b[38;2;11;140;172m⣿\x1b[0m\x1b[38;2;19;"
        "140;171m⣿\x1b[0m\x1b[38;2;3;130;162m⣿\x1b[0m\x1b[38;"
        "2;26;129;170m⣿\x1b[0m\x1b[38;2;4;146;160m⣿\x1b[0m"
        "\x1b[38;2;85;126;108m⣿\x1b[0m\x1b[38;2;140;131;11"
        "6m⣡\x1b[0m\x1b[38;2;157;154;139m⡿\x1b[0m\x1b[38;2;78"
        ";78;52m⡗\x1b[0m\x1b[38;2;65;73;75m⠊\x1b[0m\x1b[38;2;"
        "30;32;53m⠀\x1b[0m\x1b[38;2;38;47;46m⠀\x1b[0m\x1b[38;"
        "2;21;30;37m⠀\x1b[0m\x1b[38;2;30;31;35m⡀\x1b[0m\x1b[3"
        "8;2;44;48;60m⠀\x1b[0m\x1b[38;2;31;36;39m⠄\x1b[0m\x1b"
        "[38;2;35;42;50m⠀\x1b[0m\x1b[38;2;34;43;42m⠂\x1b[0"
        "m\x1b[38;2;44;51;61m⠘\x1b[0m\x1b[38;2;113;116;95m"
        "⡽\x1b[0m\x1b[38;2;117;114;95m⣿\x1b[0m\x1b[38;2;128;1"
        "25;106m⣿\x1b[0m\x1b[38;2;122;120;99m⣷\x1b[0m\x1b[38;"
        "2;143;141;120m⣤\x1b[0m\x1b[38;2;114;107;88m⣾\x1b["
        "0m\x1b[38;2;110;103;84m⣿\x1b[0m\x1b[38;2;81;107;1"
        "06m⣿\x1b[0m\x1b[38;2;0;148;182m⣿\x1b[0m\x1b[38;2;12;"
        "143;161m⣿\x1b[0m\x1b[38;2;16;153;187m⣿\x1b[0m\x1b[38"
        ";2;23;148;178m⣿\x1b[0m\x1b[38;2;30;149;173m⣿\x1b["
        "0m\x1b[38;2;20;139;163m⣿\x1b[0m\x1b[38;2;28;147;1"
        "71m⣿\x1b[0m\x1b[38;2;12;149;167m⣿\x1b[0m\x1b[38;2;18"
        ";134;159m⣿\x1b[0m\x1b[38;2;22;143;172m⣿\x1b[0m\x1b[3"
        "8;2;31;142;170m⣿\x1b[0m\x1b[38;2;37;157;182m⣿\x1b"
        "[0m\x1b[38;2;23;155;176m⣿\x1b[0m\x1b[38;2;13;138;"
        "170m⣿\x1b[0m\x1b[38;2;19;153;182m⣿\x1b[0m\x1b[38;2;1"
        "7;126;155m⣿\x1b[0m\x1b[38;2;22;136;173m⣿\x1b[0m\x1b["
        "38;2;9;141;162m⣿\x1b[0m\x1b[38;2;14;140;163m⣿\x1b"
        "[0m\x1b[38;2;16;126;153m⣿\x1b[0m\x1b[38;2;8;118;1"
        "45m⣿\x1b[0m\x1b[38;2;8;116;144m⣿\x1b[0m\x1b[38;2;9;1"
        "18;141m⣿\x1b[0m\x1b[38;2;15;119;144m⣿\x1b[0m\x1b[38;"
        "2;7;113;139m⣿\x1b[0m\x1b[38;2;4;110;136m⣿\x1b[0m\x1b"
        "[38;2;4;102;129m⣿\x1b[0m\x1b[38;2;9;103;128m⣿\x1b"
        "[0m\x1b[38;2;11;97;122m⣿\x1b[0m\x1b[38;2;18;106;1"
        "30m⣿\x1b[0m\x1b[38;2;4;105;123m⣿\x1b[0m\x1b[38;2;6;1"
        "03;122m⣿\x1b[0m\x1b[38;2;1;102;122m⣿\x1b[0m\x1b[38;2"
        ";2;97;119m⣿\x1b[0m\x1b[38;2;4;95;116m⣿\x1b[0m\x1b[38"
        ";2;6;97;118m⣿\x1b[0m\x1b[38;2;3;103;118m⣿\x1b[0m\x1b"
        "[38;2;1;101;116m⣿\x1b[0m\x1b[38;2;10;101;120m⣿"
        "\x1b[0m\x1b[38;2;8;99;118m⣿\x1b[0m\n  \x1b[38;2;8;117"
        ";150m⣿\x1b[0m\x1b[38;2;16;125;158m⣿\x1b[0m\x1b[38;2;"
        "29;140;168m⣿\x1b[0m\x1b[38;2;21;132;160m⣿\x1b[0m\x1b"
        "[38;2;12;123;151m⣿\x1b[0m\x1b[38;2;5;116;144m⣿"
        "\x1b[0m\x1b[38;2;12;120;149m⣿\x1b[0m\x1b[38;2;13;121"
        ";150m⣿\x1b[0m\x1b[38;2;13;127;163m⣿\x1b[0m\x1b[38;2;"
        "0;98;125m⣿\x1b[0m\x1b[38;2;13;138;160m⣿\x1b[0m\x1b[3"
        "8;2;18;119;149m⣿\x1b[0m\x1b[38;2;16;126;153m⣿\x1b"
        "[0m\x1b[38;2;196;229;234m⣿\x1b[0m\x1b[38;2;213;21"
        "1;214m⣿\x1b[0m\x1b[38;2;118;121;112m⣿\x1b[0m\x1b[38;"
        "2;172;163;132m⣿\x1b[0m\x1b[38;2;91;83;60m⣿\x1b[0m"
        "\x1b[38;2;43;55;41m⣣\x1b[0m\x1b[38;2;56;53;72m⡔\x1b["
        "0m\x1b[38;2;65;67;82m⠐\x1b[0m\x1b[38;2;186;174;15"
        "0m⡌\x1b[0m\x1b[38;2;104;117;91m⠦\x1b[0m\x1b[38;2;171"
        ";193;147m⢸\x1b[0m\x1b[38;2;115;117;93m⣿\x1b[0m\x1b[3"
        "8;2;96;92;63m⣧\x1b[0m\x1b[38;2;31;39;28m⣀\x1b[0m\x1b"
        "[38;2;85;87;48m⣤\x1b[0m\x1b[38;2;77;78;44m⣴\x1b[0"
        "m\x1b[38;2;98;102;77m⣷\x1b[0m\x1b[38;2;99;112;84m"
        "⣿\x1b[0m\x1b[38;2;156;159;130m⣿\x1b[0m\x1b[38;2;146;"
        "148;124m⣿\x1b[0m\x1b[38;2;117;116;86m⣿\x1b[0m\x1b[38"
        ";2;109;109;83m⡿\x1b[0m\x1b[38;2;158;155;140m⠿\x1b"
        "[0m\x1b[38;2;132;131;113m⠿\x1b[0m\x1b[38;2;154;15"
        "1;134m⠿\x1b[0m\x1b[38;2;125;118;89m⢿\x1b[0m\x1b[38;2"
        ";40;51;37m⠿\x1b[0m\x1b[38;2;132;152;140m⣿\x1b[0m\x1b"
        "[38;2;39;141;155m⣿\x1b[0m\x1b[38;2;13;133;157m"
        "⣿\x1b[0m\x1b[38;2;0;131;146m⣿\x1b[0m\x1b[38;2;22;146"
        ";172m⣿\x1b[0m\x1b[38;2;30;142;166m⣿\x1b[0m\x1b[38;2;"
        "30;126;150m⡿\x1b[0m\x1b[38;2;35;40;46m⢛\x1b[0m\x1b[3"
        "8;2;59;62;51m⠏\x1b[0m\x1b[38;2;154;155;111m⣽\x1b["
        "0m\x1b[38;2;144;128;92m⣭\x1b[0m\x1b[38;2;115;115;"
        "77m⣿\x1b[0m\x1b[38;2;110;109;79m⣿\x1b[0m\x1b[38;2;12"
        "5;118;99m⣝\x1b[0m\x1b[38;2;52;91;98m⣿\x1b[0m\x1b[38;"
        "2;2;91;123m⣿\x1b[0m\x1b[38;2;26;102;136m⣿\x1b[0m\x1b"
        "[38;2;17;109;130m⣿\x1b[0m\x1b[38;2;14;109;129m"
        "⣿\x1b[0m\x1b[38;2;6;104;129m⣿\x1b[0m\x1b[38;2;12;110"
        ";135m⣿\x1b[0m\x1b[38;2;2;100;125m⣿\x1b[0m\x1b[38;2;2"
        ";100;125m⣿\x1b[0m\x1b[38;2;11;109;134m⣿\x1b[0m\x1b[3"
        "8;2;11;110;129m⣿\x1b[0m\x1b[38;2;15;107;128m⡿\x1b"
        "[0m\x1b[38;2;12;100;120m⡿\x1b[0m\x1b[38;2;9;97;11"
        "7m⣿\x1b[0m\x1b[38;2;5;86;107m⡿\x1b[0m\x1b[38;2;3;84;"
        "101m⢟\x1b[0m\x1b[38;2;17;92;111m⡐\x1b[0m\x1b[38;2;6;"
        "81;100m⠍\x1b[0m\x1b[38;2;9;86;106m⠬\x1b[0m\x1b[38;2;"
        "20;87;104m⠈\x1b[0m\x1b[38;2;19;82;97m⠝\x1b[0m\x1b[38"
        ";2;4;63;79m⠛\x1b[0m\x1b[38;2;5;58;74m⠛\x1b[0m\x1b[38"
        ";2;13;77;89m⠑\x1b[0m\n  \x1b[38;2;17;104;134m⡯\x1b"
        "[0m\x1b[38;2;15;102;132m⣽\x1b[0m\x1b[38;2;3;94;12"
        "5m⣟\x1b[0m\x1b[38;2;20;115;145m⣿\x1b[0m\x1b[38;2;24;"
        "122;147m⣿\x1b[0m\x1b[38;2;9;107;132m⡿\x1b[0m\x1b[38;"
        "2;18;104;129m⠿\x1b[0m\x1b[38;2;16;102;127m⣿\x1b[0"
        "m\x1b[38;2;0;87;114m⣿\x1b[0m\x1b[38;2;18;117;148m"
        "⣷\x1b[0m\x1b[38;2;60;167;199m⣿\x1b[0m\x1b[38;2;165;1"
        "90;187m⣿\x1b[0m\x1b[38;2;98;90;79m⣿\x1b[0m\x1b[38;2;"
        "225;208;178m⣿\x1b[0m\x1b[38;2;200;189;161m⣿\x1b[0"
        "m\x1b[38;2;164;165;123m⣿\x1b[0m\x1b[38;2;126;112;"
        "83m⣿\x1b[0m\x1b[38;2;128;119;64m⣷\x1b[0m\x1b[38;2;19"
        "2;191;161m⣽\x1b[0m\x1b[38;2;39;50;56m⡋\x1b[0m\x1b[38"
        ";2;98;108;99m⠺\x1b[0m\x1b[38;2;117;129;115m⠌\x1b["
        "0m\x1b[38;2;54;61;54m⠂\x1b[0m\x1b[38;2;214;202;18"
        "6m⠾\x1b[0m\x1b[38;2;71;75;48m⣟\x1b[0m\x1b[38;2;137;1"
        "36;90m⣿\x1b[0m\x1b[38;2;35;35;9m⣿\x1b[0m\x1b[38;2;13"
        "5;144;115m⡿\x1b[0m\x1b[38;2;39;43;44m⠟\x1b[0m\x1b[38"
        ";2;38;48;49m⠋\x1b[0m\x1b[38;2;67;71;72m⠑\x1b[0m\x1b["
        "38;2;94;100;98m⣐\x1b[0m\x1b[38;2;48;59;63m⢀\x1b[0"
        "m\x1b[38;2;47;68;71m⣄\x1b[0m\x1b[38;2;37;71;80m⣠\x1b"
        "[0m\x1b[38;2;26;92;104m⣤\x1b[0m\x1b[38;2;7;110;12"
        "5m⣶\x1b[0m\x1b[38;2;0;110;129m⣶\x1b[0m\x1b[38;2;8;13"
        "0;151m⣶\x1b[0m\x1b[38;2;44;166;187m⣿\x1b[0m\x1b[38;2"
        ";48;170;191m⣿\x1b[0m\x1b[38;2;17;128;145m⣿\x1b[0m"
        "\x1b[38;2;41;140;161m⣿\x1b[0m\x1b[38;2;47;157;174"
        "m⣿\x1b[0m\x1b[38;2;170;178;167m⢿\x1b[0m\x1b[38;2;66;"
        "67;51m⣯\x1b[0m\x1b[38;2;47;51;50m⣔\x1b[0m\x1b[38;2;1"
        "33;135;95m⣴\x1b[0m\x1b[38;2;123;122;76m⣴\x1b[0m\x1b["
        "38;2;141;141;107m⣾\x1b[0m\x1b[38;2;157;154;147"
        "m⡟\x1b[0m\x1b[38;2;128;127;109m⣫\x1b[0m\x1b[38;2;174"
        ";168;120m⣷\x1b[0m\x1b[38;2;202;186;160m⣿\x1b[0m\x1b["
        "38;2;189;174;143m⣿\x1b[0m\x1b[38;2;199;181;143"
        "m⣿\x1b[0m\x1b[38;2;0;103;137m⡿\x1b[0m\x1b[38;2;9;97;"
        "119m⣿\x1b[0m\x1b[38;2;4;82;104m⡿\x1b[0m\x1b[38;2;14;"
        "94;117m⣿\x1b[0m\x1b[38;2;15;93;115m⣷\x1b[0m\x1b[38;2"
        ";15;93;115m⡛\x1b[0m\x1b[38;2;12;90;110m⢿\x1b[0m\x1b["
        "38;2;10;88;108m⣻\x1b[0m\x1b[38;2;12;84;106m⣊\x1b["
        "0m\x1b[38;2;7;80;97m⠹\x1b[0m\x1b[38;2;15;93;106m⡧"
        "\x1b[0m\x1b[38;2;8;75;92m⠔\x1b[0m\x1b[38;2;6;77;97m⠂"
        "\x1b[0m\x1b[38;2;16;91;110m⠢\x1b[0m\x1b[38;2;11;74;9"
        "1m⠂\x1b[0m\x1b[38;2;9;72;89m⠀\x1b[0m\x1b[38;2;10;69;"
        "85m⠐\x1b[0m\x1b[38;2;10;69;85m⠀\x1b[0m\x1b[38;2;7;65"
        ";79m⠀\x1b[0m\x1b[38;2;9;68;82m⠀\x1b[0m\x1b[38;2;11;6"
        "3;74m⠀\x1b[0m\x1b[38;2;11;57;70m⠀\x1b[0m\n  \x1b[38;2"
        ";9;75;99m⠚\x1b[0m\x1b[38;2;17;92;113m⢳\x1b[0m\x1b[38"
        ";2;0;80;105m⣍\x1b[0m\x1b[38;2;13;93;118m⡱\x1b[0m\x1b"
        "[38;2;27;108;135m⣫\x1b[0m\x1b[38;2;12;93;120m⠟"
        "\x1b[0m\x1b[38;2;20;97;123m⠽\x1b[0m\x1b[38;2;0;74;10"
        "0m⣿\x1b[0m\x1b[38;2;2;82;109m⣽\x1b[0m\x1b[38;2;5;97;"
        "120m⢿\x1b[0m\x1b[38;2;51;152;172m⣿\x1b[0m\x1b[38;2;1"
        "52;154;141m⣿\x1b[0m\x1b[38;2;134;133;112m⣯\x1b[0m"
        "\x1b[38;2;103;101;78m⣵\x1b[0m\x1b[38;2;166;160;13"
        "6m⣿\x1b[0m\x1b[38;2;182;183;149m⣿\x1b[0m\x1b[38;2;18"
        "8;178;129m⣿\x1b[0m\x1b[38;2;173;165;82m⣿\x1b[0m\x1b["
        "38;2;173;158;103m⣿\x1b[0m\x1b[38;2;173;156;102"
        "m⣿\x1b[0m\x1b[38;2;172;160;112m⣿\x1b[0m\x1b[38;2;143"
        ";132;86m⣶\x1b[0m\x1b[38;2;129;121;74m⣶\x1b[0m\x1b[38"
        ";2;212;200;158m⣦\x1b[0m\x1b[38;2;50;59;54m⣁\x1b[0"
        "m\x1b[38;2;42;50;37m⡩\x1b[0m\x1b[38;2;48;58;60m⠄\x1b"
        "[0m\x1b[38;2;49;57;59m⠀\x1b[0m\x1b[38;2;24;32;34m"
        "⠀\x1b[0m\x1b[38;2;31;42;46m⠂\x1b[0m\x1b[38;2;56;79;8"
        "7m⢶\x1b[0m\x1b[38;2;36;88;101m⣾\x1b[0m\x1b[38;2;34;1"
        "03;118m⣿\x1b[0m\x1b[38;2;30;111;130m⣿\x1b[0m\x1b[38;"
        "2;7;130;145m⣿\x1b[0m\x1b[38;2;0;121;138m⣿\x1b[0m\x1b"
        "[38;2;3;129;151m⣿\x1b[0m\x1b[38;2;9;124;143m⣿\x1b"
        "[0m\x1b[38;2;25;140;159m⣿\x1b[0m\x1b[38;2;37;154;"
        "172m⣿\x1b[0m\x1b[38;2;20;132;152m⣿\x1b[0m\x1b[38;2;1"
        "9;140;161m⣿\x1b[0m\x1b[38;2;22;143;164m⣿\x1b[0m\x1b["
        "38;2;24;136;158m⣿\x1b[0m\x1b[38;2;76;87;83m⢛\x1b["
        "0m\x1b[38;2;163;169;159m⣿\x1b[0m\x1b[38;2;199;200"
        ";192m⣿\x1b[0m\x1b[38;2;82;80;65m⡿\x1b[0m\x1b[38;2;13"
        "8;142;109m⣿\x1b[0m\x1b[38;2;33;25;12m⡾\x1b[0m\x1b[38"
        ";2;133;123;74m⡷\x1b[0m\x1b[38;2;162;159;114m⣿\x1b"
        "[0m\x1b[38;2;116;119;90m⣿\x1b[0m\x1b[38;2;100;102"
        ";80m⡿\x1b[0m\x1b[38;2;192;168;132m⣯\x1b[0m\x1b[38;2;"
        "208;221;230m⣵\x1b[0m\x1b[38;2;34;138;151m⣿\x1b[0m"
        "\x1b[38;2;3;75;90m⣗\x1b[0m\x1b[38;2;4;66;89m⠹\x1b[0m"
        "\x1b[38;2;16;88;110m⢫\x1b[0m\x1b[38;2;9;84;103m⠾\x1b"
        "[0m\x1b[38;2;28;94;116m⠜\x1b[0m\x1b[38;2;16;74;96"
        "m⠙\x1b[0m\x1b[38;2;7;72;92m⢑\x1b[0m\x1b[38;2;10;77;9"
        "3m⠆\x1b[0m\x1b[38;2;2;65;82m⠁\x1b[0m\x1b[38;2;9;75;9"
        "1m⠚\x1b[0m\x1b[38;2;8;74;90m⠔\x1b[0m\x1b[38;2;7;70;8"
        "7m⠀\x1b[0m\x1b[38;2;15;74;92m⠀\x1b[0m\x1b[38;2;21;80"
        ";96m⡂\x1b[0m\x1b[38;2;16;75;91m⠀\x1b[0m\x1b[38;2;8;6"
        "7;81m⠄\x1b[0m\x1b[38;2;8;67;81m⠀\x1b[0m\x1b[38;2;14;"
        "67;83m⠀\x1b[0m\x1b[38;2;7;60;76m⠀\x1b[0m\x1b[38;2;11"
        ";69;83m⠀\x1b[0m\x1b[38;2;10;59;76m⠀\x1b[0m\n  \x1b[38"
        ";2;15;79;104m⠡\x1b[0m\x1b[38;2;12;87;108m⠠\x1b[0m"
        "\x1b[38;2;7;71;96m⡀\x1b[0m\x1b[38;2;0;55;80m⠤\x1b[0m"
        "\x1b[38;2;9;73;98m⡄\x1b[0m\x1b[38;2;0;57;82m⠊\x1b[0m"
        "\x1b[38;2;7;73;97m⠆\x1b[0m\x1b[38;2;6;77;99m⣂\x1b[0m"
        "\x1b[38;2;12;83;105m⢺\x1b[0m\x1b[38;2;17;92;113m⣩"
        "\x1b[0m\x1b[38;2;22;109;129m⡟\x1b[0m\x1b[38;2;12;97;"
        "118m⢿\x1b[0m\x1b[38;2;56;125;140m⣿\x1b[0m\x1b[38;2;1"
        "42;139;104m⢿\x1b[0m\x1b[38;2;132;126;92m⣷\x1b[0m\x1b"
        "[38;2;133;134;100m⣿\x1b[0m\x1b[38;2;206;188;15"
        "2m⡿\x1b[0m\x1b[38;2;139;133;99m⣿\x1b[0m\x1b[38;2;94;"
        "87;58m⣿\x1b[0m\x1b[38;2;139;128;100m⣿\x1b[0m\x1b[38;"
        "2;120;109;77m⣿\x1b[0m\x1b[38;2;219;206;174m⣿\x1b["
        "0m\x1b[38;2;72;60;46m⣿\x1b[0m\x1b[38;2;121;115;89"
        "m⣏\x1b[0m\x1b[38;2;138;131;103m⣿\x1b[0m\x1b[38;2;75;"
        "77;63m⣢\x1b[0m\x1b[38;2;133;135;121m⢭\x1b[0m\x1b[38;"
        "2;88;97;80m⢤\x1b[0m\x1b[38;2;18;20;15m⣀\x1b[0m\x1b[3"
        "8;2;52;60;63m⣀\x1b[0m\x1b[38;2;34;46;46m⣊\x1b[0m\x1b"
        "[38;2;16;62;75m⡿\x1b[0m\x1b[38;2;0;102;113m⣿\x1b["
        "0m\x1b[38;2;6;98;109m⣿\x1b[0m\x1b[38;2;6;103;122m"
        "⢿\x1b[0m\x1b[38;2;0;109;129m⣿\x1b[0m\x1b[38;2;3;115;"
        "135m⣿\x1b[0m\x1b[38;2;4;123;143m⣿\x1b[0m\x1b[38;2;10"
        ";133;148m⣿\x1b[0m\x1b[38;2;3;123;139m⣿\x1b[0m\x1b[38"
        ";2;8;120;142m⣿\x1b[0m\x1b[38;2;4;117;135m⣿\x1b[0m"
        "\x1b[38;2;47;114;122m⣿\x1b[0m\x1b[38;2;183;189;17"
        "9m⣿\x1b[0m\x1b[38;2;185;188;169m⡿\x1b[0m\x1b[38;2;16"
        "2;155;126m⠿\x1b[0m\x1b[38;2;23;27;30m⡋\x1b[0m\x1b[38"
        ";2;47;46;41m⠱\x1b[0m\x1b[38;2;167;159;138m⡟\x1b[0"
        "m\x1b[38;2;147;181;191m⢥\x1b[0m\x1b[38;2;13;26;32"
        "m⠀\x1b[0m\x1b[38;2;45;33;35m⣊\x1b[0m\x1b[38;2;18;46;"
        "47m⣉\x1b[0m\x1b[38;2;132;162;172m⣤\x1b[0m\x1b[38;2;7"
        "5;137;160m⣤\x1b[0m\x1b[38;2;18;77;93m⠉\x1b[0m\x1b[38"
        ";2;12;71;87m⠉\x1b[0m\x1b[38;2;20;83;100m⠂\x1b[0m\x1b"
        "[38;2;29;91;112m⠈\x1b[0m\x1b[38;2;24;85;106m⢐\x1b"
        "[0m\x1b[38;2;15;71;94m⠘\x1b[0m\x1b[38;2;18;75;94m"
        "⠩\x1b[0m\x1b[38;2;8;61;77m⠉\x1b[0m\x1b[38;2;11;64;80"
        "m⠀\x1b[0m\x1b[38;2;13;69;84m⠀\x1b[0m\x1b[38;2;4;60;7"
        "5m⠁\x1b[0m\x1b[38;2;3;56;70m⠀\x1b[0m\x1b[38;2;9;62;7"
        "6m⠀\x1b[0m\x1b[38;2;6;59;73m⠀\x1b[0m\x1b[38;2;10;63;"
        "77m⠈\x1b[0m\x1b[38;2;16;68;82m⠀\x1b[0m\x1b[38;2;14;5"
        "5;73m⠀\x1b[0m\x1b[38;2;9;57;69m⠀\x1b[0m\x1b[38;2;12;"
        "60;72m⠀\x1b[0m\x1b[38;2;14;56;70m⠀\x1b[0m\x1b[38;2;1"
        "6;53;69m⠀\x1b[0m\x1b[38;2;19;59;69m⠀\x1b[0m\x1b[38;2"
        ";14;54;64m⠀\x1b[0m\n  \x1b[38;2;7;63;80m⠐\x1b[0m\x1b["
        "38;2;10;58;78m⠀\x1b[0m\x1b[38;2;10;57;77m⠉\x1b[0m"
        "\x1b[38;2;13;60;80m⠀\x1b[0m\x1b[38;2;2;55;73m⠀\x1b[0"
        "m\x1b[38;2;1;54;72m⠀\x1b[0m\x1b[38;2;8;63;84m⠀\x1b[0"
        "m\x1b[38;2;13;71;91m⠀\x1b[0m\x1b[38;2;0;59;76m⠀\x1b["
        "0m\x1b[38;2;12;71;89m⠀\x1b[0m\x1b[38;2;7;74;90m⠈\x1b"
        "[0m\x1b[38;2;8;74;86m⠻\x1b[0m\x1b[38;2;0;63;75m⣹\x1b"
        "[0m\x1b[38;2;86;93;85m⢎\x1b[0m\x1b[38;2;199;189;1"
        "62m⣿\x1b[0m\x1b[38;2;192;177;138m⣿\x1b[0m\x1b[38;2;8"
        "0;74;50m⡯\x1b[0m\x1b[38;2;148;142;108m⢽\x1b[0m\x1b[3"
        "8;2;191;180;152m⣿\x1b[0m\x1b[38;2;141;128;96m⡿"
        "\x1b[0m\x1b[38;2;128;118;83m⣽\x1b[0m\x1b[38;2;69;64;"
        "32m⣿\x1b[0m\x1b[38;2;130;134;99m⣿\x1b[0m\x1b[38;2;12"
        "1;122;108m⣿\x1b[0m\x1b[38;2;153;146;118m⣿\x1b[0m\x1b"
        "[38;2;122;110;72m⢿\x1b[0m\x1b[38;2;151;134;106"
        "m⢯\x1b[0m\x1b[38;2;99;79;55m⣿\x1b[0m\x1b[38;2;192;16"
        "9;135m⣿\x1b[0m\x1b[38;2;204;195;166m⣿\x1b[0m\x1b[38;"
        "2;188;179;150m⣿\x1b[0m\x1b[38;2;156;149;130m⡟\x1b"
        "[0m\x1b[38;2;183;170;136m⣷\x1b[0m\x1b[38;2;185;18"
        "0;150m⣶\x1b[0m\x1b[38;2;167;158;129m⣾\x1b[0m\x1b[38;"
        "2;109;101;78m⣿\x1b[0m\x1b[38;2;223;211;187m⣿\x1b["
        "0m\x1b[38;2;216;206;197m⣿\x1b[0m\x1b[38;2;196;186"
        ";161m⡿\x1b[0m\x1b[38;2;52;39;33m⢟\x1b[0m\x1b[38;2;18"
        "3;186;167m⣹\x1b[0m\x1b[38;2;89;83;69m⣭\x1b[0m\x1b[38"
        ";2;218;242;246m⣭\x1b[0m\x1b[38;2;150;185;207m⣶"
        "\x1b[0m\x1b[38;2;5;127;130m⠾\x1b[0m\x1b[38;2;0;84;90"
        "m⢿\x1b[0m\x1b[38;2;167;200;215m⣤\x1b[0m\x1b[38;2;103"
        ";104;106m⣶\x1b[0m\x1b[38;2;190;191;195m⣧\x1b[0m\x1b["
        "38;2;216;231;238m⣿\x1b[0m\x1b[38;2;92;170;182m"
        "⣷\x1b[0m\x1b[38;2;16;90;101m⠖\x1b[0m\x1b[38;2;13;35;"
        "48m⠉\x1b[0m\x1b[38;2;13;52;67m⠉\x1b[0m\x1b[38;2;9;52"
        ";69m⠀\x1b[0m\x1b[38;2;2;48;64m⠀\x1b[0m\x1b[38;2;3;52"
        ";67m⠀\x1b[0m\x1b[38;2;7;54;72m⡀\x1b[0m\x1b[38;2;11;5"
        "4;73m⠂\x1b[0m\x1b[38;2;8;57;74m⠀\x1b[0m\x1b[38;2;22;"
        "65;84m⠀\x1b[0m\x1b[38;2;8;55;73m⠀\x1b[0m\x1b[38;2;8;"
        "57;74m⠀\x1b[0m\x1b[38;2;13;62;79m⠀\x1b[0m\x1b[38;2;1"
        "7;66;81m⠀\x1b[0m\x1b[38;2;16;62;78m⠀\x1b[0m\x1b[38;2"
        ";6;52;68m⠀\x1b[0m\x1b[38;2;12;53;71m⠀\x1b[0m\x1b[38;"
        "2;11;50;67m⠀\x1b[0m\x1b[38;2;17;56;73m⠀\x1b[0m\x1b[3"
        "8;2;19;56;74m⠀\x1b[0m\x1b[38;2;14;51;69m⠀\x1b[0m\x1b"
        "[38;2;13;49;65m⠀\x1b[0m\x1b[38;2;15;51;67m⠀\x1b[0"
        "m\x1b[38;2;13;49;61m⠀\x1b[0m\x1b[38;2;9;45;57m⠀\x1b["
        "0m\x1b[38;2;15;47;58m⠀\x1b[0m\x1b[38;2;13;45;56m⠀"
        "\x1b[0m\n  \x1b[38;2;5;48;64m⠀\x1b[0m\x1b[38;2;9;48;6"
        "5m⠀\x1b[0m\x1b[38;2;11;47;63m⠀\x1b[0m\x1b[38;2;10;52"
        ";66m⠀\x1b[0m\x1b[38;2;11;48;66m⠀\x1b[0m\x1b[38;2;8;4"
        "5;63m⠀\x1b[0m\x1b[38;2;7;50;66m⠀\x1b[0m\x1b[38;2;9;5"
        "6;74m⠀\x1b[0m\x1b[38;2;15;64;81m⠀\x1b[0m\x1b[38;2;7;"
        "60;76m⠀\x1b[0m\x1b[38;2;9;61;75m⢀\x1b[0m\x1b[38;2;10"
        ";94;118m⣺\x1b[0m\x1b[38;2;163;172;153m⣽\x1b[0m\x1b[3"
        "8;2;193;181;155m⡿\x1b[0m\x1b[38;2;125;109;73m⣻"
        "\x1b[0m\x1b[38;2;147;125;75m⣿\x1b[0m\x1b[38;2;137;11"
        "8;78m⡷\x1b[0m\x1b[38;2;124;122;110m⠳\x1b[0m\x1b[38;2"
        ";82;69;52m⣟\x1b[0m\x1b[38;2;53;48;29m⡉\x1b[0m\x1b[38"
        ";2;173;161;135m⣿\x1b[0m\x1b[38;2;57;51;29m⡿\x1b[0"
        "m\x1b[38;2;133;113;78m⣿\x1b[0m\x1b[38;2;130;116;7"
        "1m⣿\x1b[0m\x1b[38;2;117;102;61m⣿\x1b[0m\x1b[38;2;28;"
        "26;31m⡆\x1b[0m\x1b[38;2;36;32;21m⢻\x1b[0m\x1b[38;2;1"
        "33;123;88m⣿\x1b[0m\x1b[38;2;193;182;160m⣿\x1b[0m\x1b"
        "[38;2;187;178;149m⢿\x1b[0m\x1b[38;2;85;80;50m⣿"
        "\x1b[0m\x1b[38;2;34;33;31m⢇\x1b[0m\x1b[38;2;58;58;60"
        "m⡚\x1b[0m\x1b[38;2;62;64;61m⣛\x1b[0m\x1b[38;2;37;46;"
        "41m⡛\x1b[0m\x1b[38;2;84;122;125m⢣\x1b[0m\x1b[38;2;16"
        "0;179;183m⠿\x1b[0m\x1b[38;2;45;57;53m⢯\x1b[0m\x1b[38"
        ";2;127;146;161m⠾\x1b[0m\x1b[38;2;165;217;230m⣿"
        "\x1b[0m\x1b[38;2;5;77;89m⣟\x1b[0m\x1b[38;2;6;63;82m⡛"
        "\x1b[0m\x1b[38;2;6;63;82m⠉\x1b[0m\x1b[38;2;12;78;94m"
        "⡠\x1b[0m\x1b[38;2;18;83;103m⢠\x1b[0m\x1b[38;2;4;65;8"
        "3m⠀\x1b[0m\x1b[38;2;6;58;72m⠀\x1b[0m\x1b[38;2;4;57;7"
        "5m⠈\x1b[0m\x1b[38;2;9;63;75m⠉\x1b[0m\x1b[38;2;1;54;6"
        "8m⠉\x1b[0m\x1b[38;2;4;53;68m⠁\x1b[0m\x1b[38;2;5;48;6"
        "4m⠀\x1b[0m\x1b[38;2;0;39;56m⠀\x1b[0m\x1b[38;2;17;55;"
        "74m⠀\x1b[0m\x1b[38;2;10;53;70m⠀\x1b[0m\x1b[38;2;7;54"
        ";70m⠀\x1b[0m\x1b[38;2;2;45;62m⠀\x1b[0m\x1b[38;2;0;46"
        ";62m⠀\x1b[0m\x1b[38;2;20;61;79m⠀\x1b[0m\x1b[38;2;5;5"
        "1;67m⠀\x1b[0m\x1b[38;2;1;47;62m⠀\x1b[0m\x1b[38;2;11;"
        "53;69m⠀\x1b[0m\x1b[38;2;11;47;63m⠀\x1b[0m\x1b[38;2;1"
        "3;49;65m⠀\x1b[0m\x1b[38;2;18;46;67m⠀\x1b[0m\x1b[38;2"
        ";10;47;65m⠀\x1b[0m\x1b[38;2;20;57;75m⠀\x1b[0m\x1b[38"
        ";2;17;54;72m⠀\x1b[0m\x1b[38;2;16;48;61m⠀\x1b[0m\x1b["
        "38;2;13;45;58m⠀\x1b[0m\x1b[38;2;16;44;56m⠀\x1b[0m"
        "\x1b[38;2;14;42;54m⠀\x1b[0m\x1b[38;2;14;42;54m⠀\x1b["
        "0m\x1b[38;2;23;51;63m⠀\x1b[0m\x1b[38;2;19;47;59m⠀"
        "\x1b[0m\x1b[38;2;17;45;57m⠀\x1b[0m\x1b[38;2;15;43;55"
        "m⠀\x1b[0m\x1b[38;2;20;48;60m⠀\x1b[0m\n  \x1b[38;2;9;4"
        "2;59m⠀\x1b[0m\x1b[38;2;4;40;56m⠀\x1b[0m\x1b[38;2;9;4"
        "5;61m⠀\x1b[0m\x1b[38;2;10;46;62m⠀\x1b[0m\x1b[38;2;8;"
        "43;62m⠀\x1b[0m\x1b[38;2;5;40;59m⠀\x1b[0m\x1b[38;2;17"
        ";53;67m⠀\x1b[0m\x1b[38;2;4;47;63m⠀\x1b[0m\x1b[38;2;6"
        ";52;67m⠀\x1b[0m\x1b[38;2;4;53;67m⠈\x1b[0m\x1b[38;2;0"
        ";61;81m⣿\x1b[0m\x1b[38;2;180;192;208m⣷\x1b[0m\x1b[38"
        ";2;189;176;144m⣺\x1b[0m\x1b[38;2;106;96;69m⠿\x1b["
        "0m\x1b[38;2;181;161;111m⡾\x1b[0m\x1b[38;2;198;174"
        ";128m⡿\x1b[0m\x1b[38;2;95;81;44m⠿\x1b[0m\x1b[38;2;42"
        ";31;29m⠆\x1b[0m\x1b[38;2;36;36;38m⢳\x1b[0m\x1b[38;2;"
        "35;31;46m⡋\x1b[0m\x1b[38;2;198;184;139m⣿\x1b[0m\x1b["
        "38;2;150;131;89m⣿\x1b[0m\x1b[38;2;173;158;119m"
        "⣿\x1b[0m\x1b[38;2;160;147;105m⣯\x1b[0m\x1b[38;2;180;"
        "166;129m⣿\x1b[0m\x1b[38;2;151;146;126m⡏\x1b[0m\x1b[3"
        "8;2;33;50;58m⠧\x1b[0m\x1b[38;2;84;83;89m⠝\x1b[0m\x1b"
        "[38;2;20;26;38m⠕\x1b[0m\x1b[38;2;15;17;32m⠀\x1b[0"
        "m\x1b[38;2;12;34;47m⠛\x1b[0m\x1b[38;2;16;26;38m⠋\x1b"
        "[0m\x1b[38;2;15;32;42m⠉\x1b[0m\x1b[38;2;14;32;42m"
        "⠉\x1b[0m\x1b[38;2;10;37;48m⠁\x1b[0m\x1b[38;2;7;39;50"
        "m⠀\x1b[0m\x1b[38;2;5;47;59m⠀\x1b[0m\x1b[38;2;6;48;64"
        "m⠀\x1b[0m\x1b[38;2;3;45;61m⠀\x1b[0m\x1b[38;2;14;55;7"
        "3m⠀\x1b[0m\x1b[38;2;2;43;61m⠀\x1b[0m\x1b[38;2;5;48;6"
        "5m⠀\x1b[0m\x1b[38;2;3;41;60m⠀\x1b[0m\x1b[38;2;5;43;6"
        "2m⠀\x1b[0m\x1b[38;2;4;50;66m⠀\x1b[0m\x1b[38;2;5;48;6"
        "7m⠈\x1b[0m\x1b[38;2;6;49;68m⠈\x1b[0m\x1b[38;2;12;58;"
        "74m⠀\x1b[0m\x1b[38;2;12;49;68m⠀\x1b[0m\x1b[38;2;8;43"
        ";62m⠀\x1b[0m\x1b[38;2;7;42;61m⠀\x1b[0m\x1b[38;2;8;46"
        ";65m⠀\x1b[0m\x1b[38;2;12;51;66m⠀\x1b[0m\x1b[38;2;11;"
        "44;61m⠀\x1b[0m\x1b[38;2;7;44;60m⠀\x1b[0m\x1b[38;2;9;"
        "46;64m⠀\x1b[0m\x1b[38;2;9;46;64m⠀\x1b[0m\x1b[38;2;15"
        ";50;69m⠀\x1b[0m\x1b[38;2;12;44;59m⠀\x1b[0m\x1b[38;2;"
        "13;40;59m⠀\x1b[0m\x1b[38;2;17;45;59m⠀\x1b[0m\x1b[38;"
        "2;12;40;54m⠀\x1b[0m\x1b[38;2;15;41;56m⠀\x1b[0m\x1b[3"
        "8;2;17;43;58m⠀\x1b[0m\x1b[38;2;16;38;52m⠀\x1b[0m\x1b"
        "[38;2;14;36;50m⠀\x1b[0m\x1b[38;2;18;41;55m⠀\x1b[0"
        "m\x1b[38;2;25;48;62m⠀\x1b[0m\x1b[38;2;22;50;62m⠀\x1b"
        "[0m\x1b[38;2;17;40;54m⠀\x1b[0m\x1b[38;2;14;37;51m"
        "⠀\x1b[0m\x1b[38;2;19;42;56m⠀\x1b[0m\x1b[38;2;19;41;5"
        "5m⠀\x1b[0m\x1b[38;2;20;42;56m⠀\x1b[0m\x1b[38;2;21;40"
        ";55m⠀\x1b[0m\x1b[38;2;18;37;52m⠀\x1b[0m\x1b[38;2;29;"
        "46;62m⠀\x1b[0m\x1b[38;2;23;40;56m⠀\x1b[0m\n  \x1b[38;"
        "2;16;42;57m⠀\x1b[0m\x1b[38;2;6;35;49m⠀\x1b[0m\x1b[38"
        ";2;14;45;63m⠀\x1b[0m\x1b[38;2;9;40;58m⠀\x1b[0m\x1b[3"
        "8;2;7;36;50m⠀\x1b[0m\x1b[38;2;6;42;54m⠀\x1b[0m\x1b[3"
        "8;2;8;56;70m⠀\x1b[0m\x1b[38;2;6;54;68m⠀\x1b[0m\x1b[3"
        "8;2;8;47;62m⢀\x1b[0m\x1b[38;2;5;75;85m⣄\x1b[0m\x1b[3"
        "8;2;195;243;255m⣤\x1b[0m\x1b[38;2;51;133;144m⣭"
        "\x1b[0m\x1b[38;2;0;39;58m⢉\x1b[0m\x1b[38;2;25;44;61m"
        "⣌\x1b[0m\x1b[38;2;39;59;66m⡹\x1b[0m\x1b[38;2;29;77;9"
        "1m⣯\x1b[0m\x1b[38;2;90;99;108m⠍\x1b[0m\x1b[38;2;14;2"
        "3;32m⠀\x1b[0m\x1b[38;2;41;63;74m⡠\x1b[0m\x1b[38;2;15"
        "0;182;203m⢆\x1b[0m\x1b[38;2;109;94;51m⣼\x1b[0m\x1b[3"
        "8;2;205;189;163m⣽\x1b[0m\x1b[38;2;122;109;74m⣿"
        "\x1b[0m\x1b[38;2;210;191;158m⣿\x1b[0m\x1b[38;2;200;1"
        "85;156m⣿\x1b[0m\x1b[38;2;38;37;33m⠟\x1b[0m\x1b[38;2;"
        "19;29;41m⠄\x1b[0m\x1b[38;2;19;22;37m⠀\x1b[0m\x1b[38;"
        "2;17;25;38m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[3"
        "8;2;17;31;44m⠀\x1b[0m\x1b[38;2;9;27;41m⠀\x1b[0m\x1b["
        "38;2;15;33;47m⠀\x1b[0m\x1b[38;2;14;38;50m⠀\x1b[0m"
        "\x1b[38;2;8;40;53m⠀\x1b[0m\x1b[38;2;6;42;58m⠀\x1b[0m"
        "\x1b[38;2;11;44;61m⠀\x1b[0m\x1b[38;2;3;42;57m⠀\x1b[0"
        "m\x1b[38;2;9;48;63m⠀\x1b[0m\x1b[38;2;15;52;68m⠀\x1b["
        "0m\x1b[38;2;4;37;54m⠀\x1b[0m\x1b[38;2;17;42;64m⠀\x1b"
        "[0m\x1b[38;2;18;43;65m⠀\x1b[0m\x1b[38;2;12;41;59m"
        "⠀\x1b[0m\x1b[38;2;11;44;61m⠀\x1b[0m\x1b[38;2;8;40;55"
        "m⠀\x1b[0m\x1b[38;2;15;42;59m⠀\x1b[0m\x1b[38;2;20;49;"
        "65m⠀\x1b[0m\x1b[38;2;9;38;54m⠀\x1b[0m\x1b[38;2;9;38;"
        "54m⠀\x1b[0m\x1b[38;2;13;42;58m⠀\x1b[0m\x1b[38;2;14;4"
        "9;68m⠀\x1b[0m\x1b[38;2;5;40;59m⠀\x1b[0m\x1b[38;2;13;"
        "48;67m⠀\x1b[0m\x1b[38;2;2;37;56m⠀\x1b[0m\x1b[38;2;4;"
        "36;51m⠀\x1b[0m\x1b[38;2;4;36;51m⠀\x1b[0m\x1b[38;2;16"
        ";45;61m⠀\x1b[0m\x1b[38;2;12;41;57m⠀\x1b[0m\x1b[38;2;"
        "15;44;58m⠀\x1b[0m\x1b[38;2;17;36;51m⠀\x1b[0m\x1b[38;"
        "2;25;42;58m⠀\x1b[0m\x1b[38;2;12;34;48m⠀\x1b[0m\x1b[3"
        "8;2;15;37;51m⠀\x1b[0m\x1b[38;2;14;40;53m⠀\x1b[0m\x1b"
        "[38;2;16;38;52m⠀\x1b[0m\x1b[38;2;21;37;53m⠀\x1b[0"
        "m\x1b[38;2;18;37;52m⠀\x1b[0m\x1b[38;2;20;39;54m⠀\x1b"
        "[0m\x1b[38;2;20;39;54m⠀\x1b[0m\x1b[38;2;22;39;55m"
        "⠀\x1b[0m\x1b[38;2;23;40;56m⠀\x1b[0m\x1b[38;2;20;37;5"
        "3m⠀\x1b[0m\x1b[38;2;22;39;55m⠀\x1b[0m\x1b[38;2;18;35"
        ";51m⠀\x1b[0m\x1b[38;2;14;31;47m⠀\x1b[0m\x1b[38;2;20;"
        "38;52m⠀\x1b[0m\x1b[38;2;22;40;54m⠀\x1b[0m\n  \x1b[38;"
        "2;15;38;52m⠀\x1b[0m\x1b[38;2;18;34;50m⠀\x1b[0m\x1b[3"
        "8;2;19;36;52m⠀\x1b[0m\x1b[38;2;8;36;48m⠀\x1b[0m\x1b["
        "38;2;9;39;50m⠀\x1b[0m\x1b[38;2;12;46;56m⠀\x1b[0m\x1b"
        "[38;2;19;56;65m⠀\x1b[0m\x1b[38;2;27;67;75m⠀\x1b[0"
        "m\x1b[38;2;6;43;49m⠛\x1b[0m\x1b[38;2;80;143;160m⠻"
        "\x1b[0m\x1b[38;2;64;110;126m⠟\x1b[0m\x1b[38;2;3;55;7"
        "6m⠇\x1b[0m\x1b[38;2;14;51;59m⠀\x1b[0m\x1b[38;2;17;34"
        ";44m⠈\x1b[0m\x1b[38;2;16;33;43m⠈\x1b[0m\x1b[38;2;16;"
        "41;48m⠁\x1b[0m\x1b[38;2;33;43;55m⠀\x1b[0m\x1b[38;2;2"
        "8;40;52m⠈\x1b[0m\x1b[38;2;44;105;108m⠛\x1b[0m\x1b[38"
        ";2;10;33;41m⠒\x1b[0m\x1b[38;2;13;16;25m⠢\x1b[0m\x1b["
        "38;2;100;105;101m⠼\x1b[0m\x1b[38;2;184;188;191"
        "m⠿\x1b[0m\x1b[38;2;12;16;25m⠍\x1b[0m\x1b[38;2;17;26;"
        "35m⠒\x1b[0m\x1b[38;2;7;24;34m⠁\x1b[0m\x1b[38;2;20;23"
        ";38m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;15;"
        "29;40m⠀\x1b[0m\x1b[38;2;15;33;45m⠀\x1b[0m\x1b[38;2;1"
        "7;34;50m⠀\x1b[0m\x1b[38;2;12;34;48m⠀\x1b[0m\x1b[38;2"
        ";13;35;49m⠀\x1b[0m\x1b[38;2;10;36;49m⠀\x1b[0m\x1b[38"
        ";2;11;41;52m⠀\x1b[0m\x1b[38;2;14;37;53m⠀\x1b[0m\x1b["
        "38;2;14;42;56m⠀\x1b[0m\x1b[38;2;18;61;70m⠀\x1b[0m"
        "\x1b[38;2;5;51;66m⠀\x1b[0m\x1b[38;2;10;62;76m⠀\x1b[0"
        "m\x1b[38;2;23;65;79m⠀\x1b[0m\x1b[38;2;4;33;49m⠀\x1b["
        "0m\x1b[38;2;11;37;54m⠀\x1b[0m\x1b[38;2;16;38;52m⠀"
        "\x1b[0m\x1b[38;2;19;36;52m⠀\x1b[0m\x1b[38;2;23;42;57"
        "m⠀\x1b[0m\x1b[38;2;12;35;49m⠀\x1b[0m\x1b[38;2;19;38;"
        "55m⠀\x1b[0m\x1b[38;2;9;32;48m⠀\x1b[0m\x1b[38;2;11;37"
        ";52m⠀\x1b[0m\x1b[38;2;21;47;62m⠀\x1b[0m\x1b[38;2;13;"
        "36;52m⠀\x1b[0m\x1b[38;2;13;36;52m⠀\x1b[0m\x1b[38;2;2"
        "2;41;58m⠀\x1b[0m\x1b[38;2;19;35;50m⠀\x1b[0m\x1b[38;2"
        ";16;35;50m⠀\x1b[0m\x1b[38;2;14;33;48m⠀\x1b[0m\x1b[38"
        ";2;16;38;52m⠀\x1b[0m\x1b[38;2;18;40;54m⠀\x1b[0m\x1b["
        "38;2;13;29;45m⠀\x1b[0m\x1b[38;2;11;29;43m⠀\x1b[0m"
        "\x1b[38;2;22;40;54m⠀\x1b[0m\x1b[38;2;23;39;54m⠀\x1b["
        "0m\x1b[38;2;22;38;53m⠀\x1b[0m\x1b[38;2;17;33;49m⠀"
        "\x1b[0m\x1b[38;2;22;38;54m⠀\x1b[0m\x1b[38;2;26;40;53"
        "m⠀\x1b[0m\x1b[38;2;17;31;44m⠀\x1b[0m\x1b[38;2;19;35;"
        "50m⠀\x1b[0m\x1b[38;2;15;31;46m⠀\x1b[0m\x1b[38;2;20;3"
        "6;49m⠀\x1b[0m\x1b[38;2;15;31;44m⠀\x1b[0m\x1b[38;2;17"
        ";31;44m⠀\x1b[0m\x1b[38;2;22;36;49m⠀\x1b[0m\x1b[38;2;"
        "19;33;44m⠀\x1b[0m\x1b[38;2;19;33;44m⠀\x1b[0m\x1b[38;"
        "2;21;39;53m⠀\x1b[0m\x1b[38;2;21;39;53m⠀\x1b[0m\n  "
        "\x1b[38;2;24;40;56m⠀\x1b[0m\x1b[38;2;18;34;50m⠀\x1b["
        "0m\x1b[38;2;20;36;51m⠀\x1b[0m\x1b[38;2;16;33;43m⠀"
        "\x1b[0m\x1b[38;2;17;40;54m⠀\x1b[0m\x1b[38;2;13;36;50"
        "m⠀\x1b[0m\x1b[38;2;15;34;49m⠀\x1b[0m\x1b[38;2;4;38;4"
        "8m⠀\x1b[0m\x1b[38;2;9;41;54m⠀\x1b[0m\x1b[38;2;10;38;"
        "52m⠀\x1b[0m\x1b[38;2;17;40;54m⠀\x1b[0m\x1b[38;2;20;3"
        "9;54m⠀\x1b[0m\x1b[38;2;13;41;52m⠀\x1b[0m\x1b[38;2;12"
        ";40;51m⠀\x1b[0m\x1b[38;2;16;36;45m⠀\x1b[0m\x1b[38;2;"
        "17;34;44m⠀\x1b[0m\x1b[38;2;17;34;44m⠀\x1b[0m\x1b[38;"
        "2;16;33;43m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[3"
        "8;2;12;24;36m⠀\x1b[0m\x1b[38;2;16;24;37m⠀\x1b[0m\x1b"
        "[38;2;17;23;37m⠀\x1b[0m\x1b[38;2;16;22;36m⠀\x1b[0"
        "m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;16;26;38m⠀\x1b"
        "[0m\x1b[38;2;17;25;38m⠀\x1b[0m\x1b[38;2;16;28;40m"
        "⠀\x1b[0m\x1b[38;2;20;29;44m⠀\x1b[0m\x1b[38;2;16;28;4"
        "2m⠀\x1b[0m\x1b[38;2;23;28;47m⠀\x1b[0m\x1b[38;2;18;40"
        ";53m⠀\x1b[0m\x1b[38;2;11;44;53m⠀\x1b[0m\x1b[38;2;11;"
        "43;56m⠀\x1b[0m\x1b[38;2;12;34;48m⠀\x1b[0m\x1b[38;2;1"
        "2;34;48m⠀\x1b[0m\x1b[38;2;17;34;50m⠀\x1b[0m\x1b[38;2"
        ";16;33;49m⠀\x1b[0m\x1b[38;2;10;29;44m⠀\x1b[0m\x1b[38"
        ";2;17;36;51m⠀\x1b[0m\x1b[38;2;16;38;52m⠀\x1b[0m\x1b["
        "38;2;23;45;59m⠀\x1b[0m\x1b[38;2;10;32;46m⠀\x1b[0m"
        "\x1b[38;2;21;43;57m⠀\x1b[0m\x1b[38;2;17;38;55m⠀\x1b["
        "0m\x1b[38;2;10;36;51m⠀\x1b[0m\x1b[38;2;11;37;54m⠀"
        "\x1b[0m\x1b[38;2;23;41;61m⠀\x1b[0m\x1b[38;2;19;38;53"
        "m⠀\x1b[0m\x1b[38;2;18;37;52m⠀\x1b[0m\x1b[38;2;17;34;"
        "50m⠀\x1b[0m\x1b[38;2;16;33;49m⠀\x1b[0m\x1b[38;2;18;3"
        "4;50m⠀\x1b[0m\x1b[38;2;16;32;48m⠀\x1b[0m\x1b[38;2;18"
        ";34;50m⠀\x1b[0m\x1b[38;2;22;38;54m⠀\x1b[0m\x1b[38;2;"
        "17;33;49m⠀\x1b[0m\x1b[38;2;14;30;46m⠀\x1b[0m\x1b[38;"
        "2;19;35;50m⠀\x1b[0m\x1b[38;2;16;32;47m⠀\x1b[0m\x1b[3"
        "8;2;12;25;41m⠀\x1b[0m\x1b[38;2;20;33;49m⠀\x1b[0m\x1b"
        "[38;2;21;34;50m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0"
        "m\x1b[38;2;20;34;47m⠀\x1b[0m\x1b[38;2;21;35;46m⠀\x1b"
        "[0m\x1b[38;2;18;32;43m⠀\x1b[0m\x1b[38;2;14;28;39m"
        "⠀\x1b[0m\x1b[38;2;26;40;51m⠀\x1b[0m\x1b[38;2;11;25;3"
        "8m⠀\x1b[0m\x1b[38;2;27;41;54m⠀\x1b[0m\x1b[38;2;26;40"
        ";51m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b[38;2;17;"
        "29;41m⠀\x1b[0m\x1b[38;2;21;33;45m⠀\x1b[0m\x1b[38;2;1"
        "8;30;42m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38;2"
        ";17;29;41m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\n  \x1b"
        "[38;2;18;32;45m⠀\x1b[0m\x1b[38;2;20;34;47m⠀\x1b[0"
        "m\x1b[38;2;18;34;47m⠀\x1b[0m\x1b[38;2;16;32;45m⠀\x1b"
        "[0m\x1b[38;2;20;38;50m⠀\x1b[0m\x1b[38;2;15;33;45m"
        "⠀\x1b[0m\x1b[38;2;18;34;47m⠀\x1b[0m\x1b[38;2;19;35;4"
        "8m⠀\x1b[0m\x1b[38;2;22;38;51m⠀\x1b[0m\x1b[38;2;15;31"
        ";44m⠀\x1b[0m\x1b[38;2;16;33;41m⠀\x1b[0m\x1b[38;2;13;"
        "30;38m⠀\x1b[0m\x1b[38;2;17;34;44m⠀\x1b[0m\x1b[38;2;1"
        "2;29;39m⠀\x1b[0m\x1b[38;2;15;31;44m⠀\x1b[0m\x1b[38;2"
        ";19;35;48m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38"
        ";2;19;31;43m⠀\x1b[0m\x1b[38;2;15;33;43m⠀\x1b[0m\x1b["
        "38;2;14;32;42m⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b[0m"
        "\x1b[38;2;19;27;40m⠀\x1b[0m\x1b[38;2;18;26;39m⠀\x1b["
        "0m\x1b[38;2;19;29;41m⠀\x1b[0m\x1b[38;2;19;29;41m⠀"
        "\x1b[0m\x1b[38;2;20;30;42m⠀\x1b[0m\x1b[38;2;16;30;41"
        "m⠀\x1b[0m\x1b[38;2;16;30;39m⠀\x1b[0m\x1b[38;2;26;49;"
        "65m⠠\x1b[0m\x1b[38;2;62;119;126m⠆\x1b[0m\x1b[38;2;14"
        "5;198;212m⡴\x1b[0m\x1b[38;2;113;159;174m⡾\x1b[0m\x1b"
        "[38;2;16;56;66m⠇\x1b[0m\x1b[38;2;19;32;49m⠀\x1b[0"
        "m\x1b[38;2;16;29;46m⠀\x1b[0m\x1b[38;2;11;33;47m⠀\x1b"
        "[0m\x1b[38;2;19;41;55m⠀\x1b[0m\x1b[38;2;18;34;50m"
        "⠀\x1b[0m\x1b[38;2;19;35;51m⠀\x1b[0m\x1b[38;2;18;35;5"
        "1m⠀\x1b[0m\x1b[38;2;18;35;51m⠀\x1b[0m\x1b[38;2;20;36"
        ";52m⠀\x1b[0m\x1b[38;2;16;32;48m⠀\x1b[0m\x1b[38;2;13;"
        "29;45m⠀\x1b[0m\x1b[38;2;15;31;47m⠀\x1b[0m\x1b[38;2;1"
        "6;32;48m⠀\x1b[0m\x1b[38;2;17;33;49m⠀\x1b[0m\x1b[38;2"
        ";13;29;45m⠀\x1b[0m\x1b[38;2;16;32;48m⠀\x1b[0m\x1b[38"
        ";2;22;38;54m⠀\x1b[0m\x1b[38;2;19;35;51m⠀\x1b[0m\x1b["
        "38;2;21;37;53m⠀\x1b[0m\x1b[38;2;14;30;46m⠀\x1b[0m"
        "\x1b[38;2;20;33;50m⠀\x1b[0m\x1b[38;2;22;35;52m⠀\x1b["
        "0m\x1b[38;2;17;30;47m⠀\x1b[0m\x1b[38;2;16;29;46m⠀"
        "\x1b[0m\x1b[38;2;18;32;45m⠀\x1b[0m\x1b[38;2;18;32;45"
        "m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;20;34;"
        "45m⠀\x1b[0m\x1b[38;2;20;34;45m⠀\x1b[0m\x1b[38;2;21;3"
        "5;46m⠀\x1b[0m\x1b[38;2;20;34;45m⠀\x1b[0m\x1b[38;2;19"
        ";33;44m⠀\x1b[0m\x1b[38;2;19;33;44m⠀\x1b[0m\x1b[38;2;"
        "14;28;39m⠀\x1b[0m\x1b[38;2;19;29;41m⠀\x1b[0m\x1b[38;"
        "2;21;27;41m⠀\x1b[0m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[3"
        "8;2;20;32;44m⠀\x1b[0m\x1b[38;2;18;30;42m⠀\x1b[0m\x1b"
        "[38;2;19;31;43m⠀\x1b[0m\x1b[38;2;19;27;40m⠀\x1b[0"
        "m\x1b[38;2;21;27;41m⠀\x1b[0m\x1b[38;2;21;27;41m⠀\x1b"
        "[0m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;21;31;43m"
        "⠀\x1b[0m\n  \x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;18;3"
        "2;43m⠀\x1b[0m\x1b[38;2;24;38;49m⠀\x1b[0m\x1b[38;2;14"
        ";28;39m⠀\x1b[0m\x1b[38;2;23;35;47m⠀\x1b[0m\x1b[38;2;"
        "19;31;43m⠀\x1b[0m\x1b[38;2;18;30;42m⠀\x1b[0m\x1b[38;"
        "2;18;30;42m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[3"
        "8;2;19;33;44m⠀\x1b[0m\x1b[38;2;20;36;52m⠀\x1b[0m\x1b"
        "[38;2;14;33;48m⠀\x1b[0m\x1b[38;2;19;35;48m⠀\x1b[0"
        "m\x1b[38;2;14;30;43m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b"
        "[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;15;27;39m"
        "⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b[0m\x1b[38;2;16;28;4"
        "0m⠀\x1b[0m\x1b[38;2;15;27;39m⠀\x1b[0m\x1b[38;2;16;33"
        ";43m⠀\x1b[0m\x1b[38;2;14;31;41m⠀\x1b[0m\x1b[38;2;20;"
        "37;47m⠀\x1b[0m\x1b[38;2;15;32;42m⠀\x1b[0m\x1b[38;2;1"
        "5;27;39m⠀\x1b[0m\x1b[38;2;14;41;50m⠀\x1b[0m\x1b[38;2"
        ";14;44;52m⠀\x1b[0m\x1b[38;2;13;43;53m⠀\x1b[0m\x1b[38"
        ";2;17;51;60m⠀\x1b[0m\x1b[38;2;11;52;58m⠀\x1b[0m\x1b["
        "38;2;14;36;49m⠀\x1b[0m\x1b[38;2;14;36;50m⠀\x1b[0m"
        "\x1b[38;2;19;35;51m⠀\x1b[0m\x1b[38;2;15;35;46m⠀\x1b["
        "0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;17;31;42m⠀"
        "\x1b[0m\x1b[38;2;18;32;43m⠀\x1b[0m\x1b[38;2;20;33;49"
        "m⠀\x1b[0m\x1b[38;2;17;30;46m⠀\x1b[0m\x1b[38;2;14;27;"
        "44m⠀\x1b[0m\x1b[38;2;19;32;49m⠀\x1b[0m\x1b[38;2;19;3"
        "2;48m⠀\x1b[0m\x1b[38;2;17;30;46m⠀\x1b[0m\x1b[38;2;17"
        ";30;47m⠀\x1b[0m\x1b[38;2;20;33;50m⠀\x1b[0m\x1b[38;2;"
        "15;28;45m⠀\x1b[0m\x1b[38;2;18;31;48m⠀\x1b[0m\x1b[38;"
        "2;23;36;53m⠀\x1b[0m\x1b[38;2;26;39;56m⠀\x1b[0m\x1b[3"
        "8;2;17;30;47m⠀\x1b[0m\x1b[38;2;18;31;48m⠀\x1b[0m\x1b"
        "[38;2;17;30;46m⠀\x1b[0m\x1b[38;2;16;29;45m⠀\x1b[0"
        "m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;13;27;40m⠀\x1b"
        "[0m\x1b[38;2;18;32;43m⠀\x1b[0m\x1b[38;2;21;35;46m"
        "⠀\x1b[0m\x1b[38;2;23;37;48m⠀\x1b[0m\x1b[38;2;18;32;4"
        "3m⠀\x1b[0m\x1b[38;2;21;33;45m⠀\x1b[0m\x1b[38;2;21;33"
        ";45m⠀\x1b[0m\x1b[38;2;23;35;47m⠀\x1b[0m\x1b[38;2;11;"
        "23;35m⠀\x1b[0m\x1b[38;2;19;31;43m⠀\x1b[0m\x1b[38;2;2"
        "0;26;40m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2"
        ";18;24;38m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38"
        ";2;22;28;42m⠀\x1b[0m\x1b[38;2;18;24;38m⠀\x1b[0m\x1b["
        "38;2;18;24;38m⠀\x1b[0m\x1b[38;2;21;27;41m⠀\x1b[0m"
        "\x1b[38;2;15;21;35m⠀\x1b[0m\x1b[38;2;23;29;43m⠀\x1b["
        "0m\x1b[38;2;22;28;42m⠀\x1b[0m\x1b[38;2;20;26;40m⠀"
        "\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;25;31;45"
        "m⠀\x1b[0m\n  \x1b[38;2;21;33;45m⠀\x1b[0m\x1b[38;2;16;"
        "28;40m⠀\x1b[0m\x1b[38;2;20;30;42m⠀\x1b[0m\x1b[38;2;1"
        "9;29;41m⠀\x1b[0m\x1b[38;2;23;29;43m⠀\x1b[0m\x1b[38;2"
        ";21;27;41m⠀\x1b[0m\x1b[38;2;18;28;40m⠀\x1b[0m\x1b[38"
        ";2;19;29;41m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b["
        "38;2;20;34;45m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m"
        "\x1b[38;2;25;37;49m⠀\x1b[0m\x1b[38;2;20;32;44m⠀\x1b["
        "0m\x1b[38;2;13;25;37m⠀\x1b[0m\x1b[38;2;19;25;39m⠀"
        "\x1b[0m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;16;34;44"
        "m⠀\x1b[0m\x1b[38;2;17;37;48m⠀\x1b[0m\x1b[38;2;16;33;"
        "49m⠀\x1b[0m\x1b[38;2;15;33;47m⠀\x1b[0m\x1b[38;2;14;3"
        "2;42m⠀\x1b[0m\x1b[38;2;21;35;46m⠀\x1b[0m\x1b[38;2;14"
        ";28;39m⠀\x1b[0m\x1b[38;2;18;30;42m⠀\x1b[0m\x1b[38;2;"
        "18;30;42m⠀\x1b[0m\x1b[38;2;14;31;41m⠀\x1b[0m\x1b[38;"
        "2;15;32;42m⠀\x1b[0m\x1b[38;2;20;30;40m⠀\x1b[0m\x1b[3"
        "8;2;18;32;41m⠀\x1b[0m\x1b[38;2;18;31;47m⠀\x1b[0m\x1b"
        "[38;2;16;34;48m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0"
        "m\x1b[38;2;19;33;44m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b"
        "[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;24;37;56m"
        "⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;16;30;3"
        "9m⠀\x1b[0m\x1b[38;2;17;31;40m⠀\x1b[0m\x1b[38;2;17;31"
        ";40m⠀\x1b[0m\x1b[38;2;17;31;40m⠀\x1b[0m\x1b[38;2;16;"
        "30;41m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b[38;2;1"
        "8;32;43m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2"
        ";17;31;42m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38"
        ";2;17;31;42m⠀\x1b[0m\x1b[38;2;18;32;43m⠀\x1b[0m\x1b["
        "38;2;18;32;45m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m"
        "\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b["
        "0m\x1b[38;2;18;28;40m⠀\x1b[0m\x1b[38;2;20;30;42m⠀"
        "\x1b[0m\x1b[38;2;17;27;39m⠀\x1b[0m\x1b[38;2;16;26;38"
        "m⠀\x1b[0m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;18;28;"
        "40m⠀\x1b[0m\x1b[38;2;19;25;39m⠀\x1b[0m\x1b[38;2;22;2"
        "8;42m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;21"
        ";27;41m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;"
        "21;27;41m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;"
        "2;19;25;39m⠀\x1b[0m\x1b[38;2;21;27;41m⠀\x1b[0m\x1b[3"
        "8;2;21;27;41m⠀\x1b[0m\x1b[38;2;23;29;43m⠀\x1b[0m\x1b"
        "[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0"
        "m\x1b[38;2;21;27;41m⠀\x1b[0m\x1b[38;2;19;25;39m⠀\x1b"
        "[0m\x1b[38;2;18;24;38m⠀\x1b[0m\x1b[38;2;20;26;40m"
        "⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;22;28;4"
        "2m⠀\x1b[0m\n                                "
        "                                        "
        "        \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_image_markdown_cell(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
) -> None:
    """It renders a markdown cell with an image."""
    image_path = os.fsdecode(
        pathlib.Path(__file__).parent
        / pathlib.Path("assets", "ferdinand-stohr-ig8oMCxMOTY-unsplash.jpg")
    )
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"![Azores]({image_path})",
    }
    output = rich_notebook_output(markdown_cell, image_drawing="braille")
    tempfile_path = get_tempfile_path("")
    expected_output = (
        f"  \x1b]8;id=534890;file://{tempfile_path}0.jpg\x1b\\\x1b[94m🖼 Click to vie"
        "w Azores\x1b[0m\x1b]8;;\x1b\\                     "
        "                                   \n    "
        "                                        "
        "                                    \n  \x1b"
        "[38;2;157;175;189m⣿\x1b[0m\x1b[38;2;171;183;19"
        "9m⣿\x1b[0m\x1b[38;2;158;170;186m⣿\x1b[0m\x1b[38;2;18"
        "8;194;208m⣿\x1b[0m\x1b[38;2;216;219;234m⣿\x1b[0m\x1b"
        "[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;226;229;24"
        "4m⣿\x1b[0m\x1b[38;2;225;228;243m⣿\x1b[0m\x1b[38;2;22"
        "3;226;241m⣿\x1b[0m\x1b[38;2;224;227;242m⣿\x1b[0m\x1b"
        "[38;2;225;227;242m⣿\x1b[0m\x1b[38;2;180;196;21"
        "1m⣿\x1b[0m\x1b[38;2;211;223;235m⣿\x1b[0m\x1b[38;2;22"
        "3;225;237m⣿\x1b[0m\x1b[38;2;223;226;241m⣿\x1b[0m\x1b"
        "[38;2;200;203;218m⣿\x1b[0m\x1b[38;2;194;200;21"
        "4m⣿\x1b[0m\x1b[38;2;189;195;209m⣿\x1b[0m\x1b[38;2;18"
        "7;195;206m⣿\x1b[0m\x1b[38;2;194;198;210m⣿\x1b[0m\x1b"
        "[38;2;132;168;184m⣿\x1b[0m\x1b[38;2;224;227;24"
        "2m⣿\x1b[0m\x1b[38;2;224;227;242m⣿\x1b[0m\x1b[38;2;22"
        "4;227;242m⣿\x1b[0m\x1b[38;2;220;223;238m⣿\x1b[0m\x1b"
        "[38;2;205;212;228m⣿\x1b[0m\x1b[38;2;167;183;19"
        "6m⣿\x1b[0m\x1b[38;2;200;206;218m⣿\x1b[0m\x1b[38;2;16"
        "8;191;205m⣿\x1b[0m\x1b[38;2;131;162;182m⣿\x1b[0m\x1b"
        "[38;2;116;151;173m⣿\x1b[0m\x1b[38;2;203;212;22"
        "7m⣿\x1b[0m\x1b[38;2;223;229;245m⣿\x1b[0m\x1b[38;2;22"
        "6;225;239m⣿\x1b[0m\x1b[38;2;204;220;233m⣿\x1b[0m\x1b"
        "[38;2;152;168;183m⣿\x1b[0m\x1b[38;2;225;227;24"
        "2m⣿\x1b[0m\x1b[38;2;223;226;241m⣿\x1b[0m\x1b[38;2;22"
        "4;227;242m⣿\x1b[0m\x1b[38;2;222;225;240m⣿\x1b[0m\x1b"
        "[38;2;222;225;240m⣿\x1b[0m\x1b[38;2;219;222;23"
        "7m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;21"
        "9;222;237m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b"
        "[38;2;220;223;238m⣿\x1b[0m\x1b[38;2;219;222;23"
        "7m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;21"
        "9;222;237m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b"
        "[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;219;222;23"
        "7m⣿\x1b[0m\x1b[38;2;215;218;233m⣿\x1b[0m\x1b[38;2;21"
        "3;216;231m⣿\x1b[0m\x1b[38;2;193;196;211m⣿\x1b[0m\x1b"
        "[38;2;173;179;193m⣿\x1b[0m\x1b[38;2;197;203;21"
        "7m⣿\x1b[0m\x1b[38;2;186;194;207m⣿\x1b[0m\x1b[38;2;19"
        "4;202;215m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b"
        "[38;2;217;220;235m⣿\x1b[0m\x1b[38;2;215;218;23"
        "3m⣿\x1b[0m\x1b[38;2;210;209;227m⣿\x1b[0m\x1b[38;2;17"
        "2;184;198m⣿\x1b[0m\x1b[38;2;161;170;187m⣿\x1b[0m\x1b"
        "[38;2;163;172;189m⣿\x1b[0m\x1b[38;2;180;186;20"
        "0m⣿\x1b[0m\x1b[38;2;197;199;214m⣿\x1b[0m\x1b[38;2;20"
        "6;209;224m⣿\x1b[0m\x1b[38;2;212;215;230m⣿\x1b[0m\x1b"
        "[38;2;209;212;227m⣿\x1b[0m\x1b[38;2;201;204;21"
        "9m⣿\x1b[0m\x1b[38;2;205;208;223m⣿\x1b[0m\x1b[38;2;19"
        "2;198;212m⣿\x1b[0m\x1b[38;2;85;107;120m⣿\x1b[0m\x1b["
        "38;2;73;95;108m⣿\x1b[0m\x1b[38;2;101;120;134m⣿"
        "\x1b[0m\x1b[38;2;115;134;148m⣿\x1b[0m\n  \x1b[38;2;19"
        "7;204;222m⣿\x1b[0m\x1b[38;2;197;204;222m⣿\x1b[0m\x1b"
        "[38;2;188;197;214m⣿\x1b[0m\x1b[38;2;193;199;21"
        "3m⣿\x1b[0m\x1b[38;2;158;177;194m⣿\x1b[0m\x1b[38;2;15"
        "1;170;187m⣿\x1b[0m\x1b[38;2;136;157;174m⣿\x1b[0m\x1b"
        "[38;2;139;167;181m⣿\x1b[0m\x1b[38;2;156;172;18"
        "7m⣿\x1b[0m\x1b[38;2;184;196;212m⣿\x1b[0m\x1b[38;2;21"
        "7;220;237m⣿\x1b[0m\x1b[38;2;222;221;239m⣿\x1b[0m\x1b"
        "[38;2;211;214;229m⣿\x1b[0m\x1b[38;2;200;203;21"
        "8m⣿\x1b[0m\x1b[38;2;226;229;244m⣿\x1b[0m\x1b[38;2;22"
        "4;227;242m⣿\x1b[0m\x1b[38;2;225;228;243m⣿\x1b[0m\x1b"
        "[38;2;224;227;242m⣿\x1b[0m\x1b[38;2;198;205;22"
        "1m⣿\x1b[0m\x1b[38;2;182;194;208m⣿\x1b[0m\x1b[38;2;22"
        "4;227;242m⣿\x1b[0m\x1b[38;2;225;228;243m⣿\x1b[0m\x1b"
        "[38;2;222;225;240m⣿\x1b[0m\x1b[38;2;214;222;23"
        "3m⣿\x1b[0m\x1b[38;2;191;207;220m⣿\x1b[0m\x1b[38;2;17"
        "0;193;207m⣿\x1b[0m\x1b[38;2;213;225;241m⣿\x1b[0m\x1b"
        "[38;2;204;207;222m⣿\x1b[0m\x1b[38;2;207;215;22"
        "8m⣿\x1b[0m\x1b[38;2;169;191;205m⣿\x1b[0m\x1b[38;2;14"
        "2;179;195m⣿\x1b[0m\x1b[38;2;171;193;204m⣿\x1b[0m\x1b"
        "[38;2;174;186;200m⣿\x1b[0m\x1b[38;2;179;188;20"
        "3m⣿\x1b[0m\x1b[38;2;208;211;228m⣿\x1b[0m\x1b[38;2;20"
        "7;210;225m⣿\x1b[0m\x1b[38;2;183;191;204m⣿\x1b[0m\x1b"
        "[38;2;199;205;219m⣿\x1b[0m\x1b[38;2;182;188;20"
        "2m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;22"
        "4;227;242m⣿\x1b[0m\x1b[38;2;220;223;238m⣿\x1b[0m\x1b"
        "[38;2;222;225;240m⣿\x1b[0m\x1b[38;2;223;226;24"
        "1m⣿\x1b[0m\x1b[38;2;221;224;239m⣿\x1b[0m\x1b[38;2;22"
        "0;223;238m⣿\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b"
        "[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;220;223;23"
        "8m⣿\x1b[0m\x1b[38;2;222;221;237m⣿\x1b[0m\x1b[38;2;22"
        "7;226;242m⣿\x1b[0m\x1b[38;2;217;220;235m⣿\x1b[0m\x1b"
        "[38;2;220;223;238m⣿\x1b[0m\x1b[38;2;217;220;23"
        "5m⣿\x1b[0m\x1b[38;2;220;223;238m⣿\x1b[0m\x1b[38;2;21"
        "6;222;238m⣿\x1b[0m\x1b[38;2;181;190;205m⣿\x1b[0m\x1b"
        "[38;2;202;211;226m⣿\x1b[0m\x1b[38;2;177;183;19"
        "9m⣿\x1b[0m\x1b[38;2;217;220;235m⣿\x1b[0m\x1b[38;2;17"
        "8;192;203m⣿\x1b[0m\x1b[38;2;208;214;228m⣿\x1b[0m\x1b"
        "[38;2;211;224;233m⣿\x1b[0m\x1b[38;2;52;69;77m⣿"
        "\x1b[0m\x1b[38;2;66;93;104m⣿\x1b[0m\x1b[38;2;80;107;"
        "118m⣿\x1b[0m\x1b[38;2;127;146;161m⣿\x1b[0m\x1b[38;2;"
        "123;146;160m⣿\x1b[0m\x1b[38;2;83;107;119m⣿\x1b[0m"
        "\x1b[38;2;97;116;130m⣿\x1b[0m\x1b[38;2;152;164;17"
        "8m⣿\x1b[0m\x1b[38;2;151;163;177m⣿\x1b[0m\x1b[38;2;17"
        "2;185;201m⣿\x1b[0m\x1b[38;2;120;138;152m⣿\x1b[0m\x1b"
        "[38;2;149;156;172m⣿\x1b[0m\x1b[38;2;179;186;20"
        "2m⣿\x1b[0m\x1b[38;2;162;175;191m⣿\x1b[0m\x1b[38;2;16"
        "3;176;192m⣿\x1b[0m\n  \x1b[38;2;204;210;224m⣿\x1b["
        "0m\x1b[38;2;211;217;231m⣿\x1b[0m\x1b[38;2;210;211"
        ";229m⣿\x1b[0m\x1b[38;2;189;190;208m⣿\x1b[0m\x1b[38;2"
        ";201;204;219m⣿\x1b[0m\x1b[38;2;210;213;228m⡿\x1b["
        "0m\x1b[38;2;218;222;234m⣿\x1b[0m\x1b[38;2;204;210"
        ";222m⣿\x1b[0m\x1b[38;2;214;221;231m⣻\x1b[0m\x1b[38;2"
        ";95;102;112m⣿\x1b[0m\x1b[38;2;47;60;69m⣿\x1b[0m\x1b["
        "38;2;74;86;100m⣿\x1b[0m\x1b[38;2;208;218;230m⣛"
        "\x1b[0m\x1b[38;2;200;206;220m⣿\x1b[0m\x1b[38;2;201;1"
        "98;215m⣿\x1b[0m\x1b[38;2;195;192;209m⢿\x1b[0m\x1b[38"
        ";2;200;197;216m⣿\x1b[0m\x1b[38;2;213;205;226m⣿"
        "\x1b[0m\x1b[38;2;194;200;214m⣿\x1b[0m\x1b[38;2;193;1"
        "99;213m⣿\x1b[0m\x1b[38;2;213;216;231m⣿\x1b[0m\x1b[38"
        ";2;214;217;232m⣿\x1b[0m\x1b[38;2;209;212;227m⣿"
        "\x1b[0m\x1b[38;2;216;219;234m⣿\x1b[0m\x1b[38;2;227;2"
        "30;245m⣿\x1b[0m\x1b[38;2;226;230;242m⣿\x1b[0m\x1b[38"
        ";2;197;210;226m⣿\x1b[0m\x1b[38;2;180;197;213m⣿"
        "\x1b[0m\x1b[38;2;210;222;236m⣿\x1b[0m\x1b[38;2;227;2"
        "29;244m⣿\x1b[0m\x1b[38;2;226;228;243m⣿\x1b[0m\x1b[38"
        ";2;228;230;245m⣿\x1b[0m\x1b[38;2;225;227;242m⣿"
        "\x1b[0m\x1b[38;2;219;222;237m⣿\x1b[0m\x1b[38;2;224;2"
        "27;242m⣿\x1b[0m\x1b[38;2;223;226;241m⣿\x1b[0m\x1b[38"
        ";2;225;228;243m⣿\x1b[0m\x1b[38;2;225;228;243m⣿"
        "\x1b[0m\x1b[38;2;204;207;222m⣿\x1b[0m\x1b[38;2;202;2"
        "08;224m⣿\x1b[0m\x1b[38;2;200;206;222m⣿\x1b[0m\x1b[38"
        ";2;209;215;229m⣿\x1b[0m\x1b[38;2;215;221;235m⣿"
        "\x1b[0m\x1b[38;2;198;204;220m⣿\x1b[0m\x1b[38;2;204;2"
        "13;228m⣿\x1b[0m\x1b[38;2;195;202;218m⣿\x1b[0m\x1b[38"
        ";2;210;217;233m⣿\x1b[0m\x1b[38;2;203;212;227m⣿"
        "\x1b[0m\x1b[38;2;164;178;191m⣿\x1b[0m\x1b[38;2;141;1"
        "68;185m⣿\x1b[0m\x1b[38;2;148;166;186m⣿\x1b[0m\x1b[38"
        ";2;173;186;203m⣿\x1b[0m\x1b[38;2;188;195;211m⣿"
        "\x1b[0m\x1b[38;2;154;170;183m⣿\x1b[0m\x1b[38;2;180;1"
        "86;202m⣿\x1b[0m\x1b[38;2;181;193;205m⣿\x1b[0m\x1b[38"
        ";2;213;210;227m⣿\x1b[0m\x1b[38;2;202;208;222m⣿"
        "\x1b[0m\x1b[38;2;203;209;223m⣿\x1b[0m\x1b[38;2;217;2"
        "19;234m⣿\x1b[0m\x1b[38;2;216;219;234m⣿\x1b[0m\x1b[38"
        ";2;213;216;231m⣿\x1b[0m\x1b[38;2;201;204;221m⣿"
        "\x1b[0m\x1b[38;2;188;195;211m⣿\x1b[0m\x1b[38;2;170;1"
        "78;197m⣿\x1b[0m\x1b[38;2;157;170;187m⣿\x1b[0m\x1b[38"
        ";2;149;168;185m⣿\x1b[0m\x1b[38;2;97;129;142m⣿\x1b"
        "[0m\x1b[38;2;76;105;119m⣿\x1b[0m\x1b[38;2;90;119;"
        "133m⣿\x1b[0m\x1b[38;2;73;96;110m⣿\x1b[0m\x1b[38;2;72"
        ";95;109m⣿\x1b[0m\x1b[38;2;75;97;110m⣿\x1b[0m\x1b[38;"
        "2;83;101;111m⣿\x1b[0m\x1b[38;2;113;145;158m⣿\x1b["
        "0m\x1b[38;2;97;129;142m⣿\x1b[0m\x1b[38;2;112;138;"
        "151m⣿\x1b[0m\x1b[38;2;132;149;165m⣿\x1b[0m\n  \x1b[38"
        ";2;48;75;84m⣿\x1b[0m\x1b[38;2;66;90;100m⣿\x1b[0m\x1b"
        "[38;2;91;108;118m⣿\x1b[0m\x1b[38;2;108;124;140"
        "m⣿\x1b[0m\x1b[38;2;90;112;123m⣿\x1b[0m\x1b[38;2;91;1"
        "13;124m⢿\x1b[0m\x1b[38;2;87;109;120m⣿\x1b[0m\x1b[38;"
        "2;165;188;194m⣿\x1b[0m\x1b[38;2;70;89;96m⣿\x1b[0m"
        "\x1b[38;2;96;114;128m⣿\x1b[0m\x1b[38;2;88;116;128"
        "m⣿\x1b[0m\x1b[38;2;77;119;131m⣿\x1b[0m\x1b[38;2;65;1"
        "13;127m⣿\x1b[0m\x1b[38;2;58;121;138m⣿\x1b[0m\x1b[38;"
        "2;66;116;139m⣿\x1b[0m\x1b[38;2;23;69;85m⣿\x1b[0m\x1b"
        "[38;2;87;123;137m⣻\x1b[0m\x1b[38;2;108;140;153"
        "m⣿\x1b[0m\x1b[38;2;89;132;139m⣿\x1b[0m\x1b[38;2;79;9"
        "9;110m⣿\x1b[0m\x1b[38;2;201;211;221m⣿\x1b[0m\x1b[38;"
        "2;209;215;229m⣿\x1b[0m\x1b[38;2;220;226;240m⣿\x1b"
        "[0m\x1b[38;2;210;213;228m⣿\x1b[0m\x1b[38;2;219;22"
        "2;237m⣿\x1b[0m\x1b[38;2;219;228;243m⣿\x1b[0m\x1b[38;"
        "2;191;207;222m⣿\x1b[0m\x1b[38;2;189;212;228m⣿\x1b"
        "[0m\x1b[38;2;224;220;234m⣿\x1b[0m\x1b[38;2;210;21"
        "5;235m⣿\x1b[0m\x1b[38;2;179;223;234m⣿\x1b[0m\x1b[38;"
        "2;96;143;151m⣿\x1b[0m\x1b[38;2;142;166;176m⣿\x1b["
        "0m\x1b[38;2;104;120;136m⣿\x1b[0m\x1b[38;2;129;151"
        ";165m⣿\x1b[0m\x1b[38;2;136;153;171m⣿\x1b[0m\x1b[38;2"
        ";95;114;131m⣿\x1b[0m\x1b[38;2;100;123;139m⣿\x1b[0"
        "m\x1b[38;2;99;139;149m⣻\x1b[0m\x1b[38;2;17;83;97m"
        "⣓\x1b[0m\x1b[38;2;12;99;116m⣟\x1b[0m\x1b[38;2;11;86;"
        "107m⣻\x1b[0m\x1b[38;2;0;67;93m⡾\x1b[0m\x1b[38;2;7;75"
        ";98m⣉\x1b[0m\x1b[38;2;5;77;99m⠀\x1b[0m\x1b[38;2;2;80"
        ";93m⠀\x1b[0m\x1b[38;2;4;93;109m⣙\x1b[0m\x1b[38;2;6;8"
        "5;100m⢋\x1b[0m\x1b[38;2;4;73;89m⠑\x1b[0m\x1b[38;2;2;"
        "73;93m⡂\x1b[0m\x1b[38;2;4;73;89m⢈\x1b[0m\x1b[38;2;1;"
        "68;85m⣉\x1b[0m\x1b[38;2;15;77;92m⣹\x1b[0m\x1b[38;2;2"
        "0;64;77m⣭\x1b[0m\x1b[38;2;67;101;111m⢏\x1b[0m\x1b[38"
        ";2;73;84;90m⢿\x1b[0m\x1b[38;2;53;64;70m⡝\x1b[0m\x1b["
        "38;2;48;59;63m⠛\x1b[0m\x1b[38;2;52;64;64m⢀\x1b[0m"
        "\x1b[38;2;22;29;35m⣈\x1b[0m\x1b[38;2;25;36;40m⣭\x1b["
        "0m\x1b[38;2;40;49;56m⣭\x1b[0m\x1b[38;2;65;71;83m⣉"
        "\x1b[0m\x1b[38;2;29;38;53m⠛\x1b[0m\x1b[38;2;183;192;"
        "207m⠿\x1b[0m\x1b[38;2;180;191;211m⢿\x1b[0m\x1b[38;2;"
        "144;171;178m⢿\x1b[0m\x1b[38;2;220;224;235m⣿\x1b[0"
        "m\x1b[38;2;209;211;224m⣿\x1b[0m\x1b[38;2;155;168;"
        "187m⣿\x1b[0m\x1b[38;2;115;142;159m⣿\x1b[0m\x1b[38;2;"
        "173;189;204m⣿\x1b[0m\x1b[38;2;166;183;199m⣿\x1b[0"
        "m\x1b[38;2;130;147;163m⣿\x1b[0m\x1b[38;2;176;194;"
        "206m⣿\x1b[0m\x1b[38;2;149;167;179m⣿\x1b[0m\x1b[38;2;"
        "180;187;203m⣿\x1b[0m\x1b[38;2;185;191;207m⣿\x1b[0"
        "m\n  \x1b[38;2;53;87;97m⣶\x1b[0m\x1b[38;2;49;94;10"
        "0m⣼\x1b[0m\x1b[38;2;48;91;100m⣿\x1b[0m\x1b[38;2;96;1"
        "32;144m⣻\x1b[0m\x1b[38;2;140;164;166m⣿\x1b[0m\x1b[38"
        ";2;163;174;180m⢿\x1b[0m\x1b[38;2;177;189;201m⣿"
        "\x1b[0m\x1b[38;2;169;186;196m⣿\x1b[0m\x1b[38;2;84;11"
        "1;120m⣿\x1b[0m\x1b[38;2;98;128;139m⣿\x1b[0m\x1b[38;2"
        ";89;121;132m⣿\x1b[0m\x1b[38;2;64;100;114m⣿\x1b[0m"
        "\x1b[38;2;49;85;97m⣿\x1b[0m\x1b[38;2;95;131;143m⣿"
        "\x1b[0m\x1b[38;2;72;116;127m⣿\x1b[0m\x1b[38;2;60;118"
        ";132m⣿\x1b[0m\x1b[38;2;57;119;134m⣿\x1b[0m\x1b[38;2;"
        "54;113;129m⣿\x1b[0m\x1b[38;2;33;112;125m⣿\x1b[0m\x1b"
        "[38;2;56;132;146m⣿\x1b[0m\x1b[38;2;105;171;187"
        "m⣿\x1b[0m\x1b[38;2;26;139;135m⣿\x1b[0m\x1b[38;2;12;1"
        "22;135m⣿\x1b[0m\x1b[38;2;106;173;192m⣿\x1b[0m\x1b[38"
        ";2;43;131;153m⣿\x1b[0m\x1b[38;2;32;143;150m⣿\x1b["
        "0m\x1b[38;2;111;142;170m⣿\x1b[0m\x1b[38;2;35;134;"
        "153m⣿\x1b[0m\x1b[38;2;82;160;173m⣿\x1b[0m\x1b[38;2;5"
        "9;120;141m⣿\x1b[0m\x1b[38;2;66;148;159m⣿\x1b[0m\x1b["
        "38;2;49;107;129m⣿\x1b[0m\x1b[38;2;51;107;124m⣿"
        "\x1b[0m\x1b[38;2;54;116;131m⣿\x1b[0m\x1b[38;2;85;144"
        ";158m⣿\x1b[0m\x1b[38;2;37;103;115m⣿\x1b[0m\x1b[38;2;"
        "58;120;133m⣿\x1b[0m\x1b[38;2;55;104;118m⣿\x1b[0m\x1b"
        "[38;2;49;96;106m⣿\x1b[0m\x1b[38;2;79;115;131m⢿"
        "\x1b[0m\x1b[38;2;78;107;121m⣿\x1b[0m\x1b[38;2;83;109"
        ";122m⣿\x1b[0m\x1b[38;2;69;106;114m⣿\x1b[0m\x1b[38;2;"
        "73;116;133m⣏\x1b[0m\x1b[38;2;45;122;140m⣶\x1b[0m\x1b"
        "[38;2;118;139;156m⢶\x1b[0m\x1b[38;2;37;81;92m⣿"
        "\x1b[0m\x1b[38;2;114;147;156m⣥\x1b[0m\x1b[38;2;104;1"
        "22;132m⣴\x1b[0m\x1b[38;2;84;105;122m⣥\x1b[0m\x1b[38;"
        "2;61;92;110m⣠\x1b[0m\x1b[38;2;47;75;79m⣼\x1b[0m\x1b["
        "38;2;65;88;94m⣍\x1b[0m\x1b[38;2;44;67;75m⢤\x1b[0m"
        "\x1b[38;2;51;74;82m⣋\x1b[0m\x1b[38;2;83;106;114m⠋"
        "\x1b[0m\x1b[38;2;50;73;81m⡉\x1b[0m\x1b[38;2;31;50;56"
        "m⠄\x1b[0m\x1b[38;2;46;66;67m⡉\x1b[0m\x1b[38;2;47;65;"
        "75m⢫\x1b[0m\x1b[38;2;57;75;79m⢍\x1b[0m\x1b[38;2;43;6"
        "1;65m⡈\x1b[0m\x1b[38;2;31;45;54m⢁\x1b[0m\x1b[38;2;45"
        ";74;70m⣤\x1b[0m\x1b[38;2;57;90;83m⣶\x1b[0m\x1b[38;2;"
        "88;113;109m⣤\x1b[0m\x1b[38;2;34;59;56m⣑\x1b[0m\x1b[3"
        "8;2;28;40;40m⠮\x1b[0m\x1b[38;2;48;73;70m⣿\x1b[0m\x1b"
        "[38;2;134;152;156m⢽\x1b[0m\x1b[38;2;65;74;81m⢍"
        "\x1b[0m\x1b[38;2;71;80;87m⡛\x1b[0m\x1b[38;2;33;51;61"
        "m⣩\x1b[0m\x1b[38;2;17;49;60m⠻\x1b[0m\x1b[38;2;16;53;"
        "62m⣛\x1b[0m\x1b[38;2;29;61;72m⣻\x1b[0m\x1b[38;2;26;6"
        "2;76m⣟\x1b[0m\x1b[38;2;42;78;92m⣛\x1b[0m\n  \x1b[38;2"
        ";58;86;87m⣮\x1b[0m\x1b[38;2;110;134;138m⢭\x1b[0m\x1b"
        "[38;2;50;69;75m⣯\x1b[0m\x1b[38;2;165;194;190m⣿"
        "\x1b[0m\x1b[38;2;111;147;133m⣿\x1b[0m\x1b[38;2;158;1"
        "86;163m⣾\x1b[0m\x1b[38;2;76;95;91m⣿\x1b[0m\x1b[38;2;"
        "118;136;136m⣾\x1b[0m\x1b[38;2;167;182;175m⡿\x1b[0"
        "m\x1b[38;2;171;184;167m⣿\x1b[0m\x1b[38;2;192;206;"
        "191m⣿\x1b[0m\x1b[38;2;136;157;148m⣿\x1b[0m\x1b[38;2;"
        "38;74;86m⣟\x1b[0m\x1b[38;2;43;83;93m⣋\x1b[0m\x1b[38;"
        "2;40;77;85m⣿\x1b[0m\x1b[38;2;38;95;102m⣿\x1b[0m\x1b["
        "38;2;59;105;118m⣟\x1b[0m\x1b[38;2;146;175;183m"
        "⣿\x1b[0m\x1b[38;2;207;227;228m⣿\x1b[0m\x1b[38;2;200;"
        "201;203m⣿\x1b[0m\x1b[38;2;216;209;199m⢿\x1b[0m\x1b[3"
        "8;2;208;212;213m⣿\x1b[0m\x1b[38;2;184;203;210m"
        "⣿\x1b[0m\x1b[38;2;76;111;113m⣿\x1b[0m\x1b[38;2;109;1"
        "29;140m⣿\x1b[0m\x1b[38;2;171;152;154m⣿\x1b[0m\x1b[38"
        ";2;190;195;191m⣿\x1b[0m\x1b[38;2;182;193;185m⣾"
        "\x1b[0m\x1b[38;2;155;161;151m⣿\x1b[0m\x1b[38;2;185;1"
        "92;185m⣿\x1b[0m\x1b[38;2;190;201;193m⣿\x1b[0m\x1b[38"
        ";2;61;88;83m⣿\x1b[0m\x1b[38;2;156;180;184m⣿\x1b[0"
        "m\x1b[38;2;64;108;119m⣿\x1b[0m\x1b[38;2;58;87;93m"
        "⣿\x1b[0m\x1b[38;2;152;181;185m⣿\x1b[0m\x1b[38;2;68;9"
        "8;96m⣷\x1b[0m\x1b[38;2;102;127;132m⣿\x1b[0m\x1b[38;2"
        ";62;87;92m⢻\x1b[0m\x1b[38;2;42;66;76m⣿\x1b[0m\x1b[38"
        ";2;40;64;66m⣿\x1b[0m\x1b[38;2;95;124;119m⣷\x1b[0m"
        "\x1b[38;2;88;112;99m⣾\x1b[0m\x1b[38;2;99;122;116m"
        "⣟\x1b[0m\x1b[38;2;41;64;58m⣻\x1b[0m\x1b[38;2;129;154"
        ";148m⣿\x1b[0m\x1b[38;2;118;144;131m⣷\x1b[0m\x1b[38;2"
        ";160;180;153m⢿\x1b[0m\x1b[38;2;188;191;162m⣶\x1b["
        "0m\x1b[38;2;172;180;167m⣭\x1b[0m\x1b[38;2;132;140"
        ";129m⣿\x1b[0m\x1b[38;2;175;189;174m⣿\x1b[0m\x1b[38;2"
        ";129;143;130m⣿\x1b[0m\x1b[38;2;118;142;128m⠿\x1b["
        "0m\x1b[38;2;95;124;106m⡿\x1b[0m\x1b[38;2;51;71;62"
        "m⢓\x1b[0m\x1b[38;2;54;60;56m⡷\x1b[0m\x1b[38;2;60;74;"
        "74m⣘\x1b[0m\x1b[38;2;58;73;76m⣹\x1b[0m\x1b[38;2;59;7"
        "6;83m⠜\x1b[0m\x1b[38;2;37;56;63m⣔\x1b[0m\x1b[38;2;30"
        ";49;56m⡊\x1b[0m\x1b[38;2;37;56;62m⠍\x1b[0m\x1b[38;2;"
        "47;62;69m⢤\x1b[0m\x1b[38;2;49;60;66m⠅\x1b[0m\x1b[38;"
        "2;45;56;58m⢍\x1b[0m\x1b[38;2;54;69;74m⡹\x1b[0m\x1b[3"
        "8;2;34;52;40m⠿\x1b[0m\x1b[38;2;160;156;144m⠿\x1b["
        "0m\x1b[38;2;172;171;143m⢿\x1b[0m\x1b[38;2;149;159"
        ";125m⣾\x1b[0m\x1b[38;2;90;106;95m⣷\x1b[0m\x1b[38;2;1"
        "34;159;153m⢶\x1b[0m\x1b[38;2;112;138;127m⠷\x1b[0m"
        "\x1b[38;2;24;48;34m⣛\x1b[0m\x1b[38;2;100;124;108m"
        "⣳\x1b[0m\x1b[38;2;101;112;104m⣚\x1b[0m\x1b[38;2;101;"
        "117;104m⣑\x1b[0m\n  \x1b[38;2;62;70;55m⢿\x1b[0m\x1b[3"
        "8;2;73;76;65m⣿\x1b[0m\x1b[38;2;126;133;126m⣿\x1b["
        "0m\x1b[38;2;132;145;138m⣷\x1b[0m\x1b[38;2;81;102;"
        "95m⣺\x1b[0m\x1b[38;2;67;87;86m⣻\x1b[0m\x1b[38;2;109;"
        "130;135m⣬\x1b[0m\x1b[38;2;96;116;127m⣯\x1b[0m\x1b[38"
        ";2;182;182;184m⠵\x1b[0m\x1b[38;2;194;199;176m⢥"
        "\x1b[0m\x1b[38;2;57;66;63m⣶\x1b[0m\x1b[38;2;201;206;"
        "186m⣾\x1b[0m\x1b[38;2;132;129;114m⣶\x1b[0m\x1b[38;2;"
        "189;214;185m⣿\x1b[0m\x1b[38;2;118;126;105m⣽\x1b[0"
        "m\x1b[38;2;167;172;150m⣿\x1b[0m\x1b[38;2;227;226;"
        "208m⣿\x1b[0m\x1b[38;2;183;191;170m⣿\x1b[0m\x1b[38;2;"
        "167;179;165m⣿\x1b[0m\x1b[38;2;155;180;161m⣿\x1b[0"
        "m\x1b[38;2;163;183;171m⣿\x1b[0m\x1b[38;2;102;123;"
        "126m⣿\x1b[0m\x1b[38;2;188;203;196m⣮\x1b[0m\x1b[38;2;"
        "202;210;195m⣿\x1b[0m\x1b[38;2;195;203;192m⣿\x1b[0"
        "m\x1b[38;2;175;190;187m⣿\x1b[0m\x1b[38;2;113;135;"
        "133m⣯\x1b[0m\x1b[38;2;116;130;139m⣿\x1b[0m\x1b[38;2;"
        "183;200;190m⣿\x1b[0m\x1b[38;2;143;157;160m⣿\x1b[0"
        "m\x1b[38;2;220;230;231m⣷\x1b[0m\x1b[38;2;231;236;"
        "232m⣿\x1b[0m\x1b[38;2;209;210;202m⣷\x1b[0m\x1b[38;2;"
        "192;192;182m⣿\x1b[0m\x1b[38;2;207;207;197m⣿\x1b[0"
        "m\x1b[38;2;93;105;95m⣿\x1b[0m\x1b[38;2;55;70;75m⣏"
        "\x1b[0m\x1b[38;2;78;89;91m⣿\x1b[0m\x1b[38;2;207;210;"
        "203m⡿\x1b[0m\x1b[38;2;205;196;189m⡿\x1b[0m\x1b[38;2;"
        "199;189;188m⡿\x1b[0m\x1b[38;2;88;95;88m⣿\x1b[0m\x1b["
        "38;2;187;191;190m⣿\x1b[0m\x1b[38;2;201;197;185"
        "m⣷\x1b[0m\x1b[38;2;177;168;153m⠾\x1b[0m\x1b[38;2;26;"
        "39;29m⠯\x1b[0m\x1b[38;2;128;145;127m⡷\x1b[0m\x1b[38;"
        "2;129;134;127m⠿\x1b[0m\x1b[38;2;149;160;154m⣹\x1b"
        "[0m\x1b[38;2;138;147;126m⣿\x1b[0m\x1b[38;2;46;59;"
        "65m⠑\x1b[0m\x1b[38;2;103;126;116m⣿\x1b[0m\x1b[38;2;1"
        "02;128;117m⣾\x1b[0m\x1b[38;2;57;82;79m⢏\x1b[0m\x1b[3"
        "8;2;34;45;51m⡁\x1b[0m\x1b[38;2;76;87;91m⡌\x1b[0m\x1b"
        "[38;2;71;83;83m⡸\x1b[0m\x1b[38;2;56;67;63m⡩\x1b[0"
        "m\x1b[38;2;43;54;50m⡄\x1b[0m\x1b[38;2;59;69;68m⡥\x1b"
        "[0m\x1b[38;2;55;62;70m⣈\x1b[0m\x1b[38;2;48;57;56m"
        "⠉\x1b[0m\x1b[38;2;45;55;57m⠐\x1b[0m\x1b[38;2;52;62;6"
        "4m⠑\x1b[0m\x1b[38;2;58;69;71m⡀\x1b[0m\x1b[38;2;53;61"
        ";64m⠀\x1b[0m\x1b[38;2;52;58;58m⠒\x1b[0m\x1b[38;2;64;"
        "74;73m⢖\x1b[0m\x1b[38;2;50;62;62m⠒\x1b[0m\x1b[38;2;5"
        "0;58;60m⣂\x1b[0m\x1b[38;2;42;51;56m⠈\x1b[0m\x1b[38;2"
        ";35;45;46m⠉\x1b[0m\x1b[38;2;116;122;118m⠅\x1b[0m\x1b"
        "[38;2;44;54;55m⠈\x1b[0m\x1b[38;2;40;50;49m⠽\x1b[0"
        "m\x1b[38;2;50;60;59m⠛\x1b[0m\x1b[38;2;53;60;66m⢛\x1b"
        "[0m\x1b[38;2;195;204;203m⣿\x1b[0m\n  \x1b[38;2;136"
        ";144;129m⣿\x1b[0m\x1b[38;2;218;220;206m⣷\x1b[0m\x1b["
        "38;2;221;221;209m⣿\x1b[0m\x1b[38;2;140;145;141"
        "m⣿\x1b[0m\x1b[38;2;108;116;118m⣿\x1b[0m\x1b[38;2;36;"
        "44;29m⣯\x1b[0m\x1b[38;2;222;223;209m⣿\x1b[0m\x1b[38;"
        "2;205;207;206m⣷\x1b[0m\x1b[38;2;78;91;84m⠥\x1b[0m"
        "\x1b[38;2;127;140;133m⢥\x1b[0m\x1b[38;2;177;186;1"
        "81m⣿\x1b[0m\x1b[38;2;170;179;178m⠿\x1b[0m\x1b[38;2;1"
        "37;137;147m⢿\x1b[0m\x1b[38;2;187;188;193m⣿\x1b[0m"
        "\x1b[38;2;181;182;177m⣿\x1b[0m\x1b[38;2;234;233;2"
        "39m⣿\x1b[0m\x1b[38;2;211;211;211m⣿\x1b[0m\x1b[38;2;2"
        "03;208;204m⣾\x1b[0m\x1b[38;2;163;174;170m⣿\x1b[0m"
        "\x1b[38;2;120;140;129m⣿\x1b[0m\x1b[38;2;167;178;1"
        "80m⣿\x1b[0m\x1b[38;2;209;220;204m⣿\x1b[0m\x1b[38;2;1"
        "93;195;192m⣿\x1b[0m\x1b[38;2;149;149;149m⣿\x1b[0m"
        "\x1b[38;2;194;203;186m⣿\x1b[0m\x1b[38;2;208;210;1"
        "96m⣿\x1b[0m\x1b[38;2;114;129;110m⣿\x1b[0m\x1b[38;2;1"
        "57;164;146m⣯\x1b[0m\x1b[38;2;175;182;166m⣿\x1b[0m"
        "\x1b[38;2;123;146;128m⣿\x1b[0m\x1b[38;2;182;192;1"
        "83m⣿\x1b[0m\x1b[38;2;156;172;169m⣿\x1b[0m\x1b[38;2;2"
        "14;224;223m⣿\x1b[0m\x1b[38;2;166;176;177m⣿\x1b[0m"
        "\x1b[38;2;58;68;69m⠛\x1b[0m\x1b[38;2;36;50;50m⣏\x1b["
        "0m\x1b[38;2;53;66;72m⣛\x1b[0m\x1b[38;2;19;31;31m⢫"
        "\x1b[0m\x1b[38;2;162;172;171m⡷\x1b[0m\x1b[38;2;119;1"
        "37;137m⣽\x1b[0m\x1b[38;2;87;98;100m⣷\x1b[0m\x1b[38;2"
        ";98;107;112m⣿\x1b[0m\x1b[38;2;78;94;93m⣷\x1b[0m\x1b["
        "38;2;70;85;78m⣿\x1b[0m\x1b[38;2;84;100;90m⢷\x1b[0"
        "m\x1b[38;2;122;135;126m⣺\x1b[0m\x1b[38;2;79;93;80"
        "m⡯\x1b[0m\x1b[38;2;87;99;99m⠪\x1b[0m\x1b[38;2;74;91;"
        "85m⣮\x1b[0m\x1b[38;2;38;51;42m⠚\x1b[0m\x1b[38;2;52;6"
        "5;56m⢹\x1b[0m\x1b[38;2;92;107;86m⢽\x1b[0m\x1b[38;2;8"
        "1;92;84m⣿\x1b[0m\x1b[38;2;107;136;116m⣿\x1b[0m\x1b[3"
        "8;2;120;145;123m⣷\x1b[0m\x1b[38;2;176;182;178m"
        "⣿\x1b[0m\x1b[38;2;37;55;43m⣿\x1b[0m\x1b[38;2;76;101;"
        "72m⣿\x1b[0m\x1b[38;2;3;35;14m⣟\x1b[0m\x1b[38;2;41;64"
        ";46m⣻\x1b[0m\x1b[38;2;113;138;99m⣶\x1b[0m\x1b[38;2;8"
        "8;109;92m⣶\x1b[0m\x1b[38;2;93;113;88m⡦\x1b[0m\x1b[38"
        ";2;39;45;41m⠀\x1b[0m\x1b[38;2;50;59;56m⢀\x1b[0m\x1b["
        "38;2;45;58;49m⠠\x1b[0m\x1b[38;2;44;61;51m⢸\x1b[0m"
        "\x1b[38;2;101;125;93m⣤\x1b[0m\x1b[38;2;115;130;87"
        "m⣾\x1b[0m\x1b[38;2;31;41;32m⡔\x1b[0m\x1b[38;2;108;12"
        "1;112m⡗\x1b[0m\x1b[38;2;37;50;41m⣐\x1b[0m\x1b[38;2;4"
        "1;47;43m⣀\x1b[0m\x1b[38;2;49;55;55m⠂\x1b[0m\x1b[38;2"
        ";44;49;52m⠀\x1b[0m\x1b[38;2;28;33;36m⠀\x1b[0m\x1b[38"
        ";2;46;51;47m⣭\x1b[0m\x1b[38;2;61;68;61m⠖\x1b[0m\n "
        " \x1b[38;2;38;36;39m⣟\x1b[0m\x1b[38;2;111;120;99m"
        "⢻\x1b[0m\x1b[38;2;125;133;135m⡟\x1b[0m\x1b[38;2;120;"
        "121;123m⢟\x1b[0m\x1b[38;2;125;127;116m⣿\x1b[0m\x1b[3"
        "8;2;119;117;104m⣷\x1b[0m\x1b[38;2;160;157;140m"
        "⣿\x1b[0m\x1b[38;2;103;104;86m⣿\x1b[0m\x1b[38;2;164;1"
        "72;159m⣯\x1b[0m\x1b[38;2;97;108;102m⣰\x1b[0m\x1b[38;"
        "2;64;71;63m⣾\x1b[0m\x1b[38;2;111;117;117m⡿\x1b[0m"
        "\x1b[38;2;110;118;120m⣿\x1b[0m\x1b[38;2;76;84;86m"
        "⣿\x1b[0m\x1b[38;2;94;103;98m⡿\x1b[0m\x1b[38;2;149;16"
        "0;143m⣿\x1b[0m\x1b[38;2;69;85;72m⡞\x1b[0m\x1b[38;2;1"
        "27;139;127m⡟\x1b[0m\x1b[38;2;107;128;113m⣿\x1b[0m"
        "\x1b[38;2;180;186;172m⣿\x1b[0m\x1b[38;2;171;178;1"
        "60m⣿\x1b[0m\x1b[38;2;183;182;162m⢿\x1b[0m\x1b[38;2;1"
        "89;186;181m⡿\x1b[0m\x1b[38;2;195;199;200m⣿\x1b[0m"
        "\x1b[38;2;103;106;97m⡿\x1b[0m\x1b[38;2;177;177;16"
        "7m⠿\x1b[0m\x1b[38;2;50;59;64m⢯\x1b[0m\x1b[38;2;49;65"
        ";54m⣝\x1b[0m\x1b[38;2;65;82;66m⣿\x1b[0m\x1b[38;2;162"
        ";172;147m⣷\x1b[0m\x1b[38;2;199;203;188m⣿\x1b[0m\x1b["
        "38;2;189;190;172m⣿\x1b[0m\x1b[38;2;144;147;136"
        "m⣟\x1b[0m\x1b[38;2;73;91;77m⣾\x1b[0m\x1b[38;2;147;16"
        "2;155m⣷\x1b[0m\x1b[38;2;56;77;80m⢻\x1b[0m\x1b[38;2;9"
        "6;111;116m⣿\x1b[0m\x1b[38;2;47;57;66m⣟\x1b[0m\x1b[38"
        ";2;41;50;55m⣫\x1b[0m\x1b[38;2;162;175;184m⣿\x1b[0"
        "m\x1b[38;2;34;44;43m⣟\x1b[0m\x1b[38;2;65;74;71m⣿\x1b"
        "[0m\x1b[38;2;89;105;94m⣿\x1b[0m\x1b[38;2;89;106;1"
        "00m⣿\x1b[0m\x1b[38;2;117;134;124m⣿\x1b[0m\x1b[38;2;1"
        "12;129;119m⡏\x1b[0m\x1b[38;2;57;78;71m⡯\x1b[0m\x1b[3"
        "8;2;55;79;66m⡽\x1b[0m\x1b[38;2;62;79;73m⣝\x1b[0m\x1b"
        "[38;2;43;60;54m⠉\x1b[0m\x1b[38;2;75;91;91m⠭\x1b[0"
        "m\x1b[38;2;163;173;185m⣿\x1b[0m\x1b[38;2;119;121;"
        "100m⣿\x1b[0m\x1b[38;2;87;100;82m⣿\x1b[0m\x1b[38;2;96"
        ";111;114m⣿\x1b[0m\x1b[38;2;33;47;47m⠿\x1b[0m\x1b[38;"
        "2;46;57;53m⠿\x1b[0m\x1b[38;2;173;184;178m⢻\x1b[0m"
        "\x1b[38;2;224;231;223m⣿\x1b[0m\x1b[38;2;230;229;2"
        "45m⣿\x1b[0m\x1b[38;2;192;185;177m⣿\x1b[0m\x1b[38;2;1"
        "11;117;105m⣷\x1b[0m\x1b[38;2;57;68;60m⣯\x1b[0m\x1b[3"
        "8;2;113;120;130m⣏\x1b[0m\x1b[38;2;41;47;47m⣙\x1b["
        "0m\x1b[38;2;99;114;107m⣶\x1b[0m\x1b[38;2;20;24;33"
        "m⠈\x1b[0m\x1b[38;2;49;59;60m⡻\x1b[0m\x1b[38;2;60;69;"
        "64m⢺\x1b[0m\x1b[38;2;130;140;129m⡿\x1b[0m\x1b[38;2;1"
        "87;195;198m⠿\x1b[0m\x1b[38;2;50;59;56m⣿\x1b[0m\x1b[3"
        "8;2;93;103;94m⣻\x1b[0m\x1b[38;2;157;166;161m⣷\x1b"
        "[0m\x1b[38;2;69;85;75m⣇\x1b[0m\x1b[38;2;34;50;37m"
        "⢥\x1b[0m\x1b[38;2;45;57;45m⣗\x1b[0m\x1b[38;2;243;251"
        ";236m⣿\x1b[0m\n  \x1b[38;2;35;142;162m⣿\x1b[0m\x1b[38"
        ";2;77;166;184m⣯\x1b[0m\x1b[38;2;110;175;197m⣿\x1b"
        "[0m\x1b[38;2;104;179;202m⣭\x1b[0m\x1b[38;2;91;183"
        ";204m⣿\x1b[0m\x1b[38;2;82;177;197m⣿\x1b[0m\x1b[38;2;"
        "88;176;198m⣿\x1b[0m\x1b[38;2;56;155;174m⣯\x1b[0m\x1b"
        "[38;2;90;183;200m⣿\x1b[0m\x1b[38;2;148;191;210"
        "m⣿\x1b[0m\x1b[38;2;103;186;200m⣿\x1b[0m\x1b[38;2;80;"
        "176;192m⣯\x1b[0m\x1b[38;2;17;140;158m⣬\x1b[0m\x1b[38"
        ";2;43;155;177m⣿\x1b[0m\x1b[38;2;71;156;176m⣿\x1b["
        "0m\x1b[38;2;59;118;132m⣿\x1b[0m\x1b[38;2;63;110;1"
        "26m⣿\x1b[0m\x1b[38;2;186;200;211m⣿\x1b[0m\x1b[38;2;1"
        "15;130;125m⢿\x1b[0m\x1b[38;2;53;68;61m⣣\x1b[0m\x1b[3"
        "8;2;162;164;153m⣭\x1b[0m\x1b[38;2;102;108;106m"
        "⣼\x1b[0m\x1b[38;2;18;23;26m⣷\x1b[0m\x1b[38;2;48;53;5"
        "7m⢟\x1b[0m\x1b[38;2;127;129;124m⣥\x1b[0m\x1b[38;2;10"
        "5;108;89m⣾\x1b[0m\x1b[38;2;70;79;60m⣿\x1b[0m\x1b[38;"
        "2;60;71;63m⣟\x1b[0m\x1b[38;2;70;93;75m⣿\x1b[0m\x1b[3"
        "8;2;96;123;104m⣿\x1b[0m\x1b[38;2;63;101;78m⣭\x1b["
        "0m\x1b[38;2;87;115;93m⣿\x1b[0m\x1b[38;2;81;109;94"
        "m⣿\x1b[0m\x1b[38;2;170;181;175m⣿\x1b[0m\x1b[38;2;110"
        ";121;107m⣿\x1b[0m\x1b[38;2;156;154;139m⣿\x1b[0m\x1b["
        "38;2;189;188;170m⣷\x1b[0m\x1b[38;2;180;189;172"
        "m⢯\x1b[0m\x1b[38;2;92;110;114m⣽\x1b[0m\x1b[38;2;151;"
        "164;173m⣿\x1b[0m\x1b[38;2;195;196;200m⣿\x1b[0m\x1b[3"
        "8;2;161;163;178m⣿\x1b[0m\x1b[38;2;127;134;140m"
        "⡿\x1b[0m\x1b[38;2;213;234;229m⢷\x1b[0m\x1b[38;2;181;"
        "170;178m⣷\x1b[0m\x1b[38;2;183;177;179m⣽\x1b[0m\x1b[3"
        "8;2;190;183;199m⣷\x1b[0m\x1b[38;2;157;154;163m"
        "⣾\x1b[0m\x1b[38;2;147;160;169m⣶\x1b[0m\x1b[38;2;182;"
        "184;196m⡯\x1b[0m\x1b[38;2;122;124;136m⣿\x1b[0m\x1b[3"
        "8;2;156;165;174m⠿\x1b[0m\x1b[38;2;179;190;194m"
        "⣽\x1b[0m\x1b[38;2;46;53;59m⣯\x1b[0m\x1b[38;2;163;178"
        ";181m⣿\x1b[0m\x1b[38;2;156;167;171m⡿\x1b[0m\x1b[38;2"
        ";95;108;116m⠿\x1b[0m\x1b[38;2;29;42;50m⠙\x1b[0m\x1b["
        "38;2;41;54;62m⠛\x1b[0m\x1b[38;2;99;106;114m⣹\x1b["
        "0m\x1b[38;2;134;139;145m⡽\x1b[0m\x1b[38;2;83;97;9"
        "8m⡿\x1b[0m\x1b[38;2;167;168;170m⠭\x1b[0m\x1b[38;2;29"
        ";41;41m⠙\x1b[0m\x1b[38;2;168;170;183m⠻\x1b[0m\x1b[38"
        ";2;191;193;206m⣿\x1b[0m\x1b[38;2;168;169;161m⣝"
        "\x1b[0m\x1b[38;2;40;49;44m⣳\x1b[0m\x1b[38;2;97;101;1"
        "04m⣿\x1b[0m\x1b[38;2;38;49;43m⡿\x1b[0m\x1b[38;2;152;"
        "157;161m⣿\x1b[0m\x1b[38;2;156;161;165m⣿\x1b[0m\x1b[3"
        "8;2;128;139;143m⣿\x1b[0m\x1b[38;2;191;201;202m"
        "⡻\x1b[0m\x1b[38;2;158;167;174m⣿\x1b[0m\x1b[38;2;39;3"
        "2;40m⣗\x1b[0m\x1b[38;2;106;115;120m⡶\x1b[0m\x1b[38;2"
        ";96;106;108m⣿\x1b[0m\n  \x1b[38;2;100;178;200m⣿"
        "\x1b[0m\x1b[38;2;114;186;210m⣿\x1b[0m\x1b[38;2;107;1"
        "83;206m⣿\x1b[0m\x1b[38;2;103;179;202m⣿\x1b[0m\x1b[38"
        ";2;95;180;200m⣿\x1b[0m\x1b[38;2;97;182;202m⣿\x1b["
        "0m\x1b[38;2;103;183;206m⣿\x1b[0m\x1b[38;2;102;187"
        ";208m⣿\x1b[0m\x1b[38;2;88;183;205m⣿\x1b[0m\x1b[38;2;"
        "100;188;208m⣿\x1b[0m\x1b[38;2;107;192;212m⣿\x1b[0"
        "m\x1b[38;2;113;191;213m⣿\x1b[0m\x1b[38;2;120;189;"
        "205m⣿\x1b[0m\x1b[38;2;128;193;211m⣿\x1b[0m\x1b[38;2;"
        "143;194;213m⣿\x1b[0m\x1b[38;2;151;198;214m⣿\x1b[0"
        "m\x1b[38;2;166;199;218m⣿\x1b[0m\x1b[38;2;166;202;"
        "216m⣿\x1b[0m\x1b[38;2;166;200;210m⣿\x1b[0m\x1b[38;2;"
        "164;200;212m⣿\x1b[0m\x1b[38;2;163;200;209m⣿\x1b[0"
        "m\x1b[38;2;143;190;210m⣾\x1b[0m\x1b[38;2;140;197;"
        "214m⣷\x1b[0m\x1b[38;2;97;186;202m⣯\x1b[0m\x1b[38;2;1"
        "12;181;196m⣭\x1b[0m\x1b[38;2;83;151;164m⣽\x1b[0m\x1b"
        "[38;2;37;104;121m⣾\x1b[0m\x1b[38;2;21;71;82m⣟\x1b"
        "[0m\x1b[38;2;17;49;60m⣛\x1b[0m\x1b[38;2;35;65;73m"
        "⣛\x1b[0m\x1b[38;2;55;84;92m⣹\x1b[0m\x1b[38;2;27;52;4"
        "8m⢋\x1b[0m\x1b[38;2;106;118;118m⣼\x1b[0m\x1b[38;2;11"
        "2;124;120m⢽\x1b[0m\x1b[38;2;54;71;61m⠻\x1b[0m\x1b[38"
        ";2;92;107;88m⡯\x1b[0m\x1b[38;2;82;97;90m⣛\x1b[0m\x1b"
        "[38;2;120;127;109m⢿\x1b[0m\x1b[38;2;96;103;85m"
        "⡿\x1b[0m\x1b[38;2;157;161;147m⢻\x1b[0m\x1b[38;2;203;"
        "210;192m⡿\x1b[0m\x1b[38;2;189;195;181m⡾\x1b[0m\x1b[3"
        "8;2;128;133;126m⣿\x1b[0m\x1b[38;2;161;145;155m"
        "⣿\x1b[0m\x1b[38;2;152;148;163m⣿\x1b[0m\x1b[38;2;164;"
        "169;172m⣿\x1b[0m\x1b[38;2;244;233;241m⣿\x1b[0m\x1b[3"
        "8;2;180;204;204m⣟\x1b[0m\x1b[38;2;151;148;155m"
        "⣿\x1b[0m\x1b[38;2;89;109;108m⣟\x1b[0m\x1b[38;2;179;1"
        "90;192m⣿\x1b[0m\x1b[38;2;171;187;202m⣿\x1b[0m\x1b[38"
        ";2;56;62;60m⣟\x1b[0m\x1b[38;2;101;109;112m⡿\x1b[0"
        "m\x1b[38;2;78;81;86m⡫\x1b[0m\x1b[38;2;203;211;213"
        "m⠞\x1b[0m\x1b[38;2;239;243;246m⠻\x1b[0m\x1b[38;2;175"
        ";176;178m⢽\x1b[0m\x1b[38;2;51;46;50m⣿\x1b[0m\x1b[38;"
        "2;33;42;49m⣿\x1b[0m\x1b[38;2;136;129;137m⣿\x1b[0m"
        "\x1b[38;2;139;140;145m⡿\x1b[0m\x1b[38;2;105;108;1"
        "13m⣿\x1b[0m\x1b[38;2;170;160;169m⣿\x1b[0m\x1b[38;2;6"
        "9;69;81m⣿\x1b[0m\x1b[38;2;75;80;84m⣿\x1b[0m\x1b[38;2"
        ";103;102;107m⣿\x1b[0m\x1b[38;2;154;158;161m⠿\x1b["
        "0m\x1b[38;2;91;94;99m⢻\x1b[0m\x1b[38;2;131;134;13"
        "9m⣿\x1b[0m\x1b[38;2;106;120;123m⣻\x1b[0m\x1b[38;2;96"
        ";101;104m⣿\x1b[0m\x1b[38;2;88;96;98m⣏\x1b[0m\x1b[38;"
        "2;117;118;122m⣬\x1b[0m\x1b[38;2;151;149;162m⣽\x1b"
        "[0m\x1b[38;2;38;41;50m⣷\x1b[0m\x1b[38;2;140;143;1"
        "50m⣭\x1b[0m\x1b[38;2;186;195;202m⡿\x1b[0m\n  \x1b[38;"
        "2;74;174;198m⣿\x1b[0m\x1b[38;2;74;172;197m⣿\x1b[0"
        "m\x1b[38;2;92;185;203m⣿\x1b[0m\x1b[38;2;102;182;2"
        "05m⣿\x1b[0m\x1b[38;2;101;176;199m⣿\x1b[0m\x1b[38;2;8"
        "4;175;193m⣿\x1b[0m\x1b[38;2;82;182;198m⣿\x1b[0m\x1b["
        "38;2;87;175;195m⣿\x1b[0m\x1b[38;2;98;179;208m⣿"
        "\x1b[0m\x1b[38;2;100;181;210m⣿\x1b[0m\x1b[38;2;99;18"
        "5;210m⣿\x1b[0m\x1b[38;2;96;181;202m⣿\x1b[0m\x1b[38;2"
        ";107;185;207m⣿\x1b[0m\x1b[38;2;112;187;208m⣿\x1b["
        "0m\x1b[38;2;116;187;205m⣿\x1b[0m\x1b[38;2;125;177"
        ";198m⣿\x1b[0m\x1b[38;2;139;195;210m⣿\x1b[0m\x1b[38;2"
        ";135;193;207m⣿\x1b[0m\x1b[38;2;149;195;211m⣿\x1b["
        "0m\x1b[38;2;148;194;210m⣿\x1b[0m\x1b[38;2;143;195"
        ";209m⣿\x1b[0m\x1b[38;2;144;197;215m⣿\x1b[0m\x1b[38;2"
        ";142;195;213m⣿\x1b[0m\x1b[38;2;141;190;205m⣿\x1b["
        "0m\x1b[38;2;151;200;215m⣿\x1b[0m\x1b[38;2;154;198"
        ";211m⣿\x1b[0m\x1b[38;2;156;202;218m⣿\x1b[0m\x1b[38;2"
        ";153;202;217m⣿\x1b[0m\x1b[38;2;149;200;219m⣿\x1b["
        "0m\x1b[38;2;130;202;226m⣿\x1b[0m\x1b[38;2;141;199"
        ";219m⣿\x1b[0m\x1b[38;2;134;204;216m⣿\x1b[0m\x1b[38;2"
        ";124;192;205m⣿\x1b[0m\x1b[38;2;106;199;216m⣿\x1b["
        "0m\x1b[38;2;115;198;214m⣿\x1b[0m\x1b[38;2;120;189"
        ";204m⣿\x1b[0m\x1b[38;2;109;191;212m⣷\x1b[0m\x1b[38;2"
        ";105;181;204m⣶\x1b[0m\x1b[38;2;67;178;198m⣾\x1b[0"
        "m\x1b[38;2;80;181;201m⣥\x1b[0m\x1b[38;2;31;54;68m"
        "⣤\x1b[0m\x1b[38;2;36;50;59m⣀\x1b[0m\x1b[38;2;43;55;6"
        "7m⣩\x1b[0m\x1b[38;2;44;62;74m⣿\x1b[0m\x1b[38;2;69;90"
        ";93m⣛\x1b[0m\x1b[38;2;49;63;66m⣿\x1b[0m\x1b[38;2;80;"
        "97;104m⣿\x1b[0m\x1b[38;2;147;163;163m⣿\x1b[0m\x1b[38"
        ";2;38;54;51m⣟\x1b[0m\x1b[38;2;12;32;41m⣃\x1b[0m\x1b["
        "38;2;69;98;116m⣳\x1b[0m\x1b[38;2;112;159;177m⣮"
        "\x1b[0m\x1b[38;2;82;133;154m⣽\x1b[0m\x1b[38;2;126;16"
        "9;186m⣮\x1b[0m\x1b[38;2;60;132;147m⣭\x1b[0m\x1b[38;2"
        ";70;120;145m⣯\x1b[0m\x1b[38;2;65;138;155m⣧\x1b[0m"
        "\x1b[38;2;78;141;159m⣦\x1b[0m\x1b[38;2;80;153;168"
        "m⣤\x1b[0m\x1b[38;2;71;128;148m⣥\x1b[0m\x1b[38;2;94;1"
        "54;165m⣾\x1b[0m\x1b[38;2;81;152;170m⣼\x1b[0m\x1b[38;"
        "2;56;127;149m⣦\x1b[0m\x1b[38;2;78;124;139m⣬\x1b[0"
        "m\x1b[38;2;89;126;144m⣝\x1b[0m\x1b[38;2;81;129;14"
        "3m⣵\x1b[0m\x1b[38;2;79;126;146m⣦\x1b[0m\x1b[38;2;38;"
        "79;97m⣤\x1b[0m\x1b[38;2;86;137;154m⣶\x1b[0m\x1b[38;2"
        ";17;51;60m⣺\x1b[0m\x1b[38;2;40;72;93m⣽\x1b[0m\x1b[38"
        ";2;77;118;136m⣭\x1b[0m\x1b[38;2;35;56;75m⣍\x1b[0m"
        "\x1b[38;2;29;39;51m⣉\x1b[0m\x1b[38;2;22;25;40m⣉\x1b["
        "0m\x1b[38;2;27;33;47m⠛\x1b[0m\x1b[38;2;28;35;45m⣋"
        "\x1b[0m\x1b[38;2;0;8;23m⢑\x1b[0m\n  \x1b[38;2;43;168;"
        "196m⣿\x1b[0m\x1b[38;2;32;157;185m⣿\x1b[0m\x1b[38;2;6"
        "5;176;203m⣿\x1b[0m\x1b[38;2;38;156;186m⣿\x1b[0m\x1b["
        "38;2;38;166;193m⣿\x1b[0m\x1b[38;2;39;167;194m⣿"
        "\x1b[0m\x1b[38;2;33;157;181m⣿\x1b[0m\x1b[38;2;43;167"
        ";191m⣿\x1b[0m\x1b[38;2;55;170;197m⣿\x1b[0m\x1b[38;2;"
        "70;176;202m⣿\x1b[0m\x1b[38;2;78;180;205m⣿\x1b[0m\x1b"
        "[38;2;76;178;203m⣿\x1b[0m\x1b[38;2;68;177;200m"
        "⣿\x1b[0m\x1b[38;2;73;177;202m⣿\x1b[0m\x1b[38;2;70;17"
        "6;198m⣿\x1b[0m\x1b[38;2;73;175;198m⣿\x1b[0m\x1b[38;2"
        ";89;188;211m⣿\x1b[0m\x1b[38;2;100;188;210m⣿\x1b[0"
        "m\x1b[38;2;116;197;218m⣿\x1b[0m\x1b[38;2;111;186;"
        "209m⣿\x1b[0m\x1b[38;2;120;193;212m⣿\x1b[0m\x1b[38;2;"
        "109;182;201m⣿\x1b[0m\x1b[38;2;118;195;213m⣿\x1b[0"
        "m\x1b[38;2;136;199;217m⣿\x1b[0m\x1b[38;2;146;204;"
        "224m⣿\x1b[0m\x1b[38;2;133;193;217m⣿\x1b[0m\x1b[38;2;"
        "118;191;210m⣿\x1b[0m\x1b[38;2;116;193;213m⠿\x1b[0"
        "m\x1b[38;2;116;193;213m⣿\x1b[0m\x1b[38;2;106;193;"
        "212m⣿\x1b[0m\x1b[38;2;93;188;208m⣿\x1b[0m\x1b[38;2;8"
        "6;186;202m⣿\x1b[0m\x1b[38;2;93;188;206m⣿\x1b[0m\x1b["
        "38;2;88;185;201m⣿\x1b[0m\x1b[38;2;102;187;207m"
        "⣿\x1b[0m\x1b[38;2;82;184;206m⣿\x1b[0m\x1b[38;2;63;18"
        "0;197m⣿\x1b[0m\x1b[38;2;95;199;224m⣿\x1b[0m\x1b[38;2"
        ";82;185;204m⣿\x1b[0m\x1b[38;2;87;192;211m⣿\x1b[0m"
        "\x1b[38;2;84;181;198m⣿\x1b[0m\x1b[38;2;118;189;20"
        "7m⣿\x1b[0m\x1b[38;2;112;185;200m⣿\x1b[0m\x1b[38;2;13"
        "8;201;219m⣿\x1b[0m\x1b[38;2;139;188;205m⣿\x1b[0m\x1b"
        "[38;2;134;186;208m⣿\x1b[0m\x1b[38;2;146;193;21"
        "3m⣿\x1b[0m\x1b[38;2;129;182;198m⣿\x1b[0m\x1b[38;2;13"
        "3;186;202m⣿\x1b[0m\x1b[38;2;150;196;212m⣿\x1b[0m\x1b"
        "[38;2;144;190;206m⣿\x1b[0m\x1b[38;2;138;189;20"
        "6m⣿\x1b[0m\x1b[38;2;121;177;192m⣿\x1b[0m\x1b[38;2;11"
        "6;181;201m⣿\x1b[0m\x1b[38;2;107;179;201m⣿\x1b[0m\x1b"
        "[38;2;96;173;193m⣿\x1b[0m\x1b[38;2;92;170;190m"
        "⣿\x1b[0m\x1b[38;2;81;168;185m⣿\x1b[0m\x1b[38;2;74;16"
        "6;181m⣿\x1b[0m\x1b[38;2;79;159;182m⣿\x1b[0m\x1b[38;2"
        ";59;160;178m⣿\x1b[0m\x1b[38;2;61;158;177m⣿\x1b[0m"
        "\x1b[38;2;69;168;189m⣿\x1b[0m\x1b[38;2;84;166;187"
        "m⣿\x1b[0m\x1b[38;2;62;151;167m⣿\x1b[0m\x1b[38;2;92;1"
        "67;188m⣿\x1b[0m\x1b[38;2;71;159;179m⣿\x1b[0m\x1b[38;"
        "2;95;163;184m⣿\x1b[0m\x1b[38;2;77;152;173m⣿\x1b[0"
        "m\x1b[38;2;76;154;174m⣿\x1b[0m\x1b[38;2;88;159;18"
        "1m⣿\x1b[0m\x1b[38;2;77;152;173m⣿\x1b[0m\x1b[38;2;55;"
        "142;161m⣿\x1b[0m\x1b[38;2;69;147;169m⣿\x1b[0m\x1b[38"
        ";2;58;143;164m⣿\x1b[0m\x1b[38;2;69;147;170m⣿\x1b["
        "0m\x1b[38;2;67;144;164m⣿\x1b[0m\x1b[38;2;64;145;1"
        "64m⣿\x1b[0m\n  \x1b[38;2;10;147;179m⣿\x1b[0m\x1b[38;2"
        ";14;148;177m⣿\x1b[0m\x1b[38;2;5;144;173m⣿\x1b[0m\x1b"
        "[38;2;16;151;181m⣿\x1b[0m\x1b[38;2;14;149;181m"
        "⣿\x1b[0m\x1b[38;2;11;146;178m⣿\x1b[0m\x1b[38;2;14;15"
        "5;182m⣿\x1b[0m\x1b[38;2;15;156;183m⣿\x1b[0m\x1b[38;2"
        ";21;160;189m⣿\x1b[0m\x1b[38;2;21;160;189m⣿\x1b[0m"
        "\x1b[38;2;12;152;177m⣿\x1b[0m\x1b[38;2;24;168;192"
        "m⣿\x1b[0m\x1b[38;2;21;165;189m⣿\x1b[0m\x1b[38;2;23;1"
        "63;188m⣿\x1b[0m\x1b[38;2;34;175;195m⣿\x1b[0m\x1b[38;"
        "2;24;169;188m⣿\x1b[0m\x1b[38;2;55;175;199m⣿\x1b[0"
        "m\x1b[38;2;52;164;186m⣿\x1b[0m\x1b[38;2;53;170;19"
        "0m⣿\x1b[0m\x1b[38;2;72;179;199m⣿\x1b[0m\x1b[38;2;80;"
        "179;200m⣿\x1b[0m\x1b[38;2;67;167;190m⣿\x1b[0m\x1b[38"
        ";2;87;183;199m⡿\x1b[0m\x1b[38;2;162;154;143m⠿\x1b"
        "[0m\x1b[38;2;47;67;56m⢫\x1b[0m\x1b[38;2;35;55;44m"
        "⣁\x1b[0m\x1b[38;2;80;85;63m⠑\x1b[0m\x1b[38;2;87;71;3"
        "7m⢶\x1b[0m\x1b[38;2;59;54;34m⣺\x1b[0m\x1b[38;2;58;79"
        ";74m⣫\x1b[0m\x1b[38;2;86;72;37m⣽\x1b[0m\x1b[38;2;123"
        ";125;104m⢿\x1b[0m\x1b[38;2;15;162;178m⣿\x1b[0m\x1b[3"
        "8;2;37;186;206m⣿\x1b[0m\x1b[38;2;37;173;197m⣿\x1b"
        "[0m\x1b[38;2;26;171;198m⣿\x1b[0m\x1b[38;2;27;171;"
        "198m⣿\x1b[0m\x1b[38;2;32;178;203m⣿\x1b[0m\x1b[38;2;2"
        "6;166;189m⣿\x1b[0m\x1b[38;2;37;173;189m⣿\x1b[0m\x1b["
        "38;2;66;161;181m⣿\x1b[0m\x1b[38;2;83;180;197m⣿"
        "\x1b[0m\x1b[38;2;107;175;198m⣿\x1b[0m\x1b[38;2;113;1"
        "88;209m⣿\x1b[0m\x1b[38;2;106;181;202m⣿\x1b[0m\x1b[38"
        ";2;98;173;196m⣿\x1b[0m\x1b[38;2;110;185;208m⣿\x1b"
        "[0m\x1b[38;2;107;178;196m⣿\x1b[0m\x1b[38;2;106;17"
        "7;195m⣿\x1b[0m\x1b[38;2;95;174;191m⣿\x1b[0m\x1b[38;2"
        ";98;177;194m⣿\x1b[0m\x1b[38;2;92;173;192m⣿\x1b[0m"
        "\x1b[38;2;85;170;191m⣿\x1b[0m\x1b[38;2;70;157;177"
        "m⣿\x1b[0m\x1b[38;2;70;173;188m⣿\x1b[0m\x1b[38;2;68;1"
        "63;185m⣿\x1b[0m\x1b[38;2;53;157;182m⣿\x1b[0m\x1b[38;"
        "2;47;155;181m⣿\x1b[0m\x1b[38;2;33;147;173m⣿\x1b[0"
        "m\x1b[38;2;26;152;174m⣿\x1b[0m\x1b[38;2;38;164;18"
        "7m⣿\x1b[0m\x1b[38;2;21;143;167m⣿\x1b[0m\x1b[38;2;8;1"
        "34;159m⣿\x1b[0m\x1b[38;2;25;144;168m⣿\x1b[0m\x1b[38;"
        "2;25;146;165m⣿\x1b[0m\x1b[38;2;9;138;159m⣿\x1b[0m"
        "\x1b[38;2;11;143;158m⣿\x1b[0m\x1b[38;2;44;156;180"
        "m⣿\x1b[0m\x1b[38;2;20;122;144m⣿\x1b[0m\x1b[38;2;1;11"
        "0;130m⣿\x1b[0m\x1b[38;2;37;141;166m⣿\x1b[0m\x1b[38;2"
        ";42;137;165m⣿\x1b[0m\x1b[38;2;19;125;147m⣿\x1b[0m"
        "\x1b[38;2;18;119;139m⣿\x1b[0m\x1b[38;2;39;141;166"
        "m⣿\x1b[0m\x1b[38;2;29;131;156m⣿\x1b[0m\x1b[38;2;7;10"
        "7;130m⣿\x1b[0m\x1b[38;2;2;107;128m⣿\x1b[0m\n  \x1b[38"
        ";2;17;135;165m⣿\x1b[0m\x1b[38;2;12;133;162m⣿\x1b["
        "0m\x1b[38;2;18;147;178m⣿\x1b[0m\x1b[38;2;17;146;1"
        "77m⣿\x1b[0m\x1b[38;2;14;143;174m⣿\x1b[0m\x1b[38;2;0;"
        "121;152m⣿\x1b[0m\x1b[38;2;4;133;164m⣿\x1b[0m\x1b[38;"
        "2;5;134;165m⣿\x1b[0m\x1b[38;2;9;139;173m⣿\x1b[0m\x1b"
        "[38;2;10;149;180m⣿\x1b[0m\x1b[38;2;6;141;173m⣿"
        "\x1b[0m\x1b[38;2;4;139;171m⣿\x1b[0m\x1b[38;2;10;141;"
        "171m⣿\x1b[0m\x1b[38;2;2;133;163m⣿\x1b[0m\x1b[38;2;6;"
        "147;177m⣿\x1b[0m\x1b[38;2;3;146;176m⣿\x1b[0m\x1b[38;"
        "2;13;164;181m⣿\x1b[0m\x1b[38;2;0;158;206m⣿\x1b[0m"
        "\x1b[38;2;14;166;151m⣿\x1b[0m\x1b[38;2;98;45;51m⡿"
        "\x1b[0m\x1b[38;2;163;153;141m⠯\x1b[0m\x1b[38;2;196;1"
        "94;171m⣵\x1b[0m\x1b[38;2;167;171;148m⠶\x1b[0m\x1b[38"
        ";2;155;157;154m⠿\x1b[0m\x1b[38;2;127;132;110m⢧"
        "\x1b[0m\x1b[38;2;41;50;45m⠎\x1b[0m\x1b[38;2;62;69;77"
        "m⠀\x1b[0m\x1b[38;2;17;21;30m⠀\x1b[0m\x1b[38;2;36;40;"
        "49m⠀\x1b[0m\x1b[38;2;47;49;46m⠛\x1b[0m\x1b[38;2;41;4"
        "6;49m⢟\x1b[0m\x1b[38;2;106;105;87m⣿\x1b[0m\x1b[38;2;"
        "94;93;75m⣿\x1b[0m\x1b[38;2;23;27;26m⣿\x1b[0m\x1b[38;"
        "2;46;58;36m⡿\x1b[0m\x1b[38;2;108;168;158m⣿\x1b[0m"
        "\x1b[38;2;7;168;197m⣿\x1b[0m\x1b[38;2;15;165;198m"
        "⣿\x1b[0m\x1b[38;2;19;163;189m⣿\x1b[0m\x1b[38;2;14;15"
        "4;177m⣿\x1b[0m\x1b[38;2;42;174;195m⣿\x1b[0m\x1b[38;2"
        ";47;166;186m⣿\x1b[0m\x1b[38;2;70;179;199m⣿\x1b[0m"
        "\x1b[38;2;73;169;193m⣿\x1b[0m\x1b[38;2;81;181;204"
        "m⣿\x1b[0m\x1b[38;2;76;179;198m⣿\x1b[0m\x1b[38;2;62;1"
        "72;189m⣿\x1b[0m\x1b[38;2;74;179;201m⣿\x1b[0m\x1b[38;"
        "2;69;174;196m⣿\x1b[0m\x1b[38;2;60;170;187m⣿\x1b[0"
        "m\x1b[38;2;48;160;180m⣿\x1b[0m\x1b[38;2;39;159;18"
        "4m⣿\x1b[0m\x1b[38;2;33;153;178m⣿\x1b[0m\x1b[38;2;34;"
        "160;183m⣿\x1b[0m\x1b[38;2;23;149;172m⣿\x1b[0m\x1b[38"
        ";2;10;142;163m⣿\x1b[0m\x1b[38;2;7;139;160m⣿\x1b[0"
        "m\x1b[38;2;4;134;156m⣿\x1b[0m\x1b[38;2;0;126;149m"
        "⣿\x1b[0m\x1b[38;2;22;140;166m⣿\x1b[0m\x1b[38;2;17;13"
        "5;161m⣿\x1b[0m\x1b[38;2;7;125;151m⣿\x1b[0m\x1b[38;2;"
        "0;122;140m⣿\x1b[0m\x1b[38;2;6;125;145m⣿\x1b[0m\x1b[3"
        "8;2;8;130;153m⣿\x1b[0m\x1b[38;2;10;132;155m⣿\x1b["
        "0m\x1b[38;2;5;123;149m⣿\x1b[0m\x1b[38;2;15;125;15"
        "2m⣿\x1b[0m\x1b[38;2;8;116;142m⣿\x1b[0m\x1b[38;2;5;11"
        "3;139m⣿\x1b[0m\x1b[38;2;5;111;135m⣿\x1b[0m\x1b[38;2;"
        "11;117;141m⣿\x1b[0m\x1b[38;2;0;110;133m⣿\x1b[0m\x1b["
        "38;2;18;120;145m⣿\x1b[0m\x1b[38;2;20;118;143m⣿"
        "\x1b[0m\x1b[38;2;14;119;141m⣿\x1b[0m\x1b[38;2;17;123"
        ";145m⣿\x1b[0m\x1b[38;2;0;98;121m⣿\x1b[0m\n  \x1b[38;2"
        ";12;127;156m⣿\x1b[0m\x1b[38;2;8;129;156m⣿\x1b[0m\x1b"
        "[38;2;13;128;157m⣿\x1b[0m\x1b[38;2;0;110;139m⣿"
        "\x1b[0m\x1b[38;2;6;125;159m⣿\x1b[0m\x1b[38;2;0;111;1"
        "45m⣿\x1b[0m\x1b[38;2;0;121;152m⣿\x1b[0m\x1b[38;2;19;"
        "114;142m⡿\x1b[0m\x1b[38;2;210;209;214m⠿\x1b[0m\x1b[3"
        "8;2;49;126;146m⢿\x1b[0m\x1b[38;2;7;136;168m⣿\x1b["
        "0m\x1b[38;2;11;140;172m⣿\x1b[0m\x1b[38;2;19;140;1"
        "71m⣿\x1b[0m\x1b[38;2;3;130;162m⣿\x1b[0m\x1b[38;2;26;"
        "129;170m⣿\x1b[0m\x1b[38;2;4;146;160m⣿\x1b[0m\x1b[38;"
        "2;85;126;108m⣿\x1b[0m\x1b[38;2;140;131;116m⣡\x1b["
        "0m\x1b[38;2;157;154;139m⡿\x1b[0m\x1b[38;2;78;78;5"
        "2m⡗\x1b[0m\x1b[38;2;65;73;75m⠊\x1b[0m\x1b[38;2;30;32"
        ";53m⠀\x1b[0m\x1b[38;2;38;47;46m⠀\x1b[0m\x1b[38;2;21;"
        "30;37m⠀\x1b[0m\x1b[38;2;30;31;35m⡀\x1b[0m\x1b[38;2;4"
        "4;48;60m⠀\x1b[0m\x1b[38;2;31;36;39m⠄\x1b[0m\x1b[38;2"
        ";35;42;50m⠀\x1b[0m\x1b[38;2;34;43;42m⠂\x1b[0m\x1b[38"
        ";2;44;51;61m⠘\x1b[0m\x1b[38;2;113;116;95m⡽\x1b[0m"
        "\x1b[38;2;117;114;95m⣿\x1b[0m\x1b[38;2;128;125;10"
        "6m⣿\x1b[0m\x1b[38;2;122;120;99m⣷\x1b[0m\x1b[38;2;143"
        ";141;120m⣤\x1b[0m\x1b[38;2;114;107;88m⣾\x1b[0m\x1b[3"
        "8;2;110;103;84m⣿\x1b[0m\x1b[38;2;81;107;106m⣿\x1b"
        "[0m\x1b[38;2;0;148;182m⣿\x1b[0m\x1b[38;2;12;143;1"
        "61m⣿\x1b[0m\x1b[38;2;16;153;187m⣿\x1b[0m\x1b[38;2;23"
        ";148;178m⣿\x1b[0m\x1b[38;2;30;149;173m⣿\x1b[0m\x1b[3"
        "8;2;20;139;163m⣿\x1b[0m\x1b[38;2;28;147;171m⣿\x1b"
        "[0m\x1b[38;2;12;149;167m⣿\x1b[0m\x1b[38;2;18;134;"
        "159m⣿\x1b[0m\x1b[38;2;22;143;172m⣿\x1b[0m\x1b[38;2;3"
        "1;142;170m⣿\x1b[0m\x1b[38;2;37;157;182m⣿\x1b[0m\x1b["
        "38;2;23;155;176m⣿\x1b[0m\x1b[38;2;13;138;170m⣿"
        "\x1b[0m\x1b[38;2;19;153;182m⣿\x1b[0m\x1b[38;2;17;126"
        ";155m⣿\x1b[0m\x1b[38;2;22;136;173m⣿\x1b[0m\x1b[38;2;"
        "9;141;162m⣿\x1b[0m\x1b[38;2;14;140;163m⣿\x1b[0m\x1b["
        "38;2;16;126;153m⣿\x1b[0m\x1b[38;2;8;118;145m⣿\x1b"
        "[0m\x1b[38;2;8;116;144m⣿\x1b[0m\x1b[38;2;9;118;14"
        "1m⣿\x1b[0m\x1b[38;2;15;119;144m⣿\x1b[0m\x1b[38;2;7;1"
        "13;139m⣿\x1b[0m\x1b[38;2;4;110;136m⣿\x1b[0m\x1b[38;2"
        ";4;102;129m⣿\x1b[0m\x1b[38;2;9;103;128m⣿\x1b[0m\x1b["
        "38;2;11;97;122m⣿\x1b[0m\x1b[38;2;18;106;130m⣿\x1b"
        "[0m\x1b[38;2;4;105;123m⣿\x1b[0m\x1b[38;2;6;103;12"
        "2m⣿\x1b[0m\x1b[38;2;1;102;122m⣿\x1b[0m\x1b[38;2;2;97"
        ";119m⣿\x1b[0m\x1b[38;2;4;95;116m⣿\x1b[0m\x1b[38;2;6;"
        "97;118m⣿\x1b[0m\x1b[38;2;3;103;118m⣿\x1b[0m\x1b[38;2"
        ";1;101;116m⣿\x1b[0m\x1b[38;2;10;101;120m⣿\x1b[0m\x1b"
        "[38;2;8;99;118m⣿\x1b[0m\n  \x1b[38;2;8;117;150m"
        "⣿\x1b[0m\x1b[38;2;16;125;158m⣿\x1b[0m\x1b[38;2;29;14"
        "0;168m⣿\x1b[0m\x1b[38;2;21;132;160m⣿\x1b[0m\x1b[38;2"
        ";12;123;151m⣿\x1b[0m\x1b[38;2;5;116;144m⣿\x1b[0m\x1b"
        "[38;2;12;120;149m⣿\x1b[0m\x1b[38;2;13;121;150m"
        "⣿\x1b[0m\x1b[38;2;13;127;163m⣿\x1b[0m\x1b[38;2;0;98;"
        "125m⣿\x1b[0m\x1b[38;2;13;138;160m⣿\x1b[0m\x1b[38;2;1"
        "8;119;149m⣿\x1b[0m\x1b[38;2;16;126;153m⣿\x1b[0m\x1b["
        "38;2;196;229;234m⣿\x1b[0m\x1b[38;2;213;211;214"
        "m⣿\x1b[0m\x1b[38;2;118;121;112m⣿\x1b[0m\x1b[38;2;172"
        ";163;132m⣿\x1b[0m\x1b[38;2;91;83;60m⣿\x1b[0m\x1b[38;"
        "2;43;55;41m⣣\x1b[0m\x1b[38;2;56;53;72m⡔\x1b[0m\x1b[3"
        "8;2;65;67;82m⠐\x1b[0m\x1b[38;2;186;174;150m⡌\x1b["
        "0m\x1b[38;2;104;117;91m⠦\x1b[0m\x1b[38;2;171;193;"
        "147m⢸\x1b[0m\x1b[38;2;115;117;93m⣿\x1b[0m\x1b[38;2;9"
        "6;92;63m⣧\x1b[0m\x1b[38;2;31;39;28m⣀\x1b[0m\x1b[38;2"
        ";85;87;48m⣤\x1b[0m\x1b[38;2;77;78;44m⣴\x1b[0m\x1b[38"
        ";2;98;102;77m⣷\x1b[0m\x1b[38;2;99;112;84m⣿\x1b[0m"
        "\x1b[38;2;156;159;130m⣿\x1b[0m\x1b[38;2;146;148;1"
        "24m⣿\x1b[0m\x1b[38;2;117;116;86m⣿\x1b[0m\x1b[38;2;10"
        "9;109;83m⡿\x1b[0m\x1b[38;2;158;155;140m⠿\x1b[0m\x1b["
        "38;2;132;131;113m⠿\x1b[0m\x1b[38;2;154;151;134"
        "m⠿\x1b[0m\x1b[38;2;125;118;89m⢿\x1b[0m\x1b[38;2;40;5"
        "1;37m⠿\x1b[0m\x1b[38;2;132;152;140m⣿\x1b[0m\x1b[38;2"
        ";39;141;155m⣿\x1b[0m\x1b[38;2;13;133;157m⣿\x1b[0m"
        "\x1b[38;2;0;131;146m⣿\x1b[0m\x1b[38;2;22;146;172m"
        "⣿\x1b[0m\x1b[38;2;30;142;166m⣿\x1b[0m\x1b[38;2;30;12"
        "6;150m⡿\x1b[0m\x1b[38;2;35;40;46m⢛\x1b[0m\x1b[38;2;5"
        "9;62;51m⠏\x1b[0m\x1b[38;2;154;155;111m⣽\x1b[0m\x1b[3"
        "8;2;144;128;92m⣭\x1b[0m\x1b[38;2;115;115;77m⣿\x1b"
        "[0m\x1b[38;2;110;109;79m⣿\x1b[0m\x1b[38;2;125;118"
        ";99m⣝\x1b[0m\x1b[38;2;52;91;98m⣿\x1b[0m\x1b[38;2;2;9"
        "1;123m⣿\x1b[0m\x1b[38;2;26;102;136m⣿\x1b[0m\x1b[38;2"
        ";17;109;130m⣿\x1b[0m\x1b[38;2;14;109;129m⣿\x1b[0m"
        "\x1b[38;2;6;104;129m⣿\x1b[0m\x1b[38;2;12;110;135m"
        "⣿\x1b[0m\x1b[38;2;2;100;125m⣿\x1b[0m\x1b[38;2;2;100;"
        "125m⣿\x1b[0m\x1b[38;2;11;109;134m⣿\x1b[0m\x1b[38;2;1"
        "1;110;129m⣿\x1b[0m\x1b[38;2;15;107;128m⡿\x1b[0m\x1b["
        "38;2;12;100;120m⡿\x1b[0m\x1b[38;2;9;97;117m⣿\x1b["
        "0m\x1b[38;2;5;86;107m⡿\x1b[0m\x1b[38;2;3;84;101m⢟"
        "\x1b[0m\x1b[38;2;17;92;111m⡐\x1b[0m\x1b[38;2;6;81;10"
        "0m⠍\x1b[0m\x1b[38;2;9;86;106m⠬\x1b[0m\x1b[38;2;20;87"
        ";104m⠈\x1b[0m\x1b[38;2;19;82;97m⠝\x1b[0m\x1b[38;2;4;"
        "63;79m⠛\x1b[0m\x1b[38;2;5;58;74m⠛\x1b[0m\x1b[38;2;13"
        ";77;89m⠑\x1b[0m\n  \x1b[38;2;17;104;134m⡯\x1b[0m\x1b["
        "38;2;15;102;132m⣽\x1b[0m\x1b[38;2;3;94;125m⣟\x1b["
        "0m\x1b[38;2;20;115;145m⣿\x1b[0m\x1b[38;2;24;122;1"
        "47m⣿\x1b[0m\x1b[38;2;9;107;132m⡿\x1b[0m\x1b[38;2;18;"
        "104;129m⠿\x1b[0m\x1b[38;2;16;102;127m⣿\x1b[0m\x1b[38"
        ";2;0;87;114m⣿\x1b[0m\x1b[38;2;18;117;148m⣷\x1b[0m"
        "\x1b[38;2;60;167;199m⣿\x1b[0m\x1b[38;2;165;190;18"
        "7m⣿\x1b[0m\x1b[38;2;98;90;79m⣿\x1b[0m\x1b[38;2;225;2"
        "08;178m⣿\x1b[0m\x1b[38;2;200;189;161m⣿\x1b[0m\x1b[38"
        ";2;164;165;123m⣿\x1b[0m\x1b[38;2;126;112;83m⣿\x1b"
        "[0m\x1b[38;2;128;119;64m⣷\x1b[0m\x1b[38;2;192;191"
        ";161m⣽\x1b[0m\x1b[38;2;39;50;56m⡋\x1b[0m\x1b[38;2;98"
        ";108;99m⠺\x1b[0m\x1b[38;2;117;129;115m⠌\x1b[0m\x1b[3"
        "8;2;54;61;54m⠂\x1b[0m\x1b[38;2;214;202;186m⠾\x1b["
        "0m\x1b[38;2;71;75;48m⣟\x1b[0m\x1b[38;2;137;136;90"
        "m⣿\x1b[0m\x1b[38;2;35;35;9m⣿\x1b[0m\x1b[38;2;135;144"
        ";115m⡿\x1b[0m\x1b[38;2;39;43;44m⠟\x1b[0m\x1b[38;2;38"
        ";48;49m⠋\x1b[0m\x1b[38;2;67;71;72m⠑\x1b[0m\x1b[38;2;"
        "94;100;98m⣐\x1b[0m\x1b[38;2;48;59;63m⢀\x1b[0m\x1b[38"
        ";2;47;68;71m⣄\x1b[0m\x1b[38;2;37;71;80m⣠\x1b[0m\x1b["
        "38;2;26;92;104m⣤\x1b[0m\x1b[38;2;7;110;125m⣶\x1b["
        "0m\x1b[38;2;0;110;129m⣶\x1b[0m\x1b[38;2;8;130;151"
        "m⣶\x1b[0m\x1b[38;2;44;166;187m⣿\x1b[0m\x1b[38;2;48;1"
        "70;191m⣿\x1b[0m\x1b[38;2;17;128;145m⣿\x1b[0m\x1b[38;"
        "2;41;140;161m⣿\x1b[0m\x1b[38;2;47;157;174m⣿\x1b[0"
        "m\x1b[38;2;170;178;167m⢿\x1b[0m\x1b[38;2;66;67;51"
        "m⣯\x1b[0m\x1b[38;2;47;51;50m⣔\x1b[0m\x1b[38;2;133;13"
        "5;95m⣴\x1b[0m\x1b[38;2;123;122;76m⣴\x1b[0m\x1b[38;2;"
        "141;141;107m⣾\x1b[0m\x1b[38;2;157;154;147m⡟\x1b[0"
        "m\x1b[38;2;128;127;109m⣫\x1b[0m\x1b[38;2;174;168;"
        "120m⣷\x1b[0m\x1b[38;2;202;186;160m⣿\x1b[0m\x1b[38;2;"
        "189;174;143m⣿\x1b[0m\x1b[38;2;199;181;143m⣿\x1b[0"
        "m\x1b[38;2;0;103;137m⡿\x1b[0m\x1b[38;2;9;97;119m⣿"
        "\x1b[0m\x1b[38;2;4;82;104m⡿\x1b[0m\x1b[38;2;14;94;11"
        "7m⣿\x1b[0m\x1b[38;2;15;93;115m⣷\x1b[0m\x1b[38;2;15;9"
        "3;115m⡛\x1b[0m\x1b[38;2;12;90;110m⢿\x1b[0m\x1b[38;2;"
        "10;88;108m⣻\x1b[0m\x1b[38;2;12;84;106m⣊\x1b[0m\x1b[3"
        "8;2;7;80;97m⠹\x1b[0m\x1b[38;2;15;93;106m⡧\x1b[0m\x1b"
        "[38;2;8;75;92m⠔\x1b[0m\x1b[38;2;6;77;97m⠂\x1b[0m\x1b"
        "[38;2;16;91;110m⠢\x1b[0m\x1b[38;2;11;74;91m⠂\x1b["
        "0m\x1b[38;2;9;72;89m⠀\x1b[0m\x1b[38;2;10;69;85m⠐\x1b"
        "[0m\x1b[38;2;10;69;85m⠀\x1b[0m\x1b[38;2;7;65;79m⠀"
        "\x1b[0m\x1b[38;2;9;68;82m⠀\x1b[0m\x1b[38;2;11;63;74m"
        "⠀\x1b[0m\x1b[38;2;11;57;70m⠀\x1b[0m\n  \x1b[38;2;9;75"
        ";99m⠚\x1b[0m\x1b[38;2;17;92;113m⢳\x1b[0m\x1b[38;2;0;"
        "80;105m⣍\x1b[0m\x1b[38;2;13;93;118m⡱\x1b[0m\x1b[38;2"
        ";27;108;135m⣫\x1b[0m\x1b[38;2;12;93;120m⠟\x1b[0m\x1b"
        "[38;2;20;97;123m⠽\x1b[0m\x1b[38;2;0;74;100m⣿\x1b["
        "0m\x1b[38;2;2;82;109m⣽\x1b[0m\x1b[38;2;5;97;120m⢿"
        "\x1b[0m\x1b[38;2;51;152;172m⣿\x1b[0m\x1b[38;2;152;15"
        "4;141m⣿\x1b[0m\x1b[38;2;134;133;112m⣯\x1b[0m\x1b[38;"
        "2;103;101;78m⣵\x1b[0m\x1b[38;2;166;160;136m⣿\x1b["
        "0m\x1b[38;2;182;183;149m⣿\x1b[0m\x1b[38;2;188;178"
        ";129m⣿\x1b[0m\x1b[38;2;173;165;82m⣿\x1b[0m\x1b[38;2;"
        "173;158;103m⣿\x1b[0m\x1b[38;2;173;156;102m⣿\x1b[0"
        "m\x1b[38;2;172;160;112m⣿\x1b[0m\x1b[38;2;143;132;"
        "86m⣶\x1b[0m\x1b[38;2;129;121;74m⣶\x1b[0m\x1b[38;2;21"
        "2;200;158m⣦\x1b[0m\x1b[38;2;50;59;54m⣁\x1b[0m\x1b[38"
        ";2;42;50;37m⡩\x1b[0m\x1b[38;2;48;58;60m⠄\x1b[0m\x1b["
        "38;2;49;57;59m⠀\x1b[0m\x1b[38;2;24;32;34m⠀\x1b[0m"
        "\x1b[38;2;31;42;46m⠂\x1b[0m\x1b[38;2;56;79;87m⢶\x1b["
        "0m\x1b[38;2;36;88;101m⣾\x1b[0m\x1b[38;2;34;103;11"
        "8m⣿\x1b[0m\x1b[38;2;30;111;130m⣿\x1b[0m\x1b[38;2;7;1"
        "30;145m⣿\x1b[0m\x1b[38;2;0;121;138m⣿\x1b[0m\x1b[38;2"
        ";3;129;151m⣿\x1b[0m\x1b[38;2;9;124;143m⣿\x1b[0m\x1b["
        "38;2;25;140;159m⣿\x1b[0m\x1b[38;2;37;154;172m⣿"
        "\x1b[0m\x1b[38;2;20;132;152m⣿\x1b[0m\x1b[38;2;19;140"
        ";161m⣿\x1b[0m\x1b[38;2;22;143;164m⣿\x1b[0m\x1b[38;2;"
        "24;136;158m⣿\x1b[0m\x1b[38;2;76;87;83m⢛\x1b[0m\x1b[3"
        "8;2;163;169;159m⣿\x1b[0m\x1b[38;2;199;200;192m"
        "⣿\x1b[0m\x1b[38;2;82;80;65m⡿\x1b[0m\x1b[38;2;138;142"
        ";109m⣿\x1b[0m\x1b[38;2;33;25;12m⡾\x1b[0m\x1b[38;2;13"
        "3;123;74m⡷\x1b[0m\x1b[38;2;162;159;114m⣿\x1b[0m\x1b["
        "38;2;116;119;90m⣿\x1b[0m\x1b[38;2;100;102;80m⡿"
        "\x1b[0m\x1b[38;2;192;168;132m⣯\x1b[0m\x1b[38;2;208;2"
        "21;230m⣵\x1b[0m\x1b[38;2;34;138;151m⣿\x1b[0m\x1b[38;"
        "2;3;75;90m⣗\x1b[0m\x1b[38;2;4;66;89m⠹\x1b[0m\x1b[38;"
        "2;16;88;110m⢫\x1b[0m\x1b[38;2;9;84;103m⠾\x1b[0m\x1b["
        "38;2;28;94;116m⠜\x1b[0m\x1b[38;2;16;74;96m⠙\x1b[0"
        "m\x1b[38;2;7;72;92m⢑\x1b[0m\x1b[38;2;10;77;93m⠆\x1b["
        "0m\x1b[38;2;2;65;82m⠁\x1b[0m\x1b[38;2;9;75;91m⠚\x1b["
        "0m\x1b[38;2;8;74;90m⠔\x1b[0m\x1b[38;2;7;70;87m⠀\x1b["
        "0m\x1b[38;2;15;74;92m⠀\x1b[0m\x1b[38;2;21;80;96m⡂"
        "\x1b[0m\x1b[38;2;16;75;91m⠀\x1b[0m\x1b[38;2;8;67;81m"
        "⠄\x1b[0m\x1b[38;2;8;67;81m⠀\x1b[0m\x1b[38;2;14;67;83"
        "m⠀\x1b[0m\x1b[38;2;7;60;76m⠀\x1b[0m\x1b[38;2;11;69;8"
        "3m⠀\x1b[0m\x1b[38;2;10;59;76m⠀\x1b[0m\n  \x1b[38;2;15"
        ";79;104m⠡\x1b[0m\x1b[38;2;12;87;108m⠠\x1b[0m\x1b[38;"
        "2;7;71;96m⡀\x1b[0m\x1b[38;2;0;55;80m⠤\x1b[0m\x1b[38;"
        "2;9;73;98m⡄\x1b[0m\x1b[38;2;0;57;82m⠊\x1b[0m\x1b[38;"
        "2;7;73;97m⠆\x1b[0m\x1b[38;2;6;77;99m⣂\x1b[0m\x1b[38;"
        "2;12;83;105m⢺\x1b[0m\x1b[38;2;17;92;113m⣩\x1b[0m\x1b"
        "[38;2;22;109;129m⡟\x1b[0m\x1b[38;2;12;97;118m⢿"
        "\x1b[0m\x1b[38;2;56;125;140m⣿\x1b[0m\x1b[38;2;142;13"
        "9;104m⢿\x1b[0m\x1b[38;2;132;126;92m⣷\x1b[0m\x1b[38;2"
        ";133;134;100m⣿\x1b[0m\x1b[38;2;206;188;152m⡿\x1b["
        "0m\x1b[38;2;139;133;99m⣿\x1b[0m\x1b[38;2;94;87;58"
        "m⣿\x1b[0m\x1b[38;2;139;128;100m⣿\x1b[0m\x1b[38;2;120"
        ";109;77m⣿\x1b[0m\x1b[38;2;219;206;174m⣿\x1b[0m\x1b[3"
        "8;2;72;60;46m⣿\x1b[0m\x1b[38;2;121;115;89m⣏\x1b[0"
        "m\x1b[38;2;138;131;103m⣿\x1b[0m\x1b[38;2;75;77;63"
        "m⣢\x1b[0m\x1b[38;2;133;135;121m⢭\x1b[0m\x1b[38;2;88;"
        "97;80m⢤\x1b[0m\x1b[38;2;18;20;15m⣀\x1b[0m\x1b[38;2;5"
        "2;60;63m⣀\x1b[0m\x1b[38;2;34;46;46m⣊\x1b[0m\x1b[38;2"
        ";16;62;75m⡿\x1b[0m\x1b[38;2;0;102;113m⣿\x1b[0m\x1b[3"
        "8;2;6;98;109m⣿\x1b[0m\x1b[38;2;6;103;122m⢿\x1b[0m"
        "\x1b[38;2;0;109;129m⣿\x1b[0m\x1b[38;2;3;115;135m⣿"
        "\x1b[0m\x1b[38;2;4;123;143m⣿\x1b[0m\x1b[38;2;10;133;"
        "148m⣿\x1b[0m\x1b[38;2;3;123;139m⣿\x1b[0m\x1b[38;2;8;"
        "120;142m⣿\x1b[0m\x1b[38;2;4;117;135m⣿\x1b[0m\x1b[38;"
        "2;47;114;122m⣿\x1b[0m\x1b[38;2;183;189;179m⣿\x1b["
        "0m\x1b[38;2;185;188;169m⡿\x1b[0m\x1b[38;2;162;155"
        ";126m⠿\x1b[0m\x1b[38;2;23;27;30m⡋\x1b[0m\x1b[38;2;47"
        ";46;41m⠱\x1b[0m\x1b[38;2;167;159;138m⡟\x1b[0m\x1b[38"
        ";2;147;181;191m⢥\x1b[0m\x1b[38;2;13;26;32m⠀\x1b[0"
        "m\x1b[38;2;45;33;35m⣊\x1b[0m\x1b[38;2;18;46;47m⣉\x1b"
        "[0m\x1b[38;2;132;162;172m⣤\x1b[0m\x1b[38;2;75;137"
        ";160m⣤\x1b[0m\x1b[38;2;18;77;93m⠉\x1b[0m\x1b[38;2;12"
        ";71;87m⠉\x1b[0m\x1b[38;2;20;83;100m⠂\x1b[0m\x1b[38;2"
        ";29;91;112m⠈\x1b[0m\x1b[38;2;24;85;106m⢐\x1b[0m\x1b["
        "38;2;15;71;94m⠘\x1b[0m\x1b[38;2;18;75;94m⠩\x1b[0m"
        "\x1b[38;2;8;61;77m⠉\x1b[0m\x1b[38;2;11;64;80m⠀\x1b[0"
        "m\x1b[38;2;13;69;84m⠀\x1b[0m\x1b[38;2;4;60;75m⠁\x1b["
        "0m\x1b[38;2;3;56;70m⠀\x1b[0m\x1b[38;2;9;62;76m⠀\x1b["
        "0m\x1b[38;2;6;59;73m⠀\x1b[0m\x1b[38;2;10;63;77m⠈\x1b"
        "[0m\x1b[38;2;16;68;82m⠀\x1b[0m\x1b[38;2;14;55;73m"
        "⠀\x1b[0m\x1b[38;2;9;57;69m⠀\x1b[0m\x1b[38;2;12;60;72"
        "m⠀\x1b[0m\x1b[38;2;14;56;70m⠀\x1b[0m\x1b[38;2;16;53;"
        "69m⠀\x1b[0m\x1b[38;2;19;59;69m⠀\x1b[0m\x1b[38;2;14;5"
        "4;64m⠀\x1b[0m\n  \x1b[38;2;7;63;80m⠐\x1b[0m\x1b[38;2;"
        "10;58;78m⠀\x1b[0m\x1b[38;2;10;57;77m⠉\x1b[0m\x1b[38;"
        "2;13;60;80m⠀\x1b[0m\x1b[38;2;2;55;73m⠀\x1b[0m\x1b[38"
        ";2;1;54;72m⠀\x1b[0m\x1b[38;2;8;63;84m⠀\x1b[0m\x1b[38"
        ";2;13;71;91m⠀\x1b[0m\x1b[38;2;0;59;76m⠀\x1b[0m\x1b[3"
        "8;2;12;71;89m⠀\x1b[0m\x1b[38;2;7;74;90m⠈\x1b[0m\x1b["
        "38;2;8;74;86m⠻\x1b[0m\x1b[38;2;0;63;75m⣹\x1b[0m\x1b["
        "38;2;86;93;85m⢎\x1b[0m\x1b[38;2;199;189;162m⣿\x1b"
        "[0m\x1b[38;2;192;177;138m⣿\x1b[0m\x1b[38;2;80;74;"
        "50m⡯\x1b[0m\x1b[38;2;148;142;108m⢽\x1b[0m\x1b[38;2;1"
        "91;180;152m⣿\x1b[0m\x1b[38;2;141;128;96m⡿\x1b[0m\x1b"
        "[38;2;128;118;83m⣽\x1b[0m\x1b[38;2;69;64;32m⣿\x1b"
        "[0m\x1b[38;2;130;134;99m⣿\x1b[0m\x1b[38;2;121;122"
        ";108m⣿\x1b[0m\x1b[38;2;153;146;118m⣿\x1b[0m\x1b[38;2"
        ";122;110;72m⢿\x1b[0m\x1b[38;2;151;134;106m⢯\x1b[0"
        "m\x1b[38;2;99;79;55m⣿\x1b[0m\x1b[38;2;192;169;135"
        "m⣿\x1b[0m\x1b[38;2;204;195;166m⣿\x1b[0m\x1b[38;2;188"
        ";179;150m⣿\x1b[0m\x1b[38;2;156;149;130m⡟\x1b[0m\x1b["
        "38;2;183;170;136m⣷\x1b[0m\x1b[38;2;185;180;150"
        "m⣶\x1b[0m\x1b[38;2;167;158;129m⣾\x1b[0m\x1b[38;2;109"
        ";101;78m⣿\x1b[0m\x1b[38;2;223;211;187m⣿\x1b[0m\x1b[3"
        "8;2;216;206;197m⣿\x1b[0m\x1b[38;2;196;186;161m"
        "⡿\x1b[0m\x1b[38;2;52;39;33m⢟\x1b[0m\x1b[38;2;183;186"
        ";167m⣹\x1b[0m\x1b[38;2;89;83;69m⣭\x1b[0m\x1b[38;2;21"
        "8;242;246m⣭\x1b[0m\x1b[38;2;150;185;207m⣶\x1b[0m\x1b"
        "[38;2;5;127;130m⠾\x1b[0m\x1b[38;2;0;84;90m⢿\x1b[0"
        "m\x1b[38;2;167;200;215m⣤\x1b[0m\x1b[38;2;103;104;"
        "106m⣶\x1b[0m\x1b[38;2;190;191;195m⣧\x1b[0m\x1b[38;2;"
        "216;231;238m⣿\x1b[0m\x1b[38;2;92;170;182m⣷\x1b[0m"
        "\x1b[38;2;16;90;101m⠖\x1b[0m\x1b[38;2;13;35;48m⠉\x1b"
        "[0m\x1b[38;2;13;52;67m⠉\x1b[0m\x1b[38;2;9;52;69m⠀"
        "\x1b[0m\x1b[38;2;2;48;64m⠀\x1b[0m\x1b[38;2;3;52;67m⠀"
        "\x1b[0m\x1b[38;2;7;54;72m⡀\x1b[0m\x1b[38;2;11;54;73m"
        "⠂\x1b[0m\x1b[38;2;8;57;74m⠀\x1b[0m\x1b[38;2;22;65;84"
        "m⠀\x1b[0m\x1b[38;2;8;55;73m⠀\x1b[0m\x1b[38;2;8;57;74"
        "m⠀\x1b[0m\x1b[38;2;13;62;79m⠀\x1b[0m\x1b[38;2;17;66;"
        "81m⠀\x1b[0m\x1b[38;2;16;62;78m⠀\x1b[0m\x1b[38;2;6;52"
        ";68m⠀\x1b[0m\x1b[38;2;12;53;71m⠀\x1b[0m\x1b[38;2;11;"
        "50;67m⠀\x1b[0m\x1b[38;2;17;56;73m⠀\x1b[0m\x1b[38;2;1"
        "9;56;74m⠀\x1b[0m\x1b[38;2;14;51;69m⠀\x1b[0m\x1b[38;2"
        ";13;49;65m⠀\x1b[0m\x1b[38;2;15;51;67m⠀\x1b[0m\x1b[38"
        ";2;13;49;61m⠀\x1b[0m\x1b[38;2;9;45;57m⠀\x1b[0m\x1b[3"
        "8;2;15;47;58m⠀\x1b[0m\x1b[38;2;13;45;56m⠀\x1b[0m\n"
        "  \x1b[38;2;5;48;64m⠀\x1b[0m\x1b[38;2;9;48;65m⠀\x1b["
        "0m\x1b[38;2;11;47;63m⠀\x1b[0m\x1b[38;2;10;52;66m⠀"
        "\x1b[0m\x1b[38;2;11;48;66m⠀\x1b[0m\x1b[38;2;8;45;63m"
        "⠀\x1b[0m\x1b[38;2;7;50;66m⠀\x1b[0m\x1b[38;2;9;56;74m"
        "⠀\x1b[0m\x1b[38;2;15;64;81m⠀\x1b[0m\x1b[38;2;7;60;76"
        "m⠀\x1b[0m\x1b[38;2;9;61;75m⢀\x1b[0m\x1b[38;2;10;94;1"
        "18m⣺\x1b[0m\x1b[38;2;163;172;153m⣽\x1b[0m\x1b[38;2;1"
        "93;181;155m⡿\x1b[0m\x1b[38;2;125;109;73m⣻\x1b[0m\x1b"
        "[38;2;147;125;75m⣿\x1b[0m\x1b[38;2;137;118;78m"
        "⡷\x1b[0m\x1b[38;2;124;122;110m⠳\x1b[0m\x1b[38;2;82;6"
        "9;52m⣟\x1b[0m\x1b[38;2;53;48;29m⡉\x1b[0m\x1b[38;2;17"
        "3;161;135m⣿\x1b[0m\x1b[38;2;57;51;29m⡿\x1b[0m\x1b[38"
        ";2;133;113;78m⣿\x1b[0m\x1b[38;2;130;116;71m⣿\x1b["
        "0m\x1b[38;2;117;102;61m⣿\x1b[0m\x1b[38;2;28;26;31"
        "m⡆\x1b[0m\x1b[38;2;36;32;21m⢻\x1b[0m\x1b[38;2;133;12"
        "3;88m⣿\x1b[0m\x1b[38;2;193;182;160m⣿\x1b[0m\x1b[38;2"
        ";187;178;149m⢿\x1b[0m\x1b[38;2;85;80;50m⣿\x1b[0m\x1b"
        "[38;2;34;33;31m⢇\x1b[0m\x1b[38;2;58;58;60m⡚\x1b[0"
        "m\x1b[38;2;62;64;61m⣛\x1b[0m\x1b[38;2;37;46;41m⡛\x1b"
        "[0m\x1b[38;2;84;122;125m⢣\x1b[0m\x1b[38;2;160;179"
        ";183m⠿\x1b[0m\x1b[38;2;45;57;53m⢯\x1b[0m\x1b[38;2;12"
        "7;146;161m⠾\x1b[0m\x1b[38;2;165;217;230m⣿\x1b[0m\x1b"
        "[38;2;5;77;89m⣟\x1b[0m\x1b[38;2;6;63;82m⡛\x1b[0m\x1b"
        "[38;2;6;63;82m⠉\x1b[0m\x1b[38;2;12;78;94m⡠\x1b[0m"
        "\x1b[38;2;18;83;103m⢠\x1b[0m\x1b[38;2;4;65;83m⠀\x1b["
        "0m\x1b[38;2;6;58;72m⠀\x1b[0m\x1b[38;2;4;57;75m⠈\x1b["
        "0m\x1b[38;2;9;63;75m⠉\x1b[0m\x1b[38;2;1;54;68m⠉\x1b["
        "0m\x1b[38;2;4;53;68m⠁\x1b[0m\x1b[38;2;5;48;64m⠀\x1b["
        "0m\x1b[38;2;0;39;56m⠀\x1b[0m\x1b[38;2;17;55;74m⠀\x1b"
        "[0m\x1b[38;2;10;53;70m⠀\x1b[0m\x1b[38;2;7;54;70m⠀"
        "\x1b[0m\x1b[38;2;2;45;62m⠀\x1b[0m\x1b[38;2;0;46;62m⠀"
        "\x1b[0m\x1b[38;2;20;61;79m⠀\x1b[0m\x1b[38;2;5;51;67m"
        "⠀\x1b[0m\x1b[38;2;1;47;62m⠀\x1b[0m\x1b[38;2;11;53;69"
        "m⠀\x1b[0m\x1b[38;2;11;47;63m⠀\x1b[0m\x1b[38;2;13;49;"
        "65m⠀\x1b[0m\x1b[38;2;18;46;67m⠀\x1b[0m\x1b[38;2;10;4"
        "7;65m⠀\x1b[0m\x1b[38;2;20;57;75m⠀\x1b[0m\x1b[38;2;17"
        ";54;72m⠀\x1b[0m\x1b[38;2;16;48;61m⠀\x1b[0m\x1b[38;2;"
        "13;45;58m⠀\x1b[0m\x1b[38;2;16;44;56m⠀\x1b[0m\x1b[38;"
        "2;14;42;54m⠀\x1b[0m\x1b[38;2;14;42;54m⠀\x1b[0m\x1b[3"
        "8;2;23;51;63m⠀\x1b[0m\x1b[38;2;19;47;59m⠀\x1b[0m\x1b"
        "[38;2;17;45;57m⠀\x1b[0m\x1b[38;2;15;43;55m⠀\x1b[0"
        "m\x1b[38;2;20;48;60m⠀\x1b[0m\n  \x1b[38;2;9;42;59m"
        "⠀\x1b[0m\x1b[38;2;4;40;56m⠀\x1b[0m\x1b[38;2;9;45;61m"
        "⠀\x1b[0m\x1b[38;2;10;46;62m⠀\x1b[0m\x1b[38;2;8;43;62"
        "m⠀\x1b[0m\x1b[38;2;5;40;59m⠀\x1b[0m\x1b[38;2;17;53;6"
        "7m⠀\x1b[0m\x1b[38;2;4;47;63m⠀\x1b[0m\x1b[38;2;6;52;6"
        "7m⠀\x1b[0m\x1b[38;2;4;53;67m⠈\x1b[0m\x1b[38;2;0;61;8"
        "1m⣿\x1b[0m\x1b[38;2;180;192;208m⣷\x1b[0m\x1b[38;2;18"
        "9;176;144m⣺\x1b[0m\x1b[38;2;106;96;69m⠿\x1b[0m\x1b[3"
        "8;2;181;161;111m⡾\x1b[0m\x1b[38;2;198;174;128m"
        "⡿\x1b[0m\x1b[38;2;95;81;44m⠿\x1b[0m\x1b[38;2;42;31;2"
        "9m⠆\x1b[0m\x1b[38;2;36;36;38m⢳\x1b[0m\x1b[38;2;35;31"
        ";46m⡋\x1b[0m\x1b[38;2;198;184;139m⣿\x1b[0m\x1b[38;2;"
        "150;131;89m⣿\x1b[0m\x1b[38;2;173;158;119m⣿\x1b[0m"
        "\x1b[38;2;160;147;105m⣯\x1b[0m\x1b[38;2;180;166;1"
        "29m⣿\x1b[0m\x1b[38;2;151;146;126m⡏\x1b[0m\x1b[38;2;3"
        "3;50;58m⠧\x1b[0m\x1b[38;2;84;83;89m⠝\x1b[0m\x1b[38;2"
        ";20;26;38m⠕\x1b[0m\x1b[38;2;15;17;32m⠀\x1b[0m\x1b[38"
        ";2;12;34;47m⠛\x1b[0m\x1b[38;2;16;26;38m⠋\x1b[0m\x1b["
        "38;2;15;32;42m⠉\x1b[0m\x1b[38;2;14;32;42m⠉\x1b[0m"
        "\x1b[38;2;10;37;48m⠁\x1b[0m\x1b[38;2;7;39;50m⠀\x1b[0"
        "m\x1b[38;2;5;47;59m⠀\x1b[0m\x1b[38;2;6;48;64m⠀\x1b[0"
        "m\x1b[38;2;3;45;61m⠀\x1b[0m\x1b[38;2;14;55;73m⠀\x1b["
        "0m\x1b[38;2;2;43;61m⠀\x1b[0m\x1b[38;2;5;48;65m⠀\x1b["
        "0m\x1b[38;2;3;41;60m⠀\x1b[0m\x1b[38;2;5;43;62m⠀\x1b["
        "0m\x1b[38;2;4;50;66m⠀\x1b[0m\x1b[38;2;5;48;67m⠈\x1b["
        "0m\x1b[38;2;6;49;68m⠈\x1b[0m\x1b[38;2;12;58;74m⠀\x1b"
        "[0m\x1b[38;2;12;49;68m⠀\x1b[0m\x1b[38;2;8;43;62m⠀"
        "\x1b[0m\x1b[38;2;7;42;61m⠀\x1b[0m\x1b[38;2;8;46;65m⠀"
        "\x1b[0m\x1b[38;2;12;51;66m⠀\x1b[0m\x1b[38;2;11;44;61"
        "m⠀\x1b[0m\x1b[38;2;7;44;60m⠀\x1b[0m\x1b[38;2;9;46;64"
        "m⠀\x1b[0m\x1b[38;2;9;46;64m⠀\x1b[0m\x1b[38;2;15;50;6"
        "9m⠀\x1b[0m\x1b[38;2;12;44;59m⠀\x1b[0m\x1b[38;2;13;40"
        ";59m⠀\x1b[0m\x1b[38;2;17;45;59m⠀\x1b[0m\x1b[38;2;12;"
        "40;54m⠀\x1b[0m\x1b[38;2;15;41;56m⠀\x1b[0m\x1b[38;2;1"
        "7;43;58m⠀\x1b[0m\x1b[38;2;16;38;52m⠀\x1b[0m\x1b[38;2"
        ";14;36;50m⠀\x1b[0m\x1b[38;2;18;41;55m⠀\x1b[0m\x1b[38"
        ";2;25;48;62m⠀\x1b[0m\x1b[38;2;22;50;62m⠀\x1b[0m\x1b["
        "38;2;17;40;54m⠀\x1b[0m\x1b[38;2;14;37;51m⠀\x1b[0m"
        "\x1b[38;2;19;42;56m⠀\x1b[0m\x1b[38;2;19;41;55m⠀\x1b["
        "0m\x1b[38;2;20;42;56m⠀\x1b[0m\x1b[38;2;21;40;55m⠀"
        "\x1b[0m\x1b[38;2;18;37;52m⠀\x1b[0m\x1b[38;2;29;46;62"
        "m⠀\x1b[0m\x1b[38;2;23;40;56m⠀\x1b[0m\n  \x1b[38;2;16;"
        "42;57m⠀\x1b[0m\x1b[38;2;6;35;49m⠀\x1b[0m\x1b[38;2;14"
        ";45;63m⠀\x1b[0m\x1b[38;2;9;40;58m⠀\x1b[0m\x1b[38;2;7"
        ";36;50m⠀\x1b[0m\x1b[38;2;6;42;54m⠀\x1b[0m\x1b[38;2;8"
        ";56;70m⠀\x1b[0m\x1b[38;2;6;54;68m⠀\x1b[0m\x1b[38;2;8"
        ";47;62m⢀\x1b[0m\x1b[38;2;5;75;85m⣄\x1b[0m\x1b[38;2;1"
        "95;243;255m⣤\x1b[0m\x1b[38;2;51;133;144m⣭\x1b[0m\x1b"
        "[38;2;0;39;58m⢉\x1b[0m\x1b[38;2;25;44;61m⣌\x1b[0m"
        "\x1b[38;2;39;59;66m⡹\x1b[0m\x1b[38;2;29;77;91m⣯\x1b["
        "0m\x1b[38;2;90;99;108m⠍\x1b[0m\x1b[38;2;14;23;32m"
        "⠀\x1b[0m\x1b[38;2;41;63;74m⡠\x1b[0m\x1b[38;2;150;182"
        ";203m⢆\x1b[0m\x1b[38;2;109;94;51m⣼\x1b[0m\x1b[38;2;2"
        "05;189;163m⣽\x1b[0m\x1b[38;2;122;109;74m⣿\x1b[0m\x1b"
        "[38;2;210;191;158m⣿\x1b[0m\x1b[38;2;200;185;15"
        "6m⣿\x1b[0m\x1b[38;2;38;37;33m⠟\x1b[0m\x1b[38;2;19;29"
        ";41m⠄\x1b[0m\x1b[38;2;19;22;37m⠀\x1b[0m\x1b[38;2;17;"
        "25;38m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;1"
        "7;31;44m⠀\x1b[0m\x1b[38;2;9;27;41m⠀\x1b[0m\x1b[38;2;"
        "15;33;47m⠀\x1b[0m\x1b[38;2;14;38;50m⠀\x1b[0m\x1b[38;"
        "2;8;40;53m⠀\x1b[0m\x1b[38;2;6;42;58m⠀\x1b[0m\x1b[38;"
        "2;11;44;61m⠀\x1b[0m\x1b[38;2;3;42;57m⠀\x1b[0m\x1b[38"
        ";2;9;48;63m⠀\x1b[0m\x1b[38;2;15;52;68m⠀\x1b[0m\x1b[3"
        "8;2;4;37;54m⠀\x1b[0m\x1b[38;2;17;42;64m⠀\x1b[0m\x1b["
        "38;2;18;43;65m⠀\x1b[0m\x1b[38;2;12;41;59m⠀\x1b[0m"
        "\x1b[38;2;11;44;61m⠀\x1b[0m\x1b[38;2;8;40;55m⠀\x1b[0"
        "m\x1b[38;2;15;42;59m⠀\x1b[0m\x1b[38;2;20;49;65m⠀\x1b"
        "[0m\x1b[38;2;9;38;54m⠀\x1b[0m\x1b[38;2;9;38;54m⠀\x1b"
        "[0m\x1b[38;2;13;42;58m⠀\x1b[0m\x1b[38;2;14;49;68m"
        "⠀\x1b[0m\x1b[38;2;5;40;59m⠀\x1b[0m\x1b[38;2;13;48;67"
        "m⠀\x1b[0m\x1b[38;2;2;37;56m⠀\x1b[0m\x1b[38;2;4;36;51"
        "m⠀\x1b[0m\x1b[38;2;4;36;51m⠀\x1b[0m\x1b[38;2;16;45;6"
        "1m⠀\x1b[0m\x1b[38;2;12;41;57m⠀\x1b[0m\x1b[38;2;15;44"
        ";58m⠀\x1b[0m\x1b[38;2;17;36;51m⠀\x1b[0m\x1b[38;2;25;"
        "42;58m⠀\x1b[0m\x1b[38;2;12;34;48m⠀\x1b[0m\x1b[38;2;1"
        "5;37;51m⠀\x1b[0m\x1b[38;2;14;40;53m⠀\x1b[0m\x1b[38;2"
        ";16;38;52m⠀\x1b[0m\x1b[38;2;21;37;53m⠀\x1b[0m\x1b[38"
        ";2;18;37;52m⠀\x1b[0m\x1b[38;2;20;39;54m⠀\x1b[0m\x1b["
        "38;2;20;39;54m⠀\x1b[0m\x1b[38;2;22;39;55m⠀\x1b[0m"
        "\x1b[38;2;23;40;56m⠀\x1b[0m\x1b[38;2;20;37;53m⠀\x1b["
        "0m\x1b[38;2;22;39;55m⠀\x1b[0m\x1b[38;2;18;35;51m⠀"
        "\x1b[0m\x1b[38;2;14;31;47m⠀\x1b[0m\x1b[38;2;20;38;52"
        "m⠀\x1b[0m\x1b[38;2;22;40;54m⠀\x1b[0m\n  \x1b[38;2;15;"
        "38;52m⠀\x1b[0m\x1b[38;2;18;34;50m⠀\x1b[0m\x1b[38;2;1"
        "9;36;52m⠀\x1b[0m\x1b[38;2;8;36;48m⠀\x1b[0m\x1b[38;2;"
        "9;39;50m⠀\x1b[0m\x1b[38;2;12;46;56m⠀\x1b[0m\x1b[38;2"
        ";19;56;65m⠀\x1b[0m\x1b[38;2;27;67;75m⠀\x1b[0m\x1b[38"
        ";2;6;43;49m⠛\x1b[0m\x1b[38;2;80;143;160m⠻\x1b[0m\x1b"
        "[38;2;64;110;126m⠟\x1b[0m\x1b[38;2;3;55;76m⠇\x1b["
        "0m\x1b[38;2;14;51;59m⠀\x1b[0m\x1b[38;2;17;34;44m⠈"
        "\x1b[0m\x1b[38;2;16;33;43m⠈\x1b[0m\x1b[38;2;16;41;48"
        "m⠁\x1b[0m\x1b[38;2;33;43;55m⠀\x1b[0m\x1b[38;2;28;40;"
        "52m⠈\x1b[0m\x1b[38;2;44;105;108m⠛\x1b[0m\x1b[38;2;10"
        ";33;41m⠒\x1b[0m\x1b[38;2;13;16;25m⠢\x1b[0m\x1b[38;2;"
        "100;105;101m⠼\x1b[0m\x1b[38;2;184;188;191m⠿\x1b[0"
        "m\x1b[38;2;12;16;25m⠍\x1b[0m\x1b[38;2;17;26;35m⠒\x1b"
        "[0m\x1b[38;2;7;24;34m⠁\x1b[0m\x1b[38;2;20;23;38m⠀"
        "\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;15;29;40"
        "m⠀\x1b[0m\x1b[38;2;15;33;45m⠀\x1b[0m\x1b[38;2;17;34;"
        "50m⠀\x1b[0m\x1b[38;2;12;34;48m⠀\x1b[0m\x1b[38;2;13;3"
        "5;49m⠀\x1b[0m\x1b[38;2;10;36;49m⠀\x1b[0m\x1b[38;2;11"
        ";41;52m⠀\x1b[0m\x1b[38;2;14;37;53m⠀\x1b[0m\x1b[38;2;"
        "14;42;56m⠀\x1b[0m\x1b[38;2;18;61;70m⠀\x1b[0m\x1b[38;"
        "2;5;51;66m⠀\x1b[0m\x1b[38;2;10;62;76m⠀\x1b[0m\x1b[38"
        ";2;23;65;79m⠀\x1b[0m\x1b[38;2;4;33;49m⠀\x1b[0m\x1b[3"
        "8;2;11;37;54m⠀\x1b[0m\x1b[38;2;16;38;52m⠀\x1b[0m\x1b"
        "[38;2;19;36;52m⠀\x1b[0m\x1b[38;2;23;42;57m⠀\x1b[0"
        "m\x1b[38;2;12;35;49m⠀\x1b[0m\x1b[38;2;19;38;55m⠀\x1b"
        "[0m\x1b[38;2;9;32;48m⠀\x1b[0m\x1b[38;2;11;37;52m⠀"
        "\x1b[0m\x1b[38;2;21;47;62m⠀\x1b[0m\x1b[38;2;13;36;52"
        "m⠀\x1b[0m\x1b[38;2;13;36;52m⠀\x1b[0m\x1b[38;2;22;41;"
        "58m⠀\x1b[0m\x1b[38;2;19;35;50m⠀\x1b[0m\x1b[38;2;16;3"
        "5;50m⠀\x1b[0m\x1b[38;2;14;33;48m⠀\x1b[0m\x1b[38;2;16"
        ";38;52m⠀\x1b[0m\x1b[38;2;18;40;54m⠀\x1b[0m\x1b[38;2;"
        "13;29;45m⠀\x1b[0m\x1b[38;2;11;29;43m⠀\x1b[0m\x1b[38;"
        "2;22;40;54m⠀\x1b[0m\x1b[38;2;23;39;54m⠀\x1b[0m\x1b[3"
        "8;2;22;38;53m⠀\x1b[0m\x1b[38;2;17;33;49m⠀\x1b[0m\x1b"
        "[38;2;22;38;54m⠀\x1b[0m\x1b[38;2;26;40;53m⠀\x1b[0"
        "m\x1b[38;2;17;31;44m⠀\x1b[0m\x1b[38;2;19;35;50m⠀\x1b"
        "[0m\x1b[38;2;15;31;46m⠀\x1b[0m\x1b[38;2;20;36;49m"
        "⠀\x1b[0m\x1b[38;2;15;31;44m⠀\x1b[0m\x1b[38;2;17;31;4"
        "4m⠀\x1b[0m\x1b[38;2;22;36;49m⠀\x1b[0m\x1b[38;2;19;33"
        ";44m⠀\x1b[0m\x1b[38;2;19;33;44m⠀\x1b[0m\x1b[38;2;21;"
        "39;53m⠀\x1b[0m\x1b[38;2;21;39;53m⠀\x1b[0m\n  \x1b[38;"
        "2;24;40;56m⠀\x1b[0m\x1b[38;2;18;34;50m⠀\x1b[0m\x1b[3"
        "8;2;20;36;51m⠀\x1b[0m\x1b[38;2;16;33;43m⠀\x1b[0m\x1b"
        "[38;2;17;40;54m⠀\x1b[0m\x1b[38;2;13;36;50m⠀\x1b[0"
        "m\x1b[38;2;15;34;49m⠀\x1b[0m\x1b[38;2;4;38;48m⠀\x1b["
        "0m\x1b[38;2;9;41;54m⠀\x1b[0m\x1b[38;2;10;38;52m⠀\x1b"
        "[0m\x1b[38;2;17;40;54m⠀\x1b[0m\x1b[38;2;20;39;54m"
        "⠀\x1b[0m\x1b[38;2;13;41;52m⠀\x1b[0m\x1b[38;2;12;40;5"
        "1m⠀\x1b[0m\x1b[38;2;16;36;45m⠀\x1b[0m\x1b[38;2;17;34"
        ";44m⠀\x1b[0m\x1b[38;2;17;34;44m⠀\x1b[0m\x1b[38;2;16;"
        "33;43m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38;2;1"
        "2;24;36m⠀\x1b[0m\x1b[38;2;16;24;37m⠀\x1b[0m\x1b[38;2"
        ";17;23;37m⠀\x1b[0m\x1b[38;2;16;22;36m⠀\x1b[0m\x1b[38"
        ";2;21;31;43m⠀\x1b[0m\x1b[38;2;16;26;38m⠀\x1b[0m\x1b["
        "38;2;17;25;38m⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b[0m"
        "\x1b[38;2;20;29;44m⠀\x1b[0m\x1b[38;2;16;28;42m⠀\x1b["
        "0m\x1b[38;2;23;28;47m⠀\x1b[0m\x1b[38;2;18;40;53m⠀"
        "\x1b[0m\x1b[38;2;11;44;53m⠀\x1b[0m\x1b[38;2;11;43;56"
        "m⠀\x1b[0m\x1b[38;2;12;34;48m⠀\x1b[0m\x1b[38;2;12;34;"
        "48m⠀\x1b[0m\x1b[38;2;17;34;50m⠀\x1b[0m\x1b[38;2;16;3"
        "3;49m⠀\x1b[0m\x1b[38;2;10;29;44m⠀\x1b[0m\x1b[38;2;17"
        ";36;51m⠀\x1b[0m\x1b[38;2;16;38;52m⠀\x1b[0m\x1b[38;2;"
        "23;45;59m⠀\x1b[0m\x1b[38;2;10;32;46m⠀\x1b[0m\x1b[38;"
        "2;21;43;57m⠀\x1b[0m\x1b[38;2;17;38;55m⠀\x1b[0m\x1b[3"
        "8;2;10;36;51m⠀\x1b[0m\x1b[38;2;11;37;54m⠀\x1b[0m\x1b"
        "[38;2;23;41;61m⠀\x1b[0m\x1b[38;2;19;38;53m⠀\x1b[0"
        "m\x1b[38;2;18;37;52m⠀\x1b[0m\x1b[38;2;17;34;50m⠀\x1b"
        "[0m\x1b[38;2;16;33;49m⠀\x1b[0m\x1b[38;2;18;34;50m"
        "⠀\x1b[0m\x1b[38;2;16;32;48m⠀\x1b[0m\x1b[38;2;18;34;5"
        "0m⠀\x1b[0m\x1b[38;2;22;38;54m⠀\x1b[0m\x1b[38;2;17;33"
        ";49m⠀\x1b[0m\x1b[38;2;14;30;46m⠀\x1b[0m\x1b[38;2;19;"
        "35;50m⠀\x1b[0m\x1b[38;2;16;32;47m⠀\x1b[0m\x1b[38;2;1"
        "2;25;41m⠀\x1b[0m\x1b[38;2;20;33;49m⠀\x1b[0m\x1b[38;2"
        ";21;34;50m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38"
        ";2;20;34;47m⠀\x1b[0m\x1b[38;2;21;35;46m⠀\x1b[0m\x1b["
        "38;2;18;32;43m⠀\x1b[0m\x1b[38;2;14;28;39m⠀\x1b[0m"
        "\x1b[38;2;26;40;51m⠀\x1b[0m\x1b[38;2;11;25;38m⠀\x1b["
        "0m\x1b[38;2;27;41;54m⠀\x1b[0m\x1b[38;2;26;40;51m⠀"
        "\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b[38;2;17;29;41"
        "m⠀\x1b[0m\x1b[38;2;21;33;45m⠀\x1b[0m\x1b[38;2;18;30;"
        "42m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38;2;17;2"
        "9;41m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\n  \x1b[38;2"
        ";18;32;45m⠀\x1b[0m\x1b[38;2;20;34;47m⠀\x1b[0m\x1b[38"
        ";2;18;34;47m⠀\x1b[0m\x1b[38;2;16;32;45m⠀\x1b[0m\x1b["
        "38;2;20;38;50m⠀\x1b[0m\x1b[38;2;15;33;45m⠀\x1b[0m"
        "\x1b[38;2;18;34;47m⠀\x1b[0m\x1b[38;2;19;35;48m⠀\x1b["
        "0m\x1b[38;2;22;38;51m⠀\x1b[0m\x1b[38;2;15;31;44m⠀"
        "\x1b[0m\x1b[38;2;16;33;41m⠀\x1b[0m\x1b[38;2;13;30;38"
        "m⠀\x1b[0m\x1b[38;2;17;34;44m⠀\x1b[0m\x1b[38;2;12;29;"
        "39m⠀\x1b[0m\x1b[38;2;15;31;44m⠀\x1b[0m\x1b[38;2;19;3"
        "5;48m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38;2;19"
        ";31;43m⠀\x1b[0m\x1b[38;2;15;33;43m⠀\x1b[0m\x1b[38;2;"
        "14;32;42m⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b[0m\x1b[38;"
        "2;19;27;40m⠀\x1b[0m\x1b[38;2;18;26;39m⠀\x1b[0m\x1b[3"
        "8;2;19;29;41m⠀\x1b[0m\x1b[38;2;19;29;41m⠀\x1b[0m\x1b"
        "[38;2;20;30;42m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0"
        "m\x1b[38;2;16;30;39m⠀\x1b[0m\x1b[38;2;26;49;65m⠠\x1b"
        "[0m\x1b[38;2;62;119;126m⠆\x1b[0m\x1b[38;2;145;198"
        ";212m⡴\x1b[0m\x1b[38;2;113;159;174m⡾\x1b[0m\x1b[38;2"
        ";16;56;66m⠇\x1b[0m\x1b[38;2;19;32;49m⠀\x1b[0m\x1b[38"
        ";2;16;29;46m⠀\x1b[0m\x1b[38;2;11;33;47m⠀\x1b[0m\x1b["
        "38;2;19;41;55m⠀\x1b[0m\x1b[38;2;18;34;50m⠀\x1b[0m"
        "\x1b[38;2;19;35;51m⠀\x1b[0m\x1b[38;2;18;35;51m⠀\x1b["
        "0m\x1b[38;2;18;35;51m⠀\x1b[0m\x1b[38;2;20;36;52m⠀"
        "\x1b[0m\x1b[38;2;16;32;48m⠀\x1b[0m\x1b[38;2;13;29;45"
        "m⠀\x1b[0m\x1b[38;2;15;31;47m⠀\x1b[0m\x1b[38;2;16;32;"
        "48m⠀\x1b[0m\x1b[38;2;17;33;49m⠀\x1b[0m\x1b[38;2;13;2"
        "9;45m⠀\x1b[0m\x1b[38;2;16;32;48m⠀\x1b[0m\x1b[38;2;22"
        ";38;54m⠀\x1b[0m\x1b[38;2;19;35;51m⠀\x1b[0m\x1b[38;2;"
        "21;37;53m⠀\x1b[0m\x1b[38;2;14;30;46m⠀\x1b[0m\x1b[38;"
        "2;20;33;50m⠀\x1b[0m\x1b[38;2;22;35;52m⠀\x1b[0m\x1b[3"
        "8;2;17;30;47m⠀\x1b[0m\x1b[38;2;16;29;46m⠀\x1b[0m\x1b"
        "[38;2;18;32;45m⠀\x1b[0m\x1b[38;2;18;32;45m⠀\x1b[0"
        "m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;20;34;45m⠀\x1b"
        "[0m\x1b[38;2;20;34;45m⠀\x1b[0m\x1b[38;2;21;35;46m"
        "⠀\x1b[0m\x1b[38;2;20;34;45m⠀\x1b[0m\x1b[38;2;19;33;4"
        "4m⠀\x1b[0m\x1b[38;2;19;33;44m⠀\x1b[0m\x1b[38;2;14;28"
        ";39m⠀\x1b[0m\x1b[38;2;19;29;41m⠀\x1b[0m\x1b[38;2;21;"
        "27;41m⠀\x1b[0m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;2"
        "0;32;44m⠀\x1b[0m\x1b[38;2;18;30;42m⠀\x1b[0m\x1b[38;2"
        ";19;31;43m⠀\x1b[0m\x1b[38;2;19;27;40m⠀\x1b[0m\x1b[38"
        ";2;21;27;41m⠀\x1b[0m\x1b[38;2;21;27;41m⠀\x1b[0m\x1b["
        "38;2;21;31;43m⠀\x1b[0m\x1b[38;2;21;31;43m⠀\x1b[0m"
        "\n  \x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;18;32;43m"
        "⠀\x1b[0m\x1b[38;2;24;38;49m⠀\x1b[0m\x1b[38;2;14;28;3"
        "9m⠀\x1b[0m\x1b[38;2;23;35;47m⠀\x1b[0m\x1b[38;2;19;31"
        ";43m⠀\x1b[0m\x1b[38;2;18;30;42m⠀\x1b[0m\x1b[38;2;18;"
        "30;42m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;1"
        "9;33;44m⠀\x1b[0m\x1b[38;2;20;36;52m⠀\x1b[0m\x1b[38;2"
        ";14;33;48m⠀\x1b[0m\x1b[38;2;19;35;48m⠀\x1b[0m\x1b[38"
        ";2;14;30;43m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b["
        "38;2;16;30;43m⠀\x1b[0m\x1b[38;2;15;27;39m⠀\x1b[0m"
        "\x1b[38;2;16;28;40m⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b["
        "0m\x1b[38;2;15;27;39m⠀\x1b[0m\x1b[38;2;16;33;43m⠀"
        "\x1b[0m\x1b[38;2;14;31;41m⠀\x1b[0m\x1b[38;2;20;37;47"
        "m⠀\x1b[0m\x1b[38;2;15;32;42m⠀\x1b[0m\x1b[38;2;15;27;"
        "39m⠀\x1b[0m\x1b[38;2;14;41;50m⠀\x1b[0m\x1b[38;2;14;4"
        "4;52m⠀\x1b[0m\x1b[38;2;13;43;53m⠀\x1b[0m\x1b[38;2;17"
        ";51;60m⠀\x1b[0m\x1b[38;2;11;52;58m⠀\x1b[0m\x1b[38;2;"
        "14;36;49m⠀\x1b[0m\x1b[38;2;14;36;50m⠀\x1b[0m\x1b[38;"
        "2;19;35;51m⠀\x1b[0m\x1b[38;2;15;35;46m⠀\x1b[0m\x1b[3"
        "8;2;16;30;43m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b"
        "[38;2;18;32;43m⠀\x1b[0m\x1b[38;2;20;33;49m⠀\x1b[0"
        "m\x1b[38;2;17;30;46m⠀\x1b[0m\x1b[38;2;14;27;44m⠀\x1b"
        "[0m\x1b[38;2;19;32;49m⠀\x1b[0m\x1b[38;2;19;32;48m"
        "⠀\x1b[0m\x1b[38;2;17;30;46m⠀\x1b[0m\x1b[38;2;17;30;4"
        "7m⠀\x1b[0m\x1b[38;2;20;33;50m⠀\x1b[0m\x1b[38;2;15;28"
        ";45m⠀\x1b[0m\x1b[38;2;18;31;48m⠀\x1b[0m\x1b[38;2;23;"
        "36;53m⠀\x1b[0m\x1b[38;2;26;39;56m⠀\x1b[0m\x1b[38;2;1"
        "7;30;47m⠀\x1b[0m\x1b[38;2;18;31;48m⠀\x1b[0m\x1b[38;2"
        ";17;30;46m⠀\x1b[0m\x1b[38;2;16;29;45m⠀\x1b[0m\x1b[38"
        ";2;16;30;43m⠀\x1b[0m\x1b[38;2;13;27;40m⠀\x1b[0m\x1b["
        "38;2;18;32;43m⠀\x1b[0m\x1b[38;2;21;35;46m⠀\x1b[0m"
        "\x1b[38;2;23;37;48m⠀\x1b[0m\x1b[38;2;18;32;43m⠀\x1b["
        "0m\x1b[38;2;21;33;45m⠀\x1b[0m\x1b[38;2;21;33;45m⠀"
        "\x1b[0m\x1b[38;2;23;35;47m⠀\x1b[0m\x1b[38;2;11;23;35"
        "m⠀\x1b[0m\x1b[38;2;19;31;43m⠀\x1b[0m\x1b[38;2;20;26;"
        "40m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;18;2"
        "4;38m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;22"
        ";28;42m⠀\x1b[0m\x1b[38;2;18;24;38m⠀\x1b[0m\x1b[38;2;"
        "18;24;38m⠀\x1b[0m\x1b[38;2;21;27;41m⠀\x1b[0m\x1b[38;"
        "2;15;21;35m⠀\x1b[0m\x1b[38;2;23;29;43m⠀\x1b[0m\x1b[3"
        "8;2;22;28;42m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b"
        "[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;25;31;45m⠀\x1b[0"
        "m\n  \x1b[38;2;21;33;45m⠀\x1b[0m\x1b[38;2;16;28;40"
        "m⠀\x1b[0m\x1b[38;2;20;30;42m⠀\x1b[0m\x1b[38;2;19;29;"
        "41m⠀\x1b[0m\x1b[38;2;23;29;43m⠀\x1b[0m\x1b[38;2;21;2"
        "7;41m⠀\x1b[0m\x1b[38;2;18;28;40m⠀\x1b[0m\x1b[38;2;19"
        ";29;41m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b[38;2;"
        "20;34;45m⠀\x1b[0m\x1b[38;2;17;29;41m⠀\x1b[0m\x1b[38;"
        "2;25;37;49m⠀\x1b[0m\x1b[38;2;20;32;44m⠀\x1b[0m\x1b[3"
        "8;2;13;25;37m⠀\x1b[0m\x1b[38;2;19;25;39m⠀\x1b[0m\x1b"
        "[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;16;34;44m⠀\x1b[0"
        "m\x1b[38;2;17;37;48m⠀\x1b[0m\x1b[38;2;16;33;49m⠀\x1b"
        "[0m\x1b[38;2;15;33;47m⠀\x1b[0m\x1b[38;2;14;32;42m"
        "⠀\x1b[0m\x1b[38;2;21;35;46m⠀\x1b[0m\x1b[38;2;14;28;3"
        "9m⠀\x1b[0m\x1b[38;2;18;30;42m⠀\x1b[0m\x1b[38;2;18;30"
        ";42m⠀\x1b[0m\x1b[38;2;14;31;41m⠀\x1b[0m\x1b[38;2;15;"
        "32;42m⠀\x1b[0m\x1b[38;2;20;30;40m⠀\x1b[0m\x1b[38;2;1"
        "8;32;41m⠀\x1b[0m\x1b[38;2;18;31;47m⠀\x1b[0m\x1b[38;2"
        ";16;34;48m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b[38"
        ";2;19;33;44m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b["
        "38;2;17;31;42m⠀\x1b[0m\x1b[38;2;24;37;56m⠀\x1b[0m"
        "\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;2;16;30;39m⠀\x1b["
        "0m\x1b[38;2;17;31;40m⠀\x1b[0m\x1b[38;2;17;31;40m⠀"
        "\x1b[0m\x1b[38;2;17;31;40m⠀\x1b[0m\x1b[38;2;16;30;41"
        "m⠀\x1b[0m\x1b[38;2;16;30;41m⠀\x1b[0m\x1b[38;2;18;32;"
        "43m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;17;3"
        "1;42m⠀\x1b[0m\x1b[38;2;17;31;42m⠀\x1b[0m\x1b[38;2;17"
        ";31;42m⠀\x1b[0m\x1b[38;2;18;32;43m⠀\x1b[0m\x1b[38;2;"
        "18;32;45m⠀\x1b[0m\x1b[38;2;16;30;43m⠀\x1b[0m\x1b[38;"
        "2;17;29;41m⠀\x1b[0m\x1b[38;2;16;28;40m⠀\x1b[0m\x1b[3"
        "8;2;18;28;40m⠀\x1b[0m\x1b[38;2;20;30;42m⠀\x1b[0m\x1b"
        "[38;2;17;27;39m⠀\x1b[0m\x1b[38;2;16;26;38m⠀\x1b[0"
        "m\x1b[38;2;21;31;43m⠀\x1b[0m\x1b[38;2;18;28;40m⠀\x1b"
        "[0m\x1b[38;2;19;25;39m⠀\x1b[0m\x1b[38;2;22;28;42m"
        "⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;21;27;4"
        "1m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;21;27"
        ";41m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;19;"
        "25;39m⠀\x1b[0m\x1b[38;2;21;27;41m⠀\x1b[0m\x1b[38;2;2"
        "1;27;41m⠀\x1b[0m\x1b[38;2;23;29;43m⠀\x1b[0m\x1b[38;2"
        ";20;26;40m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38"
        ";2;21;27;41m⠀\x1b[0m\x1b[38;2;19;25;39m⠀\x1b[0m\x1b["
        "38;2;18;24;38m⠀\x1b[0m\x1b[38;2;20;26;40m⠀\x1b[0m"
        "\x1b[38;2;20;26;40m⠀\x1b[0m\x1b[38;2;22;28;42m⠀\x1b["
        "0m\n                                     "
        "                                        "
        "   \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_code_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a markdown cell with code."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "```python\nfor i in range(20):\n    print(i)\n```",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  \x1b[38;2;248;248;242;49m    \x1b[0m\x1b[38;2;1"
        "02;217;239;49mfor\x1b[0m\x1b[38;2;248;248;242;"
        "49m \x1b[0m\x1b[38;2;248;248;242;49mi\x1b[0m\x1b[38;"
        "2;248;248;242;49m \x1b[0m\x1b[38;2;249;38;114;"
        "49min\x1b[0m\x1b[38;2;248;248;242;49m \x1b[0m\x1b[38"
        ";2;248;248;242;49mrange\x1b[0m\x1b[38;2;248;24"
        "8;242;49m(\x1b[0m\x1b[38;2;174;129;255;49m20\x1b["
        "0m\x1b[38;2;248;248;242;49m)\x1b[0m\x1b[38;2;248;"
        "248;242;49m:\x1b[0m                        "
        "                               \n  \x1b[38;2"
        ";248;248;242;49m        \x1b[0m\x1b[38;2;248;2"
        "48;242;49mprint\x1b[0m\x1b[38;2;248;248;242;49"
        "m(\x1b[0m\x1b[38;2;248;248;242;49mi\x1b[0m\x1b[38;2;"
        "248;248;242;49m)\x1b[0m                    "
        "                                        "
        "  \n"
    )
    assert output == expected_output


def test_heading_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a markdown cell with headings."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "# Heading 1\n## Heading 2\n### Heading 3\n#### Heading 4\n",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  \x1b[1;38;2;255;255;255;48;2;96;2;238m \x1b["
        "0m\x1b[1;38;2;255;255;255;48;2;96;2;238mHea"
        "ding 1\x1b[0m\x1b[1;38;2;255;255;255;48;2;96;2"
        ";238m \x1b[0m\x1b[1;38;2;255;255;255;48;2;96;2"
        ";238m                                   "
        "                                \x1b[0m\n  \x1b"
        "[2;38;2;96;2;238m───────────────────────"
        "────────────────────────────────────────"
        "───────────────\x1b[0m\n                    "
        "                                        "
        "                    \n                   "
        "                                        "
        "                     \n  \x1b[1;38;2;3;218;1"
        "97m## \x1b[0m\x1b[1;38;2;3;218;197mHeading 2\x1b["
        "0m\x1b[1;38;2;3;218;197m                   "
        "                                        "
        "       \x1b[0m\n  \x1b[2;38;2;3;218;197m───────"
        "────────────────────────────────────────"
        "───────────────────────────────\x1b[0m\n    "
        "                                        "
        "                                    \n   "
        "                                        "
        "                                     \n  "
        "\x1b[1;38;2;3;218;197m### \x1b[0m\x1b[1;38;2;3;21"
        "8;197mHeading 3\x1b[0m\x1b[1;38;2;3;218;197m  "
        "                                        "
        "                       \x1b[0m\n            "
        "                                        "
        "                            \n  \x1b[1;38;2;"
        "3;218;197m#### \x1b[0m\x1b[1;38;2;3;218;197mHe"
        "ading 4\x1b[0m\x1b[1;38;2;3;218;197m          "
        "                                        "
        "              \x1b[0m\n"
    )
    assert output == expected_output


def test_wide_heading_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It reduced the padding if the heading is long."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "# " + "A" * 80,
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  \x1b[1;38;2;255;255;255;48;2;96;2;238mAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA…\x1b[0m\n"
        "  \x1b[2;38;2;96;2;238m────────────────────"
        "────────────────────────────────────────"
        "──────────────────\x1b[0m\n"
    )
    assert output == expected_output


def test_ruler_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a markdown cell with a ruler."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "Section 1\n\n---\n\nsection 2\n",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  Section 1                             "
        "                                        "
        "\n                                       "
        "                                        "
        " \n  ────────────────────────────────────"
        "────────────────────────────────────────"
        "──\n  section 2                          "
        "                                        "
        "   \n"
    )
    assert output == expected_output


def test_bullet_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a markdown cell with bullets."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "- Item 1\n- Item 2\n  - Item 3\n",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "                                        "
        "                                        "
        "\n   • Item 1                            "
        "                                        "
        " \n   • Item 2                           "
        "                                        "
        "  \n      • Item 3                       "
        "                                        "
        "   \n"
    )
    assert output == expected_output


def test_number_markdown_cell(rich_notebook_output: RichOutput) -> None:
    """It renders a markdown cell with numbers."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "1. Item 1\n2. Item 2\n3. Item 3\n",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "                                        "
        "                                        "
        "\n  1. Item 1                            "
        "                                        "
        " \n  2. Item 2                           "
        "                                        "
        "  \n  3. Item 3                          "
        "                                        "
        "   \n"
    )
    assert output == expected_output


def test_image_file_link_not_image_markdown_cell(
    rich_notebook_output: RichOutput,
) -> None:
    """It does not render an image link when file is not an image."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![This is a weird file extension]"
        f"({pathlib.Path(__file__).parent / pathlib.Path('assets', 'bad_image.xyz')})",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  🖼 This is a weird file extension      "
        "                                        "
        "\n                                       "
        "                                        "
        " \n"
    )
    assert output == expected_output


def test_image_file_link_bad_extension_markdown_cell(
    rich_notebook_output: RichOutput,
) -> None:
    """It does not render an image link when extension is unknown."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": f"![This isn't even a image]({__file__})",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  🖼 This isn't even a image             "
        "                                        "
        "\n                                       "
        "                                        "
        " \n"
    )
    assert output == expected_output


def test_image_file_link_not_exist_markdown_cell(
    rich_notebook_output: RichOutput,
) -> None:
    """It does not render an image link when the file does not exist."""
    markdown_cell = {
        "cell_type": "markdown",
        "id": "academic-bride",
        "metadata": {},
        "source": "![This image does not exist](i_do_not_exists.xyz)",
    }
    output = rich_notebook_output(markdown_cell)
    expected_output = (
        "  🖼 This image does not exist           "
        "                                        "
        "\n                                       "
        "                                        "
        " \n"
    )
    assert output == expected_output


def test_notebook_code_cell(rich_notebook_output: RichOutput) -> None:
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


def test_notebook_magic_code_cell(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(code_cell)
    assert output == expected_output


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


def test_notebook_non_syntax_magic_code_cell(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(code_cell)
    assert output == expected_output


def test_notebook_plain_code_cell(rich_notebook_output: RichOutput) -> None:
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
    rich_notebook_output: RichOutput,
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
        f"file://{tempfile_path}0.html\x1b\\\x1b[94"
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
    output = rich_notebook_output(code_cell)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_plain_dataframe(
    rich_notebook_output: RichOutput,
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
        f"/{tempfile_path}0.html\x1b\\"
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
    output = rich_notebook_output(code_cell, plain=True)
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_stderr_stream(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(stderr_cell)
    assert output == expected_output


def test_render_stream_stdout(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(stdout_cell)
    assert output == expected_output


def test_render_error_traceback(rich_notebook_output: RichOutput) -> None:
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
        "                  \n      \x1b[1;31m--------"
        "----------------------------------------"
        "-------------------------…\x1b[0m\n      \x1b[1"
        ";31mZeroDivisionError\x1b[0m               "
        "          Traceback (most recent call   "
        "  \n      last)                          "
        "                                        "
        "   \n      \x1b[1;32m<ipython-input-7-9e1622"
        "b385b6>\x1b[0m in \x1b[36m<module>\x1b[0m        "
        "                        \n      \x1b[1;32m--"
        "--> 1\x1b[0m\x1b[1;33m \x1b[0m\x1b[1;36m1\x1b[0m\x1b[1;33m"
        "/\x1b[0m\x1b[1;36m0\x1b[0m                       "
        "                                        "
        "\n                                       "
        "                                        "
        " \n      \x1b[1;31mZeroDivisionError\x1b[0m: di"
        "vision by zero                          "
        "             \n"
    )
    output = rich_notebook_output(traceback_cell)
    assert output == expected_output


def test_render_error_traceback_no_hang(rich_notebook_output: RichOutput) -> None:
    """It renders the traceback from an error without hanging."""
    traceback_cell = {
        "cell_type": "code",
        "execution_count": 4,
        "id": "allied-contrary",
        "metadata": {},
        "outputs": [
            {
                "name": "stderr",
                "output_type": "stream",
                "text": "bash: line 1: ech: command not found\n",
            },
            {
                "ename": "CalledProcessError",
                "evalue": "Command 'b'ech\\n'' returned non-zero exit status 127.",
                "output_type": "error",
                "traceback": [
                    "\x1b[1;31m----------------------------------------"
                    "-----------------------------------\x1b[0m",
                    "\x1b[1;31mCalledProcessError\x1b[0m               "
                    "         Traceback (most recent call last)",
                    "\x1b[1;32m<ipython-input-4-4fb31ecfb364>\x1b[0m in"
                    " \x1b[0;36m<module>\x1b[1;34m\x1b[0m\n\x1b[1;32m--"
                    "--> 1\x1b[1;33m \x1b[0mget_ipython\x1b[0m\x1b[1;33"
                    "m(\x1b[0m\x1b[1;33m)\x1b[0m\x1b[1;33m.\x1b[0m\x1b["
                    "0mrun_cell_magic\x1b[0m\x1b[1;33m(\x1b[0m\x1b[1;34"
                    "m'bash'\x1b[0m\x1b[1;33m,\x1b[0m \x1b[1;34m''\x1b["
                    "0m\x1b[1;33m,\x1b[0m \x1b[1;34m'ech\\n'\x1b[0m\x1b"
                    "[1;33m)\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m"
                    "\x1b[0m\n\x1b[0m",
                    "\x1b[1;32m~/.pyenv/versions/scratch/lib/python3.8/"
                    "site-packages/IPython/core/interactiveshell.py\x1b"
                    "[0m in \x1b[0;36mrun_cell_magic\x1b[1;34m(self, "
                    "magic_name, line, cell)\x1b[0m\n\x1b[0;32m   2389"
                    "\x1b[0m             \x1b[1;32mwith\x1b[0m \x1b"
                    "[0mself\x1b[0m\x1b[1;33m.\x1b[0m\x1b[0mbuiltin_tra"
                    "p\x1b[0m\x1b[1;33m:\x1b[0m\x1b[1;33m\x1b[0m\x1b"
                    "[1;33m\x1b[0m\x1b[0m\n\x1b[0;32m   2390\x1b[0m    "
                    "             \x1b[0margs\x1b[0m \x1b[1;33m=\x1b[0m"
                    " \x1b[1;33m(\x1b[0m\x1b[0mmagic_arg_s\x1b[0m\x1b"
                    "[1;33m,\x1b[0m \x1b[0mcell\x1b[0m\x1b[1;33m)\x1b"
                    "[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\n\x1b"
                    "[1;32m-> 2391\x1b[1;33m                 \x1b"
                    "[0mresult\x1b[0m \x1b[1;33m=\x1b[0m \x1b[0mfn\x1b"
                    "[0m\x1b[1;33m(\x1b[0m\x1b[1;33m*\x1b[0m\x1b[0margs"
                    "\x1b[0m\x1b[1;33m,\x1b[0m \x1b[1;33m**\x1b[0m\x1b"
                    "[0mkwargs\x1b[0m\x1b[1;33m)\x1b[0m\x1b[1;33m\x1b"
                    "[0m\x1b[1;33m\x1b[0m\x1b[0m\n\x1b[0m\x1b[0;32m   "
                    "2392\x1b[0m             \x1b[1;32mreturn\x1b[0m "
                    "\x1b[0mresult\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m"
                    "\x1b[0m\x1b[0m\n\x1b[0;32m   2393\x1b[0m "
                    "\x1b[1;33m\x1b[0m\x1b[0m\n",
                    "\x1b[1;32m~/.pyenv/versions/scratch/lib/python3.8/"
                    "site-packages/IPython/core/magics/script.py\x1b[0m"
                    " in \x1b[0;36mnamed_script_magic\x1b[1;34m(line,"
                    " cell)\x1b[0m\n\x1b[0;32m    140\x1b[0m          "
                    "   \x1b[1;32melse\x1b[0m\x1b[1;33m:\x1b[0m\x1b"
                    "[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\n\x1b[0;32m"
                    "    141\x1b[0m                 \x1b[0mline\x1b[0m"
                    " \x1b[1;33m=\x1b[0m \x1b[0mscript\x1b[0m\x1b[1;33m"
                    "\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\n\x1b[1;32m--> 142"
                    "\x1b[1;33m             \x1b[1;32mreturn\x1b[0m"
                    " \x1b[0mself\x1b[0m\x1b[1;33m.\x1b[0m\x1b"
                    "[0mshebang\x1b[0m\x1b[1;33m(\x1b[0m\x1b[0mline\x1b"
                    "[0m\x1b[1;33m,\x1b[0m \x1b[0mcell\x1b[0m\x1b"
                    "[1;33m)\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m"
                    "\x1b[0m\n\x1b[0m\x1b[0;32m    143\x1b[0m \x1b"
                    "[1;33m\x1b[0m\x1b[0m\n\x1b[0;32m    144\x1b[0m    "
                    "     \x1b[1;31m# write a basic docstring:\x1b[0m"
                    "\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b"
                    "[0m\x1b[0m\n",
                    "\x1b[1;32m<decorator-gen-103>\x1b[0m in \x1b[0;36m"
                    "shebang\x1b[1;34m(self, line, cell)\x1b[0m\n",
                    "\x1b[1;32m~/.pyenv/versions/scratch/lib/python3.8"
                    "/site-packages/IPython/core/magic.py\x1b[0m in "
                    "\x1b[0;36m<lambda>\x1b[1;34m(f, *a, **k)\x1b[0m\n"
                    "\x1b[0;32m    185\x1b[0m     \x1b[1;31m# but it's"
                    " overkill for just that one bit of state.\x1b[0m"
                    "\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b"
                    "[0m\x1b[0m\n\x1b[0;32m    186\x1b[0m     \x1b[1;32"
                    "mdef\x1b[0m \x1b[0mmagic_deco\x1b[0m\x1b[1;33m("
                    "\x1b[0m\x1b[0marg\x1b[0m\x1b[1;33m)\x1b[0m\x1b"
                    "[1;33m:\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m"
                    "\x1b[0m\n\x1b[1;32m--> 187\x1b[1;33m         \x1b"
                    "[0mcall\x1b[0m \x1b[1;33m=\x1b[0m \x1b[1;32mlambda"
                    "\x1b[0m \x1b[0mf\x1b[0m\x1b[1;33m,\x1b[0m \x1b"
                    "[1;33m*\x1b[0m\x1b[0ma\x1b[0m\x1b[1;33m,\x1b[0m "
                    "\x1b[1;33m**\x1b[0m\x1b[0mk\x1b[0m\x1b[1;33m:"
                    "\x1b[0m \x1b[0mf\x1b[0m\x1b[1;33m(\x1b[0m\x1b"
                    "[1;33m*\x1b[0m\x1b[0ma\x1b[0m\x1b[1;33m,\x1b[0m "
                    "\x1b[1;33m**\x1b[0m\x1b[0mk\x1b[0m\x1b[1;33m)\x1b"
                    "[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\n\x1b"
                    "[0m\x1b[0;32m    188\x1b[0m \x1b[1;33m\x1b[0m\x1b"
                    "[0m\n\x1b[0;32m    189\x1b[0m         \x1b[1;32mif"
                    "\x1b[0m \x1b[0mcallable\x1b[0m\x1b[1;33m(\x1b[0m"
                    "\x1b[0marg\x1b[0m\x1b[1;33m)\x1b[0m\x1b[1;33m:\x1b"
                    "[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\n",
                    "\x1b[1;32m~/.pyenv/versions/scratch/lib/python3.8"
                    "/site-packages/IPython/core/magics/script.py\x1b"
                    "[0m in \x1b[0;36mshebang\x1b[1;34m(self, line, "
                    "cell)\x1b[0m\n\x1b[0;32m    243\x1b[0m            "
                    " \x1b[0msys\x1b[0m\x1b[1;33m.\x1b[0m\x1b[0mstderr"
                    "\x1b[0m\x1b[1;33m.\x1b[0m\x1b[0mflush\x1b[0m\x1b"
                    "[1;33m(\x1b[0m\x1b[1;33m)\x1b[0m\x1b[1;33m\x1b[0m"
                    "\x1b[1;33m\x1b[0m\x1b[0m\n\x1b[0;32m    244\x1b[0m"
                    "         \x1b[1;32mif\x1b[0m \x1b[0margs\x1b[0m"
                    "\x1b[1;33m.\x1b[0m\x1b[0mraise_error\x1b[0m \x1b"
                    "[1;32mand\x1b[0m \x1b[0mp\x1b[0m\x1b[1;33m.\x1b[0m"
                    "\x1b[0mreturncode\x1b[0m\x1b[1;33m!=\x1b[0m\x1b"
                    "[1;36m0\x1b[0m\x1b[1;33m:\x1b[0m\x1b[1;33m\x1b[0m"
                    "\x1b[1;33m\x1b[0m\x1b[0m\n\x1b[1;32m--> 245\x1b"
                    "[1;33m             \x1b[1;32mraise\x1b[0m \x1b[0m"
                    "CalledProcessError\x1b[0m\x1b[1;33m(\x1b[0m\x1b"
                    "[0mp\x1b[0m\x1b[1;33m.\x1b[0m\x1b[0mreturncode\x1b"
                    "[0m\x1b[1;33m,\x1b[0m \x1b[0mcell\x1b[0m\x1b[1;33m"
                    ",\x1b[0m \x1b[0moutput\x1b[0m\x1b[1;33m=\x1b[0m"
                    "\x1b[0mout\x1b[0m\x1b[1;33m,\x1b[0m \x1b[0mstderr"
                    "\x1b[0m\x1b[1;33m=\x1b[0m\x1b[0merr\x1b[0m\x1b"
                    "[1;33m)\x1b[0m\x1b[1;33m\x1b[0m\x1b[1;33m\x1b[0m"
                    "\x1b[0m\n\x1b[0m\x1b[0;32m    246\x1b[0m \x1b"
                    "[1;33m\x1b[0m\x1b[0m\n\x1b[0;32m    247\x1b[0m    "
                    " \x1b[1;32mdef\x1b[0m \x1b[0m_run_script\x1b[0m"
                    "\x1b[1;33m(\x1b[0m\x1b[0mself\x1b[0m\x1b[1;33m,"
                    "\x1b[0m \x1b[0mp\x1b[0m\x1b[1;33m,\x1b[0m \x1b"
                    "[0mcell\x1b[0m\x1b[1;33m,\x1b[0m \x1b[0mto_close"
                    "\x1b[0m\x1b[1;33m)\x1b[0m\x1b[1;33m:\x1b[0m\x1b"
                    "[1;33m\x1b[0m\x1b[1;33m\x1b[0m\x1b[0m\n",
                    "\x1b[1;31mCalledProcessError\x1b[0m: Command "
                    "'b'ech\\n'' returned non-zero exit status 127.",
                ],
            },
        ],
        "source": "%%bash\nech",
    }
    expected_output = (
        "     ╭──────────────────────────────────"
        "───────────────────────────────────────╮"
        "\n\x1b[38;5;247m[4]:\x1b[0m │ \x1b[49m%%\x1b[0m\x1b[94;4"
        "9mbash\x1b[0m                              "
        "                                    │\n  "
        "   │ \x1b[49mech\x1b[0m                       "
        "                                        "
        "      │\n     │                          "
        "                                        "
        "       │\n     ╰─────────────────────────"
        "────────────────────────────────────────"
        "────────╯\n                              "
        "                                        "
        "          \n      \x1b[38;5;237;48;5;174mbas"
        "h: line 1: ech: command not found       "
        "                               \x1b[0m\n    "
        "  \x1b[38;5;237;48;5;174m                  "
        "                                        "
        "                \x1b[0m\n                   "
        "                                        "
        "                     \n      \x1b[1;31m-----"
        "----------------------------------------"
        "----------------------------…\x1b[0m\n      "
        "\x1b[1;31mCalledProcessError\x1b[0m           "
        "             Traceback (most recent call"
        "     \n      last)                       "
        "                                        "
        "      \n      \x1b[1;32m<ipython-input-4-4fb"
        "31ecfb364>\x1b[0m in \x1b[36m<module>\x1b[0m     "
        "                           \n      \x1b[1;32"
        "m----> 1\x1b[0m\x1b[1;33m \x1b[0mget_ipython\x1b[1;3"
        "3m(\x1b[0m\x1b[1;33m)\x1b[0m\x1b[1;33m.\x1b[0mrun_cell_"
        "magic\x1b[1;33m(\x1b[0m\x1b[1;34m'bash'\x1b[0m\x1b[1;33"
        "m,\x1b[0m \x1b[1;34m''\x1b[0m\x1b[1;33m,\x1b[0m \x1b[1;34m"
        "'ech\\n'\x1b[0m\x1b[1;33m)\x1b[0m                 "
        "\n                                       "
        "                                        "
        " \n      \x1b[1;32m~/.pyenv/versions/scratch"
        "/lib/python3.8/site-packages/IPython/cor"
        "e/intera…\x1b[0m\n      in \x1b[36mrun_cell_mag"
        "ic\x1b[0m\x1b[1;34m(self, magic_name, line, ce"
        "ll)\x1b[0m                           \n     "
        " \x1b[32m   2389\x1b[0m             \x1b[1;32mwit"
        "h\x1b[0m self\x1b[1;33m.\x1b[0mbuiltin_trap\x1b[1;33"
        "m:\x1b[0m                               \n  "
        "    \x1b[32m   2390\x1b[0m                 arg"
        "s \x1b[1;33m=\x1b[0m \x1b[1;33m(\x1b[0mmagic_arg_s\x1b["
        "1;33m,\x1b[0m cell\x1b[1;33m)\x1b[0m             "
        "           \n      \x1b[1;32m-> 2391\x1b[0m\x1b[1;"
        "33m                 \x1b[0mresult \x1b[1;33m=\x1b"
        "[0m fn\x1b[1;33m(\x1b[0m\x1b[1;33m*\x1b[0margs\x1b[1;33"
        "m,\x1b[0m \x1b[1;33m**\x1b[0mkwargs\x1b[1;33m)\x1b[0m  "
        "                    \n      \x1b[32m   2392\x1b"
        "[0m             \x1b[1;32mreturn\x1b[0m result"
        "                                        "
        " \n      \x1b[32m   2393\x1b[0m                "
        "                                        "
        "           \n                            "
        "                                        "
        "            \n      \x1b[1;32m~/.pyenv/versi"
        "ons/scratch/lib/python3.8/site-packages/"
        "IPython/core/magics…\x1b[0m\n      in \x1b[36mn"
        "amed_script_magic\x1b[0m\x1b[1;34m(line, cell)"
        "\x1b[0m                                    "
        "     \n      \x1b[32m    140\x1b[0m            "
        " \x1b[1;32melse\x1b[0m\x1b[1;33m:\x1b[0m            "
        "                                     \n  "
        "    \x1b[32m    141\x1b[0m                 lin"
        "e \x1b[1;33m=\x1b[0m script                   "
        "                  \n      \x1b[1;32m--> 142\x1b"
        "[0m\x1b[1;33m             \x1b[0m\x1b[1;32mreturn"
        "\x1b[0m self\x1b[1;33m.\x1b[0mshebang\x1b[1;33m(\x1b[0m"
        "line\x1b[1;33m,\x1b[0m cell\x1b[1;33m)\x1b[0m       "
        "                \n      \x1b[32m    143\x1b[0m "
        "                                        "
        "                          \n      \x1b[32m  "
        "  144\x1b[0m         \x1b[1;31m# write a basic"
        " docstring:\x1b[0m                         "
        "       \n                                "
        "                                        "
        "        \n      \x1b[1;32m<decorator-gen-103"
        ">\x1b[0m in \x1b[36mshebang\x1b[0m\x1b[1;34m(self, l"
        "ine, cell)\x1b[0m                          "
        "\n                                       "
        "                                        "
        " \n      \x1b[1;32m~/.pyenv/versions/scratch"
        "/lib/python3.8/site-packages/IPython/cor"
        "e/magic.…\x1b[0m\n      in \x1b[36m<lambda>\x1b[0m"
        "\x1b[1;34m(f, *a, **k)\x1b[0m                 "
        "                                  \n     "
        " \x1b[32m    185\x1b[0m     \x1b[1;31m# but it's "
        "overkill for just that one bit of state."
        "\x1b[0m           \n      \x1b[32m    186\x1b[0m  "
        "   \x1b[1;32mdef\x1b[0m magic_deco\x1b[1;33m(\x1b[0m"
        "arg\x1b[1;33m)\x1b[0m\x1b[1;33m:\x1b[0m             "
        "                             \n      \x1b[1;"
        "32m--> 187\x1b[0m\x1b[1;33m         \x1b[0mcall \x1b"
        "[1;33m=\x1b[0m \x1b[1;32mlambda\x1b[0m f\x1b[1;33m,\x1b"
        "[0m \x1b[1;33m*\x1b[0ma\x1b[1;33m,\x1b[0m \x1b[1;33m**\x1b"
        "[0mk\x1b[1;33m:\x1b[0m f\x1b[1;33m(\x1b[0m\x1b[1;33m*\x1b["
        "0ma\x1b[1;33m,\x1b[0m \x1b[1;33m**\x1b[0mk\x1b[1;33m)\x1b["
        "0m                      \n      \x1b[32m    "
        "188\x1b[0m                                 "
        "                                  \n     "
        " \x1b[32m    189\x1b[0m         \x1b[1;32mif\x1b[0m "
        "callable\x1b[1;33m(\x1b[0marg\x1b[1;33m)\x1b[0m\x1b[1;3"
        "3m:\x1b[0m                                 "
        "        \n                               "
        "                                        "
        "         \n      \x1b[1;32m~/.pyenv/versions"
        "/scratch/lib/python3.8/site-packages/IPy"
        "thon/core/magics…\x1b[0m\n      in \x1b[36msheb"
        "ang\x1b[0m\x1b[1;34m(self, line, cell)\x1b[0m    "
        "                                        "
        "  \n      \x1b[32m    243\x1b[0m             sy"
        "s\x1b[1;33m.\x1b[0mstderr\x1b[1;33m.\x1b[0mflush\x1b[1;"
        "33m(\x1b[0m\x1b[1;33m)\x1b[0m                    "
        "                \n      \x1b[32m    244\x1b[0m "
        "        \x1b[1;32mif\x1b[0m args\x1b[1;33m.\x1b[0mra"
        "ise_error \x1b[1;32mand\x1b[0m p\x1b[1;33m.\x1b[0mre"
        "turncode\x1b[1;33m!=\x1b[0m\x1b[1;36m0\x1b[0m\x1b[1;33m"
        ":\x1b[0m                  \n      \x1b[1;32m-->"
        " 245\x1b[0m\x1b[1;33m             \x1b[0m\x1b[1;32mr"
        "aise\x1b[0m CalledProcessError\x1b[1;33m(\x1b[0mp"
        "\x1b[1;33m.\x1b[0mreturncode\x1b[1;33m,\x1b[0m cell\x1b"
        "[1;33m,\x1b[0m          \n      output\x1b[1;33"
        "m=\x1b[0mout\x1b[1;33m,\x1b[0m stderr\x1b[1;33m=\x1b[0m"
        "err\x1b[1;33m)\x1b[0m                         "
        "                          \n      \x1b[32m  "
        "  246\x1b[0m                               "
        "                                    \n   "
        "   \x1b[32m    247\x1b[0m     \x1b[1;32mdef\x1b[0m _"
        "run_script\x1b[1;33m(\x1b[0mself\x1b[1;33m,\x1b[0m p"
        "\x1b[1;33m,\x1b[0m cell\x1b[1;33m,\x1b[0m to_close\x1b["
        "1;33m)\x1b[0m\x1b[1;33m:\x1b[0m                  "
        "   \n                                    "
        "                                        "
        "    \n      \x1b[1;31mCalledProcessError\x1b[0m"
        ": Command 'b'ech\\n'' returned non-zero e"
        "xit status 127. \n"
    )
    output = rich_notebook_output(traceback_cell)
    assert output == expected_output


def test_render_result(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(output_cell)
    assert output == expected_output


def test_render_unknown_data_format(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(output_cell)
    assert output == expected_output


def test_render_error_no_traceback(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(traceback_cell)
    assert output == expected_output


def test_render_markdown_output(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(markdown_output_cell)
    assert output == expected_output


def test_render_unknown_display_data(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(unknown_display_data_cell)
    assert output == expected_output


def test_render_json_output(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(json_output_cell)
    assert output == expected_output


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


def test_render_text_display_data(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(text_display_data_cell)
    assert output == expected_output


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


def test_pdf_no_unicode_no_nerd(rich_notebook_output: RichOutput) -> None:
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
    output = rich_notebook_output(pdf_output_cell, nerd_font=False, unicode=False)
    assert output == expected_output


def test_vega_output(
    rich_notebook_output: RichOutput,
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
        f"58.012196-350876;file://{tempfile_path}0.html\x1b\\\x1b[94m\uf080"
        " Click to v"
        "iew Vega chart\x1b[0m\x1b]8;;\x1b\\               "
        "                                 \n"
    )
    output = rich_notebook_output(
        vega_output_cell,
        nerd_font=True,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_vegalite_output(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
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
    get_tempfile_path: Callable[[str], Path],
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
    get_tempfile_path: Callable[[str], Path],
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
        f"55.127551-234092;file://{tempfile_path}0.html\x1b\\\x1b[94mClick to vie"
        "w Vega chart\x1b[0m\x1b]8;;\x1b\\                 "
        "                                 \n"
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
    get_tempfile_path: Callable[[str], Path],
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
    tempfile_path = get_tempfile_path("")
    tempfile_directory = tempfile_path.parent
    for file in tempfile_directory.glob(f"{tempfile_path.stem}*.html"):
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
        f"35.10625-550844;file://{tempfile_path}0.html\x1b\\\x1b[94mVega"
        " chart\x1b[0"
        "m\x1b]8;;\x1b\\                                "
        "                                \n"
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
    get_tempfile_path: Callable[[str], Path],
    adjust_for_fallback: Callable[[str, int], str],
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
    tempfile_path = f"📊 file://{get_tempfile_path('')}0.html"
    line_width = 80 - 6
    if line_width - 1 < len(tempfile_path) < line_width + 2:
        first_line, second_line = tempfile_path.split(maxsplit=1)
        wrapped_file_path = "\n".join(
            (f"{'':>6}{first_line:<73}", f"{'':>6}{second_line:<74}")
        )
    else:
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
    )
    adjusted_expected_output = adjust_for_fallback(expected_output, 0)
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=False,
        hide_hyperlink_hints=True,
        unicode=True,
    )
    assert output.rstrip() == adjusted_expected_output.rstrip()


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
    output = rich_notebook_output(
        vegalite_output_cell,
        nerd_font=False,
        files=True,
        hyperlinks=True,
        hide_hyperlink_hints=False,
        unicode=False,
    )
    assert output == expected_output


def test_render_html(
    rich_notebook_output: RichOutput,
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


def test_render_unknown_data_type(rich_notebook_output: RichOutput) -> None:
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


@pytest.mark.skipif(
    "terminedia" not in sys.modules,
    reason="terminedia is used to draw the images using block"
    " characters, and is not importable on some systems due to a"
    " dependency on fcntl.",
)
def test_render_block_image(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
    disable_capture: ContextManager[_PluggyPlugin],
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
    tempfile_path = get_tempfile_path("")
    with disable_capture:
        output = rich_notebook_output(image_cell, images=True, image_drawing="block")
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
        f"  \x1b]8;id=857429;file://{tempfile_path}0.png\x1b\\\x1b"
        "[94m🖼 Click to vie"
        "w Image\x1b[0m\x1b]8;;\x1b\\                      "
        "                               \n        "
        "                                        "
        "                                \n      \x1b"
        "[39;49m███████\x1b[0m\x1b[38;2;255;255;255;48;"
        "2;0;0;0m▄\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "███\x1b[0m\x1b[38;2;248;248;248;48;2;255;255;2"
        "55m▄\x1b[0m\x1b[38;2;253;253;253;48;2;255;255;"
        "255m▄\x1b[0m\x1b[38;2;255;255;255;49m█████████"
        "\x1b[0m\x1b[38;2;253;253;253;48;2;255;255;255m"
        "▄\x1b[0m\x1b[38;2;250;250;250;48;2;255;255;255"
        "m▄\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b["
        "0m\x1b[38;2;250;250;250;48;2;255;255;255m▄\x1b"
        "[0m\x1b[38;2;252;252;252;48;2;255;255;255m▄"
        "\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b[0m"
        "\x1b[38;2;247;247;247;48;2;255;255;255m▄\x1b[0"
        "m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[3"
        "8;2;252;252;252;48;2;255;255;255m▄\x1b[0m\x1b["
        "38;2;250;250;250;48;2;255;255;255m▄\x1b[0m\x1b"
        "[38;2;255;255;255;49m████████\x1b[0m\x1b[38;2;"
        "255;255;255;48;2;0;0;0m▄\x1b[0m \n      \x1b[38"
        ";2;0;0;0;49m█\x1b[0m\x1b[38;2;122;122;122;48;2"
        ";114;114;114m▄\x1b[0m\x1b[38;2;117;117;117;49m"
        "█\x1b[0m\x1b[38;2;116;116;116;48;2;117;117;117"
        "m▄\x1b[0m\x1b[38;2;115;115;115;48;2;117;117;11"
        "7m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;249;"
        "249;249;48;2;255;255;255m▄\x1b[0m\x1b[38;2;248"
        ";248;248;48;2;255;255;255m▄\x1b[0m\x1b[38;2;24"
        "9;249;249;48;2;255;255;255m▄▄▄▄▄▄▄\x1b[0m\x1b["
        "38;2;243;243;243;48;2;252;252;252m▄\x1b[0m\x1b"
        "[38;2;247;247;247;48;2;255;255;255m▄\x1b[0m"
        "\x1b[38;2;249;249;249;48;2;255;255;255m▄▄▄▄"
        "▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;247;48;2;255;255"
        ";255m▄\x1b[0m\x1b[38;2;244;244;244;48;2;253;25"
        "3;253m▄\x1b[0m\x1b[38;2;249;249;249;48;2;255;2"
        "55;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;244;244;244;"
        "48;2;253;253;253m▄\x1b[0m\x1b[38;2;247;247;247"
        ";48;2;255;255;255m▄\x1b[0m\x1b[38;2;249;249;24"
        "9;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;"
        "243;243;243;48;2;251;251;251m▄\x1b[0m\x1b[38;2"
        ";249;249;249;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄"
        "\x1b[0m\x1b[38;2;246;246;246;48;2;255;255;255m"
        "▄\x1b[0m\x1b[38;2;243;243;244;48;2;253;253;253"
        "m▄\x1b[0m\x1b[38;2;248;248;249;48;2;255;255;25"
        "5m▄▄▄\x1b[0m\x1b[38;2;249;249;249;48;2;255;255"
        ";255m▄\x1b[0m\x1b[38;2;248;248;248;48;2;255;25"
        "5;255m▄\x1b[0m\x1b[38;2;246;246;246;48;2;255;2"
        "55;255m▄\x1b[0m\x1b[38;2;251;251;251;48;2;255;"
        "255;255m▄\x1b[0m\x1b[38;2;248;248;248;48;2;252"
        ";252;252m▄\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0"
        "m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;0;0"
        ";0;48;2;113;113;113m▄\x1b[0m\x1b[38;2;0;0;0;48"
        ";2;119;119;119m▄\x1b[0m\x1b[38;2;0;0;0;48;2;11"
        "6;116;116m▄\x1b[0m\x1b[38;2;0;0;0;48;2;109;109"
        ";109m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;2"
        "55;255;255;49m█████████\x1b[0m\x1b[38;2;248;24"
        "8;248;49m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0"
        "m\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b[38"
        ";2;253;253;253;48;2;254;254;254m▄\x1b[0m\x1b[3"
        "8;2;249;249;249;49m█\x1b[0m\x1b[38;2;255;255;2"
        "55;49m██████████\x1b[0m\x1b[38;2;249;249;249;4"
        "9m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2"
        ";255;255;255;49m██████████\x1b[0m\x1b[38;2;247"
        ";247;247;49m█\x1b[0m\x1b[38;2;255;255;255;49m█"
        "████████\x1b[0m\x1b[38;2;255;255;255;48;2;251;"
        "247;255m▄\x1b[0m\x1b[38;2;249;246;252;48;2;190"
        ";149;247m▄\x1b[0m\x1b[38;2;245;243;249;48;2;18"
        "0;134;244m▄\x1b[0m\x1b[38;2;251;249;255;48;2;1"
        "84;139;248m▄\x1b[0m\x1b[38;2;251;248;255;48;2;"
        "183;137;248m▄\x1b[0m\x1b[38;2;252;249;255;48;2"
        ";192;151;249m▄\x1b[0m\x1b[38;2;255;255;255;48;"
        "2;252;249;255m▄\x1b[0m\x1b[38;2;245;245;245;48"
        ";2;239;240;238m▄\x1b[0m\x1b[38;2;229;229;229;4"
        "8;2;207;207;207m▄\x1b[0m\x1b[38;2;255;255;255;"
        "49m███\x1b[0m \n      \x1b[38;2;0;0;0;49m██████"
        "█\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0m"
        "\x1b[38;2;248;248;248;49m█\x1b[0m\x1b[38;2;253;25"
        "3;253;49m█\x1b[0m\x1b[38;2;255;255;255;49m████"
        "█████\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38"
        ";2;249;249;249;49m█\x1b[0m\x1b[38;2;255;255;25"
        "5;49m██████████\x1b[0m\x1b[38;2;249;249;249;49"
        "m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2;"
        "255;255;255;49m██████████\x1b[0m\x1b[38;2;247;"
        "247;247;49m█\x1b[0m\x1b[38;2;255;255;255;49m██"
        "███████\x1b[0m\x1b[38;2;252;254;254;48;2;255;2"
        "55;255m▄\x1b[0m\x1b[38;2;220;240;242;48;2;255;"
        "254;253m▄\x1b[0m\x1b[38;2;213;236;238;48;2;253"
        ";251;250m▄\x1b[0m\x1b[38;2;218;242;243;48;2;25"
        "5;255;255m▄\x1b[0m\x1b[38;2;218;241;243;48;2;2"
        "55;255;255m▄\x1b[0m\x1b[38;2;222;243;244;48;2;"
        "255;255;255m▄\x1b[0m\x1b[38;2;253;255;255;48;2"
        ";255;255;255m▄\x1b[0m\x1b[38;2;236;236;236;48;"
        "2;255;255;255m▄\x1b[0m\x1b[38;2;232;232;232;48"
        ";2;255;255;255m▄\x1b[0m\x1b[38;2;255;255;255;4"
        "9m███\x1b[0m \n      \x1b[38;2;0;0;0;49m███████"
        "\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b"
        "[38;2;248;248;248;49m█\x1b[0m\x1b[38;2;253;253"
        ";253;49m█\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "████\x1b[0m\x1b[38;2;254;254;254;48;2;253;253;"
        "253m▄\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38"
        ";2;255;255;255;49m██████████\x1b[0m\x1b[38;2;2"
        "49;249;249;49m█\x1b[0m\x1b[38;2;252;252;252;49"
        "m█\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b["
        "0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[38;2;255;"
        "255;255;49m█████████\x1b[0m\x1b[38;2;255;255;2"
        "55;48;2;248;252;253m▄\x1b[0m\x1b[38;2;255;255;"
        "255;48;2;166;221;224m▄\x1b[0m\x1b[38;2;255;252"
        ";252;48;2;152;215;219m▄\x1b[0m\x1b[38;2;255;25"
        "5;255;48;2;157;219;223m▄\x1b[0m\x1b[38;2;255;2"
        "55;255;48;2;156;219;222m▄\x1b[0m\x1b[38;2;255;"
        "255;255;48;2;168;223;226m▄\x1b[0m\x1b[38;2;255"
        ";255;255;48;2;250;254;254m▄\x1b[0m\x1b[38;2;25"
        "2;252;252;48;2;233;233;233m▄\x1b[0m\x1b[38;2;2"
        "47;247;247;48;2;209;209;209m▄\x1b[0m\x1b[38;2;"
        "255;255;255;49m███\x1b[0m \n      \x1b[38;2;0;0"
        ";0;49m█\x1b[0m\x1b[38;2;106;106;106;48;2;121;1"
        "21;121m▄\x1b[0m\x1b[38;2;118;118;118;48;2;117;"
        "117;117m▄\x1b[0m\x1b[38;2;115;115;115;48;2;119"
        ";119;119m▄\x1b[0m\x1b[38;2;116;116;116;48;2;11"
        "4;114;114m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[3"
        "8;2;255;255;255;48;2;249;249;249m▄\x1b[0m\x1b["
        "38;2;251;251;251;48;2;249;249;249m▄\x1b[0m\x1b"
        "[38;2;252;252;252;48;2;250;250;250m▄▄▄▄▄"
        "▄▄\x1b[0m\x1b[38;2;245;245;245;48;2;244;244;24"
        "4m▄\x1b[0m\x1b[38;2;250;250;250;48;2;248;248;2"
        "48m▄\x1b[0m\x1b[38;2;252;252;252;48;2;250;250;"
        "250m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;250;250;250;48;2"
        ";248;248;248m▄\x1b[0m\x1b[38;2;246;246;246;48;"
        "2;245;245;245m▄\x1b[0m\x1b[38;2;252;252;252;48"
        ";2;250;250;250m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;246;"
        "246;246;48;2;245;245;245m▄\x1b[0m\x1b[38;2;249"
        ";249;249;48;2;247;247;247m▄\x1b[0m\x1b[38;2;25"
        "2;252;252;48;2;250;250;250m▄▄▄▄▄▄▄▄▄▄\x1b[0"
        "m\x1b[38;2;245;245;245;48;2;243;243;243m▄\x1b["
        "0m\x1b[38;2;252;252;252;48;2;250;250;250m▄▄"
        "▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;249;249;249;48;2;247;"
        "247;247m▄\x1b[0m\x1b[38;2;246;246;246;48;2;245"
        ";245;245m▄\x1b[0m\x1b[38;2;252;252;252;48;2;25"
        "0;250;250m▄▄▄▄▄\x1b[0m\x1b[38;2;252;252;252;48"
        ";2;251;251;251m▄\x1b[0m\x1b[38;2;253;253;253;4"
        "8;2;252;252;252m▄\x1b[0m\x1b[38;2;251;251;251;"
        "48;2;248;248;248m▄\x1b[0m\x1b[38;2;255;255;255"
        ";49m█\x1b[0m \n      \x1b[38;2;0;0;0;49m██\x1b[0m\x1b"
        "[38;2;0;0;0;48;2;102;102;102m▄\x1b[0m\x1b[38;2"
        ";0;0;0;48;2;127;127;127m▄▄\x1b[0m\x1b[38;2;0;0"
        ";0;49m██\x1b[0m\x1b[38;2;255;255;255;49m██████"
        "███\x1b[0m\x1b[38;2;248;248;248;49m█\x1b[0m\x1b[38;2"
        ";253;253;253;49m█\x1b[0m\x1b[38;2;255;255;255;"
        "49m█████████\x1b[0m\x1b[38;2;253;253;253;49m█\x1b"
        "[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;255"
        ";255;255;49m██████████\x1b[0m\x1b[38;2;249;249"
        ";249;49m█\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m"
        "\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[38"
        ";2;247;247;247;49m█\x1b[0m\x1b[38;2;255;255;25"
        "5;49m██████████\x1b[0m\x1b[38;2;252;252;252;49"
        "m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;"
        "255;255;255;49m█████████\x1b[0m \n      \x1b[38"
        ";2;0;0;0;49m███████\x1b[0m\x1b[38;2;255;255;25"
        "5;49m█████████\x1b[0m\x1b[38;2;248;248;248;49m"
        "█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;2"
        "55;255;255;49m█████████\x1b[0m\x1b[38;2;253;25"
        "3;253;49m█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0"
        "m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b[3"
        "8;2;249;249;249;49m█\x1b[0m\x1b[38;2;252;252;2"
        "52;49m█\x1b[0m\x1b[38;2;255;255;255;49m███████"
        "███\x1b[0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[38;2"
        ";255;255;255;49m██████████\x1b[0m\x1b[38;2;252"
        ";252;252;49m█\x1b[0m\x1b[38;2;249;249;249;49m█"
        "\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0m "
        "\n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;127;1"
        "27;127;48;2;0;0;0m▄▄\x1b[0m\x1b[38;2;109;109;1"
        "09;48;2;0;0;0m▄▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b["
        "0m\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b[3"
        "8;2;248;248;248;49m█\x1b[0m\x1b[38;2;253;253;2"
        "53;49m█\x1b[0m\x1b[38;2;255;255;255;49m███████"
        "██\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;"
        "249;249;249;49m█\x1b[0m\x1b[38;2;255;255;255;4"
        "9m██████████\x1b[0m\x1b[38;2;249;249;249;49m█\x1b"
        "[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2;255"
        ";255;255;49m██████████\x1b[0m\x1b[38;2;247;247"
        ";247;49m█\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "█████\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38"
        ";2;249;249;249;49m█\x1b[0m\x1b[38;2;255;255;25"
        "5;49m█████████\x1b[0m \n      \x1b[38;2;0;0;0;4"
        "9m█\x1b[0m\x1b[38;2;102;102;102;48;2;115;115;1"
        "15m▄\x1b[0m\x1b[38;2;117;117;117;49m█\x1b[0m\x1b[38;"
        "2;118;118;118;48;2;117;117;117m▄\x1b[0m\x1b[38"
        ";2;113;113;113;48;2;115;115;115m▄\x1b[0m\x1b[3"
        "8;2;0;0;0;49m██\x1b[0m\x1b[38;2;255;255;255;48"
        ";2;249;249;249m▄\x1b[0m\x1b[38;2;255;255;255;4"
        "8;2;246;246;246m▄\x1b[0m\x1b[38;2;255;255;255;"
        "48;2;248;248;248m▄\x1b[0m\x1b[38;2;255;255;255"
        ";48;2;247;247;247m▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;2"
        "48;248;48;2;242;242;242m▄\x1b[0m\x1b[38;2;253;"
        "253;253;48;2;246;246;246m▄\x1b[0m\x1b[38;2;255"
        ";255;255;48;2;247;247;247m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b"
        "[38;2;253;253;253;48;2;246;246;246m▄\x1b[0m"
        "\x1b[38;2;249;249;249;48;2;243;243;243m▄\x1b[0"
        "m\x1b[38;2;255;255;255;48;2;247;247;247m▄▄▄"
        "▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;249;249;249;48;2;243;2"
        "43;243m▄\x1b[0m\x1b[38;2;252;252;252;48;2;245;"
        "245;245m▄\x1b[0m\x1b[38;2;255;255;255;48;2;247"
        ";247;247m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;24"
        "7;48;2;242;242;242m▄\x1b[0m\x1b[38;2;255;255;2"
        "55;48;2;247;247;247m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2"
        ";252;252;252;48;2;245;245;245m▄\x1b[0m\x1b[38;"
        "2;249;249;249;48;2;243;243;243m▄\x1b[0m\x1b[38"
        ";2;255;255;255;48;2;247;247;247m▄▄▄▄▄▄\x1b["
        "0m\x1b[38;2;255;255;255;48;2;250;250;250m▄\x1b"
        "[0m\x1b[38;2;255;255;255;48;2;246;246;246m▄"
        "\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0m \n      \x1b"
        "[38;2;0;0;0;49m███████\x1b[0m\x1b[38;2;255;255"
        ";255;49m█████████\x1b[0m\x1b[38;2;248;248;248;"
        "49m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;"
        "2;255;255;255;49m█████████\x1b[0m\x1b[38;2;253"
        ";253;253;49m█\x1b[0m\x1b[38;2;249;249;249;49m█"
        "\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b[0m"
        "\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;252;25"
        "2;252;49m█\x1b[0m\x1b[38;2;255;255;255;49m████"
        "██████\x1b[0m\x1b[38;2;247;247;247;49m█\x1b[0m\x1b[3"
        "8;2;255;255;255;49m██████████\x1b[0m\x1b[38;2;"
        "252;252;252;49m█\x1b[0m\x1b[38;2;249;249;249;4"
        "9m█\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b["
        "0m \n      \x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[3"
        "8;2;255;255;255;49m█████████\x1b[0m\x1b[38;2;2"
        "48;248;248;49m█\x1b[0m\x1b[38;2;253;253;253;49"
        "m█\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0"
        "m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;249;2"
        "49;249;49m█\x1b[0m\x1b[38;2;255;255;255;49m███"
        "███████\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b["
        "38;2;252;252;252;49m█\x1b[0m\x1b[38;2;255;255;"
        "255;49m██████████\x1b[0m\x1b[38;2;247;247;247;"
        "49m█\x1b[0m\x1b[38;2;255;255;255;49m██████████"
        "\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2;24"
        "9;249;249;49m█\x1b[0m\x1b[38;2;255;255;255;49m"
        "█████████\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b["
        "0m\x1b[38;2;113;113;113;48;2;0;0;0m▄\x1b[0m\x1b[3"
        "8;2;118;118;118;48;2;0;0;0m▄\x1b[0m\x1b[38;2;1"
        "15;115;115;48;2;0;0;0m▄\x1b[0m\x1b[38;2;117;11"
        "7;117;48;2;0;0;0m▄\x1b[0m\x1b[38;2;0;0;0;49m██"
        "\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0m\x1b[38;2;25"
        "1;251;251;48;2;255;255;255m▄\x1b[0m\x1b[38;2;2"
        "52;252;252;48;2;255;255;255m▄▄▄▄▄▄▄\x1b[0m\x1b"
        "[38;2;246;246;246;48;2;248;248;248m▄\x1b[0m"
        "\x1b[38;2;251;251;251;48;2;253;253;253m▄\x1b[0"
        "m\x1b[38;2;252;252;252;48;2;255;255;255m▄▄▄"
        "▄▄▄▄▄▄\x1b[0m\x1b[38;2;250;250;250;48;2;253;25"
        "3;253m▄\x1b[0m\x1b[38;2;247;247;247;48;2;249;2"
        "49;249m▄\x1b[0m\x1b[38;2;252;252;252;48;2;255;"
        "255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;247"
        ";48;2;249;249;249m▄\x1b[0m\x1b[38;2;250;250;25"
        "0;48;2;252;252;252m▄\x1b[0m\x1b[38;2;252;252;2"
        "52;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2"
        ";245;245;245;48;2;247;247;247m▄\x1b[0m\x1b[38;"
        "2;252;252;252;48;2;255;255;255m▄▄▄▄▄▄▄▄▄"
        "▄\x1b[0m\x1b[38;2;250;250;250;48;2;252;252;252"
        "m▄\x1b[0m\x1b[38;2;247;247;247;48;2;249;249;24"
        "9m▄\x1b[0m\x1b[38;2;252;252;252;48;2;255;255;2"
        "55m▄▄▄▄▄▄\x1b[0m\x1b[38;2;253;253;253;48;2;255"
        ";255;255m▄\x1b[0m\x1b[38;2;252;252;252;48;2;25"
        "5;255;255m▄\x1b[0m\x1b[38;2;255;255;255;49m█\x1b["
        "0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;12"
        "7;127;127;48;2;120;120;120m▄\x1b[0m\x1b[38;2;1"
        "09;109;109;48;2;119;119;119m▄\x1b[0m\x1b[38;2;"
        "127;127;127;48;2;116;116;116m▄\x1b[0m\x1b[38;2"
        ";115;115;115;48;2;118;118;118m▄\x1b[0m\x1b[38;"
        "2;0;0;0;49m██\x1b[0m\x1b[38;2;255;255;255;48;2"
        ";249;249;249m▄\x1b[0m\x1b[38;2;255;255;255;48;"
        "2;248;248;248m▄\x1b[0m\x1b[38;2;255;255;255;48"
        ";2;249;249;249m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;248;248"
        ";248;48;2;243;243;243m▄\x1b[0m\x1b[38;2;254;25"
        "4;254;48;2;248;248;248m▄\x1b[0m\x1b[38;2;255;2"
        "55;255;48;2;249;249;249m▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[3"
        "8;2;254;254;254;48;2;247;247;247m▄\x1b[0m\x1b["
        "38;2;249;249;249;48;2;244;244;244m▄\x1b[0m\x1b"
        "[38;2;255;255;255;48;2;249;249;249m▄▄▄▄▄"
        "▄▄▄▄▄\x1b[0m\x1b[38;2;249;249;249;48;2;244;244"
        ";244m▄\x1b[0m\x1b[38;2;252;252;252;48;2;247;24"
        "7;247m▄\x1b[0m\x1b[38;2;255;255;255;48;2;249;2"
        "49;249m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;247;247;"
        "48;2;243;243;243m▄\x1b[0m\x1b[38;2;255;255;255"
        ";48;2;249;249;249m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;2"
        "52;252;252;48;2;247;247;247m▄\x1b[0m\x1b[38;2;"
        "249;249;249;48;2;244;244;244m▄\x1b[0m\x1b[38;2"
        ";255;255;255;48;2;249;249;249m▄▄▄▄▄▄\x1b[0m"
        "\x1b[38;2;255;255;255;48;2;251;251;251m▄\x1b[0"
        "m\x1b[38;2;255;255;255;48;2;248;248;248m▄\x1b["
        "0m\x1b[38;2;255;255;255;49m█\x1b[0m \n      \x1b[3"
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
        " \n      \x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[38;"
        "2;255;255;255;49m█████████\x1b[0m\x1b[38;2;248"
        ";248;248;49m█\x1b[0m\x1b[38;2;253;253;253;49m█"
        "\x1b[0m\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b"
        "[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;249;249"
        ";249;49m█\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "█████\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38"
        ";2;252;252;252;49m█\x1b[0m\x1b[38;2;255;255;25"
        "5;49m██████████\x1b[0m\x1b[38;2;247;247;247;49"
        "m█\x1b[0m\x1b[38;2;255;255;255;49m██████████\x1b["
        "0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2;249;"
        "249;249;49m█\x1b[0m\x1b[38;2;255;255;255;49m██"
        "███████\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m"
        "\x1b[38;2;116;116;116;48;2;127;127;127m▄\x1b[0"
        "m\x1b[38;2;119;119;119;48;2;127;127;127m▄\x1b["
        "0m\x1b[38;2;119;119;119;48;2;113;113;113m▄\x1b"
        "[0m\x1b[38;2;117;117;117;48;2;102;102;102m▄"
        "\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;249;249"
        ";249;48;2;255;255;255m▄\x1b[0m\x1b[38;2;247;24"
        "7;247;48;2;255;255;255m▄\x1b[0m\x1b[38;2;248;2"
        "48;248;48;2;255;255;255m▄▄▄▄▄▄▄\x1b[0m\x1b[38;"
        "2;242;242;242;48;2;248;248;248m▄\x1b[0m\x1b[38"
        ";2;247;247;247;48;2;253;253;253m▄\x1b[0m\x1b[3"
        "8;2;248;248;248;48;2;255;255;255m▄▄▄▄▄▄▄"
        "▄▄\x1b[0m\x1b[38;2;246;246;246;48;2;253;253;25"
        "3m▄\x1b[0m\x1b[38;2;243;243;243;48;2;249;249;2"
        "49m▄\x1b[0m\x1b[38;2;248;248;248;48;2;255;255;"
        "255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;243;243;243;48;"
        "2;249;249;249m▄\x1b[0m\x1b[38;2;246;246;246;48"
        ";2;252;252;252m▄\x1b[0m\x1b[38;2;248;248;248;4"
        "8;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;242"
        ";242;242;48;2;247;247;247m▄\x1b[0m\x1b[38;2;24"
        "8;248;248;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0"
        "m\x1b[38;2;246;246;246;48;2;252;252;252m▄\x1b["
        "0m\x1b[38;2;243;243;243;48;2;249;249;249m▄\x1b"
        "[0m\x1b[38;2;248;248;248;48;2;255;255;255m▄"
        "▄▄▄▄▄\x1b[0m\x1b[38;2;250;250;250;48;2;255;255"
        ";255m▄\x1b[0m\x1b[38;2;247;247;247;48;2;255;25"
        "5;255m▄\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0m \n"
        "      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2;0;0;0;"
        "48;2;127;127;127m▄\x1b[0m\x1b[38;2;0;0;0;48;2;"
        "120;120;120m▄\x1b[0m\x1b[38;2;85;85;85;48;2;11"
        "6;116;116m▄\x1b[0m\x1b[38;2;255;255;255;48;2;1"
        "14;114;114m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b["
        "38;2;255;255;255;49m█\x1b[0m\x1b[38;2;255;255;"
        "255;48;2;253;253;253m▄\x1b[0m\x1b[38;2;255;255"
        ";255;48;2;254;254;254m▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;"
        "248;248;248;48;2;247;247;247m▄\x1b[0m\x1b[38;2"
        ";253;253;253;48;2;252;252;252m▄\x1b[0m\x1b[38;"
        "2;255;255;255;48;2;254;254;254m▄▄▄▄▄▄▄▄▄"
        "\x1b[0m\x1b[38;2;253;253;253;48;2;252;252;252m"
        "▄\x1b[0m\x1b[38;2;249;249;249;48;2;248;248;248"
        "m▄\x1b[0m\x1b[38;2;255;255;255;48;2;254;254;25"
        "4m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;249;249;249;48;2;"
        "248;248;248m▄\x1b[0m\x1b[38;2;252;252;252;48;2"
        ";251;251;251m▄\x1b[0m\x1b[38;2;255;255;255;48;"
        "2;254;254;254m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;247;2"
        "47;247;48;2;246;246;246m▄\x1b[0m\x1b[38;2;255;"
        "255;255;48;2;254;254;254m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b"
        "[38;2;252;252;252;48;2;251;251;251m▄\x1b[0m"
        "\x1b[38;2;249;249;249;48;2;248;248;248m▄\x1b[0"
        "m\x1b[38;2;255;255;255;48;2;254;254;254m▄▄▄"
        "▄▄▄▄\x1b[0m\x1b[38;2;255;255;255;48;2;253;253;"
        "253m▄\x1b[0m\x1b[38;2;255;255;255;49m█\x1b[0m \n  "
        "    \x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[38;2;25"
        "5;255;255;49m█████████\x1b[0m\x1b[38;2;248;248"
        ";248;49m█\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m"
        "\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b[38;"
        "2;253;253;253;49m█\x1b[0m\x1b[38;2;249;249;249"
        ";49m█\x1b[0m\x1b[38;2;255;255;255;49m█████████"
        "█\x1b[0m\x1b[38;2;249;249;249;49m█\x1b[0m\x1b[38;2;2"
        "52;252;252;49m█\x1b[0m\x1b[38;2;255;255;255;49"
        "m██████████\x1b[0m\x1b[38;2;247;247;247;49m█\x1b["
        "0m\x1b[38;2;255;255;255;49m██████████\x1b[0m\x1b["
        "38;2;252;252;252;49m█\x1b[0m\x1b[38;2;249;249;"
        "249;49m█\x1b[0m\x1b[38;2;255;255;255;49m██████"
        "███\x1b[0m \n      \x1b[38;2;0;0;0;49m███████\x1b["
        "0m\x1b[38;2;255;255;255;49m█████████\x1b[0m\x1b[3"
        "8;2;248;248;248;49m█\x1b[0m\x1b[38;2;253;253;2"
        "53;49m█\x1b[0m\x1b[38;2;255;255;255;49m███████"
        "██\x1b[0m\x1b[38;2;253;253;253;49m█\x1b[0m\x1b[38;2;"
        "249;249;249;49m█\x1b[0m\x1b[38;2;255;255;255;4"
        "9m██████████\x1b[0m\x1b[38;2;249;249;249;49m█\x1b"
        "[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38;2;255"
        ";255;255;49m██████████\x1b[0m\x1b[38;2;247;247"
        ";247;49m█\x1b[0m\x1b[38;2;255;255;255;49m█████"
        "█████\x1b[0m\x1b[38;2;252;252;252;49m█\x1b[0m\x1b[38"
        ";2;249;249;249;49m█\x1b[0m\x1b[38;2;255;255;25"
        "5;49m█████████\x1b[0m \n      \x1b[38;2;0;0;0;4"
        "9m█\x1b[0m\x1b[38;2;121;121;121;48;2;115;115;1"
        "15m▄\x1b[0m\x1b[38;2;117;117;117;48;2;111;111;"
        "111m▄\x1b[0m\x1b[38;2;116;116;116;48;2;115;115"
        ";115m▄\x1b[0m\x1b[38;2;119;119;119;48;2;109;10"
        "9;109m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[38;2;"
        "249;249;249;48;2;255;255;255m▄\x1b[0m\x1b[38;2"
        ";247;247;247;48;2;253;253;253m▄\x1b[0m\x1b[38;"
        "2;248;248;248;48;2;254;254;254m▄▄▄▄▄▄▄\x1b["
        "0m\x1b[38;2;242;242;242;48;2;248;248;248m▄\x1b"
        "[0m\x1b[38;2;247;247;247;48;2;252;252;252m▄"
        "\x1b[0m\x1b[38;2;248;248;248;48;2;254;254;254m"
        "▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;246;246;246;48;2;252"
        ";252;252m▄\x1b[0m\x1b[38;2;243;243;243;48;2;24"
        "9;249;249m▄\x1b[0m\x1b[38;2;248;248;248;48;2;2"
        "54;254;254m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;243;243;"
        "243;48;2;249;249;249m▄\x1b[0m\x1b[38;2;246;246"
        ";246;48;2;251;251;251m▄\x1b[0m\x1b[38;2;248;24"
        "8;248;48;2;254;254;254m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[3"
        "8;2;242;242;242;48;2;247;247;247m▄\x1b[0m\x1b["
        "38;2;248;248;248;48;2;254;254;254m▄▄▄▄▄▄"
        "▄▄▄▄\x1b[0m\x1b[38;2;246;246;246;48;2;251;251;"
        "251m▄\x1b[0m\x1b[38;2;243;243;243;48;2;249;249"
        ";249m▄\x1b[0m\x1b[38;2;248;248;248;48;2;254;25"
        "4;254m▄▄▄▄▄▄\x1b[0m\x1b[38;2;250;250;250;48;2;"
        "255;255;255m▄\x1b[0m\x1b[38;2;247;247;247;48;2"
        ";253;253;253m▄\x1b[0m\x1b[38;2;255;255;255;49m"
        "█\x1b[0m \n      \x1b[38;2;0;0;0;49m█\x1b[0m\x1b[38;2"
        ";0;0;0;48;2;102;102;102m▄\x1b[0m\x1b[38;2;0;0;"
        "0;48;2;112;112;112m▄\x1b[0m\x1b[38;2;0;0;0;48;"
        "2;118;118;118m▄\x1b[0m\x1b[38;2;0;0;0;48;2;110"
        ";110;110m▄\x1b[0m\x1b[38;2;0;0;0;49m██\x1b[0m\x1b[38"
        ";2;180;180;180;48;2;249;249;249m▄\x1b[0m\x1b[3"
        "8;2;185;185;185;48;2;255;255;255m▄▄▄▄▄▄▄"
        "▄\x1b[0m\x1b[38;2;183;183;183;48;2;254;254;254"
        "m▄\x1b[0m\x1b[38;2;185;185;185;48;2;255;255;25"
        "5m▄▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;183;183;183;48;2"
        ";255;255;255m▄\x1b[0m\x1b[38;2;185;185;185;48;"
        "2;255;255;255m▄▄▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;183;1"
        "83;183;48;2;255;255;255m▄\x1b[0m\x1b[38;2;185;"
        "185;185;48;2;255;255;255m▄▄▄▄▄▄▄▄▄▄▄\x1b[0m"
        "\x1b[38;2;183;183;183;48;2;253;253;253m▄\x1b[0"
        "m\x1b[38;2;185;185;185;48;2;255;255;255m▄▄▄"
        "▄▄▄▄▄▄▄▄\x1b[0m\x1b[38;2;183;183;183;48;2;255;"
        "255;255m▄\x1b[0m\x1b[38;2;185;185;185;48;2;255"
        ";255;255m▄▄▄▄▄▄\x1b[0m\x1b[38;2;188;188;188;48"
        ";2;255;255;255m▄\x1b[0m\x1b[38;2;181;181;181;4"
        "8;2;249;249;249m▄\x1b[0m\x1b[38;2;113;113;113;"
        "48;2;255;255;255m▄\x1b[0m \n      \x1b[38;2;0;0"
        ";0;49m██████████████████████████████████"
        "███████████████████████████████████████\x1b"
        "[0m \n      \x1b[38;2;0;0;0;49m█████████████"
        "\x1b[0m\x1b[38;2;102;102;102;48;2;0;0;0m▄\x1b[0m\x1b"
        "[38;2;115;115;115;48;2;127;127;127m▄\x1b[0m"
        "\x1b[38;2;115;115;115;48;2;116;116;116m▄\x1b[0"
        "m\x1b[38;2;119;119;119;49m█\x1b[0m\x1b[38;2;116;1"
        "16;116;48;2;118;118;118m▄\x1b[0m\x1b[38;2;115;"
        "115;115;49m█\x1b[0m\x1b[38;2;114;114;114;48;2;"
        "111;111;111m▄\x1b[0m\x1b[38;2;0;0;0;49m█████\x1b["
        "0m\x1b[38;2;113;113;113;48;2;255;255;255m▄\x1b"
        "[0m\x1b[38;2;118;118;118;48;2;121;121;121m▄"
        "\x1b[0m\x1b[38;2;114;114;114;49m█\x1b[0m\x1b[38;2;11"
        "5;115;115;48;2;121;121;121m▄\x1b[0m\x1b[38;2;1"
        "16;116;116;49m█\x1b[0m\x1b[38;2;116;116;116;48"
        ";2;115;115;115m▄\x1b[0m\x1b[38;2;102;102;102;4"
        "8;2;85;85;85m▄\x1b[0m\x1b[38;2;0;0;0;49m█████\x1b"
        "[0m\x1b[38;2;120;120;120;48;2;111;111;111m▄"
        "\x1b[0m\x1b[38;2;117;117;117;48;2;115;115;115m"
        "▄\x1b[0m\x1b[38;2;115;115;115;48;2;114;114;114"
        "m▄\x1b[0m\x1b[38;2;115;115;115;48;2;116;116;11"
        "6m▄\x1b[0m\x1b[38;2;117;117;117;48;2;115;115;1"
        "15m▄\x1b[0m\x1b[38;2;127;127;127;48;2;255;255;"
        "255m▄\x1b[0m\x1b[38;2;0;0;0;49m██████\x1b[0m\x1b[38;"
        "2;115;115;115;48;2;120;120;120m▄\x1b[0m\x1b[38"
        ";2;117;117;117;48;2;114;114;114m▄\x1b[0m\x1b[3"
        "8;2;117;117;117;48;2;118;118;118m▄\x1b[0m\x1b["
        "38;2;115;115;115;49m█\x1b[0m\x1b[38;2;118;118;"
        "118;49m█\x1b[0m\x1b[38;2;0;0;0;49m██████\x1b[0m\x1b["
        "38;2;106;106;106;48;2;85;85;85m▄\x1b[0m\x1b[38"
        ";2;116;116;116;48;2;119;119;119m▄\x1b[0m\x1b[3"
        "8;2;117;117;117;48;2;116;116;116m▄\x1b[0m\x1b["
        "38;2;116;116;116;48;2;118;118;118m▄\x1b[0m\x1b"
        "[38;2;117;117;117;48;2;116;116;116m▄\x1b[0m"
        "\x1b[38;2;122;122;122;48;2;127;127;127m▄\x1b[0"
        "m\x1b[38;2;0;0;0;49m███████\x1b[0m \n      \x1b[38"
        ";2;0;0;0;49m███████████████\x1b[0m\x1b[38;2;0;"
        "0;0;48;2;114;114;114m▄\x1b[0m\x1b[38;2;0;0;0;4"
        "8;2;127;127;127m▄\x1b[0m\x1b[38;2;0;0;0;48;2;1"
        "14;114;114m▄\x1b[0m\x1b[38;2;0;0;0;48;2;113;11"
        "3;113m▄\x1b[0m\x1b[38;2;0;0;0;48;2;102;102;102"
        "m▄\x1b[0m\x1b[38;2;0;0;0;49m██████\x1b[0m\x1b[38;2;0"
        ";0;0;48;2;115;115;115m▄\x1b[0m\x1b[38;2;0;0;0;"
        "48;2;117;117;117m▄\x1b[0m\x1b[38;2;0;0;0;48;2;"
        "113;113;113m▄\x1b[0m\x1b[38;2;0;0;0;48;2;115;1"
        "15;115m▄\x1b[0m\x1b[38;2;0;0;0;48;2;120;120;12"
        "0m▄\x1b[0m\x1b[38;2;0;0;0;48;2;127;127;127m▄\x1b["
        "0m\x1b[38;2;0;0;0;49m█████\x1b[0m\x1b[38;2;0;0;0;"
        "48;2;127;127;127m▄\x1b[0m\x1b[38;2;0;0;0;48;2;"
        "114;114;114m▄\x1b[0m\x1b[38;2;0;0;0;48;2;115;1"
        "15;115m▄\x1b[0m\x1b[38;2;0;0;0;48;2;113;113;11"
        "3m▄\x1b[0m\x1b[38;2;0;0;0;48;2;117;117;117m▄\x1b["
        "0m\x1b[38;2;0;0;0;49m███████\x1b[0m\x1b[38;2;0;0;"
        "0;48;2;109;109;109m▄\x1b[0m\x1b[38;2;0;0;0;48;"
        "2;121;121;121m▄\x1b[0m\x1b[38;2;0;0;0;48;2;117"
        ";117;117m▄\x1b[0m\x1b[38;2;0;0;0;48;2;116;116;"
        "116m▄\x1b[0m\x1b[38;2;0;0;0;48;2;120;120;120m▄"
        "\x1b[0m\x1b[38;2;0;0;0;49m██████\x1b[0m\x1b[38;2;0;0"
        ";0;48;2;255;255;255m▄\x1b[0m\x1b[38;2;0;0;0;48"
        ";2;114;114;114m▄\x1b[0m\x1b[38;2;0;0;0;48;2;12"
        "0;120;120m▄\x1b[0m\x1b[38;2;0;0;0;48;2;122;122"
        ";122m▄\x1b[0m\x1b[38;2;0;0;0;48;2;113;113;113m"
        "▄\x1b[0m\x1b[38;2;0;0;0;48;2;109;109;109m▄\x1b[0m"
        "\x1b[38;2;0;0;0;49m███████\x1b[0m \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_render_image_link(
    rich_notebook_output: RichOutput,
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
        f"  \x1b]8;id=42532;file://{tempfile_path}0.png"
        "\x1b\\\x1b[94m🖼 Click to view"
        " Image\x1b[0m\x1b]8;;\x1b\\                       "
        "                              \n         "
        "                                        "
        "                               \n      <F"
        "igure size 432x288 with 1 Axes>         "
        "                                \n"
    )
    assert remove_link_ids(output) == remove_link_ids(expected_output)


def test_charater_drawing(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
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
        "    \x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\n      \x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;190;190;190m!\x1b[0m\x1b[38;2;156;156;156m!\x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;"
        "2;224;224;224m:\x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\n      \x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;154;154;154m!\x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\n      \x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;224;224;"
        "224m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "250;250;250m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\n      \x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n      \x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;227;227;227m:\x1b[0m\x1b[38;2;16"
        "9;169;169m!\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;22"
        "4;224;224m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;250;250;250m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\n      \x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;250;250;250"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n "
        "     \x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;224;224;224m:\x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\n      \x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;224;224;224m:"
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;250;2"
        "50;250m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\n      \x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\n      \x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;224;224"
        ";224m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";250;250;250m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\n      \x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;250;250;250m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n      "
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;227;227;227m:\x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "24;224;224m:\x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;246;246;246m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "50;250;250m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m"
        "\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\n      \x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;250;250;25"
        "0m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n"
        "      \x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;224;224;224m:\x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\n      \x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;224;224;224m"
        ":\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;250;"
        "250;250m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\n      \x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;227;227;227m:"
        "\x1b[0m\x1b[38;2;142;142;142m?\x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;250;250;250m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;2"
        "55;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38"
        ";2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m "
        "\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n      \x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;224;22"
        "4;224m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;250;250;250m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;"
        "2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b"
        "[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;25"
        "5;255m \x1b[0m\n      \x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;224;224;224m:\x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;250;250;250m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2"
        ";255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b["
        "0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255"
        ";255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n     "
        " \x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "224;224;224m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;250;250;250m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0"
        "m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;"
        "255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;"
        "255;255;255m \x1b[0m\n      \x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;224;224;224m:\x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;250;250;2"
        "50m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;2"
        "55m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;2"
        "55;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m"
        "\n      \x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;25"
        "5m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;25"
        "5;255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b"
        "[38;2;255;255;255m \x1b[0m\n      \x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;231"
        ";231;231m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;231;231;231m:\x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;231;231;231m:\x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;249;249;249m \x1b[0m\x1b[38;2;162"
        ";162;162m!\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;127;127;127"
        "m?\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;251"
        ";251;251m \x1b[0m\x1b[38;2;132;132;132m?\x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;219"
        ";219;219m:\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;169;169;169m!\x1b[0m\x1b[38;2;245;245;245"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;251;251;251m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;169;169;169m!\x1b[0m\x1b[38;2;128"
        ";128;128m?\x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255"
        ";255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b["
        "38;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255"
        "m \x1b[0m\n      \x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[38;2;255;"
        "255;255m \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\x1b[3"
        "8;2;255;255;255m \x1b[0m\x1b[38;2;255;255;255m"
        " \x1b[0m\x1b[38;2;255;255;255m \x1b[0m\n"
    )
    assert output == expected_output


def test_braille_drawing(
    rich_notebook_output: RichOutput,
    mock_tempfile_file: Generator[Mock, None, None],
    remove_link_ids: Callable[[str], str],
    get_tempfile_path: Callable[[str], Path],
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
    output = rich_notebook_output(
        image_cell, images=True, image_drawing="braille", files=False
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
        "    \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\n      \x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;222;222;222m⣿\x1b[0m\x1b[38;2;144;144;144m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;246;24"
        "6;246m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b"
        "[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;250;25"
        "0;250m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\n      \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;192;192;192m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\n      \x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;224;224;"
        "224m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "250;250;250m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\n      \x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;141;141;141m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n      \x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;227;227;227m⣿\x1b[0m\x1b[38;2;13"
        "1;131;131m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;22"
        "4;224;224m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;224;224;22"
        "4m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\n      \x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;250;250;250"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n "
        "     \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;224;224;224m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\n      \x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;224;224;224m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;250;2"
        "50;250m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\n      \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;227;227;227m⣿\x1b"
        "[0m\x1b[38;2;139;139;139m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n      \x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;224;224"
        ";224m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";250;250;250m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\n      \x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n      "
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "24;224;224m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\n      \x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;22"
        "7;227;227m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;250;250;25"
        "0m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n"
        "      \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;224;224;224m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\n      \x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;224;224;224m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;250;"
        "250;250m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\n      \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n      \x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;224;22"
        "4;224m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;250;250;250m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;"
        "2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b"
        "[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;25"
        "5;255m⣿\x1b[0m\n      \x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2"
        ";255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b["
        "0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255"
        ";255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n     "
        " \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "224;224;224m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0"
        "m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;"
        "255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;"
        "255;255;255m⣿\x1b[0m\n      \x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "27;227;227m⣿\x1b[0m\x1b[38;2;126;126;126m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;224;224;224m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;250;250;2"
        "50m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;2"
        "55m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;2"
        "55;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m"
        "\n      \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;224;224;224m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;250;250;250m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;25"
        "5m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;25"
        "5;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b"
        "[38;2;255;255;255m⣿\x1b[0m\n      \x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255"
        ";255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b["
        "38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255"
        "m⣿\x1b[0m\n      \x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;228;228;228m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;144;144;144m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;178;178;178m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;228;228;228m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;228;"
        "228;228m⣿\x1b[0m\x1b[38;2;190;190;190m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;"
        "255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[3"
        "8;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m"
        "⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\n      \x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38"
        ";2;255;255;255m⣿\x1b[0m\x1b[38;2;255;255;255m⣿"
        "\x1b[0m\x1b[38;2;255;255;255m⣿\x1b[0m\x1b[38;2;255;2"
        "55;255m⣿\x1b[0m\n"
    )
    assert output == expected_output


def test_render_image_link_no_image(
    rich_notebook_output: RichOutput,
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
    output = rich_notebook_output(svg_cell)
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
