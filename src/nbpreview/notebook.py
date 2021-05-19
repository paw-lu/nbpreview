"""Render the notebook."""
import dataclasses
from typing import Dict
from typing import Generator
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from nbformat.notebooknode import NotebookNode
from rich import padding
from rich import panel
from rich import table
from rich.console import Console
from rich.console import ConsoleOptions
from rich.emoji import Emoji
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from . import render

Cell = Union[Panel, Text, Syntax, str, Padding]


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

    def __post_init__(self) -> None:
        """Constructor."""
        self.cells = self.notebook_node.cells
        self.language = self.notebook_node.metadata.kernelspec.language

    def _render_cells(
        self,
        cell: NotebookNode,
        plain: bool,
        pad: Tuple[int, int, int, int],
        unicode_border: Optional[bool] = None,
    ) -> Tuple[Cell, ...]:
        """Render a Jupyter Notebook cell.

        Args:
            cell (NotebookNode): The cell to render.
            plain (bool): Only show plain style. No decorations such as
                boxes or execution counts.
            pad (Tuple[int, int, int, int]): The output padding to use.
            unicode_border (Optional[bool]): Whether to render the cell
                borders using unicode characters. Will autodetect by
                default.

        Returns:
            Tuple[Text, Cell]: The execution count indicator and cell
                content.
        """
        cell_type = cell.get("cell_type")
        source = cell.source
        default_lexer_name = "ipython" if self.language == "python" else self.language

        rendered_source: Union[Text, Syntax, str]
        rendered_cell: Optional[Cell] = None
        if cell_type == "markdown":
            execution_count = None
            rendered_cell = render.render_markdown_cell(
                source, theme=self.theme, pad=pad
            )

        elif cell_type == "code":
            execution_count = (
                cell.execution_count if cell.execution_count is not None else 0
            )
            rendered_source = render.render_code_cell(
                source, theme=self.theme, default_lexer_name=default_lexer_name
            )

        # Includes cell_type == "raw"
        else:
            execution_count = None
            rendered_source = source

        if rendered_cell is None:
            if not plain:
                safe_box = None if unicode_border is None else not unicode_border
                rendered_cell = panel.Panel(rendered_source, safe_box=safe_box)
            else:
                rendered_cell = rendered_source

        execution_count_indicator = render.render_execution_indicator(
            execution_count, top_pad=not plain
        )
        cell_row = (
            (execution_count_indicator, rendered_cell)
            if not plain
            else (rendered_cell,)
        )

        return cell_row

    def _render_result(
        self,
        output: NotebookNode,
        plain: bool,
        unicode: bool,
        execution_count: Union[str, None],
        hyperlinks: bool,
    ) -> Union[Table, str, Syntax, Markdown, Emoji, Text, None]:
        """Render executed result outputs."""
        data: Dict[str, str] = output.get("data", {})
        rendered_result: Union[Table, str, Syntax, Markdown, Emoji, Text, None] = None
        if "text/html" in data and rendered_result is None:
            rendered_result = render.render_html(data, unicode=unicode, plain=plain)

        if "text/markdown" in data and rendered_result is None:
            rendered_result = render.render_markdown(data, theme=self.theme)

        if "text/latex" in data and rendered_result is None:
            rendered_result = render.render_latex(data, unicode=unicode)

        if "application/json" in data and rendered_result is None:
            rendered_result = render.render_json(data, theme=self.theme)

        if "application/pdf" in data and rendered_result is None:
            rendered_result = render.render_pdf(
                nerd_font=self.nerd_font, unicode=unicode
            )

        if (
            "application/vnd.vega.v5+json" in data
            or "application/vnd.vegalite.v4+json" in data
        ) and rendered_result is None:
            rendered_result = render.render_vega(
                data,
                unicode=unicode,
                hyperlinks=hyperlinks,
                execution_count=execution_count,
                nerd_font=self.nerd_font,
                files=self.files,
                hide_hyperlink_hints=self.hide_hyperlink_hints,
            )

        if "text/plain" in data and rendered_result is None:
            rendered_result = data["text/plain"]

        return rendered_result

    def _render_output(
        self,
        outputs: List[NotebookNode],
        plain: bool,
        pad: Tuple[int, int, int, int],
        unicode: bool,
        hyperlinks: bool,
    ) -> Generator[
        Union[
            Tuple[Padding],
            Tuple[Union[Text, Padding], Union[Padding]],
        ],
        None,
        None,
    ]:
        """Render the output of a notebook.

        Args:
            outputs (List[NotebookNode]): The output nodes of a
                notebook.
            plain (bool): Whether to render the notebook in a plain
                format.
            pad (Tuple[int, int, int, int]): The output padding to use.
            unicode (bool): Whether to render using unicode characters.
            hyperlinks (bool): Whether to render hyperlinks.

        Yields:
            Generator[
                Union[
                    Tuple[Padding],
                    Tuple[Union[Text, Padding],
                    Union[Padding]],
                ],
                None,
                None,
            ]:
                The notebook output.
        """
        for output in outputs:
            rendered_outputs: List[
                Union[Text, str, Table, Syntax, Markdown, Emoji]
            ] = []
            output_type = output.output_type
            execution_count = output.get("execution_count")

            execution_count_indicator = render.render_execution_indicator(
                execution_count, top_pad=False
            )

            if output_type == "stream":
                rendered_stream = render.render_stream(output)
                rendered_outputs.append(rendered_stream)

            elif output_type == "error":
                rendered_error = render.render_error(output, theme=self.theme)
                rendered_outputs.extend(rendered_error)

            elif output_type == "execute_result" or output_type == "display_data":
                rendered_execute_result = self._render_result(
                    output,
                    plain=plain,
                    unicode=unicode,
                    execution_count=execution_count,
                    hyperlinks=hyperlinks,
                )
                if rendered_execute_result:
                    rendered_outputs.append(rendered_execute_result)

            for rendered_output in rendered_outputs:
                yield self._arrange_row(
                    rendered_output,
                    plain=plain,
                    execution_count_indicator=execution_count_indicator,
                    pad=pad,
                )

    def _arrange_row(
        self,
        content: Union[Table, Syntax, Text, str, Table, Markdown, Emoji],
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
        hyperlinks = _pick_option(self.hyperlinks, detector=options.legacy_windows)
        grid = table.Table.grid(padding=(1, 1, 1, 0))

        pad = _get_output_pad(plain)
        if not plain:
            grid.add_column(justify="right")
        grid.add_column()

        for cell in self.cells:
            cell_row = self._render_cells(
                cell,
                plain=plain,
                pad=pad,
                unicode_border=unicode,
            )
            grid.add_row(*cell_row)

            outputs = cell.get("outputs")
            if not self.hide_output and outputs is not None:
                rendered_outputs = self._render_output(
                    outputs,
                    plain=plain,
                    pad=pad,
                    unicode=unicode,
                    hyperlinks=hyperlinks,
                )
                for rendered_output in rendered_outputs:
                    grid.add_row(*rendered_output)

        yield grid
