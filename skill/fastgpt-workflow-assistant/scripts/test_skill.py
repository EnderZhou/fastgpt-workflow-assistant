#!/usr/bin/env python3
"""运行 FastGPT工作流生成助手的离线自测试。"""

from __future__ import annotations

import json
import importlib.util
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
    assert version_manifest["version"] == "1.1.0"

    current_version = run(str(ROOT / "check_skill_version.py"), "--json")
    current_version_result = json.loads(current_version.stdout)
    assert current_version_result["current_version"] == "1.1.0"
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

    cases = [{"case_id": "case-1", "expected_route": "knowledge", "expected_substrings": ["完成"], "forbidden_substrings": ["CITE"], "max_latency_ms": 1000, "max_answer_chars": 100}]
    results = [{"case_id": "case-1", "route": "knowledge", "answer": "已完成。", "latency_ms": 20}]
    with tempfile.TemporaryDirectory() as directory:
        temporary_root = Path(directory)
        case_path, result_path = temporary_root / "cases.json", temporary_root / "results.json"
        case_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
        result_path.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
        evaluation = run(str(ROOT / "evaluate_agent_results.py"), str(case_path), str(result_path), "--json")
        assert json.loads(evaluation.stdout)["summary"]["status_counts"] == {"pass": 1}

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

        package_path = Path(directory) / "fastgpt-workflow-assistant-v1.1.0.zip"
        run(str(ROOT / "package_skill.py"), str(ROOT.parent), str(package_path), "--enforce-versioned-name")
        with zipfile.ZipFile(package_path, "r") as archive:
            names = archive.namelist()
            assert "SKILL.md" in names
            assert "assets/skill-version.json" in names
            assert not any(name.startswith(ROOT.parent.name + "/") for name in names)

        package_version = run(str(ROOT / "check_skill_version.py"), "--package", str(package_path), "--json")
        package_version_result = json.loads(package_version.stdout)
        assert package_version_result["status"] == "up_to_date"
        assert package_version_result["package"]["version"] == "1.1.0"

        same_manifest_path = temporary_root / "latest-same.json"
        same_manifest_path.write_text(json.dumps({
            "skill_name": "fastgpt-workflow-assistant",
            "latest_version": "1.1.0",
        }, ensure_ascii=False), encoding="utf-8")
        same_version = run(str(ROOT / "check_skill_version.py"), "--manifest", str(same_manifest_path), "--json")
        assert json.loads(same_version.stdout)["status"] == "up_to_date"

        newer_manifest_path = temporary_root / "latest-newer.json"
        newer_manifest_path.write_text(json.dumps({
            "skill_name": "fastgpt-workflow-assistant",
            "latest_version": "2.6.0",
            "download_url": "https://example.invalid/skill-v2.6.0.zip",
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

    print("FastGPT工作流生成助手 v1.1.0 全部离线自测试通过：版本一致性与更新检查、多模式蓝图、模板生成、工作流验证、可选知识库审计、模式用例生成、Round-trip 比较、结果评测、接口异常分类、Skill 根目录打包。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
