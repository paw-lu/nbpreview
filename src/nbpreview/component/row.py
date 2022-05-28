"""Jupyter notebook rows."""
import dataclasses
import itertools
from dataclasses import InitVar
from pathlib import Path
from typing import Iterator, List, Optional, Tuple, Union

from nbformat import NotebookNode
from rich import padding
from rich.padding import Padding, PaddingDimensions

from nbpreview.component.content import input
from nbpreview.component.content.input import Cell
from nbpreview.component.content.output import error, stream
from nbpreview.component.content.output.output import Output
from nbpreview.component.content.output.result import execution_indicator, result
from nbpreview.component.content.output.result.drawing import ImageDrawing
from nbpreview.component.content.output.result.execution_indicator import Execution

Content = Union[Cell, Padding]
TableRow = Union[Tuple[Union[Execution, str], Content], Tuple[Content]]


@dataclasses.dataclass
class Row:
    """A Jupyter notebook row."""

    content: Content
    plain: bool
    execution: InitVar[Optional[Execution]] = None

    def __post_init__(self, execution: Optional[Execution]) -> None:
        """Initialize the execution indicator."""
        self.execution_indicator: Union[Execution, str]
        self.execution_indicator = execution_indicator.choose_execution(execution)

    def to_table_row(self) -> TableRow:
        """Convert to row for table usage."""
        table_row: TableRow
        if self.plain:
            table_row = (self.content,)
        else:
            table_row = (self.execution_indicator, self.content)
        return table_row


@dataclasses.dataclass(init=False)
class OutputRow(Row):
    """A Jupyter output row."""

    def __init__(
        self,
        content: Output,
        plain: bool,
        pad: PaddingDimensions,
        execution: Optional[Execution] = None,
    ) -> None:
        """Constructor."""
        padded_content = padding.Padding(content, pad=pad)
        super().__init__(padded_content, plain=plain, execution=execution)


def render_input_row(
    cell: NotebookNode,
    plain: bool,
    pad: Tuple[int, int, int, int],
    language: str,
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
    characters: Optional[str] = None,
    unicode_border: Optional[bool] = None,
    line_numbers: bool = False,
    code_wrap: bool = False,
) -> Union[Row, None]:
    """Render a Jupyter Notebook cell.

    Args:
        cell (NotebookNode): The cell to render.
        plain (bool): Only show plain style. No decorations such as
            boxes or execution counts.
        pad (Tuple[int, int, int, int]): The output padding to use.
        language (str): The programming language of the notebook. Will
            be used when highlighting the syntax of code cells.
        theme (str): The theme to use for syntax highlighting. May be
            "ansi_light", "ansi_dark", or any Pygments theme.
        nerd_font (bool): Whether to use nerd fonts as an icon.
        unicode (bool): Whether to use unicode characters as an icon.
        images (bool): Whether to render images in the output.
        image_drawing (ImageDrawing): The type of characters to draw
            images with.
        color (bool):
            Whether to draw images using color.
        negative_space (bool):
            Whether to draw only the dark areas of an image with
                characters.
        hyperlinks (bool):
            Whether to render terminal hyperlinks.
        files (bool):
            Whether to write temporary files.
        hide_hyperlink_hints (bool):
            Whether to hide hyperlink hints.
        relative_dir (Path): The directory to prefix relative
            paths to convert them to absolute. If None will assume
            current directory is relative prefix.
        characters (str):
            The characters to draw images with. If set to None will
            default to ' :!?PG@'.
        unicode_border (Optional[bool]): Whether to render the cell
            borders using unicode characters. Will autodetect by
            default.
        line_numbers (bool): Whether to render line numbers in code
            cells. By default False.
        code_wrap (bool): Whether to wrap code if it does not fit. By
            default False.

    Returns:
        Row: The execution count indicator and cell content if cell type
            is known, else None.
    """
    cell_type = cell.get("cell_type")
    source = cell.source
    default_lexer_name = "ipython" if language == "python" else language
    safe_box = None if unicode_border is None else not unicode_border
    rendered_cell: Optional[Cell] = None
    execution: Union[Execution, None] = None
    top_pad = not plain
    if cell_type == "markdown":
        rendered_cell = input.MarkdownCell(
            source,
            theme=theme,
            pad=pad,
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

    elif cell_type == "code":
        execution = Execution(cell.execution_count, top_pad=top_pad)
        rendered_cell = input.CodeCell(
            source,
            plain=plain,
            safe_box=safe_box,
            theme=theme,
            default_lexer_name=default_lexer_name,
            line_numbers=line_numbers,
            code_wrap=code_wrap,
        )

    elif cell_type == "raw":
        rendered_cell = Cell(source, plain=plain, safe_box=safe_box)

    else:
        return None

    cell_row = Row(rendered_cell, plain=plain, execution=execution)
    return cell_row


def render_output_row(
    outputs: List[NotebookNode],
    plain: bool,
    unicode: bool,
    hyperlinks: bool,
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    theme: str,
    pad: PaddingDimensions,
    images: bool,
    image_drawing: ImageDrawing,
    color: bool,
    negative_space: bool,
    relative_dir: Path,
) -> Iterator[OutputRow]:
    """Render the output row of a notebook."""
    for output in outputs:
        rendered_outputs: List[Iterator[Output]] = []
        output_type = output.output_type
        execution_count = output.get("execution_count", False)
        execution = (
            execution_indicator.Execution(execution_count, top_pad=False)
            if execution_count is not False
            else None
        )

        if output_type == "stream":
            rendered_stream = stream.render_stream(output)
            rendered_outputs.append(rendered_stream)

        elif output_type == "error":
            rendered_error = error.render_error(output)
            rendered_outputs.append(rendered_error)

        elif output_type == "execute_result" or output_type == "display_data":
            rendered_execute_result = result.render_result(
                output,
                unicode=unicode,
                execution=execution,
                hyperlinks=hyperlinks,
                nerd_font=nerd_font,
                files=files,
                hide_hyperlink_hints=hide_hyperlink_hints,
                theme=theme,
                images=images,
                image_drawing=image_drawing,
                color=color,
                negative_space=negative_space,
                relative_dir=relative_dir,
            )
            rendered_outputs.append(rendered_execute_result)

        for rendered_output in itertools.chain(*rendered_outputs):
            yield OutputRow(rendered_output, plain=plain, execution=execution, pad=pad)
