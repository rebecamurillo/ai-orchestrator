"""The HTTP shape of `GET /steps` (SPEC CAP-5, FR-25 history).

The conventions in `api/schemas/common.py` are what this module checks the row against:
money is a decimal *string* in USD, a timestamp is ISO 8601 UTC ending in `Z`, and the list
is the one `{items, next_cursor}` envelope with no second wrapper. A row that carried a JSON
number for `cost_usd` would lose a fraction-of-a-cent model cost — exactly the comparison
this epic exists to make readable — so it is asserted here rather than left to review.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.api.schemas.history import HistoryPageOut, HistoryRowOut
from orchestrator.application.use_cases.history import HistoryPage, HistoryRow
from orchestrator.domain.ids import new_id

AT = datetime(2026, 9, 9, 8, 30, 15, tzinfo=UTC)
ATTEMPT_ID = new_id()
RUN_ID = new_id()
STEP_SEQ = 7


def a_row(**overrides: object) -> HistoryRow:
    fields: dict[str, object] = {
        "attempt_id": ATTEMPT_ID,
        "run_id": RUN_ID,
        "seq": STEP_SEQ,
        "started_at": AT,
        "ended_at": None,
        "seconds": None,
        "project_name": "acme",
        "run_label": "story v1 · main",
        "path": "epics[0].stories[0].build",
        "kind": "agent",
        "harness": "local",
        "model": "qwen3-coder",
        "session_id": "ses_1",
        "status": "done",
        "token": "DON",
        "tokens_in": 10,
        "tokens_out": 20,
        "cost_usd": Decimal("0.000000"),
        "cost_provisional": False,
        "trace_url": None,
        "log_tail_url": f"/api/v1/runs/{RUN_ID}/detail",
    }
    fields.update(overrides)
    return HistoryRow(**fields)  # type: ignore[arg-type]


def dumped(row: HistoryRow) -> dict[str, object]:
    return json.loads(HistoryRowOut.of(row).model_dump_json())


def test_money_is_a_decimal_string_in_usd_not_a_json_number() -> None:
    body = dumped(a_row(cost_usd=Decimal("12.500000")))

    assert body["cost_usd"] == "12.500000"


def test_a_local_model_records_zero_cost_as_a_string_too() -> None:
    assert dumped(a_row())["cost_usd"] == "0.000000"


def test_a_row_with_no_settled_cost_carries_null() -> None:
    assert dumped(a_row(cost_usd=None))["cost_usd"] is None


def test_a_timestamp_ends_in_z() -> None:
    body = dumped(a_row(ended_at=AT))

    assert body["started_at"] == "2026-09-09T08:30:15Z"
    assert body["ended_at"] == "2026-09-09T08:30:15Z"


def test_a_running_attempt_carries_a_null_end_and_a_null_duration() -> None:
    body = dumped(a_row())

    assert body["ended_at"] is None
    assert body["seconds"] is None


def test_the_ids_are_strings_the_browser_can_link_with() -> None:
    body = dumped(a_row())

    assert body["attempt_id"] == str(ATTEMPT_ID)
    assert body["run_id"] == str(RUN_ID)
    assert body["seq"] == STEP_SEQ


def test_the_page_is_the_one_list_envelope_and_nothing_else() -> None:
    page = HistoryPageOut.of(HistoryPage(items=[a_row()], next_cursor="abc"))

    body = json.loads(page.model_dump_json())
    assert sorted(body) == ["items", "next_cursor"]
    assert body["next_cursor"] == "abc"
    assert len(body["items"]) == 1


def test_the_last_page_states_a_null_cursor_rather_than_omitting_it() -> None:
    body = json.loads(HistoryPageOut.of(HistoryPage(items=[], next_cursor=None)).model_dump_json())

    assert body == {"items": [], "next_cursor": None}
