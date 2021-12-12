"""Utilities for processing test outputs."""
import pathlib
import re
import subprocess
from typing import Tuple


def split_string(
    string: str, sub_length: int = 40, copy: bool = False
) -> Tuple[str, ...]:
    """Split a string into subsections less than or equal to new length.

    Args:
        string (str): The long string to split up.
        sub_length (int): The maximum length of the subsections.
            Defaults to 56.
        copy (bool): Copy output to clipboard.

    Returns:
        Tuple[str]: The string split into sections.
    """
    string_length = len(string)
    split = tuple(
        string[begin : begin + sub_length]
        for begin in range(0, string_length, sub_length)
    )
    if copy is True:
        string = str(split)
        copy_string(string)
    return split


def copy_string(string: str) -> None:
    """Copies the string to clipboard.

    Uses pbcopy, so for now only works with macOS.
    """
    subprocess.run("/usr/bin/pbcopy", text=True, input=string)  # noqa: S603


def write_output(string: str, test_name: str, replace_links: bool = True) -> None:
    """Write the output to the expected output's file."""
    if replace_links:
        tempfile_link_pattern = re.compile(
            r"(?P<prefix>file://)"
            r"(?P<core_tempfile_link>[\w\s/\\]*)"
            r"(?P<suffix>\d+\.\w+)"
        )
        string = tempfile_link_pattern.sub(
            lambda match: f"{match.group('prefix')}"
            "{{ tempfile_path }}"
            f"{match.group('suffix')}",
            string=string,
        )
    output_directory = pathlib.Path(__file__).parent.parent / pathlib.Path(
        "unit", "expected_outputs"
    )
    expected_output_file = output_directory / pathlib.Path(test_name).with_suffix(
        ".txt"
    )
    expected_output_file.write_text(string)
