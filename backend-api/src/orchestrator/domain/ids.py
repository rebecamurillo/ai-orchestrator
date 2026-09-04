"""The one id generator (Consistency Conventions — Ids & keys).

Every entity's primary key is a UUIDv7. Its leading 48 bits are a millisecond timestamp,
so ids sort by creation time and the primary-key index stays append-only; UUIDv4 would
scatter every insert across the b-tree. Nothing outside this module calls `uuid`.
"""

from __future__ import annotations

from uuid import UUID, uuid7


def new_id() -> UUID:
    """Return a fresh UUIDv7 — time-ordered, unique, and safe to expose in the API."""
    return uuid7()
