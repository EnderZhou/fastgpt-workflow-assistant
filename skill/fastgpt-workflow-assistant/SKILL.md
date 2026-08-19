---
name: fastgpt-workflow-assistant
description: 当前版本 1.3.0（2026-08-19）。仅在用户明确涉及 FastGPT、FastGPT 兼容自托管实例、其工作流导出 JSON，或从/向这些平台迁移与集成时，用于构建、修改、调试、测试和发布 AI 应用与工作流。不用于仅涉及 n8n、Dify、Coze、Make、Zapier、Power Automate 等其他平台，或未指定 FastGPT 的通用自动化任务。
---

# FastGPT工作流生成助手 v1.3.0

把 FastGPT AI 应用和工作流作为可版本化、可测试、可回滚的软件系统。先判断任务模式，再决定是否使用模型、知识库、工具、状态或人工审批。平台实际能力以目标实例的导出、导入和运行结果为准；通用能力参考 FastGPT 官方文档。

## 适用边界

仅在满足以下任一条件时使用本 Skill：

- 用户明确提到 FastGPT 或 FastGPT 兼容自托管实例；
- 用户提供可识别的 FastGPT 工作流导出 JSON，并要求检查、修改、导入或测试；
- 用户明确要求把其他平台的流程迁移到 FastGPT、从 FastGPT 迁出，或与其集成；
- 用户显式调用 `$fastgpt-workflow-assistant`。

不要用于仅处理 n8n、Dify、Coze、Make、Zapier、Power Automate 等其他平台的独立工作流，也不要把未指定平台的普通自动化、API 或编程问题默认解释为 FastGPT 任务。跨平台任务中，本 Skill 只负责 FastGPT 侧的设计、转换与验证；另一平台应使用其专用资料或能力。

## 版本与维护

- 当前版本：`1.3.0`，发布日期：`2026-08-19`。
- 保持机器名和目录名 `fastgpt-workflow-assistant` 稳定，只更新展示版本和内容。
- 查询、更新或回滚时读取 [版本与更新](references/版本与更新.md)，以 `assets/skill-version.json` 为版本事实来源。更新必须由用户显式发起。
- v1.3.0 同步脱敏后的工程能力基线，收紧自动触发边界，并新增变量引用/版本标签校验、用例矛盾预检、随机用例、版本差异和精简生产包。
- v1.2.0 统一接口执行与离线评测断言，增强 Unicode 匹配、运行异常分类和脱敏测试摘要。

## 核心规则

1. 新建工作流不要求用户先导出基线。依次使用目标版本模板、兼容模板、测试实例浏览器回读或候选 JSON；仅在这些证据都不足时请求脱敏导出物。
2. 涉及平台能力、版本或节点参数时，读取 [官方文档索引](references/官方文档索引.md) 与 [版本兼容性](references/版本与兼容性.md)。文档与实例冲突时，以实际导出和运行证据为准并记录漂移。
3. 修改后先离线验证；能访问测试实例时继续完成导入、重绑、保存、回读和运行回归。结构正确不代表运行正确。
4. 不把密钥、Token、私有地址、生产数据写入 Skill、样例、日志或发布说明。凭据只进入平台凭据系统或受保护变量。
5. 测试写入、通知、删除、发布等副作用前，说明影响并取得授权；设计确认、幂等、回读、补偿和审计。
6. 发布时明确区分：候选 JSON、离线验证通过、平台导入通过、运行回归通过。

## 选择任务模式

选择一个主要模式；确有组合需求再使用 `hybrid`。不要默认采用 RAG。

- `deterministic-workflow`：固定输入、规则和输出。
- `single-llm`：一次生成、提取、分类或改写。
- `rag-qa`：答案依赖受控资料；检索证据不代表实时状态。
- `tool-query`：通过 HTTP/API 或插件读取外部系统当前状态。
- `action-approval`：写入、通知、删除或发布，先确认/审批再执行并回读。
- `multi-tool-agent`：自然语言需要动态选择多个边界清晰的工具。
- `event-batch`：定时、Webhook、事件或批量任务，强调幂等、限流与恢复。
- `hybrid`：组合上述模式，并分别声明边界、证据、副作用和测试标准。

模式设计契约见 `assets/workflow-blueprints/mode-blueprints.json`。它不是目标版本已验证的导入 JSON。

## 按六阶段执行

### 1. PLAN

确认模式、触发方式、平台版本、输入输出、权限、外部系统、副作用、状态与 TTL、幂等及验收标准。仅在项目使用检索时设计知识域。设计路由、实体、状态、交付结构时读取 [架构与交付](references/架构与交付.md)；API、审批和事件流程读取 [非 RAG 工作流工程](references/非RAG工作流工程.md)。

### 2. BUILD

从已登记模板或目标实例基线构建；没有基线时仍生成候选 JSON。运行 `scripts/create_workflow_from_template.py` 生成起始工作流，具体规则见 [模板生成与浏览器测试](references/模板生成与浏览器测试.md)。

