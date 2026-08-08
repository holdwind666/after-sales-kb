param(
    [string]$Product = "",
    [Parameter(Mandatory = $true)][string]$Q,
    [switch]$Diagnose,
    [string]$ConfigPath = ""
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "common.ps1")
if ($ConfigPath) { $env:AFTERSALES_CONFIG_PATH = $ConfigPath }
$config = Get-AfterSalesConfig
if (-not $config) {
    Write-Output "NOT_INITIALIZED"
    exit 2
}
$env:AFTERSALES_DATA_ROOT = [string]$config.data_root
$env:AFTERSALES_CACHE_DIR = [string]$config.cache_root

$argsList = @((Join-Path $PSScriptRoot "quick_query.py"), "--q", $Q)
if ($Product) { $argsList += @("--product", $Product) }
if ($Diagnose) { $argsList += "--diagnose" }
& (Join-Path $PSScriptRoot "py.ps1") @argsList
exit $LASTEXITCODE
