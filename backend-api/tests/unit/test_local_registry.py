"""`local` in the registry, and everything the two revised assertions used to carry (AD-10).

Story 7.1 built `tests/unit/test_codex_registry.py` on the Operator's ruling that the *frozen*
files state a permanent invariant (`set(registry) <= set(HARNESS_NAMES)`) while the per-story
exactness lives in a per-story file. That module's own docstring named **this** story as the one
that revises its exact sets, and the Operator confirmed it in session on 2026-09-10 along with
two further rulings. This module is the coverage that strictly exceeds what those revisions
replaced — the guarantees restated, and the ones no earlier assertion could have made because
the third adapter did not exist.

What was revised, and what is restated here:

- `test_codex_registry.py` `REGISTERED` and the `alias_table` key set gained `local`. Restated
  below as the same closed sets, plus: `local` is a `LocalHarness`, satisfies the port under its
  own key, runs on the runner the registry was handed, is a name the `harness` table seeds, and
  reaches the walker.
- `test_harness_registry.py:77` and `test_harness_env_subscription.py`'s
  `ALIASES == {"claude": claude_aliases}` gained the `local` key. Restated below as what the
  equality is *for*: that the table is keyed the way the registry is, that every builder in it
  is a plain `AliasBuilder` needing no `Settings`, and that a `local` attempt's environment
  really carries the two names `scripts/harness/opencode.sh` declares.

And one thing the registry could not say before: `local` is the first registered harness that
declares no resume, so FR-21's terminal block is `None` for it — not because the registry lacks
the name, which is what made that answer true until today, but because the adapter says so.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.terminal import TerminalPorts, resume_command
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.harness import HARNESS_NAMES
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import Harness as HarnessPort
from orchestrator.infrastructure.db import seed as db_seed
from orchestrator.infrastructure.dbos.startup import walker_deps
from orchestrator.infrastructure.harness.fake import NAME as FAKE_NAME
from orchestrator.infrastructure.harness.opencode import LocalHarness, local_aliases
from orchestrator.infrastructure.harness.registry import (
    ALIASES,
    alias_table,
    build_harness_env,
    build_harnesses,
    build_terminal_env,
)
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

#: What the registry holds as of story 7.3 — the three names `HARNESS_NAMES` declares, and now
#: all of them. `test_codex_registry.py`'s `REGISTERED` was revised to the same set; this is the
#: second statement of it, in the file whose story made it true.
REGISTERED = {"claude", "codex", "local"}

NOW = datetime(2026, 9, 10, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
SESSION = "ses_7f3c1a0b9d2e4f5a"


def a_run(**over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "story",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10.00"),
        "created_at": NOW,
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def an_attempt(run: Run, harness: str | None, **over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run.id,
        "step_run_id": new_id(),
        "n": 1,
        "status": "running",
        "harness": harness,
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def an_agent_row(attempt: Attempt) -> StepRun:
    return StepRun(
        id=attempt.step_run_id,
        run_id=attempt.run_id,
        seq=0,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="blocked",
        story_id="7-3",
    )


def sessions() -> object:
    def factory() -> object:  # pragma: no cover — nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


# ── the registry now holds all three ─────────────────────────────────────────


def test_the_registry_holds_exactly_the_three_harnesses_the_domain_declares(
    env: dict[str, str],
) -> None:
    """The exactness `<=` drops, restated — and now the two sets coincide, which is the state
    the epic was working towards: every name the domain declares has an adapter."""
    built = build_harnesses(Settings(), FakeProcessRunner())

    assert set(built) == REGISTERED
    assert set(built) == set(HARNESS_NAMES)


def test_local_is_registered_under_the_name_a_template_writes(env: dict[str, str]) -> None:
    """`local` is the table row and the Template's value; `opencode` is the CLI it drives and
    is a key nowhere in this system."""
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    assert isinstance(harnesses["local"], LocalHarness)
    assert harnesses["local"].name == "local"
    assert "opencode" not in harnesses


def test_local_satisfies_the_port_under_its_own_key(env: dict[str, str]) -> None:
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    assert isinstance(harnesses["local"], HarnessPort)


def test_local_starts_its_processes_through_the_runner_the_registry_was_handed(
    env: dict[str, str],
) -> None:
    """AD-14: one runner, so one object can kill every group this process started."""
    runner = FakeProcessRunner()

    harness = build_harnesses(Settings(), runner)["local"]

    assert isinstance(harness, LocalHarness)
    assert harness.runner is runner


def test_local_is_a_name_the_harness_table_is_seeded_with(env: dict[str, str]) -> None:
    """A registry key with no seeded row would be a harness pre-flight can never enable."""
    assert "local" in db_seed.HARNESS_VERSION_SETTINGS
    assert "local" in HARNESS_NAMES


def test_the_registry_is_the_one_the_walker_is_handed(env: dict[str, str]) -> None:
    """So `harness: local` in a Template resolves inside the walker, not only in `main.py`."""
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.harnesses is not None
    assert set(ports.harnesses) == REGISTERED
    assert isinstance(ports.harnesses["local"], LocalHarness)


def test_test_mode_still_adds_the_fake_harness_and_changes_nothing_else(
    env: dict[str, str],
) -> None:
    real = build_harnesses(Settings(), FakeProcessRunner())

    built = build_harnesses(Settings(orch_test_mode=True), FakeProcessRunner())

    assert set(built) == set(real) | {FAKE_NAME}
    assert FAKE_NAME not in real


# ── the alias table, which is what the two revised equalities are about ──────


def test_the_static_table_is_keyed_the_way_the_registry_is(env: dict[str, str]) -> None:
    """What `ALIASES == {…}` exists to say. Every key is a registered harness — a builder for
    a name nothing dispatches to would never run."""
    assert set(ALIASES) <= set(build_harnesses(Settings(), FakeProcessRunner()))
    assert set(ALIASES) == {"claude", "local"}


def test_every_static_builder_takes_the_contract_and_nothing_else(env: dict[str, str]) -> None:
    """The property that decides which table a builder belongs in (AD-5): a builder needing a
    `Settings` could not be a module-level constant without reading one inside itself, which is
    why `codex` is bound by `alias_table` and `local` is a line here."""
    contract = {"LANGFUSE_BASE_URL": "http://langfuse:3000", "ORCH_RUN_ID": "run-1"}

    for builder in ALIASES.values():
        assert callable(builder)
    assert dict(local_aliases(contract)) == {
        "LANGFUSE_BASEURL": "http://langfuse:3000",
        "LANGFUSE_USER_ID": "run-1",
    }


def test_the_instance_table_binds_codex_on_top_of_the_static_one(env: dict[str, str]) -> None:
    table = alias_table(Settings())

    assert set(table) == REGISTERED
    assert table["claude"] is ALIASES["claude"]
    assert table["local"] is ALIASES["local"]


def test_a_local_attempt_gets_the_contract_and_the_plugins_two_names(
    env: dict[str, str],
) -> None:
    """The equality's whole point, over the real environment builder: without this, the
    Langfuse plugin sends generations keyed to no Run (AD-11)."""
    run = a_run()

    built = build_harness_env(Settings())(
        an_attempt(run, "local"),
        run=run,
        project_slug="acme",
        project_env={},
        log_content=False,
        story_id="7-3",
        traceparent=TRACEPARENT,
    )

    assert built["LANGFUSE_USER_ID"] == built["ORCH_RUN_ID"]
    assert built["LANGFUSE_BASEURL"] == built["LANGFUSE_BASE_URL"]
    assert built["ORCH_HARNESS"] == "local"
    # AD-5: no Claude alias and no Codex home reach a harness that declares neither
    assert "ANTHROPIC_AUTH_TOKEN" not in built
    assert "CODEX_HOME" not in built


def test_the_terminal_environment_for_local_exports_the_plugins_names_and_no_secret(
    env: dict[str, str],
) -> None:
    """FR-21, AD-5: the exports are the harness's own `HARNESS_ENV_ALIASES` by construction,
    and the line goes on a screen, so it may carry identifiers and nothing else."""
    settings = Settings()
    run = a_run()

    terminal = build_terminal_env(settings)(
        an_attempt(run, "local"),
        run=run,
        project_slug="acme",
        story_id="7-3",
        traceparent=TRACEPARENT,
    )

    assert set(dict(terminal.exports)) == {"LANGFUSE_BASEURL", "LANGFUSE_USER_ID"}
    rendered = str(terminal.identifiers) + str(terminal.exports)
    for secret in (
        settings.litellm_api_key,
        settings.litellm_spend_key,
        settings.langfuse_secret_key,
        settings.github_token,
    ):
        assert secret.get_secret_value() not in rendered


# ── FR-21: registered, and still no terminal — now for the adapter's reason ──


def test_a_parked_local_attempt_has_no_terminal_because_it_cannot_resume(
    env: dict[str, str],
) -> None:
    """`test_terminal_command.py`'s `local` row and `test_codex_registry.py`'s both still say
    `terminal: null`, and this is why they still hold now that the registry does hold the name:
    `_resumable_harness` asks `capabilities.resume`, which this adapter declares `False`."""
    settings = Settings()
    attempt = an_attempt(a_run(), "local", status="blocked", session_id=SESSION)
    run = a_run(id=attempt.run_id, status="needs_you", worktree_path="/work/acme/wt/feat-x")

    terminal = resume_command(
        TerminalPorts(
            env=build_terminal_env(settings),
            harnesses=build_harnesses(settings, FakeProcessRunner()),
        ),
        run,
        an_agent_row(attempt),
        attempt,
        project_slug="acme",
    )

    assert terminal is None
    assert build_harnesses(settings, FakeProcessRunner())["local"].capabilities.resume is False
