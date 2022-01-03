"""Enums representing option values."""
import enum
from typing import Any, List, Literal


class LowerNameEnum(enum.Enum):
    """Enum base class that sets value to lowercase version of name."""

    def _generate_next_value_(  # type: ignore[override,misc]
        name: str,  # noqa: B902,N805
        start: int,
        count: int,
        last_values: List[Any],
    ) -> str:
        """Set member's values as their lowercase name."""
        return name.lower()


@enum.unique
class ColorSystemEnum(str, LowerNameEnum):
    """The color systems supported by terminals."""

    STANDARD: Literal["standard"] = enum.auto()  # type: ignore[assignment]
    EIGHT_BIT: Literal["256"] = "256"
    TRUECOLOR: Literal["truecolor"] = enum.auto()  # type: ignore[assignment]
    WINDOWS: Literal["windows"] = enum.auto()  # type: ignore[assignment]
    NONE: Literal["none"] = enum.auto()  # type: ignore[assignment]
    # Add AUTO because callbacks must return values associated with types
    AUTO: Literal["auto"] = enum.auto()  # type: ignore[assignment]


@enum.unique
class ImageDrawingEnum(str, LowerNameEnum):
    """Image drawing types."""

    BLOCK = enum.auto()
    CHARACTER = enum.auto()
    BRAILLE = enum.auto()
