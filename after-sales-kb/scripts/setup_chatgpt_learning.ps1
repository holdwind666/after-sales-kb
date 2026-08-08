param(
    [string]$CloudRoot = "",
    [string]$ConfigPath = ""
)

# setup_chatgpt_learning.ps1 - Create the ChatGPT learning library skeleton and
# write the per-machine chatgpt_learning.json (WPS cloud paths are machine
# specific and must NOT be baked into the synced bootstrap template).
# UTF-8 with BOM so PowerShell 5.1 reads the Chinese folder names correctly.

$ErrorActionPreference = "Stop"

function Find-WpsCloudRoot {
    $Profile = [Environment]::GetFolderPath('UserProfile')
    $Candidates = @()
    $DriveDir = Join-Path $Profile "WPSDrive"
    if (Test-Path -LiteralPath $DriveDir) {
        Get-ChildItem -LiteralPath $DriveDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $Cloud = Join-Path $_.FullName "WPS云盘"
            if (Test-Path -LiteralPath $Cloud) { $Candidates += $Cloud }
        }
    }
    $FilesDir = Join-Path $Profile "WPS Cloud Files"
    if (Test-Path -LiteralPath $FilesDir) {
        Get-ChildItem -LiteralPath $FilesDir -Directory -ErrorAction SilentlyContinue | ForEach-Object {
            $Cloud = Join-Path $_.FullName "漫游文档"
            if (Test-Path -LiteralPath $Cloud) { $Candidates += $Cloud }
        }
    }
    if ($Candidates.Count -eq 0) { return "" }
    return ($Candidates | Sort-Object { (Get-Item -LiteralPath $_).LastWriteTime } -Descending | Select-Object -First 1)
}

if (-not $CloudRoot) {
    $Discovered = Find-WpsCloudRoot
    if (-not $Discovered) {
        Write-Error "WPS cloud folder not found. Pass -CloudRoot explicitly."
        exit 1
    }
    $CloudRoot = Join-Path $Discovered "售后AI学习库"
}

$RawDir = Join-Path $CloudRoot "raw"
$CorpusDir = Join-Path $CloudRoot "corpus"
$FeedbackDir = Join-Path $CloudRoot "feedback"

foreach ($Dir in @($CloudRoot, $RawDir, $CorpusDir, $FeedbackDir)) {
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
}

if (-not $ConfigPath) {
    if ($env:AFTERSALES_CACHE_DIR) {
        $ConfigPath = Join-Path $env:AFTERSALES_CACHE_DIR "chatgpt_learning.json"
    } else {
        $ConfigPath = Join-Path (Get-Location) "_售后模板缓存\chatgpt_learning.json"
    }
}

$ConfigDir = Split-Path -Parent $ConfigPath
if (-not (Test-Path -LiteralPath $ConfigDir)) {
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
}

$Config = @{
    cloud_root        = $CloudRoot
    raw_dir           = $RawDir
    corpus_dir        = $CorpusDir
    feedback_dir      = $FeedbackDir
    session           = "chatgpt"
    max_conversations = 1000
    auto_update       = @{
        enabled   = $false
        frequency = "daily"
        time      = "08:00"
        last_run  = ""
    }
}
$ConfigJson = $Config | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($ConfigPath, $ConfigJson, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "SETUP_DONE"
Write-Output "CLOUD_ROOT=$CloudRoot"
Write-Output "CONFIG=$ConfigPath"
