"""`create_initiative` (epic 7 story 3, AC1-AC8), on the shared fakes and fixture templates."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from orchestrator.application.use_cases import initiatives as use_cases
from orchestrator.application.use_cases.initiatives import create_initiative
from orchestrator.domain.entities.initiative import InitiativeKey
from orchestrator.domain.entities.repository import CloneCheck
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from tests.unit.application.initiative_world import (
    FOLDER,
    HUB_SHA,
    SHIPPED_LATEST,
    SPEC_VERSION,
    InitiativeWorld,
)
from tests.unit.fakes.remote_branches import FakeRemoteGit

BRANCH = "spec/snake-v3"


def create(world: InitiativeWorld, **overrides: Any) -> Any:
    values: dict[str, Any] = {"name": "Snake v3", "first_message": "hello"}
    values.update(overrides)
    with world.uow:
        return create_initiative(world.ports, world.project.id, **values)


def calls(world: InitiativeWorld, name: str) -> list[Any]:
    return [args for call, args in world.git.calls if call == name]


def failing_world() -> InitiativeWorld:
    """A fixture whose pre-flight has a failing line: the hub's clone check failed."""
    world = InitiativeWorld()
    broken = world.hub.model_copy(
        update={
            "clone_check": CloneCheck(
                status="failed", at=world.hub.updated_at, output="no", bmad_version=None
            )
        }
    )
    world.repositories.repositories[broken.id] = broken
    return world


