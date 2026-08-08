# ChatGPT 历史对话学习（越聊越强）

用途：把 ChatGPT 网页端项目里与**亚马逊工作相关**的历史对话（售后、运营、listing、竞品、库存、广告等，中文思路 + 日文回复模板）作为**一次性补数据**导入，沉淀到 WPS 云同步学习库，供 quick_query 检索；同时生成“虚拟客服角色卡”（persona.md）。

> 定位说明：**日常知识库成长不依赖本流程**。默认成长机制是“Codex 对话自动学习”——每次售后问答自动沉淀一条案例，无需登录、不受限流、零维护。本流程只在用户希望把网页端历史对话补进来时使用。

## 目录结构（WPS 云同步，两台电脑共享）

```
WPS云盘\售后AI学习库\            # 云端共享（两台电脑自动同步）
├── raw\                    # 抓取的原始对话（conv_<id>.json + meta）
├── corpus\                 # 构建产物：检索库 / 角色卡 / 模板对 / 审计报告
└── feedback\               # 人工反馈的成功案例（jsonl，每日一个文件）

_售后模板缓存\chatgpt_learning.json   # 每台电脑本地配置（含本机 WPS 云盘路径）
```

另一台电脑登录同一 WPS 账号后，`售后AI学习库` 会自动同步；每台电脑各自运行一次 `setup_chatgpt_learning.ps1` 生成指向本机云盘路径的本地配置，Codex 读本地路径，两边共享同一份学习成果。

## 两种学习方式（用户自行选择）

用户要求补历史对话时，把下表给用户看，让用户自己选，不替用户决定：

| 方案 | 用户需要做什么 | 预计耗时 | 复杂程度 | 说明 |
|---|---|---|---|---|
| **A：自动抓取（备选）** | 只在弹出的独立窗口登录一次 ChatGPT | 数百条约 1–3 小时（可分批续跑） | 低 | 全自动但慢，受 ChatGPT 限流影响明显；仅建议对话量少（几十条以内）时使用 |
| **B：浏览器扩展导出（推荐）** | 日常 Chrome 装扩展、点导出、把文件夹路径告诉 Codex | 约 5–15 分钟 | 中 | 导出快、不受限流影响、可只导出需要的项目；需装第三方扩展 |

选 A 后 Codex 运行 `run_chatgpt_learning.ps1 -WorkOnly`；选 B 后 Codex 运行 `import_chatgpt_export.ps1 -Source <导出文件夹>` 再构建。

## 首次学习（新电脑一条命令搞定）

```powershell
powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\run_chatgpt_learning.ps1" -WorkOnly
```

这条命令会自动完成：
1. 发现本机 WPS 云盘目录，自动创建 `售后AI学习库\raw|corpus|feedback` 并生成本地配置（无需手动跑 setup）；
2. 打开 ChatGPT 持久浏览器窗口；
3. 检测到未登录时，**自动等待你在窗口中登录**（默认等 10 分钟，可加 `-WaitLoginMinutes 30` 调整），登录完成后自动继续抓取和构建，不需要重跑；
4. 只抓标题像亚马逊工作的对话（`-WorkOnly`），数百条对话可能耗时 1–3 小时。

可选参数：
- `-TimeBudgetSeconds 1800`：每 30 分钟一批，剩余自动存 pending 下次续跑（仅 A 方案需要）；
- `-MaxItems 5`：先抓 5 条验证（推荐首次小批量测试）；
- `-WaitLoginMinutes 30`：登录等待时长；
- 去掉 `-WorkOnly` 则为全量抓取（不推荐，限流明显）。

> 为什么不用日常 Chrome 的登录态？playwright 使用独立浏览器 profile，与日常 Chrome 的 cookie 隔离，更安全也不干扰正常浏览。登录只需这一次，之后会话会保留登录态，增量抓取和定时任务都不再需要登录。

## 新电脑用户引导（给 Codex 的操作步骤）

新电脑首次初始化时，Codex **必须主动说明一次**，用以下完整话术（两件事一起讲）：

> “第一，**日常自动学习**：以后每次在这里处理售后问答，系统会自动把这次处理存进知识库，不需要你做任何操作，越用越准。
> 第二，**可选的历史对话导入**：如果你在 ChatGPT 网页端有过往的亚马逊工作对话，可以一次性补进来，约 5–15 分钟，能多出上百条可参考模板。想现在补就说‘导入 ChatGPT 对话’；不想现在补也没关系，日常自动学习已经生效。”

不主动推动、不反复追问；用户说“导入 ChatGPT 对话”后再进入方案选择。

用户同意后（或用户主动说“学习 ChatGPT 里的对话”）：

