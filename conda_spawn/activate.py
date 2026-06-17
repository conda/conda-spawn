from __future__ import annotations

from os.path import join

from conda import activate as _activate
from conda.base.context import context


class _CondabinFirstMixin:
    """JRG(2025-01-16): keep the local conda.activate changes as a shim."""

    def get_export_unset_vars(self, export_metavars=True, **kwargs):
        # JRG: spawned shells do not need CONDA_EXE and friends; those exist
        # for conda's shell function, while deactivate/reactivate still need
        # upstream's default behavior.
        suppress_metavars = "path" in kwargs or "PATH" in kwargs
        if suppress_metavars:
            export_metavars = False
        export_vars, unset_vars = super().get_export_unset_vars(
            export_metavars=export_metavars, **kwargs
        )
        if suppress_metavars:
            for name in context.conda_exe_vars_dict:
                export_vars.pop(name, None)
                if name not in unset_vars:
                    unset_vars.append(name)
        return export_vars, unset_vars

    def _ensure_root_condabin_is_first(self, path_list):
        condabin_dir = self.path_conversion(join(context.conda_prefix, "condabin"))
        if condabin_dir in path_list:
            path_list.remove(condabin_dir)
        path_list.insert(0, condabin_dir)
        return path_list

    def _add_prefix_to_path(self, prefix, starting_path_dirs=None):
        path_list = list(super()._add_prefix_to_path(prefix, starting_path_dirs))
        # JRG: no conda shell function has highest precedence here, so keep
        # $CONDA_ROOT/condabin first and avoid env-local conda shadowing base.
        return tuple(self._ensure_root_condabin_is_first(path_list))

    def _replace_prefix_in_path(self, old_prefix, new_prefix, starting_path_dirs=None):
        path_list = list(
            super()._replace_prefix_in_path(old_prefix, new_prefix, starting_path_dirs)
        )
        # JRG: mirror _add_prefix_to_path when swapping/removing prefixes.
        return tuple(self._ensure_root_condabin_is_first(path_list))


class PosixActivator(_CondabinFirstMixin, _activate.PosixActivator):
    pass


class CshActivator(_CondabinFirstMixin, _activate.CshActivator):
    pass


class XonshActivator(_CondabinFirstMixin, _activate.XonshActivator):
    pass


class CmdExeActivator(_CondabinFirstMixin, _activate.CmdExeActivator):
    pass


class FishActivator(_CondabinFirstMixin, _activate.FishActivator):
    pass


class PowerShellActivator(_CondabinFirstMixin, _activate.PowerShellActivator):
    pass


_Activator = _activate._Activator
activator_map = {
    **_activate.activator_map,
    "posix": PosixActivator,
    "ash": PosixActivator,
    "bash": PosixActivator,
    "dash": PosixActivator,
    "zsh": PosixActivator,
    "csh": CshActivator,
    "tcsh": CshActivator,
    "xonsh": XonshActivator,
    "cmd.exe": CmdExeActivator,
    "fish": FishActivator,
    "powershell": PowerShellActivator,
}
