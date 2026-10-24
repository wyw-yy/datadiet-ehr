@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo  Step 1/3 : check virtual environment
echo ============================================================
if not exist ".venv\Scripts\activate.bat" (
  echo [ERROR] .venv not found in this folder:
  echo         %~dp0
  echo Create it first with:  python -m venv .venv
  pause
  exit /b 1
)
call ".venv\Scripts\activate.bat"

echo.
echo ============================================================
echo  Step 2/3 : install torch's missing dependencies
echo ============================================================
python -m pip install typing-extensions filelock fsspec jinja2 setuptools sympy networkx -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
  echo.
  echo [WARN] Tsinghua mirror failed, retrying with default PyPI ...
  python -m pip install typing-extensions filelock fsspec jinja2 setuptools sympy networkx
)

echo.
echo ============================================================
echo  Step 3/3 : verify the GPU can really compute
echo ============================================================
python -c "import torch; print('torch      =', torch.__version__); print('cuda build =', torch.version.cuda); print('device     =', torch.cuda.get_device_name(0)); x=torch.randn(2048,2048,device='cuda'); print('matmul sum =', (x@x).sum().item())"
echo.
echo ============================================================
echo  If a number was printed above, the environment is READY.
echo ============================================================
pause
