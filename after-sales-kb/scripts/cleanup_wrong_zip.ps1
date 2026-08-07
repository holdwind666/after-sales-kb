param(
    [string]$ProtectedZip = ""
)

# cleanup_wrong_zip.ps1 - One-off cleanup: remove the after-sales-kb.zip that
# was accidentally written into a mojibake folder on E:\ by the earlier
# build_install_zip.ps1 (GBK-vs-UTF8 path issue). ASCII-only file.

$ErrorActionPreference = "Stop"

$ProtectedFull = ""
if ($ProtectedZip) {
    $ProtectedFull = [System.IO.Path]::GetFullPath($ProtectedZip)
}

$Cutoff = (Get-Date).AddHours(-6)

Get-ChildItem -LiteralPath "E:\" -Directory -Force -ErrorAction Stop | ForEach-Object {
    Get-ChildItem -LiteralPath $_.FullName -Filter "*after-sales-kb.zip" -File -Force -ErrorAction SilentlyContinue | ForEach-Object {
        $Full = [System.IO.Path]::GetFullPath($_.FullName)
        if ($ProtectedFull -and $Full -eq $ProtectedFull) {
            return
        }
        if ($_.Length -eq 60672 -and $_.LastWriteTime -gt $Cutoff) {
            Remove-Item -LiteralPath $_.FullName -Force
            Write-Output "REMOVED=$Full"
        }
    }
}

# Remove leftover temp staging folders from zip rebuilds.
Get-ChildItem -LiteralPath $env:TEMP -Directory -Filter "kb-stage-*" -Force -ErrorAction SilentlyContinue | Where-Object {
    $_.LastWriteTime -gt $Cutoff
} | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
    Write-Output "STAGE_REMOVED=$($_.FullName)"
}

Write-Output "CLEANUP_DONE"
