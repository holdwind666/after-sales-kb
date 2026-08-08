$ErrorActionPreference = "Stop"

function Get-SupportHome {
    if ($env:LOCALAPPDATA) { return (Join-Path $env:LOCALAPPDATA "AfterSalesSupport") }
    return (Join-Path $env:USERPROFILE ".after-sales-support")
}

function Get-LearningConfig {
    $path = if ($env:AFTERSALES_CONFIG_PATH) { $env:AFTERSALES_CONFIG_PATH } else { Join-Path (Get-SupportHome) "config\settings.json" }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "售后知识库尚未初始化：$path" }
    return (Get-Content -LiteralPath $path -Encoding UTF8 -Raw | ConvertFrom-Json)
}

function Get-LearningRoots {
    param([object]$Config)
    $roots = [System.Collections.Generic.List[string]]::new()
    $local = Join-Path (Get-SupportHome) "learning"
    New-Item -ItemType Directory -Path $local -Force | Out-Null
    $roots.Add($local)
    if ($Config.cloud_learning_root) {
        $cloud = [string]$Config.cloud_learning_root
        if (Test-Path -LiteralPath $cloud -PathType Container) {
            $resolved = (Resolve-Path -LiteralPath $cloud).Path
            if (-not $roots.Contains($resolved)) { $roots.Add($resolved) }
        }
    }
    return $roots
}

function Add-JsonLine {
    param([string]$Path, [object]$Value)
    $parent = Split-Path -Parent $Path
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    $line = $Value | ConvertTo-Json -Depth 10 -Compress
    Add-Content -LiteralPath $Path -Value $line -Encoding UTF8
}

function Read-JsonLines {
    param([string]$Directory)
    $items = @()
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { return $items }
    foreach ($file in (Get-ChildItem -LiteralPath $Directory -Filter *.jsonl -File -ErrorAction SilentlyContinue)) {
        foreach ($line in (Get-Content -LiteralPath $file.FullName -Encoding UTF8)) {
            if (-not $line.Trim()) { continue }
            try { $items += ($line | ConvertFrom-Json) } catch { continue }
        }
    }
    return $items
}

function Get-ContentFingerprint {
    param([string]$Text)
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-", "").ToLowerInvariant()
    } finally { $sha.Dispose() }
}
