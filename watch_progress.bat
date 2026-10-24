@echo off
chcp 65001 >nul
title DataDiet-EHR 下载进度
echo.
echo   正在打开进度窗口...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0watch_progress.ps1"
pause
