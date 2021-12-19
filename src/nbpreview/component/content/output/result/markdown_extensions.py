"""Supplement markdown renderer."""
import dataclasses
import itertools
from typing import Iterable, Iterator, Optional

import markdown_it
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from rich import markdown
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.table import Table

from nbpreview import errors
from nbpreview.component.content.output.result import latex, table


class NotIteratorError(ValueError, errors.NBPreviewError):
    """Error when not an iterator."""

    def __init__(self, arg_name: str) -> None:
        """Constructor."""
        super().__init__(f"{arg_name} not an iterator")


class UnknownTokenTypeError(ValueError, errors.NBPreviewError):
    """Error raised when the token type is unknown."""

    def __init__(self, token_type: str) -> None:
        """Constructor."""
        super().__init__(f"Unknown token type {token_type=}")


@dataclasses.dataclass
class MarkdownExtensionSection:
    """A section of rendered markdown."""

    renderable: RenderableType
    start_line: int
    end_line: int


@dataclasses.dataclass
class TokenGroup:
    """A pair of token tags that contain a Markdown group."""

    open_tag: str
    close_tag: Optional[str] = None

    def __post_init__(self) -> None:
        """Constructor."""
        self.close_tag = self.open_tag if self.close_tag is None else self.close_tag


def _group_tokens(
    iterator: Iterator[Token],
    token_groups: Iterable[TokenGroup],
) -> Iterator[Iterator[Token]]:
    """Group tokens bounded by tags into separate iterators."""
    if not isinstance(iterator, Iterator):
        raise NotIteratorError("iterator")
    open_close_pairs = {
        token_group.open_tag: token_group.close_tag for token_group in token_groups
    }
    for token in iterator:
        if (token_type := token.type) in open_close_pairs:
            close_tag = open_close_pairs[token_type]
            if token_type == close_tag:
                yield iter([token])
            else:
                yield itertools.chain(
                    (token,),
                    itertools.takewhile(
                        lambda token_: token_.type != close_tag, iterator
                    ),
                )


def _render_markdown_table(parsed_group: Iterator[Token], unicode: bool) -> Table:
    """Render a parsed Markdown table."""
    is_header = {"th_open": True, "td_open": False}
    rich_table = table.create_table(unicode)
    for parsed_row in _group_tokens(
        parsed_group,
        token_groups=[TokenGroup(open_tag="tr_open", close_tag="tr_close")],
    ):
        row_text = []
        header = False
        end_section = True
        for token in parsed_row:
            if token.type in is_header:
                header = is_header[token.type]
                if token.type == "td_open":
                    end_section = False

            elif token.type == "inline":
                row_text.append(
                    _parse_table_element(
                        token.children[0].content if token.children else token.content,
                        header=header,
                    )
                )
            else:
                header = False

        rich_table.add_row(*row_text, end_section=end_section)

    if table.is_only_header(rich_table):
        rich_table.add_row("")
    return rich_table


def _parse_table_element(element: str, header: bool) -> Markdown:
    """Parse the text in a table element as Markdown."""
    if header and element.strip():
        element = f"**{element}**"
    table_element = markdown.Markdown(element)
    return table_element


def parse_markdown_extensions(
    markup: str, unicode: bool
) -> Iterator[MarkdownExtensionSection]:
    """Return parsed tables from markdown."""
    markdown_parser = (
        markdown_it.MarkdownIt("zero")
        .enable("table")
        .use(
            dollarmath_plugin,
            allow_labels=False,
            allow_space=True,
            allow_digits=False,
            double_inline=True,
        )
    )
    parsed_markup = markdown_parser.parse(markup)
    iter_parsed_markup = iter(parsed_markup)
    token_groups = [
        TokenGroup(open_tag="table_open", close_tag="table_close"),
    ]
    if unicode:
        token_groups.append(TokenGroup(open_tag="math_block"))
    for parsed_group in _group_tokens(iter_parsed_markup, token_groups=token_groups):
        open_token = next(parsed_group)
        open_token_type = open_token.type
        start_line, end_line = open_token.map or (0, 0)
        if open_token_type == "math_block":  # noqa: S105
            rendered_math = latex.render_latex(open_token.content)
            yield MarkdownExtensionSection(
                rendered_math, start_line=start_line, end_line=end_line
            )
        elif open_token_type == "table_open":  # noqa: S105
            rendered_table = _render_markdown_table(parsed_group, unicode=unicode)
            yield MarkdownExtensionSection(
                rendered_table, start_line=start_line, end_line=end_line
            )
        else:
            raise UnknownTokenTypeError(open_token_type)
