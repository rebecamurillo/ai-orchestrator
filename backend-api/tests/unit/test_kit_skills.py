"""The contract every skill in `deploy/kit/skills/` holds (agent-delivery-kit plan §4).

The kit is prose, so nothing in the application can refuse a broken skill: a wrong endpoint,
a reference that moved or a pasted credential ships unnoticed. These checks are that refusal.
They are generic over whatever skill directories exist — the kit grows a skill per phase of
the plan, and a test that listed them would have to be revised by every one of those phases.

A skill is a directory under `deploy/kit/skills/` holding a `SKILL.md`. A directory without
one is not yet a skill and is not asserted against.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from tests.unit.conftest import REPO_ROOT

KIT = REPO_ROOT / "deploy" / "kit"
SKILLS = KIT / "skills"
MANIFEST = KIT / "manifest.json"
OPENAPI = REPO_ROOT / "contracts" / "openapi.json"

#: `/api/v1/...` as a skill writes it: inside backticks, inside a URL, inside a table cell.
#: It ends on a path character, so trailing prose punctuation stays out of the match.
API_PATH = re.compile(r"/api/v1/[A-Za-z0-9_.{}/-]*[A-Za-z0-9_}]")
#: `[text](target)`.
MD_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
#: A backticked path to another document in the kit — how the skills cross-reference each
#: other in prose, where a markdown link would read as a URL.
BACKTICK_DOC = re.compile(r"`((?:\./|\.\./|references/)[A-Za-z0-9_./-]+\.md)`")
#: Token shapes, each length-bounded: a bare `sk-` would fire on prose like "risk-free".
SECRETS = (
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\b[0-9a-f]{64}\b"),
)
#: `references/INITIATIVE.md` in `initiative-spec` — the state file the spec chain keeps
#: (plan §6), plus the step-6 command record the plan requires of it.
INITIATIVE_KEYS = {
    "initiative",
    "phase",
    "branch",
    "flavor",
    "autonomy",
    "artifacts",
    "open_questions",
    "decisions",
    "gate",
    "runs",
    "commands_verified",
}


def skill_dirs() -> list[Path]:
    if not SKILLS.is_dir():
        return []
    return sorted(d for d in SKILLS.iterdir() if (d / "SKILL.md").is_file())


def skill_ids() -> list[str]:
    return [d.name for d in skill_dirs()]


def frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text()
    assert text.startswith("---\n"), f"{path} has no YAML frontmatter"
    end = text.index("\n---", 4)
    loaded = yaml.safe_load(text[4:end])
    assert isinstance(loaded, dict), f"{path} frontmatter is not a mapping"
    return loaded


def wildcard(path: str) -> str:
    """A path with every `{param}` segment collapsed, so two spellings of one route match."""
    return "/".join("*" if s.startswith("{") and s.endswith("}") else s for s in path.split("/"))


@pytest.fixture(scope="module")
def routes() -> set[str]:
    paths = json.loads(OPENAPI.read_text())["paths"]
    return {wildcard(p) for p in paths}


@pytest.mark.parametrize("skill", skill_dirs(), ids=skill_ids())
def test_a_skill_declares_the_name_of_its_own_directory(skill: Path) -> None:
    meta = frontmatter(skill / "SKILL.md")

    assert meta.get("name") == skill.name
    description = meta.get("description")
    assert isinstance(description, str) and description.strip(), f"{skill.name}: no description"


@pytest.mark.parametrize("skill", skill_dirs(), ids=skill_ids())
def test_every_endpoint_a_skill_names_exists_in_the_contract(skill: Path, routes: set[str]) -> None:
    missing = {
        f"{doc.relative_to(SKILLS)}: {found}"
        for doc in sorted(skill.rglob("*.md"))
        for found in API_PATH.findall(doc.read_text())
        if wildcard(found) not in routes
    }

    assert not missing, f"endpoints absent from contracts/openapi.json: {sorted(missing)}"


@pytest.mark.parametrize("skill", skill_dirs(), ids=skill_ids())
def test_every_relative_reference_a_skill_makes_resolves(skill: Path) -> None:
    broken = []
    for doc in sorted(skill.rglob("*.md")):
        text = doc.read_text()
        targets = [t for t in MD_LINK.findall(text) if "://" not in t and not t.startswith("#")]
        targets += BACKTICK_DOC.findall(text)
        for target in targets:
            if not (doc.parent / target.split("#")[0]).resolve().exists():
                broken.append(f"{doc.relative_to(SKILLS)} → {target}")

    assert not broken, f"references that resolve to nothing: {broken}"


@pytest.mark.parametrize("skill", skill_dirs(), ids=skill_ids())
def test_no_skill_file_carries_a_token_shaped_string(skill: Path) -> None:
    hits = [
        f"{doc.relative_to(SKILLS)}: {pattern.pattern}"
        for doc in sorted(p for p in skill.rglob("*") if p.is_file())
        for pattern in SECRETS
        if pattern.search(doc.read_text(errors="ignore"))
    ]

    assert not hits, f"credential-shaped strings (hard rule 5): {hits}"


def test_the_manifest_lists_exactly_the_skill_directories() -> None:
    listed = json.loads(MANIFEST.read_text())["skills"]
    present = skill_ids()
    pending = [name for name in listed if name not in present]
    if pending:
        pytest.skip(f"manifest lists skills not yet written: {pending}")

    assert sorted(listed) == sorted(present)


def test_the_initiative_state_template_holds_exactly_the_planned_keys() -> None:
    template = SKILLS / "initiative-spec" / "references" / "INITIATIVE.md"

    assert set(frontmatter(template)) == INITIATIVE_KEYS
