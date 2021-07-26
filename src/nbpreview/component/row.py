"""Jupyter notebook rows."""
import dataclasses
from dataclasses import InitVar
from typing import Optional
from typing import Tuple
from typing import Union

from nbformat import NotebookNode
from rich import padding
from rich import text
from rich.padding import Padding
from rich.text import Text

from . import input
from .input import Cell


@dataclasses.dataclass
class Execution:
    """The execution count indicator."""

    execution_count: Union[int, None]
    top_pad: bool
    execution_indicator: Union[Text, Padding] = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        """Initialize execution indicator."""
        execution_indicator: Union[Text, Padding]
        if self.execution_count is None:
            execution_text = " "
        else:
            execution_text = str(self.execution_count)
        execution_indicator = text.Text(f"[{execution_text}]:", style="color(247)")

        if self.top_pad:
            execution_indicator = padding.Padding(execution_indicator, pad=(1, 0, 0, 0))

        self.execution_indicator = execution_indicator

    def __rich__(self) -> Union[Padding, Text]:
        """Render the execution indicator."""
        return self.execution_indicator


TableRow = Union[Tuple[Union[Execution, str], Cell], Tuple[Cell]]


def choose_execution(execution: Union[None, Execution]) -> Union[str, Execution]:
    """Select the execution indicator."""
    return execution if execution is not None else ""


@dataclasses.dataclass
class Row:
    """A Jupyter notebook row."""

    cell: Cell
    plain: bool
    execution: InitVar[Optional[Execution]] = None

    def __post_init__(self, execution: Optional[Execution]) -> None:
        """Initialize the execution indicator."""
        self.execution: Union[Execution, str]
        self.execution = choose_execution(execution)

    def to_table_row(self) -> TableRow:
        """Convert to row for table usage."""
        table_row: TableRow
        if self.plain:
            table_row = (self.cell,)
        else:
            table_row = (self.execution, self.cell)
        return table_row


def render_input_row(
    cell: NotebookNode,
    plain: bool,
    pad: Tuple[int, int, int, int],
    language: str,
    theme: str,
    unicode_border: Optional[bool] = None,
) -> Row:
    """Render a Jupyter Notebook cell.

    Args:
        cell (NotebookNode): The cell to render.
        plain (bool): Only show plain style. No decorations such as
            boxes or execution counts.
        pad (Tuple[int, int, int, int]): The output padding to use.
        language (str): The programming language of the notebook. Will
            be used when highlighting the syntax of code cells.
        theme (str): The theme to use for syntax highlighting. May be
            "ansi_light", "ansi_dark", or any Pygments theme. By default
            "ansi_dark".
        unicode_border (Optional[bool]): Whether to render the cell
            borders using unicode characters. Will autodetect by
            default.

    Returns:
        Row: The execution count indicator and cell
            content.
    """
    cell_type = cell.get("cell_type")
    source = cell.source
    default_lexer_name = "ipython" if language == "python" else language
    safe_box = None if unicode_border is None else not unicode_border
    rendered_cell: Optional[Cell] = None
    execution: Union[Execution, None] = None
    top_pad = not plain
    if cell_type == "markdown":
        rendered_cell = input.MarkdownCell(source, theme=theme, pad=pad)

    elif cell_type == "code":
        execution = Execution(cell.execution_count, top_pad=top_pad)
        rendered_cell = input.CodeCell(
            source,
            plain=plain,
            safe_box=safe_box,
            theme=theme,
            default_lexer_name=default_lexer_name,
        )

    # Includes cell_type == "raw"
    else:
        rendered_cell = Cell(source, plain=plain, safe_box=safe_box)

    cell_row = Row(rendered_cell, plain=plain, execution=execution)
    return cell_row
