"""Render the notebook."""
import collections
import dataclasses
import json
from typing import Dict
from typing import Generator
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import pygments
from lxml import html
from lxml.html import HtmlElement
from nbformat.notebooknode import NotebookNode
from pylatexenc import latex2text
from rich import box
from rich import markdown
from rich import padding
from rich import panel
from rich import style
from rich import syntax
from rich import table
from rich import text
from rich.console import Console
from rich.console import ConsoleOptions
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

Cell = Union[Panel, Text, Syntax, str, Padding]


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
    """

    notebook_node: NotebookNode
    theme: str = "ansi_dark"
    plain: Optional[bool] = None
    unicode: Optional[bool] = None
    hide_output: bool = False

    def __post_init__(self) -> None:
        """Constructor."""
        self.cells = self.notebook_node.cells
        self.language = self.notebook_node.metadata.kernelspec.language

    def _render_execution_indicator(
        self, execution_count: Union[int, None], top_pad: bool
    ) -> Union[Text, Padding]:
        """Render the execution indicator.

        Args:
            execution_count (Union[int, None]): The execution
                count. Set to None if there is no execution count, set
                to 0 if yet unexecuted.
            top_pad (bool): Whether to top pad the indicator count.
                Useful if aligned with a code cell box and the execution
                count should be aligned with the content.

        Returns:
            Text: The rendered execution indicator.
        """
        execution_indicator: Union[Text, Padding]
        if execution_count is None:
            execution_text = ""
        elif execution_count == 0:
            execution_text = "[ ]:"
        else:
            execution_text = f"[{execution_count}]:"
        execution_indicator = text.Text(execution_text, style="color(247)")

        if top_pad:
            execution_indicator = padding.Padding(execution_indicator, pad=(1, 0, 0, 0))

        return execution_indicator

    def _get_output_pad(self, plain: bool) -> Tuple[int, int, int, int]:
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
            rendered_cell = padding.Padding(
                markdown.Markdown(source, inline_code_theme=self.theme),
                pad=pad,
            )

        elif cell_type == "code":
            execution_count = (
                cell.execution_count if cell.execution_count is not None else 0
            )
            rendered_source = syntax.Syntax(
                source,
                lexer_name=default_lexer_name,
                theme=self.theme,
                background_color="default",
            )

            if source.startswith("%%"):
                try:
                    magic, body = source.split("\n", 1)
                    language_name = magic.lstrip("%")
                    body_lexer_name = pygments.lexers.get_lexer_by_name(
                        language_name
                    ).name
                    # Syntax needs a string in the init, so pass an
                    # empty string and then pass the actual code to
                    # highlight method
                    magic_syntax = syntax.Syntax(
                        "",
                        lexer_name=default_lexer_name,
                        theme=self.theme,
                        background_color="default",
                    ).highlight(magic)
                    body_syntax = syntax.Syntax(
                        "",
                        lexer_name=body_lexer_name,
                        theme=self.theme,
                        background_color="default",
                    ).highlight(body)
                    rendered_source = text.Text().join((magic_syntax, body_syntax))

                except pygments.util.ClassNotFound:
                    pass

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

        execution_count_indicator = self._render_execution_indicator(
            execution_count, top_pad=not plain
        )
        cell_row = (
            (execution_count_indicator, rendered_cell)
            if not plain
            else (rendered_cell,)
        )

        return cell_row

    def _render_stream(self, output: NotebookNode) -> Union[Text, str]:
        """Render a stream type output.

        Args:
            output (NotebookNode): The stream output.

        Returns:
            Union[Test, str]: The rendered stream.
        """
        name = output.get("name")
        output_text = output.get("text", "")
        if name == "stderr":
            rendered_stream = text.Text(
                output_text, style=style.Style(bgcolor="color(174)")
            )

        else:
            rendered_stream = output_text
        return rendered_stream

    def _render_error(self, output: NotebookNode) -> Generator[Syntax, None, None]:
        """Render an error type output.

        Args:
            output (NotebookNode): The error output.

        Yields:
            Generator[Syntax, None, None]: Generate each row of the
                traceback.
        """
        traceback = output.get("traceback", ())
        for traceback_line in traceback:
            lexer_name = "IPython Traceback"
            # A background here looks odd--highlighting only certain
            # words.
            yield (
                syntax.Syntax(
                    traceback_line,
                    lexer_name=lexer_name,
                    theme=self.theme,
                    background_color="default",
                )
            )

    def _render_execute_result(
        self, output: NotebookNode, plain: bool, unicode: bool
    ) -> Optional[Union[Table, str, Syntax]]:
        """Render executed result outputs."""
        data: Dict[str, str] = output.get("data", {})
        if "text/html" in data:
            # Detect if output is a rendered DataFrame
            datum = data["text/html"]
            dataframe_html = html.fromstring(datum).find_class("dataframe")
            if not plain and dataframe_html and dataframe_html[0].tag == "table":
                rendered_html = self._render_dataframe(dataframe_html, unicode=unicode)
                return rendered_html

        if "application/json" in data:
            json_data = json.dumps(data["application/json"])
            return syntax.Syntax(
                json_data,
                lexer_name="json",
                theme=self.theme,
                background_color="default",
            )

        if "text/plain" in data:
            return data["text/plain"]
        return None

    def _render_display_data(
        self, output: NotebookNode, plain: bool, unicode: bool
    ) -> Optional[Union[Markdown, str]]:
        """Render display data outputs."""
        data: Dict[str, str] = output.get("data", {})
        if "text/markdown" in data:
            markdown_text = data["text/markdown"]
            return markdown.Markdown(markdown_text, inline_code_theme=self.theme)

        if "text/latex" in data and unicode:
            latex_data = data["text/latex"]
            rendered_latex: str = latex2text.LatexNodes2Text(
                math_mode="text",
                fill_text=True,
                strict_latex_spaces=False,
            ).latex_to_text(latex_data)
            return rendered_latex
        return None

    def _render_output(
        self,
        outputs: List[NotebookNode],
        plain: bool,
        pad: Tuple[int, int, int, int],
        unicode: bool,
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
            rendered_outputs: List[Union[Text, str, Table, Syntax, Markdown]] = []
            output_type = output.output_type
            execution_count = output.get("execution_count")

            execution_count_indicator = self._render_execution_indicator(
                execution_count, top_pad=False
            )

            if output_type == "stream":
                rendered_stream = self._render_stream(output)
                rendered_outputs.append(rendered_stream)

            elif output_type == "error":
                rendered_error = self._render_error(output)
                rendered_outputs.extend(rendered_error)

            elif output_type == "execute_result":
                rendered_execute_result = self._render_execute_result(
                    output, plain=plain, unicode=unicode
                )
                if rendered_execute_result:
                    rendered_outputs.append(rendered_execute_result)

            elif output_type == "display_data":
                rendered_display_data = self._render_display_data(
                    output, plain=plain, unicode=unicode
                )
                if rendered_display_data:
                    rendered_outputs.append(rendered_display_data)

            for rendered_output in rendered_outputs:
                yield self._arrange_row(
                    rendered_output,
                    plain=plain,
                    execution_count_indicator=execution_count_indicator,
                    pad=pad,
                )

    def _render_table_element(
        self, column: HtmlElement, column_width: int
    ) -> List[Text]:
        attributes = column.attrib
        column_width = int(attributes.get("colspan", 1))
        text_style: Union[str, Style] = (
            style.Style(bold=True) if column.tag == "th" else ""
        )
        column_string = column.text if column.text is not None else ""
        element_text = text.Text(column_string, style=text_style)
        table_element = (column_width - 1) * [text.Text("")] + [element_text]
        return table_element

    def _render_dataframe(self, table_html: List[HtmlElement], unicode: bool) -> Table:
        dataframe_html = table_html[0]
        column_rows = dataframe_html.find("thead").findall("tr")

        dataframe_table = table.Table(
            show_edge=False,
            show_header=False,
            box=box.HORIZONTALS,
            show_footer=False,
            safe_box=not unicode,
        )

        n_column_rows = len(column_rows)
        for i, column_row in enumerate(column_rows):

            table_row = []
            for column in column_row.xpath("th|td"):
                attributes = column.attrib
                column_width = int(attributes.get("colspan", 1))

                if i == 0:
                    for _ in range(column_width):
                        dataframe_table.add_column(justify="right")

                table_element = self._render_table_element(
                    column, column_width=column_width
                )
                table_row.extend(table_element)

            end_section = i == n_column_rows - 1
            dataframe_table.add_row(*table_row, end_section=end_section)

        previous_row_spans: Dict[int, int] = {}
        for row in dataframe_html.find("tbody").findall("tr"):

            table_row = []
            current_row_spans: Dict[int, int] = collections.defaultdict(int)
            for i, column in enumerate(row.xpath("th|td")):
                attributes = column.attrib
                column_width = int(attributes.get("colspan", 1))
                row_span = int(attributes.get("rowspan", 1))
                table_element = self._render_table_element(
                    column, column_width=column_width
                )
                table_row.extend(table_element)

                if 1 < row_span:
                    current_row_spans[i] += row_span

            for column, row_span in previous_row_spans.copy().items():
                table_row.insert(column, text.Text(""))
                remaining_span = row_span - 1

                if 1 < remaining_span:
                    previous_row_spans[column] = remaining_span
                else:
                    previous_row_spans.pop(column, None)

            previous_row_spans = {
                column: previous_row_spans.get(column, 0)
                + current_row_spans.get(column, 0)
                for column in previous_row_spans.keys() | current_row_spans.keys()
            }
            dataframe_table.add_row(*table_row)

        return dataframe_table

    def _arrange_row(
        self,
        content: Union[Table, Syntax, Text, str, Table, Markdown],
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
        if self.plain is None:
            if options.is_terminal:
                plain = False
            else:
                plain = True
        else:
            plain = self.plain

        if self.unicode is None:
            if options.legacy_windows or options.ascii_only:
                unicode = False
            else:
                unicode = True
        else:
            unicode = self.unicode

        grid = table.Table.grid(padding=(1, 1, 1, 0))

        pad = self._get_output_pad(plain)
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
                    outputs, plain=plain, pad=pad, unicode=unicode
                )
                for rendered_output in rendered_outputs:
                    grid.add_row(*rendered_output)

        yield grid
