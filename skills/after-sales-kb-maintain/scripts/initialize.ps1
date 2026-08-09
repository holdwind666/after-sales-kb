param(
    [string]$DataRoot = "",
    [string]$WpsUrl = "",
    [string]$WpsLearningRoot = "",
    [string]$CacheRoot = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")

function Add-ValidCandidate {
    param([System.Collections.Generic.List[string]]$List, [string]$Path)
    if (-not $Path) { return }
    try { $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path } catch { return }
    if ((Test-AfterSalesDataRoot -Path $resolved) -and -not $List.Contains($resolved)) {
        $List.Add($resolved)
    }
}

function Find-DataRootCandidates {
    $items = [System.Collections.Generic.List[string]]::new()
    $cursor = (Get-Location).Path
    for ($i = 0; $i -lt 6 -and $cursor; $i++) {
        Add-ValidCandidate -List $items -Path $cursor
        $parent = Split-Path -Parent $cursor
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    if ($items.Count -gt 0) { return $items }

    foreach ($drive in (Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Root })) {
        $queue = [System.Collections.Generic.Queue[object]]::new()
        $queue.Enqueue([pscustomobject]@{ Path = $drive.Root; Depth = 0 })
        $visited = 0
        while ($queue.Count -gt 0 -and $visited -lt 2500) {
            $node = $queue.Dequeue()
            $visited++
            try {
                $children = Get-ChildItem -LiteralPath $node.Path -Directory -Force -ErrorAction Stop
            } catch { continue }
            foreach ($child in $children) {
                if ($child.Name -like "*说明书与视频*") {
                    Add-ValidCandidate -List $items -Path $child.FullName
                }
                if ($node.Depth -lt 2 -and -not ($child.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                    $queue.Enqueue([pscustomobject]@{ Path = $child.FullName; Depth = $node.Depth + 1 })
                }
            }
        }
    }
    return $items
}

$supportHome = Get-AfterSalesSupportHome
$configPath = Get-AfterSalesConfigPath
$configDir = Split-Path -Parent $configPath
New-Item -ItemType Directory -Path $configDir -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $supportHome "logs") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $supportHome "learning\pending") -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $supportHome "learning\events") -Force | Out-Null

$existing = Get-AfterSalesConfig -Path $configPath
if (-not $DataRoot -and $existing -and $existing.data_root -and (Test-AfterSalesDataRoot -Path $existing.data_root)) {
    $DataRoot = [string]$existing.data_root
}
if (-not $DataRoot) {
    $candidates = @(Find-DataRootCandidates)
    if ($candidates.Count -eq 1) {
        $DataRoot = $candidates[0]
    } elseif ($candidates.Count -gt 1) {
        Write-Output "NEED_DATA_ROOT_CHOICE"
        $candidates | ForEach-Object { Write-Output "CANDIDATE=$_" }
        exit 3
    } else {
        Write-Output "NEED_DATA_ROOT"
        exit 2
    }
}
if (-not (Test-AfterSalesDataRoot -Path $DataRoot)) {
    Write-Output "INVALID_DATA_ROOT=$DataRoot"
    exit 2
}
$DataRoot = (Resolve-Path -LiteralPath $DataRoot).Path

if (-not $CacheRoot) {
    if ($existing -and $existing.cache_root) {
        $CacheRoot = [string]$existing.cache_root
    } else {
        $legacyCache = Join-Path $DataRoot "_售后模板缓存"
        if (Test-Path -LiteralPath $legacyCache -PathType Container) {
            $CacheRoot = $legacyCache
        } else {
            $CacheRoot = Join-Path $supportHome "cache"
        }
    }
}
New-Item -ItemType Directory -Path $CacheRoot -Force | Out-Null
$CacheRoot = (Resolve-Path -LiteralPath $CacheRoot).Path

$deviceId = if ($existing -and $existing.device_id) { [string]$existing.device_id } else { [guid]::NewGuid().ToString() }
$deviceName = if ($existing -and $existing.device_name) { [string]$existing.device_name } else { [Environment]::MachineName }
$effectiveWpsUrl = if ($WpsUrl) { $WpsUrl } elseif ($existing -and $existing.wps_url) { [string]$existing.wps_url } else { "" }
$effectiveLearningRoot = if ($WpsLearningRoot) { $WpsLearningRoot } elseif ($existing -and $existing.cloud_learning_root) { [string]$existing.cloud_learning_root } else { "" }
$allowLegacyHistory = if ($existing -and $existing.learning -and $existing.learning.allow_legacy_history) { [bool]$existing.learning.allow_legacy_history } else { $false }

$settings = [ordered]@{
    schema_version = 2
    suite_version = "2.0.1"
    device_id = $deviceId
    device_name = $deviceName
    data_root = $DataRoot
    cache_root = $CacheRoot
    wps_url = $effectiveWpsUrl
    cloud_learning_root = $effectiveLearningRoot
    release_channel = "stable"
    last_initialized_at = (Get-Date).ToString("o")
    auto_update = [ordered]@{ enabled = $false; last_check = "" }
    learning = [ordered]@{ mode = "confirm_before_publish"; reminder_threshold = 10; allow_legacy_history = $allowLegacyHistory }
}
$settings | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $configPath -Encoding UTF8

$env:AFTERSALES_CONFIG_PATH = $configPath
$env:AFTERSALES_DATA_ROOT = $DataRoot
$env:AFTERSALES_CACHE_DIR = $CacheRoot

$quickMeta = Join-Path $CacheRoot "quick_index\meta.json"
Write-Output "INITIALIZED"
Write-Output "DEVICE_ID=$deviceId"
Write-Output "DATA_ROOT=$DataRoot"
Write-Output "CACHE_ROOT=$CacheRoot"
Write-Output "CONFIG_PATH=$configPath"
if (Test-Path -LiteralPath $quickMeta -PathType Leaf) {
    Write-Output "CACHE_STATUS=READY"
} else {
    Write-Output "CACHE_STATUS=BUILD_REQUIRED"
}
if ($effectiveLearningRoot -and (Test-Path -LiteralPath $effectiveLearningRoot -PathType Container)) {
    Write-Output "LEARNING_SYNC=READY"
} else {
    Write-Output "LEARNING_SYNC=LOCAL_ONLY"
}
exit 0