def refuse_create_run(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def refusing(*_: Any, **__: Any) -> None:
        raise error

    monkeypatch.setattr(use_cases, "create_run", refusing)


# ── AC1 / AC2 ────────────────────────────────────────────────────────────────


def test_the_branch_the_sequence_and_the_spec_run_are_stored() -> None:
    world = InitiativeWorld()

    initiative = create(world)

    assert calls(world, "create_remote_branch") == [(world.base_dir, BRANCH, HUB_SHA)]
    stored = world.initiatives.initiatives[initiative.id]
    assert (stored.slug, stored.round, stored.name, stored.first_message) == (
        "snake-v3",
        1,
        "Snake v3",
        "hello",
    )
    spec, build = stored.sequence.workflows
    assert (spec.template, spec.version) == ("acme.spec", SPEC_VERSION)
    assert (build.template, build.version) == ("shipped-build", SHIPPED_LATEST)
    assert stored.sequence.package == "acme"
    assert stored.sequence.sha == world.package.sha
    (run,) = world.runs.runs.values()
    assert (run.initiative_id, run.initiative_round, run.initiative_position) == (
        initiative.id,
        1,
        0,
    )
    assert run.template_version == SPEC_VERSION
    assert world.runs.get_by_initiative_key(
        InitiativeKey(initiative_id=initiative.id, round=1, position=0)
    )
    assert run.inputs["slug"] == "snake-v3"
    assert run.inputs["branch"] == BRANCH
    assert run.inputs["first_turn"] == "hello"
    assert run.inputs["initiative_folder"] == FOLDER
    assert run.inputs["harness"] == "claude"
    assert run.inputs["model"] == "sonnet"
    assert str(run.budget_usd) == "7.50"
    assert world.uow.committed is True


def test_a_template_without_first_turn_gets_no_such_input() -> None:
    world = InitiativeWorld(first_turn=False)

    create(world)

    (run,) = world.runs.runs.values()
    assert "first_turn" not in run.inputs
    assert run.inputs["slug"] == "snake-v3"


def test_a_missing_stored_version_is_create_runs_own_refusal() -> None:
    world = InitiativeWorld()
    del world.templates.versions[("acme.spec", SPEC_VERSION)]

    with pytest.raises(Exception) as refusal:
        create(world)

    assert str(refusal.value)
    assert world.initiatives.initiatives == {}
    assert calls(world, "delete_remote_branch") == [(world.base_dir, BRANCH)]


def test_an_unparsable_stored_template_declares_nothing() -> None:
    world = InitiativeWorld()
    stored = world.templates.versions[("acme.spec", SPEC_VERSION)]
    world.templates.versions[("acme.spec", SPEC_VERSION)] = stored.model_copy(
        update={"yaml": "- not: [a mapping"}
    )

    with pytest.raises(Exception):  # noqa: B017 — create_run's own refusal, not asserted
        create(world)

    assert world.initiatives.initiatives == {}


# ── AC3 ──────────────────────────────────────────────────────────────────────


def test_an_open_holder_refuses_and_creates_no_branch() -> None:
    world = InitiativeWorld()
    holder = world.seed(world.initiative(name="Other holder"))

    with pytest.raises(Conflict) as refusal:
        create(world)

    assert str(refusal.value) == (
        f"slug snake-v3 is used by an open initiative: Other holder ({holder.id})"
    )
    assert calls(world, "create_remote_branch") == []


def test_a_cancelled_holder_with_a_cleanup_error_refuses() -> None:
    world = InitiativeWorld()
    world.seed(
        world.initiative(cancelled_at=datetime(2026, 1, 1, tzinfo=UTC), branch_cleanup_error="boom")
    )

    with pytest.raises(Conflict, match="slug snake-v3 waits for its branch cleanup: boom"):
        create(world)

    assert calls(world, "create_remote_branch") == []


def test_a_cancelled_holder_without_an_error_lets_the_create_through() -> None:
    world = InitiativeWorld()
    world.seed(world.initiative(cancelled_at=datetime(2026, 1, 1, tzinfo=UTC)))

    created = create(world)

    assert created.slug == "snake-v3"


# ── AC4 ──────────────────────────────────────────────────────────────────────


def test_no_package_is_a_conflict() -> None:
    world = InitiativeWorld()
    world.packages.packages.clear()

    with pytest.raises(Conflict, match=f"no package installed on project {world.project.name}"):
        create(world)


@pytest.mark.parametrize("field", ["name", "first_message"])
def test_a_blank_field_is_invalid(field: str) -> None:
    world = InitiativeWorld()

    with pytest.raises(Invalid, match=field):
        create(world, **{field: "  "})

    assert world.git.calls == []


def test_an_unknown_project_is_not_found() -> None:
    world = InitiativeWorld()

    with world.uow, pytest.raises(NotFound):
        create_initiative(world.ports, new_id(), name="x", first_message="y")


def test_a_package_whose_hub_is_gone_is_not_found() -> None:
    world = InitiativeWorld()
    world.repositories.repositories.clear()

    with pytest.raises(NotFound):
        create(world)


def test_a_hub_without_its_default_branch_is_a_conflict() -> None:
    world = InitiativeWorld(git=FakeRemoteGit(refs={}))

    with pytest.raises(Conflict, match="branch main is not on the hub"):
        create(world)

    assert calls(world, "create_remote_branch") == []


# ── AC5 / AC6 ────────────────────────────────────────────────────────────────


def test_a_refusing_create_run_rolls_back_and_deletes_the_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = InitiativeWorld()
    refuse_create_run(monkeypatch, Conflict("line failed"))

    with pytest.raises(Conflict) as refusal:
        create(world)

    assert str(refusal.value) == "line failed"
    assert world.initiatives.initiatives == {}
    assert world.runs.runs == {}
    assert world.uow.committed is False
    assert world.uow.rolled_back is True
    names = [call for call, _ in world.git.calls]
    assert names.index("create_remote_branch") < names.index("delete_remote_branch")
    assert calls(world, "delete_remote_branch") == [(world.base_dir, BRANCH)]


def test_a_real_preflight_failure_is_the_same_refusal() -> None:
    world = failing_world()

    with pytest.raises(Conflict) as refusal:
        create(world)

    assert world.initiatives.initiatives == {}
    assert world.runs.runs == {}
    assert world.uow.committed is False
    assert str(refusal.value)


def test_a_failing_delete_adds_its_output_to_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    world = InitiativeWorld(
        git=FakeRemoteGit(
            refs={"main": HUB_SHA},
            delete_remote_branch=[GitError(command="push", exit_code=1, output="x")],
        )
    )
    refuse_create_run(monkeypatch, Conflict("line failed"))

    with pytest.raises(Conflict) as refusal:
        create(world)

    assert str(refusal.value).startswith("line failed")
    assert str(refusal.value).endswith("x")


def test_a_failing_delete_annotates_a_refusal_of_another_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = InitiativeWorld(
        git=FakeRemoteGit(
            refs={"main": HUB_SHA},
            delete_remote_branch=[GitError(command="push", exit_code=1, output="x")],
        )
    )
    refuse_create_run(monkeypatch, RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom") as refusal:
        create(world)

    assert any("x" in note for note in refusal.value.__notes__)


def test_a_branch_already_on_the_hub_refuses_and_touches_nothing() -> None:
    world = InitiativeWorld(git=FakeRemoteGit(refs={"main": HUB_SHA, BRANCH: HUB_SHA}))

    with pytest.raises(Conflict) as refusal:
        create(world)

    assert str(refusal.value) == (
        "branch spec/snake-v3 already exists on the hub; delete it or choose another name"
    )
    assert calls(world, "create_remote_branch") == []
    assert calls(world, "delete_remote_branch") == []
    assert world.initiatives.initiatives == {}


# ── AC7 ──────────────────────────────────────────────────────────────────────


def test_an_existing_base_clone_is_fetched_not_cloned() -> None:
    world = InitiativeWorld(git=FakeRemoteGit(refs={"main": HUB_SHA}, base_exists=[True]))

    create(world)

    names = [call for call, _ in world.git.calls]
    assert "clone_base" not in names
    assert calls(world, "fetch_base")[0] == (world.base_dir, "main")
    assert names.index("fetch_base") < names.index("create_remote_branch")


def test_a_missing_base_clone_is_cloned_before_the_fetch() -> None:
    world = InitiativeWorld()

    create(world)

    names = [call for call, _ in world.git.calls]
    assert names.index("clone_base") < names.index("fetch_base")


# ── AC8 ──────────────────────────────────────────────────────────────────────


def test_a_lost_slug_race_names_the_concurrent_holder_and_deletes_the_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = InitiativeWorld()
    holder = world.seed(world.initiative(name="Winner"))
    original = world.initiatives.get_open_by_slug
    seen: list[int] = []

    def blind_once(repository_id: Any, slug: str) -> Any:
        seen.append(1)
        return None if len(seen) == 1 else original(repository_id, slug)

    monkeypatch.setattr(world.initiatives, "get_open_by_slug", blind_once)

    with pytest.raises(Conflict) as refusal:
        create(world)

    assert (
        str(refusal.value) == f"slug snake-v3 is used by an open initiative: Winner ({holder.id})"
    )
    assert world.uow.committed is False
    assert calls(world, "delete_remote_branch") == [(world.base_dir, BRANCH)]


def test_a_lost_race_whose_holder_vanished_still_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    world = InitiativeWorld()
    world.seed(world.initiative())
    monkeypatch.setattr(world.initiatives, "get_open_by_slug", lambda *_: None)

    with pytest.raises(Conflict, match=r"slug snake-v3 is used by an open initiative$"):
        create(world)


def test_a_lost_race_with_a_failing_delete_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    world = InitiativeWorld(
        git=FakeRemoteGit(
            refs={"main": HUB_SHA},
            delete_remote_branch=[GitError(command="push", exit_code=1, output="denied")],
        )
    )
    world.seed(world.initiative())
    monkeypatch.setattr(world.initiatives, "get_open_by_slug", lambda *_: None)

    with pytest.raises(Conflict, match="was not deleted: denied"):
        create(world)


def test_a_failure_after_the_commit_keeps_the_branch_the_stored_run_needs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    world = InitiativeWorld()

    def refusing(*_: Any, **__: Any) -> None:
        raise RuntimeError("queue down")

    monkeypatch.setattr(world.create_ports.engine, "enqueue", refusing)

    with pytest.raises(RuntimeError, match="queue down"):
        create(world)

    assert len(world.initiatives.initiatives) == 1
    assert calls(world, "delete_remote_branch") == []
