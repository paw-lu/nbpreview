"""Render the notebook."""
import dataclasses
from typing import Iterator
from typing import Optional
from typing import Tuple

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


def _render_notebook(
    cells: NotebookNode,
    plain: bool,
    unicode: bool,
    hyperlinks: bool,
    theme: str,
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    hide_output: bool,
    language: str,
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
        image_type (Optional[str]): How to render images. Options are
            "sixel" and "iterm". If None will attempt to autodetect. By
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
    hyperlinks: Optional[bool] = None
    hide_hyperlink_hints: bool = False
    images: Optional[bool] = None
    image_type: Optional[str] = None

    def __post_init__(self) -> None:
        """Constructor."""
        self.cells = self.notebook_node.cells
        # TODO: what happens if no kernel?
        self.language = self.notebook_node.metadata.kernelspec.language

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
        # images = _pick_option(self.images, detector=not options.is_terminal)
        hyperlinks = _pick_option(self.hyperlinks, detector=options.legacy_windows)
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
        )
        yield rendered_notebook
