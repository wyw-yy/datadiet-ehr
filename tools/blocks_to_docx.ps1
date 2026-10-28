# blocks_to_docx.ps1 —— 用 Word COM 按块精确排版，生成 docx + PDF。
# 本文件必须保存为 UTF-8 带 BOM（否则 PS 按 GBK 解析中文会报错）。
# 关键写法：一律用"文档末尾 Range + InsertAfter"，再格式化最后一个段落；
# 不要用 Paragraphs.Add() 后赋 Range.Text（会把段尾标记一并替换，导致整篇被吃掉，
# 实测出现 pages=1 / chars=0）。
#
# 用法：powershell -ExecutionPolicy Bypass -File tools\blocks_to_docx.ps1 -Blocks x.json -Docx y.docx -Pdf z.pdf

param(
    [Parameter(Mandatory = $true)][string]$Blocks,
    [Parameter(Mandatory = $true)][string]$Docx,
    [string]$Pdf = ""
)

$ErrorActionPreference = "Stop"
# 注意：$Blocks 是 [string] 类型的参数，PowerShell 变量名大小写不敏感，
# 若写成 `$blocks = ... | ConvertFrom-Json`，会把数组塞回这个 [string] 变量、
# 被转成字符串 "System.Object[]"，于是循环里一个块都拿不到（曾经的 pages=1 / chars=0）。
$blocksPath = (Resolve-Path $Blocks).Path
$DocxPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Docx))
# ConvertFrom-Json 在 PS 5.1 里不会枚举数组，管道里出来的是"一个 Object[]"，
# 所以不能写 @(cmd | ConvertFrom-Json)（那会得到 Count=1），要先落变量再判断类型。
$parsed = (Get-Content $blocksPath -Raw -Encoding UTF8) | ConvertFrom-Json
$items = if ($parsed -is [System.Array]) { $parsed } else { @($parsed) }
Write-Output ("blocks loaded: " + $items.Count)

$KAI = "楷体"; $HEI = "黑体"; $SONG = "宋体"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

function Set-Font($rng, $name, $size, $bold) {
    if ($null -eq $rng) { return }
    # 表格单元格的 Range 有时是"对象数组"，先取第一个；Word 的 Size 只吃 Single，
    # 传 Double 会抛 "Specified cast is not valid"（实测 10.5 就会）。
    if ($rng -is [System.Array]) { $rng = $rng[0] }
    $rng.Font.Name = $name
    $rng.Font.NameFarEast = $name
    $rng.Font.NameAscii = $name
    $rng.Font.Size = [single]$size
    $rng.Font.Bold = if ($bold) { 1 } else { 0 }
}

function Add-Para($doc, $word, $text) {
    $rng = $doc.Content
    $rng.Collapse(0) | Out-Null      # 0 = wdCollapseEnd
    $rng.InsertAfter($text)
    $rng.InsertParagraphAfter()
    return $doc.Paragraphs.Item($doc.Paragraphs.Count - 1)
}

