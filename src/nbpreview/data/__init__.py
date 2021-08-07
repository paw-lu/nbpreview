"""The Jupyter notebook data."""
from typing import Dict
from typing import Union

from nbformat import NotebookNode

Data = Dict[str, Union[str, NotebookNode]]
