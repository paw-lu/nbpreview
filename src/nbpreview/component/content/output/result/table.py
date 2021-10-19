"""Render a table."""
from typing import Union

from rich import box, style, table, text
from rich.style import Style
from rich.table import Table
from rich.text import Text


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
