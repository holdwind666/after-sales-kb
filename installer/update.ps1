param(
    [string]$RepoUrl = "https://github.com/holdwind666/after-sales-kb.git",
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
        if (-not $git) { throw "Git is required for automatic updates." }
        & $git.Source clone --depth 1 $RepoUrl $temporaryRoot
        if ($LASTEXITCODE -ne 0) { throw "Unable to download the stable repository." }
        $SourceRoot = $temporaryRoot
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
}
