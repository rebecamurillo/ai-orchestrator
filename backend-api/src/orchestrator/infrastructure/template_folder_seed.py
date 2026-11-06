"""The folder pass at start-up: `OPERATOR_TEMPLATES_DIR`, after the shipped set (AD-26).

Lives beside `main.py`, which calls it from `run_migrations`, only to keep that module under
its length limit.
"""

from __future__ import annotations

import structlog

from orchestrator.application.use_cases.template_folder import FolderOutcome, seed_folder
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.errors import Conflict
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.templates_loader import FilesystemTemplateFolders

log = structlog.get_logger(__name__)


def seed_folder_templates(settings: Settings) -> FolderOutcome | None:
    """The folder pass (AD-26): the operator's `OPERATOR_TEMPLATES_DIR`, after the shipped set.

    Nothing runs when the setting is unset. A refused file is a warning and a concurrent save's
    `Conflict` is one warning with nothing committed; neither stops start-up. Any other error
    propagates. Own engine, disposed in a `finally`, as `seed_shipped_templates`.
    """
    if settings.operator_templates_dir is None:
        return None
    folders = FilesystemTemplateFolders(settings.templates_dir, settings.operator_templates_dir)
    folder = folders.operator()
    if folder.state == "missing":
        log.warning("operator templates folder not found", path=folder.path)
        return None
    engine = create_engine_from(settings)
    try:
        session_factory = create_session_factory(engine)
        with SQLAlchemyUnitOfWork(session_factory) as uow:
            ports = TemplatePorts(
                uow=uow,
                templates=SQLAlchemyTemplateVersionRepository(uow.session),
                clock=SystemClock(),
                folders=folders,
            )
            try:
                outcome = seed_folder(ports, folder)
                uow.commit()
            except Conflict as conflict:
                log.warning("operator templates not loaded", reason=str(conflict))
                return None
    finally:
        engine.dispose()
    _log_folder(outcome)
    return outcome


def _log_folder(outcome: FolderOutcome) -> None:
    for entry in outcome.stored:
        log.info(
            f"operator template {entry.name} stored as v{entry.version}",
            file=entry.file,
            overrides_shipped=entry.overrides_shipped,
        )
    for refusal in outcome.refused:
        log.warning(
            f"operator template file {refusal.file} refused",
            errors=[f"line {e.line}: {e.reason}" for e in refusal.errors],
        )
    for gone in outcome.not_in_folder:
        log.info(
            f"operator template {gone.name} has no file in the folder; its versions are kept",
            overrides_shipped=gone.overrides_shipped,
        )
