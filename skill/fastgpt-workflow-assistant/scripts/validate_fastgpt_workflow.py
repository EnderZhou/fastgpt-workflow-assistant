#!/usr/bin/env python3
"""离线校验 FastGPT/兼容平台导出的工作流 JSON，并输出稳定诊断码。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any


SYSTEM_TYPES = {"userGuide", "systemConfig"}
SPECIAL_REFERENCE_IDS = {"VARIABLE_NODE_ID", "SYSTEM_VARIABLE_NODE_ID"}
SECRET_PATTERNS = [
    re.compile(r"\bBearer\s+(?!\{\{)[A-Za-z0-9._~-]{16,}", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bfastgpt-[A-Za-z0-9_-]{12,}", re.I),
    re.compile(r"\b(?:api[_-]?key|token|secret)\s*[:=]\s*[\"']?[A-Za-z0-9._~-]{16,}", re.I),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workflow", type=Path, help="工作流导出 JSON")
    parser.add_argument("--baseline", type=Path, help="用于继承比较的上一版导出 JSON")
    parser.add_argument("--expect-preserve-layout", action="store_true", help="要求原节点坐标不变")
    parser.add_argument("--expect-preserve-models", action="store_true", help="要求模型配置不变")
    parser.add_argument("--node", help="用于 JavaScript 语法检查的 Node.js 可执行文件")
    parser.add_argument("--json", action="store_true", dest="json_output", help="输出机器可读 JSON")
    parser.add_argument("--strict", action="store_true", help="把 warning 也视为失败")
    return parser.parse_args()


def issue(
    code: str,
    severity: str,
    message: str,
    *,
    path: str = "$",
    node_id: str | None = None,
    suggested_fix: str = "",
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "severity": severity,
        "message": message,
        "path": path,
        "suggested_fix": suggested_fix,
    }
    if node_id:
        item["node_id"] = node_id
    return item


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as stream:
        data = json.load(stream)
    if not isinstance(data, dict):
        raise ValueError("顶层 JSON 必须是对象")
    return data


def node_id(node: dict[str, Any]) -> str:
    value = node.get("nodeId", node.get("id", ""))
    return str(value) if value is not None else ""


def edge_tuple(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(edge.get("source", "")),
        str(edge.get("target", "")),
        str(edge.get("sourceHandle", "")),
        str(edge.get("targetHandle", "")),
    )


def input_value(node: dict[str, Any], key: str) -> Any:
    for item in node.get("inputs", []):
        if isinstance(item, dict) and item.get("key") == key:
            return item.get("value")
    return None


def collect_models(nodes: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for node in nodes:
        value = input_value(node, "model")
        if isinstance(value, str) and value:
            result[node_id(node)] = value
    return result


def scan_strings(value: Any, path: str = "$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from scan_strings(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from scan_strings(child, f"{path}[{index}]")


def compile_code_nodes(nodes: list[dict[str, Any]], node_executable: str | None) -> tuple[int, list[dict[str, Any]]]:
    diagnostics: list[dict[str, Any]] = []
    checked = 0
    node_path = node_executable or shutil.which("node")

    for index, node in enumerate(nodes):
        if str(node.get("flowNodeType", "")).lower() not in {"code", "coderun", "sandbox"}:
            continue
        current_id = node_id(node)
        code = input_value(node, "code")
        code_type = str(input_value(node, "codeType") or "js").lower()
        item_path = f"$.nodes[{index}].inputs"
        if not isinstance(code, str) or not code.strip():
            diagnostics.append(issue("FG070", "error", "代码节点没有代码", path=item_path, node_id=current_id, suggested_fix="填写代码或移除该节点"))
            continue
        if code_type in {"python", "py"}:
            try:
                compile(code, f"<{current_id}>", "exec")
                checked += 1
            except SyntaxError as exc:
                diagnostics.append(issue("FG071", "error", f"Python 语法错误：第 {exc.lineno} 行，{exc.msg}", path=item_path, node_id=current_id, suggested_fix="修复语法后重新校验"))
        elif code_type in {"js", "javascript"}:
            if not node_path:
                diagnostics.append(issue("FG072", "warning", "未找到 Node.js，已跳过 JavaScript 语法检查", path=item_path, node_id=current_id, suggested_fix="安装 Node.js 或通过 --node 指定可执行文件"))
                continue
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".js", delete=False) as stream:
                stream.write(code)
                temp_path = Path(stream.name)
            try:
                process = subprocess.run(
                    [node_path, "--check", str(temp_path)],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
                if process.returncode:
                    detail = (process.stderr or process.stdout).strip().splitlines()
                    diagnostics.append(issue("FG071", "error", f"JavaScript 语法错误：{' | '.join(detail[-3:])}", path=item_path, node_id=current_id, suggested_fix="修复语法后重新校验"))
                else:
                    checked += 1
            finally:
                temp_path.unlink(missing_ok=True)
        else:
            diagnostics.append(issue("FG073", "warning", f"暂不支持检查代码类型 {code_type!r}", path=item_path, node_id=current_id, suggested_fix="在目标平台手工验证该代码节点"))
    return checked, diagnostics


def validate(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    nodes_raw = data.get("nodes")
    edges_raw = data.get("edges")
    if not isinstance(nodes_raw, list):
        diagnostics.append(issue("FG001", "error", "顶层 nodes 必须是数组", path="$.nodes", suggested_fix="从目标平台重新导出工作流基线"))
        nodes_raw = []
    if not isinstance(edges_raw, list):
        diagnostics.append(issue("FG002", "error", "顶层 edges 必须是数组", path="$.edges", suggested_fix="从目标平台重新导出工作流基线"))
        edges_raw = []

    nodes = [item for item in nodes_raw if isinstance(item, dict)]
    edges = [item for item in edges_raw if isinstance(item, dict)]
    if len(nodes) != len(nodes_raw):
        diagnostics.append(issue("FG010", "error", "一个或多个节点不是对象", path="$.nodes", suggested_fix="移除非法条目或重新导出"))
    if len(edges) != len(edges_raw):
        diagnostics.append(issue("FG010", "error", "一个或多个边不是对象", path="$.edges", suggested_fix="移除非法条目或重新导出"))

    ids = [node_id(node) for node in nodes]
    for index, current_id in enumerate(ids):
        if not current_id:
            diagnostics.append(issue("FG011", "error", "节点缺少 nodeId/id", path=f"$.nodes[{index}]", suggested_fix="从目标版本基线恢复节点 ID"))
    for duplicate in sorted(key for key, count in Counter(ids).items() if key and count > 1):
        diagnostics.append(issue("FG012", "error", f"节点 ID 重复：{duplicate}", path="$.nodes", node_id=duplicate, suggested_fix="为重复节点分配唯一 ID 并修复所有引用和连线"))
    id_set = {value for value in ids if value}

    edge_tuples = [edge_tuple(edge) for edge in edges]
    for duplicate in [item for item, count in Counter(edge_tuples).items() if count > 1]:
        diagnostics.append(issue("FG020", "error", f"边重复：{duplicate}", path="$.edges", suggested_fix="保留一条并确认 Handle 语义"))
    for index, (source, target, source_handle, target_handle) in enumerate(edge_tuples):
        path = f"$.edges[{index}]"
        if source not in id_set:
            diagnostics.append(issue("FG021", "error", f"边引用不存在的源节点：{source!r}", path=path, suggested_fix="修正 source 或恢复缺失节点"))
        if target not in id_set:
            diagnostics.append(issue("FG021", "error", f"边引用不存在的目标节点：{target!r}", path=path, suggested_fix="修正 target 或恢复缺失节点"))
        if source and source == target:
            diagnostics.append(issue("FG022", "warning", f"发现自环边：{source!r}", path=path, node_id=source, suggested_fix="确认循环是否由目标版本节点机制明确支持"))
        if not source_handle or not target_handle:
            diagnostics.append(issue("FG023", "warning", f"边 {source!r}->{target!r} 的 Handle 为空", path=path, suggested_fix="对照目标版本导出物核验 Handle"))

    starts = [node for node in nodes if "workflowstart" in str(node.get("flowNodeType", "")).lower()]
    if not starts:
        diagnostics.append(issue("FG030", "error", "未找到 workflowStart 节点", path="$.nodes", suggested_fix="恢复目标版本的开始节点"))
    elif len(starts) > 1:
        diagnostics.append(issue("FG031", "warning", f"发现多个 workflowStart 节点：{[node_id(node) for node in starts]}", path="$.nodes", suggested_fix="确认目标应用模式是否允许多个开始节点"))

    adjacency: dict[str, list[str]] = defaultdict(list)
    incoming: Counter[str] = Counter()
    for source, target, _, _ in edge_tuples:
        adjacency[source].append(target)
        incoming[target] += 1
    reachable: set[str] = set()
    queue = deque(node_id(node) for node in starts)
    while queue:
        current = queue.popleft()
        if current in reachable:
            continue
        reachable.add(current)
        queue.extend(adjacency.get(current, []))

    business_nodes = [
        node for node in nodes
        if str(node.get("flowNodeType", "")) not in SYSTEM_TYPES
        and "系统配置" not in str(node.get("name", ""))
    ]
    unreachable = [node_id(node) for node in business_nodes if node_id(node) not in reachable]
    if unreachable:
        diagnostics.append(issue("FG032", "error", f"业务节点无法从开始节点到达：{unreachable}", path="$.nodes", suggested_fix="修复连线或移除无用节点；注意未执行节点也可能影响平台校验"))
    no_incoming = [node_id(node) for node in business_nodes if node not in starts and incoming[node_id(node)] == 0]
    if no_incoming:
        diagnostics.append(issue("FG033", "error", f"业务节点没有入边：{no_incoming}", path="$.nodes", suggested_fix="补充连线或移除孤立节点"))

    coordinates: dict[tuple[Any, Any], list[str]] = defaultdict(list)
    for index, node in enumerate(nodes):
        position = node.get("position")
        current_id = node_id(node)
        if not isinstance(position, dict) or "x" not in position or "y" not in position:
            diagnostics.append(issue("FG040", "warning", "节点缺少完整坐标", path=f"$.nodes[{index}].position", node_id=current_id, suggested_fix="从基线恢复坐标或在画布中重新布局"))
            continue
        coordinates[(position.get("x"), position.get("y"))].append(current_id)
    for coordinate, overlapping in coordinates.items():
        if len(overlapping) > 1:
            diagnostics.append(issue("FG041", "warning", f"节点坐标精确重叠 {coordinate}：{overlapping}", path="$.nodes", suggested_fix="为新增分支预留空间并调整坐标"))

    for node_index, node in enumerate(nodes):
        for input_index, item in enumerate(node.get("inputs", [])):
            if not isinstance(item, dict) or "reference" not in item.get("renderTypeList", []):
                continue
            value = item.get("value")
            if not (isinstance(value, list) and value and isinstance(value[0], str)):
                continue
            source = value[0]
            if source not in id_set and source not in SPECIAL_REFERENCE_IDS:
                diagnostics.append(issue("FG050", "error", f"输入引用未知节点：{source}", path=f"$.nodes[{node_index}].inputs[{input_index}]", node_id=node_id(node), suggested_fix="修正引用节点 ID 或恢复上游节点"))

    for path, value in scan_strings(data):
        if any(pattern.search(value) for pattern in SECRET_PATTERNS):
            diagnostics.append(issue("FG060", "warning", "疑似硬编码密钥；未输出实际值", path=path, suggested_fix="改用平台凭据系统或受保护变量，并轮换已暴露凭据"))

    checked_code, code_diagnostics = compile_code_nodes(nodes, args.node)
    diagnostics.extend(code_diagnostics)

    baseline_summary: dict[str, Any] | None = None
    if args.baseline:
        baseline = load_json(args.baseline)
        base_nodes = [item for item in baseline.get("nodes", []) if isinstance(item, dict)]
        base_edges = [item for item in baseline.get("edges", []) if isinstance(item, dict)]
        base_by_id = {node_id(node): node for node in base_nodes}
        current_by_id = {node_id(node): node for node in nodes}
        moved = sorted(current_id for current_id in set(base_by_id) & id_set if base_by_id[current_id].get("position") != current_by_id[current_id].get("position"))
        base_models = collect_models(base_nodes)
        current_models = collect_models(nodes)
        model_changes = {
            current_id: {"before": base_models.get(current_id), "after": current_models.get(current_id)}
            for current_id in sorted(set(base_models) | set(current_models))
            if base_models.get(current_id) != current_models.get(current_id)
        }
        base_edges_set = {edge_tuple(edge) for edge in base_edges}
        current_edges_set = set(edge_tuples)
        baseline_summary = {
            "added_nodes": sorted(id_set - set(base_by_id)),
            "removed_nodes": sorted(set(base_by_id) - id_set),
            "moved_nodes": moved,
            "model_changes": model_changes,
            "added_edges": sorted(current_edges_set - base_edges_set),
            "removed_edges": sorted(base_edges_set - current_edges_set),
        }
        if args.expect_preserve_layout and moved:
            diagnostics.append(issue("FG101", "error", f"要求保留布局，但节点发生移动：{moved}", path="$.nodes", suggested_fix="恢复原坐标或取消不适用的布局保留要求"))
        if args.expect_preserve_models and model_changes:
            diagnostics.append(issue("FG102", "error", f"要求保留模型，但配置发生变化：{model_changes}", path="$.nodes", suggested_fix="恢复模型值或明确记录并接受模型变更"))
    elif args.expect_preserve_layout or args.expect_preserve_models:
        diagnostics.append(issue("FG103", "error", "布局/模型保留检查需要 --baseline", suggested_fix="提供上一版导出 JSON"))

    counts = Counter(item["severity"] for item in diagnostics)
    summary = {
        "nodes": len(nodes),
        "edges": len(edges),
        "start_nodes": len(starts),
        "business_nodes": len(business_nodes),
        "reachable_business_nodes": len(business_nodes) - len(unreachable),
        "code_nodes_syntax_checked": checked_code,
        "models": collect_models(nodes),
        "baseline": baseline_summary,
        "diagnostic_counts": dict(counts),
    }
    return {"schema_version": "1.0", "summary": summary, "diagnostics": diagnostics}


def main() -> int:
    args = parse_args()
    try:
        report = validate(load_json(args.workflow), args)
    except Exception as exc:
        report = {
            "schema_version": "1.0",
            "summary": {"diagnostic_counts": {"error": 1}},
            "diagnostics": [issue("FG000", "error", f"{type(exc).__name__}: {exc}", suggested_fix="检查文件路径、UTF-8 编码和 JSON 语法")],
        }

    if args.json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
        for item in report["diagnostics"]:
            location = item.get("node_id") or item.get("path") or "$"
            print(f"[{item['severity'].upper()}][{item['code']}][{location}] {item['message']}")
            if item.get("suggested_fix"):
                print(f"  修复建议：{item['suggested_fix']}")

    has_errors = any(item["severity"] == "error" for item in report["diagnostics"])
    has_warnings = any(item["severity"] == "warning" for item in report["diagnostics"])
    return 1 if has_errors or (args.strict and has_warnings) else 0


if __name__ == "__main__":
    raise SystemExit(main())
