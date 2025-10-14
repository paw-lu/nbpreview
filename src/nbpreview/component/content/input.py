"""Input notebook cells."""
import dataclasses
import functools
from pathlib import Path

import pygments
from rich import console, padding, panel, syntax
from rich.console import Group, RenderableType
from rich.padding import Padding, PaddingDimensions
from rich.syntax import Syntax

from nbpreview.component import markdown
from nbpreview.component.content.output.result.drawing import ImageDrawing


def box_cell(
    rendered_source: RenderableType, plain: bool, safe_box: bool | None = None
) -> RenderableType:
    """Wrap the content in a box."""
    if plain:
        return rendered_source
    boxed_cell = panel.Panel(rendered_source, safe_box=safe_box)
    return boxed_cell


@dataclasses.dataclass
class Cell:
    """A generic Jupyter cell."""

    source: str
    plain: bool
    safe_box: bool | None = None

    def __rich__(self) -> RenderableType:
        """Render the cell."""
        return box_cell(self.source, plain=self.plain, safe_box=self.safe_box)


@dataclasses.dataclass(init=False)
class MarkdownCell(Cell):
    """A Jupyter markdown cell."""

    def __init__(
        self,
        source: str,
        theme: str,
        pad: PaddingDimensions,
        nerd_font: bool,
        unicode: bool,
        images: bool,
        image_drawing: ImageDrawing,
        color: bool,
        negative_space: bool,
        hyperlinks: bool,
        files: bool,
        hide_hyperlink_hints: bool,
        relative_dir: Path,
        characters: str | None = None,
    ) -> None:
        """Constructor."""
        super().__init__(source, plain=True)
        self.theme = theme
        self.pad = pad
        self.nerd_font = nerd_font
        self.unicode = unicode
        self.images = images
        self.image_drawing = image_drawing
        self.color = color
        self.negative_space = negative_space
        self.hyperlinks = hyperlinks
        self.files = files
        self.hide_hyperlink_hints = hide_hyperlink_hints
        self.characters = characters
        self.relative_dir = relative_dir

    def __rich__(self) -> Padding:
        """Render the markdown cell."""
        rendered_markdown = padding.Padding(
            markdown.CustomMarkdown(
                self.source,
                theme=self.theme,
                nerd_font=self.nerd_font,
                unicode=self.unicode,
                images=self.images,
                image_drawing=self.image_drawing,
                color=self.color,
                negative_space=self.negative_space,
                hyperlinks=self.hyperlinks,
                files=self.files,
                hide_hyperlink_hints=self.hide_hyperlink_hints,
                characters=self.characters,
                relative_dir=self.relative_dir,
            ),
            pad=self.pad,
        )
        return rendered_markdown


@dataclasses.dataclass(init=False)
class CodeCell(Cell):
    """A Jupyter code cell."""

    def __init__(
        self,
        source: str,
        plain: bool,
        theme: str,
        default_lexer_name: str,
        safe_box: bool | None = None,
        line_numbers: bool = False,
        code_wrap: bool = False,
    ) -> None:
        """Constructor."""
        super().__init__(source, plain=plain, safe_box=safe_box)
        self.theme = theme
        self.default_lexer_name = default_lexer_name
        self.line_numbers = line_numbers
        self.code_wrap = code_wrap

    def __rich__(self) -> RenderableType:
        """Render the code cell."""
        rendered_code_cell: Syntax | Group
        code_cell_renderer = functools.partial(
            syntax.Syntax,
            lexer=self.default_lexer_name,
            theme=self.theme,
            background_color="default",
            line_numbers=self.line_numbers,
            word_wrap=self.code_wrap,
        )
        rendered_code_cell = code_cell_renderer(self.source)
        if self.source.startswith("%%"):
            try:
                magic, body = self.source.split("\n", 1)
                language_name = magic.lstrip("%")
                body_lexer_name = pygments.lexers.get_lexer_by_name(language_name).name
                rendered_magic = code_cell_renderer(magic)
                rendered_body = code_cell_renderer(
                    body, lexer=body_lexer_name, start_line=2
                )
                rendered_code_cell = console.Group(rendered_magic, rendered_body)

            except pygments.util.ClassNotFound:
                pass
        return box_cell(rendered_code_cell, plain=self.plain, safe_box=self.safe_box)
