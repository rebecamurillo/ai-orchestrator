#!/usr/bin/env python3
"""Prove that every manifest names the version in `VERSION` (agent-delivery-kit plan §3).

`VERSION` at the repository root is the release number: the image tag, what release.yml
checks the git tag against, and what `/api/v1/version` reports. Four other files carry a
version field and would drift on their own — `backend-api/pyproject.toml` (the distribution
`/healthz` and `/api/v1/version` read), `web-client/package.json`, the kit's
`deploy/kit/.claude-plugin/plugin.json` and `deploy/kit/manifest.json` (the number a
project's installed kit records and the handshake compares). `make lint` runs this; a
mismatch names every file that disagrees and what it says.

Stays on the system interpreter and inside the standard library, like
`check_test_pairs.py`, and for the same reason: `test_makefile.py` counts the `uv`
invocations in the lint recipe. `python3` may be 3.9 on a stock macOS, so no `tomllib`
(3.11) — `pyproject.toml` is read with a regex over its `[project]` table — and the
`X | None` annotations stay strings under `from __future__ import annotations`.

Usage: `python3 scripts/check_version.py [--root PATH]`; `--root` exists so
`tests/unit/test_check_version.py` can drive the gate against scratch trees.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

VERSION_FILE = "VERSION"
PYPROJECT = "backend-api/pyproject.toml"
PACKAGE_JSON = "web-client/package.json"
PLUGIN_JSON = "deploy/kit/.claude-plugin/plugin.json"
KIT_MANIFEST = "deploy/kit/manifest.json"

#: A release number: `1.2.0`, or `1.0.0-beta` for a pre-release. Never a `v` prefix.
RELEASE = re.compile(r"\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?")
#: `version = "…"` inside the `[project]` table, and nowhere else.
PYPROJECT_VERSION = re.compile(r"^\[project\]\n(?:(?!^\[).*\n)*?version\s*=\s*\"([^\"]*)\"", re.M)


def release_version(root: Path) -> str:
    text = (root / VERSION_FILE).read_text().strip()
    if not RELEASE.fullmatch(text):
        raise SystemExit(f"{VERSION_FILE} does not hold a release number: {text!r}")
    return text


def _json_field(path: Path, *keys: str) -> str | None:
    data = json.loads(path.read_text())
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data if isinstance(data, str) else None


def declared_versions(root: Path) -> list[tuple[str, str | None]]:
    """Each manifest's version field, `None` when the file or the field is missing."""
    found: list[tuple[str, str | None]] = []
    pyproject = root / PYPROJECT
    match = PYPROJECT_VERSION.search(pyproject.read_text()) if pyproject.is_file() else None
    found.append((PYPROJECT, match.group(1) if match else None))
    for relative, keys in (
        (PACKAGE_JSON, ("version",)),
        (PLUGIN_JSON, ("version",)),
        (KIT_MANIFEST, ("kit_version",)),
    ):
        path = root / relative
        found.append((relative, _json_field(path, *keys) if path.is_file() else None))
    return found


def compare(root: Path) -> list[str]:
    """One line per manifest that disagrees with `VERSION`; empty when they all agree."""
    expected = release_version(root)
    return [
        f"{relative}: {declared!r}, VERSION says {expected!r}"
        for relative, declared in declared_versions(root)
        if declared != expected
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    drift = compare(args.root)
    if drift:
        sys.stderr.write("version drift — set every manifest to what VERSION holds:\n")
        for line in drift:
            sys.stderr.write(f"  {line}\n")
        return 1
    names = ", ".join(relative for relative, _ in declared_versions(args.root))
    sys.stdout.write(f"version: {release_version(args.root)} in VERSION, {names}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
