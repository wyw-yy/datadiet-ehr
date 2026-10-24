@echo off
chcp 65001 >nul
cd /d "%~dp0"
setlocal

echo ============================================================
echo   Build offline wheelhouse  (run this on machine A only)
echo ============================================================
echo.
echo This downloads every wheel needed to rebuild the env offline,
echo so the other machines do not need internet at all.
echo Estimated size: about 400 MB (plus the 2.5 GB torch wheel).
echo.

if not exist "wheelhouse" mkdir "wheelhouse"

echo [1/3] downloading dependency wheels ...
".venv\Scripts\python.exe" -m pip download -r requirements-lock.txt -d wheelhouse --only-binary=:all: --disable-pip-version-check
if errorlevel 1 (
  echo [ERROR] pip download failed
  pause
  exit /b 1
)

echo.
echo [2/3] copying the torch wheel ...
copy /y "torch-2.11.0+cu128-cp312-cp312-win_amd64.whl" "wheelhouse\" >nul
if errorlevel 1 (
  echo [WARN] torch wheel not found in the project root - copy it manually into wheelhouse\
)

echo.
echo [3/3] contents of wheelhouse:
dir /b wheelhouse | find /c /v "" 
echo files in wheelhouse
echo.
echo DONE. Now copy the whole project folder (without .venv) to the other machine.
pause
