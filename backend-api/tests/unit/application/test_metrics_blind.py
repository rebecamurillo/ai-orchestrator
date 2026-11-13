"""The blind rule: models and the template name never survive it (AC8, RM-7)."""

from __future__ import annotations

from orchestrator.application.metrics.blind import HIDDEN, blind_label, blind_value
from tests.unit.application.test_metric_versions import PLAIN_ORIGIN, stored


def test_labels_read_r_then_the_position() -> None:
    assert [blind_label(n) for n in (1, 2)] == ["R1", "R2"]


def test_a_model_and_the_origin_model_and_template_name_are_hidden() -> None:
    value = blind_value(stored(model="claude-opus-5", role="plan"))

    assert value.model == HIDDEN
    assert value.origin.origin_model == HIDDEN
    assert value.origin.template_name == HIDDEN
    assert (value.role, value.metric_id, value.origin.harness) == (
        "plan",
        "activity.tool_calls",
        "claude",
    )


def test_a_model_scope_row_hides_its_key_and_label() -> None:
    value = blind_value(
        stored(
            scope_type="model",
            scope_key="claude-opus-5",
            scope_label="claude-opus-5",
            model="claude-opus-5",
        )
    )

    assert (value.scope_key, value.scope_label) == (HIDDEN, HIDDEN)


def test_other_scopes_keep_their_keys_and_a_value_without_a_model_stays_without() -> None:
    origin = PLAIN_ORIGIN.model_copy(
        update={"origin_model": None, "origin_model_na": "spans_models"}
    )
    value = blind_value(stored(scope_type="run", scope_key="run", origin=origin))

    assert (value.scope_key, value.model, value.origin.origin_model) == ("run", None, None)
    assert value.origin.origin_model_na == "spans_models"
