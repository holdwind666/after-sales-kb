param(
    [string]$ConfigPath = "",
    [int]$PageLimit = 50,
    [int]$MaxConversations = 1000,
    [int]$MaxItems = 0,
    [int]$WaitLoginMinutes = 10,
    [int]$TimeBudgetSeconds = 0,
    [switch]$WorkOnly,
    [switch]$Force,
    [switch]$NoBrowser
)

# run_chatgpt_learning.ps1 - One-shot ChatGPT history learning pipeline:
#   1) capture new conversations (login-checked persistent browser)
#   2) build corpus (work filter + template pairs + persona)
#   3) print summary
#
# ASCII-only file.

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
}

$Capture = Join-Path $ScriptDir "capture_chatgpt_conversations.ps1"
$Build = Join-Path $ScriptDir "build_chatgpt_corpus.py"
$Py = Join-Path $ScriptDir "py.ps1"
$Setup = Join-Path $ScriptDir "setup_chatgpt_learning.ps1"

if (-not $ConfigPath) {
    $mainConfig = Join-Path $env:LOCALAPPDATA "AfterSalesSupport\config\settings.json"
    if (Test-Path -LiteralPath $mainConfig -PathType Leaf) {
        $main = Get-Content -LiteralPath $mainConfig -Encoding UTF8 -Raw | ConvertFrom-Json
        if ($main.cache_root) { $ConfigPath = Join-Path ([string]$main.cache_root) "chatgpt_learning.json" }
    }
}

foreach ($Needed in @($Capture, $Build, $Py)) {
    if (-not (Test-Path -LiteralPath $Needed)) {
        Write-Error "Missing: $Needed"
        exit 1
    }
}

# First install convenience: if the local config is missing, run setup
# automatically so the user never has to call setup_chatgpt_learning.ps1.
if (-not $ConfigPath -or -not (Test-Path -LiteralPath $ConfigPath)) {
    if (-not (Test-Path -LiteralPath $Setup)) {
        Write-Error "Missing: $Setup"
        exit 1
    }
    Write-Output "CONFIG_MISSING_RUNNING_SETUP"
    & $Setup -ConfigPath $ConfigPath
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Write-Error "setup_chatgpt_learning.ps1 failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }
    if (-not $ConfigPath) { throw "setup completed without a config path" }
}
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    Write-Error "Config still missing after setup: $ConfigPath"
    exit 1
}

$CaptureArgs = @{
    ConfigPath       = $ConfigPath
    PageLimit        = $PageLimit
    MaxConversations = $MaxConversations
    MaxItems         = $MaxItems
    WaitLoginMinutes = $WaitLoginMinutes
    TimeBudgetSeconds = $TimeBudgetSeconds
}
if ($WorkOnly) { $CaptureArgs.WorkOnly = $true }
if ($Force) { $CaptureArgs.Force = $true }
if ($NoBrowser) { $CaptureArgs.NoBrowser = $true }

& $Capture @CaptureArgs
if ($LASTEXITCODE -eq 2) {
    Write-Output "LEARNING_SKIPPED_LOGIN_REQUIRED"
    exit 2
}
if ($LASTEXITCODE -ne 0) {
    Write-Error "Capture failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

$BuildArgs = @()
if ($ConfigPath) { $BuildArgs += "--config"; $BuildArgs += $ConfigPath }
& $Py $Build @BuildArgs
exit $LASTEXITCODE
