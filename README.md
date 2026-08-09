# 日本站售后客服助手

面向 Amazon 日本站售后的 Codex Skill 套件。它使用每台电脑上的本地说明书、WPS 售后规则和已批准案例，快速生成可直接发送的日文回复，并提供跨电脑初始化、缓存维护和“客服确认后学习”。

## 新电脑一句话安装

在 Codex 中发送：

> 请从 https://github.com/holdwind666/after-sales-kb.git 安装或更新全部售后客服 Skills，并运行 installer/bootstrap.ps1 完成初始化、知识库构建和代表性查询验收；保留本机配置与缓存。只有看到 READY_FOR_SUPPORT 和 BOOTSTRAP_COMPLETE 才告诉我安装完成；找不到名称包含“说明书与视频”的资料目录时，只询问我一次正确路径并继续执行。

Codex 会下载公开仓库并运行 `installer/bootstrap.ps1`。用户不需要下载 ZIP、安装 EXE、打开 PowerShell或手动复制文件。入口会依次完成校验、安装、路径发现、初始化、缓存构建、环境检查和代表性查询；安装后通常在下一轮对话生效，未出现时重启一次 Codex。

已有 `_售后模板缓存` 时只刷新快速索引，通常很快；全新电脑没有缓存时会完整处理本地 PDF，耗时取决于说明书数量，中断后再次运行会从已有结果继续。WPS 表格若已同步为本地 XLSX 会自动导入；只有既没有本地副本也没有既有 WPS 缓存时，流程会停在 `WPS_CACHE=NOT_AVAILABLE` 并提示补充资料，不会把它伪装成完整可用。

同一个 Codex 账号登录多台电脑不会自动同步本地 Skill 文件。每台新电脑都发送一次上面的指令即可；WPS 账号可以相同，本机路径、缓存、日志和设备标识各自独立。

## 日常使用

直接发送顾客原文，最好附上产品型号：

```text
顾客说：充電できない
产品：06 switch 手柄
```

默认返回：

1. 可直接发送的日文回复；
2. 必要的内部处理建议；
3. 简短参考来源。

日常查询只读预构建快速索引，不重复扫描 PDF、视频或大型 XLSX。

## 三个 Skills

- `after-sales-reply`：识别顾客问题、快速检索并生成日文回复。
- `after-sales-kb-maintain`：安装、路径发现、缓存构建、更新和故障修复。
- `after-sales-learning-review`：创建学习候选，并在客服批准后发布到正式检索库。

未批准候选不会参与回复。系统会自动记录有价值的候选，高价值候选只提示一行；客服回复“确认学习”后才正式生效。

## 安装与更新脚本

首次安装：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\bootstrap.ps1
```

更新或修复：

```powershell
powershell -ExecutionPolicy Bypass -File .\installer\update.ps1
```

脚本可重复运行。更新前备份现有 Skills，保留 `%LOCALAPPDATA%\AfterSalesSupport\` 下的配置、缓存、设备标识和学习事件；旧版单一 `after-sales-kb` Skill 会先备份再停用，避免重复触发。

## 路径与数据

每台电脑的配置位于：

```text
%LOCALAPPDATA%\AfterSalesSupport\config\settings.json
```

初始化会优先复用有效配置，然后检查当前项目及有限层级父目录，最后在固定磁盘有限深度内寻找名称包含“说明书与视频”的候选。单个有效候选自动采用；多个候选让用户选择；没有候选时询问准确路径。

仓库只包含 Skill、脚本、空白配置和测试所需结构，不包含顾客信息、WPS 登录信息、在线表格副本、本机缓存、真实学习案例或公司敏感规则。公开仓库链接并不等于私密；真实业务资料继续保存在本机和有权限的 WPS 空间。

## 仓库结构

```text
after-sales-kb/
├── .codex-plugin/plugin.json
├── skills/
│   ├── after-sales-reply/
│   ├── after-sales-kb-maintain/
│   └── after-sales-learning-review/
├── installer/
│   ├── bootstrap.ps1
│   ├── install.ps1
│   └── update.ps1
├── install-manifest.json
└── README.md
```

本项目不提供也不需要 Windows EXE。
