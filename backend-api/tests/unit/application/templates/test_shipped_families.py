"""The two shipped template families are told apart by name, header and README — and by
nothing a template edit should have to keep (hard rule 6: names and headers only, never steps,
ordering, counts or graph shape).

Operator decision 2026-10-12: the build-auto flow stays as shipped; the split dev agents are
the `staged-*` family beside it. What a reader needs to keep the two maintainable is pinned
here: every shipped file is in `templates/README.md`'s table, every staged file carries the
header block that names its family, caller and sibling, and opens its description with the
family word.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

#: `tests/unit/application/templates/test_shipped_families.py` -> the repository root.
TEMPLATES_DIR = Path(__file__).resolve().parents[5] / "templates"
README = TEMPLATES_DIR / "README.md"
STAGED_PREFIX = "staged-"
HEADER_KEYS = ("# family:", "# called by:", "# sibling:")


def shipped() -> list[Path]:
    return sorted(TEMPLATES_DIR.glob("*.yaml"))


def test_the_readme_table_names_every_shipped_file() -> None:
    listed = set(re.findall(r"\| `([a-z0-9-]+\.yaml)` \|", README.read_text()))
    assert listed == {path.name for path in shipped()}


@pytest.mark.parametrize("path", [p for p in shipped() if p.name.startswith(STAGED_PREFIX)])
def test_every_staged_file_carries_the_family_header(path: Path) -> None:
    text = path.read_text()
    for key in HEADER_KEYS:
        assert key in text, (path.name, key)
    assert "# family: staged" in text, path.name


@pytest.mark.parametrize("path", [p for p in shipped() if p.name.startswith(STAGED_PREFIX)])
def test_every_staged_description_opens_with_the_family_word(path: Path) -> None:
    document = yaml.safe_load(path.read_text())
    assert document["name"] == path.stem
    assert str(document["description"]).startswith("staged:"), path.name


@pytest.mark.parametrize("path", [p for p in shipped() if p.name.startswith(STAGED_PREFIX)])
def test_a_staged_file_calls_only_staged_callees(path: Path) -> None:
    """No callee is shared across families: a staged call tree stays inside the family."""
    for name in re.findall(r"^\s+name: ([a-z0-9-]+)$", path.read_text(), re.MULTILINE):
        assert name.startswith(STAGED_PREFIX), (path.name, name)
