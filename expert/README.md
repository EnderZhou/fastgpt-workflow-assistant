# FastGPT工作流专家 v3.0.2

为FastGPT及兼容实例设计、修改和排查工作流，生成候选JSON、维护知识库、分析导出对话日志，并交付可追溯的验证证据。WorkBuddy专家内置同版本技能，无需重复安装独立技能；技能另有Trae、Agent Skills和Hermes分发形式。

本版完善输入绑定、HTTP契约、bound行为和最终回复完整性检查；分享URL测试优先复用本机有证据的协议并通过API执行，未知实例才取证；新增发行ZIP与实际安装目录逐文件核对。

专家版本来自隐藏.codebuddy-plugin/plugin.json；技能版本、修订与build_id来自内置assets/skill-version.json。正式构建为3.0.2-20261113-release。版本号相同不代表文件完整一致，安装后可用内置verify_expert_install.py核对指定发行ZIP。

打包、客户端导入/调用、工作流平台导入/运行、GitHub发布与WorkBuddy开放平台审核是独立状态。开放平台由维护者手动上传，本包不声明审核已生效。私有实例注册表保存在用户配置目录，不包含在公开包内。

专家源码为expert/config.json、agent.md、avatar.png；构建器为tools/build_workbuddy_expert.py。稳定机器名不变，历史发行保留用于回退。
