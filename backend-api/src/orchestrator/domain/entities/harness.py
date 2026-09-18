"""The `harness` table: which coding-agent harnesses this instance may dispatch to (AD-10).

Seeded disabled at start-up with the three names the image installs (SPEC CAP-3); nothing
outside `application/use_cases/harness_readiness.py` (SPEC CAP-8) writes `enabled`,
`last_readiness_at`, `failing_check`, `last_readiness_run_id` or `lines`. Pre-flight's
harness line (4.3) reads `enabled` and nothing else here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

#: The three harnesses the image installs, and the whole of what `name` may be.
#:
#: A *row* is not what makes a name real: `harness_readiness.start` runs with
#: `skip_harness_check=True` so a harness with no row, or a row with `enabled` false, can
#: still run the Run that would enable it (AD-10). This tuple is what a name is checked
#: against instead — `POST /harnesses/{name}/readiness` takes a free string, and without it
#: a typo became a branch and a `git ls-remote` against the fixture remote.
#:
#: `main.HARNESS_VERSION_SETTINGS` names the same three, one version pin each, and
#: `tests/unit/application/test_harness_readiness_start_unknown_name.py` compares the two.
HARNESS_NAMES: tuple[str, ...] = ("claude", "codex", "local")

#: The shape of a harness name, as the API declares it on every parameter that carries one.
#:
#: Wider than `HARNESS_NAMES` on purpose: the `fake` harness `ORCH_TEST_MODE` seeds
#: (`infrastructure/harness/fake/adapter.py`) is a row with a real name outside that tuple, so
#: reading and filtering by name stay open to any well-formed one. What this refuses is a
#: value no name can be — every name in this system is a lowercase slug, and a name is
#: compared against a Postgres text column (`attempt.harness`, `harness.name`), which cannot
#: hold a NUL byte. Without the shape such a value reached psycopg as a `DataError` and left a
#: 500 where the caller had asked for something that could match nothing (schemathesis, on
#: `GET /steps?harness=` and `GET /harnesses/{name}/readiness`, 2026-09-18).
#:
#: Anchored at both ends because FastAPI matches a declared pattern unanchored.
#: `tests/unit/test_harness_name_pattern.py` pins the shape; the two router `*_shape.py`
#: modules pin the parameters that declare it.
HARNESS_NAME_PATTERN = r"^[a-z][a-z0-9-]{0,31}$"


class EvaluationLine(BaseModel):
    """One line `evaluate` (SPEC CAP-8) produced: one named check, and whether it passed."""

    model_config = ConfigDict(frozen=True)

    check: str
    ok: bool
    text: str


class Harness(BaseModel):
    """One harness this instance knows how to dispatch to, as it is stored."""

    model_config = ConfigDict(frozen=True)

    #: `claude`, `codex` or `local` — the three names the image installs. The primary key.
    name: str
    #: Whether a readiness run has passed. `False` until Epic 5 writes otherwise.
    enabled: bool = False
    #: When the last readiness run finished, successful or not. `None` until one has.
    last_readiness_at: datetime | None = None
    #: What the last readiness run failed on, or `None` when it passed or never ran.
    failing_check: str | None = None
    #: The version this instance's image pins for the harness (AD-16), read from Settings.
    version_pin: str
    #: The Run `evaluate` last wrote from, or `None` before one has.
    last_readiness_run_id: UUID | None = None
    #: Every line the last evaluation produced, in the order `evaluate` checked them.
    lines: tuple[EvaluationLine, ...] = ()
