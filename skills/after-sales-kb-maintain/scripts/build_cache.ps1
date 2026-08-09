param(
    [ValidateSet("Auto", "Full", "Refresh")][string]$Mode = "Auto",
    [string]$ConfigPath = "",
    [switch]$Force,
    [switch]$SkipPdfPages
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
if ($ConfigPath) { $env:AFTERSALES_CONFIG_PATH = $ConfigPath }
$config = Get-AfterSalesConfig
if (-not $config) { Write-Output "NOT_INITIALIZED"; exit 2 }

$dataRoot = [string]$config.data_root
$cacheRoot = [string]$config.cache_root
if (-not (Test-AfterSalesDataRoot -Path $dataRoot)) {
    Write-Output "INVALID_DATA_ROOT=$dataRoot"
    exit 2
}
New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
$env:AFTERSALES_DATA_ROOT = $dataRoot
$env:AFTERSALES_CACHE_DIR = $cacheRoot

$quickMeta = Join-Path $cacheRoot "quick_index\meta.json"
if ($Mode -eq "Auto") {
    $Mode = if ((Test-Path -LiteralPath $quickMeta) -and -not $Force) { "Refresh" } else { "Full" }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$stateDir = Join-Path $cacheRoot "build_state"
$logDir = Join-Path $cacheRoot "logs"
$statePath = Join-Path $stateDir "last_build.json"
$logPath = Join-Path $logDir ("build-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
foreach ($dir in @($stateDir, $logDir, (Join-Path $cacheRoot "kdocs"), (Join-Path $cacheRoot "faq"), (Join-Path $cacheRoot "pdf_ocr"), (Join-Path $cacheRoot "pdf_pages"), (Join-Path $cacheRoot "video_index"))) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

$script:Completed = [System.Collections.Generic.List[string]]::new()
$script:CurrentStage = "start"
function Write-BuildState {
    param([string]$Status, [string]$Message = "")
    $payload = [ordered]@{
        suite_version = "2.0.1"
        mode = $Mode
        status = $Status
        current_stage = $script:CurrentStage
        completed_stages = @($script:Completed)
        message = $Message
        data_root = $dataRoot
        cache_root = $cacheRoot
        updated_at = (Get-Date).ToString("o")
    }
    [IO.File]::WriteAllText($statePath, ($payload | ConvertTo-Json -Depth 6), $utf8)
}
function Add-Log {
    param([string]$Line)
    $rendered = "$(Get-Date -Format o)`t$Line"
    [IO.File]::AppendAllText($logPath, $rendered + "`r`n", $utf8)
    Write-Output $Line
}
function Invoke-Stage {
    param([string]$Name, [scriptblock]$Action)
    $script:CurrentStage = $Name
    Write-BuildState -Status "running"
    Add-Log "STAGE_START=$Name"
    & $Action
    $script:Completed.Add($Name)
    Add-Log "STAGE_OK=$Name"
    Write-BuildState -Status "running"
}
function Invoke-Python {
    param([string]$Name, [string[]]$Arguments = @())
    $scriptPath = Join-Path $PSScriptRoot $Name
    & (Join-Path $PSScriptRoot "py.ps1") $scriptPath @Arguments 2>&1 | ForEach-Object { Add-Log ([string]$_) }
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}

try {
    Add-Log "BUILD_MODE=$Mode"
    Add-Log "DATA_ROOT=$dataRoot"
    Add-Log "CACHE_ROOT=$cacheRoot"

    Invoke-Stage "source-discovery" {
        $kdocsDir = Join-Path $cacheRoot "kdocs"
        $textSources = @(Get-ChildItem -LiteralPath $dataRoot -Recurse -File -Filter "kdocs_*.txt" -ErrorAction SilentlyContinue | Where-Object { -not $_.FullName.StartsWith($cacheRoot, [StringComparison]::OrdinalIgnoreCase) })
        foreach ($source in $textSources) {
            $destination = Join-Path $kdocsDir $source.Name
            if ($Force -or -not (Test-Path -LiteralPath $destination)) {
                Copy-Item -LiteralPath $source.FullName -Destination $destination -Force
            }
        }

        $workbooks = @(Get-ChildItem -LiteralPath $dataRoot -Recurse -File -Filter "*.xlsx" -ErrorAction SilentlyContinue | Where-Object {
            $_.Name -match "售后.*(方案|对应)|日本站售后" -and -not $_.FullName.StartsWith($cacheRoot, [StringComparison]::OrdinalIgnoreCase)
        })
        foreach ($workbook in $workbooks) {
            $args = @("--source", $workbook.FullName, "--out", $kdocsDir)
            if ($Force) { $args += "--force" }
            Invoke-Python -Name "import_wps_xlsx.py" -Arguments $args
        }
        Add-Log "WPS_TEXT_FILES=$(@(Get-ChildItem -LiteralPath $kdocsDir -File -Filter '*.txt').Count)"
    }

    Invoke-Stage "video-index" {
        $videoRoot = Join-Path $dataRoot "演示视频"
        $rows = [System.Collections.Generic.List[string]]::new()
        if (Test-Path -LiteralPath $videoRoot) {
            Get-ChildItem -LiteralPath $videoRoot -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension.ToLowerInvariant() -in @('.mp4', '.mov', '.avi', '.mkv', '.webm') } | ForEach-Object {
                $rows.Add(($_.FullName + "`t" + $_.Length + "`t" + $_.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss")))
            }
        }
        [IO.File]::WriteAllLines((Join-Path $cacheRoot "video_index\videos.tsv"), $rows, $utf8)
        Add-Log "VIDEO_FILES=$($rows.Count)"
    }

    if ($Mode -eq "Full") {
        Invoke-Stage "manual-text" {
            $manualRoot = Join-Path $dataRoot "说明书"
            $ocrDir = Join-Path $cacheRoot "pdf_ocr"
            $allPdfs = @(Get-ChildItem -LiteralPath $manualRoot -Recurse -File -Filter "*.pdf" -ErrorAction SilentlyContinue)
            $selected = @($allPdfs | Group-Object BaseName | ForEach-Object { $_.Group | Sort-Object Length, LastWriteTime -Descending | Select-Object -First 1 })
            $duplicateCount = $allPdfs.Count - $selected.Count
            if ($duplicateCount -gt 0) { Add-Log "PDF_DUPLICATE_BASENAMES_SKIPPED=$duplicateCount" }
            $missing = @($selected | Where-Object { $Force -or -not (Test-Path -LiteralPath (Join-Path $ocrDir ($_.BaseName + '.txt'))) } | Select-Object -ExpandProperty FullName)
            Add-Log "PDF_FILES=$($allPdfs.Count)"
            Add-Log "PDF_TEXT_PENDING=$($missing.Count)"
            if ($missing.Count -gt 0) {
                $listFile = Join-Path $stateDir "pdf_text_pending.txt"
                [IO.File]::WriteAllLines($listFile, $missing, $utf8)
                $ocrOutput = & (Join-Path $PSScriptRoot "ocr_worker.ps1") -ListFile $listFile -OutDir $ocrDir -LogFile (Join-Path $logDir "ocr_worker.log") -ForceOcr:$Force 2>&1
                $ocrOutput | ForEach-Object { Add-Log ([string]$_) }
                $doneLine = $ocrOutput | Where-Object { [string]$_ -match '^DONE ok=\d+ fail=(\d+)' } | Select-Object -Last 1
                if (-not $doneLine -or [int]([regex]::Match([string]$doneLine, 'fail=(\d+)').Groups[1].Value) -gt 0) { throw "Manual text extraction did not finish cleanly" }
            }
        }

        if (-not $SkipPdfPages) {
            Invoke-Stage "manual-pages" {
                $manualRoot = Join-Path $dataRoot "说明书"
                $allPdfs = @(Get-ChildItem -LiteralPath $manualRoot -Recurse -File -Filter "*.pdf" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName)
                if ($allPdfs.Count -gt 0) {
                    $listFile = Join-Path $stateDir "pdf_pages_all.txt"
                    [IO.File]::WriteAllLines($listFile, $allPdfs, $utf8)
                    $pageOutput = & (Join-Path $PSScriptRoot "build_pdf_pages.ps1") -ListFile $listFile -OutDir (Join-Path $cacheRoot "pdf_pages") -RootDir $manualRoot -LogFile (Join-Path $logDir "pdf_pages.log") 2>&1
                    $pageOutput | ForEach-Object { Add-Log ([string]$_) }
                    $doneLine = $pageOutput | Where-Object { [string]$_ -match '^DONE ok=\d+ skip=\d+ fail=(\d+)' } | Select-Object -Last 1
                    if (-not $doneLine -or [int]([regex]::Match([string]$doneLine, 'fail=(\d+)').Groups[1].Value) -gt 0) { throw "PDF page rendering did not finish cleanly" }
                }
            }
        }
    }

    Invoke-Stage "derived-indexes" {
        Invoke-Python -Name "build_faq_index.py"
        Invoke-Python -Name "build_manual_images.py"
        Invoke-Python -Name "build_products.py"
        Invoke-Python -Name "build_facts.py"
    }
    Invoke-Stage "quick-index" {
        Invoke-Python -Name "build_quick_index.py"
        Invoke-Python -Name "build_faq_lookup.py"
        Invoke-Python -Name "build_kb_graph.py"
        Invoke-Python -Name "build_gap_report.py"
    }

    $meta = Get-Content -LiteralPath $quickMeta -Encoding UTF8 -Raw | ConvertFrom-Json
    $sourceCount = [int]$meta.counts.faq + [int]$meta.counts.ocr_pages + [int]$meta.counts.kdocs + [int]$meta.counts.spec
    if ($sourceCount -lt 1) { throw "The index contains no searchable source rows" }
    $script:CurrentStage = "complete"
    Write-BuildState -Status "complete"
    Add-Log "SEARCHABLE_ROWS=$sourceCount"
    Add-Log "WPS_CACHE=$(if ([int]$meta.counts.kdocs -gt 0) { 'READY' } else { 'NOT_AVAILABLE' })"
    Add-Log "CACHE_BUILD_COMPLETE"
    exit 0
} catch {
    $message = $_.Exception.Message
    Write-BuildState -Status "failed" -Message $message
    Add-Log "BUILD_FAILED_STAGE=$script:CurrentStage"
    Add-Log "BUILD_ERROR=$message"
    Add-Log "RESUME_COMMAND=& '$PSCommandPath' -Mode $Mode"
    exit 1
}
