"""Drawings of image outputs."""
from __future__ import annotations

import abc
import base64
import dataclasses
import functools
import io
import sys
from dataclasses import InitVar
from typing import Iterator
from typing import Optional
from typing import Tuple
from typing import Union

import PIL
import terminedia
from PIL import Image
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

if sys.version_info >= (3, 8):
    from typing import Literal
else:  # pragma: no cover
    from typing_extensions import Literal


def render_drawing(
    data: Data,
    image_drawing: Literal["block", None],
    image_type: str,
    unicode: bool,
    nerd_font: bool,
) -> Union[Drawing, None]:
    """Render a drawing of an image."""
    if image_drawing == "block" and image_type != "image/svg+xml":
        rendered_image = UnicodeDrawing.from_data(data, image_type=image_type)
        return rendered_image
    return None


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
        image_width = image

        max_ratio = (
            self.max_width / self.max_height
            if self.max_width is not None and self.max_height is not None
            else None
        )

        image_width, image_height = image.size
        image_ratio = image_width / image_height

        if self.max_width is not None and (
            (max_ratio is None) or (max_ratio is not None and max_ratio < image_ratio)
        ):
            drawing_width = self.max_width
            drawing_height = int(drawing_width / image_ratio)
        elif self.max_height is not None and (
            max_ratio is None or (max_ratio is not None and image_ratio < max_ratio)
        ):
            drawing_height = self.max_height
            drawing_width = int(drawing_height * image_ratio)
        elif self.max_width is not None and self.max_height is not None:
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

    @classmethod
    def from_data(cls, data: Data, image_type: str) -> Drawing:
        """Create a drawing from notebook data."""
        encoded_image = data[image_type]
        fallback_text = data.get("text/plain", "Image")
        decoded_image = base64.b64decode(encoded_image)
        return cls(decoded_image, fallback_text=fallback_text)

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


@functools.lru_cache(maxsize=2 ** 12)
def _render_block_drawing(
    image: bytes, max_width: int, max_height: int, fallback_text: str
) -> Tuple[Text, ...]:
    """Render a representation on an image with unicode characters."""
    try:
        pil_image = Image.open(io.BytesIO(image))
    except PIL.UnidentifiedImageError:
        pil_image = None

    if pil_image is not None:

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
    else:
        rendered_unicode_drawing = (
            text.Text(fallback_text, style=style.Style(color="#BB86FC")),
        )
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
