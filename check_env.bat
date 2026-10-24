@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo ============================================================
echo   Step 0 : environment check  (takes about 10 seconds)
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found in %CD%
  pause
  exit /b 1
)

echo [1/3] python + torch + GPU ...
".venv\Scripts\python.exe" -c "import torch; print('torch', torch.__version__); print('cuda', torch.version.cuda); print('gpu', torch.cuda.get_device_name(0)); print('cap', torch.cuda.get_device_capability()); print('cuda_ok', torch.cuda.is_available())"
if errorlevel 1 (
  echo.
  echo [ERROR] torch or GPU check failed
  pause
  exit /b 1
)
echo.

echo [2/3] base model files ...
".venv\Scripts\python.exe" -c "import os,glob; d='models/Qwen2.5-1.5B-Instruct'; fs=sorted(glob.glob(d+'/*')); print('files', len(fs)); print('has_config', os.path.exists(d+'/config.json')); print('has_tok', os.path.exists(d+'/tokenizer.json'))"
echo.

echo [3/3] data check (20 items should be green) ...
".venv\Scripts\python.exe" tools\verify.py
if errorlevel 1 (
  echo.
  echo [ERROR] data check failed - see the red lines above
  pause
  exit /b 1
)
echo.
echo ============================================================
echo   EVERYTHING LOOKS OK - you can run  run_pilots.bat  now
echo ============================================================
pause
exit /b 0
