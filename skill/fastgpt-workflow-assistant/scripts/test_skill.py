#!/usr/bin/env python3
"""运行 FastGPT工作流生成助手的离线自测试。"""

from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIXTURES = ROOT / "tests" / "fixtures"


def run(*arguments: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    process = subprocess.run([sys.executable, *arguments], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if process.returncode != expected:
        raise AssertionError(f"命令返回 {process.returncode}，期望 {expected}: {arguments}\nSTDOUT:\n{process.stdout}\nSTDERR:\n{process.stderr}")
    return process


def main() -> int:
    version_manifest = json.loads((ROOT.parent / "assets" / "skill-version.json").read_text(encoding="utf-8"))
    assert version_manifest["skill_name"] == "fastgpt-workflow-assistant"
    assert version_manifest["version"] == "2.7.0"
    assert version_manifest["distribution_profile"] == "slim-production"

    skill_text = (ROOT.parent / "SKILL.md").read_text(encoding="utf-8")
    description = skill_text.split("---", 2)[1]
    assert "FastGPT" in description
    assert all(platform in description for platform in ("n8n", "Dify", "Coze"))
    assert "不用于" in description and "未指定 FastGPT" in description
    assert "## 适用边界" in skill_text

    current_version = run(str(ROOT / "check_skill_version.py"), "--json")
    current_version_result = json.loads(current_version.stdout)
    assert current_version_result["current_version"] == "2.7.0"
    assert current_version_result["status"] == "current_only"

    valid = run(str(ROOT / "validate_fastgpt_workflow.py"), str(FIXTURES / "valid-workflow.json"), "--json")
    valid_report = json.loads(valid.stdout)
    assert not [item for item in valid_report["diagnostics"] if item["severity"] == "error"]

    invalid = run(str(ROOT / "validate_fastgpt_workflow.py"), str(FIXTURES / "invalid-workflow.json"), "--json", expected=1)
    invalid_codes = {item["code"] for item in json.loads(invalid.stdout)["diagnostics"]}
    assert {"FG012", "FG021", "FG032"}.issubset(invalid_codes), invalid_codes

    kb = run(str(ROOT / "audit_fastgpt_kb.py"), str(FIXTURES / "kb-good"), "--json")
    kb_report = json.loads(kb.stdout)
    assert not [item for item in kb_report["diagnostics"] if item["severity"] == "error"]

    roundtrip = run(str(ROOT / "compare_fastgpt_roundtrip.py"), str(FIXTURES / "valid-workflow.json"), str(FIXTURES / "valid-workflow.json"), "--json")
    assert not json.loads(roundtrip.stdout)["diagnostics"]

    mode_blueprints = json.loads((ROOT.parent / "assets" / "workflow-blueprints" / "mode-blueprints.json").read_text(encoding="utf-8"))
    blueprint_ids = {item["id"] for item in mode_blueprints["blueprints"]}
    assert {"rag-qa", "tool-query", "action-approval", "event-batch", "multi-tool-agent"}.issubset(blueprint_ids)

    cases = [
        {
            "case_id": "normalized-pass",
            "expected_route": "process",
            "expected_substrings": ["Asset-PD"],
            "expected_any_groups": [["不一定在线", "不等于当前在线"]],
            "forbidden_substrings": ["CITE"],
            "required_nodes": ["流程答复"],
            "forbidden_nodes": ["写入"],
            "runtime_failure_substrings": ["平台调用失败或超时"],
            "min_answer_chars": 8,
            "max_answer_chars": 100,
            "max_latency_ms": 1000,
        },
        {
            "case_id": "strict-hyphen-fail",
            "expected_substrings": ["Asset-PD"],
            "text_match_mode": "strict",
        },
        {
            "case_id": "advanced-fields-fail",
            "expected_any_groups": [["允许表达A", "允许表达B"]],
            "required_nodes": ["必须节点"],
            "forbidden_nodes": ["禁止节点"],
            "runtime_failure_substrings": ["运行失败"],
            "min_answer_chars": 30,
            "max_latency_ms": 1000,
        },
        {
            "case_id": "transport-fail",
        },
        {
            "case_id": "max-length-fail",
            "max_answer_chars": 3,
        },
    ]
    results = [
        {
            "case_id": "normalized-pass",
            "route": "process",
            "answer": "Asset-PD 已注册不等于当前在线。",
            "nodes": ["流程答复"],
            "latency_ms": 20,
        },
        {
            "case_id": "strict-hyphen-fail",
            "answer": "Asset‑PD",
            "latency_ms": 10,
        },
        {
            "case_id": "advanced-fields-fail",
            "answer": "运行失败",
            "nodes": ["禁止节点"],
            "latency_ms": 10,
        },
        {
            "case_id": "transport-fail",
            "answer": "存在返回正文",
            "errors": ["timeout"],
            "http_status": 503,
            "latency_ms": 10,
        },
        {
            "case_id": "max-length-fail",
            "answer": "超过三字符",
            "latency_ms": 10,
        },
    ]
    with tempfile.TemporaryDirectory() as directory:
        temporary_root = Path(directory)
        case_path, result_path = temporary_root / "cases.json", temporary_root / "results.json"
        case_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
        result_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        evaluation = run(str(ROOT / "evaluate_agent_results.py"), str(case_path), str(result_path), "--json", expected=1)
        evaluation_report = json.loads(evaluation.stdout)
        assert evaluation_report["schema_version"] == "2.0"
        assert evaluation_report["summary"]["status_counts"] == {"pass": 1, "fail": 4}
        evaluation_codes = {item["code"] for item in evaluation_report["diagnostics"]}
        assert {"EV011", "EV014", "EV015", "EV016", "EV017", "EV018", "EV019", "EV021"}.issubset(evaluation_codes), evaluation_codes
        normalized_report = next(item for item in evaluation_report["cases"] if item["case_id"] == "normalized-pass")
        assert normalized_report["status"] == "pass"

        nested_cases = [{
            "case_id": "conversation",
            "text_match_mode": "normalized",
            "turns": [
                {"question": "第一轮", "expected_substrings": ["第一轮完成"]},
                {"question": "第二轮", "expected_any_groups": [["第二轮完成", "继续完成"]], "required_nodes": ["汇总"]},
            ],
        }]
        nested_results = [
            {"case_id": "conversation-1", "answer": "第一轮完成", "latency_ms": 10},
            {"case_id": "conversation-2", "answer": "继续完成", "nodes": ["汇总"], "latency_ms": 10},
        ]
        nested_case_path = temporary_root / "nested-cases.json"
        nested_result_path = temporary_root / "nested-results.json"
        nested_case_path.write_text(json.dumps(nested_cases, ensure_ascii=False), encoding="utf-8")
        nested_result_path.write_text(json.dumps(nested_results, ensure_ascii=False), encoding="utf-8")
        nested_evaluation = run(str(ROOT / "evaluate_agent_results.py"), str(nested_case_path), str(nested_result_path), "--json")
        assert json.loads(nested_evaluation.stdout)["summary"]["status_counts"] == {"pass": 2}

        generated_workflow = temporary_root / "generated-workflow.json"
        run(
            str(ROOT / "create_workflow_from_template.py"),
            str(generated_workflow),
            "--welcome-text",
            "测试欢迎语",
            "--reply-text",
            "测试回复",
        )
        generated_report = run(str(ROOT / "validate_fastgpt_workflow.py"), str(generated_workflow), "--json")
        assert not [item for item in json.loads(generated_report.stdout)["diagnostics"] if item["severity"] == "error"]

        generated_cases = temporary_root / "generated-cases.json"
        run(
            str(ROOT / "generate_test_cases.py"),
            str(ROOT.parent / "assets" / "agent-blueprint.sample.json"),
            str(generated_cases),
        )
        generated_case_items = json.loads(generated_cases.read_text(encoding="utf-8"))
        assert len(generated_case_items) >= 12
        generated_categories = {item["category"] for item in generated_case_items}
        assert {"safety", "idempotency", "event-batch", "agent-control"}.issubset(generated_categories)

        assertions_path = ROOT / "regression_assertions.py"
        assertions_spec = importlib.util.spec_from_file_location("regression_assertions_selftest", assertions_path)
        assert assertions_spec and assertions_spec.loader
        assertions_module = importlib.util.module_from_spec(assertions_spec)
        assertions_spec.loader.exec_module(assertions_module)
        assert assertions_module.normalize_text("## **格式化标题**") == "格式化标题"
        fallback_mismatch = assertions_module.evaluate_assertions(
            {
                "case_id": "fallback-mismatch",
                "expected_behavior": "fallback",
                "expected_fallback_substrings": ["暂时无法"],
            },
            {"answer": "正常结果", "nodes": []}, "",
        )
        assert "behavior_mismatch_expected_fallback" in fallback_mismatch["runtime_anomaly_flags"]
        error_mismatch = assertions_module.evaluate_assertions(
            {"expected_behavior": "error"}, {"answer": "", "nodes": [], "http_status": 200}, "",
        )
        assert "behavior_mismatch_expected_error" in error_mismatch["runtime_anomaly_flags"]
        expected_fallback = assertions_module.evaluate_assertions(
            {
                "case_id": "expected-fallback",
                "expected_behavior": "fallback",
                "expected_fallback_substrings": ["暂时无法"],
            },
            {"answer": "当前暂时无法处理", "nodes": []}, "",
        )
        assert not expected_fallback["runtime_anomaly"]
        runtime_fallback = assertions_module.evaluate_assertions(
            {
                "case_id": "fallback-runtime",
                "expected_behavior": "fallback",
                "expected_fallback_substrings": ["暂时无法"],
                "runtime_failure_substrings": ["平台调用失败"],
            },
            {"answer": "暂时无法处理：平台调用失败", "nodes": []}, "",
        )
        assert runtime_fallback["runtime_anomaly"]
        assert "runtime_failure_text" in runtime_fallback["runtime_anomaly_flags"]

        for invalid_spec in (
            {"case_id": "empty-positive", "expected_substrings": [""]},
            {"case_id": "empty-route", "route_markers": {"process": []}},
            {
                "case_id": "contradiction",
                "expected_substrings": ["周鹏"],
                "runtime_failure_substrings": ["周鹏"],
            },
        ):
            try:
                assertions_module.validate_case_spec(invalid_spec)
            except ValueError:
                pass
            else:
                raise AssertionError(f"应拒绝无效测试用例: {invalid_spec}")

        identifier_limit = assertions_module.evaluate_assertions(
            {"case_id": "identifier-limit", "max_distinct_ipv4": 1, "max_distinct_mac": 1},
            {
                "answer": "10.1.1.1 10.1.1.2 AA:BB:CC:DD:EE:01 AA:BB:CC:DD:EE:02",
                "nodes": [],
            },
            "",
        )
        assert identifier_limit["assertion_failed"]
        assert identifier_limit["ipv4_count_exceeded"]
        assert identifier_limit["mac_count_exceeded"]

        validator_path = ROOT / "validate_fastgpt_workflow.py"
        validator_spec = importlib.util.spec_from_file_location("validator_selftest", validator_path)
        assert validator_spec and validator_spec.loader
        validator_module = importlib.util.module_from_spec(validator_spec)
        validator_spec.loader.exec_module(validator_module)
        ref_context = (0, 0, "consumer", {"source", "consumer"}, {"source": {"answer"}})
        assert not validator_module._check_single_ref("{{$source.answer$}}", *ref_context)
        assert {item["code"] for item in validator_module._check_single_ref("{{source.answer}}", *ref_context)} == {"FG080"}
        assert {item["code"] for item in validator_module._check_single_ref("{{$missing.answer$}}", *ref_context)} == {"FG081"}
        assert {item["code"] for item in validator_module._check_single_ref("{{$source.other$}}", *ref_context)} == {"FG082"}
        assert {item["code"] for item in validator_module._check_single_ref("{{$.$}}", *ref_context)} == {"FG083"}

        stale_version_workflow = temporary_root / "stale-version-workflow.json"
        stale_version_data = json.loads((FIXTURES / "valid-workflow.json").read_text(encoding="utf-8"))
        stale_version_data["chatConfig"] = {
            "variables": [{"key": "contextState", "label": "V3.5.13会话上下文状态"}]
        }
        stale_version_workflow.write_text(json.dumps(stale_version_data, ensure_ascii=False), encoding="utf-8")
        stale_version_result = run(
            str(ROOT / "validate_fastgpt_workflow.py"), str(stale_version_workflow),
            "--expected-app-version", "V3.5.14", "--json", "--strict", expected=1,
        )
        assert "FG084" in {item["code"] for item in json.loads(stale_version_result.stdout)["diagnostics"]}
        stale_version_data["chatConfig"]["variables"][0]["label"] = "V3.5.14会话上下文状态"
        stale_version_workflow.write_text(json.dumps(stale_version_data, ensure_ascii=False), encoding="utf-8")
        current_version_result = run(
            str(ROOT / "validate_fastgpt_workflow.py"), str(stale_version_workflow),
            "--expected-app-version", "V3.5.14", "--json", "--strict",
        )
        assert not [
            item for item in json.loads(current_version_result.stdout)["diagnostics"]
            if item["code"] == "FG084"
        ]
        assert stale_version_data["chatConfig"]["variables"][0]["key"] == "contextState"

        random_cases_path = temporary_root / "random-cases.json"
        run(
            str(ROOT / "generate_random_test_cases.py"),
            str(ROOT.parent / "assets" / "功能画像示例.json"),
            str(random_cases_path), "--count", "12", "--seed", "42",
        )
        random_cases = json.loads(random_cases_path.read_text(encoding="utf-8"))
        assert len(random_cases) == 12
        assert all(isinstance(item.get("turns"), list) and len(item["turns"]) == 1 for item in random_cases)
        assert not any(
            "{" in item["turns"][0]["question"] or "}" in item["turns"][0]["question"]
            for item in random_cases
        )
        assert not any("input" in item for item in random_cases)
        assert all(
            not turn.get("runtime_failure_substrings")
            for item in random_cases for turn in item["turns"]
            if turn.get("expected_behavior", "normal") == "normal"
        )

        changed_workflow = temporary_root / "changed-workflow.json"
        changed_data = json.loads((FIXTURES / "valid-workflow.json").read_text(encoding="utf-8"))
        changed_data["nodes"][0]["name"] = "已变更节点名"
        changed_workflow.write_text(json.dumps(changed_data, ensure_ascii=False), encoding="utf-8")
        version_diff = run(
            str(ROOT / "compare_workflow_versions.py"),
            str(FIXTURES / "valid-workflow.json"), str(changed_workflow), "--json",
        )
        version_diff_report = json.loads(version_diff.stdout)
        assert version_diff_report["changed_node_count"] == 1
        assert version_diff_report["changed_nodes"]

        answer_guard = (ROOT.parent / "assets" / "code-snippets" / "answer-guard-template.js").read_text(encoding="utf-8")
        assert "内部编号" not in answer_guard and "supportContact" in answer_guard

        file_input_source = temporary_root / "file-input-source.json"
        file_input_output = temporary_root / "file-input-output.json"
        file_input_data = json.loads((FIXTURES / "valid-workflow.json").read_text(encoding="utf-8"))
        file_input_data["nodes"].extend([
            {
                "nodeId": "gate-1", "name": "文件判断", "flowNodeType": "ifElseNode",
                "position": {"x": 100, "y": 100}, "inputs": [{"key": "ifElseList", "value": []}], "outputs": [],
            },
            {
                "nodeId": "ai-1", "name": "文件解析", "flowNodeType": "chatNode",
                "position": {"x": 300, "y": 100}, "inputs": [], "outputs": [],
            },
        ])
        file_input_source.write_text(json.dumps(file_input_data, ensure_ascii=False), encoding="utf-8")
        configured = run(
            str(ROOT / "configure_file_input.py"), str(file_input_source), str(file_input_output),
            "--start-node-id", "start-1", "--gate-node-id", "gate-1", "--ai-node-id", "ai-1",
            "--max-files", "8", "--enable-images", "--pdf-enhanced", "--json",
        )
        configured_report = json.loads(configured.stdout)
        assert configured_report["status"] == "candidate_generated"
        configured_data = json.loads(file_input_output.read_text(encoding="utf-8"))
        configured_start = next(node for node in configured_data["nodes"] if node["nodeId"] == "start-1")
        configured_gate = next(node for node in configured_data["nodes"] if node["nodeId"] == "gate-1")
        configured_ai = next(node for node in configured_data["nodes"] if node["nodeId"] == "ai-1")
        assert any(item.get("key") == "userFiles" for item in configured_start["outputs"])
        assert configured_data["chatConfig"]["fileSelectConfig"]["maxFiles"] == 8
        assert configured_data["chatConfig"]["fileSelectConfig"]["canSelectImg"] is True
        assert next(item for item in configured_gate["inputs"] if item["key"] == "ifElseList")["value"][0]["list"][0]["variable"] == ["start-1", "userFiles"]
        assert next(item for item in configured_ai["inputs"] if item["key"] == "fileUrlList")["value"] == [["start-1", "userFiles"]]

        package_path = Path(directory) / "fastgpt-workflow-assistant-v2.7.0.zip"
        run(
            str(ROOT / "package_skill.py"), str(ROOT.parent), str(package_path),
            "--profile", "slim-production", "--enforce-versioned-name",
        )
        with zipfile.ZipFile(package_path, "r") as archive:
            names = archive.namelist()
            assert "SKILL.md" in names
            assert "assets/skill-version.json" in names
            assert "scripts/smoke_test_skill.py" in names
            assert "scripts/generate_random_test_cases.py" in names
            assert "scripts/compare_workflow_versions.py" in names
            assert "scripts/configure_file_input.py" in names
            assert "assets/workflow-templates/retry-pattern.json" in names
            assert "assets/功能画像示例.json" in names
            assert "scripts/package_skill.py" not in names
            assert "scripts/package_desktop_agents.py" not in names
            assert "scripts/test_skill.py" not in names
            assert "references/同类技能工程参考.md" not in names
            assert not any(name.startswith("scripts/tests/") for name in names)
            assert not any(name.startswith(ROOT.parent.name + "/") for name in names)

        package_version = run(str(ROOT / "check_skill_version.py"), "--package", str(package_path), "--json")
        package_version_result = json.loads(package_version.stdout)
        assert package_version_result["status"] == "up_to_date"
        assert package_version_result["package"]["version"] == "2.7.0"

        desktop_output = temporary_root / "desktop-packages"
        desktop_packages = run(
            str(ROOT / "package_desktop_agents.py"), str(ROOT.parent), str(desktop_output),
        )
        desktop_report = json.loads(desktop_packages.stdout)
        assert desktop_report["status"] == "ok"
        assert desktop_report["version"] == "2.7.0"
        trae_path = desktop_output / desktop_report["packages"]["trae"]["file"]
        workbuddy_path = desktop_output / desktop_report["packages"]["workbuddy"]["file"]
        agent_skills_path = desktop_output / desktop_report["packages"]["agent_skills"]["file"]
        with zipfile.ZipFile(trae_path, "r") as archive:
            assert "SKILL.md" in archive.namelist()
            assert "scripts/configure_file_input.py" in archive.namelist()
        with zipfile.ZipFile(workbuddy_path, "r") as archive:
            entry = "fastgpt-workflow-assistant/SKILL.md"
            assert entry in archive.namelist()
            workbuddy_skill = archive.read(entry).decode("utf-8")
            assert "description_zh:" in workbuddy_skill
            assert "description_en:" in workbuddy_skill
            assert "version: 2.7.0" in workbuddy_skill
            assert "author:" in workbuddy_skill
        with zipfile.ZipFile(agent_skills_path, "r") as archive:
            assert "fastgpt-workflow-assistant/SKILL.md" in archive.namelist()

        same_manifest_path = temporary_root / "latest-same.json"
        same_manifest_path.write_text(json.dumps({
            "skill_name": "fastgpt-workflow-assistant",
            "latest_version": "2.7.0",
        }, ensure_ascii=False), encoding="utf-8")
        same_version = run(str(ROOT / "check_skill_version.py"), "--manifest", str(same_manifest_path), "--json")
        assert json.loads(same_version.stdout)["status"] == "up_to_date"

        newer_manifest_path = temporary_root / "latest-newer.json"
        newer_manifest_path.write_text(json.dumps({
            "skill_name": "fastgpt-workflow-assistant",
            "latest_version": "2.8.0",
            "download_url": "https://example.invalid/skill-v2.8.0.zip",
        }, ensure_ascii=False), encoding="utf-8")
        newer_version = run(str(ROOT / "check_skill_version.py"), "--manifest", str(newer_manifest_path), "--json")
        assert json.loads(newer_version.stdout)["status"] == "update_available"
        run(str(ROOT / "check_skill_version.py"), "--manifest", str(newer_manifest_path), "--require-latest", expected=2)

        optional_policy_kb = temporary_root / "optional-policy-kb"
        optional_policy_kb.mkdir()
        (optional_policy_kb / "topic.md").write_text(
            "# 可选安全策略检查\n\n该文档用于验证审计器默认不标记私网地址，只有显式启用策略时才提示。示例测试地址为 192.168.0.10。",
            encoding="utf-8",
        )
        default_audit = run(str(ROOT / "audit_fastgpt_kb.py"), str(optional_policy_kb), "--json")
        default_codes = {item["code"] for item in json.loads(default_audit.stdout)["diagnostics"]}
        assert "KB023" not in default_codes
        flagged_audit = run(str(ROOT / "audit_fastgpt_kb.py"), str(optional_policy_kb), "--flag-private-ip", "--json")
        flagged_codes = {item["code"] for item in json.loads(flagged_audit.stdout)["diagnostics"]}
        assert "KB023" in flagged_codes

        runner_path = ROOT / "run_share_api_regression.py"
        runner_spec = importlib.util.spec_from_file_location("run_share_api_regression", runner_path)
        assert runner_spec and runner_spec.loader
        runner = importlib.util.module_from_spec(runner_spec)
        runner_spec.loader.exec_module(runner)

        captured_request: dict[str, object] = {}
        original_urlopen = runner.urllib.request.urlopen

        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def __iter__(self):
                return iter([b"data: [DONE]\n"])

        def fake_urlopen(request, **kwargs):
            captured_request["payload"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse()

        runner.urllib.request.urlopen = fake_urlopen
        try:
            runner.request_turn(
                type("Args", (), {
                    "app_id": "", "share_id": "share", "authorization_env": None,
                    "url": "https://example.invalid", "timeout_seconds": 1,
                })(),
                "chat", "uid", [{"role": "user", "content": "测试"}],
            )
        finally:
            runner.urllib.request.urlopen = original_urlopen
        assert "appId" not in captured_request["payload"]
        assert captured_request["payload"]["shareId"] == "share"

        inherited_specs: list[dict[str, object]] = []
        original_request_turn = runner.request_turn
        runner.request_turn = lambda args, chat_id, uid, messages: {
            "answer": "公共断言完成", "nodes": ["公共节点"], "sources": [],
            "variables": {}, "duration_seconds": 0.1, "errors": [],
            "event_counts": {}, "done_received": True, "http_status": 200,
        }
        original_evaluate_turn = runner.evaluate_turn
        runner.evaluate_turn = lambda spec, result, route: (
            inherited_specs.append(spec) or original_evaluate_turn(spec, result, route)
        )
        try:
            runner.run_case(
                type("Args", (), {"app_id": "app", "share_id": "share", "authorization_env": None,
                                   "url": "https://example.invalid", "timeout_seconds": 1,
                                   "stage_label": "selftest", "mode": "regression", "workers": 1,
                                   "gap_seconds": 0})(),
                {
                    "case_id": "inherit",
                    "expected_substrings": ["公共断言"],
                    "required_nodes": ["公共节点"],
                    "turns": [{"question": "测试"}],
                },
                "selftest", 1,
            )
        finally:
            runner.request_turn = original_request_turn
            runner.evaluate_turn = original_evaluate_turn
        assert inherited_specs[0]["expected_substrings"] == ["公共断言"]
        assert inherited_specs[0]["required_nodes"] == ["公共节点"]

        semantic_result = runner.evaluate_turn(
            {
                "expected_any_groups": [["不一定在线", "不等于当前在线"]],
                "required_nodes": ["流程答复"],
                "min_answer_chars": 8,
            },
            {
                "answer": "已注册不等于当前在线。",
                "nodes": ["流程答复"],
                "errors": [],
                "duration_seconds": 1.2,
            },
            "process",
        )
        assert not semantic_result["assertion_failed"]
        assert not semantic_result["runtime_anomaly"]
        runtime_result = runner.evaluate_turn(
            {
                "runtime_failure_substrings": ["平台调用失败或超时"],
                "min_answer_chars": 20,
            },
            {
                "answer": "平台调用失败或超时",
                "nodes": ["工具结果"],
                "errors": [],
                "duration_seconds": 0.2,
            },
            "tool",
        )
        assert not runtime_result["assertion_failed"]
        assert runtime_result["runtime_anomaly"]
        assert "runtime_failure_text" in runtime_result["runtime_anomaly_flags"]

        strict_result = runner.evaluate_turn(
            {"expected_substrings": ["Asset-PD"], "text_match_mode": "strict"},
            {"answer": "Asset‑PD", "nodes": [], "errors": [], "duration_seconds": 0.1},
            "process",
        )
        assert strict_result["assertion_failed"]
        normalized_result = runner.evaluate_turn(
            {"expected_substrings": ["Asset-PD"]},
            {"answer": "Asset-PD", "nodes": [], "errors": [], "duration_seconds": 0.1},
            "process",
        )
        assert not normalized_result["assertion_failed"]

        missing_latency_result = runner.evaluate_turn(
            {"max_latency_ms": 1000},
            {"answer": "正常回答", "nodes": [], "errors": []},
            "process",
        )
        assert missing_latency_result["runtime_anomaly"]
        assert "latency_missing" in missing_latency_result["runtime_anomaly_flags"]

        os.environ["FASTGPT_SELFTEST_APP_ID"] = "selftest-app"
        try:
            assert runner.resolve_identifier(None, "FASTGPT_SELFTEST_APP_ID", "appId") == "selftest-app"
        finally:
            del os.environ["FASTGPT_SELFTEST_APP_ID"]

        shareable = runner.build_shareable_summary(
            {
                "run_id": "selftest", "started_at": "2026-08-11T00:00:00+0800",
                "mode": "regression", "workers": 1, "gap_seconds": 3,
                "rounds": 1, "cases_per_round": 1, "turns": 1,
                "first_attempt_failures": 0, "assertion_failures": 0,
                "runtime_anomalies": 0, "transport_errors": 0,
                "empty_answers": 0, "latency_exceeded": 0,
                "latency_ms": {"average": 100, "minimum": 100, "maximum": 100},
                "per_round": [], "output": "C:/restricted/raw.json",
            },
            [{
                "case_id": "SAFE-01", "round": 1, "assertion_failed": False,
                "runtime_anomaly": False, "latency_exceeded": False, "latency_ms": 100,
                "question": "SECRET-QUESTION", "answer": "SECRET-ANSWER",
                "nodes": ["SECRET-NODE"], "sources": ["SECRET-SOURCE"],
            }],
        )
        shareable_text = json.dumps(shareable, ensure_ascii=False)
        assert "SECRET-" not in shareable_text
        assert "C:/restricted/raw.json" not in shareable_text

    print("FastGPT工作流生成助手 v2.7.0 全部离线自测试通过：版本一致性、触发边界、文件输入补丁、变量引用校验、版本标签门禁、行为分类、用例规范检查、标识符隔离、随机用例、版本差异、模板生成、工作流验证、知识库审计、统一断言、接口异常分类、脱敏汇总、精简生产包和桌面Agent专用包。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
