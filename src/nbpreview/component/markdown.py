"""Override rich's markdown renderer with custom components."""
from __future__ import annotations

import io
import os
import pathlib
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Literal
from typing import Optional
from typing import Union

import httpx
import validators
import yarl
from picharsso.draw import gradient
from PIL import Image
from rich import _loop
from rich import markdown
from rich import rule
from rich import segment
from rich import style
from rich import syntax
from rich import text
from rich.console import Console
from rich.console import ConsoleOptions
from rich.console import JustifyMethod
from rich.console import RenderResult
from rich.style import Style

from nbpreview.component.content.output.result import drawing
from nbpreview.component.content.output.result import link


class CustomCodeBlock(markdown.CodeBlock):
    """A custom code block with syntax highlighting."""

    style_name = "none"

    def __init__(self, lexer_name: str, theme: str) -> None:
        """Constructor."""
        super().__init__(lexer_name=lexer_name, theme=theme)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render the custom code block."""
        code = textwrap.indent(str(self.text).rstrip(), prefix=" " * 4)
        rendered_syntax = syntax.Syntax(
            code, self.lexer_name, theme=self.theme, background_color="default"
        )
        yield rendered_syntax


class CustomHeading(markdown.Heading):
    """A custom rendered markdown heading."""

    def __init__(self, level: int) -> None:
        """Constructor."""
        self.level = level
        if self.level == 1:
            self.color = "#6002EE"
            self.style_name = style.Style(
                color="#FFFFFF", bgcolor=self.color, bold=True
            )  # type: ignore[assignment]
        else:
            self.color = "#03DAC5"
            self.style_name = style.Style(
                color=self.color, bold=True
            )  # type: ignore[assignment]

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render the custom markdown heading."""
        source_text = self.text
        source_text.justify = "left"
        if self.level == 1:
            if source_text.cell_len < console.width:
                source_text = text.Text(" ", style=self.style_name) + source_text
            if source_text.cell_len < console.width:
                source_text = source_text + text.Text(" ", style=self.style_name)

            yield source_text
        else:
            source_text = (
                text.Text(self.level * "#" + " ", style=self.style_name) + source_text
            )
            if self.level <= 3:
                yield text.Text("")
            yield source_text

        if self.level < 3:
            yield rule.Rule(style=style.Style(color=self.color, dim=True, bold=False))


class CustomBlockQuote(markdown.BlockQuote):
    """A custom block quote."""

    style_name = style.Style(dim=True)  # type: ignore[assignment]


