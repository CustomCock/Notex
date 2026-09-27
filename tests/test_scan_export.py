import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from notex.core import scan_export


def test_bash_script_is_syntactically_valid() -> None:
    script = scan_export.bash("10.0.0.1-10.0.0.3, 192.168.1.10", [22, 80, 443], timeout=0.5)
    assert "#!/usr/bin/env bash" in script and "/dev/tcp/$ip/$port" in script
    assert "10.0.0.1 10.0.0.2 10.0.0.3 192.168.1.10" in script
    assert "ports=(22 80 443)" in script and 'echo "ip,port,status,service,banner"' in script
    if not shutil.which("bash"):
        pytest.skip("bash nicht verfügbar")
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as handle:
        handle.write(script)
        path = handle.name
    try:
        result = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    finally:
        Path(path).unlink()


def test_bash_without_ping() -> None:
    script = scan_export.bash("10.0.0.1", [80], ping_first=False)
    assert "ping_first=0" in script
    if shutil.which("bash"):
        result = subprocess.run(["bash", "-n", "/dev/stdin"], input=script, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr


def test_powershell_script_content() -> None:
    script = scan_export.powershell("10.0.0.1-10.0.0.2", [22, 3389], timeout=0.8)
    assert "$targets = @(\"10.0.0.1\",\"10.0.0.2\")" in script
    assert "$ports   = @(22,3389)" in script and "$timeout = 800" in script
    assert "TcpClient" in script and "ExecutionPolicy Bypass" in script
    assert 'Write-Output "ip,port,status,service,banner"' in script


def test_powershell_syntax_if_pwsh_available() -> None:
    pwsh = shutil.which("pwsh") or shutil.which("powershell")
    script = scan_export.powershell("10.0.0.1", [80, 443])
    if not pwsh:
        pytest.skip("PowerShell nicht verfügbar")
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False) as handle:
        handle.write(script)
        path = handle.name
    try:
        check = ("$ErrorActionPreference='Stop'; $null = [System.Management.Automation.Language.Parser]::ParseFile("
                 f"'{path}', [ref]$null, [ref]$errors); if ($errors.Count) {{ $errors; exit 1 }}")
        result = subprocess.run([pwsh, "-NoProfile", "-Command", check], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        Path(path).unlink()
