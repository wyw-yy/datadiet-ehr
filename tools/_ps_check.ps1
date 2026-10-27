# _ps_check.ps1 —— 列出所有 python 进程（pid、父 pid、命令行），由 night_queue.py 过滤。
#
# 为什么只列不判断：Windows 上 `.venv\Scripts\python.exe` 是个"转向器"，
# 它会另起一个基座 python 跑同一个脚本，于是同一份脚本在进程表里出现两次
# （父进程 cmdline 相同、pid 不同）。判断"是不是自己"必须在 python 里
# 沿父进程链往上走，否则队列一启动就把自己当成"已有重活在跑"而自我拒绝。
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
    ForEach-Object { "$($_.ProcessId)`t$($_.ParentProcessId)`t$($_.CommandLine)" }
