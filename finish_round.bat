@echo off
REM ============================================================
REM  队列跑完之后的一条龙：重算数字 -> 出图 -> 出表 -> 全套审计
REM  双击运行即可；任何一步失败都会停在这一步并打印原因。
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=.venv\Scripts\python.exe
set RSCRIPT="C:\Program Files\R\R-4.6.1\bin\x64\Rscript.exe"

echo.
echo ============================================================
echo  [1/6] 确认队列已经跑完
echo ============================================================
if not exist night6.log (
    echo [X] 找不到 night6.log，队列没启动过？
    goto :failed
)
powershell -NoProfile -Command "$t = Get-Content night6.log -Tail 5; $t | ForEach-Object { Write-Host '   ' $_ }"
findstr /C:"[night] finished" night6.log >nul
if errorlevel 1 (
    echo.
    echo [X] night6.log 里还没有 "finished"，说明队列仍在跑。
    echo     等它跑完，或者先跑 tools\progress.ps1 看进度。
    goto :failed
)

echo.
echo ============================================================
echo  [2/6] 从 CSV 重算 headline 数字
echo ============================================================
%PY% tools\report_numbers.py
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  [3/6] R 出图与表（等效性/剂量/科室/算力）
echo ============================================================
%RSCRIPT% R\run_all.R
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  [4/6] 出论文正文表
echo ============================================================
%PY% tools\make_table1.py
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  [5/6] 刷新审计清单（哈希 + 选择日志）
echo ============================================================
%PY% tools\make_audit.py
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  [6/6] 六段交叉核对 A-F
echo ============================================================
%PY% tools\audit_final.py
if errorlevel 1 goto :failed

echo.
echo ============================================================
echo  [OK] 全部完成。接下来看：
echo        paper\table1.md          论文表
echo        paper\figures\*.png      四张图
echo        RESULTS.md               结论（数字若有变要同步）
echo ============================================================
pause
exit /b 0

:failed
echo.
echo ============================================================
echo  [FAILED] 上面最后一条输出就是原因。
echo ============================================================
pause
exit /b 1
