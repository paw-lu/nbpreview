"""Tests for src.nbpreview.component.row."""
import pytest

from nbpreview.component import markdown


@pytest.mark.parametrize(
    "string, expected_output", [("foobar", "bar"), ("barbar", "barbar")]
)
def test_remove_prefix(string: str, expected_output: str) -> None:
    """It removes the prefix from the string if it exists."""
    output = markdown._remove_prefix(string, "foo")
    assert output == expected_output
