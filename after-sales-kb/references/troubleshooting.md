# 故障排查（面向电脑小白）

如果技能无法工作，按顺序检查以下项目。每一步给出用户可以照做的操作。

## 1. 缓存目录不存在

症状：找不到 `_售后模板缓存` 文件夹。

解决：
1. 询问用户“说明书与视频”所在文件夹地址（例如 `E:\说明书与视频（第9台）`）。
2. 确认该文件夹下有 `说明书`、`演示视频`、`售后常用图片` 子文件夹。
3. 在该根目录下创建 `_售后模板缓存`，按 references/cache-build.md 执行首次全量缓存。

## 2. 在线表格打不开 / 提示登录

症状：抓取在线表格时跳转到登录页，或提示“文档需要登录查看”。

解决：
1. 让用户打开 Chrome 浏览器，访问 WPS 在线表格链接。
2. 用户本人扫码或输入账号登录（不要使用账号密码自动登录，也不要替用户填写）。
3. 登录成功后保持 Chrome 窗口打开。
4. 再用持久化 Chrome 会话（playwright-cli `-s=wps`）打开链接，确认页面标题是“日本站售后对应方案表”。

## 3. 表格能打开但抓取内容为空/全表相同

症状：所有工作表抓出来内容一样，或某个表为空。

解决：
1. 确认抓取脚本使用 ref 点击工作表（见 cache-build.md），不要用页面内合成 click。
2. 切换工作表后等待 2~3 秒再复制。
3. 复制内容小于 50 字符视为失败，重试该表。

## 4. OCR 结果为空或只有几字节

症状：pdf_ocr 下某文件只有 `===== PAGE 1 =====` 或几字节。

解决：
1. 该 PDF 可能是中文/日文路径导致切块失败，使用修复版 ocr_worker.ps1（通过 UTF-8 文件传递切块路径）。
2. 若文本层是 CID 乱码，用 `-ForceOcr` 参数强制渲染识别。
3. 若渲染像素超限，降低渲染 DPI（120）并缩放后识别。

## 5. 查询很慢

症状：每次回答要 10 秒以上。

解决：
1. 确认 `_售后模板缓存` 下已有 `products.tsv`、`faq/`、`facts/` 索引（快速路径）。
2. 避免每次全量扫描 kdocs/ 和 pdf_ocr/；先走快速索引路径。
3. 若索引缺失，按 cache-build.md 重建。
4. 确认调用的是 `quick_query.ps1` 封装，而不是直接敲 `python`：
   - 本机 PATH 中的 `python.exe` 可能是 WindowsApps 占位程序，调用后**无任何输出、退出码 1**，会让查询看起来卡住；
   - 统一用 `powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\quick_query.ps1" -Product "<产品>" -Q "<问题>"`；
   - 封装内部固定使用 Codex 自带 Python（`C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe`），不存在时才回退 `py.exe`。

## 5a. quick_query 调用后无输出 / 退出码 1

症状：运行 `python quick_query.py ...` 后没有任何输出，或第一轮查询正常、偶尔没反应。

解决：
1. 不要再用裸 `python` 调用任何技能脚本；
2. 改用 `quick_query.ps1`（或通用 `py.ps1`）入口；
3. 运行 `check_environment.ps1` 确认 Codex 自带 Python 存在；
4. 若封装本身报错，把报错原文贴给 Codex。

## 6. 未命中计数不生效

症状：连续 3 次未命中没有提醒。

解决：
1. 检查 `_售后模板缓存/miss_counter.json` 是否存在。
2. 用 `powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" "_售后模板缓存\scripts\miss_tracker.py" status` 查看计数。
3. 确认每次未命中都执行了 `record` 操作。

注：满 3 次未命中后，如果用户没有执行增量更新，之后的每一次未命中都会继续提醒；只有用户实际完成增量更新并运行 `miss_tracker.py update-done` 后才会重置。

## 6a. 检索变慢 / 命中率下降

症状：日常问答回复生成时间明显变长，或明明库里有的内容却显示未命中。

解决：
1. 日常文字问答默认只运行 `quick_query.ps1 -Product <产品> -Q <问题>` 一次（目标 <200ms），命中即答，禁止再做额外验证命令；
2. OCR 检索前必须先去除文本空格再匹配（如 `付 属 品` → `付属品`）；
3. 未命中时按“主动告知 + 可选深入”流程处理，等用户选择后才继续，不要自动深挖；
4. 未命中时可用 `quick_query.ps1 -Q "<问题>" -Diagnose` 查看分层诊断（OCR 页数/长度、PDF 文本层、页面图路径），判断内容丢在哪一层；
5. 确认 `rank-bm25` / `rapidfuzz` 已安装（混合检索依赖），缺失时 `powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\py.ps1" -m pip install rank-bm25 rapidfuzz`；
6. 若问题跨多产品/多文档且快查 NOT_FOUND，才考虑并行派 2 个子代理兜底（FAQ/kdocs + OCR/说明书）。

## 6b. 非产品类问题查不到

症状：问的是售后政策、刷单规则、工作注意事项，但产品 FAQ/说明书里没有。

解决：
1. 确认已按问题分类走非产品类路径：直接查 `kdocs/售后原则.txt` / `kdocs/刷单原则.txt` / `kdocs/各注意事项.txt`；
2. 用 `quick_query.ps1 -Q "<关键词>"`（不指定 -Product）全库扫描，命中这三个表的 kdocs 层；
3. 仍无结果时，可能是这三个表未抓取或缓存过期，按 cache-build.md 重新抓取在线表格全部工作表。

## 7. 自动更新未配置

症状：用户没有配置过更新频率。

解决：
1. 首次初始化时按向导询问：每周一次（推荐）/每天一次/暂不自动更新；
2. 指定星期几或时间点（如 每周一 09:00）；
3. 选择“暂不自动更新”后，用户说“开启自动更新”再引导创建定时任务。

## 8. 需要识图但会话不具备识图能力

症状：需要分析说明书页图/WPS 内嵌图，但会话无法直接查看图片（例如读图工具返回不支持）。

解决：
1. 优先尝试会话识图能力；确认不具备时走 vision-skill（注意：本会话图片预览偶发失败时不要反复重试，直接改用 OCR 文本核对，必要时按需识图）；
2. 检查 `C:\Users\ASUS\.codex\skills\vision-skill\scripts\vision.js` 是否存在；
3. 已安装：直接运行 `build_vision_index.py` 或 `vision.js` 接入第三方识图 API；
4. 未安装：明确提示“本会话不具备识图能力，需要安装 vision-skill 技能接入第三方识图 API 后继续”。

## 9. 本地 xlsx 太大 / 查询变慢

症状：`日本站售后对应方案表 .xlsx` 约 300MB，读起来很慢。

解决：
1. 日常文字查询只走 products/faq/facts/kdocs/pdf_ocr，不读 xlsx；
2. 图片查询先查 `xlsx_image_index/images.tsv` 拿位置，不直接解包；
3. 用户要求下载图片时，用 `build_xlsx_image_index.py --extract <ID>` 只解单张；
4. 整表只在首次初始化/更新时重新下载。

## 10. 其他环境缺失

技能依赖以下工具，缺失时按提示安装：
- Python（含 pdfplumber、PIL）：统一通过 `scripts/py.ps1` 使用 Codex 自带运行时，禁止直接敲 `python`。
- Poppler（pdftoppm / pdfinfo）：用于 PDF 渲染与页面图。
- Chrome 浏览器：用于打开 WPS 在线表格。
- playwright-cli：用于持久化浏览器会话。
- vision-skill（可选）：会话不具备识图能力时，用于接入第三方识图 API。
