"""Package-wide test fixtures."""
import contextlib
import io
import itertools
import os
import pathlib
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, ContextManager, Dict, Iterator, Optional, Union
from unittest.mock import Mock

import jinja2
import nbformat
import pytest
from _pytest.config import Config, _PluggyPlugin
from _pytest.fixtures import FixtureRequest
from jinja2 import select_autoescape
from nbformat.notebooknode import NotebookNode
from pytest_mock import MockerFixture
from rich import ansi, console, padding, text
from rich.text import Text


@pytest.fixture
def tempfile_path() -> Path:
    """Fixture that returns the tempfile path."""
    prefix = tempfile.template
    file_path = pathlib.Path(tempfile.gettempdir()) / pathlib.Path(
        f"{prefix}nbpreview_link_file"
    )
    return file_path


@pytest.fixture
def remove_link_ids() -> Callable[[str], str]:
    """Create function to remove link ids from rendered hyperlinks."""

    def _remove_link_ids(render: str) -> str:
        """Remove link ids from rendered hyperlinks."""
        re_link_ids = re.compile(r"id=[\d\.\-]*?;")
        subsituted_render = re_link_ids.sub("id=0;", render)
        return subsituted_render

    return _remove_link_ids


@pytest.fixture
def make_notebook_dict() -> Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]:
    """Fixture that returns function that constructs notebook dict."""

    def _make_notebook_dict(cell: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create valid notebook dictionary around single cell."""
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "id": "conceptual-conditions",
                    "metadata": {},
                    "outputs": [],
                    "source": "",
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "nbpreview",
                    "language": "python",
                    "name": "nbpreview",
                },
                "language_info": {
                    "codemirror_mode": {"name": "ipython", "version": 3},
                    "file_extension": ".py",
                    "mimetype": "text/x-python",
                    "name": "python",
                    "nbconvert_exporter": "python",
                    "pygments_lexer": "ipython3",
                    "version": "3.8.6",
                },
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        if cell is not None:
            notebook["cells"] = [cell]
        return notebook

    return _make_notebook_dict


@pytest.fixture
def make_notebook(
    make_notebook_dict: Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]
) -> Callable[[Optional[Dict[str, Any]]], NotebookNode]:
    """Fixture that returns a function that creates a base notebook."""

    def _make_notebook(cell: Optional[Dict[str, Any]] = None) -> NotebookNode:
        """Create a NotebookNode.

        Args:
            cell (Optional[Dict[str, Any]], optional): The cell for the
                NotebookNode. Defaults to None.

        Returns:
            NotebookNode: The NotebookNode containing the inputted cell.
        """
        notebook = make_notebook_dict(cell)
        notebook_node: NotebookNode = nbformat.from_dict(
            notebook
        )  # type: ignore[no-untyped-call]
        return notebook_node

    return _make_notebook


@pytest.fixture
def disable_capture(pytestconfig: Config) -> ContextManager[_PluggyPlugin]:
    """Disable pytest's capture."""
    # https://github.com/pytest-dev/pytest/issues/
    # 1599?utm_source=pocket_mylist#issuecomment-556327594
    @contextlib.contextmanager
    def _disable_capture() -> Iterator[_PluggyPlugin]:
        """Disable pytest's capture."""
        capmanager = pytestconfig.pluginmanager.getplugin("capturemanager")
        try:
            capmanager.suspend_global_capture(in_=True)
            yield capmanager
        finally:
            capmanager.resume_global_capture()

    return _disable_capture()


@pytest.fixture
def rich_console() -> Callable[[Any, Union[bool, None]], str]:
    """Fixture that returns Rich console."""

    def _rich_console(renderable: Any, no_wrap: Optional[bool] = None) -> str:
        """Render an object using rich."""
        con = console.Console(
            file=io.StringIO(),
            width=80,
            height=120,
            color_system="truecolor",
            legacy_windows=False,
            force_terminal=True,
        )
        con.print(renderable, no_wrap=no_wrap)
        output: str = con.file.getvalue()  # type: ignore[attr-defined]
        return output

    return _rich_console


def _wrap_ansi(
    decoded_text: Iterator[Text], width: int, left_pad: int
) -> Iterator[str]:
    """Wrap characters relative to cell width."""
    for idx, text_line in enumerate(decoded_text):
        output = io.StringIO()
        con = console.Console(
            force_terminal=True,
            file=output,
            color_system="truecolor",
            no_color=False,
            width=width,
            soft_wrap=True,
        )
        non_pad_width = width - left_pad
        if idx == 0:  # pragma: no branch
            *pre_link_text, link_text = text_line.split(" ")
            if width < text_line.cell_len and link_text.cell_len <= non_pad_width:
                text_line = link_text
                first_line = text.Text(" ").join(pre_link_text)
                con.print(first_line)
            else:
                first_line, text_line = text_line[:width], text_line[width:]
                con.print(first_line)
        if text_line:
            wrapped_lines = text_line.wrap(con, width=non_pad_width)
            padded_lines = padding.Padding(wrapped_lines, pad=(0, 0, 0, left_pad))
            con.print(padded_lines)
        if plain_text := output.getvalue():  # pragma: no branch
            yield plain_text


def decode_ansi(value: str) -> Iterator[Text]:
    """Decode ansi into rich Text."""
    decoder = ansi.AnsiDecoder()
    parsed_text = decoder.decode(value)
    yield from parsed_text


def ansi_wrap(value: str, width: int = 80, left_pad: int = 6) -> str:
    """Wrap characers relative to their cell width."""
    decoded_text = decode_ansi(value)
    wrapped_text = "\n".join(_wrap_ansi(decoded_text, width=width, left_pad=left_pad))
    return wrapped_text


def ansi_right_pad(value: str, min_width: int = 80) -> str:
    """Right pad the string to be no less than a certain width."""
    decoded_text = decode_ansi(value)
    output = io.StringIO()
    con = console.Console(
        force_terminal=True,
        file=output,
        color_system="truecolor",
        no_color=False,
        width=min_width,
        soft_wrap=True,
    )
    for line in decoded_text:
        line.rstrip()
        cell_len = line.cell_len
        pad = min_width - cell_len
        line.pad_right(pad)
        con.print(line)
    return output.getvalue().rstrip("\n")


@pytest.fixture
def expected_output(
    request: FixtureRequest, tempfile_path: Path, remove_link_ids: Callable[[str], str]
) -> str:
    """Get the expected output for a test."""
    output_directory = pathlib.Path(__file__).parent / pathlib.Path(
        "unit", "expected_outputs"
    )
    test_name = request.node.name
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(output_directory),
        autoescape=select_autoescape(),
        keep_trailing_newline=True,
    )
    env.filters["ansi_right_pad"] = ansi_right_pad
    env.filters["ansi_wrap"] = ansi_wrap
    expected_output_file = f"{test_name}.txt"
    expected_output_template = env.get_template(expected_output_file)
    project_dir = pathlib.Path(__file__).parent.parent.resolve()
    expected_output = expected_output_template.render(
        tempfile_path=os.fsdecode(tempfile_path), project_dir=project_dir
    )
    return remove_link_ids(expected_output)


@pytest.fixture
def mock_tempfile_file(mocker: MockerFixture, tempfile_path: Path) -> Iterator[Mock]:
    """Control where tempfile will write to."""
    tempfile_stem = tempfile_path.stem
    tempfile_base_name = tempfile_stem[3:]
    tempfile_parent = tempfile_path.parent
    mock = mocker.patch("tempfile._get_candidate_names")
    mock.return_value = (  # pragma: no branch
        f"{tempfile_base_name}{file_suffix}" for file_suffix in itertools.count()
    )
    yield mock
    tempfiles = tempfile_parent.glob(f"{tempfile_stem}*")
    for file in tempfiles:
        file.unlink()
