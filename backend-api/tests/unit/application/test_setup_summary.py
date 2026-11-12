"""The pure summaries of a setup record (story 2, orchestrator-deploy-folder epic 1,
2026-11-11; AC1, AC2, AC4)."""

from __future__ import annotations

from typing import Any

from orchestrator.application import setup_summary as s
from orchestrator.application.setup_summary import SetupFailure
from orchestrator.domain.entities.setup_run import ScriptRun
from tests.unit.fakes.setup_record import setup_run


def script(**fields: Any) -> dict[str, Any]:
    base = {"name": "10-copy.sh", "exit": 0, "ok": True, "clashes": [], "seconds": 1.0, "log": "l"}
    return {**base, **fields}


def reason(**fields: Any) -> str:
    return s.script_reason(ScriptRun.model_validate(script(**fields)))


def test_every_script_reason_branch() -> None:
    assert reason(exit=1, ok=False) == "exit 1"
    assert reason(exit=124, ok=False) == "timeout"
    assert reason(exit=0, ok=False, clashes=["staged-plan", "bmad-help"]) == (
        "clashes: staged-plan, bmad-help"
    )
    assert reason(exit=2, ok=False, clashes=["a"]) == "exit 2; clashes: a"
    assert reason(exit=0, ok=False) == "failed"


def test_failures_put_bmad_first_then_scripts_in_record_order() -> None:
    run = setup_run(
        bmad={"choice": "installed", "ok": False, "reason": "no network"},
        scripts=[
            script(name="a.sh", exit=1, ok=False),
            script(name="b.sh"),
            script(name="c.sh", exit=124, ok=False),
        ],
    )

    assert s.failures(run) == [
        SetupFailure("bmad", "no network"),
        SetupFailure("a.sh", "exit 1"),
        SetupFailure("c.sh", "timeout"),
    ]


def test_a_bmad_failure_without_a_reason_reads_failed() -> None:
    run = setup_run(bmad={"choice": "installed", "ok": False})

    assert s.failures(run) == [SetupFailure("bmad", "failed")]


def test_harness_setup_for_a_failed_script() -> None:
    run = setup_run(scripts=[script(exit=1, ok=False)])

    got = s.harness_setup(run, "claude")

    assert got is not None
    assert (got.ok, got.trigger, got.skills, got.at) == (False, "install", 12, run.at)
    assert got.failures == (SetupFailure("10-copy.sh", "exit 1"),)


def test_harness_setup_all_ok() -> None:
    got = s.harness_setup(setup_run(), "codex")

    assert got is not None
    assert (got.ok, got.failures, got.skills) == (True, (), 9)


def test_local_uses_the_opencode_count_and_an_unknown_harness_zero() -> None:
    run = setup_run()

    assert [getattr(s.harness_setup(run, h), "skills", None) for h in ("opencode", "local")] == [
        7,
        7,
    ]
    assert getattr(s.harness_setup(run, "fake"), "skills", None) == 0


def test_no_record_is_none_everywhere() -> None:
    assert s.harness_setup(None, "claude") is None
    assert s.bmad_installed(None) is None
    assert s.bmad_choice(None) is None


def test_bmad_installed_branches() -> None:
    ok = {"choice": "installed", "version": "6.13.0", "ok": True}
    assert s.bmad_installed(setup_run(bmad=ok)) == "6.13.0"
    assert s.bmad_installed(setup_run(bmad={**ok, "ok": False})) is None
    assert s.bmad_installed(setup_run(bmad={**ok, "choice": "removed"})) is None
    assert s.bmad_choice(setup_run(bmad={**ok, "choice": "removed"})) == "removed"
