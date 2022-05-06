"""Render the notebook."""
import dataclasses
import pathlib
import typing
from dataclasses import InitVar
from pathlib import Path
from typing import IO, Any, AnyStr, Iterator, List, Optional, Tuple, Type, Union

import jsonschema
import nbformat
from click.utils import KeepOpenFile
from nbformat import validator
from nbformat.notebooknode import NotebookNode
from rich import table
from rich.console import Console, ConsoleOptions
from rich.table import Table

from nbpreview import errors
from nbpreview.component import row
from nbpreview.component.content.output.result.drawing import ImageDrawing

# Fake KeepOpenFile used to avoid non-subscriptable error
# https://github.com/python/mypy/issues/5264
if typing.TYPE_CHECKING:  # pragma: no cover
    KeepOpenFileType = KeepOpenFile

else:

    class _KeepOpenFile:
        """Fake click's KeepOpenFile for type checking purposes."""

        def __getitem__(self, *args: Any) -> Type[KeepOpenFile]:
            """Make the fake class subscriptable."""
            return KeepOpenFile

    KeepOpenFileType = _KeepOpenFile()


def pick_option(option: Optional[bool], detector: bool) -> bool:
    """Select a render option.

    Args:
        option (Optional[bool]): The inputted option which can override
            detections. By default None, which leaves the decision to
            ``detector``.
        detector (bool): A detector based on terminal properties to set
            the option to True. Will be ignored if ``option`` is a
            boolean.

    Returns:
        bool: The option value.
    """
    if option is None:
        pick = detector
    else:
        pick = option

    return pick


def _get_output_pad(plain: bool) -> Tuple[int, int, int, int]:
    """Return the padding for outputs.

    Args:
        plain (bool): Only show plain style. No decorations such as
            boxes or execution counts.

    Returns:
        Tuple[int, int, int, int]: The padding for outputs.
    """
    if plain:
        return (0, 0, 0, 0)
    else:
        return (0, 0, 0, 1)


def _pick_image_drawing(
    option: Union[ImageDrawing, None],
    unicode: bool,
    color: bool,
    legacy_windows: bool,
    ascii_only: bool,
    color_system: Union[str, None],
) -> ImageDrawing:
    """Pick an image render option.

    Args:
        option (Literal["block", "character", "braille", ImageDrawingEnum, None]):
            The inputted option which can override detections. If None,
            will autodetect.
        unicode (bool): Whether to use unicode characters to
            render the notebook. By default will autodetect.
        color (bool): Whether to use color.
        legacy_windows (bool): Whether rendering to a legacy windows
            terminal.
        ascii_only (bool): Whether to render using only ascii
            characters.
        color_system (Union[str, None]): The color system to use.

    Returns:
        Union[Literal["block", "character", "braille"] ImageDrawingEnum]:
        The image type to render.
    """
    image_render: ImageDrawing
    if option is None:
        image_render = (
            "block"
            if all(
                [
                    unicode,
                    color,
                    not legacy_windows,
                    not ascii_only,
                    color_system is not None,
                ]
            )
            else "character"
        )

    else:
        image_render = option
    return image_render


def _render_notebook(
    cells: List[NotebookNode],
    plain: bool,
    unicode: bool,
    hyperlinks: bool,
    theme: str,
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    hide_output: bool,
    language: str,
    images: bool,
    image_drawing: ImageDrawing,
    color: bool,
    negative_space: bool,
    relative_dir: Path,
    characters: Optional[str] = None,
    line_numbers: bool = False,
    code_wrap: bool = False,
) -> Table:
    """Create a table representing a notebook."""
    grid = table.Table.grid(padding=(1, 1, 1, 0))

    pad = _get_output_pad(plain)
    if not plain:
        grid.add_column(justify="right")
    grid.add_column()

    for cell in cells:
        cell_row = row.render_input_row(
            cell,
            plain=plain,
            pad=pad,
            language=language,
            theme=theme,
            unicode_border=unicode,
            nerd_font=nerd_font,
            unicode=unicode,
            images=images,
            image_drawing=image_drawing,
            color=color,
            negative_space=negative_space,
            hyperlinks=hyperlinks,
            files=files,
            hide_hyperlink_hints=hide_hyperlink_hints,
            characters=characters,
            relative_dir=relative_dir,
            line_numbers=line_numbers,
            code_wrap=code_wrap,
        )
        if cell_row is not None:
            grid.add_row(*cell_row.to_table_row())

        outputs = cell.get("outputs")
        if not hide_output and outputs is not None:
            rendered_outputs = row.render_output_row(
                outputs,
                plain=plain,
                pad=pad,
                unicode=unicode,
                hyperlinks=hyperlinks,
                nerd_font=nerd_font,
                files=files,
                hide_hyperlink_hints=hide_hyperlink_hints,
                theme=theme,
                images=images,
                image_drawing=image_drawing,
                color=color,
                negative_space=negative_space,
                relative_dir=relative_dir,
            )
            for rendered_output in rendered_outputs:
                grid.add_row(*rendered_output.to_table_row())
    return grid


