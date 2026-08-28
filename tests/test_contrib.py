import os
import shutil
import sys
from pathlib import Path

import pexpect
import pytest

from conda_spawn.contrib import (
    CshShell,
    FishShell,
    TcshShell,
    XonshShell,
)
from conda_spawn.shell import UnixShell


@pytest.fixture
def fish_shell(simple_env):
    return FishShell(simple_env)


@pytest.fixture
def xonsh_shell(simple_env):
    return XonshShell(simple_env)


def _read_via_exit(proc, shell_name: str = "exit") -> str:
    """Send `exit` and collect all output until EOF.

    csh/tcsh/xonsh do not exit on a single `sendeof()`, so we send an explicit
    `exit` command and then wait for the process to terminate.
    """
    proc.sendline("exit")
    try:
        proc.expect(pexpect.EOF, timeout=15)
    except pexpect.TIMEOUT:
        proc.terminate(force=True)
    return (proc.before or b"").decode(errors="replace")


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell(simple_env):
    shell = FishShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    proc.sendeof()
    out = proc.read().decode(errors="replace")
    assert "_CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell_uses_init_injection(simple_env, tmp_path, monkeypatch):
    config_home = tmp_path / "xdg-config"
    fish_config = config_home / "fish"
    fish_config.mkdir(parents=True)
    (fish_config / "config.fish").write_text(
        "set -gx SPAWN_TEST_FISH_CONFIG_LOADED 1\n"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    shell = FishShell(simple_env)
    original_write_init_injection = shell.write_init_injection
    activation_paths = []

    def write_init_injection(script_path):
        activation_paths.append(Path(script_path))
        result = original_write_init_injection(script_path)
        assert result is not None
        argv, env = result
        return argv, {**env, "SPAWN_TEST_INIT_INJECTION": "1"}

    monkeypatch.setattr(shell, "write_init_injection", write_init_injection)
    proc = shell.spawn_tty()
    assert len(activation_paths) == 1
    assert not activation_paths[0].exists()
    proc.sendline(
        'printf "CONDA_PREFIX=%s\\n_CONDA_SPAWN=%s\\n'
        "SPAWN_TEST_INIT_INJECTION=%s\\n"
        'SPAWN_TEST_FISH_CONFIG_LOADED=%s\\n" "$CONDA_PREFIX" '
        '"$_CONDA_SPAWN" "$SPAWN_TEST_INIT_INJECTION" '
        '"$SPAWN_TEST_FISH_CONFIG_LOADED"'
    )
    proc.sendline("exit")
    proc.expect(pexpect.EOF, timeout=15)
    out = (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in out
    assert "_CONDA_SPAWN=1" in out
    assert "SPAWN_TEST_INIT_INJECTION=1" in out
    assert "SPAWN_TEST_FISH_CONFIG_LOADED=1" in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell_ready_marker_synchronization(simple_env):
    """Regression test: FishShell must use the ready-marker sync approach."""
    shell = FishShell(simple_env)
    proc = shell.spawn_tty()
    try:
        marker = FishShell.READY_MARKER
        assert marker, "FishShell must define a non-empty READY_MARKER"
        assert proc.after.startswith(marker.encode())
        assert proc.after != marker.encode()
    finally:
        proc.sendeof()
        proc.read()


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("csh") is None, reason="csh not installed")
def test_csh_shell(simple_env):
    shell = CshShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    out = _read_via_exit(proc)
    assert "_CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("tcsh") is None, reason="tcsh not installed")
def test_tcsh_shell(simple_env):
    shell = TcshShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    out = _read_via_exit(proc)
    assert "_CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("xonsh") is None, reason="xonsh not installed")
def test_xonsh_shell(simple_env, tmp_path, monkeypatch):
    shell = XonshShell(simple_env)
    rc_dir = tmp_path / "xonshrc.d"
    rc_dir.mkdir()
    (rc_dir / "01-prompt.xsh").write_text(
        '$PROMPT = "RC_D_LOADED " + ${...}.get("PROMPT", "")\n'
        "@events.on_post_rc\n"
        "def _conda_spawn_test_post_rc(**kwargs):\n"
        '    print("POST_RC_FILES=" + "|".join(str(path) for path in '
        "__xonsh__.rc_files), flush=True)\n"
        '    print("POST_RC_COMPLETE", flush=True)\n'
        "@events.on_pre_cmdloop\n"
        "def _conda_spawn_test_pre_cmdloop(**kwargs):\n"
        '    print("PRE_CMDLOOP_COMPLETE", flush=True)\n'
    )
    monkeypatch.setenv("XONSHRC", "")
    monkeypatch.setenv("XONSHRC_DIR", str(rc_dir))
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(
        shutil,
        "get_terminal_size",
        lambda fallback=(80, 24): os.terminal_size((500, 30)),
    )
    activation_paths = []
    original_write_init_injection = shell.write_init_injection

    def write_init_injection(script_path):
        activation_paths.append(Path(script_path))
        return original_write_init_injection(script_path)

    monkeypatch.setattr(shell, "write_init_injection", write_init_injection)
    proc = shell.spawn_tty()
    try:
        startup_bytes = (proc.before or b"") + (proc.after or b"")
        startup = startup_bytes.decode(errors="replace")
        assert "POST_RC_COMPLETE" in startup
        assert "PRE_CMDLOOP_COMPLETE" in startup
        assert UnixShell.READY_MARKER in startup

        assert startup.index("POST_RC_COMPLETE") < startup.index("PRE_CMDLOOP_COMPLETE")
        assert startup.index("PRE_CMDLOOP_COMPLETE") < startup.index(
            UnixShell.READY_MARKER
        )
        rc_files_output = next(
            line for line in startup.splitlines() if line.startswith("POST_RC_FILES=")
        )
        assert str(rc_dir / "01-prompt.xsh") in rc_files_output
        assert len(activation_paths) == 1
        assert str(activation_paths[0]) not in rc_files_output
        assert not activation_paths[0].exists()

        for _ in range(startup_bytes.count(b"\x1b[6n")):
            proc.send(b"\x1b[1;1R")

        def expect_with_cursor_response(target):
            chunks = []
            while True:
                match = proc.expect_exact([b"\x1b[6n", target], timeout=15)
                chunks.extend((proc.before or b"", proc.after or b""))
                if match == 1:
                    return b"".join(chunks)
                proc.send(b"\x1b[1;1R")

        prompt_output = expect_with_cursor_response(b"RC_D_LOADED").decode(
            errors="replace"
        )
        assert str(simple_env) in prompt_output

        proc.sendline('print("SECOND_" + "PROMPT_REACHED", flush=True)')
        expect_with_cursor_response(b"SECOND_PROMPT_REACHED")
    finally:
        if proc.isalive():
            proc.sendline("exit")
            proc.close(force=True)

    assert startup.count(UnixShell.READY_MARKER) == 1


@pytest.mark.parametrize(
    "cls, expected",
    [
        (FishShell, "fish"),
        (CshShell, "csh"),
        (TcshShell, "tcsh"),
        (XonshShell, "xonsh"),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else x,
)
def test_shell_executable(cls, expected, simple_env):
    assert cls(simple_env).executable() == expected


def test_fish_shell_prompt_preserves_existing_prompt(fish_shell):
    prompt = fish_shell.prompt()
    # Copies any existing fish_prompt to a namespaced backup ...
    assert "__conda_spawn_orig_fish_prompt" in prompt
    # ... and prepends CONDA_PROMPT_MODIFIER to the new fish_prompt.
    assert '"$CONDA_PROMPT_MODIFIER"' in prompt


def test_fish_shell_source_command_and_suffix(fish_shell):
    assert fish_shell.source_command("/tmp/x.fish") == 'source "/tmp/x.fish"'
    assert fish_shell.script_suffix == ".fish"


def test_fish_supports_init_injection():
    assert FishShell.supports_init_injection is True


def test_fish_write_init_injection(fish_shell):
    result = fish_shell.write_init_injection("/tmp/script.fish")
    assert result is not None
    argv, env = result
    assert argv == ("-C", "source /tmp/script.fish")
    assert env == {}


@pytest.mark.parametrize("cls", [CshShell, TcshShell], ids=lambda c: c.__name__)
def test_csh_family_prompt_guards_undefined_prompt(cls, simple_env):
    """Regression test: csh raises 'Undefined variable' without this guard."""
    prompt = cls(simple_env).prompt()
    assert 'if (! $?prompt) set prompt = ""' in prompt
    assert "set prompt=" in prompt
    # The guard must come before the assignment, otherwise the expansion
    # in ${prompt} happens before $prompt has been initialised.
    assert prompt.index("if (! $?prompt)") < prompt.index("set prompt=")


@pytest.mark.parametrize("cls", [CshShell, TcshShell], ids=lambda c: c.__name__)
def test_csh_family_ready_marker_uses_echo(cls, simple_env):
    """csh has no printf builtin; echo -n is the portable alternative."""
    assert cls(simple_env).ready_marker_command().startswith("echo -n ")


def test_xonsh_shell_rewrites_del_var(xonsh_shell, monkeypatch):
    """Regression test: bare `del $VAR` raises KeyError on fresh shells.

    The XonshShell.script() override must replace every such line with the
    safe `${...}.pop("VAR", None)` form.
    """
    monkeypatch.setattr(UnixShell, "script", lambda self: "del $CONDA_EXE\n")

    script = xonsh_shell.script()
    assert "del $" not in script
    assert '${...}.pop("CONDA_EXE", None)' in script


def test_xonsh_shell_script_suffix_is_xsh(xonsh_shell):
    """The activator reports .sh but xonsh needs .xsh for correct parsing."""
    assert xonsh_shell.script_suffix == ".xsh"


def test_xonsh_shell_post_activation_uses_subproc_form(xonsh_shell):
    """Bare `stty echo` is ambiguous in xonsh; `$[...]` forces subproc."""
    assert xonsh_shell.post_activation_command() == "$[stty echo]"


def test_xonsh_shell_ready_marker_uses_print(xonsh_shell):
    cmd = xonsh_shell.ready_marker_command()
    assert cmd.startswith("print(")
    assert "flush=True" in cmd
    assert "end=" in cmd


@pytest.mark.parametrize(
    "cls, expected_markers",
    [
        (CshShell, ("set prompt=",)),
        (TcshShell, ("set prompt=",)),
        (FishShell, ()),
        (XonshShell, ()),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else repr(x),
)
def test_prompt_strip_markers(cls, expected_markers):
    """Each subclass must declare the activator lines it wants stripped."""
    assert cls.prompt_strip_markers == expected_markers


def test_xonsh_supports_init_injection():
    assert XonshShell.supports_init_injection is True


def test_xonsh_write_init_injection(xonsh_shell):
    result = xonsh_shell.write_init_injection("/tmp/script.xsh")
    assert result is not None
    argv, env = result
    assert argv == ("--rc", "/tmp/script.xsh")
    assert env == {}


def test_xonsh_user_rc_loader(xonsh_shell):
    loader = xonsh_shell._user_rc_loader()
    assert "xonshrc_context" in loader
    assert "XONSHRC" in loader
    assert "XONSHRC_DIR" in loader
    assert "__xonsh__.rc_files = _conda_spawn_user_rc_files" in loader


def test_xonsh_spawn_script_defers_activation(xonsh_shell):
    script = xonsh_shell.spawn_script()
    assert "xonshrc_context" in script
    assert "events.on_pre_cmdloop.fire = _conda_spawn_fire_pre_cmdloop" in script
    assert UnixShell.READY_MARKER in script
    assert script.index("xonshrc_context") < script.index(
        "_conda_spawn_pre_cmdloop_fire(**kwargs)"
    )
    assert script.index("_conda_spawn_pre_cmdloop_fire(**kwargs)") < script.index(
        UnixShell.READY_MARKER
    )
