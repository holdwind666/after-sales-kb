param(
    [Parameter(Mandatory=$true)][string]$ListFile,
    [Parameter(Mandatory=$true)][string]$OutDir,
    [Parameter(Mandatory=$false)][string]$LogFile = "",
    [Parameter(Mandatory=$false)][switch]$ForceOcr
)

$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Resolve-PdfToPpm {
    $cmd = Get-Command pdftoppm.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $runtimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes"
    if (Test-Path -LiteralPath $runtimeRoot) {
        $found = Get-ChildItem -LiteralPath $runtimeRoot -Recurse -File -Filter pdftoppm.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($found) { return $found.FullName }
    }
    throw "pdftoppm.exe not found"
}
$script:PopplerPath = Resolve-PdfToPpm
$script:PyLauncher = Join-Path $PSScriptRoot "py.ps1"

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
    $poppler = $script:PopplerPath
    $py = $script:PyLauncher
    $tempDir = Join-Path $OutDir ("_tmp_" + [System.IO.Path]::GetFileNameWithoutExtension($PdfPath) + "_" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
    try {
        # Try text layer first (skip if ForceOcr). Exchange data through a
        # temp UTF-8 JSON file: NUL-delimited markers on native stdout get
        # mangled by PowerShell 5.1 encoding and corrupt the extracted text.
        $textLayer = @()
        if (-not $ForceOcr) {
            $env:PYTHONUTF8 = "1"
            $jsonPath = Join-Path $tempDir "textlayer.json"
            $pyScript = @'
import sys, json
try:
    import pdfplumber
    path = sys.argv[1]
    out = sys.argv[2]
    with pdfplumber.open(path) as pdf:
        pages = []
        for p in pdf.pages:
            pages.append(p.extract_text() or "")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(pages, f, ensure_ascii=False)
    print("TEXTLAYER_OK")
except Exception as e:
    print("TEXTLAYER_ERR: " + str(e))
'@
            $pyFile = Join-Path $tempDir "extract.py"
            [System.IO.File]::WriteAllText($pyFile, $pyScript, $utf8)
            & $py $pyFile $PdfPath $jsonPath 2>$null | Out-Null
            if ((Test-Path -LiteralPath $jsonPath) -and ((Get-Item -LiteralPath $jsonPath).Length -gt 0)) {
                try {
                    $textLayer = [System.IO.File]::ReadAllText($jsonPath, $utf8) | ConvertFrom-Json
                    if (-not $textLayer) { $textLayer = @() }
                } catch {
                    $textLayer = @()
                }
            }
        }
        # Render pages at 300 DPI so small table cells (e.g. spec sheets)
        # survive OCR; whole pages are scaled down only when oversized.
        Write-Output "DBG render: $pdf"
        & $poppler -png -r 300 $PdfPath (Join-Path $tempDir "page") 2>$null | Out-Null
        $pngs = @(Get-ChildItem -LiteralPath $tempDir -Filter "page-*.png" | Sort-Object Name)
        Write-Output "DBG pngs: $($pngs.Count)"
        if ($pngs.Count -eq 0) {
            return @{ Status = "render-fail"; Pages = 0 }
        }
        $pageCount = $pngs.Count
        $finalLines = @()
        $textPages = 0
        $ocrPageCount = 0
        for ($i = 0; $i -lt $pngs.Count; $i++) {
            $pageNo = $i + 1
            $finalLines += ("===== PAGE " + $pageNo + " =====")
            $tl = ""
            if ($i -lt $textLayer.Count) { $tl = [string]$textLayer[$i] }
            # A page whose embedded text layer is only a few characters is
            # usually a scanned artwork with stray text artifacts (e.g. a
            # spec table page containing just "1.8M / 1.2M"); OCR it too so
            # labels like 電源側コード長 are not lost.
            if ($tl.Trim().Length -ge 20) {
                $finalLines += $tl
                $textPages++
            } else {
                $imgPath = $pngs[$i].FullName
                $env:PYTHONUTF8 = "1"
                $scaleScript = @'
import sys
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
src = sys.argv[1]
out = sys.argv[2]
img = Image.open(src).convert("RGB")
w, h = img.size
scale = 6000.0 / max(w, h)
if scale < 1.0:
    img = img.resize((int(w * scale), int(h * scale)))
img.save(out)
'@
                $scaleFile = Join-Path $tempDir "scale.py"
                [System.IO.File]::WriteAllText($scaleFile, $scaleScript, $utf8)
                $ocrImg = Join-Path $tempDir ("page_ocr_" + $pageNo + ".png")
                & $py $scaleFile $imgPath $ocrImg 2>$null | Out-Null
                if (Test-Path -LiteralPath $ocrImg) {
                    $finalLines += (Ocr-Png $ocrImg)
                    $ocrPageCount++
                }
            }
        }
        [System.IO.File]::WriteAllText($OutTextPath, ($finalLines -join "`n"), $utf8)
        if ($ocrPageCount -eq 0) {
            return @{ Status = "text-layer"; Pages = $pageCount; TextPages = $textPages }
        }
        return @{ Status = "ocr"; Pages = $pageCount; OcrPages = $ocrPageCount; TextPages = $textPages }
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
        $line = "OK`t$($r.Status)`tpages=$($r.Pages)`tocr=$($r.OcrPages)`ttext=$($r.TextPages)`tsec=$([Math]::Round($sw.Elapsed.TotalSeconds,1))`t$pdf"
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
