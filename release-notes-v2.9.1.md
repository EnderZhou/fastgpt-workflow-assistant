修复WorkBuddy开放平台上传通用包时缺少frontmatter字段的问题。

- 请上传fastgpt-workflow-assistant-v2.9.1_WorkBuddy_import-ready.zip，普通ZIP继续面向通用客户端。
- 专用包包含name、display_name、display_name_en、description、description_zh、description_en、version、author，并提供中英文使用示例。
- 对实际ZIP内的元数据执行校验；必填字段逐项缺失/空值必须失败。
- 公开技能移除公司准入类型、期限、MAC优先与特定资产平台规则，保留通用对话、资料完整性及接口处理方法。

离线验证通过不代表WorkBuddy开放平台已经审核或导入成功。内部LeapRAG技能和业务工作流未修改。
