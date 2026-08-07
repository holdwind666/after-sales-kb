param(
    [string]$Product = "",
    [string]$Q = "",
    [switch]$Diagnose
)

# quick_query.ps1 - Daily quick-query entry point (uses the Codex bundled Python
# through py.ps1 so the WindowsApps placeholder python.exe is never called).

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$PyLauncher = Join-Path $ScriptDir "py.ps1"
if (-not (Test-Path -LiteralPath $PyLauncher)) {
    Write-Error "Missing py.ps1 launcher; please make sure the scripts folder is complete."
    exit 1
}

$ArgsList = @()
if ($Product) {
    $ArgsList += "--product"
    $ArgsList += $Product
}
if ($Q) {
    $ArgsList += "--q"
    $ArgsList += $Q
}
if ($Diagnose) {
    $ArgsList += "--diagnose"
}

$ScriptPath = Join-Path $ScriptDir "quick_query.py"
if (-not (Test-Path -LiteralPath $ScriptPath)) {
    Write-Error "Missing quick_query.py: $ScriptPath"
    exit 1
}

& $PyLauncher $ScriptPath @ArgsList
exit $LASTEXITCODE
