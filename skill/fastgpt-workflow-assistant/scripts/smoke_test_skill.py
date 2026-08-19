#!/usr/bin/env python3
"""验证 FastGPT工作流生成助手导入包的结构、版本和核心脚本。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EXPECTED_NAME = "fastgpt-workflow-assistant"
EXPECTED_VERSION = "1.3.0"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [sys.executable, *arguments], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode:
        raise AssertionError(
            f"命令失败({result.returncode}): {arguments}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def main() -> int:
    manifest = json.loads((ROOT / "assets" / "skill-version.json").read_text(encoding="utf-8-sig"))
    assert manifest["skill_name"] == EXPECTED_NAME
    assert manifest["version"] == EXPECTED_VERSION

    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8-sig")
    agent_text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8-sig")
    release = json.loads((ROOT / "assets" / "发布清单示例.json").read_text(encoding="utf-8-sig"))
    assert f"当前版本 {EXPECTED_VERSION}" in skill_text
    assert f"v{EXPECTED_VERSION}" in skill_text and f"v{EXPECTED_VERSION}" in agent_text
    assert release["skill_version"] == EXPECTED_VERSION

    required = [
        "check_skill_version.py", "create_workflow_from_template.py",
        "validate_fastgpt_workflow.py", "audit_fastgpt_kb.py",
        "compare_fastgpt_roundtrip.py", "generate_test_cases.py",
        "evaluate_agent_results.py", "run_share_api_regression.py",
        "generate_random_test_cases.py", "compare_workflow_versions.py",
    ]
    for filename in required:
        script = ROOT / "scripts" / filename
        assert script.is_file(), filename
        run(str(script), "--help")

    with tempfile.TemporaryDirectory() as directory:
        workflow = Path(directory) / "minimal.json"
        run(str(ROOT / "scripts" / "create_workflow_from_template.py"), str(workflow))
        run(str(ROOT / "scripts" / "validate_fastgpt_workflow.py"), str(workflow), "--strict")

    print(f"OK: {EXPECTED_NAME} v{EXPECTED_VERSION} 精简生产包冒烟检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
