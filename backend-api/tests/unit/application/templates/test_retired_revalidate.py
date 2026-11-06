"""Nothing that validated before the nested-loop amendment fails now (story 2, 2026-11-06).

The nine files under `fixtures/retired/` are owned copies of templates that left the shipped
set; no test pins their content, they only have to keep validating once seeded.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: The nine templates that leave the shipped set in story 7.
RETIRED_COUNT = 9
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_every_retired_file_revalidates_once_seeded() -> None:
    files = [
        (path.stem, path.read_text()) for path in sorted((FIXTURES / "retired").glob("*.yaml"))
    ]
    uow = FakeUnitOfWork()
    uow.__enter__()
    repo = FakeTemplateVersionRepository()
    ports = TemplatePorts(uow=uow, templates=repo, clock=FakeClock())

    seed_shipped(ports, files)

    assert len(files) == RETIRED_COUNT
    for name, _ in files:
        stored = repo.get(name, 1)
        assert stored is not None, name
        assert validate(stored.yaml, templates=repo).errors == (), name


def test_every_owned_exemplar_validates() -> None:
    repo = fixtures.repository_of_versions()

    for path in sorted((FIXTURES / "exemplars").glob("*.yaml")):
        assert validate(path.read_text(), templates=repo).errors == (), path.name
