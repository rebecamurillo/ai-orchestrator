"""One id generator for every entity (Consistency Conventions — Ids & keys).

UUIDv7 is chosen because its leading 48 bits are a millisecond timestamp: ids sort by
creation time, so a b-tree primary key stays append-only instead of scattering writes the
way UUIDv4 does. That property is only real if every caller goes through `new_id()`, so
the version and the ordering are asserted here rather than trusted.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.ids import new_id

UUID_VERSION_7 = 7
SAMPLE = 200


def test_new_id_returns_a_uuid() -> None:
    assert isinstance(new_id(), UUID)


def test_new_id_is_version_7() -> None:
    assert new_id().version == UUID_VERSION_7


def test_ids_are_unique() -> None:
    ids = [new_id() for _ in range(SAMPLE)]

    assert len(set(ids)) == SAMPLE


def test_ids_increase_so_the_primary_key_stays_append_only() -> None:
    """UUIDv7 sorts by creation time; a generator that lost that would sort randomly."""
    ids = [new_id() for _ in range(SAMPLE)]

    assert ids == sorted(ids)
