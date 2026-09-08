"""`sync_pins` and `seed_readiness_project` (SPEC CAP-8): the two start-up bootstraps
`main.py::seed_harness_table` now carries."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.use_cases.harness_readiness import (
    READINESS_BASE_BRANCH,
    READINESS_REPOSITORY_SLUG,
)
from orchestrator.application.use_cases.harness_readiness_seed import (
    _repository,
    seed_readiness_project,
    sync_pins,
)
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)
WORK_DIR = Path("/work")
BMAD_VERSION = "6.11.0"


def harness_ports(harnesses: list[Harness]) -> tuple[HarnessPorts, FakeUnitOfWork]:
    uow = FakeUnitOfWork()
    ports = HarnessPorts(uow=uow, harnesses=FakeHarnessRepository(harnesses))
    return ports, uow


# ── sync_pins ─────────────────────────────────────────────────────────────────────────────


def test_disables_a_harness_whose_pin_changed_and_records_old_to_new() -> None:
    ports, uow = harness_ports([Harness(name="claude", enabled=True, version_pin="2.1.258")])

    with uow:
        changed = sync_pins(ports, {"claude": "2.1.260"})

    assert [h.name for h in changed] == ["claude"]
    stored = ports.harnesses.get("claude")
    assert stored is not None
    assert stored.enabled is False
    assert stored.failing_check == "version pin changed: 2.1.258 → 2.1.260"
    assert stored.version_pin == "2.1.260"
    assert uow.committed is True


def test_leaves_a_harness_whose_pin_did_not_change() -> None:
    ports, uow = harness_ports([Harness(name="claude", enabled=True, version_pin="2.1.258")])

    with uow:
        changed = sync_pins(ports, {"claude": "2.1.258"})

    assert changed == []
    assert ports.harnesses.get("claude") == Harness(
        name="claude", enabled=True, version_pin="2.1.258"
    )
    assert uow.committed is False


def test_leaves_a_harness_pins_does_not_name() -> None:
    ports, uow = harness_ports([Harness(name="local", enabled=False, version_pin="1.18.26")])

    with uow:
        changed = sync_pins(ports, {"claude": "2.1.260"})

    assert changed == []
    assert uow.committed is False


def test_an_empty_harness_table_changes_nothing() -> None:
    ports, uow = harness_ports([])

    with uow:
        changed = sync_pins(ports, {"claude": "2.1.260"})

    assert changed == []
    assert uow.committed is False


# ── seed_readiness_project ───────────────────────────────────────────────────────────────


def project_ports(*, with_repositories: bool = True) -> tuple[ProjectPorts, FakeUnitOfWork]:
    uow = FakeUnitOfWork()
    ports = ProjectPorts(
        uow=uow,
        projects=FakeProjectRepository(),
        crypto=FakeCrypto(),
        clock=FakeClock(NOW),
        repositories=FakeRepositoryRepository() if with_repositories else None,
        git=None,
    )
    return ports, uow


def test_seeds_the_readiness_project_and_repository_once() -> None:
    ports, uow = project_ports()

    with uow:
        project = seed_readiness_project(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)

    assert project.slug == READINESS_PROJECT_SLUG
    assert project.builtin is True
    assert ports.projects.get_by_slug(READINESS_PROJECT_SLUG) is not None
    assert ports.repositories is not None
    stored_repos = ports.repositories.list_by_project(project.id)
    assert [r.slug for r in stored_repos] == [READINESS_REPOSITORY_SLUG]
    assert stored_repos[0].default_branch == READINESS_BASE_BRANCH
    assert stored_repos[0].url == f"file://{WORK_DIR}/readiness/origin.git"
    assert uow.committed is True


def test_seeding_twice_creates_the_project_and_repository_only_once() -> None:
    ports, uow = project_ports()
    with uow:
        first = seed_readiness_project(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)

    uow2 = FakeUnitOfWork()
    ports2 = ProjectPorts(
        uow=uow2,
        projects=ports.projects,
        crypto=FakeCrypto(),
        clock=FakeClock(NOW),
        repositories=ports.repositories,
        git=None,
    )
    with uow2:
        second = seed_readiness_project(ports2, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)

    assert second.id == first.id
    assert ports.repositories is not None
    assert len(ports.repositories.list_by_project(first.id)) == 1


def test_repository_skips_a_non_matching_slug_before_finding_the_readiness_one() -> None:
    project_id = new_id()
    other = Repository(
        id=new_id(),
        project_id=project_id,
        slug="something-else",
        url="https://example.test/other.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="other",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )
    matching = other.model_copy(update={"id": new_id(), "slug": READINESS_REPOSITORY_SLUG})
    repositories = FakeRepositoryRepository([other, matching])

    found = _repository(repositories, project_id)

    assert found is not None
    assert found.id == matching.id


def test_repository_answers_none_when_nothing_under_the_project_matches() -> None:
    project_id = new_id()
    other = Repository(
        id=new_id(),
        project_id=project_id,
        slug="something-else",
        url="https://example.test/other.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="other",
        clone_check=CloneCheck.pending(),
        created_at=NOW,
        updated_at=NOW,
    )
    repositories = FakeRepositoryRepository([other])

    assert _repository(repositories, project_id) is None


def test_degrades_when_no_repositories_port_is_wired() -> None:
    ports, uow = project_ports(with_repositories=False)

    with uow:
        project = seed_readiness_project(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)

    assert project.slug == READINESS_PROJECT_SLUG
    assert ports.repositories is None
