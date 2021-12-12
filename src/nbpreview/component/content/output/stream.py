"""Notebook stream results."""


import dataclasses
from typing import ClassVar, Iterator, Union

from nbformat import NotebookNode
from rich import padding, style, text
from rich.console import ConsoleRenderable
from rich.padding import Padding


@dataclasses.dataclass
class Stream:
    """A stream output."""

    content: str
    name: ClassVar[str]

    def __rich__(self) -> Union[ConsoleRenderable, str]:
        """Render the stream."""
        return self.content

    @classmethod
    def from_output(cls, output: NotebookNode) -> "Stream":
        """Create stream from notebook output."""
        stream_text = output.get("text", "")
        text = stream_text[:-1] if stream_text.endswith("\n") else stream_text
        return cls(text)


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
class StdErr(Stream):
    """A stderr stream output."""

    name: ClassVar[str] = "stderr"

    @classmethod
    def from_output(cls, output: NotebookNode) -> "StdErr":
        """Create stderr from notebook output."""
        if output["name"] != cls.name:
            raise ValueError(f"Output does not contain a {cls.name} stream")
        text = output.get("text", "")
        return cls(text)

    def __rich__(self) -> Padding:
        """Render a stderr stream."""
        stderr_text = text.Text(self.content, style=style.Style(color="color(237)"))
        rendered_stderr = padding.Padding(
            stderr_text, pad=(1, 1, 0, 1), style=style.Style(bgcolor="color(174)")
        )
        return rendered_stderr
