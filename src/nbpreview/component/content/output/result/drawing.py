"""Drawings of image outputs."""
import abc
import base64
import binascii
import dataclasses
import enum
import functools
import io
import typing
from dataclasses import InitVar
from typing import Iterator, Literal, Optional, Tuple, Union

import picharsso
import PIL.Image
from picharsso.draw import gradient
from PIL.Image import Image
from rich import ansi, measure, style, text
from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.text import Text
from term_image import image as term_image

from nbpreview.data import Data
from nbpreview.option_values import ImageDrawingEnum


class Size(typing.NamedTuple):
    """The size of a rendered image."""

    x: Union[float, None]
    y: Union[float, None]


ImageDrawing = Union[ImageDrawingEnum, Literal["block", "character", "braille"]]


class Drawing(abc.ABC):
    """A representation of an image output."""

    def __init__(self, image: bytes, fallback_text: str) -> None:
        """Constructor."""
        self.image = image
        self.fallback_text = fallback_text

    def __repr__(self) -> str:
        """String representation of class."""
        return (
            f"{self.__class__.__qualname__}(image={self.image.decode():.10},"
            f" fallback_text={self.fallback_text})"
        )

    @abc.abstractmethod
    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render a drawing of image."""

    @abc.abstractmethod
    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered drawing."""


def _get_image(data: Data, image_type: str) -> Union[bytes, None]:
    """Extract an image in bytes from data."""
    encoded_image = data[image_type]
    decoded_image: Union[bytes, None]
    try:
        decoded_image = base64.b64decode(encoded_image)
    except binascii.Error:
        decoded_image = None
    return decoded_image


def _get_fallback_text(data: Data) -> str:
    """Get a fallback text from data."""
    return data.get("text/plain", "Image")


def choose_drawing(
    image: Union[bytes, None],
    fallback_text: str,
    image_type: str,
    image_drawing: ImageDrawing,
    color: bool,
    negative_space: bool,
    characters: Optional[str] = None,
) -> Union[Drawing, None]:
    """Choose which drawing to render an image with."""
    rendered_image: Drawing
    if image is not None and image_type != "image/svg+xml":
        if image_drawing == "block":
            rendered_image = BlockDrawing(image=image, fallback_text=fallback_text)
            return rendered_image

        elif image_drawing == "braille":
            rendered_image = BrailleDrawing(
                image=image,
                fallback_text=fallback_text,
                color=color,
            )
            return rendered_image
        elif image_drawing == "character":
            rendered_image = CharacterDrawing(
                image=image,
                fallback_text=fallback_text,
                color=color,
                negative_space=negative_space,
                characters=characters,
            )
            return rendered_image
        else:
            raise ValueError(
                f"{image_drawing} is an invalid image_drawing,"
                " expected 'block', 'character', or 'braille'"
            )
    return None


def render_drawing(
    data: Data,
    image_drawing: ImageDrawing,
    image_type: str,
    color: bool,
    negative_space: bool,
    characters: Optional[str] = None,
) -> Union[Drawing, None]:
    """Render a drawing of an image."""
    image = _get_image(data, image_type=image_type)
    fallback_text = _get_fallback_text(data)
    rendered_drawing = choose_drawing(
        image=image,
        fallback_text=fallback_text,
        image_drawing=image_drawing,
        image_type=image_type,
        color=color,
        negative_space=negative_space,
        characters=characters,
    )
    return rendered_drawing


@enum.unique
class Bottleneck(enum.Enum):
    """The bottleneck when rendering a drawing."""

    WIDTH = enum.auto()
    HEIGHT = enum.auto()
    BOTH = enum.auto()
    NEITHER = enum.auto()


def _detect_image_bottleneck(
    image_width: int,
    image_height: int,
    max_width: Union[int, None],
    max_height: Union[int, None],
    scaling_factor: float = 2.125,
) -> Bottleneck:
    """Detect which dimension the image is bottlenecked on."""
    image_ratio = scaling_factor * image_width / image_height
    max_ratio = (
        max_width / max_height
        if max_width is not None and max_height is not None
        else None
    )
    if max_width is not None and (
        (max_ratio is None) or (max_ratio is not None and max_ratio < image_ratio)
    ):
        bottleneck = Bottleneck.WIDTH
    elif max_height is not None and (
        max_ratio is None or (max_ratio is not None and image_ratio < max_ratio)
    ):
        bottleneck = Bottleneck.HEIGHT
    elif max_width is not None and max_height is not None:
        bottleneck = Bottleneck.NEITHER
    else:
        bottleneck = Bottleneck.BOTH

    return bottleneck


