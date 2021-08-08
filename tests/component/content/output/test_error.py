"""Test for nbpreview.component.content.output.error."""
import nbformat
import pytest

from nbpreview.component.content.output import error


def test_render_unknown_error() -> None:
    """It does not render an unknown error type."""
    notebook_output = nbformat.from_dict({})
    output = error.render_error(notebook_output, theme="dark")
    with pytest.raises(StopIteration):
        next(output)


def test_render_error() -> None:
    """It joins all elements and renders the text."""
    output = error.Error(["Lorep", "ipsum"]).__rich__()
    expected_output = "Lorep\nipsum"
    assert output == expected_output
