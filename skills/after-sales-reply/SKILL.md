---
name: after-sales-reply
description: 根据亚马逊日本站顾客的日文或中文原文生成可直接发送的售后回复，并结合产品型号、订单情况、本地说明书、WPS 售后规则和已批准案例给出内部处理建议。用户粘贴顾客消息、询问产品使用方法、故障、配件、参数、退款、补发、换新、赔偿或 LINE 沟通话术时使用。首次安装、缓存更新或路径故障使用 after-sales-kb-maintain；审核学习候选使用 after-sales-learning-review。
---

# 日本站售后回复

目标是一次检索后给出客服可以直接复制的日文正文。

## 回复流程

1. 从顾客原文提取产品、问题、已尝试步骤、订单状态、渠道和期望结果。缺少的信息只有在会改变处理方案时才询问。
2. 读取 `%LOCALAPPDATA%\AfterSalesSupport\config\settings.json`。配置或快速索引不存在时调用 `after-sales-kb-maintain` 完成修复。
3. 只运行一次相邻 Skill 的 `../after-sales-kb-maintain/scripts/quick_query.ps1 -Product "<产品>" -Q "<问题>"`。
4. 命中后直接成稿；只有返回 `NOT_FOUND` 时才按来源优先级做定向兜底：WPS 规则与模板、已批准案例、说明书/规格书、必要的在线资料。
5. 按 [references/reply-policy.md](references/reply-policy.md) 选择解决方案并输出。
6. 发现可复用的新例外、新边界或人工修正时，调用 `../after-sales-learning-review/scripts/new_candidate.ps1` 写入待审核队列。候选不会参与正式检索。

## 默认输出

先给出 `给顾客的日文回复`，正文完整、自然、可直接复制。随后仅在有帮助时给出：

- `内部处理建议`：退款、补发、换新、排查步骤或需补充的信息；
- `参考`：一至三条命中来源；
- `学习提示`：只对高价值候选显示一行“发现一条可复用经验，回复‘确认学习’即可生效”。

用户只要回复正文时，仅输出日文正文。

## 速度边界

命中快查后停止检索。日常文字问题不启动全库 OCR、整表下载、视频抽帧或全磁盘扫描。图片问题先返回精确文件或页码；用户明确要图片或文字证据不足时再定向读取。
