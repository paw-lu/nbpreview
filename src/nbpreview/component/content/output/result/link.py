"""Hyperlinks to results."""
from __future__ import annotations

import base64
import dataclasses
import json
import tempfile
from typing import Dict
from typing import Optional
from typing import Union

import httpx
import jinja2
from rich import console
from rich import emoji
from rich import style
from rich import text
from rich.emoji import Emoji
from rich.text import Text

from nbpreview.component.content.output.result import execution_indicator
from nbpreview.component.content.output.result.execution_indicator import Execution
from nbpreview.data import Data


def render_link(
    data: Data,
    unicode: bool,
    hyperlinks: bool,
    execution: Union[Execution, None],
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
) -> Union[Hyperlink, None]:
    """Render an output link."""
    link_result: Hyperlink
    if (
        "application/vnd.vega.v5+json" in data
        or "application/vnd.vegalite.v4+json" in data
    ):
        link_result = VegaLink.from_data(
            data,
            unicode=unicode,
            hyperlinks=hyperlinks,
            execution=execution,
            nerd_font=nerd_font,
            files=files,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )
        return link_result
    image_types = {
        "image/bmp",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/svg+xml",
    }
    for image_type in image_types:
        if image_type in data:
            link_result = ImageLink.from_data(
                data,
                image_type=image_type,
                unicode=unicode,
                hyperlinks=hyperlinks,
                nerd_font=nerd_font,
                files=files,
                hide_hyperlink_hints=hide_hyperlink_hints,
            )
            return link_result
    if "text/html" in data:
        link_result = HTMLLink.from_data(
            data,
            unicode=unicode,
            hyperlinks=hyperlinks,
            nerd_font=nerd_font,
            files=files,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )
        return link_result
    return None


def select_icon(
    nerd_font_icon: str,
    emoji_name: str,
    nerd_font: bool,
    unicode: bool,
) -> str:
    """Select which icon to use."""
    if nerd_font:
        icon = f"{nerd_font_icon} "
    elif unicode:
        icon = emoji.Emoji.replace(f":{emoji_name}: ")
    else:
        icon = ""
    return icon


def _write_file(content: Union[str, bytes], extension: str) -> str:
    """Write content to a temporary file.

    Args:
        content (Union[str, bytes]): The content to write.
        extension (str): The file extension of the temporary file.

    Returns:
        str: The file name.
    """
    mode = "w"
    if isinstance(content, bytes):
        mode += "b"
    with tempfile.NamedTemporaryFile(
        mode=mode, delete=False, suffix=f".{extension}"
    ) as file:
        file.write(content)
    return file.name


def _create_hyperlink_message(
    hyperlinks: bool, subject: str, hide_hyperlink_hints: bool, icon: Union[str, Emoji]
) -> str:
    """Create the text on the hyperlink."""
    if hide_hyperlink_hints:
        message = ""
    else:
        message = f"Click to view {subject}"

    if not message and not icon:
        message = subject

    return message


@dataclasses.dataclass
class Hyperlink:
    """A hyperlink to additional content."""

    content: Union[str, bytes, None]
    file_extension: str
    nerd_font: bool
    unicode: bool
    files: bool
    subject: str
    nerd_font_icon: str
    emoji_name: str
    hyperlinks: bool
    hide_hyperlink_hints: bool

    def __post_init__(self) -> None:
        """Constructor."""
        self.icon = select_icon(
            self.nerd_font_icon,
            emoji_name=self.emoji_name,
            nerd_font=self.nerd_font,
            unicode=self.unicode,
        )
        self.message = _create_hyperlink_message(
            self.hyperlinks,
            subject=self.subject,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
            icon=self.icon,
        )

    def __rich__(self) -> Union[Text, str]:
        """Render the hyperlink."""
        rendered_hyperlink: Union[str, Text]
        if self.files is True and self.content is not None:
            file_name = _write_file(self.content, extension=self.file_extension)
            if self.hyperlinks:
                link_style = console.Console().get_style("markdown.link") + style.Style(
                    link=f"file://{file_name}"
                )
                # Append blank string to prevent entire line from being underlined
                rendered_hyperlink = text.Text.assemble(
                    text.Text.assemble(self.icon, self.message, style=link_style), ""
                )
            else:
                rendered_hyperlink = text.Text(
                    f"{self.icon}{file_name}", overflow="fold"
                )
        else:
            rendered_hyperlink = f"{self.icon}{self.subject}"

        return rendered_hyperlink


