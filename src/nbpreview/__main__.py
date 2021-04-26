"""Command-line interface."""
import sys
from pathlib import Path
from sys import stdout
from typing import Optional

import nbformat
import typer
from rich import console
from rich import traceback

from . import __version__
from . import render

app = typer.Typer()
traceback.install(theme="ansi_dark", show_locals=True)


def version_callback(value: Optional[bool] = None) -> None:
    """Return the package version.

    Args:
        value (bool): Whether to return the version.

    Raises:
        Exit: Exits the command line interface with an exit code of 0.
    """
    if value:
        typer.echo(f"nbpreview {__version__}")
        raise typer.Exit()
    pass


file_argument = typer.Argument(
    ...,
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="A Jupyter Notebook file to render.",
)
theme_option = typer.Option(
    "ansi_dark",
    "--theme",
    "-t",
    help="The theme to use for syntax highlighting. May be 'ansi_light',"
    " 'ansi_dark', or any Pygments theme.",
    envvar="NBPREVIEW_THEME",
)
plain_option = typer.Option(
    None,
    "--plain / --decorated",
    "-p / -d",
    help="Whether to render in a plain style with no boxes, execution"
    " counts, or spacing. By default detected depending on usage context.",
    envvar="NBPREVIEW_PLAIN",
)
version_option = typer.Option(
    None,
    "--version",
    "-V",
    help="Display the version and exit.",
    callback=version_callback,
    is_eager=True,
)


@app.command()
def main(
    file: Path = file_argument,
    theme: str = theme_option,
    plain: Optional[bool] = plain_option,
    version: Optional[bool] = version_option,
) -> None:
    """Render a Jupyter Notebook in the terminal."""
    stdout_console = console.Console()
    stderr_console = console.Console(file=sys.stdout)
    if plain is None:
        # Calling this instead of sys.stdout.isatty because I'm having
        # trouble mocking sys.stdout.isatty
        if stdout.isatty():
            plain = False
        else:
            plain = True
    try:
        notebook_node = nbformat.read(file, as_version=4)
        notebook = render.Notebook(
            notebook_node=notebook_node,
            theme=theme,
            plain=plain,
        )
    except nbformat.reader.NotJSONError:
        stderr_console.print(f"{file} is not a valid Jupyter Notebook path.")
        raise typer.Exit(1)
    stdout_console.print(notebook)


if __name__ == "__main__":
    app()  # pragma: no cover
