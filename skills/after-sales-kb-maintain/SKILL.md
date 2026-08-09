---
name: after-sales-kb-maintain
description: 安装、初始化、检查、更新和修复日本站售后知识库。用于用户发送仓库链接并要求安装或初始化、新电脑没有本地/WPS 缓存、登录不同 WPS 账号、需要自动发现“说明书与视频”目录、建立或更新本机索引、处理检索未命中、环境故障或版本升级。日常顾客回复使用 after-sales-reply；学习审批使用 after-sales-learning-review。
---

# 售后知识库维护

把安装、路径、缓存和更新当作一个可恢复的维护流程。日常问答不运行本 Skill 的全量任务。

## 初始化

1. 把每台电脑作为对等本地节点；在本机独立发现资料、建立缓存并保留使用习惯，不指定中央电脑。
2. 运行 `scripts/initialize.ps1`。已有有效配置时直接复用。
3. 脚本返回 `NEED_DATA_ROOT` 时，询问本机“说明书与视频”资料根目录；返回多个候选时让用户选择。
4. 运行 `scripts/build_cache.ps1 -Mode Auto`：已有缓存只刷新索引，空缓存自动执行可恢复的完整构建。
5. 导入当前电脑可访问的 WPS 本地 XLSX 或既有文字缓存。没有 WPS 缓存、账号不同或无权限时继续构建本地说明书层，标记 `READY_LOCAL_ONLY`；获得 WPS 资料后增量升级为 `READY_WITH_WPS`。登录只由用户本人完成，不保存密码、Cookie 或令牌。
6. 运行 `scripts/check_environment.ps1`，逐项解决失败项；以 `ENVIRONMENT_OK` 为环境完成标准。

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
- 每台电脑独立维护本地缓存；不依赖其他电脑的路径、WPS 登录态或缓存副本。
- 首次安装允许全量构建；后续只处理新增或变更文件。
- 现有资料根目录下的 `_售后模板缓存` 有有效索引时优先复用，避免重复构建；新电脑默认使用 `%LOCALAPPDATA%\AfterSalesSupport\cache`。
- 图片语义索引、全量视频抽帧和在线表整表下载只在用户明确要求或首次构建确实需要时运行。
- 详细构建顺序读取 [references/cache-build.md](references/cache-build.md)。故障处理读取 [references/troubleshooting.md](references/troubleshooting.md)。

## 一键安装验收

从 GitHub 下载仓库后，优先运行仓库的 `installer/bootstrap.ps1`，不要分别让用户执行多个脚本。它负责校验并安装三个 Skills、发现资料目录、初始化、完整或增量构建、环境检查和代表性查询。输出 `KB_STATE=READY_WITH_WPS` 或 `KB_STATE=READY_LOCAL_ONLY`，并同时输出 `READY_FOR_SUPPORT` 与 `BOOTSTRAP_COMPLETE` 后才能报告可用；`NEED_DATA_ROOT` 或多个候选时只询问一次正确路径，再用 `-DataRoot` 重跑同一入口。

## 更新与修复

当用户再次发送仓库链接、要求更新或检测到版本变化时，运行仓库 `installer/update.ps1`。更新必须：

- 备份当前 Skill 文件后原子替换；
- 保留 `settings.json`、缓存、设备标识和学习事件；
- 失败时继续使用上一可用版本；
- 在下一轮对话使用新 Skill，未识别时再重启 Codex。

## 完成输出

只向用户报告：安装版本、资料目录、本机知识库状态、缓存状态、WPS 状态、代表性查询结果和仍需用户处理的事项。不要让客服阅读脚本日志。
