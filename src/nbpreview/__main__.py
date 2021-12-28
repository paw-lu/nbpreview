"""Command-line interface."""
import functools
import os
import sys
from pathlib import Path
from sys import stdin, stdout
from typing import Optional, Union

import click
import nbformat
import typer
from rich import console, traceback
from rich.console import Console

from nbpreview import errors, notebook, parameters
from nbpreview.component.content.output.result import drawing
from nbpreview.component.content.output.result.drawing import ImageDrawingEnum
from nbpreview.notebook import Notebook
from nbpreview.parameters import ColorSystemEnum

app = typer.Typer()
traceback.install(theme="material")


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


def _check_image_drawing_option(
    image_drawing: Union[ImageDrawingEnum, None], stderr_console: Console
) -> None:
    """Check if the image drawing option is valid."""
    if image_drawing == drawing.ImageDrawingEnum.BLOCK:
        try:
            import terminedia  # noqa: F401
        except ModuleNotFoundError as exception:
            message = (
                f"--image-drawing='{image_drawing.value}' cannot be"
                " used on this system. This might be because it is"
                " being run on Windows."
            )
            raise typer.BadParameter(
                message=message, param_hint="image-drawing"
            ) from exception


def _detect_paging(
    paging: Union[bool, None], rendered_notebook: str, console: Console
) -> bool:
    """Determine if pager should be used."""
    detected_paging = paging or (
        paging is None
        and console.height < (rendered_notebook.count("\n") + 1)
        and console.is_interactive
        # click.echo_via_pager will not use a pager when stdin or stdout
        # is not a tty, which will result in uncolored output
        # Disable paging for now as a workaround
        # This means a pager will not be used when output is piped
        and stdin.isatty()  # Importing stdin/stdout directly because
        # of trouble in mocking when importing top level sys
        and stdout.isatty()
    )
    return detected_paging


def _render_notebook(
    nbpreview_notebook: Notebook,
    console: Console,
    paging: Union[bool, None],
    color: Union[bool, None],
) -> None:
    """Render the notebook to the console."""
    with console.capture() as capture:
        console.print(nbpreview_notebook)
    rendered_notebook = capture.get()
    _paging = _detect_paging(
        paging, rendered_notebook=rendered_notebook, console=console
    )
    if _paging:
        click.echo_via_pager(rendered_notebook, color=color)
    else:
        print(rendered_notebook, end="")


@app.command()
def main(
    file: Path = parameters.file_argument,
    theme: Optional[str] = parameters.theme_option,
    list_themes: Optional[bool] = parameters.list_themes_option,
    plain: Optional[bool] = parameters.plain_option,
    unicode: Optional[bool] = parameters.unicode_option,
    hide_output: bool = parameters.hide_output_option,
    nerd_font: bool = parameters.nerd_font_option,
    no_files: bool = parameters.no_files_option,
    positive_space: bool = parameters.positive_space_option,
    hyperlinks: bool = parameters.hyperlinks_option,
    hide_hyperlink_hints: bool = parameters.hide_hyperlink_hints_option,
    images: Optional[bool] = parameters.images_option,
    image_drawing: Optional[ImageDrawingEnum] = parameters.image_drawing_option,
    color: Optional[bool] = parameters.color_option,
    color_system: Optional[ColorSystemEnum] = parameters.color_system_option,
    width: Optional[int] = parameters.width_option,
    version: Optional[bool] = parameters.version_option,
    line_numbers: bool = parameters.line_numbers_option,
    code_wrap: bool = parameters.code_wrap_option,
    paging: Optional[bool] = parameters.paging_option,
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
    files = not no_files
    negative_space = not positive_space
    translated_theme = parameters.translate_theme(theme)

    try:
        with click.open_file(os.fsdecode(file)) as _file:
            nbpreview_notebook = notebook.Notebook.from_file(
                _file,
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
                line_numbers=line_numbers,
                code_wrap=code_wrap,
            )

    except (nbformat.reader.NotJSONError, errors.InvalidNotebookError) as exception:
        message = f"{file} is not a valid Jupyter Notebook path."
        raise typer.BadParameter(message=message, param_hint="file") from exception

    else:
        _render_notebook(
            nbpreview_notebook, console=stdout_console, paging=paging, color=color
        )


typer_click_object = typer.main.get_command(app)
if __name__ == "__main__":
    typer_click_object()  # pragma: no cover
