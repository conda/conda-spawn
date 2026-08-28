"""Best-effort shell support for conda-spawn.

These shells are provided to bring `conda spawn` to parity with
`conda activate`'s own activator coverage so it can replace
`conda activate` on systems that use them. They are lightly tested
relative to the core supported matrix (`bash`, `zsh`, `powershell`,
`cmd`) and rely on user reports for shell-specific bugs.
"""

from __future__ import annotations

import re
import shlex
from textwrap import indent
from typing import ClassVar

from . import activate
from .shell import UnixShell


class FishShell(UnixShell):
    """fish shell support.

    Best-effort: not part of the core supported shell matrix (`bash`,
    `zsh`, `powershell`, `cmd`). It exists to bring `conda spawn` to
    parity with `conda activate`'s own activator coverage, but is
    lightly tested and relies on user reports for shell-specific bugs.
    """

    Activator = activate.FishActivator
    default_shell = "fish"
    supports_init_injection: ClassVar[bool] = True

    def prompt(self) -> str:
        # Preserve any pre-existing `fish_prompt` (including ones installed
        # by prompt tools like starship) and prepend conda's prompt modifier
        # so users see their env name regardless of their shell setup.
        return (
            "if functions -q fish_prompt\n"
            "    if not functions -q __conda_spawn_orig_fish_prompt\n"
            "        functions -c fish_prompt __conda_spawn_orig_fish_prompt\n"
            "        functions -e fish_prompt\n"
            "    end\n"
            "end\n"
            "function fish_prompt\n"
            '    printf "%s" "$CONDA_PROMPT_MODIFIER"\n'
            "    if functions -q __conda_spawn_orig_fish_prompt\n"
            "        __conda_spawn_orig_fish_prompt\n"
            "    end\n"
            "end"
        )

    def source_command(self, script_path: str) -> str:
        return f'source "{script_path}"'

    def write_init_injection(
        self, script_path: str
    ) -> tuple[tuple[str, ...], dict[str, str]] | None:
        return (("-C", f"source {shlex.quote(script_path)}"), {})

    def executable(self) -> str:
        return "fish"


class CshShell(UnixShell):
    """csh shell support.

    Best-effort: not part of the core supported shell matrix (`bash`,
    `zsh`, `powershell`, `cmd`). It exists to bring `conda spawn` to
    parity with `conda activate`'s own activator coverage, but is
    lightly tested and relies on user reports for shell-specific bugs.
    """

    Activator = activate.CshActivator
    default_shell = "csh"
    default_args = ("-i",)
    prompt_strip_markers = ("set prompt=",)

    def prompt(self) -> str:
        # csh/tcsh do not define $prompt automatically in all modes; guard
        # against "Undefined variable" by initialising it to "" if absent.
        return (
            'if (! $?prompt) set prompt = ""\n'
            f'set prompt="{self.prompt_modifier()}${{prompt}}"'
        )

    def source_command(self, script_path: str) -> str:
        return f'source "{script_path}"'

    def ready_marker_command(self, ready_marker: str | None = None) -> str:
        # csh does not ship a `printf` builtin; `echo -n` is portable
        # across csh/tcsh on the platforms we support.
        return f'echo -n "{ready_marker or self.READY_MARKER}"'

    def executable(self) -> str:
        return "csh"


class TcshShell(CshShell):
    """tcsh shell support.

    Inherits the same best-effort caveat as `CshShell`.
    """

    default_shell = "tcsh"

    def executable(self) -> str:
        return "tcsh"


