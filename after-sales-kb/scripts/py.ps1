param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$PyArgs
)

# py.ps1 - Unified Python launcher for the after-sales KB.
# Always uses the Codex bundled Python runtime first, so the WindowsApps
# placeholder python.exe (silent failure: no output, exit code 1) is avoided.

$ErrorActionPreference = "Stop"

$Candidates = @(
    "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe",
    "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python3.exe"
)

$Py = $Candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

if (-not $Py) {
    $PyLauncher = "C:\Users\ASUS\AppData\Local\Programs\Python\Launcher\py.exe"
    if (Test-Path -LiteralPath $PyLauncher) {
        Write-Output "WARN: Codex bundled Python not found; falling back to py launcher"
        & $PyLauncher @PyArgs
        exit $LASTEXITCODE
    }
    Write-Error "No usable Python found (Codex runtime and py launcher both missing). Run check_environment.ps1 first."
    exit 1
}

& $Py @PyArgs
exit $LASTEXITCODE
