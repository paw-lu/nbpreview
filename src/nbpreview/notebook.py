"""Render the notebook."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Iterator
from typing import List
from typing import Literal
from typing import Optional
from typing import Tuple

import nbformat
from nbformat.notebooknode import NotebookNode
from rich import table
from rich.console import Console
from rich.console import ConsoleOptions
from rich.table import Table

from nbpreview.component import row


def _pick_option(option: Optional[bool], detector: bool) -> bool:
    """Select a render option.

    Args:
        option (Optional[bool]): The inputted option which can override
            detections. By default None, which leaves the decision to
            ``detector``.
        detector (bool): A detector based on terminal properties to set
            the option to False. Will be ignored if ``option`` is a
            boolean.

    Returns:
        bool: The option value.
    """
    if option is None:
        pick = not detector
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
    option: Literal["block", "character", "braille", None],
    is_terminal: bool,
    plain: bool,
    unicode: bool,
) -> Literal["block", "character", "braille", None]:
    """Pick an image render option.

    Args:
        option (Literal["block", "character", "braille", None]): The
            inputted option which can override detections. If None, will
            autodetect.
        is_terminal (bool): Whether the program is being used in a
            terminal.
        plain (bool): Whether to render the image in a plain style. Will
            prevent autodetection of image style, typically leading to
            returning None.
        unicode (bool): Whether to use unicode characters to
            render the notebook. By default will autodetect.

    Returns:
        Literal["block", "character", "braille", None]: The image type to render.
    """
    image_render = option
    if option is None and is_terminal and not plain:
        if unicode:
            image_render = "block"
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
    image_drawing: Literal["block", "character", "braille", None],
    color: bool,
    negative_space: bool,
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
        )
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
            )
            for rendered_output in rendered_outputs:
                grid.add_row(*rendered_output.to_table_row())
    return grid


@dataclasses.dataclass()
class Notebook:
    """Construct a Notebook object to render Jupyter Notebooks.

    Args:
        notebook_node (NotebookNode): A NotebookNode of the notebook to
            render.
        theme (str): The theme to use for syntax highlighting. May be
            "ansi_light", "ansi_dark", or any Pygments theme. By default
            "ansi_dark".
        plain (bool): Only show plain style. No decorations such as
            boxes or execution counts. By default will autodetect.
        unicode (Optional[bool]): Whether to use unicode characters to
            render the notebook. By default will autodetect.
        hide_output (bool): Do not render the notebook outputs. By
            default False.
        nerd_font (bool): Use nerd fonts when appropriate. By default
            False.
        files (bool): Create files when needed to render HTML content.
        hyperlinks (bool): Whether to use hyperlinks. If false will
            explicitly print out path.
        hide_hyperlink_hints (bool): Hide text hints of when content is
            clickable.
        images (Optional[str]): Whether to render images. If None will
            attempt to autodetect. By default None.
        image_drawing (Optional[str]): How to render images. Options are
            "block" or None. If None will attempt to autodetect. By
            default None.
    """

    # TODO: Fix incorrect docstring

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
    image_drawing: Optional[Literal["block", "character", "braille"]] = None
    color: Optional[bool] = None

    def __post_init__(self) -> None:
        """Constructor."""
        self.cells = self.notebook_node.get("cells", nbformat.from_dict([]))
        try:
            self.language = self.notebook_node.metadata.kernelspec.language
        except AttributeError:
            self.language = "python"

    @classmethod
    def from_file(
        cls,
        file: Path,
        theme: str = "ansi_dark",
        plain: Optional[bool] = None,
        unicode: Optional[bool] = None,
        hide_output: bool = False,
        nerd_font: bool = False,
        files: bool = True,
        hyperlinks: Optional[bool] = None,
        hide_hyperlink_hints: bool = False,
        images: Optional[bool] = None,
        image_drawing: Literal["block", "character", "braille", None] = None,
    ) -> Notebook:
        """Create Notebook from notebook file."""
        notebook_node = nbformat.read(file, as_version=4)
        return cls(
            notebook_node,
            theme=theme,
            plain=plain,
            unicode=unicode,
            hide_output=hide_output,
            nerd_font=nerd_font,
            files=files,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
            images=images,
            image_drawing=image_drawing,
        )

    # TODO: Add rich_measure
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
        plain = _pick_option(self.plain, detector=options.is_terminal)
        unicode = _pick_option(
            self.unicode, detector=options.legacy_windows or options.ascii_only
        )
        hyperlinks = _pick_option(self.hyperlinks, detector=options.legacy_windows)
        images = _pick_option(self.images, detector=not options.is_terminal)
        color = _pick_option(self.color, detector=not options.is_terminal)
        image_drawing = _pick_image_drawing(
            self.image_drawing,
            is_terminal=options.is_terminal,
            plain=plain,
            unicode=unicode,
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
        )
        yield rendered_notebook
