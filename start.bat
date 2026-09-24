@echo off
rem ============================================================
rem  Soulforge one-click launcher v1.2 (Windows 10/11)
rem
rem  Aligns with start.sh:
rem    1. Detect OpenClaw root / Python venv / port / browser auto-open
rem    2. Log everything in English so cmd codepage (936 / 65001) never breaks output
rem    3. Use `chcp 65001` is OPTIONAL; this script assumes console output is
rem       ASCII-only so it works under both ANSI/GBK (936) and UTF-8 (65001).
rem    Default URL: http://127.0.0.1:8848
rem ============================================================
setlocal EnableExtensions EnableDelayedExpansion
title Soulforge Launcher
cd /d "%~dp0"

set "HOST=127.0.0.1"
set "PORT=8848"
set "PYTHON="
set "OPENCLAW_DIR="
set "DATA_DIR="
set "BACKEND=%~dp0backend"
set "FRONTEND=%~dp0frontend"

echo ============================================================
echo   Soulforge Launcher
echo ============================================================
echo.

rem ---------- 0. Check Windows version ----------
set "WIN_MAJOR="
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "[System.Environment]::OSVersion.Version.Major" 2^>nul`) do set "WIN_MAJOR=%%V"
if defined WIN_MAJOR if !WIN_MAJOR! LSS 10 goto :warn_oldwin

:proceed
rem ---------- 1. Verify project layout ----------
if not exist "%BACKEND%\main.py" goto :err_struct

rem ---------- 2. Detect OpenClaw root ----------
if defined SOULFORGE_OPENCLAW_DIR (
    set "OPENCLAW_DIR=%SOULFORGE_OPENCLAW_DIR%"
    echo [OpenClaw] Using directory from environment: %OPENCLAW_DIR%
) else (
    rem Layout: soulforge is <OpenClaw-root>\workspace\projects\soulforge - 4 levels up
    for %%I in ("%BACKEND%\..\..\..\..") do set "CANDIDATE=%%~fI"
    if exist "%CANDIDATE%\openclaw.json" (
        set "OPENCLAW_DIR=%CANDIDATE%"
        echo [OpenClaw] Auto-detected root: %OPENCLAW_DIR%
    ) else (
        rem Fallback: default user profile location
        for %%C in ("%USERPROFILE%\.openclaw") do (
            if not defined OPENCLAW_DIR if exist "%%~C\openclaw.json" set "OPENCLAW_DIR=%%~C"
        )
        if defined OPENCLAW_DIR echo [OpenClaw] Fallback root: !OPENCLAW_DIR!
    )
)
if not defined OPENCLAW_DIR (
    echo [WARN] Could not locate the OpenClaw root - openclaw.json not found, or no Agent under workspace.
    echo   The Agent list will likely be empty. To fix:
    echo   1. Place soulforge under the OpenClaw workspace\projects\ directory.
    echo   2. Or set: set SOULFORGE_OPENCLAW_DIR=C:\path\to\OpenClaw
    echo.
)

rem ---------- 3. Prepare data directory ----------
if defined SOULFORGE_DATA_DIR (
    set "DATA_DIR=%SOULFORGE_DATA_DIR%"
) else (
    set "DATA_DIR=%~dp0.soulforge"
)
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%" >nul 2>&1
set "PROBE=%DATA_DIR%\.soulforge_write_test.tmp"
>nul 2>&1 echo test > "%PROBE%"
if not exist "%PROBE%" goto :err_perm
del /q "%PROBE%" >nul 2>&1
echo [Data] Data directory: %DATA_DIR%
echo.

rem ---------- 4. Locate or create Python virtual environment ----------
if exist "%BACKEND%\.venv\Scripts\python.exe" goto :venv_exists

echo [Python] No virtual environment found. Looking for system Python...
set "SYS_PY="
where py >nul 2>&1
if not errorlevel 1 for /f "delims=" %%V in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "SYS_PY=%%V"
if defined SYS_PY goto :sys_py_found
where python >nul 2>&1
if not errorlevel 1 for /f "delims=" %%V in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "SYS_PY=%%V"
if not defined SYS_PY goto :err_nopython

:sys_py_found
"%SYS_PY%" -c "import sys;raise SystemExit(sys.version_info<(3,10))" >nul 2>&1
if errorlevel 1 goto :err_pyver
echo [Python] System Python: %SYS_PY%
echo [Python] Creating virtual environment (this may take a moment)...
"%SYS_PY%" -m venv "%BACKEND%\.venv"
if errorlevel 1 goto :err_venv
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
echo [Python] Virtual environment created.
goto :py_ready

:venv_exists
set "PYTHON=%BACKEND%\.venv\Scripts\python.exe"
echo [Python] Reusing existing virtual environment.

:py_ready
"%PYTHON%" -c "import sys;raise SystemExit(sys.version_info<(3,10))" >nul 2>&1
if errorlevel 1 goto :err_venv_broken

rem ---------- 5. Install dependencies if missing ----------
"%PYTHON%" -c "import fastapi,uvicorn,sqlalchemy,pydantic,multipart,loguru,send2trash" >nul 2>&1
if not errorlevel 1 goto :deps_ok
echo [Deps] Missing dependencies. Trying default PyPI first...
"%PYTHON%" -m pip install --disable-pip-version-check fastapi uvicorn sqlalchemy pydantic python-multipart loguru tomli send2trash
if not errorlevel 1 goto :deps_check
echo [Deps] Default PyPI failed. Retrying with Tsinghua mirror...
"%PYTHON%" -m pip install --disable-pip-version-check -i https://pypi.tuna.tsinghua.edu.cn/simple fastapi uvicorn sqlalchemy pydantic python-multipart loguru tomli send2trash
if not errorlevel 1 goto :deps_check
echo [Deps] Tsinghua mirror failed. Retrying with Aliyun mirror...
"%PYTHON%" -m pip install --disable-pip-version-check -i https://mirrors.aliyun.com/pypi/simple/ fastapi uvicorn sqlalchemy pydantic python-multipart loguru tomli send2trash

:deps_check
"%PYTHON%" -c "import fastapi,uvicorn,sqlalchemy,pydantic,multipart,loguru,send2trash" >nul 2>&1
if errorlevel 1 goto :err_deps
echo [Deps] All dependencies ready.

:deps_ok

rem ---------- 6. Resolve port / check (and clean up stale instance) ----------
if defined SOULFORGE_PORT set "PORT=%SOULFORGE_PORT%"
for /f "usebackq delims=" %%P in (`"%PYTHON%" -c "import tomllib,os,pathlib;p=pathlib.Path(r'%~dp0.soulforge').joinpath('config.toml') if not os.environ.get('SOULFORGE_DATA_DIR') else pathlib.Path(os.environ['SOULFORGE_DATA_DIR']).joinpath('config.toml');print(tomllib.loads(p.read_text(encoding='utf-8')).get('server',{}).get('port',8848) if p.exists() else 8848)" 2^>nul`) do set "PORT=%%P"
echo [Port] Listening on: %PORT%

set "OCCUPIED="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /c:":%PORT% " ^| findstr "LISTENING"') do set "OCCUPIED=%%P"
if not defined OCCUPIED goto :port_ok
echo [Port] Port %PORT% is occupied by PID %OCCUPIED%. Inspecting...
set "CMDLINE="
for /f "usebackq delims=" %%C in (`powershell -NoProfile -Command "(gwmi win32_process -filter 'ProcessId=%OCCUPIED%').CommandLine" 2^>nul`) do set "CMDLINE=%%C"
echo(!CMDLINE!| findstr /i "uvicorn" >nul 2>&1
if not errorlevel 1 goto :kill_old
echo [WARN] Port %PORT% is held by another process (PID %OCCUPIED%): %CMDLINE%
echo Possible fixes:
echo   1. Stop that process manually.
echo   2. Or change the port in config.toml under [server].
echo      Or override for this run: set SOULFORGE_PORT=<other_port>
echo.
goto :fail

:kill_old
echo [Port] Killing stale Soulforge instance (PID %OCCUPIED%)...
taskkill /F /PID %OCCUPIED% >nul 2>&1
if errorlevel 1 goto :err_kill
echo [Port] Waiting 2 seconds for the port to be released...
timeout /t 2 /nobreak >nul 2>&1

:port_ok

rem ---------- 7. Verify frontend build artifacts ----------
if not exist "%FRONTEND%\dist\index.html" (
    echo [WARN] Frontend build not found at frontend\dist.
    echo   The web UI will not be served. To build it:
    echo   cd frontend ^&^& npm install ^&^& npm run build
    echo.
)

rem ---------- 8. Launch ----------
echo ============================================================
echo   Starting Soulforge server...
echo   OpenClaw root: %OPENCLAW_DIR%
echo   Data directory: %DATA_DIR%
echo   URL: http://%HOST%:%PORT%
echo   Press Ctrl+C to stop.
echo ============================================================
echo.

if defined OPENCLAW_DIR set "SOULFORGE_OPENCLAW_DIR=%OPENCLAW_DIR%"
set "SOULFORGE_DATA_DIR=%DATA_DIR%"

rem Wait 3 seconds before opening the browser so the server has time to bind.
if /i not "%SOULFORGE_NO_BROWSER%"=="1" goto :open_browser
goto :run_server

:open_browser
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process 'http://%HOST%:%PORT%'" >nul 2>&1

:run_server
cd /d "%BACKEND%"
"%PYTHON%" -m uvicorn main:app --host %HOST% --port %PORT%

echo.
echo  Soulforge server has stopped.
echo.
endlocal
exit /b 0

rem ---------- Error handlers ----------
:warn_oldwin
echo [WARN] Detected Windows major version !WIN_MAJOR!.
echo   Soulforge requires Python 3.10+, which is only supported on Windows 10/11.
echo.
goto :proceed

:err_struct
echo [ERROR] Could not find %BACKEND%\main.py.
echo Please run this script from inside the soulforge directory.
echo   Expected paths: soulforge\start.bat and soulforge\backend\main.py
echo.
goto :fail

:err_perm
echo [ERROR] The data directory is not writable: %DATA_DIR%
echo Possible fixes:
echo   1. Choose a directory you have write access to.
echo   2. Or override: set SOULFORGE_DATA_DIR=D:\soulforge-data
echo.
goto :fail

:err_nopython
echo [ERROR] No Python interpreter found in PATH.
echo Please install Python 3.10 or newer (make sure to check "Add python.exe to PATH").
echo   Download: https://www.python.org/downloads/
echo.
goto :fail

:err_pyver
echo [ERROR] The detected Python is older than 3.10.
echo Detected: %SYS_PY%
echo Please install a newer version: https://www.python.org/downloads/
echo.
goto :fail

:err_venv
echo [ERROR] Failed to create the virtual environment.
echo This usually means the venv module is missing or the path is read-only
echo   (for example, under Program Files). Run from a writable location.
echo.
goto :fail

:err_venv_broken
echo [ERROR] The existing virtual environment is broken or uses Python below 3.10.
echo Please delete %BACKEND%\.venv and let the script recreate it.
echo.
goto :fail

:err_deps
echo [ERROR] Failed to install required dependencies.
echo Possible fixes:
echo   1. Check your network or proxy, e.g.:
echo      "%PYTHON%" -m pip config set global.proxy http://host:port
echo   2. Retry from a network with access to pypi.org.
echo.
goto :fail

:err_kill
echo [ERROR] Failed to terminate stale process PID %OCCUPIED%. Please stop it manually.
echo.
goto :fail

:fail
echo Soulforge failed to start. See the message above.
pause >nul
exit /b 1