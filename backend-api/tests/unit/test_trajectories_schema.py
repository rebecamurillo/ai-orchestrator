"""The HTTP shape of one `trajectories.jsonl` line (SPEC CAP-6, AD-19, FR-32 export).

The conventions in `api/schemas/common.py` apply here exactly as they do to `HistoryRowOut`
(`test_history_schema.py`): money is a decimal *string* in USD, a timestamp is ISO 8601 UTC
ending in `Z`. This is a single JSON object, not a list — no `{items, next_cursor}` envelope.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.api.schemas.trajectories import TrajectoryLineOut
from orchestrator.domain.entities.trajectory import (
    AttemptRecord,
    GateResults,
    HumanAction,
    ProtectedPathHit,
    ProtectedPathsResult,
    Trajectory,
)
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 9, 8, 30, 15, tzinfo=UTC)


def a_trajectory(**overrides: object) -> Trajectory:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "epic_index": 0,
        "frame": "stories[0]",
        "gate_results": GateResults(build="liveness", verify="done", commit_guard="done"),
        "recorded_at": AT,
    }
    fields.update(overrides)
    return Trajectory(**fields)  # type: ignore[arg-type]


def dumped(trajectory: Trajectory) -> dict[str, object]:
    return json.loads(TrajectoryLineOut.of(trajectory).model_dump_json())


def test_money_is_a_decimal_string_in_usd_not_a_json_number() -> None:
    body = dumped(a_trajectory(cost_usd=Decimal("12.500000")))

    assert body["cost_usd"] == "12.500000"
    assert isinstance(body["cost_usd"], str)


def test_the_timestamp_leaves_as_the_z_form() -> None:
    body = dumped(a_trajectory(recorded_at=AT))

    assert body["recorded_at"] == "2026-09-09T08:30:15Z"


def test_story_file_is_present_even_when_empty() -> None:
    body = dumped(a_trajectory(story_file=""))

    assert body["story_file"] == ""


WALL_CLOCK_SECONDS = 42.5


def test_the_fields_sm1_and_sm3_need_are_all_present() -> None:
    body = dumped(
        a_trajectory(
            harness="claude",
            model="sonnet",
            cost_usd=Decimal("0.010000"),
            wall_clock_seconds=WALL_CLOCK_SECONDS,
            attempts=(AttemptRecord(n=1, route="done"),),
            human_actions=(HumanAction(event="checkpoint", at=AT),),
        )
    )

    assert body["harness"] == "claude"
    assert body["model"] == "sonnet"
    assert body["cost_usd"] == "0.010000"
    assert body["wall_clock_seconds"] == WALL_CLOCK_SECONDS
    assert body["attempts"] == [
        {
            "n": 1,
            "started_at": None,
            "ended_at": None,
            "exit_code": None,
            "session_id": None,
            "cost_usd": None,
            "tokens_in": None,
            "tokens_out": None,
            "route": "done",
        }
    ]
    assert body["human_actions"] == [{"event": "checkpoint", "at": "2026-09-09T08:30:15Z"}]
    assert body["gate_results"] == {
        "build": "liveness",
        "verify": "done",
        "commit_guard": "done",
        "protected_paths": {"hits": [], "accepted": []},
    }


def test_an_attempts_own_money_is_also_a_decimal_string() -> None:
    body = dumped(
        a_trajectory(
            attempts=(
                AttemptRecord(
                    n=2,
                    started_at=AT,
                    ended_at=AT,
                    exit_code=0,
                    session_id="s-1",
                    cost_usd=Decimal("1.234567"),
                    tokens_in=10,
                    tokens_out=20,
                    route="done",
                ),
            )
        )
    )

    assert body["attempts"][0]["cost_usd"] == "1.234567"
    assert body["attempts"][0]["started_at"] == "2026-09-09T08:30:15Z"


def test_protected_path_hits_are_present() -> None:
    body = dumped(
        a_trajectory(
            gate_results=GateResults(
                build="liveness",
                verify="skipped",
                commit_guard="no changes",
                protected_paths=ProtectedPathsResult(
                    hits=(ProtectedPathHit(path="AGENTS.md", kind="modified"),),
                    accepted=("AGENTS.md",),
                ),
            )
        )
    )

    assert body["gate_results"]["protected_paths"] == {
        "hits": [{"path": "AGENTS.md", "kind": "modified"}],
        "accepted": ["AGENTS.md"],
    }


def test_optional_identity_fields_may_be_null() -> None:
    body = dumped(
        a_trajectory(story_id=None, harness=None, model=None, start_sha=None, end_sha=None)
    )

    assert body["story_id"] is None
    assert body["harness"] is None
    assert body["model"] is None
    assert body["start_sha"] is None
    assert body["end_sha"] is None