1. 确认 `_售后模板缓存` 已存在（未建则先完成缓存构建）。
2. **先把 A/B 方案表给用户看，让用户选择**（见上表；默认推荐 B）。
3. 选 A：由 Codex 运行 `run_chatgpt_learning.ps1 -WorkOnly`（用户不用手动 setup）；若窗口打开后未登录，请用户在窗口中登录（不要代替输入账号密码），脚本会自动等待并继续。
4. 选 B：让用户在日常 Chrome 安装导出扩展并导出 JSON/JSONL 文件夹，Codex 运行 `import_chatgpt_export.ps1 -Source <文件夹>` 导入，再运行构建。
5. 学习完成后向用户汇报统计结果，并明确告知这是**一次性补数据**，日常成长靠 Codex 自动沉淀；除非用户要求，否则不注册自动抓取任务。

## 每次 Codex 售后问答都会自动学习

即使不选 ChatGPT 历史学习，每次在本工具里完成售后问答后，Codex 也会调用 `record_codex_feedback.ps1` 把本次处理沉淀到 `feedback/`（来源标记 `codex_conversation`）。下次构建时这些案例会进入检索库并更新角色卡——知识库随每一次对话变强。

## 方案 B：浏览器扩展导出（导入适配）

支持的导出格式：
- ChatGPT 官方导出 `conversations.json` / `conversations.jsonl`；
- 扩展导出的一文件夹 `*.json` / `*.jsonl`（每个文件一段对话；子文件夹名会作为项目名）；
- 同时兼容带 `meta` 字段或文件夹分项目的格式。

导入：
```powershell
powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\import_chatgpt_export.ps1" -Source "<导出文件夹>" -ConfigPath "_售后模板缓存\chatgpt_learning.json"
```

可选 `-Project "差评处理"` 只导入指定项目；导入后重跑构建即可。

## 增量更新（每日/每周）

```powershell
powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\run_chatgpt_learning.ps1" -ConfigPath "_售后模板缓存\chatgpt_learning.json" -NoBrowser
```

脚本按对话 ID + update_time 去重，只抓新增/修改的对话，然后重建 corpus。

## 人工反馈（让角色卡越聊越强）

每次确认顾客满意、或者觉得某个处理值得复用时，把该案例写入反馈库：

```powershell
powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\record_feedback.ps1" `
  -Product "6228折叠吹风机" `
  -Issue "風量を調整できない" `
  -ChineseLogic "解释为超强风单风量设计，提供保留或退款" `
  -JapaneseReply "お客様 この度は..." `
  -Result "customer_satisfied"
```

然后重跑一次 `run_chatgpt_learning.ps1 -NoBrowser`，反馈案例会进入检索库并更新 persona。

## 自动更新（Windows 计划任务）

```powershell
powershell -ExecutionPolicy Bypass -File "_售后模板缓存\scripts\register_chatgpt_learning_task.ps1" -Time "08:00" -Frequency daily
```

任务默认注册为禁用状态，确认抓取正常后再启用：

```powershell
Enable-ScheduledTask -TaskName "AfterSalesChatGPTLearning"
```

取消任务：

```powershell
Disable-ScheduledTask -TaskName "AfterSalesChatGPTLearning"
```

注意：计划任务在“未登录状态”时运行，可能打不开已登录的浏览器会话，届时脚本会输出 LOGIN_REQUIRED 安全跳过；建议把电脑设为登录后运行，或手动执行增量更新。

## 无关对话过滤

抓取是“全量抓取”，构建时自动分析并剔除与亚马逊工作明显无关的内容（菜谱、旅游、游戏等生活类），审计报告 `corpus/relevance_report.tsv` 里能看到每一段对话的判定与原因。工作账号默认没有强信号也算工作内容（`unclear`），避免误删。

## 检索接入

`quick_query.ps1` 会自动读取 WPS 学习库的 `corpus/chatgpt_norm.tsv`，新增 `CHATGPT` 检索层（FAQ/OCR/kdocs/SPEC/PARAMS/CHATGPT 共六源）。命中后输出：

```
[分数] CHATGPT | <对话标题> page=<项目> | term=...
```

回复时引用来源：`CHATGPT:<对话标题>`，并参考 `corpus/persona.md` 的语气与分层逻辑。

## 故障排查

- `LOGIN_REQUIRED`：重新打开 ChatGPT 并登录一次。
- `RAW_FILES=0`：会话未登录，或 ChatGPT 页面改版导致列表接口变化。
- 构建报 BOM/编码错误：确认 raw 文件为 UTF-8（脚本已兼容 BOM，正常不会出现）。
- 其他电脑学习库为空：确认 WPS 云同步已把 `售后AI学习库` 目录同步下来，`chatgpt_learning.json` 中的路径存在。
