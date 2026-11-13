"""Opengrep SARIF, rule pack hash and step entries of the analyses read (epic 6 story 4)."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.use_cases.run_analyses import run_analyses
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates.test_step_metrics import HEAD, STEPS, entry
from tests.unit.application.test_run_analyses import World
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository


def _opengrep_world(pack: str | None = "abcdef1234"):  # type: ignore[no-untyped-def]
    world = World()
    found = world.analysis(".")
    record = {"tool": "opengrep", "version": "1.0", "rule_pack_hash": pack}
    found = found.model_copy(update={"toolset": (*found.toolset, record)})
    world.analyses.rows[:] = [found]
    world.version(1, found)
    return world, found


def test_opengrep_sarif_is_listed_and_the_rule_pack_hash_is_read() -> None:
    world, found = _opengrep_world()
    world.sarif(found, "opengrep")

    [item] = run_analyses(world.ports, world.run.id, 1).items

    assert item.sarif_tools == ["opengrep"]
    assert item.rule_pack_hash == "abcdef1234"


def test_no_opengrep_record_holds_no_hash() -> None:
    world = World()
    found = world.analysis(".")
    world.version(1, found)

    [item] = run_analyses(world.ports, world.run.id, 1).items

    assert item.rule_pack_hash is None


def test_step_entries_come_from_the_runs_template_version() -> None:
    world, _ = _opengrep_world()
    runs = FakeRunRepository()
    runs.add(world.run.model_copy(update={"template_name": "bench-v1", "template_version": 1}))
    version = TemplateVersion(name="bench-v1", version=1, yaml=HEAD + entry() + STEPS, hash="h")
    ports = replace(world.ports, runs=runs, templates=FakeTemplateVersionRepository([version]))

    result = run_analyses(ports, world.run.id, 1)

    assert [e.id for e in result.step_entries] == ["step.bench-v1.heldout_tests"]
    assert result.step_entries[0].label == "held-out tests"


def test_step_entries_belong_to_the_template_even_without_a_version() -> None:
    world = World()
    runs = FakeRunRepository()
    runs.add(world.run.model_copy(update={"template_name": "bench-v1", "template_version": 1}))
    version = TemplateVersion(name="bench-v1", version=1, yaml=HEAD + entry() + STEPS, hash="h")
    ports = replace(world.ports, runs=runs, templates=FakeTemplateVersionRepository([version]))

    result = run_analyses(ports, world.run.id, None)

    assert result.version is None
    assert len(result.step_entries) == 1


def test_without_a_template_repository_there_are_no_step_entries() -> None:
    world, _ = _opengrep_world()

    assert run_analyses(world.ports, world.run.id, 1).step_entries == ()
