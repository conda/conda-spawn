from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from subprocess import run

import pytest
from conda.activate import PowerShellActivator
from conda.base.context import context

from conda_spawn.shell import PowershellShell

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell")


def _quote(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


@pytest.fixture
def powershell():
    executable = shutil.which("powershell.exe")
    if executable is None:
        pytest.skip("Windows PowerShell not installed")
    return executable


@pytest.mark.parametrize(
    "initialized, interactive, command, expected_status",
    [
        pytest.param(False, False, "info --json", 0, id="uninitialized-info"),
        pytest.param(True, False, "info --json", 0, id="initialized-info"),
        pytest.param(True, True, "info --json", 0, id="interactive-info"),
        pytest.param(True, True, "activate", 1, id="interactive-activate"),
        pytest.param(True, True, "deactivate", 1, id="interactive-deactivate"),
    ],
)
def test_powershell_conda_command(
    powershell, tmp_path, initialized, interactive, command, expected_status
):
    prefix = tmp_path / "spawn-env"
    (prefix / "conda-meta").mkdir(parents=True)
    shell = PowershellShell(prefix)
    result_file = tmp_path / "result.json"
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        "$global:LASTEXITCODE = 97\n"
        f"$output = conda {command} 2>&1 | Out-String\n"
        "$status = $LASTEXITCODE\n"
        "$result = @{\n"
        "    output = [string]$output\n"
        "    status = $status\n"
        "    conda_exe = [string]$Env:CONDA_EXE\n"
        "} | ConvertTo-Json\n"
        f"[System.IO.File]::WriteAllText({_quote(result_file)}, $result)\n"
        "exit $status\n",
        encoding="utf-8-sig",
    )
    invoke_probe = f". {_quote(probe)}\n"
    startup = tmp_path / "startup.ps1"
    startup.write_text(
        (PowerShellActivator().hook(auto_activate=False) if initialized else "")
        + "\n"
        + shell.script()
        + "\n"
        + ("" if interactive else invoke_probe),
        encoding="utf-8-sig",
    )
    args = [powershell, "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass"]
    if interactive:
        args.append("-NoExit")
    result = run(
        [*args, "-File", str(startup)],
        check=False,
        input=invoke_probe if interactive else "",
        capture_output=True,
        text=True,
        env=shell.env(),
        timeout=30,
    )
    assert result_file.exists(), result.stderr
    captured = json.loads(result_file.read_text(encoding="utf-8-sig"))
    assert result.returncode == expected_status, captured["output"]
    assert captured["status"] == expected_status, captured["output"]
    assert captured["conda_exe"] == ""
    if expected_status == 0:
        info = json.loads(captured["output"])
        assert info["root_prefix"] == context.root_prefix
        assert info["active_prefix"] == str(prefix)
    else:
        assert f"Run 'conda init' before 'conda {command}'" in captured["output"]


@pytest.mark.parametrize("dev", [False, True], ids=["executable", "python-module"])
def test_powershell_conda_command_preserves_arguments(
    powershell, tmp_path, monkeypatch, dev
):
    prefix = tmp_path / "spawn-env"
    (prefix / "conda-meta").mkdir(parents=True)
    if dev:
        executable = sys.executable
        (tmp_path / "forwarding_probe.py").write_text(
            "import json, sys\nprint(json.dumps(sys.argv[1:]))\nsys.exit(23)\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    else:
        executable = str(tmp_path / "conda's $executable.ps1")
        Path(executable).write_text(
            "ConvertTo-Json -InputObject @($args) -Compress\nexit 23\n",
            encoding="utf-8-sig",
        )
    monkeypatch.setattr(
        type(context),
        "conda_exe_vars_dict",
        property(
            lambda self: {
                "CONDA_EXE": executable,
                "_CE_M": "-m" if dev else None,
                "_CE_CONDA": "forwarding_probe" if dev else None,
            }
        ),
    )
    arguments = ["two words", "single'quote", "$HOME", "--"]
    script = tmp_path / "forward.ps1"
    script.write_text(
        PowershellShell(prefix).script()
        + "\n$global:LASTEXITCODE = 97\nconda "
        + " ".join(_quote(arg) for arg in arguments)
        + "\nexit $LASTEXITCODE\n",
        encoding="utf-8-sig",
    )
    result = run(
        [
            powershell,
            "-NoLogo",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 23, result.stderr
    assert json.loads(result.stdout) == arguments
