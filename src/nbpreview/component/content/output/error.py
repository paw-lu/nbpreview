"""Notebook error messages."""


import abc
from typing import Iterator, List

from nbformat.notebooknode import NotebookNode
from rich import ansi, measure
from rich.console import Console, ConsoleOptions, RenderResult
from rich.measure import Measurement
from rich.text import Text


class Error(abc.ABC):
    """An error output."""

    content: List[str]

    def __init__(self, content: List[str]) -> None:
        """Constructor."""
        self.content = content

    def __repr__(self) -> str:
        """String representation of Error."""
        return f"{self.__class__.__qualname__}(content={self.content})"

    @abc.abstractmethod
    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        """Render an error."""

    @abc.abstractmethod
    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered error."""


def render_error(output: NotebookNode) -> Iterator[Error]:
    """Render an error type output.

    Args:
        output (NotebookNode): The error output.

    Yields:
        Generator[Syntax, None, None]: Generate each row of the
            traceback.
    """
    if "traceback" in output:
        error = Traceback.from_output(output)
        yield error


class Traceback(Error):
    """A traceback output."""

    def __init__(self, content: List[str]) -> None:
        """Constructor."""
        super().__init__(content=content)
        decoder = ansi.AnsiDecoder()
        self.min_length = 0
        self.rendered_traceback = []
        for line in self.content:
            rendered_traceback_line = decoder.decode_line(line)
            self.min_length = max(self.min_length, rendered_traceback_line.cell_len)
            self.rendered_traceback.append(rendered_traceback_line)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Text]:
        """Render the traceback."""
        yield from self.rendered_traceback

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered traceback."""
        return measure.Measurement(minimum=self.min_length, maximum=options.max_width)

    @classmethod
    def from_output(cls, output: NotebookNode) -> "Traceback":
        """Create a traceback from a notebook output."""
        content = output["traceback"]
        return cls(content)