class CustomHorizontalRule(markdown.HorizontalRule):
    """A customized horizontal rule to divide sections."""

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render the horizontal rule."""
        yield rule.Rule(style="none")


class CustomListItem(markdown.ListItem):
    """A custom list element."""

    def render_bullet(self, console: Console, options: ConsoleOptions) -> RenderResult:
        """Render a markdown bullet."""
        render_options = options.update(width=options.max_width - 3)
        lines = console.render_lines(self.elements, render_options, style=self.style)
        bullet_style = console.get_style("none")

        bullet = segment.Segment(" • ", bullet_style)
        padding = segment.Segment(" " * 3, bullet_style)
        new_line = segment.Segment("\n")
        for first, line in _loop.loop_first(lines):
            yield bullet if first else padding
            yield from line
            yield new_line

    def render_number(
        self, console: Console, options: ConsoleOptions, number: int, last_number: int
    ) -> RenderResult:
        """Render a markdown number."""
        number_width = len(str(last_number)) + 2
        render_options = options.update(width=options.max_width - number_width)
        lines = console.render_lines(self.elements, render_options, style=self.style)
        number_style = console.get_style("none")

        new_line = segment.Segment("\n")
        padding = segment.Segment(" " * number_width, number_style)
        numeral = segment.Segment(
            f"{number}".rjust(number_width - 1) + " ", number_style
        )
        for first, line in _loop.loop_first(lines):
            yield numeral if first else padding
            yield from line
            yield new_line


class CustomImageItem(markdown.ImageItem):
    """Renders a placeholder for an image."""

    nerd_font: bool = False
    unicode: bool = True
    image: bool = True
    image_type: Literal["block", "character", "braille", None] = "block"
    color: bool = True
    negative_space: bool = True
    characters: str = gradient.DEFAULT_CHARSET
    hyperlinks_: bool = True
    files: bool = True
    hide_hyperlink_hints: bool = False

    def __init__(self, destination: str, hyperlinks: bool) -> None:
        """Constructor."""
        content: Union[None, Path, BytesIO]
        if not validators.url(destination):
            self.path = pathlib.Path(destination).resolve()
            destination = f"file://{os.fsdecode(self.path)}"
            content = self.path
        else:
            self.path = pathlib.Path(yarl.URL(destination).path)
            try:
                response = httpx.get(destination)
            except httpx.RequestError:
                content = None
            else:
                content = io.BytesIO(response.content)
        self.extension = self.path.suffix.lstrip(".")

        if content is not None:
            with Image.open(content) as image:
                with io.BytesIO() as output:
                    image.save(output, format=self.extension)
                    self.image_data = output.getvalue()
        else:
            self.image_data = b""

        super().__init__(destination=destination, hyperlinks=hyperlinks)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render the image."""
        title = self.text.plain or self.destination
        image_link = link.ImageLink(
            content=self.image_data,
            file_extension=self.extension,
            unicode=self.unicode,
            hyperlinks=self.hyperlinks_,
            nerd_font=self.nerd_font,
            files=self.files,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
            subject=title,
        )
        yield image_link

        if self.image:
            fallback_title = self.destination.strip("/").rsplit("/", 1)[-1]
            rendered_drawing = drawing.choose_drawing(
                image=self.image_data,
                fallback_text=self.text.plain or fallback_title,
                image_type=f"image/{self.extension}",
                image_drawing=self.image_type,
                unicode=self.unicode,
                color=self.color,
                negative_space=self.negative_space,
                characters=self.characters,
            )
            if rendered_drawing is not None:
                yield text.Text("")
                yield rendered_drawing


class CustomMarkdown(markdown.Markdown):
    """A custom markdown renderer."""

    def __init__(
        self,
        markup: str,
        code_theme: str = "monokai",
        justify: Optional[JustifyMethod] = None,
        style: Union[str, Style] = "none",
        hyperlinks: bool = True,
        inline_code_lexer: Optional[str] = None,
        inline_code_theme: Optional[str] = None,
        nerd_font: bool = False,
        unicode: bool = True,
        image: bool = True,
        image_type: Literal["block", "character", "braille", None] = "block",
        color: bool = True,
        negative_space: bool = True,
        characters: str = gradient.DEFAULT_CHARSET,
        hyperlinks_: bool = True,
        files: bool = True,
        hide_hyperlink_hints: bool = False,
    ):
        """Constructor."""
        self.elements["code_block"] = CustomCodeBlock
        self.elements["heading"] = CustomHeading
        self.elements["block_quote"] = CustomBlockQuote
        self.elements["thematic_break"] = CustomHorizontalRule
        self.elements["item"] = CustomListItem
        self.elements["image"] = CustomImageItem

        CustomImageItem.nerd_font = nerd_font
        CustomImageItem.image = image
        CustomImageItem.unicode = unicode
        CustomImageItem.image_type = image_type
        CustomImageItem.color = color
        CustomImageItem.negative_space = negative_space
        CustomImageItem.characters = characters
        CustomImageItem.hyperlinks_ = hyperlinks_
        CustomImageItem.files = files
        CustomImageItem.hide_hyperlink_hints = hide_hyperlink_hints

        super().__init__(
            markup=markup,
            code_theme=code_theme,
            justify=justify,
            style=style,
            hyperlinks=hyperlinks,
            inline_code_lexer=inline_code_lexer,
            inline_code_theme=inline_code_theme,
        )
