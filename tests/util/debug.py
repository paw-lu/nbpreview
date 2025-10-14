"""Utilities for debugging failing tests."""
import difflib
import pathlib
from collections.abc import Iterator


def diff(
    a: str, b: str, a_name: str = "", b_name: str = "", n: int = 3
) -> Iterator[str]:
    """Yield the diff between two strings."""
    yield from difflib.context_diff(
        a=a.splitlines(), b=b.splitlines(), fromfile=a_name, tofile=b_name, n=n
    )


def write(content: str, filename: str, encoding: str | None = "utf8") -> None:
    """Write content to file."""
    pathlib.Path(filename).with_suffix(".txt").write_text(content, encoding=encoding)
