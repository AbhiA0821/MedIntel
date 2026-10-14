@echo off
title MedIntel Launcher

:: =====================================================================
:: MEDINTEL — ONE-CLICK LIVE SYSTEM STARTUP
:: =====================================================================

set "PROJECT_ROOT=%~dp0"
cd /d "%PROJECT_ROOT%"

set "PYTHON_EXE=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Virtual environment python executable not found:
    echo         %PYTHON_EXE%
    echo Please create/configure the virtual environment before launching.
    pause
    exit /b 1
)

if not exist "%PROJECT_ROOT%.env" (
    if exist "%PROJECT_ROOT%.env.example" (
        echo [NOTICE] .env file not found. Copying from .env.example ...
        copy "%PROJECT_ROOT%.env.example" "%PROJECT_ROOT%.env" >nul
    )
)

echo =====================================================================
echo  MEDINTEL CLINICAL INTELLIGENCE PLATFORM
echo  Preparing Live Services...
echo =====================================================================
echo.

:: Clean up any lingering processes on ports 8000 and 5000 before starting
powershell -NoProfile -Command ^
    "$ports = @(8000, 5000);" ^
    "foreach ($p in $ports) {" ^
    "    $conns = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue;" ^
    "    foreach ($c in $conns) {" ^
    "        if ($c.OwningProcess) {" ^
    "            Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue;" ^
    "            Write-Host ('  [CLEANUP] Stopped previous process on port ' + $p + ' (PID: ' + $c.OwningProcess + ')');" ^
    "        }" ^
    "    }" ^
    "};" ^
    "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*simulator_runner.py*' -or $_.CommandLine -like '*frontend/app.py*' -or $_.CommandLine -like '*frontend\\app.py*' } | ForEach-Object {" ^
    "    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue;" ^
    "    Write-Host ('  [CLEANUP] Stopped lingering runner process (PID: ' + $_.ProcessId + ')');" ^
    "}"

echo.
echo [1/2] Starting MedIntel Backend and Simulator on Port 8000 ...
echo       (Hosts in-process FastAPI server and continuous background simulator)
start "MedIntel Backend and Simulator" /d "%PROJECT_ROOT%" "%PYTHON_EXE%" -u simulator\simulator_runner.py

echo.
echo [2/2] Starting MedIntel Frontend on Port 5000 ...
echo       (Hosts Flask presentation dashboard)
start "MedIntel Frontend" /d "%PROJECT_ROOT%" "%PYTHON_EXE%" frontend\app.py

echo.
echo Waiting for services to initialize...
"%PYTHON_EXE%" scripts\wait_for_backend.py
if %ERRORLEVEL% equ 0 (
    echo   + Backend and Simulator active on http://127.0.0.1:8000 [Health: OK]
) else (
    echo   ! Backend initialization taking longer than expected; proceeding...
)

echo.
echo =====================================================================
echo  MEDINTEL IS LIVE AND READY FOR TESTING
echo =====================================================================
echo   Backend and Simulator: http://127.0.0.1:8000
echo   Backend Health:        http://127.0.0.1:8000/health
echo   API Documentation:     http://127.0.0.1:8000/docs
echo   Frontend Dashboard:    http://127.0.0.1:5000
echo   Frontend Login:        http://127.0.0.1:5000/login
echo =====================================================================
echo.
echo Opening browser to http://127.0.0.1:5000/login ...
start http://127.0.0.1:5000/login
