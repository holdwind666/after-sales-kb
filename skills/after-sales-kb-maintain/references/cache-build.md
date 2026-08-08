# 缓存构建

所有构建脚本从 `%LOCALAPPDATA%\AfterSalesSupport\config\settings.json` 解析 `data_root` 与 `cache_root`。源资料只读，输出只写入缓存目录。

## 首次构建

1. 运行 `scripts/initialize.ps1` 并确认 `DATA_ROOT`、`CACHE_ROOT`。
2. 抓取用户已授权的 WPS 售后表文本到 `cache_root/kdocs`；需要大型 XLSX 图片索引时再下载整表。
3. 对说明书 PDF 建立文字层/OCR 和页面图，随后运行 `build_manual_images.py`。
4. 建立产品、FAQ 与事实层：`build_products.py`、`build_faq_index.py`、`build_facts.py`。
5. 建立快速层：`build_quick_index.py`、`build_faq_lookup.py`、`build_kb_graph.py`、`build_gap_report.py`。
6. 运行 `check_environment.ps1` 和两个代表性 `quick_query.ps1` 查询；`ENVIRONMENT_OK` 且查询命中才算完成。

使用安装 Skill 中的 `py.ps1` 启动 Python 脚本，例如：

```powershell
$scriptRoot = Join-Path $env:USERPROFILE ".agents\skills\after-sales-kb-maintain\scripts"
& (Join-Path $scriptRoot "py.ps1") (Join-Path $scriptRoot "build_quick_index.py")
& (Join-Path $scriptRoot "py.ps1") (Join-Path $scriptRoot "build_faq_lookup.py")
```

## 增量构建

比较文件路径、大小和修改时间，只重建新增或变化的源文件，再刷新快速索引和缺口报告。日常问答不触发全量 OCR、全量视频抽帧、整表下载或全磁盘扫描。

## 视觉索引

默认依赖 OCR 与现有页面索引。只有用户明确要求全量识图，或文字证据不足且用户同意定向识图时才运行视觉脚本；运行前说明耗时和可能的 API 费用。
