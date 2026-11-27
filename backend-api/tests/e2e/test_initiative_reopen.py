"""Reopen and the upgrade preparation against the running stack (initiative
orchestrator-initiative-steps, epic 9, SPEC CAP-2, CAP-3, CAP-5).

The unit suite proves each rule over the shared fakes. What only the running stack settles:
`POST /initiatives/{id}/reopen` cancels the real parked spec Run through `signal_run`, re-pushes
a deleted `spec/{slug}` to a real bare origin, and the next round's Run is walked by the real
engine to the reopened step, skipping the rows outside `round_steps`, with the reason as its
first turn beside the turns of the earlier round; `POST /instance/upgrade-prepare` refuses
without a hold and, under one, cancels a real parked conversation.

The fixture hub, package and origin are `test_initiatives.Hub`'s (hard rule 6: no shipped
template is read). The start-up reopen pass needs a backend restart and is proven in the unit
suite only (hard rule 9). Every initiative is cancelled when its test ends, and every hold is
released in `finally`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import UNKNOWN_ID
from tests.e2e.test_initiatives import (
    INITIATIVES,
    SIGNAL_TIMEOUT_SECONDS,
    TIMEOUT_SECONDS,
    Hub,
    branch_sha,
    detail_of,
    in_stack,
    parked_on,
    run_detail,
    spec_run_id,
    step_of,
    wait_for,
)
from tests.e2e.test_mcp_setup_path import Mcp

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

HOLD = "/api/v1/instance/hold"
ACTIVITY = "/api/v1/instance/activity"
UPGRADE_PREPARE = "/api/v1/instance/upgrade-prepare"
HOLD_TTL_SECONDS = 120

REASON = "agent exited 1"
SECOND_ROUND, THIRD_ROUND = 2, 3
DELETE_BRANCH = (
    'set -e; tmp=$(mktemp -d); git clone --quiet "$1" "$tmp/c"; '
    'git -C "$tmp/c" push --quiet origin --delete "$2"; rm -rf "$tmp"'
)


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture
def hub(api: httpx.Client, settings: Settings) -> Iterator[Hub]:
    made = Hub(api, settings)
    yield made
    made.cleanup()


@pytest.fixture
def released(api: httpx.Client) -> Iterator[None]:
    try:
        yield
    finally:
        response = api.delete(HOLD)
        assert response.status_code == HTTP_NO_CONTENT, response.text


def reopen(api: httpx.Client, initiative_id: str, step: str, reason: str) -> httpx.Response:
    return api.post(
        f"{INITIATIVES}/{initiative_id}/reopen",
        json={"step": step, "reason": reason},
        timeout=SIGNAL_TIMEOUT_SECONDS,
    )


def reopened(api: httpx.Client, initiative_id: str, step: str, reason: str) -> dict[str, Any]:
    response = reopen(api, initiative_id, step, reason)
    assert response.status_code == HTTP_CREATED, response.text
    body = dict(response.json())
    assert set(body) == {"run_id", "round"}
    return body


def parked_initiative(api: httpx.Client, hub: Hub) -> tuple[dict[str, Any], str]:
    created = hub.new()
    run_id = spec_run_id(created)
    parked_on(api, run_id, "intake")
    return created, run_id


def live_runs(detail: dict[str, Any]) -> list[dict[str, Any]]:
    return [run for run in detail["runs"] if run["status"] not in {"done", "failed", "cancelled"}]


def cancel_events(api: httpx.Client, run_id: str) -> list[dict[str, Any]]:
    records = run_detail(api, run_id)["gate_record"]
    return [record for record in records if record["event"] == "cancel"]


# ── CAP-2: reopen a parked step ─────────────────────────────────────────────────────────


def test_reopen_cancels_the_parked_run_and_walks_round_two_to_the_step_with_the_reason(
    api: httpx.Client, hub: Hub
) -> None:
    created, first = parked_initiative(api, hub)
    slug = created["slug"]
    before = branch_sha(hub.url, f"spec/{slug}")

    body = reopened(api, created["id"], "intake", REASON)

    assert body["round"] == SECOND_ROUND
    assert body["run_id"] != first
    assert run_detail(api, first)["run"]["status"] == "cancelled"
    assert cancel_events(api, first), "the cancel goes through signal_run and is recorded"
    assert branch_sha(hub.url, f"spec/{slug}") == before, "an existing branch is attached"

    run = run_detail(api, body["run_id"])["run"]
    assert (run["template"], run["version"]) == (f"{hub.package}.spec", 1)
    assert run["inputs"]["round_steps"] == "intake,product"
    assert run["inputs"]["first_turn"] == REASON
    assert run["inputs"]["branch"] == f"spec/{slug}"

    parked_on(api, body["run_id"], "intake")
    detail = detail_of(api, created["id"])
    assert detail["round"] == SECOND_ROUND
    assert [r["id"] for r in live_runs(detail)] == [body["run_id"]]
    [latest] = [r for r in detail["runs"] if r["id"] == body["run_id"]]
    assert (latest["round"], latest["position"]) == (SECOND_ROUND, 0)
    intake = step_of(detail, "intake")
    messages = [turn["message"] for turn in intake["turns"]]
    assert created["first_message"] in messages, "the earlier round's turns are kept"
    assert REASON in messages
    assert intake["reopened_after"] is None, "no auto entry was cancelled by this reopen"


def test_reopen_of_a_later_step_skips_the_rows_outside_the_round(
    api: httpx.Client, hub: Hub
) -> None:
    created, _ = parked_initiative(api, hub)

    body = reopened(api, created["id"], "product", REASON)

    assert run_detail(api, body["run_id"])["run"]["inputs"]["round_steps"] == "product"
    walked = parked_on(api, body["run_id"], "product")
    intake = next(row for row in walked["steps"] if row["path"] == "intake")
    assert intake["status"] == "skipped"


def test_reopen_recreates_a_deleted_spec_branch_from_the_default_branch(
    api: httpx.Client, hub: Hub
) -> None:
    created, first = parked_initiative(api, hub)
    branch = f"spec/{created['slug']}"
    in_stack(DELETE_BRANCH, hub.url, branch)
    assert branch_sha(hub.url, branch) == ""

    body = reopened(api, created["id"], "intake", REASON)

    assert branch_sha(hub.url, branch) == branch_sha(hub.url, "main")
    assert run_detail(api, first)["run"]["status"] == "cancelled"
    parked_on(api, body["run_id"], "intake")


def test_two_reopens_in_a_row_make_round_three_with_one_live_run(
    api: httpx.Client, hub: Hub
) -> None:
    created, _ = parked_initiative(api, hub)

    second = reopened(api, created["id"], "intake", REASON)
    third = reopened(api, created["id"], "intake", "again")

    assert (second["round"], third["round"]) == (SECOND_ROUND, THIRD_ROUND)
    assert run_detail(api, second["run_id"])["run"]["status"] == "cancelled"
    detail = detail_of(api, created["id"])
    assert detail["round"] == THIRD_ROUND
    assert [r["id"] for r in live_runs(detail)] == [third["run_id"]]
    assert sorted(r["round"] for r in detail["runs"]) == [1, 2, 3]


# ── CAP-2: the refusals write nothing ───────────────────────────────────────────────────


def test_reopen_refuses_a_step_that_is_not_a_conversation_and_a_blank_reason(
    api: httpx.Client, hub: Hub
) -> None:
    created, first = parked_initiative(api, hub)
    url = f"{INITIATIVES}/{created['id']}/reopen"

    for step in ("gate", "merge", "deploy"):
        refused = reopen(api, created["id"], step, REASON)
        assert refused.status_code == HTTP_UNPROCESSABLE, refused.text
        assert refused.headers["content-type"].startswith("application/problem+json")
        assert step in refused.json()["detail"]
    blank = reopen(api, created["id"], "intake", "   ")
    assert blank.status_code == HTTP_UNPROCESSABLE, blank.text
    extra = api.post(url, json={"step": "intake", "reason": REASON, "x": 1})
    assert extra.status_code == HTTP_UNPROCESSABLE, extra.text
    missing = api.post(url, json={"step": "intake"})
    assert missing.status_code == HTTP_UNPROCESSABLE, missing.text

    detail = detail_of(api, created["id"])
    assert detail["round"] == 1
    assert [r["id"] for r in detail["runs"]] == [first]
    assert run_detail(api, first)["run"]["status"] == "needs_you"


def test_reopen_refuses_an_unknown_and_a_cancelled_initiative(api: httpx.Client, hub: Hub) -> None:
    unknown = reopen(api, UNKNOWN_ID, "intake", REASON)
    assert unknown.status_code == HTTP_NOT_FOUND, unknown.text

    created = hub.new()
    cancelled = api.post(f"{INITIATIVES}/{created['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)
    assert cancelled.status_code == HTTP_OK, cancelled.text

    refused = reopen(api, created["id"], "intake", REASON)

    assert refused.status_code == HTTP_CONFLICT, refused.text
    assert created["slug"] in refused.json()["detail"]
    assert "cancelled" in refused.json()["detail"]
    detail = detail_of(api, created["id"])
    assert detail["round"] == 1
    assert len(detail["runs"]) == 1


# ── CAP-3: the upgrade preparation ──────────────────────────────────────────────────────


def test_upgrade_prepare_without_a_hold_is_409_and_cancels_nothing(
    api: httpx.Client, hub: Hub
) -> None:
    assert api.delete(HOLD).status_code == HTTP_NO_CONTENT
    _, run_id = parked_initiative(api, hub)

    refused = api.post(UPGRADE_PREPARE)

    assert refused.status_code == HTTP_CONFLICT, refused.text
    assert refused.headers["content-type"].startswith("application/problem+json")
    assert "no instance hold" in refused.json()["detail"]
    assert run_detail(api, run_id)["run"]["status"] == "needs_you"


def test_upgrade_prepare_under_a_hold_cancels_a_parked_conversation(
    api: httpx.Client, hub: Hub, released: None
) -> None:
    created, run_id = parked_initiative(api, hub)
    wait_for(
        lambda: api.get(ACTIVITY).json()["working"],
        lambda working: not working,
        "the instance to have no working step",
    )
    placed = api.post(HOLD, json={"ttl_seconds": HOLD_TTL_SECONDS, "reason": "e2e upgrade"})
    assert placed.status_code == HTTP_CREATED, placed.text

    response = api.post(UPGRADE_PREPARE, timeout=SIGNAL_TIMEOUT_SECONDS)

    # The preparation is instance-wide: an interactive initiative Run another module left
    # live on a non-conversation stop refuses it. Either answer is checked in full.
    if response.status_code == HTTP_CONFLICT:
        detail = response.json()["detail"]
        assert detail.startswith("upgrade-prepare refused"), detail
        assert run_id not in detail
        assert run_detail(api, run_id)["run"]["status"] == "needs_you"
        return
    assert response.status_code == HTTP_OK, response.text
    cancelled = response.json()["cancelled"]
    ours = [item for item in cancelled if item["run_id"] == run_id]
    assert ours == [{"run_id": run_id, "initiative_id": created["id"], "step": "intake"}]
    assert run_detail(api, run_id)["run"]["status"] == "cancelled"
    assert cancel_events(api, run_id)
    detail = detail_of(api, created["id"])
    assert detail["cancelled_at"] is None, "the initiative stays open for the start-up reopen"
    assert detail["round"] == 1


# ── CAP-5, B10: bearer, and no MCP tool ─────────────────────────────────────────────────


def test_reopen_and_upgrade_prepare_need_the_bearer(client: httpx.Client) -> None:
    calls = [
        ("POST", f"{INITIATIVES}/{UNKNOWN_ID}/reopen"),
        ("POST", UPGRADE_PREPARE),
    ]
    for method, url in calls:
        response = client.request(method, url, json={"step": "intake", "reason": REASON})
        assert response.status_code == httpx.codes.UNAUTHORIZED, (method, url)


def test_no_mcp_tool_reaches_reopen_or_the_upgrade_preparation(api: httpx.Client) -> None:
    tools = Mcp(api)._post("tools/list", {})["result"]["tools"]

    names = {tool["name"] for tool in tools}

    assert not {name for name in names if "reopen" in name or "upgrade" in name}, names