@dataclasses.dataclass()
class Notebook:
    """Construct a Notebook object to render Jupyter Notebooks.

    Args:
        notebook_node:
            A NotebookNode of the notebook to render.
        theme: The theme to use for syntax highlighting. May be
            ``'ansi_light'``, ``'ansi_dark'``, or any Pygments theme. By
            default ``'ansi_dark'``.
        plain: Only show plain style. No decorations such as
            boxes or execution counts. If set to ``None`` will
            autodetect. By default ``None``.
        unicode: Whether to use unicode characters to
            render the notebook. If set to ``None`` will autodetect. By
            default ``None``.
        hide_output: Do not render the notebook outputs. By
            default ``False``.
        nerd_font: Use nerd fonts when appropriate. By default
            ``False``.
        files: Create files when needed to render HTML content.
            By default ``True``.
        negative_space: Whether render character images in
            negative space. By default ``True``
        hyperlinks: Whether to use hyperlinks. If ``False`` will
            explicitly print out path. If set to ``None`` will
            autodetect. By default ``None``.
        hide_hyperlink_hints: Hide text hints of when content is
            clickable. By default ``False``.
        images: Whether to render images. If set to
            ``None`` will autodetect. By default ``None``.
        image_drawing: The characters used to
            render images. Options are ``'block'``, ``'character'``,
            ``'braille'`` or ``None``. If set to ``None``
            will autodetect. By default ``None``.
        color: Whether to use color. If set to
            ``None``
            will autodetect. By default ``None``.
        relative_dir: The directory to prefix relative paths to convert
            them to absolute. If ``None`` will assume current directory
            is relative prefix. By default ``None``.
        line_numbers: Whether to render line numbers in code
            cells. By default ``False``.
        code_wrap: Whether to wrap code if it does not fit. By
            default ``False``.
    """

    notebook_node: NotebookNode
    theme: str = "ansi_dark"
    plain: Optional[bool] = None
    unicode: Optional[bool] = None
    hide_output: bool = False
    nerd_font: bool = False
    files: bool = True
    negative_space: bool = True
    hyperlinks: Optional[bool] = None
    hide_hyperlink_hints: bool = False
    images: Optional[bool] = None
    image_drawing: Optional[ImageDrawing] = None
    color: Optional[bool] = None
    relative_dir: InitVar[Optional[Path]] = None
    line_numbers: bool = False
    code_wrap: bool = False

    def __post_init__(self, relative_dir: Optional[Path]) -> None:
        """Constructor."""
        self.cells = self.notebook_node.get(
            "cells", nbformat.from_dict([])  # type: ignore[no-untyped-call]
        )
        self.relative_dir = (
            pathlib.Path().resolve() if relative_dir is None else relative_dir
        )
        try:
            self.language = self.notebook_node.metadata.kernelspec.language
        except AttributeError:
            self.language = "python"

    @classmethod
    def from_file(
        cls,
        file: Union[Path, IO[AnyStr], KeepOpenFileType[AnyStr]],
        theme: str = "ansi_dark",
        plain: Optional[bool] = None,
        unicode: Optional[bool] = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        negative_space: bool = True,
        hyperlinks: Optional[bool] = None,
        hide_hyperlink_hints: bool = False,
        images: Optional[bool] = None,
        image_drawing: Optional[ImageDrawing] = None,
        color: Optional[bool] = None,
        line_numbers: bool = False,
        code_wrap: bool = False,
    ) -> "Notebook":
        """Create a Notebook from notebook file.

        Args:
            file:
                A path to a Jupyter Notebook file.
            theme: The theme to use for syntax highlighting. May
                be ``'ansi_light'``, ``'ansi_dark'``, or any Pygments
                theme. By default ``'ansi_dark'``.
            plain: Only show plain style. No decorations such as
                boxes or execution counts. If set to ``None``
                will autodetect. By default ``None``.
            unicode: Whether to use unicode characters
                to render the notebook. If set to ``None`` will
                autodetect. By default ``None``.
            hide_output: Do not render the notebook outputs. By
                default ``False``.
            nerd_font: Use nerd fonts when appropriate. By
                default ``False``.
            files: Create files when needed to render HTML
                content. By default ``True``.
            negative_space: Whether render character images in
                negative space. By default ``True``.
            hyperlinks: Whether to use hyperlinks. If
                ``False`` will explicitly print out path. If set
                to ``None`` will autodetect. By default
                ``None``.
            hide_hyperlink_hints: Hide text hints of when content
                is clickable. By default ``False``.
            images: Whether to render images. If set to
                ``None`` will autodetect. By default
                ``None``.
            image_drawing: The characters used
                to render images. Options are ``'block'``,
                ``'character'``, ``'braille'`` or ``None``. If
                set to ``None`` will autodetect. By default
                ``None``.
            color: Whether to use color. If set to
                ``None`` will autodetect. By default
                ``None``.
            line_numbers: Whether to render line numbers in code
                cells. By default ``False``.
            code_wrap: Whether to wrap code if it does not fit.
                By default ``False``.

        Returns:
            Notebook: A Notebook object created from the file.

        Raises:
            InvalidNotebookError: If the file is not a valid Jupyter
                notebook.
        """
        try:
            notebook_node = nbformat.read(  # type: ignore[no-untyped-call]
                file, as_version=4
            )
            nbformat.validate(notebook_node)  # type: ignore[no-untyped-call]
        except (
            AttributeError,
            validator.NotebookValidationError,
            jsonschema.ValidationError,
            UnicodeDecodeError,  # Windows failures when reading invalid files
        ) as exception:
            raise errors.InvalidNotebookError from exception
        relative_dir = (
            pathlib.Path.cwd()
            if (file_name := file.name) == "<stdin>"
            else pathlib.Path(file_name).parent
        ).resolve()
        return cls(
            notebook_node,
            theme=theme,
            plain=plain,
            unicode=unicode,
            hide_output=hide_output,
            nerd_font=nerd_font,
            files=files,
            negative_space=negative_space,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
            images=images,
            image_drawing=image_drawing,
            color=color,
            relative_dir=relative_dir,
            line_numbers=line_numbers,
            code_wrap=code_wrap,
        )

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Table]:
        """Render the Notebook to the terminal.

        Args:
            console (Console): The Rich Console object.
            options (ConsoleOptions): The Rich Console options.

        Yields:
            Iterator[RenderResult]: The
        """
        plain = pick_option(self.plain, detector=not options.is_terminal)
        unicode = pick_option(
            self.unicode, detector=not options.legacy_windows and not options.ascii_only
        )
        hyperlinks = pick_option(
            self.hyperlinks, detector=not options.legacy_windows and options.is_terminal
        )
        color = pick_option(self.color, detector=options.is_terminal)
        images = pick_option(self.images, detector=options.is_terminal and color)
        image_drawing = _pick_image_drawing(
            self.image_drawing,
            unicode=unicode,
            color=color,
            legacy_windows=options.legacy_windows,
            ascii_only=options.ascii_only,
            color_system=console.color_system,
        )
        rendered_notebook = _render_notebook(
            self.cells,
            plain=plain,
            unicode=unicode,
            hyperlinks=hyperlinks,
            theme=self.theme,
            nerd_font=self.nerd_font,
            files=self.files,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
            hide_output=self.hide_output,
            language=self.language,
            images=images,
            image_drawing=image_drawing,
            color=color,
            negative_space=self.negative_space,
            relative_dir=self.relative_dir,
            line_numbers=self.line_numbers,
            code_wrap=self.code_wrap,
        )
        yield rendered_notebook
