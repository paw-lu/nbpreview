"""Command-line interface."""
import sys
from pathlib import Path

import nbformat
import typer
from rich import console
from rich import traceback

from . import __version__
from . import render

app = typer.Typer()
traceback.install(theme="ansi_dark", show_locals=True)


def version_callback(value: bool) -> None:
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
    "ansi_dark", "--theme", "-t", help="The theme to use for syntax highlighting."
)
version_option = typer.Option(
    None,
    "--version",
    help="Display the version and exit.",
    callback=version_callback,
    is_eager=True,
)


@app.command()
def main(
    file: Path = file_argument,
    theme: str = theme_option,
    version: bool = version_option,
) -> None:
    """Render a Jupyter Notebook in the terminal."""
    stdout_console = console.Console()
    stderr_console = console.Console(file=sys.stdout)

    try:
        notebook = render.Notebook(notebook_path=file, theme=theme, nb_version=4)
    except nbformat.reader.NotJSONError:
        stderr_console.print(f"{file} is not a valid Jupyter Notebook path.")
        raise typer.Exit(1)
    stdout_console.print(notebook)


if __name__ == "__main__":
    app()  # pragma: no cover
