"""`UpgradePrepareOut.of` (epic 9 story 3)."""

from __future__ import annotations

from orchestrator.api.schemas.instance import UpgradePrepareOut
from orchestrator.application.use_cases.upgrade_prepare import PreparedConversation
from orchestrator.domain.ids import new_id


def test_the_answer_maps_field_for_field_and_keeps_the_order() -> None:
    items = (
        PreparedConversation(new_id(), new_id(), "ux"),
        PreparedConversation(new_id(), new_id(), "tech"),
    )

    out = UpgradePrepareOut.of(items)

    assert [(c.run_id, c.initiative_id, c.step) for c in out.cancelled] == [
        (i.run_id, i.initiative_id, i.step) for i in items
    ]


def test_an_empty_result_is_an_empty_list() -> None:
    assert UpgradePrepareOut.of(()).cancelled == []