class XonshShell(UnixShell):
    """xonsh shell support.

    Best-effort: not part of the core supported shell matrix (`bash`,
    `zsh`, `powershell`, `cmd`). It exists to bring `conda spawn` to
    parity with `conda activate`'s own activator coverage, but is
    lightly tested and relies on user reports for shell-specific bugs.
    """

    Activator = activate.XonshActivator
    default_shell = "xonsh"
    default_args = ("-i",)
    # xonsh's readline/prompt_toolkit backend discards pending PTY input
    # on startup, so the sendline fallback silently loses the activation
    # script. Using --rc avoids sending the script through the PTY.
    supports_init_injection: ClassVar[bool] = True

    @property
    def script_suffix(self) -> str:
        # The `XonshActivator` reports `.sh` (for bash-sourced
        # `activate.d` scripts) but `execute()` emits xonsh syntax.
        # `.xsh` is the canonical extension for xonsh scripts.
        return ".xsh"

    def _user_rc_loader(self) -> str:
        # --rc replaces xonsh's default rc discovery, so run xonsh's own
        # rc loader and preserve the loaded-file list for user handlers.
        return (
            "from xonsh.environ import xonshrc_context as "
            "_conda_spawn_xonshrc_context\n"
            "_conda_spawn_user_rc_files = _conda_spawn_xonshrc_context(\n"
            '    rcfiles=${...}.get("XONSHRC"),\n'
            '    rcdirs=${...}.get("XONSHRC_DIR"),\n'
            "    execer=__xonsh__.execer,\n"
            "    ctx=__xonsh__.ctx,\n"
            "    env=__xonsh__.env,\n"
            ")\n"
            "del _conda_spawn_xonshrc_context\n"
            "_conda_spawn_post_rc_fire = events.on_post_rc.fire\n"
            "def _conda_spawn_fire_post_rc(**kwargs):\n"
            "    __xonsh__.rc_files = _conda_spawn_user_rc_files\n"
            "    events.on_post_rc.fire = _conda_spawn_post_rc_fire\n"
            "    return _conda_spawn_post_rc_fire(**kwargs)\n"
            "events.on_post_rc.fire = _conda_spawn_fire_post_rc"
        )

    def spawn_script(self, ready_marker: str | None = None) -> str:
        # Wrap on_pre_cmdloop.fire so every user handler completes before
        # activation and the ready marker, independent of handler order.
        activation_script = super().spawn_script(ready_marker)
        return (
            f"{self._user_rc_loader()}\n"
            "_conda_spawn_pre_cmdloop_fire = events.on_pre_cmdloop.fire\n"
            "def _conda_spawn_fire_pre_cmdloop(**kwargs):\n"
            "    events.on_pre_cmdloop.fire = _conda_spawn_pre_cmdloop_fire\n"
            "    _conda_spawn_result = _conda_spawn_pre_cmdloop_fire(**kwargs)\n"
            f"{indent(activation_script, '    ')}"
            "    return _conda_spawn_result\n"
            "events.on_pre_cmdloop.fire = _conda_spawn_fire_pre_cmdloop\n"
        )

    def write_init_injection(
        self, script_path: str
    ) -> tuple[tuple[str, ...], dict[str, str]] | None:
        return (("--rc", script_path), {})

    def script(self) -> str:
        # `XonshActivator.unset_var_tmpl` emits `del $VAR` which raises
        # `KeyError` when the variable is not already set (e.g. on a fresh
        # CI runner). Replace every such line with the safe pop form.
        raw = super().script()
        return re.sub(
            r"^del \$(\w+)$",
            lambda m: f'${{...}}.pop("{m.group(1)}", None)',
            raw,
            flags=re.MULTILINE,
        )

    def prompt(self) -> str:
        # Prepend `CONDA_PROMPT_MODIFIER` to `$PROMPT` while keeping
        # any format-field tokens in the user's prompt intact.
        return "$PROMPT = ${...}.get('CONDA_PROMPT_MODIFIER', '') + $PROMPT"

    def source_command(self, script_path: str) -> str:
        return f'source "{script_path}"'

    def post_activation_command(self) -> str:
        # In xonsh, bare `stty echo` is treated as subprocess but the
        # explicit `$[...]` form is unambiguous inside a sourced script.
        return "$[stty echo]"

    def ready_marker_command(self, ready_marker: str | None = None) -> str:
        return f'print({ready_marker or self.READY_MARKER!r}, end="", flush=True)'

    def executable(self) -> str:
        return "xonsh"
