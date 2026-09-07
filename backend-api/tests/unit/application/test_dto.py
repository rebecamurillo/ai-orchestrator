"""The snapshots a Run is planned from, and the defaults they carry.

`plan_run` is pure (AD-7), so it takes values rather than entities it could re-read: a
`ProjectSnapshot` and a `RepositorySnapshot` are what the Project and Repository said at the
moment the Run was created, and nothing later re-resolves them. What is asserted here is
that they are frozen, that the three optional commands default to "there is none" rather
than to an empty string a substitution could not tell apart from a command, and that
`RunInputs.values` is per-instance so two Runs never share one mapping.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from orchestrator.application.dto import (
    DEFAULT_HARNESS,
    ProjectSnapshot,
    RepositorySnapshot,
    RunInputs,
)

PROJECT_ID = UUID("01960000-0000-7000-8000-000000000001")
REPOSITORY_ID = UUID("01960000-0000-7000-8000-000000000002")


def project() -> ProjectSnapshot:
    return ProjectSnapshot(id=PROJECT_ID, name="My Project", slug="my-project")


def repository(**overrides: object) -> RepositorySnapshot:
    return RepositorySnapshot(
        id=REPOSITORY_ID,
        slug="my-repo",
        url="https://github.com/org/my-repo.git",
        default_branch="main",
        **overrides,  # type: ignore[arg-type]
    )


def test_a_project_snapshot_carries_the_three_fields_a_template_can_name() -> None:
    snapshot = project()

    assert (snapshot.id, snapshot.name, snapshot.slug) == (PROJECT_ID, "My Project", "my-project")


def test_a_project_snapshot_is_frozen() -> None:
    with pytest.raises(ValidationError):
        project().name = "other"  # type: ignore[misc]


def test_a_repository_snapshot_defaults_every_optional_command_to_none() -> None:
    """`None` is "the Repository states none"; `""` would be a command that runs nothing."""
    snapshot = repository()

    assert snapshot.install_command is None
    assert snapshot.quality_gate_command is None
    assert snapshot.unit_test_command is None
    assert snapshot.test_globs == ()


def test_a_repository_snapshot_keeps_the_commands_it_was_given() -> None:
    snapshot = repository(quality_gate_command="make check", test_globs=("tests/**",))

    assert snapshot.quality_gate_command == "make check"
    assert snapshot.test_globs == ("tests/**",)


def test_a_repository_snapshot_is_frozen() -> None:
    with pytest.raises(ValidationError):
        repository().url = "other"  # type: ignore[misc]


def test_run_inputs_default_to_the_default_harness_no_model_and_no_re_review() -> None:
    run_inputs = RunInputs(project=project(), repository=repository(), base_branch="main")

    assert run_inputs.harness == DEFAULT_HARNESS
    assert run_inputs.model is None
    assert run_inputs.re_review_done is False
    assert run_inputs.values == {}


def test_run_inputs_carry_the_templates_own_declared_inputs() -> None:
    run_inputs = RunInputs(
        project=project(),
        repository=repository(),
        base_branch="main",
        values={"branch": "feat/x", "spec_folder": "docs/epic-1"},
    )

    assert run_inputs.values["spec_folder"] == "docs/epic-1"


def test_two_run_inputs_never_share_one_values_mapping() -> None:
    """A default built once would be a mapping every Run in the process wrote into."""
    first = RunInputs(project=project(), repository=repository(), base_branch="main")
    second = RunInputs(project=project(), repository=repository(), base_branch="main")

    assert first.values is not second.values


def test_run_inputs_are_frozen() -> None:
    run_inputs = RunInputs(project=project(), repository=repository(), base_branch="main")

    with pytest.raises(ValidationError):
        run_inputs.base_branch = "other"  # type: ignore[misc]
