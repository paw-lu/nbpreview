"""Render the notebook."""
import dataclasses
import itertools
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from nbformat.notebooknode import NotebookNode
from rich import padding
from rich import table
from rich.console import Console
from rich.console import ConsoleOptions
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from .component import display_data
from .component import error
from .component import link
from .component import row
from .component import stream
from .component.display_data import DisplayData
from .component.execution_indicator import Execution
from .component.link import Hyperlink
from .component.row import Output
from .component.row import OutputRow
from nbpreview.component import execution_indicator


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
        self.language = self.notebook_node.metadata.kernelspec.language

    def _render_result(
        self,
        output: NotebookNode,
        plain: bool,
        unicode: bool,
        execution: Union[Execution, None],
        hyperlinks: bool,
        images: bool,
    ) -> Iterator[Union[Hyperlink, DisplayData]]:
        """Render executed result outputs."""
        data: Dict[str, Union[str, NotebookNode]] = output.get("data", {})
        link_result = link.render_link(
            data,
            unicode=unicode,
            hyperlinks=hyperlinks,
            execution=execution,
            nerd_font=self.nerd_font,
            files=self.files,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
        )
        main_result = display_data.render_display_data(
            data,
            unicode=unicode,
            plain=plain,
            nerd_font=self.nerd_font,
            theme=self.theme,
        )
        # TODO: Refactor from iterator to return
        for result in (link_result, main_result):
            if result is not None:
                yield result

    def _render_output(
        self,
        outputs: List[NotebookNode],
        plain: bool,
        pad: Tuple[int, int, int, int],
        unicode: bool,
        hyperlinks: bool,
        images: bool,
    ) -> Iterator[OutputRow]:
        """Render the output of a notebook.

        Args:
            outputs (List[NotebookNode]): The output nodes of a
                notebook.
            plain (bool): Whether to render the notebook in a plain
                format.
            pad (Tuple[int, int, int, int]): The output padding to use.
            unicode (bool): Whether to render using unicode characters.
            hyperlinks (bool): Whether to render hyperlinks.
            images (bool): Whether to render images in the terminal.

        Yields:
            Iterator[OutputRow]:
                The notebook output.
        """
        for output in outputs:
            rendered_outputs: List[Iterator[Output]] = []
            output_type = output.output_type
            execution_count = output.get("execution_count", False)
            execution = (
                execution_indicator.Execution(execution_count, top_pad=False)
                if execution_count is not False
                else None
            )

            if output_type == "stream":
                rendered_stream = stream.render_stream(output)
                rendered_outputs.append(rendered_stream)

            elif output_type == "error":
                rendered_error = error.render_error(output, theme=self.theme)
                rendered_outputs.append(rendered_error)

            elif output_type == "execute_result" or output_type == "display_data":
                rendered_execute_result = self._render_result(
                    output,
                    plain=plain,
                    unicode=unicode,
                    execution=execution,
                    hyperlinks=hyperlinks,
                    images=images,
                )
                rendered_outputs.append(rendered_execute_result)

            for rendered_output in itertools.chain(*rendered_outputs):
                yield row.OutputRow(
                    rendered_output, plain=plain, execution=execution, pad=pad
                )

    def _arrange_row(
        self,
        content: Output,
        plain: bool,
        execution_count_indicator: Union[Text, Padding],
        pad: Tuple[int, int, int, int],
    ) -> Union[Tuple[Padding], Tuple[Union[Text, Padding], Union[Padding]]]:
        padded_content = padding.Padding(content, pad=pad)
        if plain:
            return (padded_content,)
        else:
            return (execution_count_indicator, padded_content)

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
        images = _pick_option(self.images, detector=not options.is_terminal)
        hyperlinks = _pick_option(self.hyperlinks, detector=options.legacy_windows)
        grid = table.Table.grid(padding=(1, 1, 1, 0))

        pad = _get_output_pad(plain)
        if not plain:
            grid.add_column(justify="right")
        grid.add_column()

        for cell in self.cells:
            cell_row = row.render_input_row(
                cell,
                plain=plain,
                pad=pad,
                language=self.language,
                theme=self.theme,
                unicode_border=unicode,
            )
            grid.add_row(*cell_row.to_table_row())

            outputs = cell.get("outputs")
            if not self.hide_output and outputs is not None:
                rendered_outputs = self._render_output(
                    outputs,
                    plain=plain,
                    pad=pad,
                    unicode=unicode,
                    hyperlinks=hyperlinks,
                    images=images,
                )
                for rendered_output in rendered_outputs:
                    grid.add_row(*rendered_output.to_table_row())

        yield grid
