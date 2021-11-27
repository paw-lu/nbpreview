"""Command-line interface."""
import functools
import itertools
import sys
import textwrap
import typing
from pathlib import Path
from typing import Iterable, List, Optional, Union

import nbformat
import typer
from click import Context, Parameter
from pygments import styles
from rich import box, console, panel, syntax, traceback

from nbpreview import __version__, errors, notebook

app = typer.Typer()
traceback.install(theme="material")


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


def _get_all_available_themes(list_duplicate_alias: bool = False) -> Iterable[str]:
    """Return the available theme names."""
    theme_alias: Iterable[str] = ["light", "dark"]
    if list_duplicate_alias:
        theme_alias = itertools.chain(
            theme_alias, (f"ansi_{alias}" for alias in theme_alias)
        )
    available_themes = itertools.chain(styles.get_all_styles(), theme_alias)
    yield from available_themes


def list_themes_callback(value: Optional[bool] = None) -> None:
    """Render a preview of all available themes."""
    example_code = textwrap.dedent(
        '''\
    """Example syntax highlighting."""
    from typing import Iterator

    class Math:
        """An example class."""

        @staticmethod
        def fib(n: int) -> Iterator[int]:
            """Fibonacci series up to n."""
            a, b = 0, 1  # Manually set first two terms
            while a < n:
                yield a
                a, b = b, a + b

    result = sum(Math.fib(42))
    print(f"The answer is {result}")
    '''
    )
    if value:
        stdout_console = console.Console(file=sys.stdout)
        panel_width = min(stdout_console.width, 88)
        for theme in _get_all_available_themes(list_duplicate_alias=False):
            translated_theme = _translate_theme(theme)
            theme_title = (
                f"{theme} / ansi_{theme}" if theme in ("dark", "light") else theme
            )
            if stdout_console.is_terminal:
                theme_example = syntax.Syntax(
                    example_code,
                    theme=translated_theme,
                    background_color="default",
                    lexer_name="python",
                )
                theme_example_panel = panel.Panel(
                    theme_example,
                    title=theme_title,
                    box=box.ROUNDED,
                    title_align="left",
                    expand=False,
                    padding=(1, 2, 1, 2),
                    safe_box=True,
                    width=panel_width,
                )
                stdout_console.print(theme_example_panel)
            else:
                stdout_console.print(theme_title)
        raise typer.Exit()
    pass


def complete_theme(ctx: Context, param: Parameter, incomplete: str) -> List[str]:
    """Completion options for theme argument."""
    available_themes = _get_all_available_themes(list_duplicate_alias=True)
    completion_suggestions = [
        theme for theme in available_themes if theme.startswith(incomplete.lower())
    ]
    return completion_suggestions


file_argument = typer.Argument(
    ...,
    exists=True,
    file_okay=True,
    dir_okay=False,
    readable=True,
    help="A Jupyter Notebook file to render.",
)
theme_option = typer.Option(
    None,
    "--theme",
    "-t",
    help="The theme to use for syntax highlighting. May be 'light',"
    " 'dark', or any Pygments theme. By default adjusts based on"
    " terminal. Call --list-themes to preview all available themes.",
    envvar="NBPREVIEW_THEME",
    shell_complete=complete_theme,
)
list_themes_option = typer.Option(
    None,
    "--list-themes",
    "--lt",
    help="Display a preview all available themes.",
    callback=list_themes_callback,
    is_eager=True,
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
    "--unicode / --no-unicode",
    "-u / -x",
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
nerd_font_option = typer.Option(
    False,
    "--nerd-font",
    "-n",
    help="Whether to use Nerd Font icons.",
    envvar="NBPREVIEW_NERD_FONT",
)
positive_space_option = typer.Option(
    False,
    "--positive-space",
    "-p",
    help="Draw character images in positive space."
    " Generally negative space works best on charts or images with"
    " light backgrounds, while positive space will look best on dark"
    " background images. Only has effect on character drawings. By "
    " default set to negative space.",
    envvar="NBPREVIEW_POSITIVE_SPACE",
)
images_option = typer.Option(
    False,
    "--images",
    "-i",
    help="Render images. See image-drawing-option for render modes.",
    envvar="NBPREVIEW_IMAGES",
)


@typing.overload
def _translate_theme(theme_argument: str) -> str:
    """Convert theme argument to one recognized by rich."""
    ...


@typing.overload
def _translate_theme(theme_argument: None) -> None:
    """Convert theme argument to one recognized by rich."""
    ...


def _translate_theme(theme_argument: Union[str, None]) -> Union[str, None]:
    """Convert theme argument to one recognized by rich."""
    translated_theme: Union[str, None]
    if theme_argument is not None:
        theme_alias = {
            "dark": "ansi_dark",
            "light": "ansi_light",
        }
        lowered_theme_argument = theme_argument.lower()
        translated_theme = theme_alias.get(
            lowered_theme_argument, lowered_theme_argument
        )
    else:
        translated_theme = None
    return translated_theme


@app.command()
def main(
    file: Path = file_argument,
    theme: Optional[str] = theme_option,
    list_themes: Optional[bool] = list_themes_option,
    plain: Optional[bool] = plain_option,
    unicode: Optional[bool] = unicode_option,
    hide_output: bool = hide_output_option,
    nerd_font: bool = nerd_font_option,
    positive_space: bool = positive_space_option,
    images: Optional[bool] = images_option,
    width: Optional[int] = width_option,
    version: Optional[bool] = version_option,
) -> None:
    """Render a Jupyter Notebook in the terminal."""
    output_console = functools.partial(
        console.Console,
        width=width,
        emoji=unicode if unicode is not None else True,
    )
    stdout_console = output_console(file=sys.stdout)
    stderr_console = output_console(file=sys.stderr)
    try:
        negative_space = not positive_space
        translated_theme = _translate_theme(theme)
        rendered_notebook = notebook.Notebook.from_file(
            file,
            theme=translated_theme,
            hide_output=hide_output,
            plain=plain,
            unicode=unicode,
            nerd_font=nerd_font,
            negative_space=negative_space,
            images=images,
        )
    except (nbformat.reader.NotJSONError, errors.InvalidNotebookError) as exception:
        stderr_console.print(f"{file} is not a valid Jupyter Notebook path.")
        raise typer.Exit(1) from exception

    stdout_console.print(rendered_notebook)


if __name__ == "__main__":
    app()  # pragma: no cover
