"""Notebook stream results."""
from __future__ import annotations

import dataclasses
from typing import ClassVar
from typing import Iterator
from typing import Union

from nbformat import NotebookNode
from rich import style
from rich import text
from rich.console import ConsoleRenderable
from rich.text import Text


def render_stream(output: NotebookNode) -> Iterator[Stream]:
    """Render a stream type output.

    Args:
        output (NotebookNode): The stream output.

    Yields:
        Stream: The rendered stream.
    """
    stream: Stream
    name = output.get("name")
    if name == "stderr":
        stream = StdErr.from_output(output)
    else:
        stream = Stream.from_output(output)
    yield stream


@dataclasses.dataclass
class Stream:
    """A stream output."""

    content: str
    name: ClassVar[str]

    def __rich__(self) -> Union[ConsoleRenderable, str]:
        """Render the stream."""
        return self.content

    @classmethod
    def from_output(cls, output: NotebookNode) -> Stream:
        """Create stream from notebook output."""
        text = output.get("text", "")
        return cls(text)


@dataclasses.dataclass
class StdErr(Stream):
    """A stderr stream output."""

    name: ClassVar[str] = "stderr"

    @classmethod
    def from_output(cls, output: NotebookNode) -> StdErr:
        """Create stderr from notebook output."""
        if output["name"] != cls.name:
            raise ValueError(f"Output does not contain a {cls.name} stream")
        text = output.get("text", "")
        return cls(text)

    def __rich__(self) -> Text:
        """Render a stderr stream."""
        rendered_stderr = text.Text(
            self.content, style=style.Style(color="color(237)", bgcolor="color(174)")
        )
        return rendered_stderr
