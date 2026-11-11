"""Print the product manifest of a deploy folder as JSON.

Usage: product_manifest.py <deploy_dir> <version_file>

Lists every regular file the client archive carries, minus `llm-platform/` (kept in the
repository for development, never shipped), this manifest itself, and the folder's own
VERSION, which is replaced by the entry hashed from <version_file>.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

SEEDS = ("compose.override.yml", "setup/bmad.choice")
SKIPPED_TOP = ("llm-platform",)
SKIPPED_FILES = ("product-files.json", "VERSION")
ARGC = 3


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(deploy_dir: str, version_file: str) -> dict:
    with open(version_file, encoding="utf-8") as fh:
        release = fh.read().strip()
    paths = []
    for current, dirs, files in os.walk(deploy_dir):
        rel_dir = os.path.relpath(current, deploy_dir)
        if rel_dir == ".":
            dirs[:] = [d for d in dirs if d not in SKIPPED_TOP]
        for name in files:
            rel = name if rel_dir == "." else os.path.join(rel_dir, name).replace(os.sep, "/")
            full = os.path.join(current, name)
            if rel in SKIPPED_FILES or not os.path.isfile(full):
                continue
            paths.append((rel, full))
    paths.append(("VERSION", version_file))
    entries = [
        {
            "path": rel,
            "sha256": _sha256(full),
            "role": "seed" if rel in SEEDS else "product",
        }
        for rel, full in sorted(paths)
    ]
    return {"release": release, "files": entries}


def main(argv: list[str]) -> int:
    if len(argv) != ARGC:
        sys.stderr.write("usage: product_manifest.py <deploy_dir> <version_file>\n")
        return 2
    json.dump(build(argv[1], argv[2]), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
