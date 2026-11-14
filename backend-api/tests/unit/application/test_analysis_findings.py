"""Read the stored opengrep findings listing of an analysis (epic 6 story 4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from orchestrator.application.analysis.findings import FINDINGS_TOOL
from orchestrator.application.use_cases.analysis_findings import FindingRow, read_findings
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.db import FakeUnitOfWork

RUN = new_id()


ROW = {
    "kind": "security",
    "rule": "r.xss",
    "path": "a.py",
    "line": 4,
    "severity": "high",
    "cwe": ["CWE-79"],
    "state": "new",
}


def world(body: object, media: str = "application/json") -> tuple[FakeAnalysisRepository, Analysis]:
    repo = FakeAnalysisRepository()
    found = Analysis(
        id=new_id(),
        run_id=RUN,
        repository_path=".",
        status="ok",
        created_at=datetime(2026, 11, 13, tzinfo=UTC),
    )
    repo.add(found)
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    repo.add_artifact(
        AnalysisArtifact(
            id=new_id(), analysis_id=found.id, tool=FINDINGS_TOOL, media_type=media, body=raw
        )
    )
    return repo, found


def test_rows_are_read_in_payload_order() -> None:
    repo, found = world([ROW, {**ROW, "line": None, "cwe": [], "state": "absent"}])

    rows = read_findings(repo, FakeUnitOfWork(), RUN, found.id)

    assert rows[0] == FindingRow("security", "r.xss", "a.py", 4, "high", ("CWE-79",), "new")
    assert (rows[1].line, rows[1].cwe, rows[1].state) == (None, (), "absent")


def test_an_unknown_analysis_or_another_runs_is_not_found() -> None:
    repo, found = world([])

    with pytest.raises(NotFound):
        read_findings(repo, FakeUnitOfWork(), RUN, new_id())
    with pytest.raises(NotFound):
        read_findings(repo, FakeUnitOfWork(), new_id(), found.id)


def test_no_listing_or_a_wrong_media_type_is_not_found() -> None:
    repo, found = world([], media="text/plain")
    bare = FakeAnalysisRepository()
    bare.add(found)

    for source in (repo, bare):
        with pytest.raises(NotFound, match="no findings listing"):
            read_findings(source, FakeUnitOfWork(), RUN, found.id)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"a": 1}',
        json.dumps([{"kind": "security"}]).encode(),
        b"[1]",
        json.dumps([{**ROW, "kind": "secret"}]).encode(),
        json.dumps([{**ROW, "severity": "critical"}]).encode(),
        json.dumps([{**ROW, "state": "gone"}]).encode(),
        json.dumps([{**ROW, "line": "12a"}]).encode(),
        json.dumps([{**ROW, "line": True}]).encode(),
        json.dumps([{**ROW, "cwe": [79]}]).encode(),
        json.dumps([{**ROW, "rule": 1}]).encode(),
        json.dumps([{**ROW, "path": None}]).encode(),
    ],
    ids=[
        "syntax",
        "not a list",
        "missing field",
        "not an object",
        "unknown kind",
        "unknown severity",
        "unknown state",
        "line not an int",
        "line a bool",
        "cwe not text",
        "rule not text",
        "path not text",
    ],
)
def test_a_malformed_body_is_not_found(body: bytes) -> None:
    repo, found = world(body)

    with pytest.raises(NotFound, match="no findings listing"):
        read_findings(repo, FakeUnitOfWork(), RUN, found.id)
