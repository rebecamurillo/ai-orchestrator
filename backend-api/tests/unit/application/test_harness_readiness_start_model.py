"""`harness_readiness.start` binds a model of its own (SPEC CAP-8, AD-10).

Without one, `Run.inputs["model"]` is `None`, `{{model}}` in the Template's `build` step
resolves to the empty string, and the harness picks its own built-in default — which for
Claude Code is a model the operator's Gateway serves no route for. So the readiness Run,
whose whole job is to prove session capture, tracing and spend attribution on a trivial
story, fails on the first agent step for a reason that is not about readiness at all.

The wiring under test is `HarnessReadinessPorts.models`, one model per harness, which
`api/providers.py` fills from `Settings.readiness_models`
(`tests/unit/test_readiness_models_setting.py` covers the contract that feeds it). This
module drives `start` itself: which model each harness ends up bound to, and what happens
when the mapping has no entry for the harness being probed.

`World` and `unseeded_ports` are imported from the two suites that already build `start`'s
world the way `readiness_ports` does, the precedent
`tests/unit/application/test_answer_signal_scope.py` sets for reusing a sibling suite's
fixtures rather than growing a second copy that can drift.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from orchestrator.application.use_cases.create_run import CreateRunResult
from orchestrator.application.use_cases.harness_readiness import (
    DEFAULT_READINESS_MODELS,
    HarnessReadinessPorts,
    start,
)
from orchestrator.domain.entities.harness import HARNESS_NAMES
from orchestrator.domain.errors import Conflict
from tests.unit.application.test_harness_readiness_start import World
from tests.unit.application.test_harness_readiness_start_unknown_name import unseeded_ports

#: What the shipped contract binds — the same three the setting suite pins.
EXPECTED = {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4", "local": "local-coder"}


def _start(ports: HarnessReadinessPorts, world: World, name: str) -> CreateRunResult:
    with world.uow:
        return start(ports, name)


# ── each harness binds its own model ─────────────────────────────────────────


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_each_harness_binds_the_model_the_mapping_gives_it(name: str) -> None:
    world = World()
    ports = replace(world.ports, models=dict(EXPECTED))

    result = _start(ports, world, name)

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.inputs["model"] == EXPECTED[name]


def test_the_bound_model_is_the_one_configured_not_a_constant() -> None:
    """A hardcoded model would pass the parametrised case above; this one moves with the
    mapping, which is what makes `READINESS_MODELS` a setting rather than a comment."""
    world = World()
    ports = replace(world.ports, models={"claude": "some-other-route"})

    result = _start(ports, world, "claude")

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.inputs["model"] == "some-other-route"


def test_the_default_mapping_binds_without_the_composition_root() -> None:
    """`World` builds the ports without naming `models` at all, as every suite written
    before this field did; the default keeps those bindings real rather than `None`."""
    world = World()

    result = _start(world.ports, world, "claude")

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.inputs["model"] == DEFAULT_READINESS_MODELS["claude"]


# ── a harness with no entry ──────────────────────────────────────────────────


def test_a_harness_with_no_entry_is_refused_and_named() -> None:
    world = World()
    ports = replace(world.ports, models={"claude": "claude-sonnet-4-6"})

    with pytest.raises(Conflict, match="codex"):
        _start(ports, world, "codex")


def test_an_entry_naming_no_model_is_refused_like_a_missing_one() -> None:
    """An empty value is how a half-filled `.env` line arrives; binding `""` is the defect."""
    world = World()
    ports = replace(world.ports, models={"codex": ""})

    with pytest.raises(Conflict, match="codex"):
        _start(ports, world, "codex")


def test_the_refusal_creates_no_run() -> None:
    """The refusal is the whole point: a Run that exists with no model is what this fixes."""
    world = World()
    ports = replace(world.ports, models={})

    with pytest.raises(Conflict):
        _start(ports, world, "claude")

    assert world.runs.runs == {}


def test_the_model_is_checked_before_the_readiness_project_is_looked_up() -> None:
    """Ordering, over a world with no Project, no Repository and a git port scripted with
    nothing: the missing model must be what the operator is told about, not whichever seed
    the empty world runs into first."""
    ports = replace(unseeded_ports(), models={})

    with pytest.raises(Conflict, match="claude"):
        start(ports, "claude")
