# 发布 FastGPT工作流生成助手

本仓库以 GitHub Releases 作为公开稳定更新渠道。仓库根目录 `latest.json` 便于源码浏览和 Raw URL 读取；每个最新 Release 同时上传同一份 `latest.json`，提供不随版本变化的稳定地址。

## 首次配置

1. 确认公开 GitHub 账号为 `EnderZhou`，仓库链接和发布清单均指向该账号。
2. 确认仓库名保持 `fastgpt-workflow-assistant`；如果改名，同步修改所有 URL。
3. 启用 Issues、Discussions、Private vulnerability reporting 和分支保护。
4. 完成 [PRE_PUBLISH_CHECKLIST.md](PRE_PUBLISH_CHECKLIST.md) 的权利与脱敏检查。

## 每次发布

以 `v1.1.0` 为例：

```powershell
python skill/fastgpt-workflow-assistant/scripts/test_skill.py
python skill/fastgpt-workflow-assistant/scripts/package_skill.py `
  skill/fastgpt-workflow-assistant `
  dist/fastgpt-workflow-assistant-v1.1.0.zip `
  --enforce-versioned-name
Copy-Item dist/fastgpt-workflow-assistant-v1.1.0.zip `
  dist/fastgpt-workflow-assistant-latest.zip -Force
Get-FileHash dist/fastgpt-workflow-assistant-v1.1.0.zip -Algorithm SHA256
```

把哈希写入仓库根目录 `latest.json`，并复制同一文件到 `dist/latest.json`。然后验证：

```powershell
python skill/fastgpt-workflow-assistant/scripts/check_skill_version.py `
  --manifest latest.json `
  --package dist/fastgpt-workflow-assistant-v1.1.0.zip `
  --json
```

提交版本文件后创建带注释的 Tag `v1.1.0` 和 GitHub Release。上传以下三个附件：

- `fastgpt-workflow-assistant-v1.1.0.zip`：不可变版本包，用于审计与回滚；
- `fastgpt-workflow-assistant-latest.zip`：固定文件名，始终指向最新版；
- `latest.json`：固定文件名的机器可读发布清单。

发布后验证：

```text
https://github.com/EnderZhou/fastgpt-workflow-assistant/releases/latest/download/latest.json
https://github.com/EnderZhou/fastgpt-workflow-assistant/releases/latest/download/fastgpt-workflow-assistant-latest.zip
```

GitHub 的 `/releases/latest` 会定位到标记为最新、且不是草稿或预发布的 Release。不要把正式更新只发布为 prerelease，否则固定最新版入口不会按预期工作。

## 回滚

不要覆盖历史 Release 的版本化 ZIP。发现问题时发布修复版本，或让用户重新安装上一版本的版本化 ZIP；回滚后运行该版本自测试。根目录和最新 Release 的 `latest.json` 必须指向当前推荐版本。
