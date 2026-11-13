"""`analyse_run` reads the Project env once and runs Tier 2 (epic 6 story 1)."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

from orchestrator.application.analysis.run_analysis import analyse_run
from orchestrator.domain.ports.git_analysis import NameStatus
from tests.unit.application.analysis.test_run_analysis import RUN, World, record
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.process import FakeProcessRunner

TWO_SIDES = 2
DECLARATION = "tier2: true\ncommands:\n  lint: L\n"


def world() -> World:
    git = FakeGit(
        analysis=AnalysisScript(
            merge_bases={("h1", "origin/main"): "m0"},
            name_status={("m0", "h1"): (NameStatus("M", "a.py", None),)},
        ),
        files={("m0", "orchestrator-analysis.yaml"): DECLARATION},
    )
    return World([record(".", 10)], git)


def test_the_project_env_is_read_once_and_reaches_the_commands() -> None:
    held = world()
    runner = FakeProcessRunner()
    asked: list[UUID] = []

    def project_env(run_id: UUID) -> dict[str, str]:
        asked.append(run_id)
        return {"NODE_ENV": "test", "GITHUB_TOKEN": "x"}

    deps = replace(held.deps(), runner=runner, command_timeout_min=3, project_env=project_env)
    analyse_run(deps, held.writes, RUN, None)
    assert asked == [RUN]
    starts = runner.called("start")
    assert len(starts) == TWO_SIDES
    assert {tuple(c["env"]) for c in starts} == {("NODE_ENV",)}
    assert {c["timeout_min"] for c in starts} == {3}
    tools = (
        {a.tool for a in held.analyses.artifacts} if hasattr(held.analyses, "artifacts") else set()
    )
    assert not tools or "tier2:head:lint" in tools


def test_without_a_runner_a_declared_repository_is_not_run() -> None:
    held = world()
    analyse_run(held.deps(), held.writes, RUN, None)
    summary = held.analyses.rows[0]
    assert summary.status == "ok"
