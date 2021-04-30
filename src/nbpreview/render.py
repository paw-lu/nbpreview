"""Render the notebook."""
import dataclasses
from typing import Iterator
from typing import Optional
from typing import Tuple
from typing import Union

import pygments
from nbformat.notebooknode import NotebookNode
from rich import markdown
from rich import padding
from rich import panel
from rich import syntax
from rich import table
from rich import text
from rich.console import Console
from rich.console import ConsoleOptions
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

Cell = Union[Padding, Markdown, Panel, Text, Syntax, str]


@dataclasses.dataclass()
class Notebook:
    """Construct a Notebook object to render Jupyter Notebooks.

    Args:
        notebook_node (NotebookNode): A NotebookNode of the notebook to
            render.
        theme (str): The theme to use for syntax highlighting. May be
            "ansi_light", "ansi_dark", or any Pygments theme. By default
            "ansi_dark".
        plain (bool): Only show plain style. No decorations such as
            boxes or execution counts. By default will autodetect.
        unicode (Optional[bool]): Whether to use unicode characters to
            render the notebook. By default will autodetect.
    """

    notebook_node: NotebookNode
    theme: str = "ansi_dark"
    plain: Optional[bool] = None
    unicode: Optional[bool] = None
    hide_output: bool = False

    def __post_init__(self) -> None:
        """Constructor."""
        self.cells = self.notebook_node.cells
        self.language = self.notebook_node.metadata.kernelspec.language

    def _render_execution_indicator(
        self, execution_count: Union[str, int, None], pad: bool
    ) -> Union[Text, Padding]:
        """Render the execution indicator.

        Args:
            execution_count (Union[str, int, None]): The execution
                count. Set to None if there is no execution count.
            pad (bool): Whether to top pad the indicator count. Useful
                if aligned with a code cell box and the execution count
                should be aligned with the content.

        Returns:
            Text: The rendered execution indicator.
        """
        execution_indicator: Union[Text, Padding]
        if execution_count is None:
            execution_text = ""
        else:
            execution_text = f"[{execution_count}]:"
        execution_indicator = text.Text(execution_text, style="color(247)")

        if pad:
            execution_indicator = padding.Padding(execution_indicator, pad=(1, 0, 0, 0))

        return execution_indicator

    def _get_output_pad(self, plain: bool) -> Tuple[int, int, int, int]:
        """Return the padding for outputs.

        Args:
            plain (bool): Only show plain style. No decorations such as
                boxes or execution counts.

        Returns:
            Tuple[int, int, int, int]: The padding for outputs.
        """
        if plain:
            return (0, 0, 0, 0)
        else:
            return (0, 0, 0, 1)

    def _render_cells(
        self,
        cell: NotebookNode,
        plain: bool = False,
        unicode_border: Optional[bool] = None,
    ) -> Tuple[Union[Text, Padding], Cell]:
        """Render a Jupyter Notebook cell.

        Args:
            cell (NotebookNode): The cell to render.
            plain (bool): Only show plain style. No decorations such as
                boxes or execution counts. By default False.
            unicode_border (Optional[bool]): Whether to render the cell
                borders using unicode characters. Will autodetect by
                default.

        Returns:
            Tuple[Text, Cell]: The execution count indicator and cell
                content.
        """
        cell_type = cell.get("cell_type")
        source = cell.source
        default_lexer_name = "ipython" if self.language == "python" else self.language

        output_pad = self._get_output_pad(plain)
        rendered_cell: Optional[Cell] = None
        rendered_source: Union[Text, Syntax, str]
        if cell_type == "markdown":
            execution_count = None
            rendered_cell = padding.Padding(
                markdown.Markdown(source, inline_code_theme=self.theme),
                pad=output_pad,
            )

        elif cell_type == "code":
            execution_count = (
                cell.execution_count if cell.execution_count is not None else " "
            )
            rendered_source = syntax.Syntax(
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

        else:
            execution_count = None
            rendered_source = source

        if rendered_cell is None:
            if not plain:
                safe_box = None if unicode_border is None else not unicode_border
                rendered_cell = panel.Panel(rendered_source, safe_box=safe_box)
            else:
                rendered_cell = rendered_source

        execution_count_indicator = self._render_execution_indicator(
            execution_count, pad=not plain
        )
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
        if self.plain is None:
            if options.is_terminal:
                plain = False
            else:
                plain = True
        else:
            plain = self.plain

        grid = table.Table.grid(padding=(1, 1, 1, 0))
        if not plain:
            grid.add_column(justify="right")
        grid.add_column()

        for cell in self.cells:
            execution_count_indicator, source = self._render_cells(
                cell, plain=plain, unicode_border=self.unicode
            )
            cell_row = (execution_count_indicator, source) if not plain else (source,)
            grid.add_row(*cell_row)

        yield grid
