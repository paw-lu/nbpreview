"""Render a table."""

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


def is_only_header(rich_table: Table) -> bool:
    """Detect if table is only headers and no content."""
    only_header = rich_table.row_count >= 1 and rich_table.rows[-1].end_section
    return only_header


def create_table_element(element_data: str, header: bool) -> Text:
    """Create a single table element."""
    text_style: str | Style = style.Style(bold=True) if header else ""
    rich_text = text.Text(element_data, style=text_style)
    return rich_text
