#!/usr/bin/env python3
"""生成 Trae、WorkBuddy 和通用 Agent Skills 桌面客户端包。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from package_skill import load_version, should_include


MACHINE_NAME = "fastgpt-workflow-assistant"
TRAE_PREFIX = ""
WORKBUDDY_PREFIX = f"{MACHINE_NAME}/"
AGENT_SKILLS_PREFIX = f"{MACHINE_NAME}/"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill_directory", type=Path)
    parser.add_argument("output_directory", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def extract_description(skill_text: str) -> str:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", skill_text, flags=re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 缺少有效 YAML frontmatter")
    for line in match.group(1).splitlines():
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    raise ValueError("SKILL.md frontmatter 缺少 description")


def workbuddy_skill_text(skill_text: str, version: str, display_name: str) -> str:
    match = re.match(r"^---\s*\n.*?\n---\s*\n(.*)$", skill_text, flags=re.DOTALL)
    if not match:
        raise ValueError("SKILL.md 缺少有效 YAML frontmatter")
    body = match.group(1)
    description = extract_description(skill_text)
    description_zh = "构建、修改、调试、测试和发布 FastGPT 工作流，支持文件输入、多文件审核和回导验证。"
    description_en = "Build, modify, debug, test, and package FastGPT workflows with file-input and round-trip validation."
    frontmatter = [
        "---",
        f"name: {MACHINE_NAME}",
        f"display_name: {yaml_quote(display_name)}",
        f"display_name_en: {yaml_quote('FastGPT Workflow Assistant')}",
        f"description: {yaml_quote(description)}",
        f"description_zh: {yaml_quote(description_zh)}",
        f"description_en: {yaml_quote(description_en)}",
        f"version: {version}",
        f"author: {yaml_quote('周鹏')}",
        "disable-model-invocation: false",
        "user-invocable: true",
        "---",
        "",
    ]
    return "\n".join(frontmatter) + body


def archive_files(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and should_include(path, root, "slim-production")
    )


def build_archive(
    root: Path,
    output: Path,
    prefix: str,
    skill_override: str | None,
    force: bool,
) -> dict[str, object]:
    if output.exists() and not force:
        raise FileExistsError(f"拒绝覆盖已存在包：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    files = archive_files(root)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            arcname = f"{prefix}{relative}"
            if relative == "SKILL.md" and skill_override is not None:
                archive.writestr(arcname, skill_override.encode("utf-8"))
            else:
                archive.write(path, arcname)
    with zipfile.ZipFile(output, "r") as archive:
        names = archive.namelist()
        expected_skill = f"{prefix}SKILL.md"
        if expected_skill not in names:
            raise RuntimeError(f"缺少入口：{expected_skill}")
        if archive.testzip() is not None:
            raise RuntimeError(f"ZIP CRC 校验失败：{output}")
        forbidden = {
            f"{prefix}scripts/package_skill.py",
            f"{prefix}scripts/package_desktop_agents.py",
            f"{prefix}scripts/test_skill.py",
            f"{prefix}references/同类技能工程参考.md",
        }
        if forbidden.intersection(names) or any(name.startswith(f"{prefix}scripts/tests/") for name in names):
            raise RuntimeError(f"研发文件泄漏到生产包：{output}")
    digest = hashlib.sha256(output.read_bytes()).hexdigest().upper()
    return {
        "file": output.name,
        "sha256": digest,
        "size": output.stat().st_size,
        "files": len(files),
        "skill_entry": f"{prefix}SKILL.md",
    }


def main() -> int:
    args = parse_args()
    try:
        root = args.skill_directory.resolve()
        if not root.is_dir():
            raise NotADirectoryError(root)
        version = load_version(root)
        version_manifest = json.loads((root / "assets" / "skill-version.json").read_text(encoding="utf-8-sig"))
        display_name = str(version_manifest.get("display_name") or "FastGPT工作流生成助手")
        skill_text = (root / "SKILL.md").read_text(encoding="utf-8-sig")
        workbuddy_text = workbuddy_skill_text(skill_text, version, display_name)
        output_dir = args.output_directory.resolve()
        packages = {
            "trae": build_archive(
                root,
                output_dir / f"fastgpt-workflow-assistant-v{version}_Trae_import-ready.zip",
                TRAE_PREFIX,
                None,
                args.force,
            ),
            "workbuddy": build_archive(
                root,
                output_dir / f"fastgpt-workflow-assistant-v{version}_WorkBuddy_import-ready.zip",
                WORKBUDDY_PREFIX,
                workbuddy_text,
                args.force,
            ),
            "agent_skills": build_archive(
                root,
                output_dir / f"fastgpt-workflow-assistant-v{version}_AgentSkills_folder.zip",
                AGENT_SKILLS_PREFIX,
                None,
                args.force,
            ),
        }
        manifest = {
            "skill_name": MACHINE_NAME,
            "version": version,
            "generated_for": ["Trae", "WorkBuddy", "Agent Skills compatible clients"],
            "validation_status": "candidate packages; target-client import pending",
            "packages": packages,
        }
        manifest_path = output_dir / f"fastgpt-workflow-assistant-v{version}_desktop-packages.json"
        if manifest_path.exists() and not args.force:
            raise FileExistsError(f"拒绝覆盖已存在清单：{manifest_path}")
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "ok", "manifest": str(manifest_path), **manifest}, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
