"""Test for nbpreview.component.content.output.result.drawing."""
import PIL.Image
import pytest
from PIL.Image import Image

from nbpreview.component.content.output.result import drawing


@pytest.fixture
def image() -> Image:
    """Create dummy Pillow Image."""
    image = PIL.Image.new("RGB", size=(80, 50))
    return image


def test_drawing_repr() -> None:
    """It has a string representation."""
    draw = drawing.UnicodeDrawing(image=b"123", fallback_text="Hello")
    expected_output = "UnicodeDrawing(image=123, fallback_text=Hello)"
    output = draw.__repr__()
    assert output == expected_output


def test_unlimited_width_dimensions(image: Image) -> None:
    """It takes the full available height with unlimited width."""
    dimensions = drawing.DrawingDimension(
        image=image,
        max_width=None,
        max_height=30,
    )
    expected_width = 48
    expected_height = 30
    width = dimensions.drawing_width
    height = dimensions.drawing_height
    assert width == expected_width
    assert height == expected_height


def test_unlimited_height_dimensions(image: Image) -> None:
    """It takes the full available width with unlimited height."""
    dimensions = drawing.DrawingDimension(
        image=image,
        max_width=30,
        max_height=None,
    )
    expected_width = 30
    expected_height = 18
    width = dimensions.drawing_width
    height = dimensions.drawing_height
    assert width == expected_width
    assert height == expected_height


def test_unlimited_dimensions(image: Image) -> None:
    """It is rendered in its original size when space is unlimited."""
    dimensions = drawing.DrawingDimension(
        image=image,
        max_width=None,
        max_height=None,
    )
    expected_width = 80
    expected_height = 50
    width = dimensions.drawing_width
    height = dimensions.drawing_height
    assert width == expected_width
    assert height == expected_height


def test_perfect_fit_dimensions(image: Image) -> None:
    """It takes up all possible space when ratios are equal."""
    max_width = 16
    max_height = 10
    dimensions = drawing.DrawingDimension(
        image=image,
        max_width=max_width,
        max_height=max_height,
    )
    expected_width = max_width
    expected_height = max_height
    width = dimensions.drawing_width
    height = dimensions.drawing_height
    assert width == expected_width
    assert height == expected_height


def test_limited_width_dimensions(image: Image) -> None:
    """It adjusts the dimensions to fit in a limited width."""
    dimensions = drawing.DrawingDimension(
        image=image,
        max_width=8,
        max_height=10,
    )
    expected_width = 8
    expected_height = 5
    width = dimensions.drawing_width
    height = dimensions.drawing_height
    assert width == expected_width
    assert height == expected_height


def test_limited_height_dimensions(image: Image) -> None:
    """It adjusts the dimensions to fit in a limited height."""
    dimensions = drawing.DrawingDimension(
        image=image,
        max_width=18,
        max_height=5,
    )
    expected_width = 8
    expected_height = 5
    width = dimensions.drawing_width
    height = dimensions.drawing_height
    assert width == expected_width
    assert height == expected_height
