"""Test for nbpreview.component.content.output.result.table."""
import pytest
from markdown_it import token

from nbpreview.component.content.output.result import table


def test_group_tokens_equal_tags() -> None:
    """It raises a NotUniqueError when tags are equal."""
    with pytest.raises(table.NotUniqueError):
        grouped_tokens = table._group_tokens(  # pragma: no branch
            (token.Token("", tag="", nesting=0) for _ in range(2)),
            open_tag="hey",
            close_tag="hey",
        )
        next(grouped_tokens)


@pytest.mark.no_typeguard
def test_group_tokens_not_iterator() -> None:
    """It raises a NotIteratorError when not an iterator."""
    with pytest.raises(table.NotIteratorError):
        grouped_tokens = table._group_tokens(
            [1, 2, 3],  # type: ignore[arg-type]
            open_tag="open",
            close_tag="close",
        )
        next(grouped_tokens)
