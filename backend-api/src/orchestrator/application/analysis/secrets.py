"""The gitleaks scan over a repository's added lines (ARCHITECTURE §7.8, hard rule 5).

The folder holds, per changed file, only the lines the head adds, so the count is the
secrets the change introduced. The report is redacted at the source: no secret value reaches
the database.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.summary import not_run
from orchestrator.domain.entities.analysis import AnalysisArtifact
from orchestrator.domain.ports.analysis_tools import AnalysisTools
from orchestrator.domain.ports.workspace import Workspace

GITLEAKS = "gitleaks"
SARIF_MEDIA_TYPE = "application/sarif+json"
GITLEAKS_TIMEOUT_MIN = 10
GITLEAKS_COMMAND = (
    GITLEAKS,
    "dir",
    "{folder}",
    "--report-format",
    "sarif",
    "--report-path",
    "{file}",
    "--redact",
    "--no-banner",
    "--ignore-gitleaks-allow",
)
#: gitleaks reads `.gitleaks.toml` and `.gitleaksignore` from the root it scans, and honours
#: inline `gitleaks:allow`: all three would let the change under measure silence the scan.
#: The added lines therefore sit one level below the scanned root, and inline allows are ignored.
ADDED_FILES = "files"
#: gitleaks exits 1 when it found something and 0 when it did not.
FINISHED_EXITS = (0, 1)


@dataclass(frozen=True)
class SecretsResult:
    count: int | None
    missing: str | None
    artifact: AnalysisArtifact | None
    version: str


def _failed(reason: str, version: str) -> SecretsResult:
    return SecretsResult(None, not_run(f"{GITLEAKS}: {reason}"), None, version)


def scan_secrets(  # noqa: PLR0913 — the added lines, the folder they go to and the ports
    added: Mapping[str, tuple[str, ...]],
    *,
    scratch_root: Workspace,
    scratch_path: Path,
    relative: str,
    tools: AnalysisTools,
    analysis_id: UUID,
    new_id: Callable[[], UUID],
) -> SecretsResult:
    files = {path: lines for path, lines in added.items() if lines}
    if not files:
        return SecretsResult(0, None, None, "")
    for path, lines in files.items():
        scratch_root.write(f"{relative}.added/{ADDED_FILES}/{path}", "\n".join(lines))
    folder = Path(f"{scratch_path}.added")
    report = Path(f"{scratch_path}.gitleaks.sarif")
    args = [a.format(folder=folder, file=report) for a in GITLEAKS_COMMAND[1:]]
    run = tools.run(GITLEAKS, args, scratch_path.parent, GITLEAKS_TIMEOUT_MIN)
    if run.timed_out:
        return _failed("timed out", run.version)
    if run.exit not in FINISHED_EXITS:
        first = run.stdout.strip().splitlines()[:1]
        return _failed(": ".join([f"exit {run.exit}", *first]), run.version)
    text = scratch_root.read(f"{relative}.gitleaks.sarif")
    if text is None:
        return _failed("no report", run.version)
    try:
        count = sum(len(r["results"]) for r in json.loads(text)["runs"])
    except ValueError, KeyError, TypeError:
        return _failed("report unreadable", run.version)
    artifact = AnalysisArtifact(
        id=new_id(),
        analysis_id=analysis_id,
        tool=GITLEAKS,
        media_type=SARIF_MEDIA_TYPE,
        body=text.encode(),
    )
    return SecretsResult(count, None, artifact, run.version)
