"""`harness_readiness.start` refuses a name that is not a harness (SPEC CAP-8).

The path parameter of `POST /harnesses/{name}/readiness` is a free string, and until this
suite existed nothing looked at it: an unknown name was carried all the way into
`create_run`, where it became a branch (`readiness/0/2026-09-08`) and a `git ls-remote`
against the fixture remote. When that remote is missing — which is every environment that
has not cloned the readiness fixture — the `GitError` escaped as a 500. Schemathesis found
it on `POST /api/v1/harnesses/0/readiness`.

The check is against `HARNESS_NAMES` and *not* against the `harness` table, because a row
is not what makes a name real here: `start` runs with `skip_harness_check=True` precisely so
a harness with no row, or a row with `enabled` false, can still run the Run that would
enable it (AD-10). `tests/unit/application/test_harness_readiness_start.py` pins that
behaviour with a `FakeHarnessRepository()` holding nothing at all, so a row-existence check
would contradict it. The image installs three harnesses; a fourth name is a typo.

Nothing here needs a Template, a git remote or a plan: the name gate is the first statement
in `start`, so an empty `FakeProjectRepository` is enough to tell "refused for its name"
apart from "refused for the seeding" by the sentence each refusal carries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.harness_readiness import HarnessReadinessPorts, start
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.harness import HARNESS_NAMES
from orchestrator.domain.errors import NotFound
from orchestrator.main import HARNESS_VERSION_SETTINGS
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)
BUDGET = Decimal("5")

#: Every name the fuzzer reached the git call with, plus the shapes a path parameter can
#: take that a harness name never does. `"0"` is schemathesis's own finding.
NOT_HARNESSES = ("0", "not-a-harness", "", "Claude", "claude ", "opencode", "../claude")

#: The exemplar this suite configures readiness with — fixture data, not a product name
#: (Operator decision 2026-09-30: no template name hardcoded in product code). Nothing here
#: plans, so the store holds no version of it either.
READINESS_TEMPLATE = "readiness-exemplar"


def unseeded_ports() -> HarnessReadinessPorts:
    """`readiness_ports`' own wiring over an empty world.

    No Project, no Repository, no harness row and a git port scripted with nothing: if the
    name gate ever stops being the first statement in `start`, a name that gets past it
    lands on one of those and says so in a different sentence.
    """
    preflight = PreflightPorts(
        git=FakeGit(),
        templates=FakeTemplateVersionRepository([]),
        runs=FakeRunRepository(),
        harnesses=FakeHarnessRepository(),
        repositories=FakeRepositoryRepository([]),
        projects=FakeProjectRepository([]),
        bmad_version=fixtures.BMAD_VERSION,
        max_active_runs=2,
        work_dir=Path("/work"),
    )
    return HarnessReadinessPorts(
        create_run=CreateRunPorts(
            preflight=preflight,
            engine=FakeWorkflowEngine(),
            steps=FakeStepRunRepository(),
            uow=FakeUnitOfWork(),
            clock=FakeClock(NOW),
            skip_harness_check=True,
        ),
        budget_usd=BUDGET,
        template_name=READINESS_TEMPLATE,
    )


# ── the refusal ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", NOT_HARNESSES)
def test_refuses_not_found_for_a_name_that_is_not_a_harness(name: str) -> None:
    with pytest.raises(NotFound, match="no harness named"):
        start(unseeded_ports(), name)


def test_the_refusal_names_the_name_it_refused() -> None:
    """A 404 that does not say which name it did not recognise is not actionable."""
    with pytest.raises(NotFound, match="'not-a-harness'"):
        start(unseeded_ports(), "not-a-harness")


def test_the_name_gate_runs_before_anything_reads_the_world() -> None:
    """The whole point: an unknown name must be refused before a git command is issued.

    This is the assertion that stands directly under the 500 — planning called `ls_remote`
    on the fixture remote for a branch named after a name that was never a harness.
    """
    ports = unseeded_ports()
    git = ports.create_run.preflight.git

    with pytest.raises(NotFound):
        start(ports, "0")

    assert git.calls == []  # type: ignore[union-attr]


# ── the three real names are not caught by it ─────────────────────────────────────────────


@pytest.mark.parametrize("name", HARNESS_NAMES)
def test_every_installed_harness_gets_past_the_name_gate(name: str) -> None:
    """Refused for the *seeding*, in the seeding's own words — not for its name.

    `unseeded_ports` holds no readiness Project, so a name that passes the gate lands on
    that refusal next. Distinguishing the two sentences is what proves the gate let it by.
    """
    with pytest.raises(NotFound, match="Project"):
        start(unseeded_ports(), name)


def test_the_installed_names_are_the_three_the_image_installs() -> None:
    assert HARNESS_NAMES == ("claude", "codex", "local")


def test_the_names_are_the_ones_the_seed_pins_versions_for() -> None:
    """`main.seed_harness_table` upserts one row per name and reads a version pin for each.

    Two statements of one list drift the moment nothing compares them — the same reason
    `test_harness_env_contract.py` parses the bash arrays rather than trusting the Python.
    A name here with no version setting would seed a harness the image never installed.
    """
    assert tuple(HARNESS_VERSION_SETTINGS) == HARNESS_NAMES
