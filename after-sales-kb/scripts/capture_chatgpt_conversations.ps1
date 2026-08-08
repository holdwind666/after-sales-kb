param(
    [string]$ConfigPath = "",
    [string]$Session = "chatgpt",
    [int]$PageLimit = 50,
    [int]$MaxConversations = 1000,
    [int]$MaxItems = 0,
    [int]$WaitLoginMinutes = 10,
    [int]$TimeBudgetSeconds = 0,
    [switch]$WorkOnly,
    [switch]$Force,
    [switch]$NoBrowser
)

# capture_chatgpt_conversations.ps1 - Capture ChatGPT conversations through the
# logged-in persistent Chrome/Edge session into the WPS-synced raw directory.
#
# ASCII-only file. Full conversation payloads are saved as raw/conv_<id>.json
# and deduplicated by conversation id + update_time via raw/state.json.

$ErrorActionPreference = "Stop"

function Resolve-PlaywrightCli {
    $cmd = Get-Command playwright-cli -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $cands = @(
        "C:\Users\ASUS\AppData\Roaming\npm\playwright-cli.ps1",
        (Join-Path $env:APPDATA "npm\playwright-cli.ps1")
    )
    foreach ($c in $cands) {
        if ($c -and (Test-Path -LiteralPath $c)) { return $c }
    }
    throw "playwright-cli not found"
}

function Resolve-Config {
    param([string]$Path)
    if ($Path -and (Test-Path -LiteralPath $Path)) { return (Resolve-Path -LiteralPath $Path).Path }
    $envCfg = ""
    if ($env:AFTERSALES_CACHE_DIR) {
        $envCfg = Join-Path $env:AFTERSALES_CACHE_DIR "chatgpt_learning.json"
    }
    if ($envCfg -and (Test-Path -LiteralPath $envCfg)) { return $envCfg }
    $cwdCfg = Join-Path (Get-Location) "_售后模板缓存\chatgpt_learning.json"
    if (Test-Path -LiteralPath $cwdCfg) { return (Resolve-Path -LiteralPath $cwdCfg).Path }
    $skillCfg = Join-Path $PSScriptRoot "..\assets\bootstrap\chatgpt_learning.json"
    if (Test-Path -LiteralPath $skillCfg) { return (Resolve-Path -LiteralPath $skillCfg).Path }
    throw "chatgpt_learning.json not found; run setup_chatgpt_learning.ps1 first"
}

function ConvertFrom-EvalJson {
    param([string]$Text)
    $Text = $Text.Trim()
    if (-not $Text) { return $null }
    $obj = $null
    try { $obj = $Text | ConvertFrom-Json } catch { return $null }
    # playwright-cli may wrap the payload as a quoted JSON string.
    if ($obj -is [string]) {
        try { $obj = $obj | ConvertFrom-Json } catch { return $null }
    }
    return $obj
}

