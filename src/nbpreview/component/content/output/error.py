"""Notebook error messages."""
from __future__ import annotations

import dataclasses
from typing import Iterator
from typing import List
from typing import Union

from nbformat.notebooknode import NotebookNode
from rich import syntax
from rich.console import ConsoleRenderable
from rich.syntax import Syntax


def render_error(output: NotebookNode, theme: str) -> Iterator[Error]:
    """Render an error type output.

    Args:
        output (NotebookNode): The error output.
        theme (str): The Pygments syntax theme to use.

    Yields:
        Generator[Syntax, None, None]: Generate each row of the
            traceback.
    """
    if "traceback" in output:
        error = Traceback.from_output(output, theme=theme)
        yield error


@dataclasses.dataclass
class Error:
    """An error output."""

    content: List[str]

    def __rich__(self) -> Union[ConsoleRenderable, str]:
        """Render the error."""
        rendered_error = "\n".join(self.content)
        return rendered_error


@dataclasses.dataclass
class Traceback(Error):
    """A traceback output."""

    content: List[str]
    theme: str
    lexer_name: str = "IPython Traceback"

    def __rich__(self) -> Syntax:
        """Render the traceback."""
        full_traceback = "\n".join(self.content)
        # A background here looks odd--highlighting only certain words.
        rendered_traceback = syntax.Syntax(
            full_traceback,
            lexer_name=self.lexer_name,
            theme=self.theme,
            background_color="default",
        )
        return rendered_traceback

    @classmethod
    def from_output(cls, output: NotebookNode, theme: str) -> Traceback:
        """Create a traceback from a notebook output."""
        content = output["traceback"]
        return cls(content, theme=theme)
