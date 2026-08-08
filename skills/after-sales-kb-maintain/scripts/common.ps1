$ErrorActionPreference = "Stop"

function Get-AfterSalesSupportHome {
    if ($env:LOCALAPPDATA) {
        return (Join-Path $env:LOCALAPPDATA "AfterSalesSupport")
    }
    return (Join-Path $env:USERPROFILE ".after-sales-support")
}

function Get-AfterSalesConfigPath {
    if ($env:AFTERSALES_CONFIG_PATH) { return $env:AFTERSALES_CONFIG_PATH }
    return (Join-Path (Get-AfterSalesSupportHome) "config\settings.json")
}

function Get-AfterSalesConfig {
    param([string]$Path = (Get-AfterSalesConfigPath))
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-Content -LiteralPath $Path -Encoding UTF8 -Raw | ConvertFrom-Json)
}

function Test-AfterSalesDataRoot {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $false }
    $expected = @("说明书", "演示视频", "售后常用图片")
    $hits = 0
    foreach ($name in $expected) {
        if (Test-Path -LiteralPath (Join-Path $Path $name) -PathType Container) { $hits++ }
    }
    return ($hits -ge 2)
}

function Resolve-AfterSalesCacheRoot {
    param([object]$Config)
    if ($env:AFTERSALES_CACHE_DIR) { return $env:AFTERSALES_CACHE_DIR }
    if ($Config -and $Config.cache_root) { return [string]$Config.cache_root }
    return (Join-Path (Get-AfterSalesSupportHome) "cache")
}
