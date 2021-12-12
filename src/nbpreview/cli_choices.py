"""Define custom enum for cli choices."""
import enum
from typing import Any, List


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
