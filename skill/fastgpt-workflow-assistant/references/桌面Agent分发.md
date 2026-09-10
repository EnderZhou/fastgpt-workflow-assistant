# 桌面 Agent 分发

创建或更新面向 Trae、WorkBuddy、Codex 或其他 Agent Skills 客户端的导入包时读取本文件。客户端规范核验日期：2026-09-10。

## 1. 共同基线

所有包都以稳定目录名 `fastgpt-workflow-assistant` 和根入口 `SKILL.md` 为核心，保留实际运行需要的 `references/`、`scripts/`、`assets/`。排除 `__pycache__`、`.pyc`、完整自测试夹具、打包脚本和工程调研资料。

发布前执行：

```powershell
uv run python scripts/test_skill.py
uv run python scripts/package_desktop_agents.py <skill目录> <输出目录>
```

导入后在目标客户端执行 `scripts/smoke_test_skill.py`。客户端无法运行 Python 时，只能标记“结构导入通过”，不能宣称脚本能力已验证。

## 2. Trae / TraeCode

Trae 官方文档说明，可以上传单个 `SKILL.md` 或包含该文件及相关资源的 ZIP。项目技能通常位于 `.trae/skills/<skill-name>/`，全局技能在 Windows 位于 `%userprofile%/.trae-cn/skills`；TraeCode CLI 还使用 `.traecli/skills/` 或 `~/.traecli/skills/`。名称使用小写字母、数字和连字符可同时兼容 IDE 与 CLI。

Trae 导入包采用：

```text
SKILL.md
references/
scripts/
assets/
agents/
```

即 ZIP 根目录直接包含 `SKILL.md`。在“设置 → 技能与命令 → 创建 → 上传”中选择 ZIP；项目级导入后确认文件实际落到 `.trae/skills/fastgpt-workflow-assistant/`。修改后刷新技能发现或重启客户端。

官方文档：

- https://docs.trae.cn/ide_skills
- https://docs.trae.cn/cli_skills

## 3. WorkBuddy

WorkBuddy 开放平台要求 `SKILL.md` 使用 YAML frontmatter，并要求 `description`、`description_zh`、`description_en`、`version` 和 `author`。其结构示例以技能目录包裹资源，因此 WorkBuddy 包采用：

```text
fastgpt-workflow-assistant/
├── SKILL.md
├── references/
├── scripts/
├── assets/
└── agents/
```

WorkBuddy 专用包会在不修改源码 `SKILL.md` 正文的前提下，生成扩展 frontmatter。不要把该扩展文件反向覆盖 Codex 安装目录，避免未知元数据影响其他客户端的校验。

在 WorkBuddy 的“技能 → 添加技能 → 上传技能”中导入 ZIP。导入前检查脚本和权限：本技能没有内置凭据或固定生产地址，但接口回归脚本会在用户显式提供 URL/标识和授权环境变量时访问目标服务，可能把测试问题发送到该服务。

官方文档：

- https://open.workbuddy.cn/en/docs/skill
- https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market

## 4. 通用 Agent Skills 目录包

支持 `.agents/skills/` 的客户端使用带外层技能目录的通用包：

```text
fastgpt-workflow-assistant/SKILL.md
```

解压后应得到 `.agents/skills/fastgpt-workflow-assistant/SKILL.md`，不要产生双重目录。Trae 支持启用项目 `.agents/skills/`；若同名技能同时存在于 `.trae/skills/`，Trae 优先使用后者。

## 5. 状态与哈希

每个包记录：

- 技能版本和发布日期；
- 客户端目标与 ZIP 根结构；
- 文件数、ZIP SHA-256；
- 完整源码自测试结果；
- 包内冒烟测试结果；
- 已知运行时依赖和网络访问边界。

只在真实客户端成功导入后写“目标客户端导入通过”。本地 ZIP 结构检查通过时使用“候选可导入包”。