function Test-WorkTitle {
    param([string]$Title)
    $t = ($Title -replace "\s+", "").ToLowerInvariant()
    if (-not $t) { return $false }
    $Work = @(
        "售后", "返品", "返金", "交換", "新品", "発送", "配送", "到着", "商品", "不良",
        "故障", "保証", "レビュー", "星", "評価", "お客様", "申し訳", "アマゾン",
        "amazon", "asin", "領星", "注文", "物流", "邮便", "住所", "電話", "部品",
        "説明書", "取扱説明書", "充電", "バッテリー", "電源", "風量", "温度", "モード",
        "ボタン", "ランプ", "ドライヤー", "扇風機", "サーキュレーター", "加湿器",
        "空気清浄機", "電動", "吹风机", "循环扇", "加湿器", "空气净化器", "充电",
        "说明书", "配件", "退货", "退款", "发新", "补发", "赔偿", "客户", "客人",
        "亚马逊", "差评", "模板", "回复", "日文", "日本語", "中文", "翻译", "话术",
        "対応", "お問い合わせ", "运营", "listing", "标题", "五点", "关键词", "文案",
        "图片", "主图", "a+", "竞品", "競合", "调研", "市场", "選品", "选品", "销量",
        "売上", "销售", "排名", "ランキング", "bsr", "秒杀", "deal", "クーポン",
        "优惠券", "广告", "広告", "ppc", "cpc", "转化", "転換", "点击", "クリック",
        "库存", "在庫", "补货", "入荷", "発注", "fba", "fbm", "海外仓", "仓库",
        "倉庫", "sku", "upc", "ean", "品牌", "ブランド", "パッケージ", "包装",
        "规格书", "仕様書", "发票", "領収書", "客户反馈", "客诉", "投诉", "商品页面",
        "listing", "コンバージョン", "売れ行き", "广告优化", "亚马逊日本", "日本站",
        "视频", "分析", "优化", "建议", "问题", "排查", "原因", "处理", "方案"
    )
    foreach ($k in $Work) {
        if ($t.Contains($k)) { return $true }
    }
    $Life = @(
        "菜谱", "食谱", "做饭", "旅游", "旅行", "电影", "音乐", "游戏", "攻略",
        "健身", "减肥", "恋爱", "天气", "新闻", "明星", "八卦", "笑话", "故事",
        "作文", "简历", "面试", "考研", "学习英语", "背单词", "美食", "探店",
        "宠物", "猫咪", "狗狗", "孩子", "小孩", "教育", "学校"
    )
    foreach ($k in $Life) {
        if ($t.Contains($k)) { return $false }
    }
    return $false
}

$PlaywrightCli = Resolve-PlaywrightCli
$ConfigPath = Resolve-Config -Path $ConfigPath
$ConfigText = [System.IO.File]::ReadAllText($ConfigPath, (New-Object System.Text.UTF8Encoding($false)))
$Config = $ConfigText | ConvertFrom-Json

$RawDir = $Config.raw_dir
if (-not $RawDir) { $RawDir = Join-Path $Config.cloud_root "raw" }
if (-not $RawDir) {
    Write-Error "chatgpt_learning.json has no raw_dir; run setup_chatgpt_learning.ps1 first."
    exit 1
}
New-Item -ItemType Directory -Path $RawDir -Force | Out-Null

if (-not $NoBrowser) {
    & $PlaywrightCli -s=$Session open "https://chatgpt.com/" --headed --persistent 2>&1 | Out-Null
    Start-Sleep -Seconds 4
}

# ---- Login check (new ChatGPT auth: /api/auth/session + Bearer token) ----
$MeCode = "async () => { const r = await fetch('/api/auth/session', {credentials:'include'}); if (!r.ok) return JSON.stringify({error: r.status}); const j = await r.json(); return JSON.stringify({name: (j.user && j.user.name) || '', email: (j.user && j.user.email) || '', id: (j.user && j.user.id) || ''}); }"
$MeRaw = (& $PlaywrightCli --raw -s=$Session eval $MeCode 2>&1 | Out-String)
$Me = ConvertFrom-EvalJson $MeRaw
if (-not $Me -or -not $Me.email) {
    Write-Output "LOGIN_REQUIRED"
    if ($NoBrowser) {
        Write-Output "No browser session is available. Re-run without -NoBrowser to open the ChatGPT window and sign in."
        exit 2
    }
    if ($WaitLoginMinutes -le 0) {
        Write-Output "Open the ChatGPT browser window, sign in, then re-run this script."
        exit 2
    }
    Write-Output "Waiting up to $WaitLoginMinutes minutes for sign-in in the opened ChatGPT window..."
    $Deadline = (Get-Date).AddMinutes($WaitLoginMinutes)
    $LoggedIn = $false
    while ((Get-Date) -lt $Deadline) {
        Start-Sleep -Seconds 10
        $MeRaw = (& $PlaywrightCli --raw -s=$Session eval $MeCode 2>&1 | Out-String)
        $Me = ConvertFrom-EvalJson $MeRaw
        if ($Me -and $Me.email) {
            $LoggedIn = $true
            break
        }
    }
    if (-not $LoggedIn) {
        Write-Output "LOGIN_TIMEOUT"
        Write-Output "Timed out waiting for sign-in. Re-run the script after signing in."
        exit 2
    }
    Write-Output "LOGIN_OK"
}

