"""Jupyter notebook output data."""
from typing import Union

from nbpreview.component.content.output.error import Error
from nbpreview.component.content.output.result import Result
from nbpreview.component.content.output.stream import Stream


Output = Union[Result, Error, Stream]
