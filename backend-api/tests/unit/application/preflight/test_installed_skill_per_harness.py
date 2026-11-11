"""Pre-flight checks each named skill on the harness that will run it (story 1,
orchestrator-deploy-folder epic 1, 2026-11-11; AD-29, BR-14)."""

from __future__ import annotations

from typing import Any

from orchestrator.application.preflight import lists
from orchestrator.application.preflight.model import Line, PreflightRequest
from orchestrator.domain.values import PlannedRow
from tests.unit.fakes.skill_catalog import FakeSkillCatalog
from tests.unit.test_preflight_installed_skill import _ctx, _plan

SETUP = "./install.sh setup"


def row(kind: str = "agent", seq: int = 1, **resolved: Any) -> PlannedRow:
    return PlannedRow(
        seq=seq,
        path=f"step-{seq}",
        label=f"step-{seq}",
        kind=kind,
        gate="liveness",
        status="planned",
        reason=None,
        with_resolved=resolved,
        frame=None,
        story_id=None,
    )


def check(
    rows: list[PlannedRow],
    catalog: dict[str, frozenset[str] | None],
    harness: str | None = "codex",
    **ctx_fields: Any,
) -> list[Line]:
    ctx = _ctx(
        plan=_plan(*rows),
        skill_catalog=FakeSkillCatalog(catalog),
        req=PreflightRequest(harness=harness),
        **ctx_fields,
    )
    return lists.installed_skill_lines(ctx)


def shown(lines: list[Line]) -> list[tuple[str, str, str | None]]:
    return [(line.status, line.text, line.fix) for line in lines]


def test_ac1_a_skill_present_only_on_claude_fails_a_codex_run() -> None:
    rows = [row(skill="bmad-build-auto", harness="codex")]

    lines = check(rows, {"claude": frozenset({"bmad-build-auto"}), "codex": frozenset()})

    assert shown(lines) == [("fail", "not installed: bmad-build-auto on codex", SETUP)]


def test_ac2_a_consult_is_checked_on_its_own_harness() -> None:
    rows = [
        row(
            skill="build", harness="codex", consult={"skill": "senior-consult", "harness": "claude"}
        )
    ]
    catalog = {"claude": frozenset({"senior-consult"}), "codex": frozenset({"build"})}

    assert shown(check(rows, catalog)) == [("ok", "ok", None)]
    catalog["codex"] = frozenset()
    assert shown(check(rows, catalog)) == [("fail", "not installed: build on codex", SETUP)]


def test_a_consult_without_a_harness_follows_the_row() -> None:
    rows = [row(skill="build", harness="codex", consult={"skill": "senior-consult"})]
    catalog = {"claude": frozenset({"build", "senior-consult"}), "codex": frozenset({"build"})}

    assert shown(check(rows, catalog)) == [
        ("fail", "not installed: senior-consult on codex", SETUP)
    ]


def test_a_consult_on_a_run_rows_on_fail_is_checked_on_its_own_harness() -> None:
    rows = [row(kind="run", on_fail={"consult": {"skill": "senior-consult", "harness": "claude"}})]

    assert shown(check(rows, {"claude": frozenset(), "codex": frozenset()})) == [
        ("fail", "not installed: senior-consult on claude", SETUP)
    ]
    assert shown(check(rows, {"claude": frozenset({"senior-consult"})})) == [("ok", "ok", None)]


def test_an_on_fail_consult_without_a_harness_follows_the_redispatch_target() -> None:
    # the consult runs inside the redispatched agent row (`agent_consult.py::_consult`), so
    # its fallback harness is that row's, not the `run` row's nor the Run's
    target = row(seq=2, skill="build", harness="claude")
    verify = row(
        kind="run", seq=3, on_fail={"target_seq": 2, "consult": {"skill": "senior-consult"}}
    )
    catalog = {"claude": frozenset({"build"}), "codex": frozenset({"senior-consult"})}

    assert shown(check([target, verify], catalog)) == [
        ("fail", "not installed: senior-consult on claude", SETUP)
    ]


def test_an_on_fail_consult_whose_target_is_not_planned_follows_its_own_row() -> None:
    rows = [row(kind="run", on_fail={"target_seq": 9, "consult": {"skill": "senior-consult"}})]

    assert shown(check(rows, {"codex": frozenset()})) == [
        ("fail", "not installed: senior-consult on codex", SETUP)
    ]


def test_ac4_an_unreadable_catalog_fails_only_its_own_harness() -> None:
    rows = [row(skill="a", harness="claude"), row(seq=2, skill="b", harness="claude")]
    catalog: dict[str, frozenset[str] | None] = {"claude": None, "codex": frozenset({"a", "b"})}

    assert shown(check(rows, catalog, harness="claude")) == [
        ("fail", "catalog unavailable on claude: cannot verify a, b", SETUP)
    ]
    codex_rows = [row(skill="a", harness="codex")]
    assert shown(check(codex_rows, catalog)) == [("ok", "ok", None)]


def test_an_unknown_harness_catalog_is_unavailable() -> None:
    assert shown(check([row(skill="a", harness="gemini")], {})) == [
        ("fail", "catalog unavailable on gemini: cannot verify a", SETUP)
    ]


def test_ac5_every_pair_present_is_one_ok_line() -> None:
    rows = [row(skill="a", harness="claude"), row(seq=2, skill="b", harness="codex")]
    catalog = {"claude": frozenset({"a"}), "codex": frozenset({"b"})}

    assert shown(check(rows, catalog)) == [("ok", "ok", None)]


def test_a_pair_named_twice_is_one_line_but_two_harnesses_are_two() -> None:
    rows = [
        row(skill="a", harness="codex"),
        row(seq=2, skill="a", harness="codex"),
        row(seq=3, skill="a", harness="claude"),
    ]

    lines = check(rows, {"claude": frozenset(), "codex": frozenset()})

    assert [line.text for line in lines] == [
        "not installed: a on codex",
        "not installed: a on claude",
    ]


def test_a_row_without_a_harness_falls_back_to_the_run_then_the_default() -> None:
    rows = [row(skill="a")]

    assert shown(check(rows, {"codex": frozenset()}, harness="codex")) == [
        ("fail", "not installed: a on codex", SETUP)
    ]
    assert shown(check(rows, {"claude": frozenset()}, harness=None)) == [
        ("fail", "not installed: a on claude", SETUP)
    ]


def test_ac8_the_fix_of_a_removed_bmad_skill_is_the_bmad_installer() -> None:
    rows = [
        row(skill="bmad-build-auto", harness="codex"),
        row(seq=2, skill="spec-gate", harness="codex"),
    ]
    catalog = {"codex": frozenset()}

    removed = check(rows, catalog, bmad_choice="removed")
    assert [line.fix for line in removed] == ["./install.sh bmad install", SETUP]
    assert [line.fix for line in check(rows, catalog)] == [SETUP, SETUP]


def test_skill_fix_branches() -> None:
    assert lists.skill_fix("bmad-x", "removed") == "./install.sh bmad install"
    assert lists.skill_fix("bmad-x", "installed") == SETUP
    assert lists.skill_fix("spec-gate", "removed") == SETUP
    assert lists.skill_fix("bmad-x", None) == SETUP
