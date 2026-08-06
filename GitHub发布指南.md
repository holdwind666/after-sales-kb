# after-sales-kb 发布到 GitHub 指南

本地仓库已准备好：`E:\说明书与视频（第9台）\售后知识库Skill发布\after-sales-kb-repo`（已初始化 git 并提交，分支 `master`）。

## 第一步：在 GitHub 上创建空仓库

1. 登录 https://github.com ，点击右上角 **+ → New repository**。
2. Repository name 填：`after-sales-kb`（推荐与本地一致）。
3. 可见性：
   - **公开（Public）**：任何电脑都可直接安装，最方便；
   - **私有（Private）**：只有有权限的人能访问，更安全。
4. 不要勾选 “Add a README file” 等初始化选项（保持空仓库），然后点 **Create repository**。
5. 复制创建后页面显示的仓库地址，例如：`https://github.com/你的用户名/after-sales-kb.git`

## 第二步：把本地仓库推送上去

在 PowerShell 中执行（把地址换成你自己的）：

```powershell
cd "E:\说明书与视频（第9台）\售后知识库Skill发布\after-sales-kb-repo"
git remote add origin https://github.com/你的用户名/after-sales-kb.git
git push -u origin master
```

首次推送会弹出 GitHub 登录窗口（或要求输入用户名+Token），登录后即可。

> 如果 `git remote add origin` 提示已存在，先执行 `git remote set-url origin <新地址>`。

## 第三步：新电脑上安装

### 方式一：让 Codex 直接安装（推荐）

新电脑上打开 Codex，发送：

```
请安装 skill：after-sales-kb
仓库：https://github.com/你的用户名/after-sales-kb
```

Codex 会自动下载 `after-sales-kb` 文件夹到 `C:\Users\<用户名>\.codex\skills\`，重启对话即可使用。

如果安装脚本需要指定路径，也可以手动用：

```
安装 skills 目录下 after-sales-kb 这个技能，来源是 https://github.com/你的用户名/after-sales-kb/tree/main/after-sales-kb
```

### 方式二：git clone 手动复制

```powershell
git clone https://github.com/你的用户名/after-sales-kb.git
```

然后把其中的 `after-sales-kb` 文件夹复制到 `C:\Users\<你的用户名>\.codex\skills\`，重启 Codex。

### 方式三：zip 下载

在 GitHub 仓库页点 **Code → Download ZIP**，解压后把 `after-sales-kb` 文件夹放入 `C:\Users\<你的用户名>\.codex\skills\`。

## 第四步：新电脑首次使用

装好后，让 Codex 按技能内置流程引导（技能会自动触发）：

1. 提供本地「说明书与视频」文件夹地址；
2. 提供 WPS 在线表格网址，并用 Chrome 打开保持登录；
3. 确认每周更新开关（默认关闭，3次未命中提醒增量更新）；
4. 学习两个案例；
5. 首次全量缓存（约1.5~2.5小时）；
6. 环境自检。

## 以后更新技能

修改技能内容后，重新推送即可：

```powershell
cd "E:\说明书与视频（第9台）\售后知识库Skill发布\after-sales-kb-repo"
git add -A
git commit -m "更新说明"
git push
```

新电脑需要重新安装一次才能拿到更新（技能不会自动热更新）。

## 常见问题

| 问题 | 解决 |
|---|---|
| 推送时要求输入用户名密码 | GitHub 已不支持密码，需要 Personal Access Token（Settings → Developer settings → Tokens），或安装 GitHub Desktop/gh CLI |
| 仓库是私有的，安装失败 | 新电脑需要有该仓库的访问权限（GitHub 账号授权），或改用公开仓库 |
| 安装时提示目录已存在 | 先删除 `C:\Users\<用户名>\.codex\skills\after-sales-kb` 再安装 |
| 技能安装了但没生效 | 重启 Codex 或新开对话 |
