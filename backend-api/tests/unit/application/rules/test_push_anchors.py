"""`application/rules/push_anchors.py`: which paths of the merge Run's push range the anchor
check reads, and which of them are hits (epic 8 retrospective R1, Operator ruling 2026-11-26)."""

from __future__ import annotations

from orchestrator.application.rules.push_anchors import checked, hits, initiative_run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from tests.unit.initiative_fixtures import a_run

GLOBS = ("tests/**/*.py",)


def paths(changes: tuple[Change, ...]) -> list[str]:
    return [change.path for change in changes]


def test_every_document_is_checked_wherever_it_sits() -> None:
    changes = (
        Change(path="AGENTS.md", kind="modified"),
        Change(path="backend-api/AGENTS.md", kind="added"),
        Change(path="initiatives/i/epic-1/SPEC.md", kind="modified"),
        Change(path="initiatives/i/epic-1/stories.yaml", kind="deleted"),
        Change(path="initiatives/i/epics.yaml", kind="modified"),
        Change(path="src/app.py", kind="modified"),
    )

    assert paths(checked(changes, GLOBS)) == [
        "AGENTS.md",
        "backend-api/AGENTS.md",
        "initiatives/i/epic-1/SPEC.md",
        "initiatives/i/epic-1/stories.yaml",
        "initiatives/i/epics.yaml",
    ]


def test_an_existing_test_file_is_checked_and_a_new_one_is_not() -> None:
    changes = (
        Change(path="tests/unit/test_a.py", kind="modified"),
        Change(path="tests/unit/test_b.py", kind="deleted"),
        Change(path="tests/unit/test_c.py", kind="added"),
    )

    assert paths(checked(changes, GLOBS)) == ["tests/unit/test_a.py", "tests/unit/test_b.py"]


def test_a_path_equal_to_the_merge_source_is_not_a_hit() -> None:
    change = Change(path="AGENTS.md", kind="modified")

    assert hits((change,), {"AGENTS.md": "x"}, {"AGENTS.md": "x"}, ()) == ()


def test_a_path_that_differs_from_the_merge_source_is_a_hit() -> None:
    change = Change(path="AGENTS.md", kind="modified")

    assert hits((change,), {"AGENTS.md": "agent"}, {"AGENTS.md": "spec"}, ()) == (change,)


def test_a_path_deleted_at_head_but_held_by_the_source_is_a_hit() -> None:
    change = Change(path="SPEC.md", kind="deleted")

    assert hits((change,), {"SPEC.md": None}, {"SPEC.md": "spec"}, ()) == (change,)


def test_an_accepted_path_is_not_a_hit() -> None:
    change = Change(path="AGENTS.md", kind="modified")

    assert hits((change,), {"AGENTS.md": "agent"}, {"AGENTS.md": "spec"}, ("AGENTS.md",)) == ()


def test_an_initiative_run_is_one_with_an_initiative_id() -> None:
    initiative = a_run(initiative_id=new_id(), initiative_round=1, initiative_position=1)

    assert initiative_run(initiative) is True
    assert initiative_run(a_run()) is False
    assert initiative_run(None) is False
