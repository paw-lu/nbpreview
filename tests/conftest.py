"""Package-wide test fixtures."""
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional

import nbformat
import pytest


@pytest.fixture
def make_notebook() -> Callable[[Optional[Dict[str, Any]]], Dict[str, Any]]:
    """Fixture that returns a function that creates a base notebook."""

    def _make_notebook(cell: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        notebook = {
            "cells": [
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "id": "stone-segment",
                    "metadata": {},
                    "outputs": [],
                    "source": [],
                }
            ],
            "metadata": {
                "kernelspec": {
                    "display_name": "Python 3",
                    "language": "python",
                    "name": "python3",
                },
                "language_info": {
                    "codemirror_mode": {"name": "ipython", "version": 3},
                    "file_extension": ".py",
                    "mimetype": "text/x-python",
                    "name": "python",
                    "nbconvert_exporter": "python",
                    "pygments_lexer": "ipython3",
                    "version": "3.9.2",
                },
            },
            "nbformat": 4,
            "nbformat_minor": 5,
        }
        if cell is not None:
            notebook["cells"] = [cell]
        nbformat.validate(notebook)
        return notebook

    return _make_notebook
