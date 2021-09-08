"""Notebook display data and execute result."""
from __future__ import annotations

import collections
import dataclasses
import json
from typing import ClassVar
from typing import Dict
from typing import List
from typing import Literal
from typing import Union

import html2text
from lxml import html
from lxml.html import HtmlElement
from pylatexenc import latex2text
from rich import box
from rich import markdown
from rich import style
from rich import syntax
from rich import table
from rich import text
from rich.console import ConsoleRenderable
from rich.emoji import Emoji
from rich.markdown import Markdown
from rich.style import Style
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from nbpreview.component.content.output.result import drawing
from nbpreview.component.content.output.result import link
from nbpreview.component.content.output.result.drawing import Drawing
from nbpreview.data import Data


def _render_html(
    data: Data, unicode: bool, theme: str
) -> Union[DataFrameDisplay, HTMLDisplay]:
    """Render HTML output."""
    display_data: Union[DataFrameDisplay, HTMLDisplay]
    html_data = data["text/html"]
    if DataFrameDisplay.is_dataframe(html_data):
        display_data = DataFrameDisplay.from_data(data, unicode=unicode)
    else:
        display_data = HTMLDisplay.from_data(data, theme=theme)
    return display_data


def _choose_basic_renderer(
    data: Data, unicode: bool, nerd_font: bool, theme: str
) -> Union[MarkdownDisplay, LaTeXDisplay, JSONDisplay, PDFDisplay, PlainDisplay, None]:
    """Render straightforward text data."""
    display_data: DisplayData
    if "text/markdown" in data:
        display_data = MarkdownDisplay.from_data(data, theme=theme)
        return display_data
    elif unicode and "text/latex" in data:
        display_data = LaTeXDisplay.from_data(data)
        return display_data
    elif "application/json" in data:
        display_data = JSONDisplay.from_data(data, theme=theme)
        return display_data
    elif (unicode or nerd_font) and "application/pdf" in data:
        display_data = PDFDisplay.from_data(data, nerd_font=nerd_font, unicode=unicode)
        return display_data
    elif "text/plain" in data:
        display_data = PlainDisplay.from_data(data)
        return display_data
    else:
        return None


def render_display_data(
    data: Data,
    unicode: bool,
    plain: bool,
    nerd_font: bool,
    theme: str,
    images: bool,
    image_drawing: Literal["block", "character", "braille", None],
    color: bool,
    negative_space: bool,
) -> Union[DisplayData, None, Drawing]:
    """Render the notebook display data."""
    display_data: Union[DisplayData, None, Drawing]
    if images:
        image_types = (
            "image/bmp",
            "image/gif",
            "image/jpeg",
            "image/png",
            "image/svg+xml",
        )
        for image_type in image_types:
            if image_type in data:
                display_data = drawing.render_drawing(
                    data,
                    image_drawing=image_drawing,
                    image_type=image_type,
                    unicode=unicode,
                    color=color,
                    negative_space=negative_space,
                )
                if display_data is not None:
                    return display_data

    if not plain and "text/html" in data:
        display_data = _render_html(data, unicode=unicode, theme=theme)
        return display_data
    else:
        display_data = _choose_basic_renderer(
            data, unicode=unicode, nerd_font=nerd_font, theme=theme
        )
        return display_data


@dataclasses.dataclass
class DisplayData:
    """A notebook's display data."""

    content: str
    data_type: ClassVar[str]

    def __rich__(self) -> Union[ConsoleRenderable, str]:
        """Render the display."""
        return self.content


@dataclasses.dataclass
class PlainDisplay(DisplayData):
    """Notebook plain display data."""

    data_type: ClassVar[str] = "text/plain"

    @classmethod
    def from_data(cls, data: Data) -> PlainDisplay:
        """Create a plain display data from notebook data."""
        content = data[cls.data_type]
        return cls(content)


@dataclasses.dataclass
class HTMLDisplay(DisplayData):
    """Notebook HTML display data."""

    theme: str
    data_type: ClassVar[str] = "text/html"

    @classmethod
    def from_data(cls, data: Data, theme: str) -> HTMLDisplay:
        """Create an HTML display data from notebook data."""
        content = data[cls.data_type]
        return cls(content, theme=theme)

    def __rich__(self) -> Markdown:
        """Render the HTML display data."""
        converted_markdown = html2text.html2text(self.content)
        rendered_html = markdown.Markdown(
            converted_markdown, inline_code_theme=self.theme
        )
        return rendered_html


