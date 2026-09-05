"""`template_graph` — one stored version, re-parsed and shaped (3.4).

The use case is `get_version`'s read-then-`validate()` shape with `build_template_graph` on
the end: the stored text goes through the one validator (AD-15), never through a second
reading, so the graph a screen draws and the errors a validation reports come from the same
judgement.

`StoredTemplateInvalid` covers the case storage is meant to make impossible — only validated
text is ever saved — because "impossible" and "unhandled" are different things, and the
router has to have something to render. It carries the validator's own errors, the way
`TemplateValidationFailed` does for a save.
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.templates import (
    StoredTemplateInvalid,
    TemplatePorts,
    template_graph,
)
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.domain.errors import NotFound
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

LEAF = "name: leaf\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"

CALLER = """\
name: caller
version: 1
inputs:
  folder: { type: path, required: true }
steps:
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

#: `BROKEN`'s `uses:` line — what the 500 the router renders has to name.
BROKEN_LINE = 5


@pytest.fixture
def ports() -> TemplatePorts:
    templates = FakeTemplateVersionRepository(
        [
            TemplateVersion(name="leaf", version=1, yaml=LEAF, hash="sha-leaf"),
            TemplateVersion(
                name="caller",
                version=1,
                yaml=CALLER,
                hash="sha-caller",
                calls=(TemplateRef(name="leaf", version=1),),
            ),
        ]
    )
    return TemplatePorts(uow=FakeUnitOfWork(), templates=templates, clock=FakeClock())


def test_a_stored_version_is_answered_as_its_graph(ports: TemplatePorts) -> None:
    graph = template_graph(ports, "caller", 1)

    assert [node.id for node in graph.nodes] == ["items.call", "items.after"]
    assert [(edge.from_id, edge.to_id) for edge in graph.edges] == [("items.call", "items.after")]
    assert [group.id for group in graph.groups] == ["items"]


def test_the_call_node_names_the_callee_the_file_pinned(ports: TemplatePorts) -> None:
    call = next(node for node in template_graph(ports, "caller", 1).nodes if node.call)

    assert call.call is not None
    assert (call.call.name, call.call.version) == ("leaf", 1)


def test_the_callee_is_read_through_the_same_repository() -> None:
    """The proof, and not merely the claim: with the callee absent from the store the same
    text stops validating — `callee not found` — so the caller's graph is built against what
    this repository holds, not against the caller's text alone."""
    ports = TemplatePorts(
        uow=FakeUnitOfWork(),
        templates=FakeTemplateVersionRepository(
            [
                TemplateVersion(
                    name="caller",
                    version=1,
                    yaml=CALLER,
                    hash="sha-caller",
                    calls=(TemplateRef(name="leaf", version=1),),
                )
            ]
        ),
        clock=FakeClock(),
    )

    with pytest.raises(StoredTemplateInvalid) as raised:
        template_graph(ports, "caller", 1)

    assert [error.reason for error in raised.value.errors] == ["callee not found"]


def test_a_leaf_template_is_answered_as_its_one_node(ports: TemplatePorts) -> None:
    graph = template_graph(ports, "leaf", 1)

    assert [node.id for node in graph.nodes] == ["sync"]
    assert graph.edges == ()
    assert graph.groups == ()


def test_an_unknown_name_is_not_found(ports: TemplatePorts) -> None:
    with pytest.raises(NotFound):
        template_graph(ports, "nope", 1)


def test_an_unknown_version_is_not_found(ports: TemplatePorts) -> None:
    with pytest.raises(NotFound):
        template_graph(ports, "leaf", 9)


def test_nothing_is_written_while_a_graph_is_read(ports: TemplatePorts) -> None:
    template_graph(ports, "caller", 1)

    assert ports.uow.calls == []  # type: ignore[attr-defined]


def test_text_that_no_longer_validates_is_reported_with_its_errors() -> None:
    """Storage only ever accepts validated text, so this is the case that cannot happen."""
    templates = FakeTemplateVersionRepository(
        [TemplateVersion(name="broken", version=1, yaml=BROKEN, hash="sha-broken")]
    )
    ports = TemplatePorts(uow=FakeUnitOfWork(), templates=templates, clock=FakeClock())

    with pytest.raises(StoredTemplateInvalid) as raised:
        template_graph(ports, "broken", 1)

    assert raised.value.errors
    first = raised.value.errors[0]
    assert (first.line, first.reason) == (BROKEN_LINE, "unknown kind")


def test_the_stored_failure_names_how_many_problems_it_carries() -> None:
    """The message is what a log line reads; the errors are what the router renders."""
    templates = FakeTemplateVersionRepository(
        [TemplateVersion(name="broken", version=1, yaml=BROKEN, hash="sha-broken")]
    )
    ports = TemplatePorts(uow=FakeUnitOfWork(), templates=templates, clock=FakeClock())

    with pytest.raises(StoredTemplateInvalid, match="broken@1"):
        template_graph(ports, "broken", 1)
