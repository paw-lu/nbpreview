"""Render the notebook."""
from typing import Iterator
from typing import Tuple
from typing import Union

import pygments
from nbformat.notebooknode import NotebookNode
from rich import markdown
from rich import panel
from rich import syntax
from rich import table
from rich import text
from rich.console import Console
from rich.console import ConsoleOptions
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

Cell = Union[Markdown, Panel, Text, Syntax]


class Notebook:
    """Construct a Notebook object to render Jupyter Notebooks.

    Args:
        notebook_node (NotebookNode): A NotebookNode of the notebook to
            render.
        theme (str): The theme to use for syntax highlighting. May be
            "ansi_light", "ansi_dark", or any Pygments theme. By default
            "ansi_dark".
        plain (bool): Only show plain style. No decorations such as
            boxes or execution counts. By default False.
    """

    def __init__(
        self, notebook_node: NotebookNode, theme: str = "ansi_dark", plain: bool = False
    ) -> None:
        """Initialize."""
        self.cells = notebook_node.cells
        self.language = notebook_node.metadata.kernelspec.language
        self.theme = theme
        self.plain = plain

    def _render_execution_indicator(
        self, execution_count: Union[str, int, None]
    ) -> Text:
        """Render the execution indicator.

        Args:
            execution_count (Union[str, int, None]): The execution
                count. Set to None if there is no execution count.

        Returns:
            Text: The rendered execution indicator.
        """
        if execution_count is None:
            execution_indicator = ""
        else:
            execution_indicator = f"\n[{execution_count}]:"
        return text.Text(execution_indicator, style="color(247)")

    def _render_cells(self, cell: NotebookNode) -> Tuple[Text, Cell]:
        """Render a Jupyter Notebook cell.

        Args:
            cell (NotebookNode): The cell to render

        Returns:
            Tuple[Text, Cell]: The execution count indicator and cell
                content.
        """
        cell_type = cell.get("cell_type", False)
        source = cell.source
        default_lexer_name = "ipython" if self.language == "python" else self.language

        if cell_type == "markdown":
            execution_count = None
            rendered_cell: Cell = markdown.Markdown(
                source, inline_code_theme=self.theme
            )

        elif cell_type == "code":
            execution_count = (
                cell.execution_count if cell.execution_count is not None else " "
            )
            rendered_source: Cell = syntax.Syntax(
                source,
                lexer_name=default_lexer_name,
                theme=self.theme,
                background_color="default",
            )

            if source.startswith("%%"):
                try:
                    magic, body = source.split("\n", 1)
                    language_name = magic.lstrip("%")
                    body_lexer_name = pygments.lexers.get_lexer_by_name(
                        language_name
                    ).name
                    # Syntax needs a string in the init, so pass an
                    # empty string and then pass the actual code to
                    # highlight method
                    magic_syntax = syntax.Syntax(
                        "",
                        lexer_name=default_lexer_name,
                        theme=self.theme,
                        background_color="default",
                    ).highlight(magic)
                    body_syntax = syntax.Syntax(
                        "",
                        lexer_name=body_lexer_name,
                        theme=self.theme,
                        background_color="default",
                    ).highlight(body)
                    rendered_source = text.Text().join((magic_syntax, body_syntax))

                except pygments.util.ClassNotFound:
                    pass

            if not self.plain:
                rendered_cell = panel.Panel(
                    rendered_source,
                    expand=True,
                )
            else:
                rendered_cell = rendered_source

        else:
            execution_count = None
            rendered_cell = panel.Panel(source)

        execution_count_indicator = self._render_execution_indicator(execution_count)
        return execution_count_indicator, rendered_cell

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> Iterator[Table]:
        """Render the Notebook to the terminal.

        Args:
            console (Console): The Rich Console object.
            options (ConsoleOptions): The Rich Console options.

        Yields:
            Iterator[RenderResult]: The
        """
        grid = table.Table.grid(
            padding=(0, 1, 0, 0),
            collapse_padding=True,
        )
        if not self.plain:
            grid.add_column(justify="right")
        grid.add_column()

        for cell in self.cells:
            execution_count_indicator, source = self._render_cells(cell)
            cell_row = (
                (execution_count_indicator, source) if not self.plain else (source,)
            )
            grid.add_row(*cell_row)

        yield grid
