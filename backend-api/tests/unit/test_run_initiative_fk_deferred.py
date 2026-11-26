"""`run.initiative_id` is checked at commit, not at insert.

`create_initiative` stores the spec Run first (`SQLAlchemyRunRepository.add` flushes at once)
and its initiative from `create_run`'s `before_commit`, in the same transaction. An immediate
foreign key refused that order with a 500 on every create; the fakes hold no foreign key, so
only the aio-e2e stack saw it (2026-11-26).
"""

from __future__ import annotations

from orchestrator.infrastructure.db.models.run import RunRow


def test_the_initiative_key_is_deferred_to_the_commit() -> None:
    (fk,) = RunRow.__table__.c.initiative_id.foreign_keys

    assert fk.constraint is not None
    assert (fk.constraint.deferrable, fk.constraint.initially) == (True, "DEFERRED")
