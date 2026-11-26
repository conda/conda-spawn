from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from subprocess import DEVNULL, PIPE

import pytest
from conda.activate import CmdExeActivator
from conda.base.context import context

from conda_spawn.shell import CmdExeShell


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe requires Windows")
@pytest.mark.parametrize("replace", [False, True], ids=["fresh", "replace"])
def test_cmd_activation_runs_scripts_and_sets_environment(
    tmp_path, monkeypatch, replace
):
    prefix = tmp_path / "target environment"
    (prefix / "conda-meta").mkdir(parents=True)
    (prefix / "conda-meta" / "state").write_text(
        json.dumps({"env_vars": {"SPAWN_TEST_CONFIGURED": "configured value"}}),
        encoding="utf-8",
    )
    activate_dir = prefix / "etc" / "conda" / "activate.d"
    activate_dir.mkdir(parents=True)
    (activate_dir / "probe.bat").write_text(
        '@SET "SPAWN_TEST_ACTIVATED=activation script"\n'
        '@SET "SPAWN_TEST_ORDER=%SPAWN_TEST_DEACTIVATED%|%SPAWN_TEST_CONFIGURED%"\n',
        encoding="utf-8",
    )
    for name in (
        "SPAWN_TEST_CONFIGURED",
        "SPAWN_TEST_ACTIVATED",
        "SPAWN_TEST_DEACTIVATED",
        "SPAWN_TEST_ORDER",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        "CONDA_PROMPT_MODIFIER",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CONDA_SHLVL", "0")
    monkeypatch.setenv("CONDA_EXE", "parent-conda.exe")

    if replace:
        previous = tmp_path / "previous environment"
        (previous / "conda-meta").mkdir(parents=True)
        deactivate_dir = previous / "etc" / "conda" / "deactivate.d"
        deactivate_dir.mkdir(parents=True)
        (deactivate_dir / "probe.bat").write_text(
            '@SET "SPAWN_TEST_DEACTIVATED=deactivation script"\n', encoding="utf-8"
        )
        previous_path = CmdExeActivator()._get_path_dirs(str(previous))
        monkeypatch.setenv(
            "PATH", os.pathsep.join([*previous_path, os.environ["PATH"]])
        )
        monkeypatch.setenv("CONDA_PREFIX", str(previous))
        monkeypatch.setenv("CONDA_DEFAULT_ENV", str(previous))
        monkeypatch.setenv("CONDA_SHLVL", "1")

    probe = tmp_path / "probe.py"
    probe.write_text(
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "names = ('SPAWN_TEST_CONFIGURED', 'SPAWN_TEST_ACTIVATED', "
        "'SPAWN_TEST_DEACTIVATED', 'SPAWN_TEST_ORDER', 'CONDA_PREFIX', 'CONDA_EXE')\n"
        "result = {name: os.environ.get(name) for name in names}\n"
        "result['path_first'] = os.environ['PATH'].split(os.pathsep)[0]\n"
        "Path(sys.argv[1]).write_text(json.dumps(result), encoding='utf-8')\n",
        encoding="utf-8",
    )
    result_path = tmp_path / "result.json"
    shell = CmdExeShell(prefix)
    try:
        proc = shell.spawn_popen(
            command=[sys.executable, str(probe), str(result_path)],
            cwd=tmp_path,
            stdin=DEVNULL,
            stdout=PIPE,
            stderr=PIPE,
            text=True,
        )
        try:
            _, stderr = proc.communicate(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
    finally:
        shell.cleanup()

    assert proc.returncode == 0
    assert len(stderr) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["SPAWN_TEST_CONFIGURED"] == "configured value"
    assert result["SPAWN_TEST_ACTIVATED"] == "activation script"
    deactivated = "deactivation script" if replace else None
    assert result["SPAWN_TEST_DEACTIVATED"] == deactivated
    assert result["SPAWN_TEST_ORDER"] == f"{deactivated or ''}|configured value"
    prefix_matches = result["CONDA_PREFIX"] == str(prefix)
    launcher_cleared = result["CONDA_EXE"] is None
    root_condabin_first = result["path_first"] == str(
        Path(context.conda_prefix) / "condabin"
    )
    assert prefix_matches
    assert launcher_cleared
    assert root_condabin_first
