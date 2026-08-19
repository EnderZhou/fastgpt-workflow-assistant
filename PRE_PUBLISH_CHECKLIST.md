# 公开发布前检查清单

## 权利与审批

- [ ] 已确认本仓库内容的著作权及其他知识产权归属。
- [ ] 如内容属于职务成果或使用过公司资源，已取得权利人书面开源授权。
- [ ] 已核对劳动合同、保密协议、公司开源制度和数据安全要求。
- [ ] 所有第三方材料均有兼容的使用许可或只保留了公开链接与自行编写的摘要。
- [ ] “周鹏”可作为公开创建人和维护者署名；如版权主体另有约定，已按授权文件调整。

## 脱敏与安全

- [ ] 搜索并移除公司名称、内部平台名、项目代号、工号、企业微信和内部组织信息。
- [ ] 搜索并移除 Token、API Key、Cookie、密码、真实域名、私有地址、生产数据和日志。
- [ ] 工作流 JSON、知识库片段、截图和测试样例均为虚构或经权利人确认的公开数据。
- [ ] Git 历史中不存在已删除但仍可恢复的敏感内容；必要时在首次提交前重新建立干净仓库。
- [ ] 已启用 GitHub Private vulnerability reporting，安全问题不要求公开披露。

## GitHub 配置

- [x] 已将 README 中的“个人主页”替换为公开 GitHub 账号链接。
- [x] 已将 README、`latest.json` 和 Skill 更新文档中的账号占位符替换为实际公开 GitHub 账号。
- [ ] 已启用 Discussions，并设置 Q&A、Ideas 等分类。
- [ ] 已启用 Issues，确认 Issue 表单可以正常创建。
- [ ] 已设置默认分支保护，要求 CI 通过后再合并。
- [ ] 已确认仓库许可证显示为 Apache-2.0。
- [ ] 已将 `dist/fastgpt-workflow-assistant-v1.3.0.zip`、`dist/fastgpt-workflow-assistant-latest.zip` 和 `dist/latest.json` 上传到 `v1.3.0` Release。
- [ ] 已验证 `/releases/latest/download/latest.json` 和 `/releases/latest/download/fastgpt-workflow-assistant-latest.zip` 两个固定链接。

## 发布验证

- [ ] `python skill/fastgpt-workflow-assistant/scripts/test_skill.py` 通过。
- [ ] 发布 ZIP 根目录直接包含 `SKILL.md`。
- [ ] 已从发布 ZIP 做过一次全新导入测试。
- [ ] README、Skill 版本号、`latest.json`、Release Tag 和版本化 ZIP 文件名一致。
- [ ] `latest.json` 中的 SHA-256 与两个发布 ZIP 的实际哈希一致。
