#!/usr/bin/env python3
"""Create the post-signing Sinbar release manifest and SHA-256 list."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys


EXPECTED_ASSETS = (
    (
        "Sinbar-Support-Assistant-Setup.exe",
        "windows",
        b"MZ",
    ),
    (
        "Sinbar-Support-Assistant.pkg",
        "macos",
        b"xar!",
    ),
)


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"ERROR: {message}")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_created_at(value: str) -> str:
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("--created-at must be an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        fail("--created-at must include an explicit timezone")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets-dir", required=True, type=pathlib.Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--output-dir", required=True, type=pathlib.Path)
    args = parser.parse_args()

    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", args.tag):
        fail("release tag must be vMAJOR.MINOR.PATCH")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", args.commit):
        fail("commit must be a full 40-character Git object ID")

    assets_dir = args.assets_dir.resolve(strict=True)
    output_dir = args.output_dir.resolve()
    if not assets_dir.is_dir():
        fail("--assets-dir is not a directory")
    output_dir.mkdir(parents=True, exist_ok=True)

    version = args.tag[1:]
    assets: list[dict[str, object]] = []
    expected_names = {entry[0] for entry in EXPECTED_ASSETS}
    actual_names = {
        entry.name
        for entry in assets_dir.iterdir()
        if entry.name not in {"release-manifest.json", "SHA256SUMS.txt"}
    }
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        unexpected = sorted(actual_names - expected_names)
        fail(f"release asset set mismatch; missing={missing}, unexpected={unexpected}")

    for name, platform, magic in EXPECTED_ASSETS:
        path = assets_dir / name
        if path.is_symlink() or not path.is_file():
            fail(f"release asset must be a regular non-symlink file: {name}")
        if path.stat().st_size <= len(magic):
            fail(f"release asset is empty or truncated: {name}")
        with path.open("rb") as handle:
            if handle.read(len(magic)) != magic:
                fail(f"release asset has the wrong file signature: {name}")

        assets.append(
            {
                "bytes": path.stat().st_size,
                "downloadPath": f"/download/v{version}/{platform}/{name}",
                "name": name,
                "platform": platform,
                "sha256": sha256(path),
            }
        )

    manifest = {
        "assets": assets,
        "release": {
            "commit": args.commit.lower(),
            "createdAt": validate_created_at(args.created_at),
            "tag": args.tag,
            "version": version,
        },
        "schemaVersion": 1,
    }
    manifest_path = output_dir / "release-manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    checksum_paths = [assets_dir / entry[0] for entry in EXPECTED_ASSETS]
    checksum_paths.append(manifest_path)
    checksum_lines = [
        f"{sha256(path)}  {path.name}"
        for path in sorted(checksum_paths, key=lambda item: item.name)
    ]
    (output_dir / "SHA256SUMS.txt").write_text(
        "\n".join(checksum_lines) + "\n",
        encoding="ascii",
        newline="\n",
    )

    print("PASS: post-signing release manifest and SHA-256 list created")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exception:
        print(f"ERROR: {exception}", file=sys.stderr)
        raise SystemExit(1) from exception
