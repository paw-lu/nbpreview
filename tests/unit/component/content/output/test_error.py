"""Test for nbpreview.component.content.output.error."""
import nbformat
import pytest

from nbpreview.component.content.output import error


def test_render_unknown_error() -> None:
    """It does not render an unknown error type."""
    notebook_output = nbformat.from_dict({})  # type: ignore[no-untyped-call]
    output = error.render_error(notebook_output)
    with pytest.raises(StopIteration):
        next(output)


def test_error_repr() -> None:
    """It has a string representation."""
    content = ["foo", "bar"]
    traceback = error.Traceback(content)
    expected_output = f"Traceback(content={content})"
    output = repr(traceback)
    assert output == expected_output
