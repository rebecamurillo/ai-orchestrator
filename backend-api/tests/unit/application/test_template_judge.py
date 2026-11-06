"""`judge_text` and the six use cases behind it (AD-26, D13): a fault in the text is a result,
a fault of the repository is an error."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.application.templates import model
from orchestrator.application.use_cases import template_judge
from orchestrator.application.use_cases import templates as use_cases
from orchestrator.application.use_cases.template_folder import seed_folder
from orchestrator.application.use_cases.template_judge import _Guarded, judge_text
from orchestrator.application.use_cases.templates import (
    StoredTemplateInvalid,
    TemplatePorts,
    TemplateValidationFailed,
    get_version,
    graph_text,
    save_version,
    template_graph,
    text_hash,
    validate_latest,
    validate_text,
)
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.template_folders import FakeTemplateFolders, file, ready
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AT = datetime(2026, 11, 6, tzinfo=UTC)
STEP = "steps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
MARKER = "name: marker\nversion: 1\n" + STEP
GOOD = "name: good\nversion: 1\n" + STEP
CALLER = (
    "name: caller\nversion: 1\nsteps:\n  - id: c\n    uses: template\n    with:\n"
    "      name: lib\n      version: 1\n      inputs: {}\n"
)


UNPINNED = CALLER.replace("      version: 1\n", "")


def a_stored(name: str = "lib", yaml: str = GOOD) -> TemplateVersion:
    return TemplateVersion(name=name, version=1, yaml=yaml, hash=text_hash(yaml), created_at=AT)


def ports(templates: FakeTemplateVersionRepository | None = None) -> TemplatePorts:
    return TemplatePorts(
        uow=FakeUnitOfWork(),
        templates=templates or FakeTemplateVersionRepository(),
        clock=FakeClock(AT),
        folders=FakeTemplateFolders(),
    )


class _RaisingGet(FakeTemplateVersionRepository):
    def get(self, name: str, version: int) -> TemplateVersion | None:
        raise RuntimeError("get failed")


class _RaisingList(FakeTemplateVersionRepository):
    def list_versions(self, name: str) -> list[int]:
        raise RuntimeError("list failed")


def test_a_repository_error_during_validation_is_raised_not_refused() -> None:
    with pytest.raises(RuntimeError, match="get failed"):
        judge_text(CALLER, _RaisingGet())
    with pytest.raises(RuntimeError, match="list failed"):
        judge_text(UNPINNED, _RaisingList())


def test_the_guard_forwards_and_wraps_every_repository_method() -> None:
    inner = FakeTemplateVersionRepository([a_stored()])
    guarded = _Guarded(inner)

    assert guarded.get("lib", 1) is not None
    guarded.add_version(a_stored("other"), description="d")
    assert guarded.list_versions("other") == [1]
    assert guarded.callers_of("lib", 1) == []
    assert guarded.pinned_by("lib", 1) == 0
    assert guarded.names_with_source("folder") == frozenset()
    assert [s.name for s in guarded.list()] == ["lib", "other"]

    class Broken(FakeTemplateVersionRepository):
        def __getattribute__(self, name: str) -> object:
            if name in {
                "get",
                "add_version",
                "list_versions",
                "callers_of",
                "pinned_by",
                "names_with_source",
                "list",
            }:
                raise RuntimeError(name)
            return super().__getattribute__(name)

    broken = _Guarded(Broken())
    calls = (
        lambda: broken.get("a", 1),
        lambda: broken.add_version(a_stored(), description=None),
        lambda: broken.list_versions("a"),
        lambda: broken.callers_of("a", 1),
        lambda: broken.pinned_by("a", 1),
        lambda: broken.names_with_source("x"),
        broken.list,
    )
    for call in calls:
        with pytest.raises(template_judge.PortRaised):
            call()


@pytest.fixture
def exploding(monkeypatch: pytest.MonkeyPatch) -> None:
    real = template_judge.validate

    def validate(text: str, *, templates: object) -> object:
        if "name: marker" in text:
            raise KeyError("boom")
        return real(text, templates=templates)  # type: ignore[arg-type]

    monkeypatch.setattr(template_judge, "validate", validate)


def test_a_text_that_makes_validate_raise_is_one_invalid_template(exploding: None) -> None:
    result = judge_text(MARKER, FakeTemplateVersionRepository())

    assert [(e.line, e.reason) for e in result.errors] == [(1, model.INVALID_TEMPLATE)]
    assert result.template is None


def test_the_folder_pass_refuses_the_marker_and_stores_the_rest(exploding: None) -> None:
    templates = FakeTemplateVersionRepository()
    folders = FakeTemplateFolders(folder=ready(file("good", GOOD), file("marker", MARKER)))

    fresh = TemplatePorts(
        uow=FakeUnitOfWork(), templates=templates, clock=FakeClock(AT), folders=folders
    )
    outcome = seed_folder(fresh, folders.folder)

    assert [e.name for e in outcome.stored] == ["good"]
    assert [r.file for r in outcome.refused] == ["marker.yaml"]
    assert outcome.refused[0].errors[0].reason == model.INVALID_TEMPLATE


def test_no_web_use_case_raises_anything_else_for_such_a_text(exploding: None) -> None:
    held = FakeTemplateVersionRepository([a_stored("marker", MARKER)])
    fresh = ports(held)

    assert [e.reason for e in validate_text(fresh, MARKER).errors] == [model.INVALID_TEMPLATE]
    with pytest.raises(TemplateValidationFailed):
        save_version(fresh, "marker", MARKER)
    with pytest.raises(TemplateValidationFailed):
        graph_text(fresh, MARKER)
    assert [e.reason for e in validate_latest(fresh, "marker").errors] == [model.INVALID_TEMPLATE]
    assert get_version(fresh, "marker", 1).inputs == ()
    with pytest.raises(StoredTemplateInvalid):
        template_graph(fresh, "marker", 1)


def test_the_use_case_module_still_exposes_the_judge() -> None:
    assert use_cases.judge_text is judge_text
