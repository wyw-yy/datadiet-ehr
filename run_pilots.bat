@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo ============================================================
echo   DataDiet-EHR  :  pilot runs  (3 runs, about 85 minutes)
echo ============================================================
echo.

if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] .venv not found in %CD%
  echo         make sure this .bat sits in the datadiet-ehr folder
  pause
  exit /b 1
)

echo [0/4] GPU check ...
".venv\Scripts\python.exe" -c "import torch; print('torch', torch.__version__); print('cuda', torch.version.cuda); print('gpu', torch.cuda.get_device_name(0)); print('cap', torch.cuda.get_device_capability())"
if errorlevel 1 (
  echo.
  echo [ERROR] torch or GPU check failed - do not continue
  pause
  exit /b 1
)
echo.

echo [1/4] data check (20 items should be green) ...
".venv\Scripts\python.exe" tools\verify.py
if errorlevel 1 (
  echo.
  echo [ERROR] data check failed - see the red lines above
  pause
  exit /b 1
)
echo.

echo opening progress window ...
start "progress" powershell -NoProfile -ExecutionPolicy Bypass -File "tools\progress.ps1" -Config "tools\progress_pilot.json"
echo.

echo [2/4] RUN 1 of 3 : full   (12000 rows, about 50 min)
echo        leave this window alone. closing it stops the training.
".venv\Scripts\python.exe" -u run_one.py --method full --seed 1 --epochs 1
if errorlevel 1 goto failed
echo.

echo [3/4] RUN 2 of 3 : nait r30   (3600 rows, about 16 min)
".venv\Scripts\python.exe" -u run_one.py --method nait --ratio 0.30 --seed 1 --epochs 1
if errorlevel 1 goto failed
echo.

echo [4/4] RUN 3 of 3 : random r30 (3600 rows, about 16 min)
".venv\Scripts\python.exe" -u run_one.py --method random --ratio 0.30 --seed 1 --epochs 1
if errorlevel 1 goto failed
echo.

echo ============================================================
echo   RESULTS  (results\metrics_long.csv)
echo ============================================================
type results\metrics_long.csv
echo ============================================================
echo.
echo All three runs finished. Copy the table above into the chat.
echo.
pause
exit /b 0

:failed
echo.
echo [ERROR] one of the runs failed.
echo         1. scroll up, find the red / Traceback lines
echo         2. send those lines in the chat
echo         logs are in results\runs\ and models\adapters\
pause
exit /b 1
