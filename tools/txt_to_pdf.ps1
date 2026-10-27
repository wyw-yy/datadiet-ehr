# txt_to_pdf.ps1 —— 用 Word 把 .txt 排成 PDF（软著登记要交 PDF）
# 用法：
#   powershell -File tools\txt_to_pdf.ps1 -In ..\softcopyright\源程序.txt -Out ..\softcopyright\源程序.pdf -Font Consolas -Size 8
#
# 为什么用 Word 而不是 Python 库：本机已装 Word 16，能一次搞定 A4 版式、
# 页眉（软著要求页眉带软件名称与版本号）、页码与换页符；而 python-docx 没装、
# reportlab 也没装，临时装包反而慢。
param(
    [Parameter(Mandatory = $true)][string]$In,
    [Parameter(Mandatory = $true)][string]$Out,
    [string]$Header = "",
    [string]$Font = "宋体",
    [int]$Size = 9
)

$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    $doc = $word.Documents.Open($In, $false, $true)

    # A4 + 2 cm 页边距（7 = wdPaperA4）
    $ps = $doc.PageSetup
    $ps.PaperSize = 7
    $ps.TopMargin = 56.7; $ps.BottomMargin = 56.7
    $ps.LeftMargin = 56.7; $ps.RightMargin = 56.7

    # 全文统一字体与字号。
    # 行距必须用"固定值"：软著要求每页不少于 50 行，而 Word 的"单倍行距"对中文
    # 字体太松（8 pt 实测只有 44 行/页）。固定成 字号+2 磅后能稳到 60 行以上。
    $doc.Content.Font.Name = $Font
    $doc.Content.Font.NameFarEast = $Font
    $doc.Content.Font.Size = $Size
    $doc.Content.ParagraphFormat.LineSpacingRule = 4      # 4 = wdLineSpaceExactly
    $doc.Content.ParagraphFormat.LineSpacing = $Size + 2
    $doc.Content.ParagraphFormat.SpaceBefore = 0
    $doc.Content.ParagraphFormat.SpaceAfter = 0

    if ($Header -ne "") {
        $hdr = $doc.Sections.Item(1).Headers.Item(1)
        $hdr.LinkToPrevious = $false
        $hdr.Range.Text = $Header
        $hdr.Range.Font.Name = "宋体"
        $hdr.Range.Font.Size = 8
        $hdr.Range.ParagraphFormat.Alignment = 1          # 居中
    }

    $doc.ExportAsFixedFormat($Out, 17)                     # 17 = wdExportFormatPDF
    $pages = $doc.ComputeStatistics(2)                     # 2 = wdStatisticPages
    Write-Output "OK  $Out  ($pages 页)"
}
finally {
    if ($doc) { $doc.Close($false) }
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
