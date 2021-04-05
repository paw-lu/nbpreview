"""Package-wide test fixtures."""
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional

import nbformat
import pytest
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
        nbformat.validate(notebook)

        return nbformat.from_dict(notebook)

    return _make_notebook
