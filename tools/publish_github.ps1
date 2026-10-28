# publish_github.ps1 —— 一条命令把仓库发上 GitHub（需要先 gh auth login）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File tools\publish_github.ps1                # 默认私有仓库
#   powershell -ExecutionPolicy Bypass -File tools\publish_github.ps1 -Public        # 公开仓库
#   powershell -ExecutionPolicy Bypass -File tools\publish_github.ps1 -SkipRelease   # 只推代码不做 Release
#
# 前置（只做一次）：gh auth login    —— 选 GitHub.com / HTTPS / 浏览器登录
#
# 做完的事：
#   1) 检查 gh 登录状态；没登录就打印怎么登，直接退出（绝不半途改仓库）
#   2) 在账号下建 datadiet-ehr 仓库（默认私有），设 remote origin 并推送 master + tags
#   3) 用 tools/make_release.py 打成果包，作为 Release 资产上传
#   4) 打印 Zenodo 之后要用的 DOI 步骤

param(
    [string]$Repo = "datadiet-ehr",
    [switch]$Public,
    [switch]$SkipRelease
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

function Fail($msg) { Write-Host "[x] $msg" -ForegroundColor Red; exit 1 }
function Info($msg) { Write-Host "[·] $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "[√] $msg" -ForegroundColor Green }

# 原生命令（git/gh）把进度写到 stderr，而 $ErrorActionPreference="Stop" 会把
# stderr 当终止错误 —— 上一次就因此"推送其实成功了、脚本却中途退出"。
# 用这个包一层：只看退出码。
function Run-Native {
    param([scriptblock]$Cmd)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $Cmd 2>&1 | Out-Host; return $LASTEXITCODE } finally { $ErrorActionPreference = $prev }
}

# ---------------------------------------------------------------- 0. 前置检查
$gh = Get-Command gh -ErrorAction SilentlyContinue
if (-not $gh) { Fail "没装 GitHub CLI。装：winget install --id GitHub.cli" }

$authOk = $false
try { gh auth status 2>&1 | Out-Null; $authOk = ($LASTEXITCODE -eq 0) } catch { $authOk = $false }
if (-not $authOk) {
    Write-Host ""
    Write-Host "还没登录 GitHub。先在这个窗口跑一次（只做一次）：" -ForegroundColor Yellow
    Write-Host "    gh auth login" -ForegroundColor White
    Write-Host "  选：GitHub.com → HTTPS → Login with a web browser → 浏览器里贴 8 位码" -ForegroundColor Yellow
    Write-Host ""
    exit 2
}
Ok "gh 已登录"

if (git status --porcelain) { Fail "工作区不干净，先提交（我不想把半成品推上去）" }
Ok "工作区干净"

# ---------------------------------------------------------- 1. 已经有 origin 吗
$hasOrigin = (git remote) -contains "origin"
if ($hasOrigin) {
    Info "已有 origin：" + (git remote get-url origin)
} else {
    $vis = if ($Public) { "--public" } else { "--private" }
    Info "创建仓库 $Repo（$vis）并推送..."
    $rc = Run-Native { gh repo create $Repo $vis --source . --remote origin --push --description "DataDiet-EHR: activation-based training-subset selection with an equivalence protocol (reproducible, audited)" }
    if ($rc -ne 0) { Fail "gh repo create 失败（可能仓库名已被占用，换个 -Repo 名字）" }
    Ok "仓库已创建并推送"
}

# --------------------------------------------------------------- 2. 推 tag 与分支
Info "推送 master 与 tags..."
$null = Run-Native { git push -u origin master }
$null = Run-Native { git push origin --tags }
Ok "分支与 tag 已推送"

# ------------------------------------------------------- 3. 打成果包并上传 Release
if (-not $SkipRelease) {
    $ver = "1.0.0"
    Info "打成果包 v$ver ..."
    & ".\.venv\Scripts\python.exe" "tools\make_release.py" --version $ver | Out-Host
    $zip = "dist/datadiet-ehr-v$ver.zip"
    if (-not (Test-Path $zip)) { Fail "没生成 $zip" }
    $notes = "docs/release_notes_v$ver.md"
    $tag = "v$ver"
    $exists = (git tag) -contains $tag
    if (-not $exists) {
        Info "本地还没有 $tag，先创建（指向当前 HEAD）"
        git tag -a $tag -m "paper/competition submission snapshot"
        git push origin $tag 2>&1 | Out-Null
    }
    Info "创建 GitHub Release $tag ..."
    $useNotes = if (Test-Path $notes) { "--notes-file $notes" } else { "--generate-notes" }
    $existing = Run-Native { gh release view $tag --json tagName }
    if ($existing -eq 0) {
        Info "Release $tag 已存在，跳过"
    } else {
        $rc = Run-Native { gh release create $tag $zip --title "v$ver — 数据冗余度实证：30% 数据等效，净省 48.2%" $useNotes }
        if ($rc -ne 0) { Write-Host "[!] Release 创建失败，但代码已经推上去了" -ForegroundColor Yellow }
        else { Ok "Release 已发布" }
    }
}

# ------------------------------------------------------------------- 4. 收尾提示
$url = (gh repo view --json url -q .url)
Write-Host ""
Ok "仓库：$url"
Write-Host "下一步（拿 DOI 写进论文）：" -ForegroundColor Cyan
Write-Host "  1) 论文投稿前把仓库设为 public：gh repo edit --visibility public --accept-visibility-change-consequences"
Write-Host "  2) 在 https://zenodo.org 用 GitHub 账号登录 → Settings → GitHub → 打开本仓库开关"
Write-Host "  3) 在 GitHub 上发一个 Release（Zenodo 会自动抓取并给 DOI）"
Write-Host "  4) 把 DOI 填进论文的 Code Availability 段（docs/ARTIFACT_USE.md 有模板句）"
exit 0
