"""Command-line interface."""
import sys
from pathlib import Path
from typing import Optional

import nbformat
import typer
from rich import console
from rich import traceback

from nbpreview import __version__
from nbpreview import notebook

app = typer.Typer()
traceback.install(theme="ansi_dark")


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
hide_output_option = typer.Option(
    False,
    "--hide-output",
    "-h",
    help="Whether to hide the notebook outputs.",
    envvar="NBPREVIEW_HIDE_OUTPUT",
)
plain_option = typer.Option(
    None,
    "--plain / --decorated",
    "-p / -d",
    help="Whether to render in a plain style with no boxes, execution"
    " counts, or spacing. By default detected depending on usage context.",
    envvar="NBPREVIEW_PLAIN",
)
width_option = typer.Option(
    None,
    "--width",
    "-w",
    help="Explicitly set the width of the render instead of determining automatically.",
    envvar="NBPREVIEW_WIDTH",
)
unicode_option = typer.Option(
    None,
    help="Force the display or replacement of unicode chartacters"
    " instead of determining automatically.",
    envvar="NBPREVIEW_UNICODE",
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
    width: Optional[int] = width_option,
    hide_output: bool = hide_output_option,
    plain: Optional[bool] = plain_option,
    unicode: Optional[bool] = unicode_option,
    version: Optional[bool] = version_option,
) -> None:
    """Render a Jupyter Notebook in the terminal."""
    stdout_console = console.Console(file=sys.stdout, width=width)
    stderr_console = console.Console(file=sys.stderr)
    try:
        rendered_notebook = notebook.Notebook.from_file(
            file,
            theme=theme,
            hide_output=hide_output,
            plain=plain,
            unicode=unicode,
        )
    except nbformat.reader.NotJSONError:
        stderr_console.print(f"{file} is not a valid Jupyter Notebook path.")
        raise typer.Exit(1)

    stdout_console.print(rendered_notebook)


if __name__ == "__main__":
    app()  # pragma: no cover
