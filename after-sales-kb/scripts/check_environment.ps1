param(
    [string]$RootDir = ""
)

$ErrorActionPreference = "Continue"
Write-Output "===== after-sales-kb 环境自检 ====="

if (-not $RootDir) {
    Write-Output "[1] 根目录: 未提供"
    Write-Output "    -> 请先告诉 Codex 说明书与视频所在文件夹地址，例如 E:\说明书与视频（第9台）"
    exit 1
}
Write-Output "[1] 根目录: $RootDir (存在: $(Test-Path -LiteralPath $RootDir))"

# 子目录
$subs = @("说明书", "演示视频", "售后常用图片")
foreach ($s in $subs) {
    $p = Join-Path $RootDir $s
    Write-Output "    - $s : $(Test-Path -LiteralPath $p)"
}

# 缓存目录
$cache = Join-Path $RootDir "_售后模板缓存"
Write-Output "[2] 缓存目录: $cache (存在: $(Test-Path -LiteralPath $cache))"
if (Test-Path -LiteralPath $cache) {
    $idx = @("products.tsv", "miss_counter.json", "settings.json")
    foreach ($i in $idx) {
        Write-Output "    - $i : $(Test-Path -LiteralPath (Join-Path $cache $i))"
    }
    foreach ($d in @("faq", "facts", "kdocs", "pdf_ocr", "pdf_pages", "video_index", "image_index", "manual_image_index", "xlsx_image_index", "vision_index")) {
        $dp = Join-Path $cache $d
        $n = 0
        if (Test-Path -LiteralPath $dp) { $n = (Get-ChildItem -LiteralPath $dp -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count }
        Write-Output "    - $d/ : $n 个文件"
    }
    $xlsx = Get-ChildItem -LiteralPath $cache -Filter "日本站售后对应方案表*.xlsx" -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($xlsx) {
        Write-Output "    - 本地整表xlsx: $($xlsx.Name) ($([Math]::Round($xlsx.Length/1MB,1)) MB)"
    } else {
        Write-Output "    - 本地整表xlsx: 未找到（图片查询走在线定位，或按需下载）"
    }
}

# Chrome 会话（仅提示）
Write-Output "[3] 在线表格访问: 需要 Chrome 打开并保持登录 WPS"
$chrome = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
Write-Output "    - Chrome: $(if ($chrome) { $chrome } else { "未找到，请安装 Chrome" })"

# Python 依赖
Write-Output "[4] Python 依赖:"
$py = "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if (Test-Path $py) {
    Write-Output "    - Python: $py"
    $deps = & $py -c "import importlib.util; print('pdfplumber', bool(importlib.util.find_spec('pdfplumber'))); print('PIL', bool(importlib.util.find_spec('PIL'))); print('pypdf', bool(importlib.util.find_spec('pypdf')))" 2>$null
    $deps | ForEach-Object { Write-Output "    - $_" }
} else {
    Write-Output "    - Python: 未找到，请使用 Codex 自带运行环境"
}

# 启动封装检查
Write-Output "    - 启动封装（必须存在，禁止直接敲 python）:"
$launcher = Join-Path $PSScriptRoot "py.ps1"
$qq = Join-Path $PSScriptRoot "quick_query.ps1"
Write-Output "    - py.ps1: $(Test-Path -LiteralPath $launcher)"
Write-Output "    - quick_query.ps1: $(Test-Path -LiteralPath $qq)"
if (Test-Path -LiteralPath $launcher) {
    $testOut = & powershell -NoProfile -ExecutionPolicy Bypass -File $launcher -c "print('PY_LAUNCH_OK')" 2>$null
    Write-Output "    - py.ps1 实测: $(if ($testOut -match 'PY_LAUNCH_OK') { '可用' } else { '异常，请检查' })"
}

# Poppler
$poppler = "C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\poppler\Library\bin\pdftoppm.exe"
Write-Output "    - Poppler(pdftoppm): $(Test-Path $poppler)"

# 识图能力检查
Write-Output "[5] 识图能力:"
Write-Output "    - 会话识图能力: 由 Codex 运行环境决定（若可查看图片则优先使用）"
$vision = "C:\Users\ASUS\.codex\skills\vision-skill\scripts\vision.js"
Write-Output "    - vision-skill: $(Test-Path $vision)（会话不具备识图能力时需用此技能接入第三方识图 API）"

Write-Output "===== 自检完成 ====="
Write-Output "若以上有缺失项，请按 references/troubleshooting.md 分步解决。"
