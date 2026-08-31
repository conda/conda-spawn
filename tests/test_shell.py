import gc
import shutil
import sys
from pathlib import Path
from subprocess import DEVNULL, PIPE, check_output

import pexpect
import pytest
from conda.base.context import reset_context

from conda_spawn import shell as shell_module
from conda_spawn.constants import CONDA_SPAWN_ENV_VAR
from conda_spawn.shell import (
    BashShell,
    CmdExeShell,
    PosixShell,
    PowershellShell,
    UnixShell,
    ZshShell,
)


@pytest.fixture(scope="session")
def conda_env(session_tmp_env):
    with session_tmp_env("conda") as prefix:
        yield prefix


@pytest.fixture
def no_prompt(monkeypatch):
    monkeypatch.setenv("CONDA_CHANGEPS1", "false")
    reset_context()
    yield


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_posix_shell(simple_env):
    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline("env")
    proc.sendeof()
    out = proc.read().decode()
    env_vars = set(out.splitlines())
    assert f"{CONDA_SPAWN_ENV_VAR}=1" in env_vars
    assert not any(line.startswith("CONDA_SPAWN=") for line in env_vars)
    assert "CONDA_PREFIX" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("dash") is None, reason="dash not installed")
def test_posix_shell_uses_native_startup_before_fallback_activation(
    simple_env, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    home.mkdir()
    initial_env = home / "initial-env.sh"
    initial_env.write_text("export SPAWN_TEST_INITIAL_ENV_LOADED=1\n")
    profile_env = home / "profile-env.sh"
    profile_env.write_text("export SPAWN_TEST_USER_ENV_LOADED=1\n")
    (home / ".profile").write_text(
        'export SPAWN_TEST_PROFILE_LOADED=1\nENV="$HOME/profile-env.sh"\nexport ENV\n'
    )

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHELL", shutil.which("dash") or "dash")
    monkeypatch.setenv("ENV", str(initial_env))

    shell = PosixShell(simple_env)
    activation_script = shell.script()
    monkeypatch.setattr(
        shell,
        "script",
        lambda: activation_script + "\nprintf 'SPAWN_TEST_ACTIVATION_RAN\\n'\n",
    )
    proc = shell.spawn_tty()
    startup = (proc.before or b"").decode(errors="replace")
    assert startup.count("SPAWN_TEST_ACTIVATION_RAN") == 1

    proc.sendline(
        f'printf "CONDA_PREFIX=%s\\n{CONDA_SPAWN_ENV_VAR}=%s\\n'
        "SPAWN_TEST_PROFILE_LOADED=%s\\n"
        "SPAWN_TEST_USER_ENV_LOADED=%s\\n"
        "SPAWN_TEST_INITIAL_ENV_LOADED=%s\\n"
        f'ENV=%s\\n" "$CONDA_PREFIX" "${CONDA_SPAWN_ENV_VAR}" '
        '"$SPAWN_TEST_PROFILE_LOADED" "$SPAWN_TEST_USER_ENV_LOADED" '
        '"${SPAWN_TEST_INITIAL_ENV_LOADED:-}" "$ENV"'
    )
    proc.sendline("dash -i -c 'printf NESTED_SHELL_READY'")
    proc.expect_exact(b"NESTED_SHELL_READY", timeout=15)
    nested_startup = (proc.before or b"").decode(errors="replace")
    assert "SPAWN_TEST_ACTIVATION_RAN" not in nested_startup
    proc.sendline("printf OUTER_SHELL_READY")
    proc.expect_exact(b"OUTER_SHELL_READY", timeout=15)
    out = nested_startup + (proc.before or b"").decode(errors="replace")
    proc.sendline("exit")
    proc.expect(pexpect.EOF, timeout=15)
    out += (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in out
    assert f"{CONDA_SPAWN_ENV_VAR}=1" in out
    assert "SPAWN_TEST_PROFILE_LOADED=1" in out
    assert "SPAWN_TEST_USER_ENV_LOADED=1" in out
    assert "SPAWN_TEST_INITIAL_ENV_LOADED=" in out
    assert f"ENV={profile_env}" in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("dash") is None, reason="dash not installed")
def test_posix_profile_can_unset_env_before_fallback_activation(
    simple_env, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    home.mkdir()
    initial_env = home / "initial-env.sh"
    initial_env.write_text("export SPAWN_TEST_INITIAL_ENV_LOADED=1\n")
    (home / ".profile").write_text("export SPAWN_TEST_PROFILE_LOADED=1\nunset ENV\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("SHELL", shutil.which("dash") or "dash")
    monkeypatch.setenv("ENV", str(initial_env))

    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline(
        'printf "CONDA_PREFIX=%s\\nSPAWN_TEST_PROFILE_LOADED=%s\\n'
        'SPAWN_TEST_INITIAL_ENV_LOADED=%s\\nENV_SET=%s\\n" '
        '"$CONDA_PREFIX" "$SPAWN_TEST_PROFILE_LOADED" '
        '"${SPAWN_TEST_INITIAL_ENV_LOADED:-}" "${ENV+x}"'
    )
    proc.sendline("exit")
    proc.expect(pexpect.EOF, timeout=15)
    out = (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in out
    assert "SPAWN_TEST_PROFILE_LOADED=1" in out
    assert "SPAWN_TEST_INITIAL_ENV_LOADED=" in out
    assert "ENV_SET=" in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_bash_native_login_startup_before_fallback_activation(
    simple_env, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text(
        f"printf '{UnixShell.READY_MARKER}\\n'\n"
        "sleep 0.2\n"
        "printf 'SPAWN_TEST_BASH_PROFILE_LOADED\\n'\n"
        "SPAWN_TEST_BASH_PROFILE_VAR=profile\n"
        "spawn_test_profile_func() { printf 'SPAWN_TEST_BASH_FUNCTION\\n'; }\n"
        "alias spawn_test_profile_alias='echo SPAWN_TEST_BASH_ALIAS'\n"
        "shopt -s nullglob\n"
        "PROMPT_COMMAND='echo SPAWN_TEST_PROMPT_COMMAND'\n"
        '. "$HOME/.bashrc"\n'
    )
    (home / ".bashrc").write_text("printf 'SPAWN_TEST_BASHRC_LOADED\\n'\n")
    (home / ".bash_login").write_text("printf 'SPAWN_TEST_BASH_LOGIN_LOADED\\n'\n")
    (home / ".profile").write_text("printf 'SPAWN_TEST_PROFILE_LOADED\\n'\n")
    (home / ".bash_logout").write_text("printf 'SPAWN_TEST_BASH_LOGOUT_LOADED\\n'\n")
    monkeypatch.setenv("HOME", str(home))

    shell = BashShell(simple_env)
    activation_script = shell.script()
    monkeypatch.setattr(
        shell,
        "script",
        lambda: activation_script + "\nprintf 'SPAWN_TEST_ACTIVATION_RAN\\n'\n",
    )
    activation_paths = []
    original_source_command = shell.source_command

    def source_command(script_path):
        activation_paths.append(Path(script_path))
        return original_source_command(script_path)

    monkeypatch.setattr(shell, "source_command", source_command)
    proc = shell.spawn_tty()
    startup = (proc.before or b"").decode(errors="replace")
    assert "SPAWN_TEST_BASH_PROFILE_LOADED" in startup
    assert UnixShell.READY_MARKER in startup
    assert "SPAWN_TEST_BASHRC_LOADED" in startup
    assert "SPAWN_TEST_BASH_LOGIN_LOADED" not in startup
    assert "SPAWN_TEST_PROFILE_LOADED" not in startup
    assert startup.count("SPAWN_TEST_ACTIVATION_RAN") == 1
    assert "SPAWN_TEST_PROMPT_COMMAND" in startup
    assert len(activation_paths) == 1
    assert not activation_paths[0].exists()

    proc.sendline(
        f'printf "CONDA_PREFIX=%s\\n{CONDA_SPAWN_ENV_VAR}=%s\\nPROFILE_VAR=%s\\n" '
        f'"$CONDA_PREFIX" "${CONDA_SPAWN_ENV_VAR}" '
        '"$SPAWN_TEST_BASH_PROFILE_VAR"'
    )
    proc.sendline("spawn_test_profile_func")
    proc.sendline("spawn_test_profile_alias")
    proc.sendline("shopt -q login_shell && printf 'SPAWN_TEST_LOGIN_SHELL\\n'")
    proc.sendline("shopt -q nullglob && printf 'SPAWN_TEST_NULLGLOB\\n'")
    proc.sendline("printf 'SPAWN_TEST_BASH_%s' STATE_DONE")
    proc.expect_exact(b"SPAWN_TEST_BASH_STATE_DONE", timeout=15)
    state = (proc.before or b"").decode(errors="replace")
    proc.sendline("logout")
    proc.expect(pexpect.EOF, timeout=15)
    logout = (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in state
    assert f"{CONDA_SPAWN_ENV_VAR}=1" in state
    assert "PROFILE_VAR=profile" in state
    assert "SPAWN_TEST_BASH_FUNCTION" in state
    assert "SPAWN_TEST_BASH_ALIAS" in state
    assert "SPAWN_TEST_LOGIN_SHELL" in state
    assert "SPAWN_TEST_NULLGLOB" in state
    assert "SPAWN_TEST_BASH_LOGOUT_LOADED" in logout


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not installed")
def test_zsh_native_startup_precedes_fallback_activation(
    simple_env, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    user_zdotdir = home / ".config" / "zsh"
    user_zdotdir.mkdir(parents=True)
    (home / ".zshenv").write_text(
        'export ZDOTDIR="$HOME/.config/zsh"\nprint -r -- SPAWN_TEST_ZSHENV_LOADED\n'
    )
    (user_zdotdir / ".zprofile").write_text("print -r -- SPAWN_TEST_ZPROFILE_LOADED\n")
    (user_zdotdir / ".zshrc").write_text("print -r -- SPAWN_TEST_ZSHRC_LOADED\n")
    (user_zdotdir / ".zlogin").write_text("print -r -- SPAWN_TEST_ZLOGIN_LOADED\n")
    (user_zdotdir / ".zlogout").write_text("print -r -- SPAWN_TEST_ZLOGOUT_LOADED\n")
    posix_env = tmp_path / "posix-env.sh"
    posix_env.write_text("print -r -- POSIX_ENV_RAN\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ZDOTDIR", raising=False)
    monkeypatch.setenv("ENV", str(posix_env))

    shell = ZshShell(simple_env)
    activation_script = shell.script()
    monkeypatch.setattr(
        shell,
        "script",
        lambda: activation_script + "\nprint -r -- SPAWN_TEST_ACTIVATION_RAN\n",
    )
    proc = shell.spawn_tty()
    startup = (proc.before or b"").decode(errors="replace")
    assert "SPAWN_TEST_ZSHENV_LOADED" in startup
    assert "SPAWN_TEST_ZPROFILE_LOADED" in startup
    assert "SPAWN_TEST_ZSHRC_LOADED" in startup
    assert "SPAWN_TEST_ZLOGIN_LOADED" in startup
    assert startup.count("SPAWN_TEST_ACTIVATION_RAN") == 1
    assert "POSIX_ENV_RAN" not in startup

    proc.sendline(
        'print -r -- "CONDA_PREFIX=$CONDA_PREFIX" '
        f'"{CONDA_SPAWN_ENV_VAR}=${CONDA_SPAWN_ENV_VAR}" '
        '"PROMPT_ZDOTDIR=${ZDOTDIR-<unset>}"'
    )
    proc.sendline("zsh -dlic 'print -r -- NESTED_SHELL_READY'")
    proc.expect_exact(b"NESTED_SHELL_READY", timeout=15)
    nested_startup = (proc.before or b"").decode(errors="replace")
    assert "SPAWN_TEST_ACTIVATION_RAN" not in nested_startup
    proc.sendline("print -r -- OUTER_SHELL_READY")
    proc.expect_exact(b"OUTER_SHELL_READY", timeout=15)
    after_nested = (proc.before or b"").decode(errors="replace")
    assert "SPAWN_TEST_ZLOGOUT_LOADED" in after_nested
    proc.sendline("exit")
    proc.expect(pexpect.EOF, timeout=15)
    out = nested_startup + after_nested + (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in out
    assert f"{CONDA_SPAWN_ENV_VAR}=1" in out
    assert f"PROMPT_ZDOTDIR={user_zdotdir}" in out
    assert "SPAWN_TEST_ZLOGOUT_LOADED" in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not installed")
def test_zsh_rcs_setting_and_unset_zdotdir_survive_fallback_activation(
    simple_env, tmp_path, monkeypatch
):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".zshenv").write_text(
        "print -r -- SPAWN_TEST_ZSHENV_LOADED\nunsetopt RCS\n"
    )
    (home / ".zprofile").write_text("print -r -- SPAWN_TEST_ZPROFILE_SHOULD_NOT_RUN\n")
    (home / ".zshrc").write_text("print -r -- SPAWN_TEST_ZSHRC_SHOULD_NOT_RUN\n")
    (home / ".zlogin").write_text("print -r -- SPAWN_TEST_ZLOGIN_SHOULD_NOT_RUN\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ZDOTDIR", raising=False)

    shell = ZshShell(simple_env)
    activation_script = shell.script()
    monkeypatch.setattr(
        shell,
        "script",
        lambda: activation_script + "\nprint -r -- SPAWN_TEST_ACTIVATION_RAN\n",
    )
    proc = shell.spawn_tty()
    startup = (proc.before or b"").decode(errors="replace")
    assert "SPAWN_TEST_ZSHENV_LOADED" in startup
    assert "SPAWN_TEST_ZPROFILE_SHOULD_NOT_RUN" not in startup
    assert "SPAWN_TEST_ZSHRC_SHOULD_NOT_RUN" not in startup
    assert "SPAWN_TEST_ZLOGIN_SHOULD_NOT_RUN" not in startup
    assert startup.count("SPAWN_TEST_ACTIVATION_RAN") == 1

    proc.sendline(
        'print -r -- "CONDA_PREFIX=$CONDA_PREFIX" '
        '"RCS_STATE=$options[rcs]" "ZDOTDIR_SET=${+ZDOTDIR}"'
    )
    proc.sendline("exit")
    proc.expect(pexpect.EOF, timeout=15)
    out = (proc.before or b"").decode(errors="replace")

    assert f"CONDA_PREFIX={simple_env}" in out
    assert "RCS_STATE=off" in out
    assert "ZDOTDIR_SET=0" in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_posix_shell_ready_marker_synchronization(simple_env, request):
    """Regression test for the double-prompt fix (#22).

    `spawn_tty()` prints a distinctive ready marker after the activation
    script, the new `PS1`, and `stty echo` have all been applied, and
    then blocks on `expect_exact` until it sees that marker. Because
    `expect_exact` consumes everything up to *and including* the match,
    any output the shell emitted before activation completed -- including
    an initial prompt rendered from the parent process's (stale)
    `CONDA_DEFAULT_ENV`, which is what prompt tools like starship would
    read -- ends up in `child.before` and is never forwarded to the
    interactive user.

    Refs conda-incubator/conda-workspaces#20.
    """
    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()

    def _drain():
        proc.sendeof()
        proc.read()

    request.addfinalizer(_drain)

    marker = PosixShell.READY_MARKER
    assert marker, "PosixShell must define a non-empty READY_MARKER"
    # expect_exact() leaves the matched literal in child.after; if
    # someone removes the marker sync this assertion fails loudly
    # instead of regressing to the old racy os.read()-based approach.
    assert proc.after.startswith(marker.encode())
    assert proc.after != marker.encode()


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_powershell(simple_env):
    shell = PowershellShell(simple_env)
    with shell.spawn_popen(
        command=["ls", "env:"], stdin=DEVNULL, stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=30)
        proc.kill()
        assert not proc.poll()
        assert CONDA_SPAWN_ENV_VAR in out
        assert "CONDA_PREFIX" in out
        assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_cmd(simple_env):
    shell = CmdExeShell(simple_env)
    with shell.spawn_popen(command=["@SET"], stdout=PIPE, text=True) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert CONDA_SPAWN_ENV_VAR in out
        assert "CONDA_PREFIX" in out
        assert str(simple_env) in out


def test_hooks(conda_cli, simple_env):
    out, err, rc = conda_cli("spawn", "--hook", simple_env)
    print(out)
    print(err, file=sys.stderr)
    assert not rc
    assert not err
    assert "CONDA_EXE" in out
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Only tested on Unix")
def test_hooks_integration_posix(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell posix '{simple_env}'"
    script = f'eval "$({hook})"\nenv | sort'
    script_path = tmp_path / "script-eval.sh"
    script_path.write_text(script)

    out = check_output(["bash", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_hooks_integration_powershell(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell powershell {simple_env}"
    script = f"{hook} | Out-String | Invoke-Expression\r\nls env:"
    script_path = tmp_path / "script-eval.ps1"
    script_path.write_text(script)

    out = check_output(["powershell", "-NoLogo", "-File", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_hooks_integration_cmd(simple_env, tmp_path):
    hook = f"{sys.executable} -m conda spawn --hook --shell cmd {simple_env}"
    script = f"FOR /F \"tokens=*\" %%g IN ('{hook}') do @CALL %%g\r\nset"
    script_path = tmp_path / "script-eval.bat"
    script_path.write_text(script)

    out = check_output(["cmd", "/D", "/C", script_path], text=True)
    print(out)
    assert str(simple_env) in out


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_condabin_first_posix_shell(simple_env, conda_env, no_prompt):
    shell = PosixShell(simple_env)
    proc = shell.spawn_tty()
    proc.sendline('echo "$PATH"')
    proc.sendeof()
    out = proc.read().decode()
    print(out)
    assert sys.prefix in out
    assert str(simple_env) in out
    assert out.index(sys.prefix) < out.index(str(simple_env))

    shell = PosixShell(conda_env)
    proc = shell.spawn_tty()
    proc.sendline("which conda")
    proc.sendeof()
    print(out)
    out = proc.read().decode()
    assert f"{sys.prefix}/condabin/conda" in out
    assert str(conda_env) not in out


@pytest.mark.skipif(sys.platform != "win32", reason="Powershell only tested on Windows")
def test_condabin_first_powershell(simple_env, conda_env, no_prompt):
    shell = PowershellShell(simple_env)
    with shell.spawn_popen(
        command=["echo", "$env:PATH"], stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert sys.prefix in out
        assert str(simple_env) in out
        assert out.index(sys.prefix) < out.index(str(simple_env))

    shell = PowershellShell(conda_env)
    with shell.spawn_popen(
        command=["where.exe", "conda"], stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert out.index(f"{sys.prefix}\\condabin\\conda") < out.index(str(conda_env))


@pytest.mark.skipif(sys.platform != "win32", reason="Cmd.exe only tested on Windows")
def test_condabin_first_cmd(simple_env, conda_env, no_prompt):
    shell = CmdExeShell(simple_env)
    with shell.spawn_popen(command=["echo", "%PATH%"], stdout=PIPE, text=True) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert sys.prefix in out
        assert str(simple_env) in out
        assert out.index(sys.prefix) < out.index(str(simple_env))

    shell = CmdExeShell(conda_env)
    with shell.spawn_popen(
        command=["where.exe", "conda"], stdout=PIPE, text=True
    ) as proc:
        out, _ = proc.communicate(timeout=5)
        proc.kill()
        assert not proc.poll()
        assert out.index(f"{sys.prefix}\\condabin\\conda") < out.index(str(conda_env))


@pytest.mark.parametrize(
    "cls, expected",
    [
        (BashShell, "bash"),
        (ZshShell, "zsh"),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else x,
)
def test_shell_executable(cls, expected, simple_env):
    assert cls(simple_env).executable() == expected


@pytest.mark.parametrize(
    "cls, expected_markers",
    [
        (PosixShell, ("PS1=",)),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else repr(x),
)
def test_prompt_strip_markers(cls, expected_markers):
    """Each subclass must declare the activator lines it wants stripped."""
    assert cls.prompt_strip_markers == expected_markers


def test_unix_shell_is_abstract_enough_to_require_subclass(simple_env):
    """Instantiating UnixShell directly fails on the abstract `Activator`.

    UnixShell deliberately does not pick an Activator; it's the base class
    shared by PosixShell / FishShell / CshShell / XonshShell.
    """
    with pytest.raises(AttributeError):
        UnixShell(simple_env)


@pytest.mark.parametrize(
    "cls, expected",
    [
        (BashShell, False),
        (PosixShell, False),
        (ZshShell, False),
    ],
    ids=lambda x: x.__name__ if isinstance(x, type) else repr(x),
)
def test_supports_init_injection(cls, expected):
    assert cls.supports_init_injection is expected


@pytest.mark.parametrize("cls", [PosixShell, BashShell, ZshShell])
def test_posix_family_write_init_injection_falls_back(cls, simple_env):
    shell = cls(simple_env)
    assert shell.write_init_injection("/tmp/script.sh") is None


def test_bash_default_args(simple_env):
    shell = BashShell(simple_env)
    assert shell.args() == ("-l", "-i")


def test_shell_env_sets_private_spawn_marker(simple_env):
    env = PosixShell(simple_env).env()
    assert env[CONDA_SPAWN_ENV_VAR] == "1"


def test_ready_marker_cannot_be_empty(simple_env):
    with pytest.raises(ValueError, match="ready marker cannot be empty"):
        PosixShell(simple_env).ready_marker_command("")


def test_shell_cleanup_removes_registered_paths(simple_env, tmp_path):
    temp_file = tmp_path / "activation.sh"
    temp_file.write_text("")
    temp_dir = tmp_path / "startup"
    temp_dir.mkdir()
    shell = PosixShell(simple_env)
    shell._register_cleanup_path(str(temp_file))
    shell._register_cleanup_path(str(temp_dir))

    shell.cleanup()
    shell.cleanup()

    assert not temp_file.exists()
    assert not temp_dir.exists()
    assert shell._files_to_remove == []


@pytest.mark.skipif(sys.platform == "win32", reason="Pty's only available on Unix")
def test_unix_shell_startup_failure_closes_child_and_removes_script(
    simple_env, monkeypatch
):
    script_paths = []

    class Child:
        closed = False

        def sendline(self, command):
            return None

        def expect_exact(self, marker):
            raise RuntimeError("startup failed")

        def close(self, force=False):
            self.closed = force

    child = Child()
    shell = PosixShell(simple_env)
    source_command = shell.source_command
    previous_sigwinch_handler = object()
    sigwinch_handlers = []

    def capture_source_command(script_path):
        script_paths.append(Path(script_path))
        return source_command(script_path)

    def signal_handler(signal_number, handler):
        assert signal_number == shell_module.signal.SIGWINCH
        sigwinch_handlers.append(handler)
        return previous_sigwinch_handler

    monkeypatch.setattr(shell, "source_command", capture_source_command)
    monkeypatch.setattr(shell_module.pexpect, "spawn", lambda *args, **kwargs: child)
    monkeypatch.setattr(shell_module.signal, "signal", signal_handler)

    with pytest.raises(RuntimeError, match="startup failed"):
        shell.spawn_tty()

    assert child.closed is True
    assert len(sigwinch_handlers) == 2
    assert sigwinch_handlers[-1] is previous_sigwinch_handler
    assert len(script_paths) == 1
    assert not script_paths[0].exists()


def test_powershell_spawn_popen_uses_atexit_fallback(simple_env, monkeypatch):
    script_paths = []
    process = object()

    def popen(args, **kwargs):
        script_path = Path(args[-1])
        assert script_path.exists()
        script_paths.append(script_path)
        return process

    monkeypatch.setattr(shell_module.subprocess, "Popen", popen)

    assert PowershellShell(simple_env).spawn_popen() is process
    gc.collect()

    assert len(script_paths) == 1
    assert script_paths[0].exists()

    shell_module._cleanup_pending_paths()

    assert not script_paths[0].exists()


def test_powershell_spawn_popen_failure_removes_script(simple_env, monkeypatch):
    script_paths = []

    def popen(args, **kwargs):
        script_path = Path(args[-1])
        assert script_path.exists()
        script_paths.append(script_path)
        raise OSError("process creation failed")

    monkeypatch.setattr(shell_module.subprocess, "Popen", popen)
    shell = PowershellShell(simple_env)

    with pytest.raises(OSError, match="process creation failed"):
        shell.spawn_popen()

    assert len(script_paths) == 1
    assert not script_paths[0].exists()
