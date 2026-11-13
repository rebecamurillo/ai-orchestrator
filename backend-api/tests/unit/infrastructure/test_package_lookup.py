"""`HttpPackageLookup` over `httpx.MockTransport` and `FakeAnalysisTools` (epic 5 story 3, AC9).

The registry bodies and the osv-scanner reports are the synthetic fixtures of
`fixtures/analysis/tier1b/` (see its README): no live registry or scan stands behind them.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.package_lookup import FakePackageLookup

from orchestrator.domain.ports.analysis_tools import ToolRun
from orchestrator.domain.ports.package_lookup import (
    LookupUnavailable,
    PackageLookup,
    PackageMeta,
)
from orchestrator.infrastructure.analysis.package_lookup import (
    OSV_COMMAND,
    OSV_JSON_COMMAND,
    OSV_TIMEOUT_MIN,
    HttpPackageLookup,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "analysis" / "tier1b"
NPM = (FIXTURES / "synthetic-npm-left-pad.json").read_text()
PYPI = (FIXTURES / "synthetic-pypi-requests.json").read_text()
DEFAULT_HEADERS = {"host", "accept", "accept-encoding", "connection", "user-agent"}


def lookup_with(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[HttpPackageLookup, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(record))
    return HttpPackageLookup(FakeAnalysisTools(), client), seen


def ok(body: str) -> Callable[[httpx.Request], httpx.Response]:
    return lambda _request: httpx.Response(200, text=body)


# ── metadata ─────────────────────────────────────────────────────────────────


def test_an_npm_request_carries_only_the_package_name_in_its_url() -> None:
    lookup, seen = lookup_with(ok(NPM))
    meta = lookup.metadata("npm", "left-pad", "1.3.0", None)
    (request,) = seen
    assert request.method == "GET"
    assert str(request.url) == "https://registry.npmjs.org/left-pad"
    assert request.content == b""
    assert request.url.query == b""
    assert request.headers["user-agent"] == "ai-orchestrator"
    assert set(request.headers) <= DEFAULT_HEADERS
    assert meta == PackageMeta(True, datetime(2014, 3, 14, 18, 19, 21, 325000, tzinfo=UTC), "MIT")


def test_a_scoped_npm_name_has_its_slash_encoded() -> None:
    lookup, seen = lookup_with(ok(NPM))
    lookup.metadata("npm", "@scope/pkg", "1.0.0", None)
    assert seen[0].url.raw_path == b"/@scope%2Fpkg"


def test_a_private_registry_is_the_base_and_its_trailing_slash_is_dropped() -> None:
    lookup, seen = lookup_with(ok(NPM))
    lookup.metadata("npm", "left-pad", "1.3.0", "https://npm.example.internal/base/")
    assert str(seen[0].url) == "https://npm.example.internal/base/left-pad"


def test_the_licence_falls_back_to_the_package_level_one_and_reads_the_dict_form() -> None:
    lookup, _ = lookup_with(ok(NPM))
    assert lookup.metadata("npm", "left-pad", "9.9.9", None).licence == "WTFPL"
    lookup, _ = lookup_with(ok('{"license": {"type": "ISC", "url": "x"}, "time": {}}'))
    assert lookup.metadata("npm", "x", "1.0.0", None) == PackageMeta(True, None, "ISC")
    lookup, _ = lookup_with(ok('{"license": "  ", "versions": {"1.0.0": 3}, "time": 5}'))
    assert lookup.metadata("npm", "x", "1.0.0", None) == PackageMeta(True, None, None)
    lookup, _ = lookup_with(ok('{"license": 7, "time": {"created": "not a date"}}'))
    assert lookup.metadata("npm", "x", "1.0.0", None) == PackageMeta(True, None, None)
    lookup, _ = lookup_with(ok('{"time": {"created": 12}}'))
    assert lookup.metadata("npm", "x", "1.0.0", None).first_published is None


def test_a_timestamp_without_a_zone_is_read_as_utc() -> None:
    lookup, _ = lookup_with(ok('{"time": {"created": "2020-01-02T03:04:05"}}'))
    assert lookup.metadata("npm", "x", "1", None).first_published == datetime(
        2020, 1, 2, 3, 4, 5, tzinfo=UTC
    )


def test_pypi_reads_the_earliest_upload_and_the_licence() -> None:
    lookup, seen = lookup_with(ok(PYPI))
    meta = lookup.metadata("pypi", "requests", "2.32.3", None)
    assert str(seen[0].url) == "https://pypi.org/pypi/requests/json"
    assert meta == PackageMeta(True, datetime(2011, 2, 13, 9, 0, tzinfo=UTC), "Apache 2.0")


def test_pypi_prefers_the_licence_expression_and_reads_a_blank_licence_as_none() -> None:
    body = '{"info": {"license_expression": "MIT", "license": "other"}, "releases": {}}'
    lookup, _ = lookup_with(ok(body))
    assert lookup.metadata("pypi", "x", "1", "https://pypi.example.internal").licence == "MIT"
    lookup, seen = lookup_with(
        ok('{"info": {"license": " "}, "releases": {"1": "nope", "2": [3]}}')
    )
    assert lookup.metadata("pypi", "x", "1", "https://pypi.example.internal") == PackageMeta(
        True, None, None
    )
    assert str(seen[0].url) == "https://pypi.example.internal/pypi/x/json"
    lookup, _ = lookup_with(ok("{}"))
    assert lookup.metadata("pypi", "x", "1", None) == PackageMeta(True, None, None)


def test_a_404_is_a_package_that_does_not_exist() -> None:
    lookup, _ = lookup_with(lambda _r: httpx.Response(404))
    assert lookup.metadata("npm", "nope", "1.0.0", None) == PackageMeta(False, None, None)


@pytest.mark.parametrize("status", [500, 502, 401, 403, 429])
def test_any_other_status_is_a_registry_that_did_not_answer(status: int) -> None:
    lookup, _ = lookup_with(lambda _r: httpx.Response(status))
    with pytest.raises(LookupUnavailable) as raised:
        lookup.metadata("npm", "x", "1.0.0", "https://private.example.internal/secret")
    assert raised.value.reason == "registry unreachable"
    assert "secret" not in str(raised.value)


def test_a_connection_error_or_a_timeout_is_a_registry_that_did_not_answer() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    for handler in (refuse, slow):
        lookup, _ = lookup_with(handler)
        with pytest.raises(LookupUnavailable, match="registry unreachable"):
            lookup.metadata("pypi", "x", "1.0.0", None)


@pytest.mark.parametrize("body", ["<html>", "[]", "3"])
def test_a_body_that_is_not_a_package_document_is_a_registry_that_did_not_answer(body: str) -> None:
    lookup, _ = lookup_with(ok(body))
    with pytest.raises(LookupUnavailable, match="registry unreachable"):
        lookup.metadata("npm", "x", "1.0.0", None)


# ── vulnerabilities ──────────────────────────────────────────────────────────


def scan(
    tmp_path: Path, run: ToolRun, *, sarif: bool = True, report: str | None = None
) -> tuple[HttpPackageLookup, FakeAnalysisTools, Path]:
    lock = tmp_path / "package-lock.json"
    if sarif:
        (tmp_path / "package-lock.json.osv.sarif").write_bytes(
            (FIXTURES / "synthetic-osv.sarif").read_bytes()
        )
    body = (FIXTURES / "synthetic-osv.json").read_text() if report is None else report
    (tmp_path / "package-lock.json.osv.json").write_text(body)
    tools = FakeAnalysisTools({"osv-scanner": run})
    return (
        HttpPackageLookup(tools, httpx.Client(transport=httpx.MockTransport(ok("{}")))),
        tools,
        lock,
    )


def test_the_vulnerable_pairs_and_the_sarif_come_from_the_two_scans(tmp_path: Path) -> None:
    lookup, tools, lock = scan(tmp_path, ToolRun(1, "", "", "2.7.1"))
    report = lookup.vulnerabilities(lock)
    assert report.vulnerable == {("left-pad", "1.3.0"), ("requests", "2.31.0")}
    assert report.sarif == (FIXTURES / "synthetic-osv.sarif").read_bytes()
    assert report.version == "2.7.1"
    sarif_call, json_call = tools.calls
    assert sarif_call["args"] == (
        "scan",
        "--lockfile",
        str(lock),
        "--format",
        "sarif",
        "--output-file",
        f"{lock}.osv.sarif",
    )
    assert json_call["args"] == (
        "scan",
        "--lockfile",
        str(lock),
        "--format",
        "json",
        "--output-file",
        f"{lock}.osv.json",
    )
    assert sarif_call["cwd"] == json_call["cwd"] == tmp_path
    assert sarif_call["timeout"] == json_call["timeout"] == OSV_TIMEOUT_MIN == 10
    assert OSV_COMMAND[0] == OSV_JSON_COMMAND[0] == "scan"


def test_a_clean_scan_that_exits_zero_is_no_vulnerable_pair(tmp_path: Path) -> None:
    lookup, _, lock = scan(tmp_path, ToolRun(0, "", "", "2.7.1"), report='{"results": []}')
    assert lookup.vulnerabilities(lock).vulnerable == frozenset()
    assert json.loads(lookup.vulnerabilities(lock).sarif)["version"] == "2.1.0"


def test_an_exit_outside_the_finished_codes_does_not_answer(tmp_path: Path) -> None:
    lookup, _, lock = scan(tmp_path, ToolRun(127, "osv-scanner: not found\nmore", "", "unknown"))
    with pytest.raises(LookupUnavailable) as raised:
        lookup.vulnerabilities(lock)
    assert raised.value.reason == "osv-scanner: exit 127: osv-scanner: not found"


def test_a_timeout_does_not_answer(tmp_path: Path) -> None:
    lookup, _, lock = scan(tmp_path, ToolRun(None, "", "", "2.7.1", timed_out=True))
    with pytest.raises(LookupUnavailable, match="osv-scanner: timed out"):
        lookup.vulnerabilities(lock)


def test_a_missing_report_does_not_answer(tmp_path: Path) -> None:
    lookup, _, lock = scan(tmp_path, ToolRun(0, "", "", "2.7.1"), sarif=False)
    with pytest.raises(LookupUnavailable, match="osv-scanner: no report"):
        lookup.vulnerabilities(lock)


@pytest.mark.parametrize(
    "report",
    ["{broken", "[]", '{"results": [{"packages": [{"package": {}}]}]}', '{"results": 3}'],
)
def test_an_unreadable_json_report_does_not_answer(tmp_path: Path, report: str) -> None:
    lookup, _, lock = scan(tmp_path, ToolRun(1, "", "", "2.7.1"), report=report)
    with pytest.raises(LookupUnavailable, match="osv-scanner: report unreadable"):
        lookup.vulnerabilities(lock)


# ── the port ─────────────────────────────────────────────────────────────────


def test_the_adapter_and_the_fake_both_satisfy_the_port() -> None:
    assert isinstance(HttpPackageLookup(FakeAnalysisTools()), PackageLookup)
    assert isinstance(FakePackageLookup(), PackageLookup)
