"""Root `AGENTS.md` carries SPEC.md's hard-rule-7 line byte for byte (epic 8 story 3, AC14)."""

from __future__ import annotations

from tests.unit.conftest import REPO_ROOT

RULE = (
    "7. **No silent retry.** A failed command is reported with its output. The only automatic "
    "retries in this system are the ones a template declares, and each is bounded: `retry: "
    "{max, prompt}` on an agent step, and `retry: {max, sync_first: true}` on a `git.push` "
    "step, which syncs the branch and pushes again, each try written to the step log. "
    "(Operator revision 2026-11-23, initiative orchestrator-initiative-steps; AD-37.)"
)


def test_exactly_one_line_is_hard_rule_7_and_it_is_the_declared_text() -> None:
    lines = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()

    rule_7 = [line for line in lines if line.startswith("7. **No silent retry.**")]

    assert rule_7 == [RULE]
