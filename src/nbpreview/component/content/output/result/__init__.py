"""Execution results from Jupyter notebooks."""
from typing import Dict, Iterator, Literal, Union

from nbformat import NotebookNode

from nbpreview.component.content.output.result import display_data, link
from nbpreview.component.content.output.result.display_data import DisplayData
from nbpreview.component.content.output.result.drawing import Drawing
from nbpreview.component.content.output.result.execution_indicator import Execution
from nbpreview.component.content.output.result.link import FileLink

Result = Union[FileLink, DisplayData, Drawing]


def render_result(
    output: NotebookNode,
    plain: bool,
    unicode: bool,
    execution: Union[Execution, None],
    hyperlinks: bool,
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
    theme: str,
    images: bool,
    image_drawing: Literal["block", "character", "braille"],
    color: bool,
    negative_space: bool,
) -> Iterator[Result]:
    """Render executed result outputs."""
    data: Dict[str, Union[str, NotebookNode]] = output.get("data", {})
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
        plain=plain,
        nerd_font=nerd_font,
        theme=theme,
        images=images,
        image_drawing=image_drawing,
        color=color,
        negative_space=negative_space,
    )
    for result in (link_result, main_result):
        if result is not None:
            yield result
