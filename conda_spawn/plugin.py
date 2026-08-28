from __future__ import annotations

from inspect import signature

from conda import plugins
from conda.plugins.types import CondaSubcommand

from . import cli


@plugins.hookimpl
def conda_subcommands():
    kwargs = {
        "summary": "Activate conda environments in new shell processes.",
        "action": cli.execute,
        "configure_parser": cli.configure_parser,
    }
    if "aliases" in signature(CondaSubcommand).parameters:
        yield CondaSubcommand(
            name="spawn",
            aliases=("shell",),
            **kwargs,
        )
    else:
        for name in ("spawn", "shell"):
            yield CondaSubcommand(name=name, **kwargs)
