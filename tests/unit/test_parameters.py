"""Test cases for the parameters module."""
import itertools

from pygments import styles

from nbpreview import parameters


def test_get_all_available_themes() -> None:
    """It lists all available pygment themes."""
    output = parameters._get_all_available_themes()
    expected_output = itertools.chain(styles.get_all_styles(), ("light", "dark"))
    assert list(output) == list(expected_output)
