"""Installed-skill pre-flight check (FR-8, story 4-2): `installed_skill_lines` and the
`FsSkillCatalog` adapter that backs it in production.

Every row of the I/O matrix in the story spec is covered here:

(a) catalog unavailable (`FakeSkillCatalog(None)`) → single `skip` line
(b) no skill steps in plan → empty list
(c) skill present → single `ok` line
(d) one skill absent → one `fail` line naming the skill
(e) two skills absent → two `fail` lines (one per name)
(f) plan is `None` → empty list

Plus:
- `skill_catalog=None` on `Context` → also treated as catalog unavailable
- `FsSkillCatalog` adapter: reads JSON manifest; returns `None` on missing/malformed file
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.application.preflight import checks
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import CHECK_INSTALLED_SKILL, PreflightRequest
from orchestrator.application.templates.plan_model import Plan
from orchestrator.domain.values import PlannedRow
from orchestrator.infrastructure.skill_catalog import FsSkillCatalog
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.skill_catalog import FakeSkillCatalog

# ---------------------------------------------------------------------------
# Minimal helpers
# ---------------------------------------------------------------------------


def _row(kind: str = "agent", skill: str | None = None, seq: int = 1) -> PlannedRow:
    with_resolved: dict[str, object] = {}
    if skill is not None:
        with_resolved["skill"] = skill
    return PlannedRow(
        seq=seq,
        path=f"step-{seq}",
        label=f"step-{seq}",
        kind=kind,
        gate="deterministic",
        status="planned",
        reason=None,
        with_resolved=with_resolved,
        frame=None,
        story_id=None,
    )


def _plan(*rows: PlannedRow) -> Plan:
    return Plan(
        rows=tuple(rows),
        branches={},
        plan_ref="abc1234",
    )


def _ctx(**overrides: object) -> Context:
    fields: dict[str, object] = {
        "git": FakeGit(),
        "base_dir": Path("/work/proj/repo/base"),
        "bmad_version": "6.11.0",
        "max_active_runs": 2,
        "repository": None,
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "req": PreflightRequest(),
        "tree": None,
        "plan": None,
        "plan_error": None,
    }
    fields.update(overrides)
    return Context(**fields)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# (f) plan is None → empty list
# ---------------------------------------------------------------------------


def test_installed_skill_lines_returns_empty_when_plan_is_none() -> None:
    ctx = _ctx(skill_catalog=FakeSkillCatalog(frozenset({"bmad-build-auto"})))

    assert checks.installed_skill_lines(ctx) == []


# ---------------------------------------------------------------------------
# (b) no skill steps → empty list
# ---------------------------------------------------------------------------


def test_installed_skill_lines_returns_empty_when_no_skill_steps() -> None:
    plan = _plan(_row(kind="git.worktree"))
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(frozenset({"bmad-build-auto"})))

    assert checks.installed_skill_lines(ctx) == []


def test_installed_skill_lines_returns_empty_for_agent_step_without_skill_key() -> None:
    plan = _plan(_row(kind="agent"))  # no `skill` key in with_resolved
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(frozenset({"bmad-build-auto"})))

    assert checks.installed_skill_lines(ctx) == []


# ---------------------------------------------------------------------------
# (a) catalog unavailable: FakeSkillCatalog(None) → single skip line
# ---------------------------------------------------------------------------


def test_installed_skill_lines_skips_when_installed_skills_returns_none() -> None:
    plan = _plan(_row(kind="agent", skill="bmad-build-auto"))
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(None))

    result = checks.installed_skill_lines(ctx)

    assert len(result) == 1
    assert result[0].check == CHECK_INSTALLED_SKILL
    assert result[0].status == "skip"
    assert "catalog unavailable" in result[0].text


def test_installed_skill_lines_skips_when_skill_catalog_is_none() -> None:
    """Context with no catalog at all (skill_catalog=None) is treated as unavailable."""
    plan = _plan(_row(kind="agent", skill="bmad-build-auto"))
    ctx = _ctx(plan=plan, skill_catalog=None)

    result = checks.installed_skill_lines(ctx)

    assert len(result) == 1
    assert result[0].status == "skip"


# ---------------------------------------------------------------------------
# (c) all skills installed → single ok line
# ---------------------------------------------------------------------------


def test_installed_skill_lines_ok_when_skill_is_installed() -> None:
    plan = _plan(_row(kind="agent", skill="bmad-build-auto"))
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(frozenset({"bmad-build-auto"})))

    result = checks.installed_skill_lines(ctx)

    assert len(result) == 1
    assert result[0].check == CHECK_INSTALLED_SKILL
    assert result[0].status == "ok"


# ---------------------------------------------------------------------------
# (d) one skill absent → one fail line naming it
# ---------------------------------------------------------------------------


def test_installed_skill_lines_fails_when_skill_is_absent() -> None:
    plan = _plan(_row(kind="agent", skill="bmad-missing"))
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(frozenset({"bmad-build-auto"})))

    result = checks.installed_skill_lines(ctx)

    assert len(result) == 1
    assert result[0].check == CHECK_INSTALLED_SKILL
    assert result[0].status == "fail"
    assert "bmad-missing" in result[0].text
    assert result[0].fix is not None


# ---------------------------------------------------------------------------
# (e) multiple absent → one fail per name
# ---------------------------------------------------------------------------


def test_installed_skill_lines_emits_one_fail_per_missing_skill() -> None:
    plan = _plan(
        _row(kind="agent", skill="bmad-x", seq=1),
        _row(kind="agent", skill="bmad-y", seq=2),
    )
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(frozenset()))

    result = checks.installed_skill_lines(ctx)

    expected_count = len(plan.rows)
    assert len(result) == expected_count
    assert all(line.status == "fail" for line in result)
    names = {line.text for line in result}
    assert any("bmad-x" in name for name in names)
    assert any("bmad-y" in name for name in names)


def test_installed_skill_lines_deduplicates_repeated_skill_names() -> None:
    """Two agent steps naming the same skill produce only one fail line."""
    plan = _plan(
        _row(kind="agent", skill="bmad-build-auto", seq=1),
        _row(kind="agent", skill="bmad-build-auto", seq=2),
    )
    ctx = _ctx(plan=plan, skill_catalog=FakeSkillCatalog(frozenset()))

    result = checks.installed_skill_lines(ctx)

    assert len(result) == 1
    assert "bmad-build-auto" in result[0].text


# ---------------------------------------------------------------------------
# FsSkillCatalog adapter
# ---------------------------------------------------------------------------


def test_fs_skill_catalog_returns_skills_from_valid_manifest(tmp_path: Path) -> None:
    manifest = tmp_path / "skills-manifest.json"
    manifest.write_text(json.dumps({"skills": ["bmad-build-auto", "bmad-dev-story"]}))

    catalog = FsSkillCatalog(manifest)

    assert catalog.installed_skills() == frozenset({"bmad-build-auto", "bmad-dev-story"})


def test_fs_skill_catalog_returns_none_when_file_is_missing(tmp_path: Path) -> None:
    catalog = FsSkillCatalog(tmp_path / "nonexistent.json")

    assert catalog.installed_skills() is None


def test_fs_skill_catalog_returns_none_when_json_is_malformed(tmp_path: Path) -> None:
    manifest = tmp_path / "skills-manifest.json"
    manifest.write_text("not valid json {")

    catalog = FsSkillCatalog(manifest)

    assert catalog.installed_skills() is None


def test_fs_skill_catalog_returns_none_when_skills_key_is_missing(tmp_path: Path) -> None:
    manifest = tmp_path / "skills-manifest.json"
    manifest.write_text(json.dumps({"other": ["bmad-build-auto"]}))

    catalog = FsSkillCatalog(manifest)

    assert catalog.installed_skills() is None


def test_fs_skill_catalog_returns_empty_frozenset_for_empty_skills_list(tmp_path: Path) -> None:
    manifest = tmp_path / "skills-manifest.json"
    manifest.write_text(json.dumps({"skills": []}))

    catalog = FsSkillCatalog(manifest)

    assert catalog.installed_skills() == frozenset()
