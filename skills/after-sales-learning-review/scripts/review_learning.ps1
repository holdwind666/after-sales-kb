param(
    [ValidateSet("List", "Approve", "Reject", "Revoke")][string]$Action = "List",
    [string[]]$CandidateId = @(),
    [string]$Reason = "",
    [int]$Limit = 10
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "learning_common.ps1")
$config = Get-LearningConfig
$roots = @(Get-LearningRoots -Config $config)
$candidateMap = @{}
$eventMap = @{}
foreach ($root in $roots) {
    foreach ($item in @(Read-JsonLines -Directory (Join-Path $root "pending"))) {
        if ($item.candidate_id -and -not $candidateMap.ContainsKey([string]$item.candidate_id)) { $candidateMap[[string]$item.candidate_id] = $item }
    }
    foreach ($event in @(Read-JsonLines -Directory (Join-Path $root "events"))) {
        if (-not $event.candidate_id) { continue }
        $key = [string]$event.candidate_id
        if (-not $eventMap.ContainsKey($key) -or ([datetime]$event.created_at -gt [datetime]$eventMap[$key].created_at)) { $eventMap[$key] = $event }
    }
}

if ($Action -eq "List") {
    $pending = @($candidateMap.Values | Where-Object { -not $eventMap.ContainsKey([string]$_.candidate_id) } | Sort-Object created_at | Select-Object -First $Limit)
    Write-Output "PENDING_COUNT=$($pending.Count)"
    foreach ($item in $pending) {
        Write-Output ("ID={0} | 产品={1} | 问题={2} | 回复={3}" -f $item.candidate_id, $item.product, $item.issue, ([string]$item.japanese_reply).Substring(0, [Math]::Min(80, ([string]$item.japanese_reply).Length)))
    }
    exit 0
}

if ($CandidateId.Count -eq 0) {
    $lastPath = Join-Path (Get-SupportHome) "learning\last_candidate.json"
    if (-not (Test-Path -LiteralPath $lastPath -PathType Leaf)) { throw "没有可审核的最近候选。" }
    $last = Get-Content -LiteralPath $lastPath -Encoding UTF8 -Raw | ConvertFrom-Json
    $CandidateId = @([string]$last.candidate_id)
}

$written = 0
foreach ($id in $CandidateId) {
    if (-not $candidateMap.ContainsKey($id)) { Write-Output "NOT_FOUND=$id"; continue }
    $event = [ordered]@{
        event_id = [guid]::NewGuid().ToString()
        candidate_id = $id
        device_id = [string]$config.device_id
        created_at = (Get-Date).ToString("o")
        action = $Action.ToLowerInvariant()
        reason = $Reason
    }
    foreach ($root in $roots) {
        Add-JsonLine -Path (Join-Path $root "events\$($config.device_id).jsonl") -Value $event
    }
    $written++
    Write-Output "$($Action.ToUpperInvariant())=$id"
}
Write-Output "EVENTS_WRITTEN=$written"