# Seed the access token once into the page so every conversation fetch does
# not need its own /api/auth/session round trip (halves API calls and lowers
# the chance of hitting ChatGPT rate limits).
$TokenSeedCode = "async () => { const r = await fetch('/api/auth/session', {credentials:'include', cache:'no-store'}); const j = await r.json(); window.__chatgptTok = (j && j.accessToken) || ''; return JSON.stringify({seeded: !!window.__chatgptTok}); }"
$TokenSeedRaw = (& $PlaywrightCli --raw -s=$Session eval $TokenSeedCode 2>&1 | Out-String)
$TokenSeed = ConvertFrom-EvalJson $TokenSeedRaw
if (-not $TokenSeed -or -not $TokenSeed.seeded) {
    Write-Output "TOKEN_SEED_FAILED"
    exit 2
}

# ---- Project list (best effort; not fatal if endpoint changes) ----
$Projects = @{}
$ProjectCode = "async () => { const tok = window.__chatgptTok || ''; try { const r = await fetch('/backend-api/projects?limit=200', {credentials:'include', headers:{'Authorization':'Bearer ' + tok}}); if (!r.ok) return '{}'; const j = await r.json(); return JSON.stringify({items: j.items || j.projects || []}); } catch (e) { return '{}'; } }"
$ProjectRaw = (& $PlaywrightCli --raw -s=$Session eval $ProjectCode 2>&1 | Out-String)
$ProjectObj = ConvertFrom-EvalJson $ProjectRaw
if ($ProjectObj -and $ProjectObj.items) {
    foreach ($p in @($ProjectObj.items)) {
        if ($p.id) { $Projects[[string]$p.id] = $p.name }
    }
}

# Optional title-level prefilter: dramatically reduces API calls and 429 risk.
$TitleSkipped = 0
if ($WorkOnly) {
    $Filtered = [System.Collections.Generic.List[object]]::new()
    foreach ($Item in $Items) {
        if (Test-WorkTitle -Title ([string]$Item.title)) {
            $Filtered.Add($Item)
        } else {
            $TitleSkipped++
        }
    }
    $Items = @($Filtered)
}

