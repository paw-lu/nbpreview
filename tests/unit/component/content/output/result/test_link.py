"""Test for nbpreview.component.content.output.result.link."""
import nbformat

from nbpreview.component.content.output.result import link
from nbpreview.data import Data


def test_image_link_no_str_data() -> None:
    """It sets the content to None when the data is not a string."""
    image_type = "image"
    data: Data = {image_type: nbformat.NotebookNode()}  # type: ignore[no-untyped-call]
    image_link = link.ImageLink.from_data(
        data,
        image_type=image_type,
        unicode=True,
        hyperlinks=True,
        nerd_font=True,
        files=False,
        hide_hyperlink_hints=False,
    )
    output = image_link.content
    expected_output = None
    assert output is expected_output


def test_image_link_bad_decode() -> None:
    """It fallsback to None when there is a decode error."""
    image_type = "image"
    data: Data = {image_type: "123"}
    image_link = link.ImageLink.from_data(
        data,
        image_type=image_type,
        unicode=True,
        hyperlinks=True,
        nerd_font=True,
        files=False,
        hide_hyperlink_hints=False,
    )
    output = image_link.content
    expected_output = None
    assert output is expected_output
