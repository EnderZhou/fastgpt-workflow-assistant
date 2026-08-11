#!/usr/bin/env python3
"""将完整 GitHub 仓库打包为保留 Unicode 文件名的 ZIP。"""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


EXCLUDED_PARTS = {".git", "__pycache__", ".idea", ".vscode"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("output_zip", type=Path)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def should_include(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    return not any(part in EXCLUDED_PARTS for part in relative.parts) and path.suffix.lower() != ".pyc"


def main() -> int:
    args = parse_args()
    root = args.repository.resolve()
    output = args.output_zip.resolve()
    if not root.is_dir() or not (root / "README.md").is_file():
        raise NotADirectoryError(f"invalid repository root: {root}")
    if root == output.parent or root in output.parents:
        raise ValueError("output ZIP must be outside the repository")
    if output.exists() and not args.force:
        raise FileExistsError(f"refusing to overwrite: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    files = sorted(path for path in root.rglob("*") if path.is_file() and should_include(path, root))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, (Path(root.name) / path.relative_to(root)).as_posix())
    with zipfile.ZipFile(output) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity validation failed")
        names = archive.namelist()
        if f"{root.name}/.github/workflows/validate.yml" not in names:
            raise RuntimeError("GitHub workflow missing from ZIP")
        if any("__pycache__" in name or name.endswith(".pyc") for name in names):
            raise RuntimeError("cache file unexpectedly included")
    print(f"OK: {output}")
    print(f"FILES: {len(files)}")
    print(f"SIZE: {output.stat().st_size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

