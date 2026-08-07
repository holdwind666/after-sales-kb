# 缓存构建与增量更新

所有缓存写入 `_售后模板缓存` 目录，严禁修改源文件夹。

## 首次全量构建

0. 安装检索依赖（混合检索需要）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" -m pip install rank-bm25 rapidfuzz
   ```
1. 抓取在线表格全部工作表：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\capture_kdocs_sheets.ps1" -CacheDir "_售后模板缓存\kdocs"
   ```
2. 下载整张 WPS 在线表为本地 xlsx（一次性，约 300MB；通过页面“普通下载”按钮走浏览器下载通道，不要用后台导出 API 轮询）：
   - 保存为 `_售后模板缓存\日本站售后对应方案表 .xlsx`
   - 之后建立 DISPIMG 图片索引：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_xlsx_image_index.py" --xlsx "_售后模板缓存\日本站售后对应方案表 .xlsx" --out "_售后模板缓存\xlsx_image_index"
   ```
3. OCR 全部说明书 PDF（并行 2~3 份加速）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\ocr_worker.ps1" -ListFile "<分片清单>" -OutDir "_售后模板缓存\pdf_ocr" -LogFile "<日志>"
   ```
4. 渲染每页 PDF 为图片（供顾客参考）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\build_pdf_pages.ps1" -ListFile "<PDF清单>" -OutDir "_售后模板缓存\pdf_pages" -RootDir "<说明书根目录>"
   ```
5. 建立视频/图片索引：
   ```powershell
   Get-ChildItem -Recurse -File "<根目录>\演示视频" -Include *.mp4,*.mov | % { "$($_.FullName)`t$($_.Length)" } | Set-Content "_售后模板缓存\video_index\videos.tsv"
   ```
6. 建立说明书图文关联索引（OCR 段落 ↔ 页面图）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_manual_images.py"
   ```
7. （可选，仅用户明确要求时运行）建立视觉语义索引：识图消耗 API 额度，默认不建。用户要求全量识图时再按以下方式运行，并先提示耗时与额度消耗：
   ```powershell
   # 建议 4 分片 × 每片 2 路并发（共 8 路），不要直接 12 路以上（实测高并发会触发 API 排队变慢）
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_vision_index.py" --source all --split 4 --split-index 0 --workers 2 --shard p0
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_vision_index.py" --source all --split 4 --split-index 1 --workers 2 --shard p1
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_vision_index.py" --source all --split 4 --split-index 2 --workers 2 --shard p2
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_vision_index.py" --source all --split 4 --split-index 3 --workers 2 --shard p3
   # 分片全部完成后合并：
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_vision_index.py" --merge
   ```
   若 vision-skill 未安装，脚本会明确提示“本会话不具备识图能力，需安装 vision-skill 接入第三方 API”。
8. 生成产品映射与 FAQ 索引：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_products.py"
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_faq_index.py"
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_facts.py"
   ```
9. 生成快速查询预索引（日常问答默认入口，必须在索引/OCR 更新后重跑）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_quick_index.py"
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_faq_lookup.py"
   ```
   - 输出：`faq_norm.tsv`（FAQ 规范化）、`ocr_pages.tsv`（按页粒度 OCR 索引）、`ocr_sources.tsv`（OCR 页数/长度诊断）、`kdocs_norm.tsv`、`spec_norm.tsv`（规格书参数）、`synonyms.tsv`（中→日同义词词典）。
   - `faq_lookup.json`：**预编译 FAQ 查表**（产品+问题关键词 → 完整日文模板，约 1-2 秒生成，无 OCR/识图/联网），日常 FAQ 问题走字典直查，最快路径。
   - 日常查询使用 `quick_query.ps1 -Product <产品> -Q <问题>`：先查 `faq_lookup.json` 预编译表 → 同义词扩展 → 精确匹配 → 模糊匹配（rapidfuzz）→ BM25 排序，一次聚合四源；`-Diagnose` 可输出未命中的分层诊断。
10. （维护用）生成知识缺口报告：
    ```powershell
    powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_gap_report.py"
    ```

## 增量更新（每周或按需）

1. 对比源目录文件清单，找出新增/修改的 PDF、视频、图片。
2. 只对新增文件执行 OCR 与页面图渲染（脚本会自动跳过已存在文件）。
3. 重新抓取在线表格全部工作表（约 10 分钟）。
4. 需要更新图片时（或表格内容有新增图片）重新下载整表并重建 xlsx 图片索引。
5. 重新运行 build_manual_images.py（说明书图文关联）与 build_products.py / build_faq_index.py / build_facts.py。
6. 新增图片需要语义描述时，增量运行 build_vision_index.py（自动跳过已索引图片）。
7. 重新运行 build_quick_index.py 与 build_faq_lookup.py 重建快速查询预索引与 FAQ 查表。
8. 运行 build_gap_report.py 复查知识缺口（空 OCR / 无 FAQ / 未命中）。
9. 更新后重新查询触发增量更新的问题。

## 日常问答（图片策略）

- 文字类问题：默认运行 `scripts/quick_query.ps1 -Product <产品> -Q <问题>` 单命令快查（目标 <200ms）；命中即答，未命中才走兜底，不读取 300MB xlsx。
- 未命中时可用 `-Diagnose` 查看各层状态（OCR 页数/长度、PDF 文本层、页面图），判断内容丢在哪一层；若 OCR 为空且页面图存在，建议定向识图确认（用户同意后执行）。
- 图片类问题：先查 manual_image_index / xlsx_image_index / vision_index，**先报告图片位置**（工作表+单元格，或说明书文件名+页码）。
- 用户明确要求下载图片时才取图，并提前提示耗时。
- 未命中时：主动告知 + 提供顾客礼貌回复模板 + 可选深入项（识图/联网，注明预计耗时）；等用户选择后才继续，严禁自动深挖。

## 只读约束

- 不修改源 PDF、视频、图片。
- 不修改在线表格内容（只读取）。
- 所有写入仅限 `_售后模板缓存`。
