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


def test_character_drawing_repr(image: Image) -> None:
    """It has a string representation."""
    character_drawing = drawing.CharacterDrawing(
        b"sefi", fallback_text="Hey", color=True, negative_space=True
    )
    output = repr(character_drawing)
    expected_output = (
        "CharacterDrawing(image=sefi, fallback_text=Hey,"
        " color=True, negative_space=True, characters= :!?PG@)"
    )
    assert output == expected_output


def test_render_character_drawing_invalid_image() -> None:
    """It uses the fallback text when it fails to read the image."""
    fallback_text = "Fallback"
    output = drawing._render_character_drawing(
        image=b"", color=True, max_width=10, max_height=30, fallback_text=fallback_text
    )
    expected_output = (drawing.render_fallback_text(fallback_text),)
    assert output == expected_output


def test_bottlenecked_height_character_dimensions(image: Image) -> None:
    """It sets the width to 0 when bottlenecked by height."""
    max_height = 80
    character_dimensions = drawing.CharacterDimensions(
        drawing.Bottleneck.HEIGHT, max_width=30, max_height=max_height
    )
    character_width = character_dimensions.width
    character_height = character_dimensions.height
    expected_width = 0
    assert character_width == expected_width
    assert character_height == max_height


def test_no_bottleneck_character_dimensions(image: Image) -> None:
    """It sets the width to 0 when bottlenecked by height."""
    max_width = 30
    max_height = 80
    character_dimensions = drawing.CharacterDimensions(
        drawing.Bottleneck.BOTH, max_width=max_width, max_height=max_height
    )
    character_width = character_dimensions.width
    character_height = character_dimensions.height
    assert character_width == max_width
    assert character_height == max_height
