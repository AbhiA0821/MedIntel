@echo off
title MedIntel Stop

:: =====================================================================
:: MEDINTEL — SAFE STOP SCRIPT
:: =====================================================================

echo =====================================================================
echo  Stopping MedIntel services (Ports 8000 and 5000)...
echo =====================================================================

powershell -NoProfile -Command ^
    "$ports = @(8000, 5000);" ^
    "foreach ($p in $ports) {" ^
    "    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue;" ^
    "    foreach ($c in $conns) {" ^
    "        if ($c.OwningProcess) {" ^
    "            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue;" ^
    "            Write-Host ('  [STOPPED] Process on port ' + $p + ' (PID: ' + $c.OwningProcess + ')');" ^
    "        }" ^
    "    }" ^
    "};" ^
    "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*simulator_runner.py*' -or $_.CommandLine -like '*frontend/app.py*' -or $_.CommandLine -like '*frontend\\app.py*' } | ForEach-Object {" ^
    "    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue;" ^
    "    Write-Host ('  [STOPPED] Lingering runner process (PID: ' + $_.ProcessId + ')');" ^
    "}"

echo.
echo MedIntel services stopped cleanly.
echo Database and data files remain intact.
