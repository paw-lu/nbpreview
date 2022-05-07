"""Hyperlinks to results."""
import base64
import binascii
import dataclasses
import json
import tempfile
from typing import Optional, Union

import httpx
import jinja2
from jinja2 import select_autoescape
from rich import console, emoji, style, text
from rich.emoji import Emoji
from rich.text import Text

from nbpreview.component.content.output.result import execution_indicator
from nbpreview.component.content.output.result.execution_indicator import Execution
from nbpreview.data import Data


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
    subject: str, hide_hyperlink_hints: bool, icon: Union[str, Emoji]
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
class Link:
    """A hyperlink."""

    path: Union[str, None]
    nerd_font: bool
    unicode: bool
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
            subject=self.subject,
            hide_hyperlink_hints=self.hide_hyperlink_hints,
            icon=self.icon,
        )

    def __rich__(self) -> Text:
        """Render the hyperlink."""
        if self.hyperlinks and self.path:
            link_style = console.Console().get_style("markdown.link") + style.Style(
                link=self.path
            )
            # Append blank string to prevent entire line from being underlined
            rendered_hyperlink = text.Text.assemble(
                text.Text.assemble(self.icon, self.message, style=link_style), ""
            )
        elif self.path is not None:
            rendered_hyperlink = text.Text(f"{self.icon}{self.path}", overflow="fold")
        else:
            rendered_hyperlink = text.Text(f"{self.icon}{self.subject}")
        return rendered_hyperlink


@dataclasses.dataclass(init=False)
class FileLink(Link):
    """A hyperlink to a generated temporary file."""

    def __init__(
        self,
        content: Union[str, bytes, None],
        file_extension: str,
        files: bool,
        hyperlinks: bool,
        hide_hyperlink_hints: bool,
        nerd_font: bool,
        unicode: bool,
        subject: str,
        emoji_name: str = "page_facing_up",
        nerd_font_icon: str = "",
    ) -> None:
        """Constructor."""
        path: Union[str, None]
        if files is True and content is not None:
            path = f"file://{_write_file(content, extension=file_extension)}"
        else:
            path = None
        self.files = files
        self.content = content
        self.file_extension = file_extension
        super().__init__(
            path=path,
            nerd_font=nerd_font,
            unicode=unicode,
            subject=subject,
            nerd_font_icon=nerd_font_icon,
            emoji_name=emoji_name,
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )


def render_link(
    data: Data,
    unicode: bool,
    hyperlinks: bool,
    execution: Union[Execution, None],
    nerd_font: bool,
    files: bool,
    hide_hyperlink_hints: bool,
) -> Union[FileLink, None]:
    """Render an output link."""
    link_result: FileLink
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


@dataclasses.dataclass(init=False)
class HTMLLink(FileLink):
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
    ) -> "HTMLLink":
        """Construct an HTML link from notebook data."""
        content = (
            text_html_data
            if isinstance((text_html_data := data.get("text/html")), str)
            else ""
        )
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
class VegaLink(FileLink):
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
    ) -> "VegaLink":
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
            env = jinja2.Environment(
                loader=jinja2.PackageLoader("nbpreview"),
                autoescape=select_autoescape(),
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
class ImageLink(FileLink):
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
        subject: str = "Image",
    ) -> None:
        """Constructor."""
        super().__init__(
            content,
            file_extension=file_extension,
            nerd_font=nerd_font,
            unicode=unicode,
            files=files,
            subject=subject,
            nerd_font_icon="",
            emoji_name="framed_picture",
            hyperlinks=hyperlinks,
            hide_hyperlink_hints=hide_hyperlink_hints,
        )

    @classmethod
    def from_data(
        cls,
        data: Data,
        image_type: str,
        unicode: bool,
        hyperlinks: bool,
        nerd_font: bool,
        files: bool,
        hide_hyperlink_hints: bool,
    ) -> "ImageLink":
        """Construct an image link from notebook data."""
        content: Union[str, bytes, None]
        encoded_content = data[image_type]
        if image_type == "image/svg+xml":
            file_extension = "svg"
            content = encoded_content if isinstance(encoded_content, str) else None
        elif isinstance(encoded_content, str):
            *_, file_extension = image_type.split("/")
            try:
                content = base64.b64decode(encoded_content)
            except binascii.Error:
                content = None
        else:
            file_extension = "txt"
            content = None

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
