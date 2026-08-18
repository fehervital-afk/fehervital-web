#!/usr/bin/env python3
"""Build the production-safe static site into ``dist/``.

Only explicitly public files are copied. Local admin tools, AI/business state JSON,
Git metadata, backups and helper scripts are intentionally excluded from the
published directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"

PUBLIC_HTML = (
    "index.html",
    "preview.html",
    "biorezonancia.html",
    "harmonyscan.html",
    "ai.html",
    "kapcsolat.html",
    "adatkezeles.html",
    "idopontfoglalas.html",
)

PUBLIC_FILES = (
    "assets/css/style.css",
    "assets/js/app.js",
    "assets/content/pages.json",
)

PUBLIC_DIRS = (
    "assets/uploads",
)


def copy_file(relative_path: str) -> None:
    source = ROOT / relative_path
    if not source.is_file():
        raise FileNotFoundError(f"Hiányzó publikus fájl: {relative_path}")
    target = DIST / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def copy_dir(relative_path: str) -> None:
    source = ROOT / relative_path
    if not source.exists():
        return
    if not source.is_dir():
        raise NotADirectoryError(f"Nem könyvtár: {relative_path}")
    target = DIST / relative_path
    shutil.copytree(source, target, dirs_exist_ok=True)


def build() -> Path:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    for item in PUBLIC_HTML:
        copy_file(item)
    for item in PUBLIC_FILES:
        copy_file(item)
    for item in PUBLIC_DIRS:
        copy_dir(item)

    return DIST


if __name__ == "__main__":
    output = build()
    files = sum(1 for path in output.rglob("*") if path.is_file())
    print(f"Publikus build elkészült: {output} ({files} fájl)")
