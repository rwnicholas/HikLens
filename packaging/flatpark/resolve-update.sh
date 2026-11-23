#!/usr/bin/env python3
"""Resolve the latest GitHub Release AppImage URL, SHA-256, and byte size for FlatPark."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.request

REPO = "rwnicholas/HikLens"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
MANIFEST_PATH = Path(__file__).resolve().parent / "io.github.rwnicholas.HikLens.yml"


def fetch_latest_appimage_asset() -> tuple[str, str, int]:
    request = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "flatpark-updater"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.loads(response.read().decode("utf-8"))

    tag = str(release.get("tag_name", "")).strip()
    for asset in release.get("assets", []):
        name = str(asset.get("name", ""))
        if name.endswith("-x86_64.AppImage") or name.endswith(".AppImage"):
            return (
                tag,
                str(asset["browser_download_url"]),
                int(asset.get("size", 0)),
            )
    raise RuntimeError(f"No x86_64 AppImage asset found in {REPO} latest release ({tag}).")


def compute_sha256(url: str) -> tuple[str, int]:
    digest = hashlib.sha256()
    total = 0
    request = urllib.request.Request(url, headers={"User-Agent": "flatpark-updater"})
    with urllib.request.urlopen(request, timeout=120) as response:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def update_manifest(url: str, sha256: str, size: int, manifest_path: Path = MANIFEST_PATH) -> None:
    text = manifest_path.read_text(encoding="utf-8")
    text = re.sub(r"(^\s*url:\s*).*$", rf"\g<1>{url}", text, flags=re.MULTILINE)
    text = re.sub(r"(^\s*sha256:\s*).*$", rf"\g<1>{sha256}", text, flags=re.MULTILINE)
    text = re.sub(r"(^\s*size:\s*).*$", rf"\g<1>{size}", text, flags=re.MULTILINE)
    manifest_path.write_text(text, encoding="utf-8")


def main() -> int:
    tag, url, reported_size = fetch_latest_appimage_asset()
    sha256, actual_size = compute_sha256(url)
    size = actual_size or reported_size
    update_manifest(url, sha256, size)
    print(json.dumps({"version": tag.lstrip("v"), "tag": tag, "url": url, "sha256": sha256, "size": size}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
