param(
    [string]$SkillDir = "C:\Users\ASUS\.codex\skills\after-sales-kb",
    [string]$ZipPath = ""
)

# build_install_zip.ps1 - Rebuild the after-sales-kb install zip.
# Keep this file ASCII-only: Windows PowerShell 5.1 reads UTF-8 files without
# BOM as ANSI, so any Chinese literal inside would be mangled.
#
# Usage (recommended: run from the install-package folder):
#   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\build_install_zip.ps1"
# Or pass the target explicitly:
#   powershell -ExecutionPolicy Bypass -File "...\build_install_zip.ps1" -ZipPath "D:\path\after-sales-kb.zip"

$ErrorActionPreference = "Stop"

if (-not $ZipPath) {
    $ZipPath = Join-Path (Get-Location) "after-sales-kb.zip"
}

if (-not (Test-Path -LiteralPath $SkillDir)) {
    Write-Error "Skill directory not found: $SkillDir"
    exit 1
}

$StageRoot = Join-Path $env:TEMP ("kb-stage-" + [System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $StageRoot | Out-Null

try {
    $Target = Join-Path $StageRoot "after-sales-kb"
    Copy-Item -LiteralPath $SkillDir -Destination $Target -Recurse -Force

    # Drop __pycache__ so the zip stays clean.
    Get-ChildItem -LiteralPath $Target -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
        if ($_.FullName.StartsWith($StageRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $_.FullName -Recurse -Force
        }
    }

    $ZipDir = Split-Path -Parent $ZipPath
    if (-not (Test-Path -LiteralPath $ZipDir)) {
        New-Item -ItemType Directory -Path $ZipDir -Force | Out-Null
    }
    if (Test-Path -LiteralPath $ZipPath) {
        Remove-Item -LiteralPath $ZipPath -Force
    }

    Compress-Archive -Path $Target -DestinationPath $ZipPath -CompressionLevel Optimal
    $item = Get-Item -LiteralPath $ZipPath
    Write-Output "ZIP_DONE"
    Write-Output "PATH=$($item.FullName)"
    Write-Output "SIZE_MB=$([Math]::Round($item.Length / 1MB, 2))"
    Write-Output "MODIFIED=$($item.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss'))"
} finally {
    if (Test-Path -LiteralPath $StageRoot) {
        Remove-Item -LiteralPath $StageRoot -Recurse -Force
    }
}
