param([string]$ConfigPath = "")

$ErrorActionPreference = "Continue"
. (Join-Path $PSScriptRoot "common.ps1")
if ($ConfigPath) { $env:AFTERSALES_CONFIG_PATH = $ConfigPath }
$config = Get-AfterSalesConfig
if (-not $config) { Write-Output "NOT_INITIALIZED"; exit 2 }

$failed = 0
Write-Output "CONFIG=$((Get-AfterSalesConfigPath))"
if (Test-AfterSalesDataRoot -Path ([string]$config.data_root)) {
    Write-Output "DATA_ROOT=OK"
} else { Write-Output "DATA_ROOT=INVALID"; $failed++ }

$cache = [string]$config.cache_root
if (Test-Path -LiteralPath $cache -PathType Container) { Write-Output "CACHE_ROOT=OK" } else { Write-Output "CACHE_ROOT=MISSING"; $failed++ }
if (Test-Path -LiteralPath (Join-Path $cache "quick_index\meta.json") -PathType Leaf) {
    Write-Output "QUICK_INDEX=READY"
} else { Write-Output "QUICK_INDEX=BUILD_REQUIRED"; $failed++ }

$pyOut = & (Join-Path $PSScriptRoot "py.ps1") -c "import sys; print(sys.version_info.major)" 2>$null
if ($LASTEXITCODE -eq 0 -and $pyOut -match "3") { Write-Output "PYTHON=OK" } else { Write-Output "PYTHON=MISSING"; $failed++ }

$pdftoppm = Get-Command pdftoppm.exe -ErrorAction SilentlyContinue
if (-not $pdftoppm) {
    $runtimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes"
    if (Test-Path -LiteralPath $runtimeRoot) {
        $pdftoppm = Get-ChildItem -LiteralPath $runtimeRoot -Recurse -File -Filter pdftoppm.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    }
}
Write-Output "PDF_RENDERER=$(if ($pdftoppm) { 'OK' } else { 'OPTIONAL_MISSING' })"
Write-Output "WPS_LINK=$(if ($config.wps_url) { 'CONFIGURED' } else { 'NOT_CONFIGURED' })"
Write-Output "LEARNING_SYNC=$(if ($config.cloud_learning_root -and (Test-Path -LiteralPath $config.cloud_learning_root)) { 'READY' } else { 'LOCAL_ONLY' })"

if ($failed -eq 0) { Write-Output "ENVIRONMENT_OK"; exit 0 }
Write-Output "ENVIRONMENT_NEEDS_ATTENTION=$failed"
exit 1
