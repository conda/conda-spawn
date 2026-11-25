"""Exceptions raised by conda-spawn."""

from conda.base.constants import COMPATIBLE_SHELLS
from conda.common.io import dashlist
from conda.exceptions import CondaError


class ShellNotSupported(CondaError):
    def __init__(self, name: str):
        message = (
            f"The specified shell {name} is not supported."
            "Try one of:\n"
            f"{dashlist(COMPATIBLE_SHELLS)}"
        )
        super().__init__(message)
