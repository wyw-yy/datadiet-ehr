
param([string]$Out)
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $word.Documents.Add()
$doc.PageSetup.TopMargin = $word.CentimetersToPoints(2.8)
$doc.PageSetup.BottomMargin = $word.CentimetersToPoints(2.4)
$doc.PageSetup.LeftMargin = $word.CentimetersToPoints(3.0)
$doc.PageSetup.RightMargin = $word.CentimetersToPoints(3.0)

$sel = $word.Selection

function Add-Line([string]$text, [double]$size, [string]$font, [bool]$bold, [double]$before, [double]$after, [double]$space) {
  $sel.ParagraphFormat.Alignment = 1
  $sel.ParagraphFormat.SpaceBefore = $before
  $sel.ParagraphFormat.SpaceAfter = $after
  $sel.ParagraphFormat.LineSpacingRule = 5
  $sel.ParagraphFormat.LineSpacing = $space
  $sel.Font.Name = $font
  $sel.Font.NameFarEast = $font
  $sel.Font.Size = $size
  $sel.Font.Bold = $bold
  $sel.TypeText($text)
  $sel.TypeParagraph()
}

Add-Line '皖江工学院' 30 '黑体' $true 0 8 38
Add-Line '第五届“挑战杯”大学生课外学术科技作品竞赛' 15 '宋体' $false 0 6 24
Add-Line '作 品 申 报 材 料' 24 '黑体' $true 24 14 40
Add-Line '作品名称' 12 '楷体' $false 10 4 22
Add-Line 'DataDiet-EHR' 20 '黑体' $true 0 2 30
Add-Line '面向临床语言模型的可复现训练子集选择与等效性评估软件' 14 '黑体' $true 0 14 24
Add-Line '作品类别：科技发明制作 B 类' 14 '宋体' $false 6 4 24
Add-Line '学科类别：B 信息技术' 14 '宋体' $false 0 14 24
Add-Line '申 报 者：杨　宇' 14 '宋体' $false 0 6 26
Add-Line '学　　号：＿＿＿＿＿＿＿＿＿＿＿' 14 '宋体' $false 0 6 26
Add-Line '所在学院：＿＿＿＿＿＿＿＿＿＿＿（学院盖章）' 14 '宋体' $false 0 6 26
Add-Line '指导教师：＿＿＿＿＿＿＿＿＿＿＿' 14 '宋体' $false 0 6 26
Add-Line '推 荐 人：＿＿＿＿＿＿＿　　＿＿＿＿＿＿＿' 14 '宋体' $false 0 30 26
Add-Line '2026 年 11 月' 15 '宋体' $false 14 0 26

$doc.SaveAs2($Out, 16)
$pages = $doc.ComputeStatistics(2)
$doc.Close($false)
$word.Quit()
Write-Output ("pages=" + $pages)