@dataclasses.dataclass
class DrawingDimension:
    """The dimensions of a drawing."""

    image: InitVar[Image]
    max_width: Optional[int] = None
    max_height: Optional[int] = None
    scaling_factor: float = 2.125

    def __post_init__(self, image: Image) -> None:
        """Constructor."""
        image_width, image_height = image.size
        image_ratio = self.scaling_factor * image_width / image_height

        self.bottleneck = _detect_image_bottleneck(
            image_width=image_width,
            image_height=image_height,
            max_width=self.max_width,
            max_height=self.max_height,
            scaling_factor=self.scaling_factor,
        )

        if self.bottleneck == Bottleneck.WIDTH and self.max_width is not None:
            drawing_width = self.max_width
            drawing_height = round(drawing_width / image_ratio)
        elif self.bottleneck == Bottleneck.HEIGHT and self.max_height is not None:
            drawing_height = self.max_height
            drawing_width = int(drawing_height * image_ratio)
        elif (
            self.bottleneck == Bottleneck.NEITHER
            and self.max_width is not None
            and self.max_height is not None
        ):
            drawing_width = self.max_width
            drawing_height = self.max_height
        else:
            drawing_width = image_width
            drawing_height = image_height

        self.drawing_width = drawing_width
        self.drawing_height = drawing_height


def render_fallback_text(fallback_text: str) -> Text:
    """Render the fallback text representing an image."""
    rendered_fallback_text = text.Text(
        fallback_text, style=style.Style(color="#BB86FC")
    )
    return rendered_fallback_text


@functools.lru_cache(maxsize=2**12)
def _render_block_drawing(
    image: bytes, max_width: int, max_height: int, fallback_text: str
) -> Tuple[Text, ...]:
    """Render a representation on an image with unicode characters."""
    rendered_unicode_drawing: Tuple[Text, ...]
    try:
        pil_image = PIL.Image.open(io.BytesIO(image))
        block_image = term_image.TermImage(pil_image)
        block_image.set_size(maxsize=(max_width, max_height))
        string_image = str(block_image)
        pil_image.close()

    except (PIL.UnidentifiedImageError, ValueError):
        rendered_unicode_drawing = (render_fallback_text(fallback_text=fallback_text),)

    else:
        decoder = ansi.AnsiDecoder()
        rendered_unicode_drawing = tuple(decoder.decode(string_image))

    return rendered_unicode_drawing


class BlockDrawing(Drawing):
    """A block representation of an image."""

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Text]:
        """Render a unicode drawing of image."""
        rendered_unicode_drawing = _render_block_drawing(
            self.image,
            max_height=options.max_height,
            max_width=options.max_width,
            fallback_text=self.fallback_text,
        )
        yield from rendered_unicode_drawing

    @classmethod
    def from_data(cls, data: Data, image_type: str) -> "BlockDrawing":
        """Create a drawing from notebook data."""
        encoded_image = data[image_type]
        fallback_text = data.get("text/plain", "Image")
        decoded_image = base64.b64decode(encoded_image)
        return cls(decoded_image, fallback_text=fallback_text)

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered unicode drawing."""
        rendered_unicode_drawing = _render_block_drawing(
            self.image,
            max_height=options.max_height,
            max_width=options.max_width,
            fallback_text=self.fallback_text,
        )
        minimum = max(line.cell_len for line in rendered_unicode_drawing)
        return measure.Measurement(minimum, maximum=options.max_width)


@dataclasses.dataclass
class CharacterDimensions:
    """Dimensions for a character drawing."""

    bottleneck: Bottleneck
    max_width: Union[int, None]
    max_height: Union[int, None]

    def __post_init__(self) -> None:
        """Constructor."""
        if self.bottleneck == Bottleneck.WIDTH:
            width = self.max_width
            height = None
        elif self.bottleneck == Bottleneck.HEIGHT:
            width = None
            height = self.max_height
        else:
            width = self.max_width
            height = self.max_height

        self.width = width
        self.height = height


@functools.lru_cache(maxsize=2**12)
def _render_character_drawing(
    image: bytes,
    color: bool,
    max_width: int,
    max_height: int,
    fallback_text: str,
    characters: Optional[str] = None,
    negative_space: bool = True,
) -> Tuple[Text, ...]:
    """Render a representation of an image with text characters."""
    rendered_character_drawing: Tuple[Text, ...]
    characters = characters if characters is not None else gradient.DEFAULT_CHARSET
    try:
        pil_image = PIL.Image.open(io.BytesIO(image))
        dimensions = DrawingDimension(
            image=pil_image, max_width=max_width, max_height=max_height
        )
        character_dimensions = CharacterDimensions(
            bottleneck=dimensions.bottleneck, max_width=max_width, max_height=max_height
        )
        drawer = picharsso.new_drawer(
            style="gradient",
            width=character_dimensions.width or 0,
            height=character_dimensions.height or 0,
            colorize=color,
            charset=characters,
            negative=negative_space,
        )
        drawing = drawer(pil_image)

    except (PIL.UnidentifiedImageError, ValueError):
        rendered_character_drawing = (render_fallback_text(fallback_text),)

    else:
        pil_image.close()

        decoder = ansi.AnsiDecoder()
        rendered_character_drawing = tuple(decoder.decode(drawing))

    return rendered_character_drawing


class CharacterDrawing(Drawing):
    """A representation of an image using text characters."""

    def __init__(
        self,
        image: bytes,
        fallback_text: str,
        color: bool,
        negative_space: bool,
        characters: Optional[str] = None,
    ) -> None:
        """Constructor."""
        super().__init__(image=image, fallback_text=fallback_text)
        self.negative_space = negative_space
        self.characters = characters
        self.color = color

    def __repr__(self) -> str:
        """String representation of CharacterDrawing."""
        return (
            f"{self.__class__.__qualname__}(image={self.image.decode():.10},"
            f" fallback_text={self.fallback_text},"
            f" color={self.color},"
            f" negative_space={self.negative_space},"
            f" characters={self.characters})"
        )

    @classmethod
    def from_data(
        cls,
        data: Data,
        image_type: str,
        color: bool,
        negative_space: bool,
        characters: Optional[str] = None,
    ) -> "CharacterDrawing":
        """Create a drawing from notebook data."""
        encoded_image = data[image_type]
        fallback_text = data.get("text/plain", "Image")
        decoded_image = base64.b64decode(encoded_image)
        return cls(
            decoded_image,
            fallback_text=fallback_text,
            color=color,
            negative_space=negative_space,
            characters=characters,
        )

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Text]:
        """Render a character drawing of an image."""
        rendered_character_drawing = _render_character_drawing(
            image=self.image,
            characters=self.characters,
            color=self.color,
            max_width=options.max_width,
            max_height=options.max_height,
            fallback_text=self.fallback_text,
            negative_space=self.negative_space,
        )
        yield from rendered_character_drawing

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered unicode drawing."""
        rendered_character_drawing = _render_character_drawing(
            image=self.image,
            characters=self.characters,
            color=self.color,
            max_width=options.max_width,
            max_height=options.max_height,
            fallback_text=self.fallback_text,
            negative_space=self.negative_space,
        )
        minimum = max(line.cell_len for line in rendered_character_drawing)
        return measure.Measurement(minimum=minimum, maximum=options.max_width)


