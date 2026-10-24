# 通用进度窗口：读一个 JSON 配置，每 N 秒刷新"文件大小 + 日志尾巴"。
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\progress.ps1 -Config tools\progress_xxx.json
#
# 配置格式（UTF-8）：
# {
#   "title": "标题",
#   "log": "相对或绝对路径的日志文件（可省略）",
#   "note": "进度条下面那句提示（可省略）",
#   "items": [
#     {"label": "模型权重", "path": "models/Qwen2.5-3B-Instruct", "expect": 6.19},
#     {"label": "数据 MedQA", "path": "data/raw/medqa"}
#   ]
# }
# expect 单位是 GB：给了就画进度条，不给就只显示已占用大小。

param(
    [Parameter(Mandatory = $true)][string]$Config,
    [int]$Seconds = 3
)

$ErrorActionPreference = 'SilentlyContinue'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

if (-not (Test-Path $Config)) {
    $Config = Join-Path $root $Config
}
if (-not (Test-Path $Config)) {
    Write-Host "找不到配置: $Config" -ForegroundColor Red
    exit 1
}
$cfg = Get-Content $Config -Raw -Encoding UTF8 | ConvertFrom-Json

function Resolve-P($p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return $null }
    if ([System.IO.Path]::IsPathRooted($p)) { return $p }
    return (Join-Path $root $p)
}

function Get-SizeGB($p) {
    $rp = Resolve-P $p
    if (-not $rp -or -not (Test-Path $rp)) { return 0 }
    if (Test-Path $rp -PathType Leaf) { return (Get-Item $rp).Length / 1GB }
    $b = (Get-ChildItem $rp -Recurse -File -ErrorAction SilentlyContinue |
          Measure-Object -Property Length -Sum).Sum
    if ($null -eq $b) { return 0 }
    return $b / 1GB
}

function Show-Bar($frac) {
    $w = 32
    $n = [int][math]::Round($frac * $w)
    if ($n -gt $w) { $n = $w }
    if ($n -lt 0) { $n = 0 }
    return ("[" + ("#" * $n) + ("." * ($w - $n)) + "]")
}

$started = Get-Date
$logPath = Resolve-P $cfg.log

while ($true) {
    Clear-Host
    Write-Host ""
    Write-Host ("  " + $cfg.title) -ForegroundColor Cyan
    Write-Host ("  项目: $root") -ForegroundColor DarkGray
    Write-Host ("  " + ("-" * 64)) -ForegroundColor DarkGray
    $total = 0.0
    $expectTotal = 0.0
    foreach ($it in $cfg.items) {
        $gb = Get-SizeGB $it.path
        $total += $gb
        $expect = 0.0
        if ($null -ne $it.expect) { $expect = [double]$it.expect }
        if ($expect -gt 0) {
            $expectTotal += $expect
            $frac = [math]::Min(1.0, $gb / $expect)
            $line = "  {0,-24} {1} {2,5:N1}%  {3,5:N2} / {4:N2} GB" -f `
                    $it.label, (Show-Bar $frac), ($frac * 100), $gb, $expect
            $color = if ($frac -ge 0.999) { "Green" } elseif ($frac -gt 0.001) { "Yellow" } else { "DarkGray" }
        } else {
            $line = "  {0,-24} {1,8:N2} GB" -f $it.label, $gb
            $color = if ($gb -gt 0.001) { "Green" } else { "DarkGray" }
        }
        Write-Host $line -ForegroundColor $color
    }
    Write-Host ("  " + ("-" * 64)) -ForegroundColor DarkGray
    if ($expectTotal -gt 0) {
        $pct = [math]::Min(100, ($total / $expectTotal) * 100)
        Write-Host ("  合计 {0:N2} / {1:N2} GB  ({2:N1}%)" -f $total, $expectTotal, $pct) -ForegroundColor White
    } else {
        Write-Host ("  合计 {0:N2} GB" -f $total) -ForegroundColor White
    }
    Write-Host ("  已运行 {0:hh\:mm\:ss}" -f ((Get-Date) - $started)) -ForegroundColor DarkGray

    if ($cfg.note) {
        Write-Host ""
        Write-Host ("  " + $cfg.note) -ForegroundColor DarkCyan
    }

    if ($logPath -and (Test-Path $logPath)) {
        Write-Host ""
        Write-Host "  最近日志:" -ForegroundColor DarkGray
        Get-Content $logPath -Tail 5 | ForEach-Object {
            Write-Host ("    " + ($_ -replace "`t", " ")) -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host "  关掉这个窗口即可停止刷新（任务本身继续跑）。" -ForegroundColor DarkGray
    Start-Sleep -Seconds $Seconds
}
