from __future__ import annotations

import shutil

import pytest
from conda.activate import PosixActivator

from conda_spawn.shell import BashShell, PosixShell, ZshShell

pytest_plugins = ("conda.testing.fixtures",)


@pytest.fixture(scope="session")
def simple_env(session_tmp_env):
    with session_tmp_env() as prefix:
        yield prefix


@pytest.fixture(params=[PosixShell, BashShell, ZshShell], ids=["posix", "bash", "zsh"])
def initialized_posix_shell(request, simple_env, tmp_path, monkeypatch, conda_alias):
    shell_cls = request.param
    executable = {PosixShell: "sh", BashShell: "bash", ZshShell: "zsh"}[shell_cls]
    if shutil.which(executable) is None:
        pytest.skip(f"{executable} not installed")
    startup_file = {
        PosixShell: ".profile",
        BashShell: ".bash_profile",
        ZshShell: ".zshrc",
    }[shell_cls]
    home = tmp_path / "home"
    home.mkdir()
    (home / startup_file).write_text(
        PosixActivator().hook(False)
        + "\nPS1=''\nprintf 'CONDA_INIT_LOADED\\n'\n"
        + ("alias conda='false'\n" if conda_alias else "")
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("ZDOTDIR", str(home))
    monkeypatch.setenv("SHELL", shutil.which(executable))
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("BASH_ENV", raising=False)
    return shell_cls(simple_env)
