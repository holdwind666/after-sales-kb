param(
    [string]$ConfigPath = "",
    [string]$Time = "08:00",
    [string]$Frequency = "daily",
    [switch]$Enable
)

# register_chatgpt_learning_task.ps1 - Register a Windows scheduled task that
# runs the ChatGPT learning pipeline on a schedule (default: daily 08:00).
#
# ASCII-only file.

$ErrorActionPreference = "Stop"

function Resolve-Config {
    param([string]$Path)
    if ($Path -and (Test-Path -LiteralPath $Path)) { return (Resolve-Path -LiteralPath $Path).Path }
    $cwdCfg = Join-Path (Get-Location) "_售后模板缓存\chatgpt_learning.json"
    if (Test-Path -LiteralPath $cwdCfg) { return (Resolve-Path -LiteralPath $cwdCfg).Path }
    $skillCfg = Join-Path $PSScriptRoot "..\assets\bootstrap\chatgpt_learning.json"
    if (Test-Path -LiteralPath $skillCfg) { return (Resolve-Path -LiteralPath $skillCfg).Path }
    throw "chatgpt_learning.json not found"
}

$ConfigPath = Resolve-Config -Path $ConfigPath
$RunScript = Join-Path $PSScriptRoot "run_chatgpt_learning.ps1"
if (-not (Test-Path -LiteralPath $RunScript)) {
    Write-Error "Missing: $RunScript"
    exit 1
}

$TaskName = "AfterSalesChatGPTLearning"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-ExecutionPolicy Bypass -File `"$RunScript`" -ConfigPath `"$ConfigPath`""

if ($Frequency -eq "weekly") {
    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $Time
} else {
    $Trigger = New-ScheduledTaskTrigger -Daily -At $Time
}

$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew

try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Force -ErrorAction Stop | Out-Null
    if (-not $Enable) {
        Disable-ScheduledTask -TaskName $TaskName -ErrorAction Stop | Out-Null
    }
    Write-Output "TASK_REGISTERED"
    Write-Output "TASK=$TaskName"
    Write-Output "FREQUENCY=$Frequency"
    Write-Output "TIME=$Time"
    if ($Enable) { Write-Output "ENABLED=yes" } else { Write-Output "ENABLED=no (run Enable-ScheduledTask to turn on)" }
} catch {
    Write-Output "TASK_REGISTER_FAILED"
    Write-Output $_.Exception.Message
    exit 1
}
