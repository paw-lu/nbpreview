"""Package-wide test fixtures."""
import contextlib
from typing import Any
from typing import Callable
from typing import ContextManager
from typing import Dict
from typing import Iterator
from typing import Optional

import nbformat
import pytest
from _pytest.config import _PluggyPlugin
from _pytest.config import Config
from nbformat.notebooknode import NotebookNode


@pytest.fixture
def make_notebook() -> Callable[[Optional[Dict[str, Any]]], NotebookNode]:
    """Fixture that returns a function that creates a base notebook."""

    def _make_notebook(cell: Optional[Dict[str, Any]] = None) -> NotebookNode:
        """Create a NotebookNode.

        Args:
            cell (Optional[Dict[str, Any]], optional): The cell for the
                NotebookNode. Defaults to None.

        Returns:
            NotebookNode: The NotebookNode containing the inputted cell.
        """
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
        nbformat.validate(notebook, version=4)

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
