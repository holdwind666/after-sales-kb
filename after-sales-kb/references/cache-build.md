# 缓存构建与增量更新

所有缓存写入 `_售后模板缓存` 目录，严禁修改源文件夹。

## 首次全量构建

1. 抓取在线表格全部工作表：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\capture_kdocs_sheets.ps1" -CacheDir "_售后模板缓存\kdocs"
   ```
2. OCR 全部说明书 PDF（并行 2~3 份加速）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\ocr_worker.ps1" -ListFile "<分片清单>" -OutDir "_售后模板缓存\pdf_ocr" -LogFile "<日志>"
   ```
3. 渲染每页 PDF 为图片（供顾客参考）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\build_pdf_pages.ps1" -ListFile "<PDF清单>" -OutDir "_售后模板缓存\pdf_pages" -RootDir "<说明书根目录>"
   ```
4. 建立视频/图片索引：
   ```powershell
   Get-ChildItem -Recurse -File "<根目录>\演示视频" -Include *.mp4,*.mov | % { "$($_.FullName)`t$($_.Length)" } | Set-Content "_售后模板缓存\video_index\videos.tsv"
   ```
5. 生成产品映射与 FAQ 索引：
   ```powershell
   python "_售后模板缓存\scripts\build_products.py"
   python "_售后模板缓存\scripts\build_faq_index.py"
   python "_售后模板缓存\scripts\build_facts.py"
   ```

## 增量更新（每周或按需）

1. 对比源目录文件清单，找出新增/修改的 PDF、视频、图片。
2. 只对新增文件执行 OCR 与页面图渲染（脚本会自动跳过已存在文件）。
3. 重新抓取在线表格全部工作表（约 10 分钟）。
4. 重新运行 build_products.py / build_faq_index.py / build_facts.py。
5. 更新后重新查询触发增量更新的问题。

## 只读约束

- 不修改源 PDF、视频、图片。
- 不修改在线表格内容（只读取）。
- 所有写入仅限 `_售后模板缓存`。
