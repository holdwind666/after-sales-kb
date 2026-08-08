param(
    [string]$Issue = "",
    [string]$ChineseLogic = "",
    [string]$JapaneseReply = "",
    [string]$Product = "",
    [string]$Result = "",
    [string]$ConfigPath = ""
)

# record_codex_feedback.ps1 - Lightweight feedback recorder used at the end of
# every answered after-sales query so the knowledge base grows with each Codex
# conversation, even when ChatGPT history learning is not enabled.
#
# ASCII-only file.

$ErrorActionPreference = "Stop"

function Resolve-Config {
    param([string]$Path)
    if ($Path -and (Test-Path -LiteralPath $Path)) { return (Resolve-Path -LiteralPath $Path).Path }
    if ($env:AFTERSALES_CACHE_DIR) {
        $cand = Join-Path $env:AFTERSALES_CACHE_DIR "chatgpt_learning.json"
        if (Test-Path -LiteralPath $cand) { return $cand }
    }
    $cwdCfg = Join-Path (Get-Location) "_售后模板缓存\chatgpt_learning.json"
    if (Test-Path -LiteralPath $cwdCfg) { return (Resolve-Path -LiteralPath $cwdCfg).Path }
    $skillCfg = Join-Path $PSScriptRoot "..\assets\bootstrap\chatgpt_learning.json"
    if (Test-Path -LiteralPath $skillCfg) { return (Resolve-Path -LiteralPath $skillCfg).Path }
    throw "chatgpt_learning.json not found; run setup_chatgpt_learning.ps1 first"
}

$ConfigPath = Resolve-Config -Path $ConfigPath
$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, (New-Object System.Text.UTF8Encoding($false)))
$Config = $ConfigText | ConvertFrom-Json
$FeedbackDir = $Config.feedback_dir
if (-not $FeedbackDir) { $FeedbackDir = Join-Path $Config.cloud_root "feedback" }
if (-not $FeedbackDir) {
    Write-Error "chatgpt_learning.json has no feedback_dir; run setup_chatgpt_learning.ps1 first."
    exit 1
}
New-Item -ItemType Directory -Path $FeedbackDir -Force | Out-Null

$Date = Get-Date -Format "yyyy-MM-dd"
$File = Join-Path $FeedbackDir ($Date + ".jsonl")

$Entry = @{
    date           = $Date
    source         = "codex_conversation"
    product        = $Product
    issue          = $Issue
    chinese_logic  = $ChineseLogic
    japanese_reply = $JapaneseReply
    result         = $Result
}

$Line = ($Entry | ConvertTo-Json -Compress -Depth 4)
$Utf8 = New-Object System.Text.UTF8Encoding($false)
if (-not (Test-Path -LiteralPath $File)) {
    [System.IO.File]::WriteAllText($File, $Line + "`r`n", $Utf8)
} else {
    [System.IO.File]::AppendAllText($File, $Line + "`r`n", $Utf8)
}

Write-Output "CODEX_FEEDBACK_SAVED"
Write-Output "FILE=$File"
