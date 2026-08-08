param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

$ErrorActionPreference = "Stop"
$candidates = [System.Collections.Generic.List[string]]::new()
foreach ($commandName in @("py.exe", "python.exe", "python3.exe")) {
    $cmd = Get-Command $commandName -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and -not $candidates.Contains($cmd.Source)) { $candidates.Add($cmd.Source) }
}
$runtimeRoot = Join-Path $env:USERPROFILE ".cache\codex-runtimes"
if (Test-Path -LiteralPath $runtimeRoot) {
    Get-ChildItem -LiteralPath $runtimeRoot -Recurse -File -Include python.exe,python3.exe -ErrorAction SilentlyContinue |
        ForEach-Object { if (-not $candidates.Contains($_.FullName)) { $candidates.Add($_.FullName) } }
}
foreach ($candidate in $candidates) {
    try {
        & $candidate @Arguments
        exit $LASTEXITCODE
    } catch { continue }
}
Write-Error "未找到可用 Python。请让 Codex 检查工作区运行时或安装 Python 3。"
exit 1
