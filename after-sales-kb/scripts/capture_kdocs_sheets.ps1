param(
    [Parameter(Mandatory=$true)][string]$CacheDir,
    [Parameter(Mandatory=$false)][int]$WaitMs = 2500
)

$ErrorActionPreference = "Continue"
$utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Path $CacheDir -Force | Out-Null

# Step 1: get sheet name list
$namesJson = (& playwright-cli -s=wps eval "() => { const opts=[...document.querySelectorAll('[role=option]')]; return JSON.stringify(opts.map(o=>(o.innerText||'').trim())); }" 2>$null | Out-String)
$names = @()
$jsonLine = ($namesJson -split "`n") | Where-Object { $_ -match '^\s*".*\[.*\]"\s*$' } | Select-Object -First 1
if ($jsonLine) {
    try {
        $inner = ($jsonLine.Trim() | ConvertFrom-Json)
        $parsed = @($inner | ConvertFrom-Json)
        $names = @($parsed[0])
    } catch {
        Write-Output "PARSE ERROR: $($_.Exception.Message)"
    }
}
if ($names.Count -eq 0) {
    Write-Output "ERROR: cannot get sheet list"
    exit 1
}
Write-Output "sheets: $($names.Count)"

# Build a name -> ref map from one snapshot call.
# Snapshot line format: - option "name" [ref=e676] [cursor=pointer]:
$snap = (& playwright-cli -s=wps snapshot 2>$null | Out-String)
$refMap = @{}
foreach ($line in ($snap -split "`r?`n")) {
    if ($line -match 'option "((?:[^"\\]|\\.)*)" \[ref=([A-Za-z0-9]+)\]') {
        $optName = $Matches[1] -replace '\\"', '"'
        $refMap[$optName] = $Matches[2]
    }
}
Write-Output "refMap entries: $($refMap.Count)"

$ok = 0; $skip = 0; $fail = 0
foreach ($name in $names) {
    $safe = $name -replace '[\\/:*?"<>|]', '_' -replace '\s+', ' '
    $outFile = Join-Path $CacheDir ($safe + ".txt")
    if ((Test-Path -LiteralPath $outFile) -and ((Get-Item -LiteralPath $outFile).Length -gt 50)) {
        $skip++
        continue
    }
    $ref = $refMap[$name]
    if (-not $ref) {
        [System.IO.File]::AppendAllText((Join-Path $CacheDir "_capture_log.txt"), "NOREF`t$name`r`n", $utf8)
        $fail++
        Write-Output "FAIL noref: $name"
        continue
    }
    $clickOut = (& playwright-cli -s=wps click $ref 2>&1 | Out-String)
    if ($clickOut -match '### Error|not found|is not defined') {
        [System.IO.File]::AppendAllText((Join-Path $CacheDir "_capture_log.txt"), "CLICKFAIL`t$name`r`n", $utf8)
        $fail++
        Write-Output "FAIL click: $name"
        continue
    }
    Start-Sleep -Milliseconds $WaitMs
    & playwright-cli -s=wps press "Control+a" 2>$null | Out-Null
    & playwright-cli -s=wps press "Control+c" 2>$null | Out-Null
    Start-Sleep -Milliseconds 900
    $content = Get-Clipboard -Raw
    if (-not $content -or $content.Length -lt 50) {
        [System.IO.File]::AppendAllText((Join-Path $CacheDir "_capture_log.txt"), "EMPTY`t$name`r`n", $utf8)
        $fail++
        Write-Output "FAIL empty: $name"
        continue
    }
    [System.IO.File]::WriteAllText($outFile, $content, $utf8)
    $ok++
    Write-Output "OK: $name ($($content.Length) chars)"
}
Write-Output "DONE ok=$ok skip=$skip fail=$fail"