def _render_table_element(column: HtmlElement, column_width: int) -> List[Text]:
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


def _render_dataframe(table_html: List[HtmlElement], unicode: bool) -> Table:
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

            table_element = _render_table_element(column, column_width=column_width)
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
            table_element = _render_table_element(column, column_width=column_width)
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


@dataclasses.dataclass
class DataFrameDisplay(DisplayData):
    """Notebook DataFrame display data."""

    unicode: bool
    data_type: ClassVar[str] = "text/html"

    @staticmethod
    def is_dataframe(content: str) -> bool:
        """Determine if DataFrame is contained with in HTML."""
        table_html = html.fromstring(content).find_class("dataframe")
        if table_html and table_html[0].tag == "table":
            return True
        else:
            return False

    @classmethod
    def from_data(cls, data: Data, unicode: bool) -> DataFrameDisplay:
        """Create DataFrame display data from notebook data."""
        content = data[cls.data_type]
        return cls(content, unicode=unicode)

    def __rich__(self) -> Table:
        """Render the DataFrame display data."""
        table_html = html.fromstring(self.content).find_class("dataframe")
        rendered_dataframe = _render_dataframe(table_html, unicode=self.unicode)
        return rendered_dataframe


@dataclasses.dataclass
class MarkdownDisplay(DisplayData):
    """Notebook Markdown display data."""

    theme: str
    data_type: ClassVar[str] = "text/markdown"

    @classmethod
    def from_data(cls, data: Data, theme: str) -> MarkdownDisplay:
        """Create Markdown display data from notebook data."""
        content = data[cls.data_type]
        return cls(content, theme=theme)

    def __rich__(self) -> Markdown:
        """Render the Markdown display data."""
        rendered_markdown = markdown.Markdown(
            self.content, inline_code_theme=self.theme
        )
        return rendered_markdown


@dataclasses.dataclass
class LaTeXDisplay(DisplayData):
    """Notebook LaTeX display data."""

    data_type: ClassVar[str] = "text/latex"

    @classmethod
    def from_data(cls, data: Data) -> LaTeXDisplay:
        """Create LaTeX display data from notebook data."""
        content = data[cls.data_type]
        return cls(content)

    def __rich__(self) -> str:
        """Render the LaTeX display data."""
        rendered_latex: str = latex2text.LatexNodes2Text(
            math_mode="text", fill_text=True, strict_latex_spaces=False
        ).latex_to_text(self.content)
        return rendered_latex


@dataclasses.dataclass
class JSONDisplay(DisplayData):
    """Notebook JSON display data."""

    theme: str
    data_type: ClassVar[str] = "application/json"

    @classmethod
    def from_data(cls, data: Data, theme: str) -> JSONDisplay:
        """Create JSON display data from notebook data."""
        content = json.dumps(data[cls.data_type])
        return cls(content, theme=theme)

    def __rich__(self) -> Syntax:
        """Render the JSON display data."""
        rendered_json = syntax.Syntax(
            self.content,
            lexer_name="json",
            theme=self.theme,
            background_color="default",
        )
        return rendered_json


@dataclasses.dataclass
class PDFDisplay(DisplayData):
    """Notebook PDF display data."""

    nerd_font: bool
    unicode: bool
    data_type: ClassVar[str] = "application/pdf"

    def __rich__(self) -> Union[str, Emoji]:
        """Render the PDF display data."""
        rendered_pdf = link.select_icon(
            "",
            emoji_name="page_facing_up",
            nerd_font=self.nerd_font,
            unicode=self.unicode,
        )
        return rendered_pdf

    @classmethod
    def from_data(
        cls,
        data: Data,
        nerd_font: bool,
        unicode: bool,
    ) -> PDFDisplay:
        """Create PDF display data from notebook data."""
        content = data[cls.data_type]
        return cls(content, nerd_font=nerd_font, unicode=unicode)
