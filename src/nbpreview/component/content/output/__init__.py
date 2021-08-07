"""Jupyter notebook output data."""
from typing import Union

from nbpreview.component.content.output.error import Error
from nbpreview.component.content.output.result.display_data import DisplayData
from nbpreview.component.content.output.result.link import Hyperlink
from nbpreview.component.content.output.stream import Stream


Output = Union[DisplayData, Error, Hyperlink, Stream]
