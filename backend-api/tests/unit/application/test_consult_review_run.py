"""The consult attempt at a `protected_path` stop (story 1-8, spine AD-17/AD-22, hard rule 1 as
amended 2026-11-02). Before the senior runs it writes the stopped attempt's diff of every hit
beside the decision file, in that hit's own tree. Only `accept` naming exactly the hit files,
with a reason, comes back as an acceptance; every other outcome parks `protected_path` with
status `error` and the original hits payload, so the Operator's `continue` still works."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.domain.ports.git import Change
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Consult, Park, StepResult
from tests.unit.application.consult_fixtures import (
    AGENT_SESSION,
    CONSULT_LOG,
    DECISION,
    SNAP_HEAD,
    World,
    a_consult_world,
    a_decision,
    consulting,
    due_entry,
    planned,
)
from tests.unit.application.steps.agent_budget_fixtures import spend, with_spend
from tests.unit.application.steps.agent_fixtures import ROW_PATH, WORKTREE, a_run, an_attempt
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit

FROZEN, OTHER = "tests/a.py", "tests/b.py"
QUESTION = f"protected path modified: {FROZEN}, {OTHER} · story done"
HITS = {"hits": [{"path": FROZEN, "kind": "modified"}, {"path": OTHER, "kind": "modified"}]}
DIFF_FILE = ".orchestrator/consult/003-2.diff"
DIFF_A = "@@ -1 +1 @@\n-assert old\n+assert new\n"
DIFF_B = "@@ -2 +2 @@\n-x = 1\n+x = 2\n"
START = "1" * 40
MEMBER = f"{WORKTREE}/repos/member"
ROOT_START = "4" * 40


def accepting(files: str, status: str = "accept", reason: str = "AC 2 changes it") -> str:
    said = f"reason: {reason}\n" if reason else ""
    return f"---\nstatus: {status}\napproved_files: {files}\n{said}---\n"


def reviewing(world: World, entry: dict[str, Any]) -> World:
    row = world.row.model_copy(update={"consults": {"protected_path": entry}})
    return replace(world, row=row, ctx=replace(world.ctx, row=row))


def a_review_world(
    decision: str | None = None, *, hits: dict[str, Any] | None = None, **over: Any
) -> World:
    """Attempt 2, a `consult`, on a row whose agent attempt 1 hit `hits` and was offered."""
    fields: dict[str, Any] = {
        "git": FakeGit(
            heads={WORKTREE: [SNAP_HEAD]}, statuses={WORKTREE: ""}, diff=[DIFF_A, DIFF_B]
        ),
        "with_resolved": consulting(consult=planned(on=["blocked", "protected_path"])),
    }
    fields.update(over)
    world = a_consult_world(decision=decision, **fields)
    return reviewing(world, due_entry(question=QUESTION, hits=hits if hits is not None else HITS))


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def parked(reason: str) -> Park:
    return Park(kind="protected_path", reason=reason, path=ROW_PATH)


def fails_closed(world: World, why: str) -> StepResult:
    result = run(world)

    reason = f"{QUESTION} · consult failed: {why}"
    assert result.status == "error"
    assert result.reason == reason
    assert result.park == parked(reason)
    assert result.payload == HITS
    assert result.consult == Consult(kind="protected_path", question=QUESTION, outcome="failed")
    return result


# ── the diff the senior reads ────────────────────────────────────────────────


def test_the_diff_of_every_hit_is_written_beside_the_decision_file() -> None:
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"))

    run(world)

    assert world.workspace.read(DIFF_FILE) == f"### {FROZEN}\n{DIFF_A}\n### {OTHER}\n{DIFF_B}"
    assert world.git.called("diff") == [
        (Path(WORKTREE), START, FROZEN),
        (Path(WORKTREE), START, OTHER),
    ]


def test_the_diff_is_there_while_the_senior_runs() -> None:
    world = a_review_world()
    seen: list[str | None] = []
    world.harness.on_wait = lambda: seen.append(world.workspace.read(DIFF_FILE))

    run(world)

    assert seen == [f"### {FROZEN}\n{DIFF_A}\n### {OTHER}\n{DIFF_B}"]


REAL_DIFF = f"### {FROZEN}\n{DIFF_A}\n### {OTHER}\n{DIFF_B}"


@pytest.mark.parametrize("link", [False, True], ids=["a regular file", "a link"])
def test_a_planted_diff_is_removed_and_the_senior_reads_the_real_one(link: bool) -> None:
    """Review of story 1-8, 2026-11-02: the agent can write the ignored folder."""
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"))
    world.workspace.write(DIFF_FILE, "### tests/a.py\nnothing to see\n")
    if link:
        world.workspace.links.add(DIFF_FILE)
    seen: list[str | None] = []
    world.harness.on_wait = lambda: seen.append(world.workspace.read(DIFF_FILE))

    run(world)

    assert seen == [REAL_DIFF]
    assert DIFF_FILE not in world.workspace.links


def test_a_diff_folder_under_a_link_parks_before_the_senior_runs() -> None:
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"))
    world.workspace.links.add(".orchestrator/consult")

    fails_closed(world, "diff file is under a link")

    assert world.workspace.read(DIFF_FILE) is None
    assert world.harness.calls == []


def test_a_stopped_attempt_with_no_start_parks_before_the_senior_runs() -> None:
    """Review of story 1-8, 2026-11-02: a senior is never sent an empty diff to read."""
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"))
    stopped = an_attempt(world.row, 1, status="error", session_id=AGENT_SESSION, start_sha=None)
    world = replace(world, ctx=replace(world.ctx, previous_attempt=stopped))

    fails_closed(world, f"no start commit to diff {FROZEN} from")

    assert world.git.called("diff") == []
    assert world.harness.calls == []


def test_a_consult_with_no_stopped_attempt_parks_before_the_senior_runs() -> None:
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"))
    world = replace(world, ctx=replace(world.ctx, previous_attempt=None))

    fails_closed(world, f"no start commit to diff {FROZEN} from")

    assert world.harness.calls == []


def test_a_blocked_consult_writes_no_diff() -> None:
    world = a_consult_world(decision=a_decision())

    run(world)

    assert world.workspace.read(DIFF_FILE) is None


# ── an acceptance ────────────────────────────────────────────────────────────


def test_an_accept_naming_exactly_the_hits_goes_back_as_an_acceptance() -> None:
    world = a_review_world(accepting(f"[{OTHER}, {FROZEN}]"))

    result = run(world)

    assert result.status == "error"
    assert result.park is None
    assert result.reason == f"senior accepted: {FROZEN}, {OTHER}"
    assert result.output_ref == str(CONSULT_LOG)
    assert result.consult == Consult(
        kind="protected_path",
        question=QUESTION,
        outcome="accept",
        approved_files=(FROZEN, OTHER),
        reason="AC 2 changes it",
    )


def test_an_accept_reads_the_decision_with_the_stops_kind_not_as_an_answer() -> None:
    world = a_review_world("---\nstatus: answer\nreason: r\n---\n\nRevise it.\n")

    fails_closed(world, "no readable decision")


# ── an escalation ────────────────────────────────────────────────────────────


def test_an_escalation_parks_with_the_seniors_reason_and_the_hits() -> None:
    world = a_review_world("---\nstatus: escalate\nreason: an unrelated test\n---\n")

    result = run(world)

    reason = f"{QUESTION} · senior: an unrelated test"
    assert result.status == "error"
    assert result.park == parked(reason)
    assert result.payload == HITS
    assert result.consult == Consult(kind="protected_path", question=QUESTION, outcome="escalate")


# ── every other outcome fails closed ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("decision", "why"),
    [
        (None, "no readable decision"),
        ("not a decision", "no readable decision"),
        (accepting(f"[{FROZEN}]"), "approved files differ from the hits"),
        (accepting(f"[{FROZEN}, {OTHER}, tests/c.py]"), "approved files differ from the hits"),
        (accepting("[]"), "approved files differ from the hits"),
        (accepting(f"[{FROZEN}, {OTHER}]", reason=""), "approval names no reason"),
    ],
    ids=["no file", "unreadable", "fewer", "more", "none", "no reason"],
)
def test_no_acceptance_fails_closed(decision: str | None, why: str) -> None:
    fails_closed(a_review_world(decision), why)


def test_a_senior_crash_fails_closed() -> None:
    result = HarnessResult(session_id="x", exit_code=2, log_path=CONSULT_LOG)
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"), result=result)

    fails_closed(world, "senior exit 2")


def test_a_senior_that_changed_the_tree_fails_closed() -> None:
    git = FakeGit(
        heads={WORKTREE: ["6" * 40]},
        statuses={WORKTREE: ""},
        diff_changes=[(Change(path=FROZEN, kind="modified"),)],
    )
    world = a_review_world(accepting(f"[{FROZEN}, {OTHER}]"), git=git)

    fails_closed(world, f"tree changed: {FROZEN}")


def test_no_remaining_budget_dispatches_nothing() -> None:
    world = a_review_world(run=a_run(budget_usd=Decimal("5.00"), spend_usd=Decimal("5.00")))

    fails_closed(world, "no remaining budget")

    assert world.harness.calls == []


def test_a_crash_inside_the_consult_still_parks_with_the_hits() -> None:
    git = FakeGit(heads={WORKTREE: [SNAP_HEAD]}, statuses={WORKTREE: ""}, diff=[OSError("gone")])

    fails_closed(a_review_world(accepting(f"[{FROZEN}, {OTHER}]"), git=git), "OSError: gone")


def test_an_acceptance_that_exhausts_the_budget_parks_with_the_budget_on_top() -> None:
    gateway = FakeGateway()
    world = with_spend(
        a_review_world(
            accepting(f"[{FROZEN}, {OTHER}]"),
            run=a_run(budget_usd=Decimal("3.00"), spend_usd=Decimal("2.50")),
        ),
        gateway=gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend("5.00"))

    result = run(world)

    reason = f"{QUESTION} · consult failed: senior accepted (AC 2 changes it); no remaining budget"
    assert result.status == "error"
    assert result.park == parked(reason)
    assert result.payload == HITS
    assert result.consult == Consult(kind="protected_path", question=QUESTION, outcome="accept")
    assert result.budget_park is not None
    assert result.budget_park.kind == "budget"


def test_an_escalation_over_budget_keeps_the_hits_and_gets_the_budget_record() -> None:
    gateway = FakeGateway()
    world = with_spend(
        a_review_world(
            "---\nstatus: escalate\nreason: r\n---\n",
            run=a_run(budget_usd=Decimal("3.00"), spend_usd=Decimal("2.50")),
        ),
        gateway=gateway,
    )
    gateway.script(world.run.id, world.attempt.id, spend("5.00"))

    result = run(world)

    assert result.park == parked(f"{QUESTION} · senior: r")
    assert result.payload == HITS
    assert result.budget_park is not None


# ── a hub row ────────────────────────────────────────────────────────────────


def a_hub_review(decision: str) -> World:
    git = FakeGit(
        heads={MEMBER: [SNAP_HEAD], WORKTREE: ["9" * 40]},
        statuses={MEMBER: "", WORKTREE: ""},
        diff=[DIFF_A, DIFF_B],
    )
    hits = {
        "hits": [
            {"path": "repos/member/tests/a.py", "kind": "modified"},
            {"path": "tests/hub.py", "kind": "modified"},
        ]
    }
    world = a_consult_world(
        decision=decision,
        git=git,
        with_resolved=consulting(
            workdir="repos/member", consult=planned(on=["blocked", "protected_path"])
        ),
    )
    stopped = an_attempt(
        world.row,
        1,
        status="error",
        session_id=AGENT_SESSION,
        start_sha=START,
        root_start_sha=ROOT_START,
    )
    world = replace(world, ctx=replace(world.ctx, previous_attempt=stopped))
    entry = due_entry(
        question=QUESTION,
        hits=hits,
        snapshot={
            "tree": {"head": SNAP_HEAD, "status": ""},
            "root": {"head": "9" * 40, "status": ""},
        },
    )
    return reviewing(world, entry)


def test_a_hub_rows_diff_is_read_in_each_hits_own_tree() -> None:
    world = a_hub_review(accepting("[repos/member/tests/a.py, tests/hub.py]"))

    run(world)

    assert world.git.called("diff") == [
        (Path(MEMBER), START, "tests/a.py"),
        (Path(WORKTREE), ROOT_START, "tests/hub.py"),
    ]
    assert world.workspace.read(DIFF_FILE) == (
        f"### repos/member/tests/a.py\n{DIFF_A}\n### tests/hub.py\n{DIFF_B}"
    )


def test_a_hub_rows_acceptance_keeps_the_workdir_spelling() -> None:
    result = run(a_hub_review(accepting("[repos/member/tests/a.py, tests/hub.py]")))

    assert result.consult is not None
    assert result.consult.outcome == "accept"
    assert result.consult.approved_files == ("repos/member/tests/a.py", "tests/hub.py")


def test_a_hub_root_hit_with_no_root_start_parks_before_the_senior_runs() -> None:
    world = a_hub_review(accepting("[repos/member/tests/a.py, tests/hub.py]"))
    stopped = world.ctx.previous_attempt
    assert stopped is not None
    world = replace(
        world,
        ctx=replace(
            world.ctx, previous_attempt=stopped.model_copy(update={"root_start_sha": None})
        ),
    )

    result = run(world)

    assert result.park is not None
    assert result.park.reason.endswith("consult failed: no start commit to diff tests/hub.py from")
    assert world.harness.calls == []


def test_a_hub_acceptance_spelled_without_the_workdir_fails_closed() -> None:
    result = run(a_hub_review(accepting("[tests/a.py, tests/hub.py]")))

    assert result.park is not None
    assert result.park.reason.endswith("consult failed: approved files differ from the hits")


def test_the_decision_file_is_still_the_consults_own() -> None:
    assert DECISION == ".orchestrator/consult/003-2.decision.md"
    assert DIFF_FILE.removesuffix(".diff") == DECISION.removesuffix(".decision.md")
