"""Pre-flight reads the setup record's BMAD choice for the skill fix (story 2,
orchestrator-deploy-folder epic 1, 2026-11-11; AC5)."""

from __future__ import annotations

from orchestrator.application.preflight.model import CHECK_INSTALLED_SKILL
from orchestrator.application.use_cases.preflight import preflight_and_plan
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_preflight_plan_git_failure import (
    WORK_DIR,
    PreflightPorts,
    epic_request,
    project,
    repository,
)
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.setup_record import FakeSetupRecord, setup_run
from tests.unit.fakes.skill_catalog import FakeSkillCatalog

SETUP = "./install.sh setup"
BMAD = "./install.sh bmad install"


def ports(record: FakeSetupRecord | None) -> PreflightPorts:
    return PreflightPorts(
        git=fixtures.epic_git(),
        templates=fixtures.repository_of_versions(),
        runs=FakeRunRepository(),
        harnesses=FakeHarnessRepository(),
        repositories=FakeRepositoryRepository([repository()]),
        projects=FakeProjectRepository([project()]),
        bmad_version=fixtures.BMAD_VERSION,
        max_active_runs=2,
        work_dir=WORK_DIR,
        skill_catalog=FakeSkillCatalog({"claude": frozenset()}),
        setup_record=record,
    )


def fixes(p: PreflightPorts) -> list[str | None]:
    result = preflight_and_plan(p, epic_request()).result
    return [
        line.fix
        for line in result.lines
        if line.check == CHECK_INSTALLED_SKILL and line.status == "fail"
    ]


def removed() -> FakeSetupRecord:
    return FakeSetupRecord(setup_run(bmad={"choice": "removed", "ok": True}))


def test_ac5_a_removed_bmad_points_at_the_bmad_installer() -> None:
    record = removed()

    got = fixes(ports(record))

    assert BMAD in got
    assert record.reads == 1


def test_ac5_an_installed_record_keeps_the_setup_fix() -> None:
    assert BMAD not in fixes(ports(FakeSetupRecord(setup_run())))


def test_ac5_no_record_keeps_the_setup_fix() -> None:
    got = fixes(ports(FakeSetupRecord(None)))

    assert got
    assert set(got) == {SETUP}


def test_ac5_no_port_keeps_the_setup_fix() -> None:
    got = fixes(ports(None))

    assert got
    assert set(got) == {SETUP}
