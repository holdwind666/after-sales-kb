param(
    [Parameter(Mandatory=$true)][string]$Source,
    [string]$ConfigPath = "",
    [string]$Project = "",
    [switch]$Force
)

# import_chatgpt_export.ps1 - 方案 B：把浏览器扩展导出的 ChatGPT JSON/JSONL
# 导入学习库 raw 目录（内部调用 import_chatgpt_export.py）。

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
if (-not $ScriptDir) { $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }

$Py = Join-Path $ScriptDir "py.ps1"
$PyScript = Join-Path $ScriptDir "import_chatgpt_export.py"
if (-not (Test-Path -LiteralPath $PyScript)) {
    Write-Error "Missing: $PyScript"
    exit 1
}

$ArgsList = @("--source", $Source)
if ($ConfigPath) { $ArgsList += @("--config", $ConfigPath) }
if ($Project) { $ArgsList += @("--project", $Project) }
if ($Force) { $ArgsList += "--force" }

& $Py $PyScript @ArgsList
exit $LASTEXITCODE
