"""Notebook display data and execute result."""

import collections
import dataclasses
import enum
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar, TypeAlias

import html2text
from lxml import html
from lxml.html import HtmlElement
from rich import measure, syntax, text
from rich.console import Console, ConsoleOptions, ConsoleRenderable
from rich.emoji import Emoji
from rich.measure import Measurement
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from nbpreview.component import markdown
from nbpreview.component.content.output.result import drawing, latex, link, table
from nbpreview.component.content.output.result.drawing import Drawing, ImageDrawing
from nbpreview.component.markdown import CustomMarkdown
from nbpreview.data import Data


@dataclasses.dataclass
class DisplayData:
    """A notebook's display data."""

    content: str
    data_type: ClassVar[str]

    def __rich__(self) -> ConsoleRenderable | str:
        """Render the display."""
        return self.content


@dataclasses.dataclass
class PlainDisplay(DisplayData):
    """Notebook plain display data."""

    data_type: ClassVar[str] = "text/plain"

    @classmethod
    def from_data(cls, data: Data) -> "PlainDisplay":
        """Create a plain display data from notebook data."""
        content = _get_content(data, data_type=cls.data_type)
        return cls(content)


def _get_content(data: Data, data_type: str) -> str:
    """Extract the content form the data."""
    content = (
        data_type_content
        if isinstance((data_type_content := data[data_type]), str)
        else ""
    )
    return content


@dataclasses.dataclass
class HTMLDisplay(DisplayData):
    """Notebook HTML display data."""

    theme: str
    nerd_font: bool
    unicode: bool
    images: bool
    image_drawing: ImageDrawing
    color: bool
    negative_space: bool
    hyperlinks: bool
    files: bool
    hide_hyperlink_hints: bool
    relative_dir: Path
    characters: str | None = None
    data_type: ClassVar[str] = "text/html"

    @classmethod
    def from_data(
        cls,
        data: Data,
        theme: str,
        nerd_font: bool,
        unicode: bool,
        images: bool,
        image_drawing: ImageDrawing,
        color: bool,
        negative_space: bool,
        hyperlinks: bool,
        files: bool,
        hide_hyperlink_hints: bool,
        relative_dir: Path,
        characters: str | None = None,
    ) -> "HTMLDisplay":
        """Create an HTML display data from notebook data."""
        content = _get_content(data, data_type=cls.data_type)
        return cls(
            content,
            theme=theme,
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
        )

    def __rich__(self) -> CustomMarkdown:
        """Render the HTML display data."""
        converted_markdown = html2text.html2text(self.content)
        rendered_html = markdown.CustomMarkdown(
            converted_markdown,
            theme=self.theme,
            unicode=self.unicode,
            images=self.images,
            image_drawing=self.image_drawing,
            color=self.color,
            negative_space=self.negative_space,
            hyperlinks=self.hyperlinks,
            files=self.files,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
            characters=self.characters,
            relative_dir=self.relative_dir,
        )
        return rendered_html


def _render_table_element(column: HtmlElement, column_width: int) -> list[Text]:
    """Render a DataFrame table element.

    Args:
        column (HtmlElement): The HTML element to render.
        column_width (int): The width of the column to render.

    Returns:
        List[Text]: The rendered DataFrame element.
    """
    attributes = column.attrib
    column_width = int(attributes.get("colspan", 1))
    header = column.tag == "th"
    column_string = column.text.strip() if column.text is not None else ""
    element_text = table.create_table_element(column_string, header=header)
    table_element = (column_width - 1) * [text.Text("")] + [element_text]
    return table_element