@dataclasses.dataclass(init=False)
class HTMLLink(Hyperlink):
    """A link to HTML content."""

    def __init__(
        self,
        content: Union[str, bytes, None],
        nerd_font: bool,
        unicode: bool,
        files: bool,
        hyperlinks: bool,
        hide_hyperlink_hints: bool,
    ) -> None:
        """Constructor."""
        super().__init__(
            content=content,
            nerd_font_icon="",
            file_extension="html",
            unicode=unicode,
            files=files,
            subject="HTML",
            emoji_name="globe_with_meridians",
            nerd_font=nerd_font,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )

    @classmethod
    def from_data(
        cls,
        data: Data,
        nerd_font: bool,
        unicode: bool,
        files: bool,
        hyperlinks: bool,
        hide_hyperlink_hints: bool,
    ) -> HTMLLink:
        """Construct an HTML link from notebook data."""
        content = data.get("text/html", "")
        html_link = cls(
            content,
            nerd_font=nerd_font,
            unicode=unicode,
            files=files,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )
        return html_link


@dataclasses.dataclass(init=False)
class VegaLink(Hyperlink):
    """Hyperlink to Vega charts."""

    def __init__(
        self,
        content: Union[str, bytes, None],
        nerd_font: bool,
        unicode: bool,
        files: bool,
        hyperlinks: bool,
        hide_hyperlink_hints: bool,
    ) -> None:
        """Constructor."""
        super().__init__(
            content=content,
            file_extension="html",
            nerd_font=nerd_font,
            unicode=unicode,
            files=files,
            subject="Vega chart",
            nerd_font_icon="",
            emoji_name="bar_chart",
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )

    @classmethod
    def from_data(
        cls,
        data: Data,
        nerd_font: bool,
        unicode: bool,
        files: bool,
        hyperlinks: bool,
        hide_hyperlink_hints: bool,
        execution: Union[Execution, None],
    ) -> VegaLink:
        """Create a Vega link from notebook data."""
        vega_html: Optional[str]
        vega_data = data.get(
            "application/vnd.vega.v5+json",
            data.get("application/vnd.vegalite.v4+json", ""),
        )
        if isinstance(vega_data, str) and vega_data.startswith("https://" or "http://"):
            try:
                response = httpx.get(url=vega_data)
                vega_json = response.text
            except httpx.RequestError:
                vega_json = ""
        else:
            vega_json = json.dumps(vega_data)

        if files and vega_json:

            execution_count_indicator = execution_indicator.choose_execution(execution)
            env = jinja2.Environment(  # noqa: S701
                loader=jinja2.PackageLoader("nbpreview"),
                autoescape=jinja2.select_autoescape(),
            )
            vega_template = env.get_template("vega_template.jinja")
            vega_html = vega_template.render(
                execution_count_indicator=execution_count_indicator,
                subject="Vega chart",
                vega_json=vega_json,
            )
        else:
            vega_html = None

        vega_link = cls(
            vega_html,
            nerd_font=nerd_font,
            unicode=unicode,
            files=files,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )
        return vega_link


@dataclasses.dataclass(init=False)
class ImageLink(Hyperlink):
    """Hyperlink to images."""

    def __init__(
        self,
        content: Union[str, bytes, None],
        file_extension: str,
        unicode: bool,
        hyperlinks: bool,
        nerd_font: bool,
        files: bool,
        hide_hyperlink_hints: bool,
    ) -> None:
        """Constructor."""
        super().__init__(
            content,
            file_extension=file_extension,
            nerd_font=nerd_font,
            unicode=unicode,
            files=files,
            subject="Image",
            nerd_font_icon="",
            emoji_name="framed_picture",
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )

    @classmethod
    def from_data(
        cls,
        data: Dict[str, str],
        image_type: str,
        unicode: bool,
        hyperlinks: bool,
        nerd_font: bool,
        files: bool,
        hide_hyperlink_hints: bool,
    ) -> ImageLink:
        """Construct an image link from notebook data."""
        content: Union[str, bytes]
        encoded_content = data[image_type]
        if image_type == "image/svg+xml":
            file_extension = "svg"
            content = encoded_content
        else:
            *_, file_extension = image_type.split("/")
            content = base64.b64decode(encoded_content)
        image_link = cls(
            content,
            file_extension=file_extension,
            unicode=unicode,
            hyperlinks=hyperlinks,
            nerd_font=nerd_font,
            files=files,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )
        return image_link
