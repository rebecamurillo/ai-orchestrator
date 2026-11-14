"""`HttpPackageLookup`: the `PackageLookup` port over osv-scanner and the package registries.

RM-6: a registry request carries the package name in its URL and nothing else — no body, no
credential, a generic `User-Agent` — and the vulnerability scan reads a lock file on the
instance. The private registry URL of a declaration is used as the base and never reported.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from orchestrator.domain.ports.analysis_tools import AnalysisTools, ToolRun
from orchestrator.domain.ports.package_lookup import LookupUnavailable, PackageMeta, VulnReport

OSV_SCANNER = "osv-scanner"
OSV_COMMAND = ("scan", "--lockfile", "{file}", "--format", "sarif", "--output-file", "{report}")
OSV_JSON_COMMAND = ("scan", "--lockfile", "{file}", "--format", "json", "--output-file", "{report}")
OSV_TIMEOUT_MIN = 10
#: osv-scanner exits 0 when it found nothing and 1 when it found vulnerabilities.
OSV_FINISHED_EXITS = (0, 1)
DEFAULT_REGISTRIES = {"npm": "https://registry.npmjs.org", "pypi": "https://pypi.org"}
USER_AGENT = "ai-orchestrator"
UNREACHABLE = "registry unreachable"
NOT_FOUND = 404
OK = 200


def _unavailable(reason: str) -> LookupUnavailable:
    return LookupUnavailable(f"{OSV_SCANNER}: {reason}")


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _text(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("type")
    return value if isinstance(value, str) and value.strip() else None


def _npm_meta(document: dict[str, Any], version: str) -> PackageMeta:
    versions = document.get("versions")
    release = versions.get(version) if isinstance(versions, dict) else None
    licence = _text(release.get("license")) if isinstance(release, dict) else None
    times = document.get("time")
    created = _timestamp(times.get("created")) if isinstance(times, dict) else None
    return PackageMeta(True, created, licence or _text(document.get("license")))


def _pypi_meta(document: dict[str, Any]) -> PackageMeta:
    info = document.get("info")
    info = info if isinstance(info, dict) else {}
    releases = document.get("releases")
    uploads = [
        stamp
        for files in (releases.values() if isinstance(releases, dict) else [])
        if isinstance(files, list)
        for entry in files
        if isinstance(entry, dict) and (stamp := _timestamp(entry.get("upload_time_iso_8601")))
    ]
    licence = _text(info.get("license_expression")) or _text(info.get("license"))
    return PackageMeta(True, min(uploads, default=None), licence)


class HttpPackageLookup:
    def __init__(
        self,
        tools: AnalysisTools,
        client: httpx.Client | None = None,
        timeout_s: float = 10.0,
    ) -> None:
        self._tools = tools
        self._client = client or httpx.Client(timeout=timeout_s)

    def metadata(
        self, ecosystem: str, name: str, version: str, registry_url: str | None
    ) -> PackageMeta:
        base = (registry_url or DEFAULT_REGISTRIES[ecosystem]).rstrip("/")
        url = (
            f"{base}/{name.replace('/', '%2F')}"
            if ecosystem == "npm"
            else f"{base}/pypi/{name}/json"
        )
        try:
            response = self._client.get(url, headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as error:
            raise LookupUnavailable(UNREACHABLE) from error
        if response.status_code == NOT_FOUND:
            return PackageMeta(False, None, None)
        if response.status_code != OK:
            raise LookupUnavailable(UNREACHABLE)
        try:
            document = response.json()
            if not isinstance(document, dict):
                raise ValueError
            return _npm_meta(document, version) if ecosystem == "npm" else _pypi_meta(document)
        except ValueError as error:
            raise LookupUnavailable(UNREACHABLE) from error

    def _scan(self, command: tuple[str, ...], lockfile: Path, suffix: str) -> tuple[ToolRun, bytes]:
        report = Path(f"{lockfile}{suffix}")
        args = [a.format(file=lockfile, report=report) for a in command]
        run = self._tools.run(OSV_SCANNER, args, lockfile.parent, OSV_TIMEOUT_MIN)
        if run.timed_out:
            raise _unavailable("timed out")
        if run.exit not in OSV_FINISHED_EXITS:
            first = run.stdout.strip().splitlines()[:1]
            raise _unavailable(": ".join([f"exit {run.exit}", *first]))
        try:
            return run, report.read_bytes()
        except OSError as error:
            raise _unavailable("no report") from error

    def vulnerabilities(self, lockfile_path: Path) -> VulnReport:
        """The SARIF is kept as the artefact; the pairs come from a second scan as JSON, whose
        `results[].packages[].package` is the documented place for them."""
        run, sarif = self._scan(OSV_COMMAND, lockfile_path, ".osv.sarif")
        _, body = self._scan(OSV_JSON_COMMAND, lockfile_path, ".osv.json")
        try:
            document = json.loads(body)
            pairs = frozenset(
                (package["package"]["name"], package["package"]["version"])
                for result in document.get("results", [])
                for package in result.get("packages", [])
            )
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise _unavailable("report unreadable") from error
        return VulnReport(pairs, sarif, run.version)
