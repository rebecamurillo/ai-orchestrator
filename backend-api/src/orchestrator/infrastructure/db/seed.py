"""The harness table's start-up seed, and the built-in `readiness` Project beside it (AD-10).

Moved out of `main.py` for the reason `infrastructure/harness/registry.py` was, and stated
in that module's own docstring: the composition root sits at its 400-line cap, and this is
one subject of its own — the rows that must exist in the database *before* the process
serves, written once per start against an engine this function opens and disposes itself.
`main.py` re-exports both public names, so `orchestrator.main.seed_harness_table` and
`orchestrator.main.HARNESS_VERSION_SETTINGS` stay reachable exactly where every caller and
every test already reaches them, and `run_migrations` still names one collaborator.

Adapters *are* instantiated here, which is the composition root's job — that is why this
module is the seam and not a use case: the use cases it calls (`sync_pins`,
`seed_harnesses`, `seed_test_harness`, `seed_readiness_project`) take ports and know nothing
about a session, and everything below assembles those ports and nothing else.
"""

from __future__ import annotations

from orchestrator.application.use_cases.harness_readiness_seed import (
    seed_readiness_project,
    sync_pins,
)
from orchestrator.application.use_cases.harnesses import (
    HarnessPorts,
    seed_harnesses,
    seed_test_harness,
)
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.harness import Harness
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.crypto import FernetCrypto
from orchestrator.infrastructure.db import (
    SQLAlchemyHarnessRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyUnitOfWork,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.git import SubprocessGit
from orchestrator.infrastructure.harness.fake import NAME as FAKE_HARNESS_NAME
from orchestrator.infrastructure.settings import Settings

#: The three harness names this image installs (SPEC CAP-3, AD-10), each paired with the
#: `Settings` field that pins its version. `local` is OpenCode — see `.env.example`'s own
#: comment on `LOCAL_MODELS`.
HARNESS_VERSION_SETTINGS: dict[str, str] = {
    "claude": "claude_code_version",
    "codex": "codex_version",
    "local": "opencode_version",
}

#: What the scripted `fake` harness's `version_pin` states (SPEC CAP-1, AR-14). It pins no
#: installed tool — there is none — so the column says what the row *is* rather than naming
#: a version this image does not carry. Deliberately outside `HARNESS_VERSION_SETTINGS`:
#: that table is the names the image installs paired with the `Settings` field pinning each,
#: `fake` has neither, and `sync_pins` must never see it — a harness the pin table does not
#: name is left alone, which is exactly right for one whose version can never change.
FAKE_HARNESS_PIN = "test-mode"


def seed_harness_table(settings: Settings) -> list[Harness]:
    """Idempotent upsert of the three harness names and pinned versions (AD-10), plus the
    readiness bootstrapping this step carries (SPEC CAP-8): `sync_pins` against the *stored*
    version, the upsert, then the built-in `readiness` Project and Repository — still the
    one name `run_migrations` calls, `test_main_templates_seed.py`'s frozen
    three-collaborator test replacing this whole function, not a fourth collaborator to it.

    Under `ORCH_TEST_MODE` the scripted `fake` harness gets a row of its own, enabled
    (SPEC CAP-1). It is written after the upsert rather than inside it because
    `seed_harnesses` may not touch `enabled` — only readiness writes that column, and this
    is the one harness readiness has nothing to say about (`seed_test_harness`'s docstring).
    Without test mode the row is never written at all, so `harness: fake` fails pre-flight's
    own harness line and `create_run` refuses it: the conditional an Operator experiences.
    """
    pins = {name: getattr(settings, field) for name, field in HARNESS_VERSION_SETTINGS.items()}
    engine = create_engine_from(settings)
    try:
        session_factory = create_session_factory(engine)
        with SQLAlchemyUnitOfWork(session_factory) as uow:
            hports = HarnessPorts(uow=uow, harnesses=SQLAlchemyHarnessRepository(uow.session))
            sync_pins(hports, pins)
            seeded = seed_harnesses(hports, pins)
            if settings.orch_test_mode:
                seeded.append(seed_test_harness(hports, FAKE_HARNESS_NAME, FAKE_HARNESS_PIN))
            pports = ProjectPorts(
                uow=uow,
                projects=SQLAlchemyProjectRepository(uow.session),
                crypto=FernetCrypto(settings.orchestrator_secret_key.get_secret_value()),
                clock=SystemClock(),
                repositories=SQLAlchemyRepositoryRepository(uow.session),
                git=SubprocessGit(settings.github_token.get_secret_value()),
            )
            seed_readiness_project(
                pports, work_dir=settings.work_dir, bmad_version=settings.bmad_version
            )
        return seeded
    finally:
        engine.dispose()
