from __future__ import annotations

from conda.base.context import context
from conda.common.compat import on_win

from conda_spawn.shell import PosixShell, PowershellShell


def test_spawn_script_omits_conda_meta_vars(simple_env):
    script = PosixShell(simple_env).script()
    assert context.conda_exe_vars_dict["CONDA_EXE"] not in script
    assert "CONDA_PREFIX" in script


def test_uppercase_path_omits_conda_meta_vars(simple_env):
    export_vars, unset_vars = PosixShell(simple_env)._activator.get_export_unset_vars(
        PATH="/x"
    )
    assert "CONDA_EXE" not in export_vars
    assert "CONDA_EXE" in unset_vars


def test_powershell_script_defines_conda_function(simple_env):
    """PowerShell script must define a conda function routing to conda.exe (#32).

    Without this, conda.bat (in condabin) silently no-ops for
    activate/deactivate in PowerShell. The function ensures conda.exe
    (the Python entry point) handles the command so main_mock_activate
    fires as intended.
    """
    conda_exe = context.conda_exe_vars_dict["CONDA_EXE"]
    shell = PowershellShell(simple_env)
    script = shell.script()
    assert (f'function conda {{ & "{conda_exe}" @args }}' in script) == on_win
