"""Execution results from Jupyter notebooks."""
import sys
from typing import Dict
from typing import Iterator
from typing import Union

from nbformat import NotebookNode

from nbpreview.component.content.output.result import display_data
from nbpreview.component.content.output.result import link
from nbpreview.component.content.output.result.display_data import DisplayData
from nbpreview.component.content.output.result.drawing import Drawing
from nbpreview.component.content.output.result.execution_indicator import Execution
from nbpreview.component.content.output.result.link import Hyperlink

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

Result = Union[Hyperlink, DisplayData, Drawing]


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
    image_drawing: Literal["block", None],
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
    )
    for result in (link_result, main_result):
        if result is not None:
            yield result
