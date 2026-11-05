@echo off
rem 由 Windows 计划任务调用：脱离 DSH 会话跑完那 25 个补跑，跑完关机。
rem 起因：2026-11-05 凌晨那批是会话后台 job 的子进程，会话重启后被杀，机器空转 15.5 h。
cd /d D:\code\codetest\datadiet-ehr
set PYTHONIOENCODING=utf-8
set DATADIET_N_TRAIN=48000
set DATADIET_N_POOL=48000
set DATADIET_EPOCHS=1
set DATADIET_RATIOS=0.01,0.05,0.10,0.20,0.30,0.50,0.70

.venv\Scripts\python.exe tools\resume_rigor.py >> logs\resume_task.log 2>&1
echo [%DATE% %TIME%] resume_rigor exited with %ERRORLEVEL% >> logs\resume_task.log

.venv\Scripts\python.exe tools\shutdown_after_rigor.py --log logs/resume.log --process resume_rigor.py --interval 120 --max-wait-hours 30 >> logs\shutdown_watch_out.log 2>&1