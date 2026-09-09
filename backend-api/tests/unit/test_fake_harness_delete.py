"""`delete: [paths]` in the `fake` scenario schema (6.8, SPEC CAP-8, AR-14).

The one effect `files:` cannot express. A UJ-3 scenario has to make the target repository's
own quality gate *fail*, and a gate command decides for itself what "the file is fine" means
— so the only portable way to fail it is for the file to be gone. This module covers the
schema (what `parse` keeps and what it silently drops) and the effect (what `_apply` removes,
and what it declines to remove), the two halves separately, because a path that parses is not
yet a path that was deleted.

Everything here is new: `tests/unit/test_fake_harness_scenarios.py` and
`test_fake_harness_adapter.py` are untouched.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.steps.agent import DISPATCH
from orchestrator.infrastructure.harness.fake import FakeHarness
from orchestrator.infrastructure.harness.fake import scenario as scenarios
from orchestrator.infrastructure.harness.fake.adapter import _apply
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

SPEC_FOLDER = "specs/gates"
STORY_ID = "3"
SESSION = "01a06887-79ab-759b-97a0-71c32ad939d3"

GATE_FILE = "specs/gates/GATE_OK"


def a_prompt() -> str:
    return DISPATCH.format(skill="bmad-build-auto", spec_folder=SPEC_FOLDER, story_id=STORY_ID)


@pytest.fixture
def worktree(tmp_path: Path) -> Path:
    directory = tmp_path / "wt"
    (directory / ".fake-harness" / STORY_ID).mkdir(parents=True)
    (directory / "specs" / "gates").mkdir(parents=True)
    (directory / GATE_FILE).write_text("1\n")
    return directory


def apply_delete(worktree: Path, deletes: tuple[str, ...]) -> None:
    """`_apply` with nothing but a `delete:` list — the effect on its own."""
    _apply(
        worktree,
        scenarios.Dispatch(spec_folder=SPEC_FOLDER, story_id=STORY_ID),
        scenarios.Scenario(delete=deletes),
        a_prompt(),
    )


# ── the schema ──────────────────────────────────────────────────────────────────────────


def test_a_list_of_paths_is_kept_in_order() -> None:
    parsed = scenarios.parse("delete: [GATE_OK, specs/gates/GATE_OK]\n")

    assert parsed.delete == ("GATE_OK", "specs/gates/GATE_OK")


def test_a_scenario_without_the_key_deletes_nothing() -> None:
    assert scenarios.parse("commit: true\n").delete == ()
    assert scenarios.Scenario().delete == ()


@pytest.mark.parametrize(
    "document",
    ["delete: GATE_OK\n", "delete: 3\n", "delete: {a: b}\n", "delete:\n"],
    ids=["a-string", "a-number", "a-mapping", "null"],
)
def test_a_delete_that_is_not_a_list_is_dropped_whole(document: str) -> None:
    """The module's own contract: a malformed key is the field's default, never a raise."""
    assert scenarios.parse(document).delete == ()


def test_entries_that_are_not_usable_paths_are_dropped_one_by_one() -> None:
    parsed = scenarios.parse('delete: ["  ", 7, null, "  GATE_OK  ", {a: b}]\n')

    assert parsed.delete == ("GATE_OK",)


@pytest.mark.parametrize(
    "entry",
    ["/etc/passwd", "../outside", "specs/../../outside", ".."],
    ids=["absolute", "parent", "parent-inside", "bare-parent"],
)
def test_a_path_that_could_reach_outside_the_worktree_is_dropped(entry: str) -> None:
    """A scenario is input inside a Run's worktree; a delete that escapes it is a mistake
    this harness declines to carry out rather than a traceback in a durable step."""
    assert scenarios.parse(f"delete: [{entry!r}]\n").delete == ()


# ── the effect ──────────────────────────────────────────────────────────────────────────


def test_the_named_file_is_gone_after_the_scenario_is_applied(worktree: Path) -> None:
    apply_delete(worktree, (GATE_FILE,))

    assert not (worktree / GATE_FILE).exists()


def test_a_path_that_is_already_absent_is_not_an_error(worktree: Path) -> None:
    """The ordinary case for a `default.yaml` read on a second dispatch."""
    apply_delete(worktree, (GATE_FILE,))
    apply_delete(worktree, (GATE_FILE,))

    assert not (worktree / GATE_FILE).exists()


def test_a_path_that_names_a_directory_is_left_alone(worktree: Path) -> None:
    apply_delete(worktree, ("specs/gates",))

    assert (worktree / "specs" / "gates").is_dir()
    assert (worktree / GATE_FILE).exists()


def test_the_delete_runs_before_the_writes_so_a_re_created_path_survives(
    worktree: Path,
) -> None:
    """Deletes first: a scenario that removes and re-writes the same path ends with the
    write, which is what makes `delete:` composable with `files:` rather than racing it."""
    _apply(
        worktree,
        scenarios.Dispatch(spec_folder=SPEC_FOLDER, story_id=STORY_ID),
        scenarios.Scenario(
            delete=(GATE_FILE,),
            files=(scenarios.FileSpec(path=GATE_FILE, content="0\n"),),
        ),
        a_prompt(),
    )

    assert (worktree / GATE_FILE).read_text() == "0\n"


def test_a_dispatch_carries_the_deletion_into_the_worktree_before_the_process_starts(
    env: dict[str, str], worktree: Path, tmp_path: Path
) -> None:
    """End to end through the adapter, not through `_apply`: `start` applies the scenario's
    writes before any process exists (AD-14), so the file is gone by the time `sh` runs."""
    (worktree / ".fake-harness" / STORY_ID / "default.yaml").write_text(
        "story_file:\n"
        "  slug: ship\n"
        "  content: |\n"
        "    ---\n"
        "    status: done\n"
        "    ---\n"
        f"delete: [{GATE_FILE}]\n"
        "exit_code: 0\n"
    )
    harness = FakeHarness(FakeProcessRunner(), Settings(work_dir=tmp_path / "work"))

    harness.start(
        cwd=worktree,
        prompt=a_prompt(),
        env={"ORCH_RUN_ID": "r"},
        model=None,
        session_id=SESSION,
        budget_usd_remaining=Decimal("5"),
        timeout_min=1.0,
        log_path=tmp_path / "logs" / "run" / "003-1.log",
    )

    assert not (worktree / GATE_FILE).exists()
    assert (worktree / f"{SPEC_FOLDER}/stories/{STORY_ID}-ship.md").exists()
