$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path ([IO.Path]::GetTempPath()) ("after-sales-smoke-" + [guid]::NewGuid().ToString("N"))
$originalLocalAppData = $env:LOCALAPPDATA

try {
    $env:LOCALAPPDATA = Join-Path $testRoot "localappdata"
    $dataRoot = Join-Path $testRoot "测试说明书与视频"
    $cacheRoot = Join-Path $testRoot "cache"
    $cloudRoot = Join-Path $testRoot "wps-learning"
    $skillRoot = Join-Path $testRoot "skills"
    foreach ($path in @(
        (Join-Path $dataRoot "说明书"),
        (Join-Path $dataRoot "演示视频"),
        (Join-Path $dataRoot "售后常用图片"),
        $cloudRoot,
        $skillRoot
    )) { New-Item -ItemType Directory -Path $path -Force | Out-Null }
    $fixture = @"
日期`t问题`t回复模板
2026-08-09`t无法充电`t別のUSBケーブルで充電をお試しください。
"@
    [IO.File]::WriteAllText((Join-Path $dataRoot "kdocs_日本站售后对应方案表_测试产品.txt"), $fixture, (New-Object Text.UTF8Encoding($false)))

    $bootstrap = Join-Path $repoRoot "installer\bootstrap.ps1"
    $bootstrapOutput = & $bootstrap -DestinationRoot $skillRoot -DataRoot $dataRoot -CacheRoot $cacheRoot -WpsLearningRoot $cloudRoot -BuildMode Full -SkipPdfPages -ValidationProduct "测试产品" -ValidationQuery "无法充电"
    if ($LASTEXITCODE -ne 0) { throw "bootstrap failed: $LASTEXITCODE`n$($bootstrapOutput -join "`n")" }
    if (-not ($bootstrapOutput | Where-Object { $_ -eq "READY_FOR_SUPPORT" })) { throw "bootstrap did not report ready" }
    foreach ($name in @("after-sales-reply", "after-sales-kb-maintain", "after-sales-learning-review")) {
        if (-not (Test-Path -LiteralPath (Join-Path $skillRoot "$name\SKILL.md"))) { throw "missing installed skill: $name" }
    }

    $configPath = Join-Path $env:LOCALAPPDATA "AfterSalesSupport\config\settings.json"
    $config = Get-Content -LiteralPath $configPath -Encoding UTF8 -Raw | ConvertFrom-Json
    $firstDeviceId = [string]$config.device_id
    if (-not $firstDeviceId) { throw "device id missing" }
    & (Join-Path $skillRoot "after-sales-kb-maintain\scripts\initialize.ps1") -DataRoot $dataRoot -CacheRoot $cacheRoot -WpsLearningRoot $cloudRoot | Out-Null
    $config2 = Get-Content -LiteralPath $configPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if ([string]$config2.device_id -ne $firstDeviceId) { throw "device id changed" }
    if (-not (Test-Path -LiteralPath (Join-Path $cacheRoot "quick_index\meta.json"))) { throw "full build did not create quick index" }

    & (Join-Path $repoRoot "installer\update.ps1") -SourceRoot $repoRoot -DestinationRoot $skillRoot -SkipInitialization
    if ($LASTEXITCODE -ne 0) { throw "idempotent update failed: $LASTEXITCODE" }
    $configAfterUpdate = Get-Content -LiteralPath $configPath -Encoding UTF8 -Raw | ConvertFrom-Json
    if ([string]$configAfterUpdate.device_id -ne $firstDeviceId) { throw "update replaced local config" }

    $learningScripts = Join-Path $skillRoot "after-sales-learning-review\scripts"
    $created = & (Join-Path $learningScripts "new_candidate.ps1") -Product "测试产品" -Issue "无法充电" -ChineseLogic "换线复测" -JapaneseReply "別のケーブルでお試しください。" -Value high
    $candidateLine = $created | Where-Object { $_ -like "CANDIDATE_CREATED=*" } | Select-Object -First 1
    $candidateId = ($candidateLine -split "=", 2)[1]
    if (-not $candidateId) { throw "candidate id missing" }
    $beforeApproval = & (Join-Path $learningScripts "sync_learning.ps1")
    if (-not ($beforeApproval | Where-Object { $_ -eq "APPROVED_CASES=0" })) { throw "pending candidate leaked into approved index" }
    & (Join-Path $learningScripts "review_learning.ps1") -Action Approve -CandidateId $candidateId | Out-Null
    $sync = & (Join-Path $learningScripts "sync_learning.ps1")
    if (-not ($sync | Where-Object { $_ -eq "APPROVED_CASES=1" })) { throw "approved case did not enter index" }
    $approvedIndex = Join-Path $cacheRoot "quick_index\approved_cases_norm.tsv"
    if (-not (Test-Path -LiteralPath $approvedIndex)) { throw "approved index missing" }
    $query = & (Join-Path $skillRoot "after-sales-kb-maintain\scripts\quick_query.ps1") -Product "测试产品" -Q "无法充电"
    if (-not ($query | Where-Object { $_ -match "APPROVED" })) { throw "approved case was not searchable" }

    Write-Output "SMOKE_OK"
} finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
    $target = [IO.Path]::GetFullPath($testRoot)
    if ($target.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $testRoot)) {
        Remove-Item -LiteralPath $testRoot -Recurse -Force
    }
}
