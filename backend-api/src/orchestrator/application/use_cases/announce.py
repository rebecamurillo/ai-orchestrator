"""Telling the outside world a Run needs the Operator or has ended.

Called from `writers.set_run`, the one place a Run's status is written, so a transition is
announced once however it was reached (`apply_step_result`, `signal_run`, the dependency
resolver). Nothing here decides a status or does I/O: the `Notifier` port delivers, and
delivery is best-effort — it never reaches back into the transition.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.notifier import NOTIFIED_STATUSES, Notifier, RunNotification
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    ProjectRepository,
    RepositoryRepository,
)

#: What the event names a Project or Repository that no longer resolves.
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Announcer:
    """The `Notifier` plus the reads that turn a Run row into something a person can read."""

    notifier: Notifier
    projects: ProjectRepository
    repositories: RepositoryRepository
    attempts: AttemptRepository
    clock: Clock

    def transition(self, before: Run, after: Run, reason: str | None = None) -> None:
        """Announce `before → after` when it enters one of `NOTIFIED_STATUSES`."""
        if after.status == before.status or after.status not in NOTIFIED_STATUSES:
            return
        project = self.projects.get(after.project_id)
        repository = self.repositories.get(after.repository_id)
        attempt = self.attempts.latest_for_run(after.id)
        self.notifier.notify(
            RunNotification(
                run_id=after.id,
                project=project.name if project is not None else UNKNOWN,
                repository=repository.slug if repository is not None else UNKNOWN,
                template=after.template_name,
                status=after.status,
                park_kind=after.park_kind,
                reason=after.park_reason or reason,
                step_path=after.park_path,
                attempt_id=attempt.id if attempt is not None else None,
                spend_usd=after.spend_usd,
                occurred_at=self.clock.now(),
            )
        )
