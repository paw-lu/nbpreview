"""Test cases for the option_values module."""
import itertools

from pygments import styles

from nbpreview import option_values


def test_get_all_available_themes() -> None:
    """It lists all available pygment themes."""
    output = option_values.get_all_available_themes()
    expected_output = itertools.chain(styles.get_all_styles(), ("light", "dark"))
    assert list(output) == list(expected_output)
