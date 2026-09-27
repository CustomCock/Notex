"""Einen konfigurierten Scan als eigenständiges Skript exportieren – PowerShell (nur Bordmittel) und Bash
(bash /dev/tcp, timeout, ping). Gleiche Zieldefinition, CSV-Ausgabe, ausführlich kommentiert. Ohne Qt.

Die Skripte machen dasselbe wie der eingebaute Scanner: TCP-Connect auf eine feste Portliste, optional ping vorweg.
Kein SYN-Scan, keine Admin-Rechte. Sie sind zum Nachvollziehen und für Rechner ohne Notex gedacht.
"""
from __future__ import annotations

from notex.core import scan


def _ports_list(ports: list[int]) -> str:
    return ",".join(str(p) for p in ports)


def powershell(targets_text: str, ports: list[int], timeout: float = 1.0, ping_first: bool = True) -> str:
    """PowerShell-5+-Skript (nur .NET-Bordmittel: TcpClient). Erwartet erweiterte Ziele als Kommaliste unten."""
    resolved = ",".join(f'"{t.ip}"' for t in _resolve(targets_text))
    ms = int(timeout * 1000)
    ping_line = ("        if (-not (Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 1)) "
                 "{ $alive = $false }") if ping_first else "        # (ping übersprungen)"
    return f'''# Netzwerk-Scan (aus Notex exportiert) – PowerShell, nur Bordmittel, keine Admin-Rechte.
# TCP-Connect-Scan wie in Notex: kein SYN-Scan, keine OS-Erkennung, kein UDP. Nur im eigenen Netz verwenden.
#
# Ausführen (Ausführungsrichtlinie nur für diesen Prozess lockern, nichts dauerhaft ändern):
#   powershell -ExecutionPolicy Bypass -File .\\scan.ps1
#   .\\scan.ps1 > scan.csv
#
$ErrorActionPreference = "SilentlyContinue"
$targets = @({resolved})
$ports   = @({_ports_list(ports)})
$timeout = {ms}   # Millisekunden je Verbindungsversuch
$pingFirst = ${str(ping_first).lower()}

Write-Output "ip,port,status,service,banner"
foreach ($ip in $targets) {{
    $alive = $true
    if ($pingFirst) {{
{ping_line}
    }}
    if (-not $alive) {{ continue }}
    foreach ($port in $ports) {{
        $client = New-Object System.Net.Sockets.TcpClient
        try {{
            $async = $client.BeginConnect($ip, $port, $null, $null)
            if ($async.AsyncWaitHandle.WaitOne($timeout)) {{
                $client.EndConnect($async)
                $banner = ""
                try {{
                    $stream = $client.GetStream()
                    $stream.ReadTimeout = $timeout
                    $buffer = New-Object byte[] 128
                    $read = $stream.Read($buffer, 0, 128)
                    if ($read -gt 0) {{
                        $banner = ([System.Text.Encoding]::ASCII.GetString($buffer, 0, $read) -replace '[^ -~]', ' ').Trim()
                    }}
                }} catch {{}}
                $banner = $banner -replace '"', "'"
                Write-Output ("{{0}},{{1}},open,,{{2}}" -f $ip, $port, $banner)
            }}
        }} catch {{}} finally {{ $client.Close() }}
    }}
}}
'''


def bash(targets_text: str, ports: list[int], timeout: float = 1.0, ping_first: bool = True) -> str:
    """Bash-Skript mit /dev/tcp (kein nc/nmap nötig), `timeout` je Verbindung, optional ping vorweg."""
    resolved = " ".join(t.ip for t in _resolve(targets_text))
    secs = f"{timeout:g}"
    ping_block = '''  if [ "$ping_first" = "1" ]; then
    ping -c1 -W1 "$ip" >/dev/null 2>&1 || continue
  fi''' if ping_first else "  :"
    return f'''#!/usr/bin/env bash
# Netzwerk-Scan (aus Notex exportiert) – Bash, nur Bordmittel (/dev/tcp), keine Admin-Rechte.
# TCP-Connect-Scan wie in Notex: kein SYN-Scan, keine OS-Erkennung, kein UDP. Nur im eigenen Netz verwenden.
#
# Ausführen:
#   bash scan.sh > scan.csv
#
set -u
targets=({resolved})
ports=({_ports_list(ports).replace(",", " ")})
timeout_s={secs}
ping_first={"1" if ping_first else "0"}

echo "ip,port,status,service,banner"
for ip in "${{targets[@]}}"; do
{ping_block}
  for port in "${{ports[@]}}"; do
    if timeout "$timeout_s" bash -c "exec 3<>/dev/tcp/$ip/$port" 2>/dev/null; then
      banner=$(timeout "$timeout_s" head -c 128 <&3 2>/dev/null | tr -d '\\000-\\037\\177' | tr ',"' '  ')
      exec 3>&- 2>/dev/null || true
      echo "$ip,$port,open,,$banner"
    fi
  done
done
'''


def _resolve(targets_text: str) -> list[scan.Target]:
    targets, _warnings = scan.parse_targets(targets_text)
    return targets or [scan.Target(targets_text.strip() or "127.0.0.1")]
