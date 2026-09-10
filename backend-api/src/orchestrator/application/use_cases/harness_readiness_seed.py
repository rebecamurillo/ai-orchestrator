"""`sync_pins` and `seed_readiness_project`: what runs once, at container start (SPEC CAP-8).

Both are called from inside `main.py::seed_harness_table` — not as new, separate
collaborators of `main.py::run_migrations` — because `tests/unit/test_main_templates_seed.
py::test_run_migrations_migrates_then_seeds_and_returns_the_head` closes `run_migrations`'s
own call sequence to exactly three named collaborators (`db_migrations.run_migrations`,
`seed_shipped_templates`, `seed_harness_table`) and names no successor story; a fourth,
unstubbed call inside that test reaches a real database and fails it outright (its own
docstring says so). `seed_harness_table` is one of the three, already replaced wholesale by
that test's own fake, so extending its *body* — call `sync_pins` first, then the existing
upsert, then this module's project seed — changes nothing that test observes.

`sync_pins` runs **before** the existing `seed_harnesses` upsert in that same body, on
purpose: it compares the settings' pin against the *stored* `version_pin` from the last
start, and `seed_harnesses` would otherwise have already overwritten that value by the time
anything looked at it.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from orchestrator.application.use_cases.clone_check import run_clone_checks_for_project
from orchestrator.application.use_cases.harness_readiness import (
    READINESS_BASE_BRANCH,
    READINESS_REPOSITORY_SLUG,
)
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    DEFAULT_TEST_GLOBS,
    CloneCheck,
    Repository,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.repositories import RepositoryRepository

#: Said onto a harness `sync_pins` disables — `"{old} → {new}"` fills the two blanks.
VERSION_PIN_CHANGED = "version pin changed: {old} → {new}"


def sync_pins(ports: HarnessPorts, pins: dict[str, str]) -> list[Harness]:
    """Disable every harness whose stored `version_pin` no longer matches `pins[name]`.

    A harness `pins` does not name is left alone — `seed_harnesses` is what stores a name
    for the first time, not this function. A parked Run keeps whatever harness it already
    routed to (AD-10: `enabled` is read only by `create_run` and pre-flight).
    """
    changed = [
        harness.model_copy(
            update={
                "enabled": False,
                "failing_check": VERSION_PIN_CHANGED.format(old=harness.version_pin, new=pin),
                "version_pin": pin,
            }
        )
        for harness in ports.harnesses.list()
        if (pin := pins.get(harness.name)) is not None and pin != harness.version_pin
    ]
    for harness in changed:
        ports.harnesses.update(harness)
    if changed:
        ports.uow.commit()
    return changed


def seed_readiness_project(ports: ProjectPorts, *, work_dir: Path, bmad_version: str) -> Project:
    """The built-in `readiness` Project and its one Repository, created once and re-checked
    every start-up thereafter (`run_clone_checks_for_project` is idempotent)."""
    project = ports.projects.get_by_slug(READINESS_PROJECT_SLUG)
    if project is None:
        project = _seed_project(ports)
    repositories = ports.repositories
    if repositories is not None and _repository(repositories, project.id) is None:
        _seed_repository(repositories, ports.clock, project.id, work_dir)
        ports.uow.commit()
    run_clone_checks_for_project(ports, project.id, work_dir=work_dir, bmad_version=bmad_version)
    return project


def _repository(repositories: RepositoryRepository, project_id: UUID) -> Repository | None:
    for repository in repositories.list_by_project(project_id):
        if repository.slug == READINESS_REPOSITORY_SLUG:
            return repository
    return None


def _seed_project(ports: ProjectPorts) -> Project:
    now = ports.clock.now()
    project = Project(
        id=new_id(),
        slug=READINESS_PROJECT_SLUG,
        name="Readiness",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=True,
        created_at=now,
        updated_at=now,
    )
    ports.projects.add(project)
    ports.uow.commit()
    return project


def _seed_repository(
    repositories: RepositoryRepository, clock: Clock, project_id: UUID, work_dir: Path
) -> None:
    now = clock.now()
    repository = Repository(
        id=new_id(),
        project_id=project_id,
        slug=READINESS_REPOSITORY_SLUG,
        url=f"file://{work_dir}/readiness/origin.git",
        default_branch=READINESS_BASE_BRANCH,
        install_command="",
        # Readiness proves the harness, not the repository, so the fixture declares no
        # quality gate at all. It used to declare `sh check.sh`, which the fixture's own
        # story is what makes pass — so `epic@1`'s `baseline` row ran it before any agent
        # had touched the tree, failed, and `on_fail: fail` ended the Run. No agent row was
        # ever dispatched and no harness could ever reach `enabled`. `baseline` is right to
        # fail a Run whose repository was already red: that is how the Operator learns the
        # break predates the agent. What was wrong is asking a harness-readiness fixture to
        # be green before the work it exists to do. With no command declared, the planner
        # skips `baseline` and the frame's `verify` as `skipped · no quality_gate_command`
        # (`Repository.verify_skipped`), and readiness proves what it is named for: the
        # harness starts, reaches `done`, records a session id, emits a trace, and its spend
        # is attributable. The quality-gate mechanics stay proven end to end by the
        # `gates-repo` fixture and `tests/unit/test_gates_fixture_uj3.py`.
        quality_gate_command="",
        unit_test_command="",
        test_globs=DEFAULT_TEST_GLOBS,
        package_manager=DEFAULT_PACKAGE_MANAGER,
        clone_check=CloneCheck.pending(),
        created_at=now,
        updated_at=now,
    )
    repositories.add(repository)
