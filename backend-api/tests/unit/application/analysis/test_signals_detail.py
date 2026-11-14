"""Languages and commits outside the Run on `RepositorySignals` (epic 5 story 5, AC1)."""

from __future__ import annotations

import json
from uuid import UUID

from orchestrator.application.analysis.declaration import DEFAULT_DECLARATION
from orchestrator.application.analysis.inputs import RepositoryInputs
from orchestrator.application.analysis.signals import (
    RepositorySignals,
    collect_tier1a,
    signals_from_json,
    signals_to_json,
)
from orchestrator.domain.ports.git_analysis import NameStatus, NumstatEntry
from tests.unit.application.analysis.test_signals_collect import ANALYSIS_ID, NOW, ROOT, analysis
from tests.unit.fakes.analysis_tools import FakeAnalysisTools
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.workspace import FakeWorkspace


def _git() -> FakeGit:
    script = AnalysisScript(
        numstat={("b1", "h1"): (NumstatEntry("app.py", 4, 0, False),)},
        name_status={("b1", "h1"): (NameStatus("M", "app.py", None),)},
    )
    return FakeGit(analysis=script, files={("h1", "app.py"): "x = 1\n"})


def _collect(status: str, commits: tuple[str, ...]) -> RepositorySignals:
    workspace = FakeWorkspace()
    scratch = None if status == "failed" else ROOT / f"{ANALYSIS_ID}/root"
    prepared = RepositoryInputs(analysis(status), scratch, DEFAULT_DECLARATION, commits, False)
    return collect_tier1a(
        prepared,
        git=_git(),
        scratch_root=workspace,
        tools=FakeAnalysisTools(workspace=workspace, root=ROOT),
        new_id=iter(UUID(int=n) for n in range(900, 999)).__next__,
    )


def test_the_ok_path_stores_languages_and_commits_outside_the_run() -> None:
    signals = _collect("ok", ("c1", "c2"))

    assert signals.languages == ("Python",)
    assert signals.commits_not_made_by_run == ("c1", "c2")


def test_the_failed_path_records_neither() -> None:
    signals = _collect("failed", ())

    assert signals.languages is None
    assert signals.commits_not_made_by_run is None
    assert NOW


def test_json_round_trip_keeps_the_new_fields() -> None:
    signals = RepositorySignals(
        ".", "ok", "", (), languages=("Go",), commits_not_made_by_run=("c",)
    )

    back = signals_from_json(signals_to_json(signals))

    assert back.languages == ("Go",)
    assert back.commits_not_made_by_run == ("c",)


def test_an_old_document_loads_with_none() -> None:
    old = json.dumps(
        {
            "path": ".",
            "status": "ok",
            "output": "",
            "counts": [],
            "words": {},
            "tool_versions": {},
        }
    ).encode()

    back = signals_from_json(old)

    assert back.languages is None
    assert back.commits_not_made_by_run is None
    assert json.loads(signals_to_json(back))["languages"] is None
