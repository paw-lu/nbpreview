"""Functions for rendering notebook components."""
from typing import Iterator
from typing import Union

from nbformat import NotebookNode
from rich import padding
from rich import syntax
from rich import text
from rich.padding import Padding
from rich.syntax import Syntax
from rich.text import Text


def render_error(output: NotebookNode, theme: str) -> Iterator[Syntax]:
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