优先用确定性节点处理规则和精确标识符；用工具读取或改变外部状态；用检索提供受控依据；只让模型处理必要的理解与表达。外部访问使用 HTTP 节点或插件，不假定代码沙箱可联网。每条分支定义无命中、非法输入、超时、部分成功和人工升级路径。

v1.3.0 新增资产：`assets/workflow-templates/retry-pattern.json`（非导入式守卫/兜底设计参考，强调 `{{$nodeId.var$}}` 语法）、`assets/code-snippets/ip-mac-validation.js`、`assets/code-snippets/answer-guard-template.js` 和 `assets/功能画像示例.json`。使用前按目标工作流替换支持渠道、阈值和业务断言，不直接复制示例业务值。

### 3. VALIDATE

修改既有 JSON 时按稳定 `nodeId` 定位，最小修改字段和连线，并保留无关 ID、坐标、模型与 Handle。比较边时使用 `(source, target, sourceHandle, targetHandle)`。

```powershell
python scripts/validate_fastgpt_workflow.py agent.json --strict
python scripts/validate_fastgpt_workflow.py new.json --baseline old.json --expect-preserve-layout --expect-preserve-models --strict
python scripts/validate_fastgpt_workflow.py new.json --expected-app-version V3.5.14 --strict
# 仅在使用知识库时执行
python scripts/audit_fastgpt_kb.py knowledge-base --max-chars 2000 --strict
```

变量引用诊断码包括FG080-FG083。应用版本升级时保持全局变量机器键稳定，除非已有明确迁移方案；同时更新带版本号的显示标签，并用 `--expected-app-version` 检查FG084。不要为了更新显示版本而重命名 `contextState` 等持久化键。

知识库工程读取 [知识库工程](references/知识库工程.md)；无知识库时不要虚构相关交付物。

### 4. TEST

在非生产应用导入候选 JSON，重新绑定实际使用的模型、知识库、应用、插件、变量和凭据，保存后重导出并执行回读比较。按模式覆盖核心、边界、权限、安全、失败、部分成功、副作用、重复触发和延迟；先把用户反馈固化为失败用例，再做最小修改并回归。

```powershell
python scripts/generate_test_cases.py blueprint.json test-cases.json
python scripts/compare_fastgpt_roundtrip.py before.json after-export.json --json
python scripts/evaluate_agent_results.py test-cases.json test-results.json --json
```

测试用例支持 `expected_behavior`（`normal`/`fallback`/`error`）。`fallback`表示预期的业务兜底，不等于运行失败；使用 `expected_fallback_substrings` 描述兜底标记，`runtime_failure_substrings` 始终表示不应出现的运行失败文本。用例不得包含空期望、空路由标记或相互矛盾的期望/失败文本。基于agent功能画像生成的随机用例直接输出接口执行器可用的`turns`结构：

```powershell
python scripts/generate_random_test_cases.py assets/功能画像示例.json random-cases.json --count 20 --seed 42
python scripts/compare_workflow_versions.py old.json new.json --json
```

正式接口回归默认单并发、请求间隔至少 3 秒，保留首次异常并把答案断言失败与运行异常分开。接口自动化读取 [接口自动化回归](references/接口自动化回归.md)，发布门禁读取 [评测与发布闭环](references/评测与发布闭环.md)。用户授权且浏览器可用时，可在测试应用完成导入、配置、运行和回读；不得在未授权生产环境执行。

全量回归必须为关键路径设置必经节点、答案长度、时延和输出隔离断言。单目标资产查询应限制不同IP/MAC数量；变更节点和重试/错误路径未实际执行时，不得宣称对应缺陷已完成运行验证。

### 5. PUBLISH

确认目标版本导入、节点/边/绑定回读、运行回归、安全与副作用控制、上下文过期策略、脱敏、性能和回滚均达到验收标准。定位导入、路由、上下文、工具、引用或延迟问题时读取 [调试手册](references/调试手册.md) 与 [通用故障模式](references/通用故障模式.md)。

### 6. HANDOFF

交付实际使用的工作流 JSON、可选知识库、受限测试证据、脱敏测试摘要、离线与回读报告、发布清单、版本说明和回滚文件。清单记录基线/模板、目标版本、哈希、变更、需重绑项及各级验证状态。受限与可分享目录都不得含真实密钥。知识库内容发生变化时，按组织规范或 [知识库工程](references/知识库工程.md) 的推荐结构建立版本化更新包。

## 输出契约

报告主要/次要模式、已完成设计或变更、JSON 来源、验证证据、待完成的平台验证、需重绑/授权项、交付文件绝对路径，以及影响验收的风险。无法访问平台时交付候选 JSON 与操作清单，不宣称已完成真实导入和运行验证。

## 分发本 Skill

面向客户端导入时，从完整源码生成精简生产包：

```powershell
python scripts/package_skill.py <skill-directory> <output.zip> --profile slim-production --enforce-versioned-name
```

ZIP 根目录必须直接包含 `SKILL.md`，不得增加外层技能目录。发布前运行完整源码中的 `scripts/test_skill.py`；导入后运行包内 `scripts/smoke_test_skill.py`。精简包不携带打包脚本、工程调研资料和开发期测试夹具。
