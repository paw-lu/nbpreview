"""Jupyter execution indicators."""
import dataclasses

from rich import padding, text
from rich.padding import Padding
from rich.text import Text


@dataclasses.dataclass
class Execution:
    """The execution count indicator."""

    execution_count: int | None
    top_pad: bool
    execution_indicator: Text | Padding = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        """Initialize execution indicator."""
        execution_indicator: Text | Padding
        if self.execution_count is None:
            execution_text = " "
        else:
            execution_text = str(self.execution_count)
        execution_indicator = text.Text(f"[{execution_text}]:", style="color(247)")

        if self.top_pad:
            execution_indicator = padding.Padding(execution_indicator, pad=(1, 0, 0, 0))

        self.execution_indicator = execution_indicator

    def __rich__(self) -> Padding | Text:
        """Render the execution indicator."""
        return self.execution_indicator


def choose_execution(execution: None | Execution) -> str | Execution:
    """Select the execution indicator."""
    return execution if execution is not None else ""
