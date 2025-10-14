"""Render execution results from Jupyter Notebooks."""
from collections.abc import Iterator
from pathlib import Path
from typing import Union

from nbformat import NotebookNode

from nbpreview.component.content.output.result import display_data, link
from nbpreview.component.content.output.result.display_data import DisplayData
from nbpreview.component.content.output.result.drawing import Drawing, ImageDrawing
from nbpreview.component.content.output.result.execution_indicator import Execution
from nbpreview.component.content.output.result.link import FileLink

Result = Union[FileLink, DisplayData, Drawing]


def render_result(
    output: NotebookNode,
    unicode: bool,
    execution: Execution | None,
    hyperlinks: bool,
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    theme: str,
    images: bool,
    image_drawing: ImageDrawing,
    color: bool,
    negative_space: bool,
    relative_dir: Path,
) -> Iterator[Result]:
    """Render executed result outputs."""
    data = output.get("data", {})
    link_result = link.render_link(
        data,
        unicode=unicode,
        hyperlinks=hyperlinks,
        execution=execution,
        nerd_font=nerd_font,
        files=files,
        hide_hyperlink_hints=hide_hyperlink_hints,
    )
    main_result = display_data.render_display_data(
        data,
        unicode=unicode,
        nerd_font=nerd_font,
        theme=theme,
        images=images,
        image_drawing=image_drawing,
        color=color,
        negative_space=negative_space,
        hyperlinks=hyperlinks,
        files=files,
        hide_hyperlink_hints=hide_hyperlink_hints,
        relative_dir=relative_dir,
    )
    for result in (link_result, main_result):
        if result is not None:
            yield result