try {
    $doc = $word.Documents.Add()

    foreach ($sec in $doc.Sections) {
        $ps = $sec.PageSetup
        $ps.PageWidth = $word.CentimetersToPoints(21.0)
        $ps.PageHeight = $word.CentimetersToPoints(29.7)
        $ps.TopMargin = $word.CentimetersToPoints(2.54)
        $ps.BottomMargin = $word.CentimetersToPoints(2.54)
        $ps.LeftMargin = $word.CentimetersToPoints(3.0)
        $ps.RightMargin = $word.CentimetersToPoints(3.0)
    }

    # 页脚页码：试过 footer.Range.Fields.Add 和文档级 doc.Fields.Add(33)，
    # 两种写法在这台机器上都不落盘（解包 docx 查 footer1.xml：fldChar=0、instrText=0），
    # 所以这里不再尝试——页码请在 Word 里 3 秒加上：插入 → 页码 → 页面底端（居中）。
    $footer = $doc.Sections.Item(1).Footers.Item(1)
    $footer.Range.ParagraphFormat.Alignment = 1

    $nTable = 0
    $idx = 0
    foreach ($b in $items) {
        $idx++
        $text = [string]$b.text
        try {
        switch ($b.type) {
            "title" {
                $p = Add-Para $doc $word $text
                $p.Range.ParagraphFormat.Alignment = 1
                $p.Range.ParagraphFormat.CharacterUnitFirstLineIndent = 0
                $p.Range.ParagraphFormat.SpaceAfter = 16
                Set-Font $p.Range $HEI 22 $true
            }
            "h2" {
                $p = Add-Para $doc $word $text
                $p.Range.ParagraphFormat.CharacterUnitFirstLineIndent = 0
                $p.Range.ParagraphFormat.SpaceBefore = 12
                $p.Range.ParagraphFormat.SpaceAfter = 6
                Set-Font $p.Range $HEI 14 $true
            }
            "h3" {
                $p = Add-Para $doc $word $text
                $p.Range.ParagraphFormat.CharacterUnitFirstLineIndent = 0
                $p.Range.ParagraphFormat.SpaceBefore = 8
                $p.Range.ParagraphFormat.SpaceAfter = 4
                Set-Font $p.Range $HEI 12 $true
            }
            "li" {
                $p = Add-Para $doc $word ("· " + $text)
                $p.Range.ParagraphFormat.CharacterUnitFirstLineIndent = 0
                $p.Range.ParagraphFormat.LeftIndent = $word.CentimetersToPoints(0.75)
                $p.Range.ParagraphFormat.SpaceAfter = 2
                $p.Range.ParagraphFormat.LineSpacingRule = 5
                $p.Range.ParagraphFormat.LineSpacing = $word.LinesToPoints(1.3)
                Set-Font $p.Range $KAI 14 $false
            }
            "table" {
                $rows = @($b.rows)
                # COM 只吃 System.Int32：JSON 反序列化出来的是 Int64，直接传会报
                # "Specified cast is not valid"，必须显式 [int]。
                $nRow = [int]$rows.Count
                $nCol = [int](@($rows[0]).Count)
                $anchor = Add-Para $doc $word ""
                $tbl = $doc.Tables.Add($anchor.Range, $nRow, $nCol)
                $tbl.Borders.InsideLineStyle = 1
                $tbl.Borders.OutsideLineStyle = 1
                $tbl.Range.ParagraphFormat.SpaceAfter = 1
                for ($r = 0; $r -lt $nRow; $r++) {
                    $row = $rows[$r]
                    for ($c = 0; $c -lt $nCol; $c++) {
                        $cell = $tbl.Cell([int]($r + 1), [int]($c + 1))
                        $cells = @($row)
                        $val = if ($c -lt $cells.Count) { [string]$cells[$c] } else { "" }
                        $cell.Range.Text = $val
                        Set-Font $cell.Range $SONG 10.5 ($r -eq 0)
                        $cell.Range.ParagraphFormat.Alignment = 0
                        if ($r -eq 0) { $cell.Shading.BackgroundPatternColor = 15921906 }
                    }
                }
                $nTable++
                $doc.Content.InsertParagraphAfter()
            }
            default {
                $p = Add-Para $doc $word $text
                $p.Range.ParagraphFormat.CharacterUnitFirstLineIndent = 2
                $p.Range.ParagraphFormat.SpaceAfter = 4
                $p.Range.ParagraphFormat.LineSpacingRule = 5
                $p.Range.ParagraphFormat.LineSpacing = $word.LinesToPoints(1.4)
                Set-Font $p.Range $KAI 14 $false
            }
        }
        } catch {
            Write-Output ("  [warn] block " + $idx + " type=" + $b.type + " line=" + $_.InvocationInfo.ScriptLineNumber + " -> " + $_.Exception.Message)
        }
    }

    $doc.SaveAs2($DocxPath, 16)
    $pages = $doc.ComputeStatistics(2)
    $chars = $doc.ComputeStatistics(3)
    Write-Output "docx: $DocxPath"
    Write-Output "tables: $nTable"
    Write-Output "pages: $pages"
    Write-Output "chars: $chars"

    if ($Pdf -ne "") {
        $Pdf = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Pdf))
        $doc.ExportAsFixedFormat($Pdf, 17)
        Write-Output "pdf: $Pdf"
    }
    $doc.Close($false)
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
exit 0
