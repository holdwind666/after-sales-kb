# after-sales-kb 发布到 GitHub 指南

本地仓库已就绪：`E:\说明书与视频（第9台）\售后知识库Skill发布\after-sales-kb-repo`（分支 `main`，远程 `origin → https://github.com/holdwind666/after-sales-kb.git`）。

## 推送最新版本

```powershell
cd "E:\说明书与视频（第9台）\售后知识库Skill发布\after-sales-kb-repo"
git add -A
git commit -m "更新技能：ChatGPT历史对话学习+日常自动沉淀+新手引导"
git push origin main
```

若提示需要认证：使用 GitHub Personal Access Token（Settings → Developer settings → Tokens）或安装 GitHub Desktop / gh CLI。

## 新电脑安装

打开 Codex，发送：

```
请安装 skill：after-sales-kb
仓库：https://github.com/holdwind666/after-sales-kb
```

或手动把 `after-sales-kb` 文件夹复制到 `C:\Users\<你的用户名>\.codex\skills\`，重启 Codex。

## 注意事项

- 每次技能内容更新后，新电脑需重新安装（不会自动热更新）；
- README.md 面向最终使用者，保持简单可读；
- 仓库仅限内部使用。
