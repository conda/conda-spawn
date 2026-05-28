import shutil
import sys
import time
from tempfile import NamedTemporaryFile

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
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell_uses_init_injection(simple_env, tmp_path, monkeypatch):
    config_home = tmp_path / "xdg-config"
    fish_config = config_home / "fish"
    fish_config.mkdir(parents=True)
    (fish_config / "config.fish").write_text(
        "set -gx CONDA_SPAWN_FISH_CONFIG_LOADED 1\n"
    )
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))

    shell = FishShell(simple_env)
    original_write_init_injection = shell.write_init_injection

    def write_init_injection(script_path):
        result = original_write_init_injection(script_path)
        assert result is not None
        argv, env = result
        return argv, {**env, "CONDA_SPAWN_INIT_INJECTION": "1"}

    monkeypatch.setattr(shell, "write_init_injection", write_init_injection)
    proc = shell.spawn_tty()
    proc.sendline(
        'printf "CONDA_PREFIX=%s\\nCONDA_SPAWN=%s\\n'
        "CONDA_SPAWN_INIT_INJECTION=%s\\n"
        'CONDA_SPAWN_FISH_CONFIG_LOADED=%s\\n" "$CONDA_PREFIX" '
        '"$CONDA_SPAWN" "$CONDA_SPAWN_INIT_INJECTION" '
        '"$CONDA_SPAWN_FISH_CONFIG_LOADED"'
    )
    proc.sendline("exit")
    proc.expect(pexpect.EOF, timeout=15)
    out = (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in out
    assert "CONDA_SPAWN=1" in out
    assert "CONDA_SPAWN_INIT_INJECTION=1" in out
    assert "CONDA_SPAWN_FISH_CONFIG_LOADED=1" in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_shell_ready_marker_synchronization(simple_env):
    """Regression test: FishShell must use the ready-marker sync approach."""
    shell = FishShell(simple_env)
    proc = shell.spawn_tty()
    try:
        marker = FishShell.READY_MARKER
        assert marker, "FishShell must define a non-empty READY_MARKER"
        assert proc.after == marker.encode()
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
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("tcsh") is None, reason="tcsh not installed")
def test_tcsh_shell(simple_env):
    shell = TcshShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    out = _read_via_exit(proc)
    assert "CONDA_SPAWN" in out
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("xonsh") is None, reason="xonsh not installed")
def test_xonsh_shell(simple_env, tmp_path, vt100_terminal):
    shell = XonshShell(simple_env)
    rc_dir = tmp_path / "xonshrc.d"
    rc_dir.mkdir()
    (rc_dir / "01-prompt.xsh").write_text(
        '$PROMPT = "RC_D_LOADED " + ${...}.get("PROMPT", "")\n'
    )
    with NamedTemporaryFile(
        prefix="conda-spawn-",
        suffix=".xsh",
        delete=False,
        mode="w",
    ) as f:
        f.write(shell.spawn_script())

    env = shell.env()
    env["XONSHRC"] = ""
    env["XONSHRC_DIR"] = str(rc_dir)
    screen = vt100_terminal("xonsh", ["--rc", f.name, "-i"], env)

    # Poll the virtual screen until the env prefix appears in the
    # prompt, proving CONDA_DEFAULT_ENV was set by the activation.
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        text = "\n".join(screen.display)
        if str(simple_env) in text and "RC_D_LOADED" in text:
            break
        time.sleep(0.1)
    else:
        text = "\n".join(screen.display)
        assert str(simple_env) in text, f"env not in screen:\n{text}"
        assert "RC_D_LOADED" in text, f"xonsh rc dir not loaded:\n{text}"


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


def test_xonsh_user_rc_preamble(xonsh_shell):
    preamble = xonsh_shell.user_rc_preamble()
    assert "xonshrc_context" in preamble
    assert "XONSHRC" in preamble
    assert "XONSHRC_DIR" in preamble


def test_xonsh_spawn_script_includes_preamble(xonsh_shell):
    script = xonsh_shell.spawn_script()
    assert "xonshrc_context" in script
    assert UnixShell.READY_MARKER in script
