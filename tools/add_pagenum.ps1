param([string[]]$Docx)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
foreach ($d in $Docx) {
  $doc = $word.Documents.Open($d, $false, $false)
  foreach ($sec in $doc.Sections) {
    $ftr = $sec.Footers.Item(1)
    $ftr.Range.Text = ""
    $ftr.Range.ParagraphFormat.Alignment = 1
    $ftr.Range.Font.Size = 9
    $ftr.Range.Font.Name = "Times New Roman"
    $fld = $ftr.Range.Fields.Add($ftr.Range, 33, "", $true)
    [void]$fld.Update()
  }
  $doc.Fields.Update()
  $doc.Save()
  $doc.Close($false)
  Write-Output ("pagenum ok: " + $d)
}
$word.Quit()
