import sys
from types import SimpleNamespace

import pytest
from conda import CondaError

from conda_spawn import plugin
from conda_spawn.constants import CONDA_SPAWN_ENV_VAR


@pytest.mark.parametrize("command", ("spawn", "shell"))
def test_cli(monkeypatch, conda_cli, command):
    monkeypatch.setattr(sys, "argv", ["conda", *sys.argv[1:]])
    out, err, _ = conda_cli(command, "-h", raises=SystemExit)
    assert not err
    assert "conda spawn" in out


def test_alias_registration_with_aliases_parameter(monkeypatch):
    def conda_subcommand(*, name, summary, action, configure_parser=None, aliases=()):
        return SimpleNamespace(
            name=name,
            summary=summary,
            action=action,
            configure_parser=configure_parser,
            aliases=aliases,
        )

    monkeypatch.setattr(plugin, "CondaSubcommand", conda_subcommand)

    (command,) = plugin.conda_subcommands()

    assert command.name == "spawn"
    assert command.aliases == ("shell",)


def test_alias_registration_without_aliases_parameter(monkeypatch):
    def conda_subcommand(*, name, summary, action, configure_parser=None):
        return SimpleNamespace(
            name=name,
            summary=summary,
            action=action,
            configure_parser=configure_parser,
        )

    monkeypatch.setattr(plugin, "CondaSubcommand", conda_subcommand)

    commands = tuple(plugin.conda_subcommands())

    assert tuple(command.name for command in commands) == ("spawn", "shell")
    assert commands[0].action is commands[1].action
    assert commands[0].configure_parser is commands[1].configure_parser


def test_shell_alias(monkeypatch, conda_cli):
    monkeypatch.delenv(CONDA_SPAWN_ENV_VAR, raising=False)
    args = (sys.prefix, "--hook", "--shell", "posix")
    assert conda_cli("shell", *args) == conda_cli("spawn", *args)


def test_nesting_disallowed(monkeypatch, conda_cli):
    monkeypatch.setenv(CONDA_SPAWN_ENV_VAR, "1")
    conda_cli("spawn", sys.prefix, "--hook", raises=CondaError)


def test_nesting_replace(monkeypatch, conda_cli):
    monkeypatch.setenv(CONDA_SPAWN_ENV_VAR, "1")
    out, err, rc = conda_cli("spawn", sys.prefix, "--hook", "--replace")
    assert sys.prefix in out
    assert not err
    assert not rc


def test_nesting_stack(monkeypatch, conda_cli):
    monkeypatch.setenv(CONDA_SPAWN_ENV_VAR, "1")
    out, err, rc = conda_cli("spawn", sys.prefix, "--hook", "--stack")
    assert sys.prefix in out
    assert not err
    assert not rc
