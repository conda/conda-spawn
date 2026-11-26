from __future__ import annotations

from conda.base.context import context

from conda_spawn.shell import PosixShell


def test_spawn_activation_omits_conda_meta_vars(simple_env):
    activation = PosixShell(simple_env)._activator.build_activate(str(simple_env))
    assert not context.conda_exe_vars_dict.keys() & activation["export_vars"].keys()
    assert context.conda_exe_vars_dict.keys() <= set(activation["unset_vars"])
    assert activation["export_vars"]["CONDA_PREFIX"] == str(simple_env)


def test_uppercase_path_omits_conda_meta_vars(simple_env):
    export_vars, unset_vars = PosixShell(simple_env)._activator.get_export_unset_vars(
        PATH="/x"
    )
    assert "CONDA_EXE" not in export_vars
    assert "CONDA_EXE" in unset_vars
