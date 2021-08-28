"""Tests for src.nbpreview.component.row."""
import nbformat
import pytest

from nbpreview.component import row


def test_render_unknown_output_type() -> None:
    """It does not render an unknown output type."""
    notebook_outputs = [nbformat.from_dict({"output_type": "unknown"})]
    rendered_output_row = row.render_output_row(
        notebook_outputs,
        plain=True,
        unicode=True,
        hyperlinks=True,
        nerd_font=True,
        files=True,
        hide_hyperlink_hints=True,
        theme="ansi_dark",
        pad=(0, 1, 0, 0),
        images=False,
        image_drawing=None,
    )
    with pytest.raises(StopIteration):
        next(rendered_output_row)
