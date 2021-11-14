"""Package-wide test fixtures."""
import contextlib
import io
import pathlib
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, ContextManager, Dict, Iterator, Optional, Union

import jinja2
import nbformat
import pytest
from _pytest.config import Config, _PluggyPlugin
from _pytest.fixtures import FixtureRequest
from jinja2 import select_autoescape
from nbformat.notebooknode import NotebookNode
from rich import console


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
        return nbformat.from_dict(notebook)

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
    expected_output_file = f"{test_name}.txt"
    expected_output_template = env.get_template(expected_output_file)
    project_dir = pathlib.Path(__file__).parent.parent.resolve()
    expected_output = expected_output_template.render(
        tempfile_path=tempfile_path, project_dir=project_dir
    )
    return remove_link_ids(expected_output)