@dataclasses.dataclass
class HTMLDataFrameRender:
    """Rich counterpart of HTML table."""

    unicode: bool
    min_width: int = 4

    def __post_init__(self) -> None:
        """Constructor."""
        self.table = table.create_table(unicode=self.unicode)
        self.column_widths: list[int] | None = None

    def _update_column_widths(self, row: list[Text]) -> None:
        """Update the column widths with the current row."""
        row_widths = [text.cell_len for text in row]
        if self.column_widths is None:
            self.column_widths = row_widths
        else:
            self.column_widths = [
                max(current_column_width, row_column_width)
                for current_column_width, row_column_width in zip(
                    self.column_widths, row_widths, strict=False
                )
            ]

    def add_headers(self, column_rows: list[HtmlElement]) -> None:
        """Add headers to table."""
        n_column_rows = len(column_rows)
        for i, column_row in enumerate(column_rows):
            table_row = []
            for column in column_row.xpath("th|td"):
                attributes = column.attrib
                column_width = int(attributes.get("colspan", 1))

                if i == 0:
                    for _ in range(column_width):
                        self.table.add_column(justify="right")

                table_element = _render_table_element(column, column_width=column_width)
                table_row.extend(table_element)

            end_section = i == n_column_rows - 1
            self._update_column_widths(table_row)
            self.table.add_row(*table_row, end_section=end_section)

    def add_data(self, data_rows: list[HtmlElement]) -> None:
        """Add data rows to table."""
        previous_row_spans: dict[int, int] = {}
        for row in data_rows:
            table_row = []
            current_row_spans: dict[int, int] = collections.defaultdict(int)
            for i, column in enumerate(row.xpath("th|td")):
                attributes = column.attrib
                column_width = int(attributes.get("colspan", 1))
                row_span = int(attributes.get("rowspan", 1))
                table_element = _render_table_element(column, column_width=column_width)
                table_row.extend(table_element)

                if row_span > 1:
                    current_row_spans[i] += row_span

            for column, row_span in previous_row_spans.copy().items():
                table_row.insert(column, text.Text(""))
                remaining_span = row_span - 1

                if remaining_span > 1:
                    previous_row_spans[column] = remaining_span
                else:
                    previous_row_spans.pop(column, None)

            previous_row_spans = {
                column: previous_row_spans.get(column, 0)
                + current_row_spans.get(column, 0)
                for column in previous_row_spans.keys() | current_row_spans.keys()
            }
            self._update_column_widths(table_row)
            self.table.add_row(*table_row)

        if table.is_only_header(self.table):
            # Divide won't show up unless there is content underneath
            self.table.add_row("")

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Table]:
        """Render the DataFrame table."""
        if self.column_widths is not None:
            for table_column, column_width in zip(
                self.table.columns, self.column_widths, strict=False
            ):
                table_column.min_width = min(column_width, self.min_width)
        yield self.table

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        """Define the dimensions of the rendered DataFrame."""
        measurement = measure.Measurement.get(
            console=console, options=options, renderable=self.table
        )
        return measurement


def _render_dataframe(
    dataframe_html: HtmlElement, unicode: bool
) -> HTMLDataFrameRender:
    """Render a DataFrame from its HTML.

    Args:
        dataframe_html (HtmlElement): The DataFrame rendered as HTML.
        unicode (bool): Whether to use unicode characters when rendering
            the table.

    Returns:
        HTMLDataFrameRender: The DataFrame rendered as a Rich Table.
    """
    thead_element = dataframe_html.find("thead")
    column_rows = thead_element.findall("tr") if thead_element is not None else []

    rendered_html_dataframe = HTMLDataFrameRender(unicode=unicode)
    rendered_html_dataframe.add_headers(column_rows)

    tbody_element = dataframe_html.find("tbody")
    data_rows = tbody_element.findall("tr") if tbody_element is not None else []
    rendered_html_dataframe.add_data(data_rows)

    return rendered_html_dataframe


class DataFrameDisplayType(enum.Enum):
    """The type of DataFrame HTML output."""

    PLAIN = enum.auto()
    STYLED = enum.auto()


