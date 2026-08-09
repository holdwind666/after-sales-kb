param(
    [string]$DestinationRoot = "",
    [string]$DataRoot = "",
    [string]$CacheRoot = "",
    [string]$WpsUrl = "",
    [string]$WpsLearningRoot = "",
    [ValidateSet("Auto", "Full", "Refresh")][string]$BuildMode = "Auto",
    [string]$ValidationProduct = "",
    [string]$ValidationQuery = "",
    [switch]$ForceBuild,
    [switch]$SkipPdfPages,
    [switch]$AllowWithoutWps
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifest = Get-Content -LiteralPath (Join-Path $repoRoot "install-manifest.json") -Encoding UTF8 -Raw | ConvertFrom-Json
if (-not $DestinationRoot) { $DestinationRoot = Join-Path $env:USERPROFILE ".agents\skills" }

function Stop-Bootstrap {
    param([string]$Code, [int]$ExitCode)
    Write-Output $Code
    Write-Output "BOOTSTRAP_INCOMPLETE"
    exit $ExitCode
}

Write-Output "BOOTSTRAP_VERSION=$($manifest.version)"
Write-Output "BOOTSTRAP_PHASE=INSTALL"
& (Join-Path $PSScriptRoot "install.ps1") -DestinationRoot $DestinationRoot -SkipInitialization
if ($LASTEXITCODE -ne 0) { Stop-Bootstrap -Code "INSTALL_FAILED" -ExitCode $LASTEXITCODE }

$scriptRoot = Join-Path $DestinationRoot "after-sales-kb-maintain\scripts"
$initialize = Join-Path $scriptRoot "initialize.ps1"
$build = Join-Path $scriptRoot "build_cache.ps1"
$check = Join-Path $scriptRoot "check_environment.ps1"
$query = Join-Path $scriptRoot "quick_query.ps1"
foreach ($required in @($initialize, $build, $check, $query)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { Stop-Bootstrap -Code "INSTALLED_FILE_MISSING=$required" -ExitCode 10 }
}

Write-Output "BOOTSTRAP_PHASE=INITIALIZE"
$initArgs = @{}
if ($DataRoot) { $initArgs.DataRoot = $DataRoot }
if ($CacheRoot) { $initArgs.CacheRoot = $CacheRoot }
if ($WpsUrl) { $initArgs.WpsUrl = $WpsUrl }
if ($WpsLearningRoot) { $initArgs.WpsLearningRoot = $WpsLearningRoot }
$initOutput = & $initialize @initArgs 2>&1
$initExit = $LASTEXITCODE
$initOutput | ForEach-Object { Write-Output $_ }
if ($initExit -eq 2) { Stop-Bootstrap -Code "ACTION_REQUIRED=请提供本机名称包含说明书与视频的资料根目录，然后用-DataRoot继续。" -ExitCode 2 }
if ($initExit -eq 3) { Stop-Bootstrap -Code "ACTION_REQUIRED=发现多个资料目录，请选择上方一个CANDIDATE路径，然后用-DataRoot继续。" -ExitCode 3 }
if ($initExit -ne 0) { Stop-Bootstrap -Code "INITIALIZE_FAILED=$initExit" -ExitCode $initExit }

$configLine = $initOutput | Where-Object { [string]$_ -like "CONFIG_PATH=*" } | Select-Object -Last 1
$configPath = if ($configLine) { ([string]$configLine -split "=", 2)[1] } else { Join-Path $env:LOCALAPPDATA "AfterSalesSupport\config\settings.json" }

Write-Output "BOOTSTRAP_PHASE=BUILD"
& $build -Mode $BuildMode -ConfigPath $configPath -Force:$ForceBuild -SkipPdfPages:$SkipPdfPages
if ($LASTEXITCODE -ne 0) { Stop-Bootstrap -Code "CACHE_BUILD_FAILED" -ExitCode $LASTEXITCODE }

Write-Output "BOOTSTRAP_PHASE=VERIFY"
$environment = & $check -ConfigPath $configPath 2>&1
$environmentExit = $LASTEXITCODE
$environment | ForEach-Object { Write-Output $_ }
if ($environmentExit -ne 0 -or -not ($environment | Where-Object { [string]$_ -eq "ENVIRONMENT_OK" })) {
    Stop-Bootstrap -Code "ENVIRONMENT_VERIFY_FAILED" -ExitCode 11
}

$config = Get-Content -LiteralPath $configPath -Encoding UTF8 -Raw | ConvertFrom-Json
if (-not $ValidationQuery) {
    $faqFull = Join-Path ([string]$config.cache_root) "quick_index\faq_full.jsonl"
    if (Test-Path -LiteralPath $faqFull) {
        foreach ($faqLine in @(Get-Content -LiteralPath $faqFull -Encoding UTF8 -TotalCount 20)) {
            try {
                $sample = $faqLine | ConvertFrom-Json
                if ([string]$sample.question) {
                    $ValidationProduct = [string]$sample.sheet
                    $ValidationQuery = [string]$sample.question
                    break
                }
            } catch { }
        }
    }
}
if (-not $ValidationQuery) {
    foreach ($indexName in @("kdocs_norm.tsv", "ocr_pages.tsv", "spec_norm.tsv")) {
        $indexPath = Join-Path ([string]$config.cache_root) ("quick_index\" + $indexName)
        if (-not (Test-Path -LiteralPath $indexPath)) { continue }
        foreach ($line in @(Get-Content -LiteralPath $indexPath -Encoding UTF8 -TotalCount 10)) {
            $parts = $line -split "`t"
            $blob = [string]$parts[$parts.Count - 1]
            if ($blob -and $blob -notin @("page_text", "param_text") -and $blob.Length -ge 4) {
                $ValidationQuery = $blob.Substring(0, [Math]::Min(12, $blob.Length))
                break
            }
        }
        if ($ValidationQuery) { break }
    }
}
if ($ValidationQuery) {
    $queryOutput = & $query -Product $ValidationProduct -Q $ValidationQuery -ConfigPath $configPath 2>&1
    $queryExit = $LASTEXITCODE
    $queryOutput | Select-Object -First 12 | ForEach-Object { Write-Output "VERIFY_QUERY=$_" }
    if ($queryExit -ne 0 -or -not ($queryOutput | Where-Object { [string]$_ -match '^HITS' })) {
        Stop-Bootstrap -Code "REPRESENTATIVE_QUERY_FAILED" -ExitCode 12
    }
    Write-Output "REPRESENTATIVE_QUERY=HIT"
} else {
    Stop-Bootstrap -Code "REPRESENTATIVE_QUERY_UNAVAILABLE" -ExitCode 12
}

$meta = Get-Content -LiteralPath (Join-Path ([string]$config.cache_root) "quick_index\meta.json") -Encoding UTF8 -Raw | ConvertFrom-Json
$wpsStatus = if ([int]$meta.counts.kdocs -gt 0) { "READY" } else { "NOT_AVAILABLE" }
$kbState = if ($wpsStatus -eq "READY") { "READY_WITH_WPS" } else { "READY_LOCAL_ONLY" }
Write-Output "INSTALLED_VERSION=$($manifest.version)"
Write-Output "DATA_ROOT=$($config.data_root)"
Write-Output "CACHE_ROOT=$($config.cache_root)"
Write-Output "WPS_CACHE=$wpsStatus"
Write-Output "KB_STATE=$kbState"
if ($kbState -eq "READY_LOCAL_ONLY" -and -not $AllowWithoutWps) {
    Write-Output "ACTION_RECOMMENDED=当前电脑未找到可访问的WPS售后表缓存；本地说明书知识库已经可用，取得WPS本地XLSX或缓存后再次运行即可升级。"
}
Write-Output "READY_FOR_SUPPORT"
Write-Output "BOOTSTRAP_COMPLETE"
exit 0
