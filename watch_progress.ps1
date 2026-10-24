# 实时下载进度（双击 watch_progress.bat 打开，关窗口即停）
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$targets = @(
    @{ label = "模型 Qwen2.5-3B-Instruct"; path = Join-Path $root "models\Qwen2.5-3B-Instruct"; expect = 6.19 },
    @{ label = "数据 HealthCareMagic-100k"; path = Join-Path $root "data\raw\healthcaremagic"; expect = 0 },
    @{ label = "数据 MedQA-USMLE";         path = Join-Path $root "data\raw\medqa";           expect = 0 },
    @{ label = "数据 MedMCQA";             path = Join-Path $root "data\raw\medmcqa";         expect = 0 }
)

function Get-SizeGB($p) {
    if (-not (Test-Path $p)) { return 0 }
    $b = (Get-ChildItem $p -Recurse -File -ErrorAction SilentlyContinue |
          Measure-Object -Property Length -Sum).Sum
    if ($null -eq $b) { return 0 }
    return $b / 1GB
}

function Show-Bar($frac) {
    $w = 34
    $n = [int][math]::Round($frac * $w)
    if ($n -gt $w) { $n = $w }
    return ("[" + ("#" * $n) + ("." * ($w - $n)) + "]")
}

while ($true) {
    Clear-Host
    Write-Host ""
    Write-Host "  DataDiet-EHR  —— 下载进度（每 3 秒刷新，关掉窗口就停）" -ForegroundColor Cyan
    Write-Host "  目录: $root" -ForegroundColor DarkGray
    Write-Host ("  " + ("-" * 62)) -ForegroundColor DarkGray
    $total = 0
    foreach ($t in $targets) {
        $gb = Get-SizeGB $t.path
        $total += $gb
        if ($t.expect -gt 0) {
            $frac = [math]::Min(1.0, $gb / $t.expect)
            $line = "  {0,-26} {1} {2,5:N1}%  {3,5:N2}/{4:N2} GB" -f $t.label, (Show-Bar $frac), ($frac * 100), $gb, $t.expect
            $color = if ($frac -ge 0.999) { "Green" } else { "Yellow" }
        } else {
            $line = "  {0,-26} {1,5:N2} GB" -f $t.label, $gb
            $color = if ($gb -gt 0.001) { "Green" } else { "DarkGray" }
        }
        Write-Host $line -ForegroundColor $color
    }
    Write-Host ("  " + ("-" * 62)) -ForegroundColor DarkGray
    Write-Host ("  合计已下载: {0:N2} GB" -f $total) -ForegroundColor White

    $log = Join-Path $root "model_download.log"
    if (Test-Path $log) {
        Write-Host ""
        Write-Host "  最近日志:" -ForegroundColor DarkGray
        Get-Content $log -Tail 4 | ForEach-Object {
            Write-Host ("    " + ($_ -replace "`t", " ")) -ForegroundColor DarkGray
        }
    }
    Start-Sleep -Seconds 3
}
