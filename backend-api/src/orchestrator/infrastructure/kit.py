"""The client kit off disk: the one reader of `KIT_DIR` (AD-2).

`deploy/kit/` is what a project repository installs to talk to this instance — the skills
and their installer. The image carries it at `KIT_DIR` so the running instance can hand a
project the kit that matches it exactly: a kit fetched from the instance can never be a
different version than the instance (plan agent-delivery-kit §1, the same law AD-16 lays
down for `BMAD_VERSION`). `api/routers/kit.py` serves what this module reads.

A source-tree run has no kit directory unless `KIT_DIR` points at `deploy/kit`; every
reader answers `None` for an absent kit, and the router turns that into a 404 that says so.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

#: The installer a project pipes into bash, and the manifest carrying the kit's version.
INSTALL_SCRIPT = "install.sh"
MANIFEST = "manifest.json"
MANIFEST_VERSION_KEY = "kit_version"


def kit_version(kit_dir: Path) -> str | None:
    """`kit_version` from the kit's manifest, or `None` when there is no readable manifest."""
    manifest = kit_dir / MANIFEST
    if not manifest.is_file():
        return None
    try:
        data = json.loads(manifest.read_text())
    except ValueError:
        return None
    value = data.get(MANIFEST_VERSION_KEY) if isinstance(data, dict) else None
    return value if isinstance(value, str) and value else None


def install_script(kit_dir: Path) -> str | None:
    """The installer's text, or `None` when the kit is not there."""
    path = kit_dir / INSTALL_SCRIPT
    return path.read_text() if path.is_file() else None


def archive(kit_dir: Path) -> bytes | None:
    """The whole kit as a gzipped tar with paths relative to the kit root, or `None`.

    Files only, name-sorted, so two archives of one kit list their members in one order;
    the installer's presence is what makes a directory a kit at all.
    """
    if not (kit_dir / INSTALL_SCRIPT).is_file():
        return None
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in sorted(candidate for candidate in kit_dir.rglob("*") if candidate.is_file()):
            tar.add(path, arcname=str(path.relative_to(kit_dir)), recursive=False)
    return buffer.getvalue()
