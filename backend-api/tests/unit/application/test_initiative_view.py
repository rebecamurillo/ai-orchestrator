"""`GET /initiatives/{slug}`'s read model (multi-repo initiative S6, 2026-09-23).

The cross-repo DAG is read off the member Runs themselves — AD-12 puts the whole graph
there — so the property worth asserting is that nothing in this projection *derives*
anything: the role, the epic id, the status and the park all come back exactly as the
dispatch and AD-8's two writers left them.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.initiative_view import (
    InitiativeReadPorts,
    get_initiative,
)
from orchestrator.domain.errors import NotFound
from tests.unit.application.initiatives import fixtures as fx


def dispatched() -> tuple[fx.Harness, InitiativeReadPorts]:
    """A whole initiative, dispatched, and the ports the view reads it back through."""
    harness = fx.Harness()
    harness.dispatch(fx.request())
    return harness, InitiativeReadPorts(runs=harness.runs, repositories=harness.repositories)


def test_an_initiative_nothing_was_dispatched_under_is_a_not_found() -> None:
    harness = fx.Harness()
    ports = InitiativeReadPorts(runs=harness.runs, repositories=harness.repositories)

    with pytest.raises(NotFound, match="no initiative 'nope'"):
        get_initiative(ports, "nope")


def test_every_member_run_comes_back_in_the_order_it_was_created() -> None:
    _harness, ports = dispatched()

    view = get_initiative(ports, fx.SLUG)

    assert [(m.role, m.epic_id) for m in view.members] == [
        ("epic", "web-1"),
        ("merge", "web-1"),
        ("epic", "api-1"),
        ("merge", "api-1"),
        ("golive", None),
    ]
    assert view.slug == fx.SLUG


def test_each_member_carries_the_stored_status_and_the_edges_it_waits_on() -> None:
    _harness, ports = dispatched()

    view = get_initiative(ports, fx.SLUG)
    epic = view.members[0]
    merge = view.members[1]

    assert epic.status == "queued"
    assert epic.park_kind is None
    assert epic.park_reason is None
    assert merge.after_run_ids == (epic.run_id,)
    assert merge.template == fx.MERGE_TEMPLATE


def test_a_parked_member_reports_the_park_the_writers_left_on_it() -> None:
    harness, ports = dispatched()
    run_id = harness.runs.list_by_initiative(fx.SLUG)[-1].id
    stored = harness.runs.get(run_id)
    assert stored is not None
    harness.runs.update(
        stored.model_copy(
            update={
                "status": "needs_you",
                "park_kind": "dependency",
                "park_reason": "run x ended failed",
            }
        )
    )

    parked = next(m for m in get_initiative(ports, fx.SLUG).members if m.run_id == run_id)

    assert (parked.status, parked.park_kind, parked.park_reason) == (
        "needs_you",
        "dependency",
        "run x ended failed",
    )


def test_each_repository_reports_the_branch_its_epics_merge_into() -> None:
    _harness, ports = dispatched()

    view = get_initiative(ports, fx.SLUG)

    assert [(r.slug, r.branch) for r in view.repos] == [
        ("web", fx.WEB_BRANCH),
        ("api", fx.API_BRANCH),
        # the hub holds no epic of its own — only the go-live Run — so it has no
        # integration branch to report, and `None` says so rather than borrowing one
        ("hub", None),
    ]


def test_a_repository_row_carries_what_the_screen_links_to() -> None:
    _harness, ports = dispatched()

    web = get_initiative(ports, fx.SLUG).repos[0]

    assert web.repository_id == fx.WEB_ID
    assert web.url.endswith("/web.git")
    assert web.default_branch == fx.MAIN


def test_a_repository_the_store_no_longer_holds_is_left_out_rather_than_guessed() -> None:
    harness, ports = dispatched()
    harness.repositories.repositories.pop(fx.API_ID)

    assert [r.slug for r in get_initiative(ports, fx.SLUG).repos] == ["web", "hub"]