# ---- Conversation list ----
# playwright-cli only allows --filename writes inside the workspace
# (.playwright-cli or the working tree); TEMP is rejected with
# "File access denied ... outside allowed roots".
$ConfigDir = Split-Path -Parent $ConfigPath
$TmpDir = Join-Path $ConfigDir (".playwright-cli\chatgpt_capture_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TmpDir | Out-Null

$Items = @()
try {
    $Offset = 0
    while ($Offset -lt $MaxConversations) {
        $PageFile = Join-Path $TmpDir ("list_" + $Offset + ".json")
        $ListCode = "async () => { const tok = window.__chatgptTok || ''; const r = await fetch('/backend-api/conversations?offset=$Offset&limit=$PageLimit&order=updated', {credentials:'include', headers:{'Authorization':'Bearer ' + tok}}); if (!r.ok) throw new Error('HTTP ' + r.status); return JSON.stringify(await r.json()); }"
        & $PlaywrightCli --raw -s=$Session eval --filename $PageFile $ListCode 2>&1 | Out-Null
        # Read with explicit UTF-8: PowerShell 5.1 Get-Content -Raw would
        # decode the JSON as ANSI/GBK and mangle CJK text, breaking the parse.
        $PageRaw = [System.IO.File]::ReadAllText($PageFile, (New-Object System.Text.UTF8Encoding($false)))
        $Page = ConvertFrom-EvalJson $PageRaw
        if (-not $Page -or -not $Page.items) { break }
        $PageItems = @($Page.items)
        $Items += $PageItems
        if ($PageItems.Count -lt $PageLimit) { break }
        $Offset += $PageLimit
        Start-Sleep -Milliseconds 400
    }
} finally {
    if (Test-Path -LiteralPath $TmpDir) {
        Remove-Item -LiteralPath $TmpDir -Recurse -Force
    }
}

# ---- Incremental full-conversation capture ----
$StatePath = Join-Path $RawDir "state.json"
$State = @{}
$Pending = [System.Collections.Generic.List[string]]::new()
if (Test-Path -LiteralPath $StatePath) {
    try {
        $Old = Get-Content -Raw -LiteralPath $StatePath | ConvertFrom-Json
        if ($Old.seen) {
            foreach ($Prop in $Old.seen.PSObject.Properties) {
                $State[$Prop.Name] = [string]$Prop.Value
            }
        }
        if ($Old.pending) {
            foreach ($PendingId in @($Old.pending)) {
                $P = [string]$PendingId
                if ($P -and -not $Pending.Contains($P)) { $Pending.Add($P) }
            }
        }
    } catch { $State = @{} }
}

$NewCount = 0
$SkipCount = 0
$FailCount = 0
$ProjectMap = @{}

# Work queue: previously failed conversations resume first, then new items.
$UpdateMap = @{}
foreach ($Item in $Items) {
    if ($Item.id) { $UpdateMap[[string]$Item.id] = [string]$Item.update_time }
}

# Reconcile: conversations already on disk (from a run that was killed before
# the final state write) count as seen so we never re-fetch them.
$Reconciled = 0
foreach ($Item in $Items) {
    $Id = [string]$Item.id
    if (-not $Id) { continue }
    if ($State.ContainsKey($Id)) { continue }
    $ExistingFile = Join-Path $RawDir ("conv_" + $Id + ".json")
    if (Test-Path -LiteralPath $ExistingFile) {
        $State[$Id] = [string]$Item.update_time
        $Reconciled++
    }
}

$WorkQueue = [System.Collections.Generic.List[object]]::new()
$QueuedIds = [System.Collections.Generic.HashSet[string]]::new()

foreach ($PendingId in $Pending) {
    $PendingTitle = ""
    if ($UpdateMap.ContainsKey($PendingId)) { $PendingTitle = $UpdateMap[$PendingId] }
    if ($WorkOnly -and -not (Test-WorkTitle -Title $PendingTitle)) { continue }
    if ($QueuedIds.Add($PendingId)) {
        $WorkQueue.Add([pscustomobject]@{ id = $PendingId; update_time = ""; project_id = "" })
    }
}

foreach ($Item in $Items) {
    $Id = [string]$Item.id
    if (-not $Id) { continue }
    $Update = [string]$Item.update_time
    if ($Item.project_id) {
        $ProjectMap[$Id] = @{
            id    = [string]$Item.project_id
            title = [string]$Projects[[string]$Item.project_id]
        }
    }

    if (-not $Force -and $State.ContainsKey($Id) -and $State[$Id] -eq $Update) {
        $SkipCount++
        continue
    }
    if (-not $QueuedIds.Add($Id)) { continue }
    $WorkQueue.Add($Item)
}

if ($MaxItems -gt 0 -and $WorkQueue.Count -gt $MaxItems) {
    $WorkQueue = $WorkQueue.GetRange(0, $MaxItems)
}

$NewPending = [System.Collections.Generic.List[string]]::new()
# playwright-cli --filename is restricted to the workspace, so conversation
# payloads are staged inside the cache folder first, then moved into the WPS
# cloud raw directory. Direct writes to the WPS path would be rejected.
$ConvStagingDir = Join-Path $ConfigDir (".playwright-cli\chatgpt_conv_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $ConvStagingDir | Out-Null
try {
    $Stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    foreach ($Item in $WorkQueue) {
        if ($TimeBudgetSeconds -gt 0 -and $Stopwatch.Elapsed.TotalSeconds -ge $TimeBudgetSeconds) {
            Write-Output "TIME_BUDGET_REACHED"
            break
        }
        $Id = [string]$Item.id
        if (-not $Id) { continue }
        $Update = [string]$Item.update_time
        $ConvFile = Join-Path $RawDir ("conv_" + $Id + ".json")
        $StagingFile = Join-Path $ConvStagingDir ("conv_" + $Id + ".json")
        $ConvCode = "async () => { const tok = window.__chatgptTok || ''; const r = await fetch('/backend-api/conversation/$Id', {credentials:'include', headers:{'Authorization':'Bearer ' + tok}}); if (!r.ok) throw new Error('HTTP ' + r.status); return await r.json(); }"
        $Ok = $false
        $LastError = ""
        for ($Attempt = 1; $Attempt -le 3; $Attempt++) {
            try {
                if ([System.IO.File]::Exists($StagingFile)) {
                    [System.IO.File]::Delete($StagingFile)
                }
                $EvalOut = (& $PlaywrightCli --raw -s=$Session eval --filename $StagingFile $ConvCode 2>&1 | Out-String)
                if ($EvalOut -match "429") {
                    $LastError = "rate_limited"
                    Start-Sleep -Seconds (30 * $Attempt)
                    continue
                }
                if (-not (Test-Path -LiteralPath $StagingFile)) {
                    $LastError = "file_not_written"
                    Start-Sleep -Seconds 5
                    continue
                }
                if ((Get-Item -LiteralPath $StagingFile).Length -lt 10) {
                    $LastError = "empty_response"
                    Start-Sleep -Seconds 5
                    continue
                }
                [System.IO.File]::Copy($StagingFile, $ConvFile, $true)
                # Attach project metadata next to the payload for the ingester.
                if ($Item.project_id) {
                    $MetaPath = Join-Path $RawDir ("conv_" + $Id + ".meta.json")
                    $MetaJson = @{ project_id = [string]$Item.project_id; project_title = [string]$Projects[[string]$Item.project_id] } |
                        ConvertTo-Json
                    [System.IO.File]::WriteAllText($MetaPath, $MetaJson, (New-Object System.Text.UTF8Encoding($false)))
                }
                # Use the real update_time from the list when available so a
                # resumed pending item does not get refetched next run.
                $RealUpdate = ""
                if ($UpdateMap.ContainsKey($Id)) { $RealUpdate = $UpdateMap[$Id] }
                $State[$Id] = $RealUpdate
                $NewCount++
                $Ok = $true
                break
            } catch {
                $LastError = $_.Exception.Message
                Start-Sleep -Seconds 5
            }
        }
    if (-not $Ok) {
        $FailCount++
        if (-not $NewPending.Contains($Id)) { $NewPending.Add($Id) }
        Write-Output "FAIL_CONV $Id $LastError"
    }
    # Incremental state save: even if the process is killed mid-run, progress
    # is preserved and already-downloaded conversations are never refetched.
    $StateJson = @{ seen = $State; pending = @($NewPending); last_run = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") } |
        ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($StatePath, $StateJson, (New-Object System.Text.UTF8Encoding($false)))
    Start-Sleep -Milliseconds 3000
}
    # Items left unprocessed when the budget cut us off must be retried later.
    if ($TimeBudgetSeconds -gt 0 -and $Stopwatch.Elapsed.TotalSeconds -ge $TimeBudgetSeconds) {
        for ($i = $NewCount + $FailCount; $i -lt $WorkQueue.Count; $i++) {
            $RemainingId = [string]$WorkQueue[$i].id
            if ($RemainingId -and -not $NewPending.Contains($RemainingId)) {
                $NewPending.Add($RemainingId)
            }
        }
    }
} finally {
    if (Test-Path -LiteralPath $ConvStagingDir) {
        Remove-Item -LiteralPath $ConvStagingDir -Recurse -Force
    }
}

$StateJson = @{ seen = $State; pending = @($NewPending); last_run = (Get-Date -Format "yyyy-MM-ddTHH:mm:ss") } |
    ConvertTo-Json -Depth 8
[System.IO.File]::WriteAllText($StatePath, $StateJson, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "CAPTURE_DONE"
Write-Output "LISTED=$($Items.Count) TITLE_SKIPPED=$TitleSkipped QUEUED=$($WorkQueue.Count) RECONCILED=$Reconciled NEW=$NewCount SKIP=$SkipCount FAIL=$FailCount"
Write-Output "RAW_DIR=$RawDir"
