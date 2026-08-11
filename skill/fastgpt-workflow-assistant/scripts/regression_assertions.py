#!/usr/bin/env python3
"""回归执行器与离线评测器共用的断言和文本规范化逻辑。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


MATCH_MODES = {"normalized", "strict"}
HYPHEN_TRANSLATION = str.maketrans({
    "\u2010": "-",  # hyphen
    "\u2011": "-",  # non-breaking hyphen
    "\u2012": "-",  # figure dash
    "\u2013": "-",  # en dash
    "\u2014": "-",  # em dash
    "\u2212": "-",  # minus sign
    "\ufe63": "-",  # small hyphen-minus
    "\uff0d": "-",  # fullwidth hyphen-minus
    "\u00a0": " ",  # no-break space
    "\u2007": " ",  # figure space
    "\u202f": " ",  # narrow no-break space
})


def normalize_text(value: Any) -> str:
    """统一兼容等价字符；不改变大小写，也不做模糊或同义词匹配。"""
    text = unicodedata.normalize("NFKC", str(value)).translate(HYPHEN_TRANSLATION)
    return re.sub(r"\s+", " ", text).strip()


def get_match_mode(spec: dict[str, Any]) -> str:
    mode = str(spec.get("text_match_mode", "normalized")).strip().lower()
    if mode not in MATCH_MODES:
        raise ValueError(f"text_match_mode必须是normalized或strict，实际为{mode!r}")
    return mode


def contains_text(haystack: Any, needle: Any, mode: str = "normalized") -> bool:
    if mode == "strict":
        return str(needle) in str(haystack)
    if mode != "normalized":
        raise ValueError(f"未知文本匹配模式：{mode!r}")
    return normalize_text(needle) in normalize_text(haystack)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def resolve_latency_ms(result: dict[str, Any]) -> int | None:
    latency = result.get("latency_ms")
    if isinstance(latency, (int, float)) and not isinstance(latency, bool):
        return round(latency)
    duration = result.get("duration_seconds")
    if isinstance(duration, (int, float)) and not isinstance(duration, bool):
        return round(duration * 1000)
    return None


def evaluate_assertions(spec: dict[str, Any], result: dict[str, Any], route: str) -> dict[str, Any]:
    """按统一契约评估答案、节点、运行信号、长度和时延。"""
    mode = get_match_mode(spec)
    answer = str(result.get("answer", ""))
    raw_nodes = result.get("nodes", [])
    nodes = [str(value) for value in raw_nodes] if isinstance(raw_nodes, list) else []

    missing = [
        str(value) for value in _as_list(spec.get("expected_substrings"))
        if not contains_text(answer, value, mode)
    ]
    missing_any_groups: list[list[str]] = []
    for raw_group in _as_list(spec.get("expected_any_groups")):
        group = [str(value) for value in _as_list(raw_group)]
        if group and not any(contains_text(answer, value, mode) for value in group):
            missing_any_groups.append(group)
    forbidden = [
        str(value) for value in _as_list(spec.get("forbidden_substrings"))
        if contains_text(answer, value, mode)
    ]
    missing_nodes = [
        str(value) for value in _as_list(spec.get("required_nodes"))
        if not any(contains_text(node, value, mode) for node in nodes)
    ]
    forbidden_nodes = [
        str(value) for value in _as_list(spec.get("forbidden_nodes"))
        if any(contains_text(node, value, mode) for node in nodes)
    ]

    expected_route = str(spec.get("expected_route", "")).strip()
    route_mismatch = bool(expected_route and route != expected_route)
    runtime_failure_matches = [
        str(value) for value in _as_list(spec.get("runtime_failure_substrings"))
        if contains_text(answer, value, mode)
    ]

    answer_chars = len(answer)
    min_answer_chars = spec.get("min_answer_chars")
    answer_too_short = bool(
        isinstance(min_answer_chars, (int, float))
        and not isinstance(min_answer_chars, bool)
        and answer_chars < int(min_answer_chars)
    )
    max_answer_chars = spec.get("max_answer_chars")
    answer_too_long = bool(
        isinstance(max_answer_chars, (int, float))
        and not isinstance(max_answer_chars, bool)
        and answer_chars > int(max_answer_chars)
    )

    runtime_anomaly_flags: list[str] = []
    if result.get("errors"):
        runtime_anomaly_flags.append("transport_or_sse_error")
    http_status = result.get("http_status")
    if isinstance(http_status, int) and not 200 <= http_status < 300:
        runtime_anomaly_flags.append("http_status_error")
    if not answer:
        runtime_anomaly_flags.append("empty_answer")
    if answer_too_short:
        runtime_anomaly_flags.append("answer_too_short")
    min_node_count = spec.get("min_node_count")
    if (
        isinstance(min_node_count, (int, float))
        and not isinstance(min_node_count, bool)
        and len(nodes) < int(min_node_count)
    ):
        runtime_anomaly_flags.append("node_count_below_minimum")
    if missing_nodes:
        runtime_anomaly_flags.append("required_node_missing")
    if forbidden_nodes:
        runtime_anomaly_flags.append("forbidden_node_executed")
    if runtime_failure_matches:
        runtime_anomaly_flags.append("runtime_failure_text")
    if spec.get("require_done_event") is True and result.get("done_received") is not True:
        runtime_anomaly_flags.append("done_event_missing")
    reported_flags = result.get("runtime_anomaly_flags", [])
    if isinstance(reported_flags, list):
        for raw_flag in reported_flags:
            flag = str(raw_flag)
            if flag and flag not in runtime_anomaly_flags:
                runtime_anomaly_flags.append(flag)
    if result.get("runtime_anomaly") is True and not runtime_anomaly_flags:
        runtime_anomaly_flags.append("reported_runtime_anomaly")

    latency_ms = resolve_latency_ms(result)
    max_latency_ms = spec.get("max_latency_ms")
    latency_required = isinstance(max_latency_ms, (int, float)) and not isinstance(max_latency_ms, bool)
    latency_missing = bool(latency_required and latency_ms is None)
    latency_exceeded = bool(latency_required and latency_ms is not None and latency_ms > int(max_latency_ms))
    if latency_missing:
        runtime_anomaly_flags.append("latency_missing")

    assertion_failed = bool(
        missing
        or missing_any_groups
        or forbidden
        or route_mismatch
        or answer_too_long
    )
    runtime_anomaly = bool(runtime_anomaly_flags)
    return {
        "text_match_mode": mode,
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
        "answer_chars": answer_chars,
        "answer_too_short": answer_too_short,
        "answer_too_long": answer_too_long,
        "latency_ms": latency_ms,
        "latency_missing": latency_missing,
        "latency_exceeded": latency_exceeded,
    }
