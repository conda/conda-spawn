""" """

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Iterable

from .exceptions import ShellNotSupported
from .registry import SHELLS, detect_shell_class

if TYPE_CHECKING:
    from .shell import Shell


def spawn(
    prefix: Path,
    shell_cls: Shell | None = None,
    stack: bool = False,
    command: Iterable[str] | None = None,
) -> int:
    if shell_cls is None:
        shell_cls = detect_shell_class()
    return shell_cls(prefix, stack=stack).spawn(command=command)


def hook(
    prefix: Path,
    shell_cls: Shell | None = None,
    stack: bool = False,
) -> int:
    if shell_cls is None:
        shell_cls = detect_shell_class()
    shell_inst = shell_cls(prefix, stack=stack)
    print(shell_inst.script())
    print(shell_inst.prompt())
    return 0


def shell_specifier_to_shell(name: str | None = None) -> type[Shell]:
    if name is None:
        return detect_shell_class()

    try:
        return SHELLS[name]
    except KeyError:
        raise ShellNotSupported(name)
