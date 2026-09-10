"""`attempt_tag`: one definition of the `attempt:` tag, bound to the one that writes it.

Two adapters now *read* that tag back — `LiteLLMSpend` in `attempt_tag` mode narrows spend
rows by it, and `LangfuseTracer`'s session-level fallback queries Langfuse by it — while
`env.py::tag_list` is what writes it into `ORCH_TAGS`/`ORCH_LANGFUSE_TAGS`. These assertions
are what keep the readers and the writer from drifting: they bind the helper to `tag_list`'s
own output rather than to a literal, so a change to the tag format breaks here rather than
silently returning zero rows on a live host.
"""

from __future__ import annotations

from orchestrator.infrastructure.harness.env import TAG_POSITIONS, attempt_tag, tag_list

VALUES = {
    "run": "run-1",
    "attempt": "attempt-2",
    "story": "3",
    "harness": "codex",
    "project": "aio",
}


def test_the_helper_is_one_of_the_tags_tag_list_writes() -> None:
    assert attempt_tag(VALUES["attempt"]) in tag_list(VALUES)


def test_the_helper_names_the_attempt_position_and_no_other() -> None:
    tags = tag_list(VALUES)

    assert tags[TAG_POSITIONS.index("attempt")] == attempt_tag(VALUES["attempt"])


def test_another_positions_value_does_not_produce_the_attempt_tag() -> None:
    """`run:` and `attempt:` both carry a UUID, so a helper that dropped the position
    would match the wrong row on a real host and look right in every other test."""
    assert attempt_tag(VALUES["run"]) not in tag_list(VALUES)


def test_exactly_one_tag_equals_the_helper() -> None:
    tag = attempt_tag(VALUES["attempt"])

    assert [written for written in tag_list(VALUES) if written == tag] == [tag]