@dataclasses.dataclass
class DataFrameDisplay(DisplayData):
    """Notebook DataFrame display data."""

    unicode: bool
    styled: bool = False
    data_type: ClassVar[str] = "text/html"

    @staticmethod
    def dataframe_display_type(content: str) -> DataFrameDisplayType | None:
        """Determine the type of DataFrame output."""
        html_element = html.fromstring(content)

        table_html = html_element.find_class("dataframe")
        if table_html and table_html[0].tag == "table":
            return DataFrameDisplayType.PLAIN

        # Basic check for styled dataframe
        try:
            style_element, *non_style_elements = html_element.head.iterchildren()
            *non_table_elements, table_element = html_element.body.iterchildren()

        except (ValueError, IndexError, AttributeError):
            pass

        else:
            if (
                len(non_style_elements) == 0
                and style_element.tag == "style"
                and style_element.attrib == {"type": "text/css"}
                and len(non_table_elements) <= 1
                and table_element.tag == "table"
            ):
                return DataFrameDisplayType.STYLED

        return None

    @classmethod
    def from_data(cls, data: Data, unicode: bool, styled: bool) -> "DataFrameDisplay":
        """Create DataFrame display data from notebook data."""
        content = (
            data_content
            if isinstance((data_content := data[cls.data_type]), str)
            else ""
        )
        return cls(content, unicode=unicode, styled=styled)

    def __rich__(self) -> HTMLDataFrameRender:
        """Render the DataFrame display data."""
        if self.styled:
            dataframe_html, *_ = html.fromstring(self.content).xpath("//body/table")
        else:
            dataframe_html, *_ = html.fromstring(self.content).find_class("dataframe")
        rendered_dataframe = _render_dataframe(dataframe_html, unicode=self.unicode)
        return rendered_dataframe


@dataclasses.dataclass
class MarkdownDisplay(DisplayData):
    """Notebook Markdown display data."""

    theme: str
    nerd_font: bool
    unicode: bool
    images: bool
    image_drawing: ImageDrawing
    color: bool
    negative_space: bool
    hyperlinks: bool
    files: bool
    hide_hyperlink_hints: bool
    relative_dir: Path
    characters: str | None = None
    data_type: ClassVar[str] = "text/markdown"

    @classmethod
    def from_data(
        cls,
        data: Data,
        theme: str,
        nerd_font: bool,
        unicode: bool,
        images: bool,
        image_drawing: ImageDrawing,
        color: bool,
        negative_space: bool,
        hyperlinks: bool,
        files: bool,
        hide_hyperlink_hints: bool,
        relative_dir: Path,
        characters: str | None = None,
    ) -> "MarkdownDisplay":
        """Create Markdown display data from notebook data."""
        content = _get_content(data, data_type=cls.data_type)
        return cls(
            content,
            theme=theme,
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
        )

    def __rich__(self) -> CustomMarkdown:
        """Render the Markdown display data."""
        rendered_markdown = markdown.CustomMarkdown(
            self.content,
            theme=self.theme,
            unicode=self.unicode,
            images=self.images,
            image_drawing=self.image_drawing,
            color=self.color,
            negative_space=self.negative_space,
            hyperlinks=self.hyperlinks,
            files=self.files,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
            characters=self.characters,
            relative_dir=self.relative_dir,
        )
        return rendered_markdown


@dataclasses.dataclass
class LaTeXDisplay(DisplayData):
    """Notebook LaTeX display data."""

    data_type: ClassVar[str] = "text/latex"

    @classmethod
    def from_data(cls, data: Data) -> "LaTeXDisplay":
        """Create LaTeX display data from notebook data."""
        content = _get_content(data, data_type=cls.data_type)
        return cls(content)

    def __rich__(self) -> str:
        """Render the LaTeX display data."""
        rendered_latex: str = latex.render_latex(self.content)
        return rendered_latex


