param(
    [Parameter(Mandatory=$true)][string]$ListFile,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [Parameter(Mandatory=$false)][string]$LogFile = "",
    [Parameter(Mandatory=$false)][switch]$ForceOcr
)

$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding($false)

# ---------- WinRT OCR helpers ----------
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Media, ContentType=WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime]

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    return $netTask.Result
}

$ocrLang = New-Object Windows.Globalization.Language 'ja'
$ocrEngine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($ocrLang)
if (-not $ocrEngine) {
    Write-Output "ERROR: Japanese OCR engine not available"
    exit 1
}

function Ocr-Png($PngPath) {
    $file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($PngPath)) ([Windows.Storage.StorageFile])
    $stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $bmp = [Windows.Graphics.Imaging.SoftwareBitmap]::Convert($bitmap, [Windows.Graphics.Imaging.BitmapPixelFormat]::Bgra8, [Windows.Graphics.Imaging.BitmapAlphaMode]::Ignore)
    $result = Await ($ocrEngine.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    $lines = @()
    foreach ($line in $result.Lines) { $lines += $line.Text }
    return ($lines -join "`n")
}

function Ocr-Pdf($PdfPath, $OutTextPath) {
    $poppler = "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
    $py = "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $tempDir = Join-Path $OutDir ("_tmp_" + [System.IO.Path]::GetFileNameWithoutExtension($PdfPath) + "_" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    try {
        # Try text layer first (skip if ForceOcr)
        $textParts = @()
        if (-not $ForceOcr) {
            $env:PYTHONUTF8 = "1"
            $pyScript = @'
import os, sys
try:
    import pdfplumber
    path = sys.argv[1]
    with pdfplumber.open(path) as pdf:
        pages = []
        for p in pdf.pages:
            t = p.extract_text() or ""
            pages.append(t)
    print("\x00PAGES\x00" + str(len(pages)))
    print("\x00TEXT\x00" + "\x00PAGEBREAK\x00".join(pages))
except Exception as e:
    print("\x00ERROR\x00" + str(e))
'@
            $pyFile = Join-Path $tempDir "extract.py"
            [System.IO.File]::WriteAllText($pyFile, $pyScript, $utf8)
            $pyOut = & $py $pyFile $PdfPath 2>$null | Out-String
            if ($pyOut -match "\x00PAGES\x00(\d+)") {
                $pageCount = [int]$Matches[1]
                if ($pyOut -match "\x00TEXT\x00(.*)") {
                    $allText = $Matches[1]
                    $segments = $allText -split "\x00PAGEBREAK\x00"
                    $nonEmpty = @($segments | Where-Object { $_.Trim().Length -gt 0 }).Count
                    if ($nonEmpty -ge $pageCount) {
                        # Full text layer available
                        [System.IO.File]::WriteAllText($OutTextPath, $allText, $utf8)
                        return @{ Status = "text-layer"; Pages = $pageCount }
                    }
                    if ($nonEmpty -gt 0) {
                        # Partial text layer: keep it and OCR only remaining pages (simplify: append OCR of all pages)
                        $textParts += $segments
                    }
                }
            }
        }
        if (-not $pageCount) { $pageCount = 1 }
        # Render pages
        Write-Output "DBG render: $pdf"
        & $poppler -png -r 200 $PdfPath (Join-Path $tempDir "page") 2>$null | Out-Null
        $pngs = @(Get-ChildItem -LiteralPath $tempDir -Filter "page-*.png" | Sort-Object Name)
        Write-Output "DBG pngs: $($pngs.Count)"
        if ($pngs.Count -eq 0) {
            return @{ Status = "render-fail"; Pages = $pageCount }
        }
        $ocrPages = @()
        foreach ($png in $pngs) {
            $imgPath = $png.FullName
            $env:PYTHONUTF8 = "1"
            $tileScript = @'
import sys, os
from PIL import Image
src = sys.argv[1]
outdir = sys.argv[2]
listfile = sys.argv[3]
img = Image.open(src).convert("RGB")
w, h = img.size
cols, rows = 3, 2
paths = []
for r in range(rows):
    for c in range(cols):
        x0 = w*c//cols; x1 = w*(c+1)//cols
        y0 = h*r//rows; y1 = h*(r+1)//rows
        t = img.crop((x0,y0,x1,y1))
        tp = os.path.join(outdir, f"tile_{r}{c}.png")
        t.save(tp)
        paths.append(tp)
with open(listfile, "w", encoding="utf-8") as f:
    f.write("\n".join(paths))
'@
            $tileFile = Join-Path $tempDir "tile.py"
            [System.IO.File]::WriteAllText($tileFile, $tileScript, $utf8)
            $tilesFile = Join-Path $tempDir "tiles.txt"
            & $py $tileFile $imgPath $tempDir $tilesFile 2>$null | Out-Null
            $tilePaths = @()
            if (Test-Path -LiteralPath $tilesFile) {
                $tilePaths = @([System.IO.File]::ReadAllLines($tilesFile, $utf8) | Where-Object { $_.Trim().Length -gt 0 })
            }
            $pageText = @()
            foreach ($tp in $tilePaths) {
                if (Test-Path -LiteralPath $tp) {
                    $pageText += (Ocr-Png $tp)
                }
            }
            $ocrPages += ("===== PAGE " + ($ocrPages.Count + 1) + " =====")
            $ocrPages += ($pageText -join "`n")
        }
        $finalText = if ($textParts.Count -gt 0) { ($textParts -join "`n") + "`n" + ($ocrPages -join "`n") } else { $ocrPages -join "`n" }
        [System.IO.File]::WriteAllText($OutTextPath, $finalText, $utf8)
        return @{ Status = "ocr"; Pages = $pageCount; Pngs = $pngs.Count }
    }
    finally {
        if (Test-Path -LiteralPath $tempDir) {
            Remove-Item -LiteralPath $tempDir -Recurse -Force -ErrorAction SilentlyContinue
        }
    }
}

# ---------- Main ----------
$list = [System.IO.File]::ReadAllLines($ListFile, $utf8) | Where-Object { $_.Trim().Length -gt 0 }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
if (-not $LogFile) { $LogFile = Join-Path $OutDir "ocr_worker_log.txt" }

$ok = 0; $fail = 0; $skip = 0
foreach ($pdf in $list) {
    if (-not (Test-Path -LiteralPath $pdf)) {
        [System.IO.File]::AppendAllText($LogFile, "MISSING`t$pdf`r`n", $utf8)
        $fail++
        continue
    }
    $baseName = [System.IO.Path]::GetFileNameWithoutExtension($pdf)
    $outText = Join-Path $OutDir ($baseName + ".txt")
    if (-not $ForceOcr -and (Test-Path -LiteralPath $outText) -and ((Get-Item -LiteralPath $outText).Length -gt 0)) {
        $skip++
        continue
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $r = Ocr-Pdf $pdf $outText
        $sw.Stop()
        $line = "OK`t$($r.Status)`tpages=$($r.Pages)`tsec=$([Math]::Round($sw.Elapsed.TotalSeconds,1))`t$pdf"
        [System.IO.File]::AppendAllText($LogFile, $line + "`r`n", $utf8)
        Write-Output $line
        $ok++
    }
    catch {
        $sw.Stop()
        $line = "ERR`t$($_.Exception.Message)`tsec=$([Math]::Round($sw.Elapsed.TotalSeconds,1))`t$pdf"
        [System.IO.File]::AppendAllText($LogFile, $line + "`r`n", $utf8)
        Write-Output $line
        $fail++
    }
}
Write-Output ("DONE ok=$ok fail=$fail skip=$skip")
