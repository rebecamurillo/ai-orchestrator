"""Reading the shipped Template files off disk, for `seed_shipped` at start-up (SPEC CAP-3).

`application/` performs no file I/O (AD-2); this is the one module that reads
`Settings.templates_dir`, handing `main.py` the `(name, yaml_text)` pairs `seed_shipped`
validates and stores. Sorted by name so seeding is deterministic across runs of the same
directory — `seed_shipped` itself tolerates any order, but a stable order keeps its log
lines and its retry rounds reproducible.
"""

from __future__ import annotations

from pathlib import Path

#: The one extension a shipped Template file carries.
TEMPLATE_SUFFIX = ".yaml"


def load_shipped_templates(templates_dir: Path) -> list[tuple[str, str]]:
    """Every `*.yaml` file directly under `templates_dir`, as `(stem, text)`, name-sorted."""
    paths = sorted(templates_dir.glob(f"*{TEMPLATE_SUFFIX}"))
    return [(path.stem, path.read_text()) for path in paths]
