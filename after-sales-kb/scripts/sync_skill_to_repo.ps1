$ErrorActionPreference = "Stop"

$repo = "E:\说明书与视频（第9台）\售后知识库Skill发布\after-sales-kb-repo"
$skill = "C:\Users\ASUS\.codex\skills\after-sales-kb"
$target = Join-Path $repo "after-sales-kb"

if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
New-Item -ItemType Directory -Path $target -Force | Out-Null
# Copy the skill's CONTENTS into the target. Copy-Item with an existing
# destination directory would nest the source folder (after-sales-kb\after-sales-kb).
Get-ChildItem -LiteralPath $skill -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $target -Recurse -Force
}

$pycache = Join-Path $target "scripts\__pycache__"
if (Test-Path -LiteralPath $pycache) {
    Remove-Item -LiteralPath $pycache -Recurse -Force
}

Write-Output "SYNC_DONE"
Get-ChildItem -Recurse -File -LiteralPath $target | ForEach-Object {
    $_.FullName.Replace($target, "")
} | Sort-Object
