"""Functions for rendering notebook components."""
import collections
import json
import tempfile
from typing import Dict
from typing import Generator
from typing import List
from typing import Union

import html2text
from lxml import html
from lxml.html import HtmlElement
from nbformat import NotebookNode
from pylatexenc import latex2text
from rich import box
from rich import emoji
from rich import markdown
from rich import padding
from rich import style
from rich import syntax
from rich import table
from rich import text
from rich.emoji import Emoji
from rich.markdown import Markdown
from rich.padding import Padding
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text


def _write_file(content: Union[str, bytes], extension: str) -> str:
    """Write content to a temporary file.

    Args:
        content (Union[str, bytes]): The content to write.
        extension (str): The file extension of the temporary file.

    Returns:
        str: The file name.
    """
    mode = "w"
    if isinstance(content, bytes):
        mode += "b"
    with tempfile.NamedTemporaryFile(
        mode=mode, delete=False, suffix=f".{extension}"
    ) as file:
        file.write(content)
    return file.name


def render_dataframe(table_html: List[HtmlElement], unicode: bool) -> Table:
    """Render a DataFrame from its HTML.

    Args:
        table_html (List[HtmlElement]): The DataFrame rendered as HTML.
        unicode (bool): Whether to use unicode characters when rendering
            the table.

    Returns:
        Table: The DataFrame rendered as a Rich Table.
    """
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

            table_element = render_table_element(column, column_width=column_width)
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
            table_element = render_table_element(column, column_width=column_width)
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
            column: previous_row_spans.get(column, 0) + current_row_spans.get(column, 0)
            for column in previous_row_spans.keys() | current_row_spans.keys()
        }
        dataframe_table.add_row(*table_row)

    return dataframe_table


def render_html(
    data: Dict[str, str], unicode: bool, plain: bool, theme: str
) -> Union[Table, Markdown, None]:
    """Render HTML output.

    Args:
        data (Dict[str, str]): The notebook output data.
        unicode (bool): Whether to use unicode characters when
            rendering.
        plain (bool): Whether to render the output in a plain style.
        theme (str): The Pygments theme to use for syntax highlighting.

    Returns:
        Union[Table, None]: The rendered HTML.
    """
    # Detect if output is a rendered DataFrame
    rendered_html: Union[Table, Markdown]
    datum = data["text/html"]
    dataframe_html = html.fromstring(datum).find_class("dataframe")
    if not plain:
        if dataframe_html and dataframe_html[0].tag == "table":
            rendered_html = render_dataframe(dataframe_html, unicode=unicode)
        else:
            converted_markdown = html2text.html2text(datum)
            rendered_html = markdown.Markdown(
                converted_markdown, inline_code_theme=theme
            )
        return rendered_html
    else:
        return None


def render_table_element(column: HtmlElement, column_width: int) -> List[Text]:
    """Render a DataFrame table element.

    Args:
        column (HtmlElement): The HTML element to render.
        column_width (int): The width of the column to render.

    Returns:
        List[Text]: The rendered DataFrame element.
    """
    attributes = column.attrib
    column_width = int(attributes.get("colspan", 1))
    text_style: Union[str, Style] = style.Style(bold=True) if column.tag == "th" else ""
    column_string = column.text if column.text is not None else ""
    element_text = text.Text(column_string, style=text_style)
    table_element = (column_width - 1) * [text.Text("")] + [element_text]
    return table_element


def render_markdown(data: Dict[str, str], theme: str) -> Markdown:
    """Render Markdown output.

    Args:
        data (Dict[str, str]): The notebook output data.
        theme (str): The Pygments theme to use for syntax highlighting.

    Returns:
        Markdown: The rendered Markdown output.
    """
    markdown_text = data["text/markdown"]
    return markdown.Markdown(markdown_text, inline_code_theme=theme)


def render_latex(data: Dict[str, str], unicode: bool) -> Union[str, None]:
    """Render LaTeX output.

    Args:
        data (Dict[str, str]): The notebook output data.
        unicode (bool): Whether to use unicode characters. Will return
            None if False.

    Returns:
        str: The rendered LaTeX as unicode characters.
    """
    if unicode:
        latex_data = data["text/latex"]
        rendered_latex: str = latex2text.LatexNodes2Text(
            math_mode="text",
            fill_text=True,
            strict_latex_spaces=False,
        ).latex_to_text(latex_data)
        return rendered_latex
    else:
        return None


def render_json(data: Dict[str, Union[str, NotebookNode]], theme: str) -> Syntax:
    """Render JSON output.

    Args:
        data (Dict[str, str]): The notebook output data.
        theme (str): The Pygments theme to use for syntax highlighting.

    Returns:
        Syntax: Rendered JSON output.
    """
    json_data = json.dumps(data["application/json"])
    return syntax.Syntax(
        json_data,
        lexer_name="json",
        theme=theme,
        background_color="default",
    )


def render_pdf(nerd_font: bool, unicode: bool) -> Union[str, Emoji, None]:
    """Render PDF output.

    Args:
        nerd_font (bool): Whether Nerd Font icons may be used. Will
            override unicode if True.
        unicode (bool): Whether Unicode characters may be used.

    Returns:
        Union[str, Emoji, None]: A rendered icon representing a PDF.
    """
    if nerd_font:
        return ""
    elif unicode:
        return emoji.Emoji(name="page_facing_up")
    else:
        return None


def render_error(output: NotebookNode, theme: str) -> Generator[Syntax, None, None]:
    """Render an error type output.

    Args:
        output (NotebookNode): The error output.
        theme (str): The Pygments syntax theme to use.

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
                theme=theme,
                background_color="default",
            )
        )


def render_stream(output: NotebookNode) -> Generator[Union[Text, str], None, None]:
    """Render a stream type output.

    Args:
        output (NotebookNode): The stream output.

    Yields:
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
    yield rendered_stream


def render_execution_indicator(
    execution_count: Union[int, None], top_pad: bool
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
