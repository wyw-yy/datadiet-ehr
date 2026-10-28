# html_to_docx.ps1 —— 用 Word COM 把 HTML 打开、另存为 docx 并导出 PDF。
# 依赖：本机装有 Word（16.x）。注意本文件必须保存为 UTF-8 带 BOM，否则 PS 按 GBK 解析中文会报错。
# 用法：powershell -ExecutionPolicy Bypass -File tools\html_to_docx.ps1 -In a.html -Docx a.docx -Pdf a.pdf

param(
    [Parameter(Mandatory = $true)][string]$In,
    [Parameter(Mandatory = $true)][string]$Docx,
    [string]$Pdf = ""
)

$ErrorActionPreference = "Stop"
$In = (Resolve-Path $In).Path
$Docx = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Docx))

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    # Format 8 = wdOpenFormatWebPages，让 Word 按 HTML 解析并套用 CSS 字体
    $doc = $word.Documents.Open($In, $false, $true, $false, "", "", $false, "", "", 8, 65001, $false, $false, $false)

    foreach ($sec in $doc.Sections) {
        $ps = $sec.PageSetup
        $ps.PageWidth = $word.CentimetersToPoints(21.0)
        $ps.PageHeight = $word.CentimetersToPoints(29.7)
        $ps.TopMargin = $word.CentimetersToPoints(2.54)
        $ps.BottomMargin = $word.CentimetersToPoints(2.54)
        $ps.LeftMargin = $word.CentimetersToPoints(3.0)
        $ps.RightMargin = $word.CentimetersToPoints(3.0)
    }

    # 页脚页码
    $footer = $doc.Sections.Item(1).Footers.Item(1)
    $footer.Range.ParagraphFormat.Alignment = 1
    $footer.Range.Fields.Add($footer.Range, 33) | Out-Null   # 33 = wdFieldPage

    # 16 = wdFormatXMLDocument
    $doc.SaveAs2($Docx, 16)
    $pages = $doc.ComputeStatistics(2)
    $words = $doc.ComputeStatistics(0)
    Write-Output "docx: $Docx"
    Write-Output "pages: $pages"
    Write-Output "words: $words"

    if ($Pdf -ne "") {
        $Pdf = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Pdf))
        $doc.ExportAsFixedFormat($Pdf, 17)   # 17 = wdExportFormatPDF
        Write-Output "pdf: $Pdf"
    }
    $doc.Close($false)
}
finally {
    $word.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
}
