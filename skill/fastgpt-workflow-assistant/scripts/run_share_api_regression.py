#!/usr/bin/env python3
"""以可控频率调用 FastGPT 分享接口并保存可评估的回归结果。"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cases", type=Path, help="测试用例JSON对象数组")
    parser.add_argument("results", type=Path, help="结果JSON输出路径")
    parser.add_argument("--url", required=True, help="chat/completions接口URL")
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--share-id", required=True)
    parser.add_argument("--gap-seconds", type=float, default=3.0, help="一次响应结束后的冷却秒数")
    parser.add_argument("--timeout-seconds", type=float, default=90.0)
    parser.add_argument("--mode", choices=("regression", "stress"), default="regression")
    parser.add_argument("--workers", type=int, default=1, help="仅stress模式允许大于1")
    parser.add_argument("--rounds", type=int, default=1, help="独立采样轮次；正式回归必须为1")
    parser.add_argument("--round-gap-seconds", type=float, default=10.0, help="压力测试轮次间冷却秒数")
    parser.add_argument("--stage-label", default="", help="写入结果和汇总的测试阶段标签")
    parser.add_argument("--summary-output", type=Path, help="汇总JSON路径；默认与结果文件同名并添加.summary")
    parser.add_argument("--authorization-env", help="可选Bearer Token环境变量名")
    return parser.parse_args()


def load_cases(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("用例文件顶层必须是对象数组")
    for item in value:
        if not item.get("case_id") or not isinstance(item.get("turns"), list) or not item["turns"]:
            raise ValueError("每个用例必须包含case_id和非空turns数组")
    return value


def parse_sse(response) -> dict[str, Any]:
    answer: list[str] = []
    nodes: list[str] = []
    sources: list[str] = []
    variables: dict[str, Any] = {}
    errors: list[str] = []
    duration_seconds = None
    event = ""
    event_counts: dict[str, int] = {}
    done_received = False
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if line.startswith("event:"):
            event = line[6:].strip()
            continue
        if not line.startswith("data:"):
            continue
        text = line[5:].strip()
        if text == "[DONE]":
            done_received = True
            continue
        if not text:
            continue
        event_counts[event or "<unspecified>"] = event_counts.get(event or "<unspecified>", 0) + 1
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            errors.append(f"invalid_event_json:{text[:160]}")
            continue
        if event in {"answer", "fastAnswer"} and isinstance(data, dict):
            try:
                content = data["choices"][0]["delta"]["content"]
                if content:
                    answer.append(str(content))
            except (KeyError, IndexError, TypeError):
                pass
        elif event == "flowNodeStatus" and isinstance(data, dict):
            name = data.get("name")
            if name and name not in nodes:
                nodes.append(str(name))
        elif event == "flowNodeResponse" and isinstance(data, dict):
            for quote in data.get("quoteList") or []:
                name = quote.get("sourceName") if isinstance(quote, dict) else None
                if name and name not in sources:
                    sources.append(str(name))
        elif event == "workflowDuration" and isinstance(data, dict):
            duration_seconds = data.get("durationSeconds")
        elif event == "updateVariables" and isinstance(data, dict):
            variables.update(data)
        elif event == "error":
            errors.append(str(data))
    return {
        "answer": "".join(answer).strip(),
        "nodes": nodes,
        "sources": sources,
        "variables": variables,
        "duration_seconds": duration_seconds,
        "errors": errors,
        "event_counts": event_counts,
        "done_received": done_received,
    }


def infer_route(nodes: list[str], answer: str, turn: dict[str, Any]) -> str:
    """按用例声明的通用标记推断路由，避免在脚本中固化业务分类。"""
    joined = "\n".join(nodes)
    route_markers = turn.get("route_markers", {})
    if isinstance(route_markers, dict):
        for route, raw_markers in route_markers.items():
            markers = raw_markers if isinstance(raw_markers, list) else [raw_markers]
            if any(str(marker) in joined or str(marker) in answer for marker in markers):
                return str(route)
    expected_route = str(turn.get("expected_route", "")).strip()
    required_nodes = [str(value) for value in turn.get("required_nodes", [])]
    if expected_route and required_nodes and all(any(value in node for node in nodes) for value in required_nodes):
        return expected_route
    return "unknown"


def request_turn(args: argparse.Namespace, chat_id: str, uid: str,
                 messages: list[dict[str, str]]) -> dict[str, Any]:
    payload = {
        "chatId": chat_id,
        "appId": args.app_id,
        "shareId": args.share_id,
        "outLinkUid": uid,
        "messages": messages,
        "variables": {},
        "detail": True,
        "stream": True,
        "retainDatasetCite": True,
    }
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if args.authorization_env:
        import os
        token = os.environ.get(args.authorization_env, "").strip()
        if not token:
            raise ValueError(f"环境变量{args.authorization_env}为空")
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        args.url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=args.timeout_seconds,
                                context=ssl.create_default_context()) as response:
        result = parse_sse(response)
        result["http_status"] = getattr(response, "status", None)
        return result


def evaluate_turn(turn: dict[str, Any], result: dict[str, Any], route: str) -> dict[str, Any]:
    answer = result["answer"]
    missing = [str(value) for value in turn.get("expected_substrings", []) if str(value) not in answer]
    missing_any_groups: list[list[str]] = []
    for raw_group in turn.get("expected_any_groups", []):
        group = [str(value) for value in raw_group] if isinstance(raw_group, list) else [str(raw_group)]
        if group and not any(value in answer for value in group):
            missing_any_groups.append(group)
    forbidden = [str(value) for value in turn.get("forbidden_substrings", []) if str(value) in answer]
    nodes = result["nodes"]
    missing_nodes = [str(value) for value in turn.get("required_nodes", [])
                     if not any(str(value) in node for node in nodes)]
    forbidden_nodes = [str(value) for value in turn.get("forbidden_nodes", [])
                       if any(str(value) in node for node in nodes)]
    expected_route = str(turn.get("expected_route", "")).strip()
    route_mismatch = bool(expected_route and route != expected_route)
    runtime_failure_matches = [str(value) for value in turn.get("runtime_failure_substrings", [])
                               if str(value) in answer]

    runtime_anomaly_flags: list[str] = []
    if result["errors"]:
        runtime_anomaly_flags.append("transport_or_sse_error")
    if not answer:
        runtime_anomaly_flags.append("empty_answer")
    min_answer_chars = turn.get("min_answer_chars")
    if isinstance(min_answer_chars, (int, float)) and len(answer) < int(min_answer_chars):
        runtime_anomaly_flags.append("answer_too_short")
    min_node_count = turn.get("min_node_count")
    if isinstance(min_node_count, (int, float)) and len(nodes) < int(min_node_count):
        runtime_anomaly_flags.append("node_count_below_minimum")
    if missing_nodes:
        runtime_anomaly_flags.append("required_node_missing")
    if forbidden_nodes:
        runtime_anomaly_flags.append("forbidden_node_executed")
    if runtime_failure_matches:
        runtime_anomaly_flags.append("runtime_failure_text")

    latency_ms = round(result["duration_seconds"] * 1000) if isinstance(result["duration_seconds"], (int, float)) else None
    max_latency_ms = turn.get("max_latency_ms")
    latency_exceeded = bool(isinstance(max_latency_ms, (int, float)) and
                            isinstance(latency_ms, int) and latency_ms > int(max_latency_ms))
    assertion_failed = bool(missing or missing_any_groups or forbidden or route_mismatch)
    runtime_anomaly = bool(runtime_anomaly_flags)
    return {
        "missing": missing,
        "missing_any_groups": missing_any_groups,
        "forbidden": forbidden,
        "missing_nodes": missing_nodes,
        "forbidden_nodes": forbidden_nodes,
        "route_mismatch": route_mismatch,
        "runtime_failure_matches": runtime_failure_matches,
        "runtime_anomaly_flags": runtime_anomaly_flags,
        "assertion_failed": assertion_failed,
        "runtime_anomaly": runtime_anomaly,
        "latency_ms": latency_ms,
        "latency_exceeded": latency_exceeded,
    }


def run_case(args: argparse.Namespace, case: dict[str, Any], run_id: str,
             round_number: int) -> list[dict[str, Any]]:
    case_id = str(case["case_id"])
    chat_id = f"api-regression-{run_id}-{case_id}-{uuid.uuid4().hex[:8]}"
    uid = f"shareChat-{chat_id}"
    messages: list[dict[str, str]] = []
    outputs: list[dict[str, Any]] = []
    for index, turn in enumerate(case["turns"], 1):
        question = str(turn.get("question", ""))
        messages.append({"role": "user", "content": question})
        started = time.perf_counter()
        try:
            result = request_turn(args, chat_id, uid, messages)
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            result = {
                "answer": "", "nodes": [], "sources": [], "variables": {},
                "duration_seconds": None, "errors": [f"{type(exc).__name__}:{exc}"],
                "event_counts": {}, "done_received": False,
                "http_status": getattr(exc, "code", None),
            }
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        messages.append({"role": "assistant", "content": result["answer"]})
        route = infer_route(result["nodes"], result["answer"], turn)
        evaluation = evaluate_turn(turn, result, route)
        outputs.append({
            "case_id": str(turn.get("result_id") or (case_id if len(case["turns"]) == 1 else f"{case_id}-{index}")),
            "conversation_id": case_id,
            "turn": index,
            "run_id": run_id,
            "round": round_number,
            "stage_label": args.stage_label,
            "mode": args.mode,
            "workers": args.workers,
            "gap_seconds": args.gap_seconds,
            "question": question,
            "answer": result["answer"],
            "route": route,
            "nodes": result["nodes"],
            "sources": result["sources"],
            "variables": result["variables"],
            "latency_ms": evaluation["latency_ms"],
            "client_elapsed_ms": elapsed_ms,
            "http_status": result.get("http_status"),
            "event_counts": result.get("event_counts", {}),
            "done_received": result.get("done_received", False),
            "errors": result["errors"],
            "missing": evaluation["missing"],
            "missing_any_groups": evaluation["missing_any_groups"],
            "forbidden": evaluation["forbidden"],
            "missing_nodes": evaluation["missing_nodes"],
            "forbidden_nodes": evaluation["forbidden_nodes"],
            "route_mismatch": evaluation["route_mismatch"],
            "runtime_failure_matches": evaluation["runtime_failure_matches"],
            "runtime_anomaly_flags": evaluation["runtime_anomaly_flags"],
            "assertion_failed": evaluation["assertion_failed"],
            "runtime_anomaly": evaluation["runtime_anomaly"],
            "latency_exceeded": evaluation["latency_exceeded"],
            "first_attempt_failed": bool(evaluation["assertion_failed"] or evaluation["runtime_anomaly"]),
        })
        if args.gap_seconds > 0:
            time.sleep(args.gap_seconds)
    return outputs


def summarize_results(results: list[dict[str, Any]], args: argparse.Namespace,
                      run_id: str, cases_count: int, started_at: str,
                      elapsed_seconds: float) -> dict[str, Any]:
    latencies = [item["latency_ms"] for item in results if isinstance(item.get("latency_ms"), int)]
    per_round: list[dict[str, Any]] = []
    for round_number in range(1, args.rounds + 1):
        items = [item for item in results if item["round"] == round_number]
        per_round.append({
            "round": round_number,
            "turns": len(items),
            "assertion_failures": sum(bool(item["assertion_failed"]) for item in items),
            "runtime_anomalies": sum(bool(item["runtime_anomaly"]) for item in items),
            "transport_errors": sum(bool(item["errors"]) for item in items),
            "empty_answers": sum(not bool(item["answer"]) for item in items),
            "latency_exceeded": sum(bool(item["latency_exceeded"]) for item in items),
        })
    return {
        "run_id": run_id,
        "stage_label": args.stage_label,
        "started_at": started_at,
        "elapsed_seconds": round(elapsed_seconds, 2),
        "cases_per_round": cases_count,
        "rounds": args.rounds,
        "turns": len(results),
        "first_attempt_failures": sum(bool(item["first_attempt_failed"]) for item in results),
        "assertion_failures": sum(bool(item["assertion_failed"]) for item in results),
        "runtime_anomalies": sum(bool(item["runtime_anomaly"]) for item in results),
        "transport_errors": sum(bool(item["errors"]) for item in results),
        "empty_answers": sum(not bool(item["answer"]) for item in results),
        "latency_exceeded": sum(bool(item["latency_exceeded"]) for item in results),
        "latency_ms": {
            "average": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "minimum": min(latencies) if latencies else None,
            "maximum": max(latencies) if latencies else None,
        },
        "gap_seconds": args.gap_seconds,
        "round_gap_seconds": args.round_gap_seconds,
        "mode": args.mode,
        "workers": args.workers,
        "per_round": per_round,
        "output": str(args.results),
    }


def main() -> int:
    args = parse_args()
    if args.gap_seconds < 0:
        raise ValueError("gap-seconds不能为负数")
    if args.round_gap_seconds < 0:
        raise ValueError("round-gap-seconds不能为负数")
    if args.rounds < 1:
        raise ValueError("rounds必须大于0")
    if args.mode == "regression" and args.workers != 1:
        raise ValueError("正式回归必须workers=1；并发测试请使用--mode stress")
    if args.mode == "regression" and args.rounds != 1:
        raise ValueError("正式回归必须rounds=1；多轮采样请使用--mode stress")
    if args.mode == "stress" and args.workers < 1:
        raise ValueError("workers必须大于0")
    cases = load_cases(args.cases)
    run_id = time.strftime("%Y%m%d%H%M%S")
    started_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for round_number in range(1, args.rounds + 1):
        if args.mode == "regression" or args.workers == 1:
            for case in cases:
                results.extend(run_case(args, case, run_id, round_number))
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
                futures = [executor.submit(run_case, args, case, run_id, round_number) for case in cases]
                for future in concurrent.futures.as_completed(futures):
                    results.extend(future.result())
        if round_number < args.rounds and args.round_gap_seconds > 0:
            time.sleep(args.round_gap_seconds)
    args.results.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = summarize_results(
        results, args, run_id, len(cases), started_at,
        time.perf_counter() - started
    )
    summary_path = args.summary_output or args.results.with_name(f"{args.results.stem}.summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary["summary_output"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["first_attempt_failures"] else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
