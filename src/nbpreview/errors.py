"""nbpreview errors."""


class NBPreviewError(Exception):
    """Base nbpreview error."""


class InvalidNotebookError(NBPreviewError):
    """Error when input notebook in invalid."""
