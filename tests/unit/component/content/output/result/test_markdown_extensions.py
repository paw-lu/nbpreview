"""Test for nbpreview.component.content.output.result.markdown_extensions."""

import pytest
from markdown_it import token
from pytest_mock import MockerFixture

from nbpreview.component.content.output.result import markdown_extensions


@pytest.mark.no_typeguard
def test_group_tokens_not_iterator() -> None:
    """It raises a NotIteratorError when not an iterator."""
    token_groups = [
        markdown_extensions.TokenGroup(
            open_tag="open",
            close_tag="close",
        )
    ]
    grouped_tokens = markdown_extensions._group_tokens(
        [1, 2, 3],  # type: ignore[arg-type]
        token_groups=token_groups,
    )

    with pytest.raises(markdown_extensions.NotIteratorError):
        next(grouped_tokens)


def test_unknown_token_type_error(mocker: MockerFixture) -> None:
    """It raises UnknownTokenTypeError when open token is not caught."""
    mocker.patch(
        "nbpreview.component.content.output.result.markdown_extensions._group_tokens",
        return_value=iter([iter([token.Token(type="unknown", tag="", nesting=0)])]),
    )
    parsed_markdown_extensions = markdown_extensions.parse_markdown_extensions(
        markup="", unicode=True
    )
    with pytest.raises(markdown_extensions.UnknownTokenTypeError):
        next(parsed_markdown_extensions)
