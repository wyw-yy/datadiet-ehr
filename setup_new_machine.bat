@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal enabledelayedexpansion

echo ============================================================
echo   Setup a new machine  (run this on machine B / C)
echo ============================================================
echo.
echo Requirements:
echo   - Python 3.12 installed (same minor version as machine A)
echo   - the wheelhouse\ folder present (built on machine A)
echo   - about 12 GB free disk
echo.

if not exist "wheelhouse" (
  echo [ERROR] wheelhouse\ not found. Copy it from machine A first.
  pause
  exit /b 1
)

echo [1/4] locating Python 3.12 ...
where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not on PATH. Install Python 3.12 and tick "Add to PATH".
  pause
  exit /b 1
)
python -c "import sys;print('python', sys.version.split()[0]); sys.exit(0 if sys.version_info[:2]==(3,12) else 1)"
if errorlevel 1 (
  echo [ERROR] need Python 3.12 exactly
  pause
  exit /b 1
)
echo.

echo [2/4] creating venv ...
if exist ".venv" (
  echo [INFO] .venv already exists - reusing it
) else (
  python -m venv .venv
  if errorlevel 1 (
    echo [ERROR] venv creation failed
    pause
    exit /b 1
  )
)
echo.

echo [3/4] installing torch (offline) ...
set "TORCHW="
for %%f in ("wheelhouse\torch-*.whl") do set "TORCHW=%%~ff"
if "%TORCHW%"=="" (
  echo [ERROR] no torch wheel in wheelhouse\
  pause
  exit /b 1
)
echo      wheel: %TORCHW%
".venv\Scripts\python.exe" -m pip install --no-index --no-cache-dir "%TORCHW%" --disable-pip-version-check
if errorlevel 1 (
  echo [ERROR] torch install failed
  pause
  exit /b 1
)
echo.

echo [4/4] installing the rest (offline) ...
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements-lock.txt --disable-pip-version-check
if errorlevel 1 (
  echo [ERROR] dependency install failed
  pause
  exit /b 1
)
echo.

echo verifying ...
".venv\Scripts\python.exe" -c "import torch, transformers, peft, datasets, pandas; print('torch', torch.__version__); print('gpu', torch.cuda.get_device_name(0)); print('cap', torch.cuda.get_device_capability()); print('transformers', transformers.__version__); print('cuda_ok', torch.cuda.is_available())"
if errorlevel 1 (
  echo [ERROR] verification failed
  pause
  exit /b 1
)
echo.
echo ============================================================
echo   Machine ready. Next: run tools\verify.py, then
echo   run_one.py --shard k/3  (see docs\SETUP_MACHINES.md)
echo ============================================================
pause
