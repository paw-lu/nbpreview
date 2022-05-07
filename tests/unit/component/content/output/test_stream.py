"""Test for nbpreview.component.content.output.stream."""
import nbformat
import pytest

from nbpreview.component.content.output import stream


def test_invalid_stderr_name() -> None:
    """It raises a ValueError when the name is not 'stderr'."""
    notebook_output = nbformat.from_dict(  # type: ignore[no-untyped-call]
        {"name": "unknown"}
    )
    with pytest.raises(ValueError):
        stream.StdErr.from_output(notebook_output)
