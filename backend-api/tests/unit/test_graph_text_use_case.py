"""`graph_text` and `graph_latest` — a posted Template's shape, and the latest stored one's.

3.6's browser half needs a graph for text that is *not* stored yet: the Templates screen
edits YAML, and a diagram that could only be drawn from a saved version would be one save
behind the editor. `graph_text` is that operation, and it is the same two steps
`template_graph` already performs — the one validator (AD-15), then `build_template_graph`
— over text handed in rather than text read back.

It refuses rather than answering, and that is the difference from `validate_text`. A
validation problem is data on `/validate` (NFR-2) because the caller asked *what is wrong*;
here the caller asked for a picture, and text that does not validate has no picture, so
`TemplateValidationFailed` — the exception `save_version` already raises with the validator's
own errors — carries them out to a 422. No third failure type is invented.

`graph_latest` is the read-only sibling `test_bearer_auth.py` makes mandatory: `GET` on the
same path, the latest stored version, answered through `template_graph` so the stored-invalid
case keeps one statement rather than two.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.templates import (
    StoredTemplateInvalid,
    TemplatePorts,
    TemplateValidationFailed,
    graph_latest,
    graph_text,
    template_graph,
)
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.domain.errors import NotFound
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"

LEAF_V2 = (
    "name: leaf\nversion: 2\nsteps:\n"
    "  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
    "  - id: push\n    uses: git.push\n    gate: deterministic\n"
)

CALLER = """\
name: caller
version: 1
inputs:
  folder: { type: path, required: true }
steps:
  - id: first
    uses: git.sync
    gate: deterministic
  - id: items
    for_each: "{{folder}}/items.yaml"
    as: item
    pause_after_item_when: "item.done_checkpoint"
    steps:
      - id: call
        uses: template
        with:
          name: leaf
          version: 1
"""

BROKEN = "name: broken\nversion: 1\nsteps:\n  - id: sync\n    uses: no.such.kind\n"

UNKNOWN_CALLEE = """\
name: caller
version: 1
steps:
  - id: call
    uses: template
    with:
      name: nothing-stores-this
      version: 1
"""

#: `BROKEN`'s `uses:` line — what a refusal built from these errors has to name.
BROKEN_LINE = 5


@pytest.fixture
def templates() -> FakeTemplateVersionRepository:
    return FakeTemplateVersionRepository(
        [TemplateVersion(name="leaf", version=1, yaml=LEAF, hash="sha-leaf")]
    )


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def ports(templates: FakeTemplateVersionRepository, uow: FakeUnitOfWork) -> TemplatePorts:
    return TemplatePorts(uow=uow, templates=templates, clock=FakeClock())


# ── graph_text ───────────────────────────────────────────────────────────────


def test_posted_text_is_answered_as_its_graph(ports: TemplatePorts) -> None:
    graph = graph_text(ports, CALLER)

    assert [node.id for node in graph.nodes] == ["first", "items.call", "items.after"]
    assert [(edge.from_id, edge.to_id) for edge in graph.edges] == [
        ("first", "items.call"),
        ("items.call", "items.after"),
    ]
    assert [group.id for group in graph.groups] == ["items"]
    assert [group.members for group in graph.groups] == [("items.call", "items.after")]


def test_the_posted_graph_is_the_one_the_stored_version_answers(ports: TemplatePorts) -> None:
    """AD-15: one validator, one shaping. Posting a stored version's own text can only
    answer what `template_graph` answers for it, or the diagram and the file disagree."""
    assert graph_text(ports, LEAF) == template_graph(ports, "leaf", 1)


def test_a_collapsed_call_is_resolved_through_the_same_repository(ports: TemplatePorts) -> None:
    call = next(node for node in graph_text(ports, CALLER).nodes if node.id == "items.call")

    assert call.call is not None
    assert (call.call.name, call.call.version) == ("leaf", 1)
    assert call.label == "leaf@1"
    assert call.gate is None


def test_invalid_text_is_refused_with_every_error_the_validator_found(
    ports: TemplatePorts,
) -> None:
    with pytest.raises(TemplateValidationFailed) as raised:
        graph_text(ports, BROKEN)

    assert [error.reason for error in raised.value.errors] == ["unknown kind"]
    assert raised.value.errors[0].line == BROKEN_LINE


def test_text_naming_a_callee_nothing_stores_is_refused(ports: TemplatePorts) -> None:
    with pytest.raises(TemplateValidationFailed) as raised:
        graph_text(ports, UNKNOWN_CALLEE)

    assert raised.value.errors


def test_a_graph_of_posted_text_stores_nothing(
    ports: TemplatePorts, templates: FakeTemplateVersionRepository, uow: FakeUnitOfWork
) -> None:
    before = dict(templates.versions)

    graph_text(ports, CALLER)

    assert templates.versions == before
    assert uow.calls == []


# ── graph_latest ─────────────────────────────────────────────────────────────


def test_the_latest_stored_version_is_the_one_graphed(
    ports: TemplatePorts, templates: FakeTemplateVersionRepository
) -> None:
    templates.add(TemplateVersion(name="leaf", version=2, yaml=LEAF_V2, hash="sha-leaf-2"))

    assert [node.id for node in graph_latest(ports, "leaf").nodes] == ["sync", "push"]


def test_a_single_stored_version_is_the_latest(ports: TemplatePorts) -> None:
    assert [node.id for node in graph_latest(ports, "leaf").nodes] == ["sync"]


def test_a_name_nothing_stores_is_not_found(ports: TemplatePorts) -> None:
    with pytest.raises(NotFound):
        graph_latest(ports, "no-such-template")


def test_stored_text_that_no_longer_validates_is_carried_not_assumed_away(
    ports: TemplatePorts, templates: FakeTemplateVersionRepository
) -> None:
    templates.add(TemplateVersion(name="broken", version=1, yaml=BROKEN, hash="sha-broken"))

    with pytest.raises(StoredTemplateInvalid) as raised:
        graph_latest(ports, "broken")

    assert raised.value.name == "broken"
    assert raised.value.version == 1
    assert [error.line for error in raised.value.errors] == [BROKEN_LINE]


def test_a_stored_call_is_resolved_when_the_latest_is_graphed(
    ports: TemplatePorts, templates: FakeTemplateVersionRepository
) -> None:
    templates.add(
        TemplateVersion(
            name="caller",
            version=1,
            yaml=CALLER,
            hash="sha-caller",
            calls=(TemplateRef(name="leaf", version=1),),
        )
    )

    call = next(node for node in graph_latest(ports, "caller").nodes if node.id == "items.call")

    assert call.label == "leaf@1"
