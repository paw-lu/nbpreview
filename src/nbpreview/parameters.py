"""Command line interface parameters."""
import os
import pathlib
import sys
import textwrap
from pathlib import Path
from typing import Any, Callable, List, Literal, Optional, Type, Union

import typer
from click import Context, Parameter
from click.shell_completion import CompletionItem
from rich import box, console, panel, syntax

from nbpreview import __version__, option_values
from nbpreview.option_values import ColorSystemEnum, ImageDrawingEnum, ThemeEnum


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


def _theme_callback(theme_argument: ThemeEnum) -> str:
    """Convert theme argument to one recognized by rich."""
    translated_theme = _translate_theme(theme_argument.value)
    return translated_theme


def _translate_theme(theme_value: str) -> str:
    """Translate the theme from CLI value to pygments theme."""
    theme_alias = {
        "dark": "ansi_dark",
        "light": "ansi_light",
    }
    lowered_theme_argument = theme_value.lower()
    pygments_theme = theme_alias.get(lowered_theme_argument, lowered_theme_argument)
    return pygments_theme


def _list_themes_callback(value: Optional[bool] = None) -> None:
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
        for theme in option_values.get_all_available_themes(list_duplicate_alias=False):
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


def _image_drawing_option_callback(
    ctx: Context, image_drawing_value: Union[ImageDrawingEnum, None]
) -> Union[str, None]:
    """Check if the image drawing option is valid."""
    if image_drawing_value == option_values.ImageDrawingEnum.BLOCK:
        try:
            import terminedia  # noqa: F401

        except ModuleNotFoundError as exception:
            message = (
                f"'{image_drawing_value.value}' cannot be"
                " used on this system. This might be because it is"
                " being run on Windows."
            )
            raise typer.BadParameter(message=message, ctx=ctx) from exception
    if image_drawing_value is None:
        return image_drawing_value

    else:
        return image_drawing_value.value


def _stdin_path_callback(ctx: Context, file_value: List[Path]) -> List[Path]:
    """Return '-', which signifies stdin, if no files are provided."""
    cleaned_file = file_value if file_value else [pathlib.Path("-")]
    return cleaned_file


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


def _color_option_callback(color_value: Union[bool, None]) -> Union[bool, None]:
    """Detect if any no color environmental variables are set."""
    color = False if color_value is None and _detect_no_color() else color_value
    return color


def _color_system_callback(
    color_system_value: Union[ColorSystemEnum, None]
) -> Union[Literal["auto", "standard", "256", "truecolor", "windows"], None]:
    """Translate the color system values to ones rich understands."""
    color_system: Union[
        Literal["auto", "standard", "256", "truecolor", "windows"], None
    ]
    if color_system_value is None:
        color_system = "auto"

    elif color_system_value == "none":
        color_system = None

    else:
        color_system = color_system_value.value
    return color_system


def stdin_path_argument(
    metavar: Optional[str] = None,
    expose_value: bool = True,
    is_eager: bool = False,
    envvar: Optional[Union[str, List[str]]] = None,
    shell_complete: Optional[
        Callable[
            [Context, Parameter, str],
            Union[List[CompletionItem], List[str]],
        ]
    ] = None,
    autocompletion: Optional[Callable[..., Any]] = None,
    show_default: Union[bool, str] = True,
    show_choices: bool = True,
    show_envvar: bool = True,
    help: Optional[str] = None,
    hidden: bool = False,
    case_sensitive: bool = True,
    min: Optional[Union[int, float]] = None,
    max: Optional[Union[int, float]] = None,
    clamp: bool = False,
    formats: Optional[List[str]] = None,
    mode: Optional[str] = None,
    encoding: Optional[str] = None,
    errors: Optional[str] = "strict",
    lazy: Optional[bool] = None,
    atomic: bool = False,
    writable: bool = False,
    resolve_path: bool = False,
    path_type: Union[None, Type[str], Type[bytes]] = None,
) -> Any:
    """A required file argument that also reads from stdin.

    Sets default value to '-' when piped terminal std in detected.
    """
    default: Any
    is_piped = not sys.stdin.isatty()
    # I'm unable to mock sys.stdin.isatty
    # Typer/Click does not allow default values when unlimited argument
    # values are accepted
    # None is one exception, so later processing can transform it to a
    # hyphen
    if is_piped:  # pragma: no branch
        default = None
    else:  # pragma: no cover
        default = ...
    exists = readable = not is_piped
    argument = typer.Argument(
        default=default,
        callback=_stdin_path_callback,
        metavar=metavar,
        expose_value=expose_value,
        is_eager=is_eager,
        envvar=envvar,
        shell_complete=shell_complete,
        autocompletion=autocompletion,
        show_default=show_default,
        show_choices=show_choices,
        show_envvar=show_envvar,
        help=help,
        hidden=hidden,
        case_sensitive=case_sensitive,
        min=min,
        max=max,
        clamp=clamp,
        formats=formats,
        mode=mode,
        encoding=encoding,
        errors=errors,
        lazy=lazy,
        atomic=atomic,
        exists=exists,
        file_okay=True,
        dir_okay=False,
        writable=writable,
        readable=readable,
        resolve_path=resolve_path,
        allow_dash=True,
        path_type=path_type,
    )
    return argument


file_argument = stdin_path_argument(
    help="Jupyter notebook file(s) to render on the terminal."
    " Use a dash ('-') or pipe in data to the command to read from"
    " standard input."
)
theme_option = typer.Option(
    "dark",
    "--theme",
    "-t",
    help="The theme to use for syntax highlighting."
    " Call '--list-themes' to preview all available themes.",
    envvar="NBPREVIEW_THEME",
    callback=_theme_callback,
)
list_themes_option = typer.Option(
    None,
    "--list-themes",
    "--lt",
    help="Display a preview of all available themes.",
    callback=_list_themes_callback,
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
    help="Force the display or replacement of Unicode characters"
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
    "-s",
    help="Draw character images in positive space."
    " Generally, negative space works best on charts or images with"
    " light backgrounds, while positive space will look best on dark"
    " background images. Only affects character drawings. By default"
    " set to negative space.",
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
no_images_option = typer.Option(
    None,
    "--images / --no-images",
    "-i / -e",
    help="Whether to render images. By default will autodetect."
    " May significantly affect performance.",
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
    callback=_image_drawing_option_callback,
)
color_option = typer.Option(
    None,
    "--color / --no-color",
    "-c / -o",
    help="Whether to render with color. By default will autodetect."
    " Additionally respects NO_COLOR, NBPREVIEW_NO_COLOR, and"
    " TERM='dumb'.",
    envvar="NBPREVIEW_COLOR",
    callback=_color_option_callback,
)
color_system_option = typer.Option(
    None,
    "--color-system",
    "--cs",
    help="The type of color system to use.",
    envvar="NBPREVIEW_COLOR_SYSTEM",
    case_sensitive=False,
    callback=_color_system_callback,
)
line_numbers_option = typer.Option(
    False,
    "--line-numbers",
    "-m",
    help="Show line numbers for code in cells.",
    envvar="NBPREVIEW_LINE_NUMBERS",
)
code_wrap_option = typer.Option(
    False,
    "--code-wrap",
    "-q",
    help="Wrap code onto the next line if it does not fit in width."
    " May be used with --line-numbers for clarity.",
    envvar="NBPREVIEW_CODE_WRAP",
)
paging_option = typer.Option(
    None,
    "--paging / --no-paging",
    "-g / -f",
    help="Whether to display the output in a pager." " By default autodetects.",
    envvar="NBPREVIEW_PAGING",
)
