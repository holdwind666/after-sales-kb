param(
    [Parameter(Mandatory=$true)][string]$ListFile,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [Parameter(Mandatory=$true)][string]$RootDir,
    [Parameter(Mandatory=$false)][string]$LogFile = ""
)

$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
if (-not $LogFile) { $LogFile = Join-Path $OutDir "_build_log.txt" }

$poppler = "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
$list = [System.IO.File]::ReadAllLines($ListFile, $utf8) | Where-Object { $_.Trim().Length -gt 0 }

$ok = 0; $skip = 0; $fail = 0
foreach ($pdf in $list) {
    if (-not (Test-Path -LiteralPath $pdf)) {
        [System.IO.File]::AppendAllText($LogFile, "MISSING`t$pdf`r`n", $utf8)
        $fail++
        continue
    }
    # Mirror source relative path under OutDir (PS 5.1 compatible)
    $rel = $pdf
    if ($pdf.StartsWith($RootDir, [System.StringComparison]::OrdinalIgnoreCase)) {
        $rel = $pdf.Substring($RootDir.Length).TrimStart('\', '/')
    }
    $relDir = [System.IO.Path]::GetDirectoryName($rel)
    if ([string]::IsNullOrEmpty($relDir)) { $relDir = "" }
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($pdf)
    $targetDir = Join-Path $OutDir $relDir
    New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
    $prefix = Join-Path $targetDir ($baseName + "_p")
    $firstPage = $prefix + "-1.jpg"
    if ((Test-Path -LiteralPath $firstPage) -and ((Get-Item -LiteralPath $firstPage).Length -gt 0)) {
        $skip++
        continue
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        & $poppler -jpeg -r 150 $pdf $prefix 2>$null | Out-Null
        $sw.Stop()
        $pages = @(Get-ChildItem -LiteralPath $targetDir -Filter ($baseName + "_p-*.jpg") | Measure-Object).Count
        if ($pages -eq 0) {
            $line = "FAIL`trender-empty`tsec=$([Math]::Round($sw.Elapsed.TotalSeconds,1))`t$pdf"
            [System.IO.File]::AppendAllText($LogFile, $line + "`r`n", $utf8)
            Write-Output $line
            $fail++
        } else {
            $line = "OK`tpages=$pages`tsec=$([Math]::Round($sw.Elapsed.TotalSeconds,1))`t$pdf"
            [System.IO.File]::AppendAllText($LogFile, $line + "`r`n", $utf8)
            Write-Output $line
            $ok++
        }
    }
    catch {
        $sw.Stop()
        $line = "ERR`t$($_.Exception.Message)`tsec=$([Math]::Round($sw.Elapsed.TotalSeconds,1))`t$pdf"
        [System.IO.File]::AppendAllText($LogFile, $line + "`r`n", $utf8)
        Write-Output $line
        $fail++
    }
}
Write-Output "DONE ok=$ok skip=$skip fail=$fail"
