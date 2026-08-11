#!/usr/bin/env python3
"""按期望路由、子串、禁止子串、长度和延迟评估 Agent 测试结果。"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path, help="测试用例 JSON 数组")
    parser.add_argument("results", type=Path, help="测试结果 JSON 数组")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser.parse_args()


def load_array(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        value = json.load(stream)
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{path}: 顶层必须是对象数组")
    return value


def diagnostic(code: str, case_id: str, message: str) -> dict[str, str]:
    return {"code": code, "severity": "error", "case_id": case_id, "message": message}


def evaluate(cases: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics: list[dict[str, str]] = []
    result_by_id = {str(item.get("case_id")): item for item in results}
    case_reports: list[dict[str, Any]] = []

    for case in cases:
        case_id = str(case.get("case_id", ""))
        failures: list[str] = []
        if not case_id:
            diagnostics.append(diagnostic("EV001", "<missing>", "测试用例缺少 case_id"))
            continue
        result = result_by_id.get(case_id)
        if result is None:
            diagnostics.append(diagnostic("EV002", case_id, "缺少测试结果"))
            case_reports.append({"case_id": case_id, "status": "fail", "failures": ["missing_result"]})
            continue

        answer = str(result.get("answer", ""))
        route = str(result.get("route", ""))
        expected_route = case.get("expected_route")
        if expected_route is not None and route != str(expected_route):
            diagnostics.append(diagnostic("EV010", case_id, f"路由不符：期望 {expected_route!r}，实际 {route!r}"))
            failures.append("route")
        for expected in case.get("expected_substrings", []):
            if str(expected) not in answer:
                diagnostics.append(diagnostic("EV011", case_id, f"答案缺少期望子串：{expected!r}"))
                failures.append(f"missing:{expected}")
        for forbidden in case.get("forbidden_substrings", []):
            if str(forbidden) in answer:
                diagnostics.append(diagnostic("EV012", case_id, f"答案包含禁止子串：{forbidden!r}"))
                failures.append(f"forbidden:{forbidden}")
        max_latency = case.get("max_latency_ms")
        latency = result.get("latency_ms")
        if max_latency is not None and (not isinstance(latency, (int, float)) or latency > max_latency):
            diagnostics.append(diagnostic("EV013", case_id, f"延迟超限或缺失：{latency!r} > {max_latency}"))
            failures.append("latency")
        max_chars = case.get("max_answer_chars")
        if max_chars is not None and len(answer) > int(max_chars):
            diagnostics.append(diagnostic("EV014", case_id, f"答案过长：{len(answer)} > {max_chars}"))
            failures.append("length")
        case_reports.append({"case_id": case_id, "status": "fail" if failures else "pass", "failures": failures})

    defined_ids = {str(case.get("case_id")) for case in cases}
    for extra_id in sorted(set(result_by_id) - defined_ids):
        diagnostics.append({"code": "EV020", "severity": "warning", "case_id": extra_id, "message": "结果中存在未定义用例"})

    status_counts = Counter(item["status"] for item in case_reports)
    return {
        "schema_version": "1.0",
        "summary": {"cases": len(cases), "results": len(results), "status_counts": dict(status_counts)},
        "cases": case_reports,
        "diagnostics": diagnostics,
    }


def main() -> int:
    args = parse_args()
    try:
        report = evaluate(load_array(args.cases), load_array(args.results))
    except Exception as exc:
        report = {"schema_version": "1.0", "summary": {"status_counts": {"fail": 1}}, "cases": [], "diagnostics": [diagnostic("EV000", "<file>", f"{type(exc).__name__}: {exc}")]}
    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        for item in report["diagnostics"]:
            print(f"[{item['severity'].upper()}][{item['code']}][{item['case_id']}] {item['message']}")
    return 1 if any(item["severity"] == "error" for item in report["diagnostics"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
