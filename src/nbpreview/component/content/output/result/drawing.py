"""Drawings of image outputs."""
from __future__ import annotations

import abc
import base64
import dataclasses
import enum
import functools
import io
import sys
from dataclasses import InitVar
from typing import Iterator
from typing import Literal
from typing import Optional
from typing import Tuple
from typing import Union

import picharsso
import PIL.Image
from picharsso.draw import gradient
from PIL.Image import Image
from rich import ansi
from rich import measure
from rich import style
from rich import text
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import RenderResult
from rich.measure import Measurement
from rich.text import Text

from nbpreview.data import Data

# terminedia depends on fcntl, which is not present on Windows platforms
try:
    import terminedia
except ModuleNotFoundError:
    pass


def render_drawing(
    data: Data,
    image_drawing: Literal["block", "character", "braille", None],
    image_type: str,
    unicode: bool,
    color: bool,
    negative_space: bool,
    characters: str = gradient.DEFAULT_CHARSET,
) -> Union[Drawing, None]:
    """Render a drawing of an image."""
    rendered_image: Drawing
    if image_type != "image/svg+xml":
        if (
            image_drawing == "block"
            and unicode
            and "terminedia" in sys.modules
            and color
        ):
            rendered_image = UnicodeDrawing.from_data(data, image_type=image_type)
            return rendered_image

        elif image_drawing == "braille" and unicode:
            rendered_image = BrailleDrawing.from_data(
                data,
                image_type=image_type,
                color=color,
            )
            return rendered_image

        elif image_drawing == "character":
            rendered_image = CharacterDrawing.from_data(
                data,
                image_type=image_type,
                color=color,
                negative_space=negative_space,
                characters=characters,
            )
            return rendered_image

    return None


class Bottleneck(str, enum.Enum):
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
) -> Bottleneck:
    """Detect which dimension the image is bottlenecked on."""
    image_ratio = image_width / image_height
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

    def __post_init__(self, image: Image) -> None:
        """Constructor."""
        image_width, image_height = image.size
        image_ratio = image_width / image_height

        self.bottleneck = _detect_image_bottleneck(
            image_width=image_width,
            image_height=image_height,
            max_width=self.max_width,
            max_height=self.max_height,
        )

        image_width, image_height = image.size
        image_ratio = image_width / image_height

        if self.bottleneck == Bottleneck.WIDTH and self.max_width is not None:
            drawing_width = self.max_width
            drawing_height = int(drawing_width / image_ratio)
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


def render_fallback_text(fallback_text: str) -> Text:
    """Render the fallback text representing an image."""
    rendered_fallback_text = text.Text(
        fallback_text, style=style.Style(color="#BB86FC")
    )
    return rendered_fallback_text


@functools.lru_cache(maxsize=2 ** 12)
def _render_block_drawing(
    image: bytes, max_width: int, max_height: int, fallback_text: str
) -> Tuple[Text, ...]:
    """Render a representation on an image with unicode characters."""
    rendered_unicode_drawing: Tuple[Text, ...]
    try:
        pil_image = PIL.Image.open(io.BytesIO(image))

    except PIL.UnidentifiedImageError:
        rendered_unicode_drawing = (render_fallback_text(fallback_text=fallback_text),)

    else:
        dimensions = DrawingDimension(
            pil_image, max_width=max_width, max_height=max_height
        )
        size = terminedia.V2(x=dimensions.drawing_width, y=dimensions.drawing_height)

        shape = terminedia.shape(
            pil_image,
            size=size,
            promote=True,
            resolution="square",
        )

        output = io.StringIO()
        shape.render(output=output, backend="ANSI")
        string_image = output.getvalue()
        decoder = ansi.AnsiDecoder()
        rendered_unicode_drawing = tuple(decoder.decode(string_image))

    return rendered_unicode_drawing


class UnicodeDrawing(Drawing):
    """A unicode representation of an image."""

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
    def from_data(cls, data: Data, image_type: str) -> UnicodeDrawing:
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
        minimum = max(len(line) for line in rendered_unicode_drawing)
        return measure.Measurement(minimum, maximum=options.max_width)


@dataclasses.dataclass
class CharacterDimensions:
    """Dimensions for a character drawing."""

    bottleneck: Bottleneck
    max_width: int
    max_height: int

    def __post_init__(self) -> None:
        """Constructor."""
        if self.bottleneck == Bottleneck.WIDTH:
            width = self.max_width
            height = 0
        elif self.bottleneck == Bottleneck.HEIGHT:
            width = 0
            height = self.max_height
        else:
            width = self.max_width
            height = self.max_height

        self.width = width
        self.height = height


@functools.lru_cache(maxsize=2 ** 12)
def _render_character_drawing(
    image: bytes,
    color: bool,
    max_width: int,
    max_height: int,
    fallback_text: str,
    characters: str = gradient.DEFAULT_CHARSET,
    negative_space: bool = True,
) -> Tuple[Text, ...]:
    """Render a representation of an image with text characters."""
    rendered_character_drawing: Tuple[Text, ...]
    try:
        pil_image = PIL.Image.open(io.BytesIO(image))

    except PIL.UnidentifiedImageError:
        rendered_character_drawing = (render_fallback_text(fallback_text),)

    else:
        dimensions = DrawingDimension(
            image=pil_image, max_width=max_width, max_height=max_height
        )
        character_dimensions = CharacterDimensions(
            bottleneck=dimensions.bottleneck, max_width=max_width, max_height=max_height
        )

        drawer = picharsso.new_drawer(
            style="gradient",
            width=character_dimensions.width,
            height=character_dimensions.height,
            colorize=color,
            charset=characters,
            negative=negative_space,
        )
        drawing = drawer(pil_image)

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
        characters: str = gradient.DEFAULT_CHARSET,
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
        characters: str = gradient.DEFAULT_CHARSET,
    ) -> CharacterDrawing:
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
        minimum = max(len(line) for line in rendered_character_drawing)
        return measure.Measurement(minimum=minimum, maximum=options.max_width)


@functools.lru_cache(maxsize=2 ** 12)
def _render_braille_drawing(
    image: bytes,
    color: bool,
    max_width: int,
    max_height: int,
    fallback_text: str,
    negative_space: bool = True,
) -> Tuple[Text, ...]:
    """Render a representation of an image with braille characters."""
    rendered_character_drawing: Tuple[Text, ...]
    try:
        pil_image = PIL.Image.open(io.BytesIO(image))

    except PIL.UnidentifiedImageError:
        rendered_character_drawing = (render_fallback_text(fallback_text),)

    else:
        dimensions = DrawingDimension(
            image=pil_image, max_width=max_width, max_height=max_height
        )
        character_dimensions = CharacterDimensions(
            bottleneck=dimensions.bottleneck, max_width=max_width, max_height=max_height
        )
        drawer = picharsso.new_drawer(
            style="braille",
            width=character_dimensions.width,
            height=character_dimensions.height,
            colorize=color,
        )
        drawing = drawer(pil_image)

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
    ) -> BrailleDrawing:
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
        minimum = max(len(line) for line in rendered_braille_drawing)
        return measure.Measurement(minimum=minimum, maximum=options.max_width)
