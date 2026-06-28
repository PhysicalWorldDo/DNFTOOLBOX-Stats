# DNFTOOLBOX-Stats

自动统计 DNF 工具箱所有工具在 GitHub Releases 上的下载次数，并发布到 GitHub Pages。

## 功能

- 每天北京时间 09:00 自动刷新统计
- 读取 `DNFTOOLBOX-Registry` 的 `index.json` 和每个工具 manifest
- 统计每个工具、每个版本、每个 release asset 的累计下载次数
- 保存 `data/stats-latest.json` 和 `data/history/YYYY-MM-DD.json`
- 部署 `public/` 为 GitHub Pages 看板
- 可选发送邮件日报

## GitHub Pages

仓库创建后，在 GitHub 仓库设置里开启 Pages：

- Source: GitHub Actions
- Actions: 允许 workflow 读写仓库内容

首页文件在 `public/index.html`，数据文件是 `public/stats-latest.json`。

## 邮件 Secrets

如果需要邮件日报，在仓库 `Settings -> Secrets and variables -> Actions` 添加：

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
MAIL_FROM
MAIL_TO
```

未配置完整时，workflow 会跳过发信，不会失败。

## 可选变量

如果以后 registry 地址变化，可以在仓库变量里添加：

```text
REGISTRY_INDEX_URL
```

默认值：

```text
https://raw.githubusercontent.com/PhysicalWorldDo/DNFTOOLBOX-Registry/main/index.json
```

## 本地运行

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
python scripts/refresh_stats.py
python -m http.server 8000 -d public
```

打开：

```text
http://localhost:8000
```
