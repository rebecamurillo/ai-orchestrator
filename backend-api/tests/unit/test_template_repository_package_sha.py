"""The template adapter carries `package_sha` and reads by it (story 3 of epic 6)."""

from __future__ import annotations

from orchestrator.infrastructure.db.repositories.templates import to_entity
from tests.unit.test_template_repository_adapter import (
    RecordingSession,
    a_row,
    a_version,
    repository,
)

SHA = "a" * 40


def test_add_version_carries_package_sha() -> None:
    session = RecordingSession()

    repository(session).add_version(a_version(source="package", package_sha=SHA), description=None)

    assert session.added[-1].package_sha == SHA


def test_to_entity_reads_package_sha() -> None:
    row = a_row(a_version())
    row.package_sha = SHA

    assert to_entity(row).package_sha == SHA


def test_get_by_package_sha_queries_name_and_sha_in_version_order() -> None:
    row = a_row(a_version(name="acme.spec", source="package"))
    row.package_sha = SHA
    session = RecordingSession(scalars_queue=[[row]])

    found = repository(session).get_by_package_sha("acme.spec", SHA)

    assert found is not None and found.package_sha == SHA
    statement = str(session.statements[0])
    assert "template_version.package_sha" in statement
    assert "ORDER BY template_version.version" in statement


def test_a_miss_is_none() -> None:
    assert repository(RecordingSession(scalars_queue=[[]])).get_by_package_sha("n", SHA) is None


def test_an_unstorable_name_or_sha_matches_nothing_without_a_query() -> None:
    session = RecordingSession()
    assert repository(session).get_by_package_sha("a\x00b", SHA) is None
    assert repository(session).get_by_package_sha("n", "a\x00b") is None
    assert session.statements == []
