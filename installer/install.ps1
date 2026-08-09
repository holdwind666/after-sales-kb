param(
    [string]$DestinationRoot = "",
    [string]$DataRoot = "",
    [string]$WpsUrl = "",
    [string]$WpsLearningRoot = "",
    [switch]$SkipInitialization
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$manifestPath = Join-Path $repoRoot "install-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw "Missing install-manifest.json" }
$manifest = Get-Content -LiteralPath $manifestPath -Encoding UTF8 -Raw | ConvertFrom-Json
if ($manifest.checksums_file) {
    $checksumsPath = Join-Path $repoRoot ([string]$manifest.checksums_file)
    if (-not (Test-Path -LiteralPath $checksumsPath -PathType Leaf)) { throw "Missing checksums file: $checksumsPath" }
    foreach ($line in (Get-Content -LiteralPath $checksumsPath -Encoding UTF8)) {
        if (-not $line.Trim() -or $line.TrimStart().StartsWith("#")) { continue }
        $parts = $line -split '\s+', 2
        if ($parts.Count -ne 2) { throw "Invalid checksum line: $line" }
        $expectedHash = $parts[0].ToLowerInvariant()
        $relativePath = $parts[1].Trim().Replace('/', '\')
        $filePath = Join-Path $repoRoot $relativePath
        if (-not (Test-Path -LiteralPath $filePath -PathType Leaf)) { throw "Checksum target missing: $relativePath" }
        $actualHash = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actualHash -ne $expectedHash) { throw "Checksum mismatch: $relativePath" }
    }
    Write-Output "CHECKSUMS_VERIFIED"
}
$defaultDestination = Join-Path $env:USERPROFILE ".agents\skills"
if (-not $DestinationRoot) { $DestinationRoot = $defaultDestination }
New-Item -ItemType Directory -Path $DestinationRoot -Force | Out-Null
$DestinationRoot = (Resolve-Path -LiteralPath $DestinationRoot).Path
$defaultDestinationFull = [IO.Path]::GetFullPath($defaultDestination).TrimEnd('\')
$isDefaultDestination = $DestinationRoot.TrimEnd('\').Equals($defaultDestinationFull, [StringComparison]::OrdinalIgnoreCase)

function Assert-ChildPath {
    param([string]$Parent, [string]$Child)
    $parentFull = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    $childFull = [IO.Path]::GetFullPath($Child)
    if (-not $childFull.StartsWith($parentFull, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe target outside destination root: $childFull"
    }
}

$supportHome = if ($env:LOCALAPPDATA) { Join-Path $env:LOCALAPPDATA "AfterSalesSupport" } else { Join-Path $env:USERPROFILE ".after-sales-support" }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupRoot = Join-Path $supportHome "backups\$stamp\skills"
$stageRoot = Join-Path $DestinationRoot (".after-sales-stage-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null
$originals = @{}
$replaced = [System.Collections.Generic.List[string]]::new()

try {
    foreach ($relative in $manifest.skills) {
        $source = Join-Path $repoRoot ([string]$relative)
        $name = Split-Path -Leaf $source
        $stage = Join-Path $stageRoot $name
        if (-not (Test-Path -LiteralPath (Join-Path $source "SKILL.md") -PathType Leaf)) { throw "Invalid skill source: $source" }
        Copy-Item -LiteralPath $source -Destination $stage -Recurse -Force
    }
    foreach ($relative in $manifest.skills) {
        $name = Split-Path -Leaf ([string]$relative)
        $target = Join-Path $DestinationRoot $name
        Assert-ChildPath -Parent $DestinationRoot -Child $target
        $hadOriginal = Test-Path -LiteralPath $target
        $originals[$name] = $hadOriginal
        if ($hadOriginal) {
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            Copy-Item -LiteralPath $target -Destination (Join-Path $backupRoot $name) -Recurse -Force
            $replaced.Add($name)
            Remove-Item -LiteralPath $target -Recurse -Force
        } else {
            $replaced.Add($name)
        }
        Move-Item -LiteralPath (Join-Path $stageRoot $name) -Destination $target
    }
} catch {
    $installError = $_
    foreach ($name in @($replaced)) {
        $target = Join-Path $DestinationRoot $name
        Assert-ChildPath -Parent $DestinationRoot -Child $target
        if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue }
        $backup = Join-Path $backupRoot $name
        if ($originals[$name] -and (Test-Path -LiteralPath $backup)) {
            Copy-Item -LiteralPath $backup -Destination $target -Recurse -Force
        }
    }
    Write-Output "INSTALL_ROLLED_BACK"
    throw $installError
} finally {
    if (Test-Path -LiteralPath $stageRoot) {
        Assert-ChildPath -Parent $DestinationRoot -Child $stageRoot
        Remove-Item -LiteralPath $stageRoot -Recurse -Force
    }
}

if ($isDefaultDestination) {
    $legacyRoots = @(
        (Join-Path $env:USERPROFILE ".agents\skills\after-sales-kb"),
        (Join-Path $env:USERPROFILE ".codex\skills\after-sales-kb")
    ) | Select-Object -Unique
    foreach ($legacy in $legacyRoots) {
        if (Test-Path -LiteralPath $legacy -PathType Container) {
            $legacyParent = Split-Path -Parent $legacy
            Assert-ChildPath -Parent $legacyParent -Child $legacy
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            Copy-Item -LiteralPath $legacy -Destination (Join-Path $backupRoot "after-sales-kb-legacy") -Recurse -Force
            Remove-Item -LiteralPath $legacy -Recurse -Force
            Write-Output "LEGACY_SKILL_BACKED_UP=$legacy"
        }
    }
}

Write-Output "SKILLS_INSTALLED=$($manifest.version)"
Write-Output "DESTINATION_ROOT=$DestinationRoot"
if (-not $SkipInitialization) {
    $init = Join-Path $DestinationRoot "after-sales-kb-maintain\scripts\initialize.ps1"
    & $init -DataRoot $DataRoot -WpsUrl $WpsUrl -WpsLearningRoot $WpsLearningRoot
    $initExit = $LASTEXITCODE
    if ($initExit -ne 0) {
        Write-Output "INSTALL_NEEDS_INPUT"
        exit $initExit
    }
}
Write-Output "INSTALL_COMPLETE"
exit 0
