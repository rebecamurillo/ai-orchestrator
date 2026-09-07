"""`StepRowOut.of()` / `StoryCellOut.of()` actually carry `cost_usd` (5.3) — new file, does
not touch the frozen `test_run_view_schemas.py`.

Every other test either builds a `StepRowView`/`StoryCell` with the default `cost_usd =
Decimal("0")` and never reads it back off the `Out` schema, or asserts on the
application-layer dataclasses directly without ever calling `.of()`. Neither would notice a
reverted or typo'd `cost_usd=row.cost_usd` / `cost_usd=cell.cost_usd` line in `.of()` — the
real `/runs/{run_id}/detail` response would silently show `"0"` for every step and story
cost while every other test in this diff kept passing. This is the one test that would
actually catch that.
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.api.schemas.run_views import StepRowOut, StoryCellOut
from orchestrator.application.use_cases.run_view_types import StepRowView, StoryCell

NON_ZERO_COST = Decimal("12.34")


def test_step_row_out_of_carries_a_non_zero_cost_usd() -> None:
    row = StepRowView(
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="done",
        token="DON",
        reason=None,
        attempts=1,
        latest=None,
        cost_usd=NON_ZERO_COST,
    )

    out = StepRowOut.of(row)

    assert out.cost_usd == NON_ZERO_COST


def test_story_cell_out_of_carries_a_non_zero_cost_usd() -> None:
    cell = StoryCell(epic_index=0, story_id="4-1", state="done", cost_usd=NON_ZERO_COST)

    out = StoryCellOut.of(cell)

    assert out.cost_usd == NON_ZERO_COST
