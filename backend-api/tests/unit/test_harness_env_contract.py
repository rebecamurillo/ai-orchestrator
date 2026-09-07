"""The Python environment builder and the shell scripts, held to one list (AD-10, AD-5).

`scripts/harness/_common.sh` is normative: it declares `HARNESS_ENV_CONTRACT`, and each
`scripts/harness/<name>.sh` declares the harness-native `HARNESS_ENV_ALIASES` derived from
it. `infrastructure/harness/env.py` states the same list in Python, and an adapter's
`env_for` produces exactly those names. Two statements of one contract drift the moment
nothing compares them, so this module parses the bash arrays out of the scripts and
compares them with what the Python actually produces.

Three assertions, and the third is what makes the first two worth having:

- the Python mirror constant equals the array `_common.sh` declares, name for name and in
  the same order;
- `set(env_for(...))` is exactly that contract, plus the harness's alias names, plus the
  Project's own variables, plus the four names every process needs (`HOME`, `PATH`, `LANG`,
  `TERM`);
- run against a *copy* of `_common.sh` with one name appended, the same comparison fails and
  names the added variable — so a name added to the script and forgotten in Python is caught
  by a red test rather than by a harness that cannot find its own configuration.

Epic 7 reuses this module's shape for `codex` and `local`: only `ALIAS_SCRIPT` and the
alias builder change.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import env_for
from orchestrator.infrastructure.harness.claude.adapter import claude_aliases
from orchestrator.infrastructure.harness.env import BASE_NAMES, HARNESS_ENV_CONTRACT
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
CONTRACT_SCRIPT = HARNESS_DIR / "_common.sh"
ALIAS_SCRIPT = HARNESS_DIR / "claude.sh"

#: The Project's own variables, as `env_for` receives them decrypted (AD-5).
PROJECT_ENV = {"MY_FLAG": "on", "NPM_CONFIG_REGISTRY": "https://registry.example"}


def bash_array(script: Path, name: str) -> tuple[str, ...]:
    """The words of `name=( … )` in a bash script, comments and line breaks ignored.

    Deliberately not a bash invocation: sourcing `_common.sh` to read the array would make
    this test depend on a shell, and the point is to read the declaration a reader reads.
    """
    body = script.read_text()
    match = re.search(rf"^{name}=\((.*?)\)", body, re.MULTILINE | re.DOTALL)
    assert match, f"{script.name}: no {name}=( … ) declaration"
    words = match.group(1).split()
    assert words, f"{script.name}: {name} is empty"
    return tuple(words)


def alias_names(script: Path) -> tuple[str, ...]:
    """The left-hand names of `HARNESS_ENV_ALIASES=(NAME=source …)`."""
    return tuple(word.split("=", 1)[0] for word in bash_array(script, "HARNESS_ENV_ALIASES"))


def an_attempt(**overrides: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "running",
        "harness": "claude",
        "model": "claude-opus-5",
    }
    fields.update(overrides)
    return Attempt(**fields)  # type: ignore[arg-type]


def a_run(attempt: Attempt) -> Run:
    return Run(
        id=attempt.run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="initiative",
        template_version=1,
        status="running",
        budget_usd=Decimal("40"),
        created_at=datetime(2026, 9, 7, tzinfo=UTC),
    )


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


def keys_for(settings: Settings, *, log_content: bool = False) -> set[str]:
    attempt = an_attempt()
    return set(
        env_for(
            attempt,
            run=a_run(attempt),
            project_slug="acme",
            project_env=PROJECT_ENV,
            log_content=log_content,
            settings=settings,
            story_id="5-1",
            aliases=claude_aliases,
        )
    )


# ── the Python mirror is the script's own list ───────────────────────────────


def test_the_python_contract_mirrors_the_normative_script() -> None:
    assert HARNESS_ENV_CONTRACT == bash_array(CONTRACT_SCRIPT, "HARNESS_ENV_CONTRACT")


def test_the_contract_names_no_credential_a_harness_never_receives() -> None:
    """AD-5, restated over the Python list so the mirror cannot re-introduce one."""
    for forbidden in ("GITHUB_TOKEN", "LITELLM_SPEND_KEY", "DATABASE_URL"):
        assert forbidden not in HARNESS_ENV_CONTRACT


# ── env_for produces exactly the two script lists, plus project and base ─────


def test_the_key_set_is_the_two_script_lists_plus_the_project_and_the_base_names(
    settings: Settings,
) -> None:
    expected = (
        set(bash_array(CONTRACT_SCRIPT, "HARNESS_ENV_CONTRACT"))
        | set(alias_names(ALIAS_SCRIPT))
        | set(PROJECT_ENV)
        | set(BASE_NAMES)
    )

    assert keys_for(settings) == expected


def test_the_base_names_are_the_four_the_process_runner_re_adds() -> None:
    assert set(BASE_NAMES) == {"HOME", "PATH", "LANG", "TERM"}


# ── the gate fires: a name added to the script and not to Python is caught ───


def test_a_name_added_to_the_script_makes_the_comparison_fail_naming_it(
    settings: Settings, tmp_path: Path
) -> None:
    """The proof that the assertion above is a gate and not a tautology.

    A copy of `_common.sh` gains one name in the array; the same comparison is re-run
    against the copy and must fail, and the failure must name the variable that was added,
    because "the environments differ" is only actionable when it says which name.
    """
    added = "ORCH_NEW_THING"
    copy = tmp_path / "_common.sh"
    body = CONTRACT_SCRIPT.read_text()
    drifted_body = body.replace("ORCH_LOG_CONTENT)", f"ORCH_LOG_CONTENT {added})")
    assert drifted_body != body, "the array no longer ends with ORCH_LOG_CONTENT)"
    copy.write_text(drifted_body)

    drifted = set(bash_array(copy, "HARNESS_ENV_CONTRACT"))

    assert added in drifted
    assert added not in HARNESS_ENV_CONTRACT
    missing = drifted - keys_for(settings)
    assert added in missing, f"the drifted name must be reported: {sorted(missing)}"
