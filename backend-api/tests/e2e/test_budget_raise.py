"""Raise budget, end to end on the scripted harness (6.6, SPEC CAP-6, FR-17, AD-11).

What only the running stack settles is that a raised budget *resumes what the Run was
doing* — which is two different things depending on the row the budget park landed on, and
`agent_tail.py::_spend_and_budget` is what decides which. FR-17: the step keeps the status
its own file routed to, and the Run parks on top of it.

The gates fixture already scripts both, with no new scenario file: story 1's first dispatch
costs `$0.01` and routes **blocked**, its second costs `$0.02` and routes **done**. So a Run
created with a budget under the first cost parks `budget` over a `blocked` row, and one whose
budget is cleared again by the second dispatch parks `budget` over a `done` row. The two
raises those need are AD-13's two outcomes:

- over `blocked`: `park_kind` goes back to `blocked`, the Run stays `needs_you`, and the
  Question is on screen again — no engine signal at all;
- over `done`: the Run reaches `running` and the walker carries on at the frame's `verify`.

Needs `ORCH_TEST_MODE=1` on the stack (`docker-compose.e2e.yml` sets it, `make e2e` uses it).
The Run is cancelled at the end so it holds neither a global slot nor its Repository's
partition (AD-12).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.gates_fixture import GatesFixture
from tests.e2e.helpers.templates import save_epic_pair
from tests.e2e.test_answer_signal import detail_of, poll_until, step_status
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
TIMEOUT_SECONDS = 10.0

SPEC_FOLDER = "specs/gates"
QUALITY_GATE = "sh check.sh"
DECLARED_BRANCH = "epics/gates"

STORY_1_BUILD = "stories[0].build"
STORY_1_VERIFY = "stories[0].verify"

#: Under `.fake-harness/1/attempt-1.yaml`'s own `cost_usd: "0.01"`, so the first dispatch
#: routes `blocked` and then parks `budget` on top of it (`_spend_and_budget`, FR-17).
STARTING_BUDGET = "0.005"
#: Over the spend after attempt 1 (`$0.01`) and under the spend after attempt 2 (`$0.03`),
#: so the Answer's own dispatch runs and then parks `budget` over a row that routed `done`.
SECOND_BUDGET = "0.02"
#: Clear of everything the fixture costs, so the last raise really resumes the walk.
FINAL_BUDGET = "5"


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def bmad_version() -> str:
    value = os.environ.get("BMAD_VERSION")
    if not value:
        pytest.fail(
            "BMAD_VERSION is not set: the gates fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return value


@pytest.fixture(scope="module")
def gates(settings: Settings, bmad_version: str) -> GatesFixture:
    return GatesFixture(settings.work_dir, bmad_version)


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    response = api.get("/api/v1/harnesses")
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert "fake" in rows, (
        "the `fake` harness is not seeded: this gate needs ORCH_TEST_MODE=1 on the stack "
        "(docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows["fake"]["enabled"] is True, rows["fake"]


@pytest.fixture(scope="module")
def over_budget(
    api: httpx.Client, gates: GatesFixture, test_mode: None
) -> Iterator[dict[str, Any]]:
    """A Run walked until it parks `budget` over story 1's own `blocked` row."""
    project_id = create_project(api)
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={
            "url": gates.make(),
            "default_branch": "main",
            "quality_gate_command": QUALITY_GATE,
            # operator revision 2026-09-15: since the quality-gate reorder (b0f3898) the
            # story's verify row runs `unit_test_command`; declaring it keeps verify
            # exercised — without it the row plans `skipped · no command`.
            "unit_test_command": QUALITY_GATE,
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    template_name, _ = save_epic_pair(api, "e2e-gates-budget")

    started = api.post(
        RUNS,
        json={
            "template_name": template_name,
            "template_version": 1,
            "project_id": project_id,
            "repository_id": repository_id,
            "base_branch": "main",
            "budget_usd": STARTING_BUDGET,
            "harness": "fake",
            "inputs": {"spec_folder": SPEC_FOLDER, "branch": f"{DECLARED_BRANCH}-{uuid4().hex}"},
        },
    )
    assert started.status_code == HTTP_CREATED, started.text
    run_id = str(started.json()["run"]["id"])
    try:
        detail = poll_until(
            api,
            run_id,
            lambda detail: (detail["alert"] or {}).get("park_kind") == "budget",
            "the Run parking on its budget during story 1",
        )
        yield {"id": run_id, "detail": detail}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel"})


def test_the_budget_stop_offers_a_skip_step_beside_the_raise_and_the_cancel(
    over_budget: dict[str, Any],
) -> None:
    """PRD §4.6's row for this park as story 1 of step-handling revised it (SPEC.md: "Skip is
    admitted on every park kind", operator decision 2026-09-25): `skip_story` and `skip_epic`
    stay refused on `budget`, and `skip_step` is admitted on all twelve — the Operator decides
    whether a row is worth skipping, the table does not decide for them.

    What makes it admitted *here* is the row: this park lands on story 1's own `blocked` build
    row (the fixture's first dispatch), and `blocked` is one of the three statuses the step
    machine has a `skip` edge from — so the offer and `validate` agree, which is what the
    assertion below and `test_the_budget_stop_over_a_finished_row_offers_no_skip_step` pin from
    the two sides. This test previously asserted `["budget_raise", "cancel"]` and pinned the
    pre-story-1 set exactly; revised 2026-09-26 on the Operator's word, with the row status it
    depends on now asserted beside it.
    """
    assert over_budget["detail"]["admitted_signals"] == ["skip_step", "budget_raise", "cancel"]
    assert step_status(over_budget["detail"], STORY_1_BUILD) == "blocked"


def test_the_banner_names_the_spend_against_the_budget(over_budget: dict[str, Any]) -> None:
    """UX-DR10's own `budget $x / $y` — `rules/budget.py::forced` writes the reason."""
    reason = over_budget["detail"]["alert"]["reason"]

    assert reason.startswith("budget $")
    assert f"/ ${Decimal(STARTING_BUDGET):.2f}" in reason


def test_a_raise_that_does_not_clear_the_spend_is_refused_with_the_spend(
    api: httpx.Client, over_budget: dict[str, Any]
) -> None:
    """AC3 over the wire: the 409 says which figure has to be beaten."""
    response = api.post(
        f"{RUNS}/{over_budget['id']}/signals",
        json={"kind": "budget_raise", "payload": {"budget_usd": "0.001"}},
    )

    assert response.status_code == HTTP_CONFLICT, response.text
    assert response.json()["detail"].startswith("new budget must exceed spend $")


@pytest.fixture(scope="module")
def raised_over_blocked(api: httpx.Client, over_budget: dict[str, Any]) -> dict[str, Any]:
    """AC1: the raise over a `blocked` row, and the detail it leaves behind."""
    response = api.post(
        f"{RUNS}/{over_budget['id']}/signals",
        json={"kind": "budget_raise", "payload": {"budget_usd": SECOND_BUDGET}},
    )
    assert response.status_code == HTTP_OK, response.text
    return {"signalled": response.json(), "detail": detail_of(api, over_budget["id"])}


def test_the_raise_over_a_blocked_row_leaves_the_run_parked_on_the_question(
    raised_over_blocked: dict[str, Any],
) -> None:
    """AC1: `needs_you`, `park_kind` rewritten to the row's own status, no engine signal —
    so the next poll shows the Question the Story blocked with, not a resumed Run."""
    detail = raised_over_blocked["detail"]

    assert raised_over_blocked["signalled"]["status"] == "needs_you"
    assert detail["run"]["status"] == "needs_you"
    assert detail["alert"]["park_kind"] == "blocked"
    assert step_status(detail, STORY_1_BUILD) == "blocked"


def test_the_new_budget_is_stored_and_the_record_names_the_figure(
    raised_over_blocked: dict[str, Any],
) -> None:
    detail = raised_over_blocked["detail"]
    raises = [entry for entry in detail["gate_record"] if entry["event"] == "budget_raise"]

    assert Decimal(detail["cost"]["budget_usd"]) == Decimal(SECOND_BUDGET)
    assert raises[-1]["actor"] == "operator"
    assert raises[-1]["text"] == f"budget raised to ${Decimal(SECOND_BUDGET):.2f}"


def test_the_question_is_answerable_again_now_the_park_kind_is_back(
    raised_over_blocked: dict[str, Any],
) -> None:
    """The point of the rewrite: the stop the Operator sees is the one they can act on."""
    assert "answer" in raised_over_blocked["detail"]["admitted_signals"]


@pytest.fixture(scope="module")
def over_budget_on_a_done_row(
    api: httpx.Client, over_budget: dict[str, Any], raised_over_blocked: dict[str, Any]
) -> dict[str, Any]:
    """Answer the Question; attempt 2 finishes the Story and costs past the new budget, so
    the Run parks `budget` a second time — this time over a row that routed `done`."""
    answered = api.post(
        f"{RUNS}/{over_budget['id']}/signals",
        json={"kind": "answer", "payload": {"text": "Post to the project's channel only."}},
    )
    assert answered.status_code == HTTP_OK, answered.text
    return poll_until(
        api,
        over_budget["id"],
        lambda detail: (
            (detail["alert"] or {}).get("park_kind") == "budget"
            and step_status(detail, STORY_1_BUILD) == "done"
        ),
        "the Run parking on its budget over story 1's finished build row",
    )


def test_the_second_park_kept_the_status_the_row_routed_to(
    over_budget_on_a_done_row: dict[str, Any],
) -> None:
    """FR-17: the budget park sits *on top of* the route, it does not replace it."""
    assert step_status(over_budget_on_a_done_row, STORY_1_BUILD) == "done"
    assert over_budget_on_a_done_row["run"]["status"] == "needs_you"


def test_the_budget_stop_over_a_finished_row_offers_no_skip_step(
    api: httpx.Client, over_budget: dict[str, Any], over_budget_on_a_done_row: dict[str, Any]
) -> None:
    """The other half of story 1's rule, over the wire (Operator, 2026-09-26). `skip_step` is
    admitted on every park *kind*, but `validate` admits it only from a row that is `blocked`,
    `checkpoint` or `error` — and this is the stop story 1's own brief names as one of the two
    Skip step cannot reach: "a budget park taken after a row ended `done`". The offer reads the
    parked row's status for exactly this reason, so what the stop advertises is what a POST to
    it is allowed to do — asserted here from both sides, the second being the refusal, which
    changes no state.
    """
    assert over_budget_on_a_done_row["admitted_signals"] == ["budget_raise", "cancel"]

    refused = api.post(
        f"{RUNS}/{over_budget['id']}/signals",
        json={"kind": "skip_step"},
    )

    assert refused.status_code == HTTP_CONFLICT, refused.text


def test_raising_over_a_done_row_resumes_the_walk_at_the_next_row(
    api: httpx.Client, over_budget: dict[str, Any], over_budget_on_a_done_row: dict[str, Any]
) -> None:
    """AC2: the Run goes `running` and the walker continues at the frame's `verify` row —
    the half that queued nothing at all before this story."""
    response = api.post(
        f"{RUNS}/{over_budget['id']}/signals",
        json={"kind": "budget_raise", "payload": {"budget_usd": FINAL_BUDGET}},
    )
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "running"

    detail = poll_until(
        api,
        over_budget["id"],
        lambda detail: step_status(detail, STORY_1_VERIFY) in ("running", "done", "error"),
        "story 1's verify row starting after the budget was raised",
    )

    assert step_status(detail, STORY_1_VERIFY) in ("running", "done", "error")
    assert (detail["alert"] or {}).get("park_kind") != "budget"
