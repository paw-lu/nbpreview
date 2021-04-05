"""nbpreview."""
import sys

if sys.version_info >= (3, 8):
    from importlib.metadata import version, PackageNotFoundError
else:  # pragma: no cover
    from importlib_metadata import version, PackageNotFoundError

try:
    __version__ = version(__name__)  # type: ignore[no-untyped-call]
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"
