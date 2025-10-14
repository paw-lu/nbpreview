"""Enums representing option values."""

import enum
import itertools
from collections.abc import Iterable
from typing import Any

from pygments import styles


def get_all_available_themes(list_duplicate_alias: bool = False) -> Iterable[str]:
    """Return the available theme names."""
    theme_alias: Iterable[str] = ["light", "dark"]
    if list_duplicate_alias:
        theme_alias = itertools.chain(
            theme_alias, (f"ansi_{alias}" for alias in theme_alias)
        )
    available_themes = itertools.chain(styles.get_all_styles(), theme_alias)
    yield from available_themes


class _ThemeEnum(str, enum.Enum):
    """Enum version of available pygment themes."""


ThemeEnum = _ThemeEnum(  # type: ignore[call-overload]
    "ThemeEnum",
    {theme.upper(): theme for theme in get_all_available_themes(True)},
)


class LowerNameEnum(enum.Enum):
    """Enum base class that sets value to lowercase version of name."""

    def _generate_next_value_(  # type: ignore[override, misc]
        name: str,  # noqa: B902, N805
        start: int,
        count: int,
        last_values: list[Any],
    ) -> str:
        """Set member's values as their lowercase name."""
        return name.lower()


@enum.unique
class ColorSystemEnum(str, LowerNameEnum):
    """The color systems supported by terminals."""

    STANDARD = enum.auto()
    EIGHT_BIT = "256"
    TRUECOLOR = enum.auto()
    WINDOWS = enum.auto()
    NONE = enum.auto()
    # Add AUTO because callbacks must return values associated with types
    AUTO = enum.auto()


@enum.unique
class ImageDrawingEnum(str, LowerNameEnum):
    """Image drawing types."""

    BLOCK = enum.auto()
    CHARACTER = enum.auto()
    BRAILLE = enum.auto()
