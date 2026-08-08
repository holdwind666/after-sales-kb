# 故障排查

## 没有自动找到资料目录

运行 `scripts/initialize.ps1`。返回 `NEED_DATA_ROOT` 时询问准确根目录；返回 `NEED_DATA_ROOT_CHOICE` 时把候选列给用户选择。有效目录应在 `说明书`、`演示视频`、`售后常用图片` 中至少包含两类。

## 安装后没有触发

确认三个目录都存在于当前用户的 `.agents\skills`，且各自包含 `SKILL.md`。新开一轮对话；仍未出现时重启 Codex。检查旧版 `after-sales-kb` 是否已从 Skill 目录迁到备份，避免重复名称或触发冲突。

## 快速查询返回 NOT_INITIALIZED

运行 `scripts/initialize.ps1`，检查 `%LOCALAPPDATA%\AfterSalesSupport\config\settings.json` 中的 `data_root` 和 `cache_root` 是否存在。

## 快速查询返回 NOT_FOUND

先运行 `quick_query.ps1 -Q "<问题>" -Diagnose`。只对诊断指出的产品、文档或页面做增量修复；连续未命中达到阈值时提醒一次增量更新。

## Python 或 PDF 渲染器缺失

`scripts/py.ps1` 会依次寻找 Python Launcher、系统 Python 和 Codex 工作区运行时。PDF 构建脚本会从 PATH 和当前用户的 Codex 运行时目录寻找 `pdftoppm.exe`。运行 `scripts/check_environment.ps1` 获取明确状态。

## WPS 不可访问

让用户本人在浏览器或 WPS 客户端登录并确认权限。不要请求密码、Cookie 或令牌。WPS 暂不可用时继续使用本机缓存，并向用户说明缓存生成时间。

## 学习案例没有同步

检查本机配置的 `cloud_learning_root` 是否存在，然后运行 `after-sales-learning-review/scripts/sync_learning.ps1`。共享目录按设备分别追加事件，不直接覆盖其他电脑文件。
