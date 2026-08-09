# 缓存构建

所有构建脚本从 `%LOCALAPPDATA%\AfterSalesSupport\config\settings.json` 解析 `data_root` 与 `cache_root`。源资料只读，输出只写入缓存目录。

## 首次构建

1. 运行 `scripts/initialize.ps1` 并确认 `DATA_ROOT`、`CACHE_ROOT`。
2. 运行 `scripts/build_cache.ps1 -Mode Auto`。它自动复用旧缓存；空缓存执行 WPS/XLSX 文本导入、视频索引、说明书文字层/OCR、PDF 页图和全部派生索引。
3. 中断后重复同一命令。已完成的 OCR 与页图会跳过，状态保存在 `cache_root/build_state/last_build.json`，日志保存在 `cache_root/logs/`。
4. 运行 `check_environment.ps1` 和代表性 `quick_query.ps1`；`ENVIRONMENT_OK` 且查询命中才算完成。

使用安装 Skill 中的 `py.ps1` 启动 Python 脚本，例如：

```powershell
$scriptRoot = Join-Path $env:USERPROFILE ".agents\skills\after-sales-kb-maintain\scripts"
& (Join-Path $scriptRoot "build_cache.ps1") -Mode Auto
```

## 增量构建

`-Mode Refresh` 只重新导入本地售后表并刷新派生索引；`-Mode Full` 还补齐缺少的 PDF OCR 和页图。日常问答不触发构建。

## 视觉索引

默认依赖 OCR 与现有页面索引。只有用户明确要求全量识图，或文字证据不足且用户同意定向识图时才运行视觉脚本；运行前说明耗时和可能的 API 费用。