@functools.lru_cache(maxsize=2**12)
def _render_braille_drawing(
    image: bytes,
    color: bool,
    max_width: int,
    max_height: int,
    fallback_text: str,
) -> Tuple[Text, ...]:
    """Render a representation of an image with braille characters."""
    rendered_character_drawing: Tuple[Text, ...]
    try:
        pil_image = PIL.Image.open(io.BytesIO(image))
        dimensions = DrawingDimension(
            image=pil_image, max_width=max_width, max_height=max_height
        )
        character_dimensions = CharacterDimensions(
            bottleneck=dimensions.bottleneck, max_width=max_width, max_height=max_height
        )
        drawer = picharsso.new_drawer(
            style="braille",
            width=character_dimensions.width or 0,
            height=character_dimensions.height or 0,
            colorize=color,
        )
        drawing = drawer(pil_image)
        pil_image.close()

    except (PIL.UnidentifiedImageError, ValueError):
        rendered_character_drawing = (render_fallback_text(fallback_text),)

    else:
        decoder = ansi.AnsiDecoder()
        rendered_character_drawing = tuple(decoder.decode(drawing))

    return rendered_character_drawing


class BrailleDrawing(Drawing):
    """A representation of an image using braille characters."""

    def __init__(
        self,
        image: bytes,
        fallback_text: str,
        color: bool,
    ) -> None:
        """Constructor."""
        super().__init__(image=image, fallback_text=fallback_text)
        self.color = color

    def __repr__(self) -> str:
        """String representation of BrailleDrawing."""
        return (
            f"{self.__class__.__qualname__}(image={self.image.decode():.10},"
            f" fallback_text={self.fallback_text},"
            f" color={self.color})"
        )

    @classmethod
    def from_data(
        cls,
        data: Data,
        image_type: str,
        color: bool,
    ) -> "BrailleDrawing":
        """Create a braille drawing from notebook data."""
        encoded_image = data[image_type]
        fallback_text = data.get("text/plain", "Image")
        decoded_image = base64.b64decode(encoded_image)
        return cls(
            decoded_image,
            fallback_text=fallback_text,
            color=color,
        )

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Text]:
        """Render a braille drawing of an image."""
        rendered_braille_drawing = _render_braille_drawing(
            image=self.image,
            color=self.color,
            max_width=options.max_width,
            max_height=options.max_height,
            fallback_text=self.fallback_text,
        )
        yield from rendered_braille_drawing

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered unicode drawing."""
        rendered_braille_drawing = _render_braille_drawing(
            image=self.image,
            color=self.color,
            max_width=options.max_width,
            max_height=options.max_height,
            fallback_text=self.fallback_text,
        )
        minimum = max(line.cell_len for line in rendered_braille_drawing)
        return measure.Measurement(minimum=minimum, maximum=options.max_width)
