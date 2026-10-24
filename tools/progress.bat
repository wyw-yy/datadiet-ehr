@echo off
chcp 65001 >nul
rem 用法: tools\progress.bat tools\progress_xxx.json
if "%~1"=="" (
  echo 用法: progress.bat ^<配置文件.json^>
  pause
  exit /b 1
)
title DataDiet-EHR 进度
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0progress.ps1" -Config "%~1"
