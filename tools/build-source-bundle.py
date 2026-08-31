#!/usr/bin/env python3
"""Build a reviewable, deterministic Sinbar Support Assistant source ZIP."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import stat
import zipfile


ARCHIVE_ROOT = "Sinbar-Remote-Support-Intel-Style-v2.0.0-source"
FIXED_TIME = (2026, 8, 31, 0, 0, 0)
EXCLUDED_PARTS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".swiftpm",
    ".build",
    ".venv",
    "__pycache__",
    "bin",
    "coverage",
    "data",
    "dist",
    "htmlcov",
    "obj",
    "venv",
}
EXCLUDED_SUFFIXES = {
    ".7z",
    ".db",
    ".dmg",
    ".env",
    ".exe",
    ".gz",
    ".key",
    ".log",
    ".msi",
    ".p12",
    ".p8",
    ".pem",
    ".pfx",
    ".pkg",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tar",
    ".tgz",
    ".zip",
}
EXCLUDED_NAMES = {".coverage", ".DS_Store", "coverage.xml"}


def included_files(root: Path) -> list[Path]:
    result: list[Path] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.is_symlink():
            raise SystemExit(f"ERROR: source bundle refuses symlink: {relative}")
        if not path.is_file():
            continue
        if path.suffix.lower() in EXCLUDED_SUFFIXES or path.name in EXCLUDED_NAMES:
            continue
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(root).as_posix())


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def zip_info(name: str, mode: int = 0o644) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIME)
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def build(root: Path, output: Path) -> None:
    files = included_files(root)
    if not files:
        raise SystemExit("ERROR: no source files found")

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + f".new.{os.getpid()}")
    sums: list[str] = []

    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in files:
                relative = path.relative_to(root).as_posix()
                data = path.read_bytes()
                mode = 0o755 if os.access(path, os.X_OK) else 0o644
                archive.writestr(zip_info(f"{ARCHIVE_ROOT}/{relative}", mode), data)
                sums.append(f"{hashlib.sha256(data).hexdigest()}  {relative}")

            manifest = ("\n".join(sums) + "\n").encode("ascii")
            archive.writestr(
                zip_info(f"{ARCHIVE_ROOT}/SOURCE_SHA256SUMS.txt"),
                manifest,
            )

        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    print(f"bundle={output}")
    print(f"bytes={output.stat().st_size}")
    print(f"sha256={digest(output)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.root.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
