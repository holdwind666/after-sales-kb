param(
    [Parameter(Mandatory = $true)][string]$Product,
    [Parameter(Mandatory = $true)][string]$Issue,
    [Parameter(Mandatory = $true)][string]$JapaneseReply,
    [string]$ChineseLogic = "",
    [string]$Source = "codex_conversation",
    [string]$Channel = "amazon",
    [ValidateSet("normal", "high")][string]$Value = "normal"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "learning_common.ps1")
$config = Get-LearningConfig
$roots = @(Get-LearningRoots -Config $config)

function Remove-PersonalData {
    param([string]$Text)
    if (-not $Text) { return "" }
    $clean = $Text -replace '[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[email]'
    $clean = $clean -replace '(?<!\d)\d{10,}(?!\d)', '[number]'
    $clean = $clean -replace '(订单|注文)(号|番号)?\s*[:：]?\s*[A-Za-z0-9-]{6,}', '$1$2：[redacted]'
    return $clean.Trim()
}

$productSafe = Remove-PersonalData $Product
$issueSafe = Remove-PersonalData $Issue
$logicSafe = Remove-PersonalData $ChineseLogic
$replySafe = Remove-PersonalData $JapaneseReply
$fingerprint = Get-ContentFingerprint ("$productSafe`n$issueSafe`n$logicSafe`n$replySafe")
$candidate = [ordered]@{
    candidate_id = [guid]::NewGuid().ToString()
    event_id = [guid]::NewGuid().ToString()
    device_id = [string]$config.device_id
    device_name = [string]$config.device_name
    created_at = (Get-Date).ToString("o")
    product = $productSafe
    issue = $issueSafe
    chinese_logic = $logicSafe
    japanese_reply = $replySafe
    source = $Source
    channel = $Channel
    value = $Value
    fingerprint = $fingerprint
    status = "pending"
}
foreach ($root in $roots) {
    Add-JsonLine -Path (Join-Path $root "pending\$($config.device_id).jsonl") -Value $candidate
}
$lastPath = Join-Path (Get-SupportHome) "learning\last_candidate.json"
$candidate | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $lastPath -Encoding UTF8
Write-Output "CANDIDATE_CREATED=$($candidate.candidate_id)"
Write-Output "VALUE=$Value"
