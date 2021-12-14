"""Command-line interface."""
import enum
import functools
import itertools
import os
import sys
import textwrap
import typing
from pathlib import Path
from typing import Iterable, List, Optional, Union

import nbformat
import typer
from click import Context, Parameter
from pygments import styles
from rich import box, console, panel, style, syntax, text, traceback
from rich.console import Console

from nbpreview import __version__, cli_choices, errors, notebook
from nbpreview.component.content.output.result import drawing
from nbpreview.component.content.output.result.drawing import ImageDrawingEnum

app = typer.Typer()
traceback.install(theme="material")


class ColorSystemEnum(str, cli_choices.LowerNameEnum):
    """The color systems supported by terminals."""

    STANDARD = enum.auto()
    EIGHT_BIT = "256"
    TRUECOLOR = enum.auto()
    WINDOWS = enum.auto()
    NONE = enum.auto()


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
no_files_option = typer.Option(
    False,
    "--no-files",
    "-l",
    help="Do not write temporary files for previews.",
    envvar="NBPREVIEW_NO_FILES",
)
positive_space_option = typer.Option(
    False,
    "--positive-space",
    "-p",
    help="Draw character images in positive space."
    " Generally negative space works best on charts or images with"
    " light backgrounds, while positive space will look best on dark"
    " background images. Only has effect on character drawings. By"
    " default set to negative space.",
    envvar="NBPREVIEW_POSITIVE_SPACE",
)
hyperlinks_option = typer.Option(
    None,
    "--hyperlinks / --no-hyperlinks",
    "-k / -r",
    help="Whether to use terminal hyperlinks when rendering content."
    " By default autodetects.",
    envvar="NBPREVIEW_HYPERLINKS",
)
hide_hyperlink_hints_option = typer.Option(
    False,
    "--hide-hyperlink-hints",
    "-y",
    help="Hide text hints that hyperlinks are clickable.",
    envvar="NBPREVIEW_HIDE_HYPERLINK_HINTS",
)
images_option = typer.Option(
    False,
    "--images",
    "-i",
    help="Render images. See image-drawing-option for render modes.",
    envvar="NBPREVIEW_IMAGES",
)
image_drawing_option = typer.Option(
    None,
    "--image-drawing",
    "--id",
    help="The type of image drawing. Accepted values are 'block',"
    " 'character', or 'braille'. 'block' might raise issues on Windows.",
    envvar="NBPREVIEW_IMAGE_DRAWING",
    case_sensitive=False,
)
color_option = typer.Option(
    None,
    "--color / --no-color",
    "-c / -o",
    help="Whether to render with color. By default will autodetect."
    " Additionally respects NO_COLOR, NBPREVIEW_NO_COLOR, and"
    " TERM='dumb'.",
    envvar="NBPREVIEW_COLOR",
)
color_system_option = typer.Option(
    None,
    "--color-system",
    "--cs",
    help="The type of color system to use.",
    envvar="NBPREVIEW_COLOR_SYSTEM",
    case_sensitive=False,
)


def _envvar_to_bool(envvar: str) -> bool:
    """Convert environmental variable values to bool."""
    envvar_value = os.environ.get(envvar, False)
    envvar_bool = bool(envvar_value) and (envvar != "0") and (envvar.lower() != "false")
    return envvar_bool


def _detect_no_color() -> Union[bool, None]:
    """Detect if color should be used."""
    no_color_variables = (
        _envvar_to_bool("NO_COLOR"),
        _envvar_to_bool("NBPREVIEW_NO_COLOR"),
        os.environ.get("TERM", "smart").lower() == "dumb",
    )
    force_no_color = any(no_color_variables)
    return force_no_color


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


def print_error(console: Console, message: str) -> None:
    """Print stylized error message to the terminal."""
    rich_message = text.Text(message, style=style.Style(color="#B3261E"))
    console.print(rich_message)


def _check_image_drawing_option(
    image_drawing: Union[ImageDrawingEnum, None], stderr_console: Console
) -> None:
    """Check if the image drawing option is valid."""
    if image_drawing == drawing.ImageDrawingEnum.BLOCK:
        try:
            import terminedia  # noqa: F401
        except ModuleNotFoundError as exception:
            print_error(
                stderr_console,
                message=f"--image-drawing='{image_drawing.value}' cannot be"
                " used on this system. This might be because it is"
                " being run on Windows.",
            )
            raise typer.Exit(1) from exception


@app.command()
def main(
    file: Path = file_argument,
    theme: Optional[str] = theme_option,
    list_themes: Optional[bool] = list_themes_option,
    plain: Optional[bool] = plain_option,
    unicode: Optional[bool] = unicode_option,
    hide_output: bool = hide_output_option,
    nerd_font: bool = nerd_font_option,
    no_files: bool = no_files_option,
    positive_space: bool = positive_space_option,
    hyperlinks: bool = hyperlinks_option,
    hide_hyperlink_hints: bool = hide_hyperlink_hints_option,
    images: Optional[bool] = images_option,
    image_drawing: Optional[ImageDrawingEnum] = image_drawing_option,
    color: Optional[bool] = color_option,
    color_system: Optional[ColorSystemEnum] = color_system_option,
    width: Optional[int] = width_option,
    version: Optional[bool] = version_option,
) -> None:
    """Render a Jupyter Notebook in the terminal."""
    if color is None and _detect_no_color():
        color = False
    no_color = not color if color is not None else color
    _color_system: Union[str, None]
    if color_system is None:
        _color_system = "auto"
    elif color_system == "none":
        _color_system = None
    else:
        _color_system = color_system

    output_console = functools.partial(
        console.Console,
        width=width,
        no_color=no_color,
        emoji=unicode if unicode is not None else True,
        color_system=_color_system,
    )
    stdout_console = output_console(file=sys.stdout)
    stderr_console = output_console(file=sys.stderr)
    _check_image_drawing_option(image_drawing, stderr_console=stderr_console)
    try:
        files = not no_files
        negative_space = not positive_space
        translated_theme = _translate_theme(theme)
        rendered_notebook = notebook.Notebook.from_file(
            file,
            theme=translated_theme,
            hide_output=hide_output,
            plain=plain,
            unicode=unicode,
            nerd_font=nerd_font,
            files=files,
            negative_space=negative_space,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
            images=images,
            image_drawing=image_drawing,
            color=color,
        )

    except (nbformat.reader.NotJSONError, errors.InvalidNotebookError) as exception:
        print_error(
            stderr_console, message=f"{file} is not a valid Jupyter Notebook path."
        )
        raise typer.Exit(1) from exception

    else:
        stdout_console.print(rendered_notebook)


if __name__ == "__main__":
    app()  # pragma: no cover
