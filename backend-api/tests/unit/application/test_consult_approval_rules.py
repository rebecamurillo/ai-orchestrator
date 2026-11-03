"""The decision file's `approved_files`, and what a document is (story 1-5, spine AD-17/AD-22,
2026-11-02). Pure: no port."""

from __future__ import annotations

import pytest

from orchestrator.application.rules import consult
from orchestrator.application.rules.protected_paths import is_document
from orchestrator.domain.statuses import MACHINE_EVENTS


def a_file(head: str, body: str = "Edit the assertion.") -> str:
    return f"---\nstatus: answer\n{head}---\n\n{body}\n"


def test_an_absent_key_reads_as_no_files() -> None:
    decision = consult.parse(a_file(""))

    assert decision is not None
    assert decision.approved_files == ()


def test_a_list_of_strings_is_read_in_order() -> None:
    decision = consult.parse(a_file("approved_files: [tests/b.py, tests/a.py]\n"))

    assert decision is not None
    assert decision.approved_files == ("tests/b.py", "tests/a.py")


@pytest.mark.parametrize(
    "head",
    [
        "approved_files: tests/a.py\n",
        "approved_files: {tests/a.py: yes}\n",
        "approved_files: [tests/a.py, 3]\n",
        "approved_files: [[tests/a.py]]\n",
        "approved_files:\n",
    ],
)
def test_anything_but_a_list_of_strings_is_no_readable_decision(head: str) -> None:
    assert consult.parse(a_file(head)) is None


def test_the_acceptance_event_is_a_machine_event() -> None:
    assert consult.ACCEPT_EVENT == "senior_accept"
    assert consult.ACCEPT_EVENT in MACHINE_EVENTS


def test_the_story_baseline_sits_beside_the_decision_file() -> None:
    assert consult.story_path(3, 2) == ".orchestrator/consult/003-2.story.md"
    assert consult.decision_path(3, 2) == ".orchestrator/consult/003-2.decision.md"


@pytest.mark.parametrize(
    "path",
    [
        "specs/x/SPEC.md",
        "specs/x/stories.yaml",
        "initiative/epics.yaml",
        "AGENTS.md",
        "repos/member/web/AGENTS.md",
        "SPEC.md",
    ],
)
def test_the_four_basenames_are_documents(path: str) -> None:
    assert is_document(path)


@pytest.mark.parametrize("path", ["tests/a.py", "tests/SPEC.md.py", "docs/spec.md", "AGENTS.mdx"])
def test_anything_else_is_not_a_document(path: str) -> None:
    assert not is_document(path)
