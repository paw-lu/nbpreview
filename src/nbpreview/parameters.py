"""Command line interface parameters."""
import enum
import itertools
import sys
import textwrap
import typing
from typing import Any, Iterable, List, Optional, Union

import typer
from click import Context, Parameter
from pygments import styles
from rich import box, console, panel, syntax

from nbpreview import __version__


class LowerNameEnum(enum.Enum):
    """Enum base class that sets value to lowercase version of name."""

    def _generate_next_value_(  # type: ignore[override,misc]
        name: str,  # noqa: B902,N805
        start: int,
        count: int,
        last_values: List[Any],
    ) -> str:
        """Set member's values as their lowercase name."""
        return name.lower()


class ColorSystemEnum(str, LowerNameEnum):
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


def complete_theme(ctx: Context, param: Parameter, incomplete: str) -> List[str]:
    """Completion options for theme argument."""
    available_themes = _get_all_available_themes(list_duplicate_alias=True)
    completion_suggestions = [
        theme for theme in available_themes if theme.startswith(incomplete.lower())
    ]
    return completion_suggestions


@typing.overload
def translate_theme(theme_argument: str) -> str:
    """Convert theme argument to one recognized by rich."""
    ...


@typing.overload
def translate_theme(theme_argument: None) -> None:
    """Convert theme argument to one recognized by rich."""
    ...


def translate_theme(theme_argument: Union[str, None]) -> Union[str, None]:
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
            translated_theme = translate_theme(theme)
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
    help="Wrap code onto next line if it does not fit in width."
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
