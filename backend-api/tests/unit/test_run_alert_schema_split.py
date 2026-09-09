"""`api/schemas/run_alert.py` — the Alert's own HTTP shapes, and the split that made them one
module (6.7).

`api/schemas/run_views.py` was at its 400-line limit when this story added `TerminalOut`, so
the three Alert shapes moved out along the seam `application/use_cases/run_views_alert.py`
already cut on the builder side. Nothing about the wire changed, and this file is what says
so: every name is still reachable off `run_views`, `AlertOut.of` still projects an `Alert`
whole, and the defaulted fields still carry no JSON-schema `default` — which is what
`openapi-typescript` reads to emit them as optional, and therefore what keeps the web-client
fixtures that predate them compiling (AD-3).
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.api.schemas import run_alert, run_views
from orchestrator.application.use_cases.run_views import Alert, Attribution, CheckpointStory

MOVED = ("AlertOut", "AttributionOut", "CheckpointStoryOut")
#: The fields a fixture written before them omits, so their JSON schema must not name a
#: `default` — see this module's own docstring.
OPTIONAL_FIELDS = ("attribution", "row_kind", "checkpoint_story", "payload")


def test_every_moved_name_is_still_reachable_off_run_views() -> None:
    for name in MOVED:
        assert getattr(run_views, name) is getattr(run_alert, name)


def test_the_alert_projection_is_unchanged_by_the_move() -> None:
    alert = Alert(
        token="BLK",
        reason="intent gap",
        park_kind="blocked",
        attribution=Attribution(harness="claude", model="claude-opus-5", ended_at=None),
        row_kind="agent",
        checkpoint_story=CheckpointStory(
            story_id="1-1", title="Answer", attempts=2, cost_usd=Decimal("1.25"), verify="done"
        ),
        payload={"hits": [{"path": "AGENTS.md", "kind": "modified"}]},
    )

    out = run_alert.AlertOut.of(alert)

    assert out.token == "BLK"
    assert out.park_kind == "blocked"
    assert out.attribution is not None and out.attribution.harness == "claude"
    assert out.checkpoint_story is not None
    assert out.checkpoint_story.cost_usd == Decimal("1.25")
    assert out.payload == {"hits": [{"path": "AGENTS.md", "kind": "modified"}]}


def test_a_minimal_alert_still_omits_everything_a_later_story_added() -> None:
    out = run_alert.AlertOut.of(Alert(token="BLK", reason=None, park_kind=None))

    assert (out.attribution, out.row_kind, out.checkpoint_story, out.payload) == (
        None,
        None,
        None,
        {},
    )


def test_the_optional_fields_publish_no_json_schema_default() -> None:
    """`_drop_default` travelled with them; without it `openapi-typescript` would emit these
    as required and every web-client fixture predating them would stop compiling."""
    schema = run_alert.AlertOut.model_json_schema()

    for field in OPTIONAL_FIELDS:
        assert "default" not in schema["properties"][field], field
