# FastGPT工作流生成助手

当前公开版本：`v1.2.0`（2026-08-11）。

一个面向 FastGPT 及兼容自托管实例的开源 Codex Skill，用于把 AI 应用、Agent 和自动化工作流当作可版本化、可测试、可回滚的软件工程项目来开发。

它会先判断需求属于确定性流程、单模型生成、RAG 问答、工具查询、审批写回、多工具 Agent、事件/批量任务还是混合编排，再选择合适的骨架。它可以根据内置版本化模板生成候选工作流 JSON，辅助修改既有 JSON，按需治理知识库，生成测试用例，执行离线校验、接口回归和导入回读检查，并根据真实导入错误与使用反馈持续迭代。

> 本项目是独立维护的社区工具，与 FastGPT、Sealos 及其关联方不存在隶属、赞助或官方背书关系。“FastGPT”等名称及相关商标归其权利人所有。本仓库不分发 FastGPT 源码或品牌素材。

## 主要能力

- 无需用户先导出“最小工作流”，可从已登记模板生成候选 JSON。
- 覆盖 RAG 与非 RAG 场景，包括 API 查询、写操作审批、多工具 Agent、定时/批量/事件驱动和混合编排。
- 区分候选 JSON、离线结构验证、目标实例导入和真实运行回归四种状态。
- 对工作流节点、连线、模型、布局和回读差异进行自动检查。
- 仅在项目确实使用知识库时审计文档结构、重复、长度、链接和可选安全策略。
- 按主要任务模式生成核心、边界、失败、权限、安全、副作用和性能测试用例。
- 通过 FastGPT 分享接口执行低频功能回归，并把首次失败与复测分开记录。
- 使用统一断言内核评估接口执行结果和离线结果，支持 Unicode 规范化、节点、运行异常、长度和时延门禁。
- 将原始测试证据与可分享脱敏摘要分级保存，避免在协作材料中暴露业务正文或本地路径。
- 在用户授权且浏览器可用时，辅助完成非生产实例的导入、配置、运行和回读验证。
- 内置语义化版本、版本一致性检查、SHA-256 校验、显式更新与回滚方案。

## 安装

### 下载最新版

本仓库提供两个固定入口：

- 版本清单：`https://github.com/EnderZhou/fastgpt-workflow-assistant/releases/latest/download/latest.json`
- 最新安装包：`https://github.com/EnderZhou/fastgpt-workflow-assistant/releases/latest/download/fastgpt-workflow-assistant-latest.zip`

每个 Release 同时保留版本化安装包，例如 `fastgpt-workflow-assistant-v1.2.0.zip`，用于审计与回滚。压缩包根目录直接包含 `SKILL.md`，没有多余的外层目录。

### 从源码安装

将以下目录复制到本地 Skills 目录：

```text
skill/fastgpt-workflow-assistant/
```

安装后可使用类似请求触发：

```text
使用 FastGPT工作流生成助手，根据这份需求选择合适的工作流模式，生成可导入 JSON 和测试用例。
```

```text
检查当前技能版本；如果有更新，只报告可信下载地址和校验信息，不要自动覆盖安装。
```

## 版本检查与更新

本地查看版本：

```powershell
python skill/fastgpt-workflow-assistant/scripts/check_skill_version.py
```

与固定发布清单比较：

```powershell
python skill/fastgpt-workflow-assistant/scripts/check_skill_version.py `
  --manifest https://github.com/EnderZhou/fastgpt-workflow-assistant/releases/latest/download/latest.json
```

脚本只检查版本、技能名和可选安装包哈希，不会静默下载或安装。更新前保留旧版 ZIP 或备份安装目录；更新后重新加载客户端并运行离线自测试。详细步骤见 [版本与更新](skill/fastgpt-workflow-assistant/references/版本与更新.md)。

## 仓库结构

```text
.
├─ latest.json                        # 仓库中的最新版机器可读清单
├─ skill/fastgpt-workflow-assistant/ # 可安装 Skill 源码
├─ dist/                             # 版本化包、固定最新版包和发布清单
├─ .github/                          # Issue、PR 与持续集成配置
├─ RELEASING.md                      # GitHub Release 发布步骤
├─ CONTRIBUTING.md                   # 贡献指南
├─ SECURITY.md                       # 安全问题报告方式
└─ LICENSE                           # Apache-2.0
```

## 本地验证与打包

```powershell
python skill/fastgpt-workflow-assistant/scripts/test_skill.py
python skill/fastgpt-workflow-assistant/scripts/package_skill.py `
  skill/fastgpt-workflow-assistant `
  dist/fastgpt-workflow-assistant-v1.2.0.zip `
  --enforce-versioned-name
```

完整仓库压缩包：

```powershell
python tools/package_repository.py . ../FastGPT-Workflow-Generator-Assistant_GitHub_v1.2.0.zip --force
```

## 参与完善

- 使用 Issues 报告缺陷、兼容性问题或提出明确需求。
- 使用 Discussions 交流使用方法、工作流设计和较早期的改进想法。
- 提交 Pull Request 前阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，并附上脱敏样例、目标 FastGPT 版本和验证证据。
- 不要上传真实密钥、Cookie、Token、私有地址、生产数据、内部系统名称或未获授权的公司资料。

建议为仓库启用 GitHub Discussions、Private vulnerability reporting、分支保护和必需的 CI 检查。

## 维护者与联系

- 创建人及维护者：周鹏
- 使用问题与优化建议：优先通过 GitHub Discussions 公开交流
- 缺陷与功能请求：通过 GitHub Issues 提交
- 非公开安全问题：使用 GitHub 的 Private vulnerability reporting
- 个人主页：[github.com/EnderZhou](https://github.com/EnderZhou)

公开仓库不展示工号、企业微信、手机号或公司内网地址。如需电子邮件，建议使用专门的公开项目邮箱。

## 许可与权利说明

本仓库按 [Apache License 2.0](LICENSE) 发布。贡献者提交的内容按同一许可证授权。

发布前请完成 [PRE_PUBLISH_CHECKLIST.md](PRE_PUBLISH_CHECKLIST.md)，特别是确认劳动合同、公司制度、保密义务、职务成果归属和第三方材料授权。技术脱敏不能替代权利人授权。
