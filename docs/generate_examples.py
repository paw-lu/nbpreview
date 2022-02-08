"""Generate example renders for documentation."""
import dataclasses
import io
import json
import os
import pathlib
import re
import textwrap
import typing
from pathlib import Path
from typing import Any, Dict, Iterator, List, Sequence, Tuple

import nbformat
import tomli
from lxml import html
from nbformat import NotebookNode
from rich import console, style, terminal_theme, text
from rich.console import Console
from rich.terminal_theme import TerminalTheme
from rich.text import Text

from nbpreview import notebook


def create_notebook(cells: List[Dict[str, Any]]) -> NotebookNode:
    """Create valid notebook dictionary around cells."""
    # "source" is stored as a list, but processed as one string
    for cell in cells:
        cell["source"] = "".join(cell["source"])
        if (outputs := cell.get("outputs")) is not None:
            for output in outputs:
                if (data := output.get("data")) is not None:
                    for data_type, value in data.items():
                        data[data_type] = "".join(value)
                elif isinstance(output.get("text"), list):
                    output["text"] = "".join(output["text"])

    notebook_dict = {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "nbpreview",
                "language": "python",
                "name": "nbpreview",
            },
            "language_info": {
                "codemirror_mode": {"name": "ipython", "version": 3},
                "file_extension": ".py",
                "mimetype": "text/x-python",
                "name": "python",
                "nbconvert_exporter": "python",
                "pygments_lexer": "ipython3",
                "version": "3.8.6",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    notebook_node = nbformat.from_dict(notebook_dict)
    nbformat.validate(notebook_node)
    return notebook_node


def load_notebook_cells(file_path: Path) -> NotebookNode:
    """Create a notebook from a file of cells."""
    notebook_cells = json.load(file_path.open())
    notebook_node = create_notebook(notebook_cells)
    return notebook_node


def hex_to_rgb(hex: str, hsl: bool = False) -> Tuple[int, int, int]:
    """Converts a HEX code into RGB or HSL.

    Taken from https://stackoverflow.com/a/62083599/7853533

    Args:
        hex (str): Takes both short as well as long HEX codes.
        hsl (bool): Converts the given HEX code into HSL value if True.

    Returns:
        Tuple[int, int, int]: Tuple of RGB values.

    Raises:
        ValueError: If given value is not a valid HEX code.
    """
    if re.compile(r"#[a-fA-F0-9]{3}(?:[a-fA-F0-9]{3})?$").match(hex):
        div = 255 if hsl else 0
        if len(hex) <= 4:
            rgb = tuple(
                int(int(hex[i] * 2, 16) / div) if div else int(hex[i] * 2, 16)
                for i in (1, 2, 3)
            )
        else:
            rgb = tuple(
                int(int(hex[i : i + 2], 16) / div) if div else int(hex[i : i + 2], 16)
                for i in (1, 3, 5)
            )
        rgb = typing.cast(Tuple[int, int, int], rgb)
        return rgb
    raise ValueError(f"{hex} is not a valid HEX code.")


def make_example_console() -> Console:
    """Make a console for rendering examples."""
    output_file = io.StringIO()
    example_console = console.Console(
        file=output_file,
        width=79,
        record=True,
        color_system="truecolor",
        legacy_windows=False,
        force_terminal=True,
        force_interactive=True,
    )
    return example_console


def make_material_terminal_theme(light_theme: bool = False) -> TerminalTheme:
    """Create the material terminal theme."""
    if light_theme:
        background = hex_to_rgb("#fafafa")
        foreground = hex_to_rgb("#90a4ae")
        normal = [
            hex_to_rgb(hex)
            for hex in (
                "#000000",
                "#E53935",
                "#91B859",
                "#E2931D",
                "#6182B8",
                "#9C3EDA",
                "#39ADB5",
                "#FFFFFF",
            )
        ]
    else:
        background = hex_to_rgb("#263238")
        foreground = hex_to_rgb("#e9e9f4")
        normal = [
            hex_to_rgb(hex)
            for hex in (
                "#000000",
                "#f07178",
                "#C3E88D",
                "#FFCB6B",
                "#82AAFF",
                "#C792EA",
                "#89DDFF",
                "#ffffff",
            )
        ]
    material_terminal_theme = terminal_theme.TerminalTheme(
        background=background, foreground=foreground, normal=normal
    )
    return material_terminal_theme


def make_code_format(light_theme: bool = False) -> str:
    """Create code format template for rich."""
    theme = "light" if light_theme else "dark"
    code_format = textwrap.dedent(
        f"""\
            <div class="terminal-container">
              <div class="terminal {theme}-terminal">
                <div class="top">
                  <div class="buttons">
                    <span class="circle {theme}-red"></span>
                    <span class="circle {theme}-yellow"></span>
                    <span class="circle {theme}-green"></span>
                  </div>
                </div>
                <code>
                  <pre class="terminal-content">{{code}}</pre>
                </code>
              </div>
            </div>
        """
    )
    return code_format


@dataclasses.dataclass
class Example:
    """An example rendering of a notebook."""

    cells_filename: str
    notebook_kwargs: Dict[str, Any]
    example_filename: str
    args: Sequence[str]
    light_theme: bool = False
    override: Optional[Dict[str, Any]] = None
    substitute_links: Optional[Dict[str, str]] = None

    def __post_init__(self) -> None:
        """Post-initialization."""
        if (relative_dir := self.notebook_kwargs.get("relative_dir")) is not None:
            self.notebook_kwargs["relative_dir"] = pathlib.Path(
                __file__
            ).parent / pathlib.Path(relative_dir)


def get_examples() -> Iterator[Example]:
    """Yield examples to generate."""
    examples_config_path = pathlib.Path(__file__).parent / pathlib.Path("examples.toml")
    examples_config = tomli.load(examples_config_path.open("rb"))
    for example_config in examples_config["examples"]:
        example = Example(**example_config)
        yield example


def make_example_command(args: Sequence[str]) -> Text:
    """Create example command."""
    prompt = text.Text("% ", style=style.Style(color="green"))
    command = text.Text(" ".join(args))
    example_command = text.Text.assemble(prompt, command)
    return example_command


def substitute_example_links(
    example_path: Path, substitute_links: Dict[str, str]
) -> None:
    """Substitute links in example."""
    example_text = example_path.read_text()
    example_html_element = html.fromstring(example_text)
    example_links = example_html_element.xpath("//a")
    for link_position, substitute_link in substitute_links.items():
        example_links[int(link_position)].set("href", substitute_link)
    substituted_links_example = html.tostring(example_html_element, encoding="unicode")
    example_path.write_text(substituted_links_example)


def generate_examples() -> None:
    """Generate the examples for the documentation."""
    example_notebook_cell_directory = pathlib.Path(__file__).parent / pathlib.Path(
        "example_notebook_cells"
    )
    example_console = make_example_console()
    for example in get_examples():
        example_notebook_cell_path = example_notebook_cell_directory / pathlib.Path(
            example.cells_filename
        ).with_suffix(".json")
        notebook_node = load_notebook_cells(example_notebook_cell_path)

        example_command = make_example_command(example.args)
        example_console.print(example_command)
        nbpreview_notebook = notebook.Notebook(notebook_node, **example.notebook_kwargs)
        example_console.print(nbpreview_notebook)

        example_path = (
            pathlib.Path(__file__).parent
            / pathlib.Path("_static", "examples")
            / pathlib.Path(example.example_filename).with_suffix(".html")
        )
        material_terminal_theme = make_material_terminal_theme(example.light_theme)
        code_format = make_code_format(example.light_theme)
        example_console.save_html(
            os.fsdecode(example_path),
            theme=material_terminal_theme,
            inline_styles=True,
            code_format=code_format,
        )
        if (substitute_links := example.substitute_links) is not None:
            substitute_example_links(example_path, substitute_links=substitute_links)


if __name__ == "__main__":
    generate_examples()
