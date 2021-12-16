"""Render a table."""
import dataclasses
import itertools
from collections import abc
from typing import Iterator, Union

import markdown_it
from markdown_it.token import Token
from rich import box, markdown, style, table, text
from rich.markdown import Markdown
from rich.style import Style
from rich.table import Table
from rich.text import Text

from nbpreview import errors


def create_table(unicode: bool) -> Table:
    """Create a rich table."""
    rich_table = table.Table(
        show_edge=False,
        show_header=False,
        box=box.HORIZONTALS,
        show_footer=False,
        safe_box=not unicode,
    )
    return rich_table


def create_table_element(element_data: str, header: bool) -> Text:
    """Create a single table element."""
    text_style: Union[str, Style] = style.Style(bold=True) if header else ""
    rich_text = text.Text(element_data, style=text_style)
    return rich_text


def is_only_header(rich_table: Table) -> bool:
    """Detect if table is only headers and no content."""
    only_header = 1 <= rich_table.row_count and rich_table.rows[-1].end_section
    return only_header


@dataclasses.dataclass
class TableSection:
    """A section of rendered Markdown containing a table."""

    table: Table
    start_line: int
    end_line: int


class NotIteratorError(ValueError, errors.NBPreviewError):
    """Error when not an iterator."""

    def __init__(self, arg_name: str) -> None:
        """Constructor."""
        super().__init__(f"{arg_name} not an iterator")


class NotUniqueError(ValueError, errors.NBPreviewError):
    """Error when arguments are not unique."""

    def __init__(self, *args: str) -> None:
        """Constructor."""
        argument_names = ", ".join(args)
        super().__init__(f"{argument_names} must be unique")


def _group_tokens(
    iterator: Iterator[Token], open_tag: str, close_tag: str
) -> Iterator[Iterator[Token]]:
    """Group tokens bounded by tags into separate iterators."""
    if not isinstance(iterator, abc.Iterator):
        raise NotIteratorError("iterator")
    if open_tag == close_tag:
        raise NotUniqueError(open_tag, close_tag)
    for token in iterator:
        if token.type == open_tag:
            yield itertools.takewhile(lambda token_: token_.type != close_tag, iterator)


def _parse_table_element(element: str, header: bool) -> Markdown:
    """Parse the text in a table element as Markdown."""
    if header and element.strip():
        element = f"**{element}**"
    table_element = markdown.Markdown(element)
    return table_element


def parse_markdown_tables(markup: str, unicode: bool) -> Iterator[TableSection]:
    """Return parsed tables from markdown."""
    markdown_parser = markdown_it.MarkdownIt("zero").enable("table")
    parsed_markup = markdown_parser.parse(markup)
    is_header = {"th_open": True, "td_open": False}
    iter_parsed_markup = iter(parsed_markup)
    for parsed_table in _group_tokens(
        iter_parsed_markup, open_tag="table_open", close_tag="table_close"
    ):
        start_line = None
        rich_table = create_table(unicode)
        for parsed_row in _group_tokens(
            parsed_table, open_tag="tr_open", close_tag="tr_close"
        ):
            row_text = []
            header = False
            end_section = True
            for token in parsed_row:
                if token.type in is_header:
                    header = is_header[token.type]
                    if token.type == "td_open":
                        end_section = False

                elif token.type == "inline":
                    row_text.append(
                        _parse_table_element(
                            token.children[0].content
                            if token.children
                            else token.content,
                            header=header,
                        )
                    )
                    current_line, *_ = token.map or (0, None)
                    if start_line is None:
                        start_line, *_ = token.map or (0, None)
                        end_line = start_line + 1
                    end_line = max(end_line, current_line)
                else:
                    header = False

            rich_table.add_row(*row_text, end_section=end_section)

        if is_only_header(rich_table):
            rich_table.add_row("")

        yield TableSection(rich_table, start_line=start_line or 0, end_line=end_line)
