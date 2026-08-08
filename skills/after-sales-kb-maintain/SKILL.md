---
name: after-sales-kb-maintain
description: 安装、初始化、检查、更新和修复日本站售后知识库。用于新电脑收到 GitHub 仓库链接后安装全部售后 Skills、自动寻找名称包含“说明书与视频”的资料目录、配置不同电脑的本地路径与设备标识、建立或增量更新缓存索引、检查 WPS 登录和共享学习库、处理检索未命中、环境故障或版本升级。日常顾客回复使用 after-sales-reply；学习审批使用 after-sales-learning-review。
---

# 售后知识库维护

把安装、路径、缓存和更新当作一个可恢复的维护流程。日常问答不运行本 Skill 的全量任务。

## 初始化

1. 运行 `scripts/initialize.ps1`。已有有效配置时直接复用。
2. 脚本返回 `NEED_DATA_ROOT` 时，询问本机“说明书与视频”资料根目录；返回多个候选时让用户选择。
3. 需要权限的 WPS 资料只让用户本人在浏览器登录。保存链接或本机同步目录，不保存密码、Cookie 或令牌。
4. 快速索引存在时运行代表性查询完成验收；缺失时按 [references/cache-build.md](references/cache-build.md) 建立首次全量缓存。
5. 运行 `scripts/check_environment.ps1`，逐项解决失败项；以 `ENVIRONMENT_OK` 为完成标准。

每台电脑把配置写到 `%LOCALAPPDATA%\AfterSalesSupport\config\settings.json`。共享资料中不写 Windows 用户名、盘符或本机绝对路径。

## 路径发现

按以下顺序定位资料：

1. 读取本机配置中的 `data_root` 并校验。
2. 检查当前项目目录及有限层级父目录。
3. 在固定磁盘执行有深度限制的候选搜索，目录名需包含“说明书与视频”。
4. 用 `说明书`、`演示视频`、`售后常用图片` 三类内容校验候选；至少命中两类。
5. 单个候选自动采用；多个候选让用户选择；没有候选时主动询问准确路径。

## 缓存策略

- 日常查询只读 `cache_root/quick_index`，不重复扫描 PDF、视频或大型 XLSX。
- 首次安装允许全量构建；后续只处理新增或变更文件。
- 现有资料根目录下的 `_售后模板缓存` 有有效索引时优先复用，避免重复构建；新电脑默认使用 `%LOCALAPPDATA%\AfterSalesSupport\cache`。
- 图片语义索引、全量视频抽帧和在线表整表下载只在用户明确要求或首次构建确实需要时运行。
- 详细构建顺序读取 [references/cache-build.md](references/cache-build.md)。故障处理读取 [references/troubleshooting.md](references/troubleshooting.md)。

## 更新与修复

当用户再次发送仓库链接、要求更新或检测到版本变化时，运行仓库 `installer/update.ps1`。更新必须：

- 备份当前 Skill 文件后原子替换；
- 保留 `settings.json`、缓存、设备标识和学习事件；
- 失败时继续使用上一可用版本；
- 在下一轮对话使用新 Skill，未识别时再重启 Codex。

## 完成输出

只向用户报告：安装版本、资料目录、缓存状态、WPS 状态、代表性查询结果和仍需用户处理的事项。不要让客服阅读脚本日志。
