param()

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

$approved = [System.Collections.Generic.List[object]]::new()
$seen = @{}
foreach ($id in $candidateMap.Keys) {
    if (-not $eventMap.ContainsKey($id) -or $eventMap[$id].action -ne "approve") { continue }
    $item = $candidateMap[$id]
    $fingerprint = [string]$item.fingerprint
    if ($seen.ContainsKey($fingerprint)) { continue }
    $seen[$fingerprint] = $true
    $approved.Add($item)
}

$localCorpus = Join-Path (Get-SupportHome) "learning\corpus"
New-Item -ItemType Directory -Path $localCorpus -Force | Out-Null
$jsonPath = Join-Path $localCorpus "approved_cases.jsonl"
$jsonLines = @($approved | ForEach-Object { $_ | ConvertTo-Json -Depth 10 -Compress })
[IO.File]::WriteAllLines($jsonPath, [string[]]$jsonLines, [Text.UTF8Encoding]::new($false))

$quickDir = Join-Path ([string]$config.cache_root) "quick_index"
New-Item -ItemType Directory -Path $quickDir -Force | Out-Null
$indexPath = Join-Path $quickDir "approved_cases_norm.tsv"
$rows = @()
foreach ($item in $approved) {
    $text = "$($item.product) $($item.issue) $($item.chinese_logic) $($item.japanese_reply)".ToLowerInvariant() -replace '\s+', ''
    $rows += "$($item.product)|$($item.candidate_id)`t$text"
}
[IO.File]::WriteAllLines($indexPath, [string[]]$rows, [Text.UTF8Encoding]::new($false))

foreach ($root in $roots) {
    $corpus = Join-Path $root "corpus"
    New-Item -ItemType Directory -Path $corpus -Force | Out-Null
    $destination = Join-Path $corpus "approved_cases.jsonl"
    if (-not ([IO.Path]::GetFullPath($destination).Equals([IO.Path]::GetFullPath($jsonPath), [StringComparison]::OrdinalIgnoreCase))) {
        Copy-Item -LiteralPath $jsonPath -Destination $destination -Force
    }
}
Write-Output "APPROVED_CASES=$($approved.Count)"
Write-Output "DEDUPLICATED=$($candidateMap.Count - $approved.Count)"
Write-Output "INDEX=$indexPath"
