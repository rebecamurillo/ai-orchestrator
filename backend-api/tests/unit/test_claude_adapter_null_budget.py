"""`ClaudeHarness._argv`: `budget_usd_remaining=None` omits `--max-budget-usd` (story 3-2, AC3).

Complementary to `test_claude_adapter.py` — only the null-budget path is new here.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.infrastructure.harness.claude.adapter import ClaudeHarness
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

SESSION_ID = "0199a1f2-7c3d-7b2a-9f21-0d1e2f3a4b5c"
TIMEOUT_MIN = 45.0
PROMPT = "Run bmad-build-auto for story 5-1."
WORKTREE = Path("/work/acme/widgets/wt/feat-x")


def test_null_budget_omits_max_budget_usd_flag(env: dict[str, str], tmp_path: Path) -> None:
    settings = Settings()
    runner = FakeProcessRunner()
    harness = ClaudeHarness(runner, settings)
    log_path = tmp_path / "logs" / "007-1.log"

    harness.run(
        cwd=WORKTREE,
        prompt=PROMPT,
        env={"ORCH_RUN_ID": "r-1"},
        model=None,
        session_id=SESSION_ID,
        budget_usd_remaining=None,
        timeout_min=TIMEOUT_MIN,
        log_path=log_path,
    )

    cmd = runner.called("start")[0]["cmd"]
    assert "--max-budget-usd" not in cmd
