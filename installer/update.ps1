param(
    [string]$RepoUrl = "https://github.com/holdwind666/after-sales-kb.git",
    [string]$Ref = "v2.0.2",
    [string]$SourceRoot = "",
    [string]$DestinationRoot = "",
    [switch]$SkipInitialization
)

$ErrorActionPreference = "Stop"
$temporaryRoot = ""
try {
    if (-not $SourceRoot) {
        $temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) ("after-sales-kb-" + [guid]::NewGuid().ToString("N"))
        $git = Get-Command git.exe -ErrorAction SilentlyContinue
        if ($git) {
            & $git.Source clone --depth 1 --branch $Ref $RepoUrl $temporaryRoot
            if ($LASTEXITCODE -ne 0) { throw "Unable to download release $Ref." }
            $SourceRoot = $temporaryRoot
        } else {
            if ($RepoUrl -notmatch '^https://github\.com/([^/]+)/([^/.]+)(?:\.git)?$') { throw "ZIP fallback supports public GitHub repositories only." }
            $owner = $Matches[1]
            $repo = $Matches[2]
            $archiveRef = if ($Ref -eq "main") { "heads/main" } else { "tags/$Ref" }
            $zipPath = $temporaryRoot + ".zip"
            New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
            Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/$owner/$repo/archive/refs/$archiveRef.zip" -OutFile $zipPath
            $extractRoot = Join-Path $temporaryRoot "extract"
            Expand-Archive -LiteralPath $zipPath -DestinationPath $extractRoot -Force
            $downloaded = Get-ChildItem -LiteralPath $extractRoot -Directory | Select-Object -First 1
            if (-not $downloaded) { throw "Downloaded archive is empty." }
            $SourceRoot = $downloaded.FullName
        }
    }
    $installer = Join-Path $SourceRoot "installer\install.ps1"
    if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "Update source has no installer/install.ps1" }
    & $installer -DestinationRoot $DestinationRoot -SkipInitialization:$SkipInitialization
    exit $LASTEXITCODE
} finally {
    if ($temporaryRoot -and (Test-Path -LiteralPath $temporaryRoot)) {
        $tempBase = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\'
        $target = [IO.Path]::GetFullPath($temporaryRoot)
        if ($target.StartsWith($tempBase, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
        }
    }
    $zipPath = $temporaryRoot + ".zip"
    if ($temporaryRoot -and (Test-Path -LiteralPath $zipPath)) { Remove-Item -LiteralPath $zipPath -Force }
}
