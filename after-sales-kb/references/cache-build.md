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
   - 脚本会先尝试提取 PDF 内嵌文字层（通过临时 JSON 传递，避免编码损坏）；文字层过短/缺失的页面自动以 300 DPI 渲染后逐页 OCR；页码标记按 1..N 顺序写入。
   - 旧版缓存升级时，先运行一次页码迁移，再重建索引：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\migrate_ocr_page_markers.py"
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
7. 坏页视觉修复（自动，无需手动提示词）：扫描 OCR 中疑似坏页（空页 / 规格表标签或数值缺失），对命中页面图调用识图模型逐字读取并合并回 OCR 索引：
   ```powershell
   # 1) 只列出需要修复的坏页（全库：约百页量级，多为空 OCR 页）
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\repair_ocr_vision.py" plan
   # 2) 视觉修复（优先当前模型识图；无识图模型时自动回退 vision-skill）
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\repair_ocr_vision.py" run --workers 2
   # 默认只修规格表/参数页等“内容坏但值得修”的页面；若要连空白页一起修，
   # 加 --include-empty（全库可能数百页，耗时与额度显著增加）
   # 3) 合并修复结果到 ocr_repair/overlay.tsv（build_quick_index 自动优先采用）
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\repair_ocr_vision.py" merge
   # 或一条命令完成 plan + run + merge：
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\repair_ocr_vision.py" all --workers 2
   ```
   - 坏页判定规则：空 OCR（规范化长度 <30）；规格表页（出现 仕様/規格 + 品名/品番/製品型番）但没有任何参数数值；规格书文件中无数值的参数页。
   - 提示词已内置于脚本（逐字原样读取标签与数值，不概括），日常操作不需要手动输入复杂提示词。
   - 修复结果不覆盖原始 OCR，只写入 `ocr_repair/`；`build_quick_index.py` 构建时自动把修复文本叠加到对应页，缺失/乱码的规格数值即可被检索命中。
   - 若本机模型带识图功能，可运行 `plan` 后直接查看 `ocr_repair/todo.tsv` 中的页面图，由模型逐页读取并追加到 `ocr_repair/repairs.tsv`（列：pdf_base / page_seq / image_rel / text / model / status=ok / generated_at），再运行 `merge`；此路径不消耗第三方 API。
8. （可选，仅用户明确要求时运行）建立视觉语义索引：识图消耗 API 额度，默认不建。用户要求全量识图时再按以下方式运行，并先提示耗时与额度消耗：
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
9. 生成产品映射与 FAQ 索引：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_products.py"
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_faq_index.py"
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_facts.py"
   ```
10. 生成快速查询预索引（日常问答默认入口，必须在索引/OCR 更新后重跑）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_quick_index.py"
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_faq_lookup.py"
   ```
   - 输出：`faq_norm.tsv`（FAQ 规范化）、`ocr_pages.tsv`（按页粒度 OCR 索引）、`ocr_sources.tsv`（OCR 页数/长度诊断）、`kdocs_norm.tsv`、`spec_norm.tsv`（规格书 xlsx+PDF 文字层）、`params_norm.tsv`（参数行层：线长/尺寸/功率/电压/容量/配件等）、`param_seeds.tsv`（人工核验参数种子表，可自行增行后重建）、`synonyms.tsv`（中→日同义词词典，支持短语级扩展）。
   - `faq_lookup.json`：**预编译 FAQ 查表**（产品+问题关键词 → 完整日文模板，约 1-2 秒生成，无 OCR/识图/联网），日常 FAQ 问题走字典直查，最快路径。
   - 日常查询使用 `quick_query.ps1 -Product <产品> -Q <问题>`：先查 `faq_lookup.json` 预编译表 → 同义词扩展（短语级）→ 精确匹配（命中词越长越优先）→ 模糊匹配（rapidfuzz）→ BM25 排序，一次聚合 FAQ/OCR/kdocs/SPEC/PARAMS 五源；`-Diagnose` 输出未命中分层诊断，并列出 `CANDIDATE_IMAGES`（与查询词相关的具体页面图，供定向识图）。
11. 生成轻量知识图谱（用于校验收录完整性和兜底定位）：
    ```powershell
    powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\build_kb_graph.py"
    ```
    - 输出 `kb_graph/nodes.tsv`、`edges.tsv`、`summary.json`（产品↔FAQ/说明书/规格书/页面图/视频 的关系网，及无 FAQ/无 OCR/无视频 的缺口清单）。
12. （维护用）生成知识缺口报告：
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
7. 对新增文件运行坏页视觉修复（repair_ocr_vision.py plan → run → merge），只处理新坏页（脚本自动跳过已修复页面）。
8. 重新运行 build_quick_index.py 与 build_faq_lookup.py 重建快速查询预索引与 FAQ 查表。
9. 运行 build_gap_report.py 复查知识缺口（空 OCR / 无 FAQ / 未命中）。
10. 更新后重新查询触发增量更新的问题。

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
