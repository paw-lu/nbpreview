"""Input notebook cells."""
from __future__ import annotations

import dataclasses
from typing import Optional
from typing import Union

import pygments
from rich import markdown
from rich import padding
from rich import panel
from rich import syntax
from rich import text
from rich.console import RenderableType
from rich.padding import Padding
from rich.padding import PaddingDimensions
from rich.syntax import Syntax
from rich.text import Text


def box_cell(
    rendered_source: RenderableType, plain: bool, safe_box: Optional[bool] = None
) -> RenderableType:
    """Wrap the content in a box."""
    if plain:
        return rendered_source
    else:
        boxed_cell = panel.Panel(rendered_source, safe_box=safe_box)
        return boxed_cell


@dataclasses.dataclass
class Cell:
    """A generic Jupyter cell."""

    source: str
    plain: bool
    safe_box: Optional[bool] = None

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
    ) -> None:
        """Constructor."""
        super().__init__(source, plain=True)
        self.theme = theme
        self.pad = pad

    def __rich__(self) -> Padding:
        """Render the markdown cell."""
        rendered_markdown = padding.Padding(
            markdown.Markdown(self.source, inline_code_theme=self.theme), pad=self.pad
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
        safe_box: Optional[bool] = None,
    ) -> None:
        """Constructor."""
        super().__init__(source, plain=plain, safe_box=safe_box)
        self.theme = theme
        self.default_lexer_name = default_lexer_name

    def __rich__(self) -> RenderableType:
        """Render the code cell."""
        rendered_code_cell: Union[Syntax, Text]
        rendered_code_cell = syntax.Syntax(
            self.source,
            lexer_name=self.default_lexer_name,
            theme=self.theme,
            background_color="default",
        )
        if self.source.startswith("%%"):
            try:
                magic, body = self.source.split("\n", 1)
                language_name = magic.lstrip("%")
                body_lexer_name = pygments.lexers.get_lexer_by_name(language_name).name
                # Syntax needs a string in the init, so pass an
                # empty string and then pass the actual code to
                # highlight method
                rendered_magic = syntax.Syntax(
                    "",
                    lexer_name=self.default_lexer_name,
                    theme=self.theme,
                    background_color="default",
                ).highlight(magic)
                rendered_body = syntax.Syntax(
                    "",
                    lexer_name=body_lexer_name,
                    theme=self.theme,
                    background_color="default",
                ).highlight(body)
                rendered_code_cell = text.Text().join((rendered_magic, rendered_body))

            except pygments.util.ClassNotFound:
                pass
        return box_cell(rendered_code_cell, plain=self.plain, safe_box=self.safe_box)
