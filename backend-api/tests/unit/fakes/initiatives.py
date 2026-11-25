"""In-memory fakes for the initiative ports (AD-36). They mirror the two unique indexes."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance


class FakeInitiativeRepository:
    """Stored initiatives in a dictionary, keyed by id."""

    def __init__(self, initiatives: list[Initiative] | None = None) -> None:
        self.initiatives: dict[UUID, Initiative] = {}
        self.calls: list[tuple[str, object]] = []
        for initiative in initiatives or []:
            self.add(initiative)

    def add(self, initiative: Initiative) -> None:
        self.calls.append(("add", initiative.id))
        if initiative.id in self.initiatives:
            raise ValueError(f"an initiative with id {initiative.id} is already stored")
        self._refuse_second_open_slug(initiative)
        self.initiatives[initiative.id] = initiative

    def get(self, initiative_id: UUID) -> Initiative | None:
        self.calls.append(("get", initiative_id))
        return self.initiatives.get(initiative_id)

    def get_for_update(self, initiative_id: UUID) -> Initiative | None:
        self.calls.append(("get_for_update", initiative_id))
        return self.initiatives.get(initiative_id)

    def update(self, initiative: Initiative) -> None:
        self.calls.append(("update", initiative.id))
        if initiative.id not in self.initiatives:
            raise ValueError(f"no initiative with id {initiative.id} is stored")
        self._refuse_second_open_slug(initiative)
        self.initiatives[initiative.id] = initiative

    def list(self, *, project_id: UUID | None = None) -> list[Initiative]:
        self.calls.append(("list", project_id))
        return sorted(
            (i for i in self.initiatives.values() if project_id in (None, i.project_id)),
            key=lambda i: (i.created_at, i.id),
            reverse=True,
        )

    def get_open_by_slug(self, repository_id: UUID, slug: str) -> Initiative | None:
        self.calls.append(("get_open_by_slug", (repository_id, slug)))
        return next(
            (
                i
                for i in self.initiatives.values()
                if i.repository_id == repository_id and i.slug == slug and i.cancelled_at is None
            ),
            None,
        )

    def list_by_slug(self, repository_id: UUID, slug: str) -> list[Initiative]:
        self.calls.append(("list_by_slug", (repository_id, slug)))
        return self._in_creation_order(
            i
            for i in self.initiatives.values()
            if i.repository_id == repository_id and i.slug == slug
        )

    def list_open_for_package(self, project_id: UUID, package_name: str) -> list[Initiative]:
        self.calls.append(("list_open_for_package", (project_id, package_name)))
        return self._in_creation_order(
            i
            for i in self.initiatives.values()
            if i.project_id == project_id and i.is_open and i.sequence.package == package_name
        )

    def _refuse_second_open_slug(self, initiative: Initiative) -> None:
        if initiative.cancelled_at is not None:
            return
        for stored in self.initiatives.values():
            if (
                stored.id != initiative.id
                and stored.cancelled_at is None
                and stored.repository_id == initiative.repository_id
                and stored.slug == initiative.slug
            ):
                raise ValueError(f"an open initiative {initiative.slug!r} already exists")

    @staticmethod
    def _in_creation_order(initiatives: Iterable[Initiative]) -> list[Initiative]:
        return sorted(initiatives, key=lambda i: (i.created_at, i.id))


class FakeInitiativeAdvanceRepository:
    """Stored advances, unique on `(initiative_id, round, position)`."""

    def __init__(self) -> None:
        self.advances: list[InitiativeAdvance] = []
        self.calls: list[tuple[str, object]] = []

    def add(self, advance: InitiativeAdvance) -> None:
        self.calls.append(("add", advance.id))
        for stored in self.advances:
            if stored.id == advance.id or (stored.initiative_id, stored.round, stored.position) == (
                advance.initiative_id,
                advance.round,
                advance.position,
            ):
                raise ValueError("an advance with this id or key is already stored")
        self.advances.append(advance)

    def list_for_initiative(self, initiative_id: UUID) -> list[InitiativeAdvance]:
        self.calls.append(("list_for_initiative", initiative_id))
        return sorted(
            (a for a in self.advances if a.initiative_id == initiative_id),
            key=lambda a: (a.round, a.position),
        )

    def list_unconsumed(self) -> list[InitiativeAdvance]:
        self.calls.append(("list_unconsumed", None))
        return sorted(
            (a for a in self.advances if a.consumed_at is None),
            key=lambda a: (a.round, a.position, a.id),
        )
