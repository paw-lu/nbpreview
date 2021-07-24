"""Jupyter notebook rows."""
import dataclasses
from dataclasses import InitVar
from typing import Optional
from typing import Tuple
from typing import Union

from rich import padding
from rich import text
from rich.padding import Padding
from rich.text import Text

from .input import Cell


@dataclasses.dataclass
class Execution:
    """The execution count indicator."""

    execution_count: Union[int, None]
    top_pad: bool

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


@dataclasses.dataclass
class Row:
    """A Jupyter notebook row."""

    cell: Cell
    plain: bool
    execution: InitVar[Optional[Execution]] = None

    def __post_init__(self, execution: Optional[Execution]) -> None:
        """Initialize the execution indicator."""
        self.execution: Union[Execution, str]
        self.execution = execution if execution is not None else ""

    def to_table_row(self) -> TableRow:
        """Convert to row for table usage."""
        table_row: TableRow
        if self.plain:
            table_row = (self.cell,)
        else:
            table_row = (self.execution, self.cell)
        return table_row