@dataclasses.dataclass
class JSONDisplay(DisplayData):
    """Notebook JSON display data."""

    theme: str
    data_type: ClassVar[str] = "application/json"

    @classmethod
    def from_data(cls, data: Data, theme: str) -> "JSONDisplay":
        """Create JSON display data from notebook data."""
        content = json.dumps(data[cls.data_type])
        return cls(content, theme=theme)

    def __rich__(self) -> Syntax:
        """Render the JSON display data."""
        rendered_json = syntax.Syntax(
            self.content,
            lexer="json",
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

    def __rich__(self) -> str | Emoji:
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
    ) -> "PDFDisplay":
        """Create PDF display data from notebook data."""
        content = _get_content(data, data_type=cls.data_type)
        return cls(content, nerd_font=nerd_font, unicode=unicode)


def _has_custom_repr(data: Data) -> bool:
    """Rough logic to check if data has a custom representation."""
    repr_pattern = r"\<([^\s<>]|[^\S\n\v\f\r\u2028\u2029])+\>"
    has_custom_repr = (
        (plain_text := data.get("text/plain")) is not None
        and isinstance(plain_text, str)
        and re.fullmatch(repr_pattern, plain_text, flags=re.UNICODE) is None
    )
    return has_custom_repr


Renderer: TypeAlias = (
    DataFrameDisplay
    | HTMLDisplay
    | MarkdownDisplay
    | LaTeXDisplay
    | JSONDisplay
    | PDFDisplay
    | PlainDisplay
)


def _choose_basic_renderer(
    data: Data,
    unicode: bool,
    nerd_font: bool,
    theme: str,
    images: bool,
    image_drawing: ImageDrawing,
    color: bool,
    negative_space: bool,
    hyperlinks: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    relative_dir: Path,
    characters: str | None = None,
) -> Renderer | None:
    """Render straightforward text data."""
    display_data: DisplayData
    if (html_data := data.get("text/html")) is not None:
        if (
            isinstance(html_data, str)
            and (
                dataframe_display_type := DataFrameDisplay.dataframe_display_type(
                    html_data
                )
            )
            is not None
        ):
            styled = dataframe_display_type == DataFrameDisplayType.STYLED
            display_data = DataFrameDisplay.from_data(
                data, unicode=unicode, styled=styled
            )
            return display_data
        if not _has_custom_repr(data):
            display_data = HTMLDisplay.from_data(
                data,
                theme=theme,
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
            )
            return display_data
    if "text/markdown" in data:
        display_data = MarkdownDisplay.from_data(
            data,
            theme=theme,
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
        )
        return display_data
    if unicode and "text/latex" in data:
        display_data = LaTeXDisplay.from_data(data)
        return display_data
    if "application/json" in data:
        display_data = JSONDisplay.from_data(data, theme=theme)
        return display_data
    if (unicode or nerd_font) and "application/pdf" in data:
        display_data = PDFDisplay.from_data(data, nerd_font=nerd_font, unicode=unicode)
        return display_data
    if "text/plain" in data:
        display_data = PlainDisplay.from_data(data)
        return display_data
    return None


def render_display_data(
    data: Data,
    unicode: bool,
    nerd_font: bool,
    theme: str,
    images: bool,
    image_drawing: ImageDrawing,
    color: bool,
    negative_space: bool,
    hyperlinks: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    relative_dir: Path,
    characters: str | None = None,
) -> DisplayData | None | Drawing:
    """Render the notebook display data."""
    display_data: DisplayData | None | Drawing
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
                    data=data,
                    image_drawing=image_drawing,
                    image_type=image_type,
                    color=color,
                    negative_space=negative_space,
                )
                if display_data is not None:
                    return display_data

    display_data = _choose_basic_renderer(
        data,
        unicode=unicode,
        nerd_font=nerd_font,
        theme=theme,
        images=images,
        image_drawing=image_drawing,
        color=color,
        negative_space=negative_space,
        hyperlinks=hyperlinks,
        files=files,
        hide_hyperlink_hints=hide_hyperlink_hints,
        characters=characters,
        relative_dir=relative_dir,
    )
    return display_data
