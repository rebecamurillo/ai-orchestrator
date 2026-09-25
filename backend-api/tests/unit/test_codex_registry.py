"""`codex` in the registry, and everything the loosened anchors stopped guaranteeing (AD-10).

Four frozen assertions used to pin the harness registry to the literal `["claude"]` — the list
of what Epic 5 shipped. Story 7.1 adds a second adapter, and the Operator authorised replacing
each literal with the *permanent* invariant instead (`set(registry) <= set(HARNESS_NAMES)`: every
registered name is a name the domain declares), specifically so that `local` landing in 7.3 costs
no further anchor edit. `<=` is weaker than `==`, so this module is where the exactness comes
back — and comes back stronger, because it also states the things the old literals never did.

What the four originals guaranteed and `<=` drops, restated here:

- `test_main_harness_registry.py` / `test_harness_registry.py` — the registry holds exactly the
  adapters landed *as of this story*, and each is the class it should be, on the runner it was
  handed, under a key the `harness` table also seeds.
- `test_dbos_startup_agent.py` — the walker's `StepPorts.harnesses` is that same registry, so a
  Template writing `harness: codex` resolves inside the walker and not only in a composition root.
- `test_fake_harness_registry.py` — test mode adds `fake` *beside* the real registry and changes
  nothing else about it.

And one thing none of them could state, because the second adapter did not exist: `codex` reaches
its own native name through `alias_table`, not through `ALIASES`, and the terminal command FR-21
prints for it is the adapter's own and carries no secret (AD-5).

**The exact-set assertions here are this story's own, and 7.3 revises them when `local` lands** —
that is the trade the ruling made: the epic's *frozen* files state an invariant that never needs
touching again, and the per-story exactness lives in per-story files like this one.
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
from orchestrator.infrastructure.harness import ClaudeHarness, CodexHarness
from orchestrator.infrastructure.harness.codex.adapter import CODEX_HOME
from orchestrator.infrastructure.harness.fake import NAME as FAKE_NAME
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

#: What the registry holds as of story 7.1. `local` is 7.3's and is deliberately absent: an
#: assertion that expected it would sit red between the two stories.
REGISTERED = {"claude", "codex", "local"}

NOW = datetime(2026, 9, 10, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("10.00"),
        created_at=NOW,
    )


def an_attempt(run: Run, harness: str | None) -> Attempt:
    return Attempt(
        id=new_id(), run_id=run.id, step_run_id=new_id(), n=1, status="running", harness=harness
    )


def sessions() -> object:
    def factory() -> object:  # pragma: no cover — nothing here opens a session
        raise AssertionError("no session is opened while the deps are built")

    return factory


# ── the registry holds exactly what this story landed ────────────────────────


def test_the_registry_holds_exactly_the_two_adapters_landed_so_far(env: dict[str, str]) -> None:
    """The exactness the four loosened anchors used to carry, restated for this story."""
    assert set(build_harnesses(Settings(), FakeProcessRunner())) == REGISTERED


def test_codex_is_registered_under_its_own_name(env: dict[str, str]) -> None:
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    assert isinstance(harnesses["codex"], CodexHarness)
    assert harnesses["codex"].name == "codex"


def test_every_registered_adapter_is_the_class_it_should_be(env: dict[str, str]) -> None:
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    assert isinstance(harnesses["claude"], ClaudeHarness)
    assert isinstance(harnesses["codex"], CodexHarness)


def test_every_registered_adapter_satisfies_the_port_under_its_own_key(
    env: dict[str, str],
) -> None:
    for name, harness in build_harnesses(Settings(), FakeProcessRunner()).items():
        assert isinstance(harness, HarnessPort), name
        assert harness.name == name, name


def test_codex_starts_its_processes_through_the_runner_the_registry_was_handed(
    env: dict[str, str],
) -> None:
    """AD-14: one `ProcessRunner`, so one object can kill every group this process started."""
    runner = FakeProcessRunner()

    harness = build_harnesses(Settings(), runner)["codex"]

    assert isinstance(harness, CodexHarness)
    assert harness.runner is runner


# ── the keys are names the rest of the system already knows ──────────────────


def test_every_registered_name_is_a_name_the_domain_declares(env: dict[str, str]) -> None:
    """The invariant the frozen files now state; asserted here too, so the exact set above and
    the loosened `<=` cannot disagree about which direction the containment runs."""
    assert set(build_harnesses(Settings(), FakeProcessRunner())) <= set(HARNESS_NAMES)


def test_codex_is_a_name_the_harness_table_is_seeded_with(env: dict[str, str]) -> None:
    """A registry key with no seeded row would be a harness pre-flight can never enable."""
    assert "codex" in db_seed.HARNESS_VERSION_SETTINGS
    assert "codex" in HARNESS_NAMES


def test_the_registry_is_the_one_the_walker_is_handed(env: dict[str, str]) -> None:
    """`test_dbos_startup_agent.py` now says `<=`; this says the walker's is the same mapping,
    so `harness: codex` in a Template resolves inside the walker and not only in `main.py`."""
    ports = walker_deps(Settings(), sessions(), FakeGit()).step_ports

    assert ports.harnesses is not None
    assert set(ports.harnesses) == REGISTERED
    assert isinstance(ports.harnesses["codex"], CodexHarness)


# ── test mode adds `fake` beside the real registry and nothing else ──────────


def test_test_mode_adds_the_fake_harness_and_changes_nothing_else(env: dict[str, str]) -> None:
    real = build_harnesses(Settings(), FakeProcessRunner())

    built = build_harnesses(Settings(orch_test_mode=True), FakeProcessRunner())

    assert set(built) == set(real) | {FAKE_NAME}
    assert FAKE_NAME not in real


def test_the_shipped_default_registers_no_fake_harness_beside_codex(env: dict[str, str]) -> None:
    assert FAKE_NAME not in build_harnesses(Settings(), FakeProcessRunner())


# ── codex reaches its native name through the instance table, not `ALIASES` ──


def test_the_static_alias_table_stays_claude_only(env: dict[str, str]) -> None:
    """`codex_aliases` is a factory over `AGENT_HOME`, so it could never be a line here."""
    assert "codex" not in ALIASES


def test_the_instance_alias_table_binds_codex_on_top_of_the_static_one(
    env: dict[str, str],
) -> None:
    table = alias_table(Settings())

    assert set(table) == {"claude", "codex", "local"}
    assert table["claude"] is ALIASES["claude"]


def test_a_codex_attempt_gets_the_contract_and_its_own_home(env: dict[str, str]) -> None:
    run = a_run()

    built = build_harness_env(Settings())(
        an_attempt(run, "codex"),
        run=run,
        project_slug="acme",
        project_env={},
        log_content=False,
        story_id="7-1",
        traceparent=TRACEPARENT,
    )

    assert built[CODEX_HOME] == f"{Settings().agent_home}/.codex"
    assert built["ORCH_HARNESS"] == "codex"
    assert built["TRACEPARENT"] == TRACEPARENT
    # AD-5: Codex reads the contract names directly, so it has no credential alias at all
    assert "ANTHROPIC_AUTH_TOKEN" not in built


def test_the_terminal_environment_for_codex_exports_its_home_and_no_secret(
    env: dict[str, str],
) -> None:
    """FR-21, AD-5: the line goes on a screen, so it may carry identifiers and nothing else."""
    settings = Settings()
    run = a_run()

    terminal = build_terminal_env(settings)(
        an_attempt(run, "codex"),
        run=run,
        project_slug="acme",
        story_id="7-1",
        traceparent=TRACEPARENT,
    )

    assert dict(terminal.exports) == {CODEX_HOME: f"{settings.agent_home}/.codex"}
    rendered = str(terminal.identifiers) + str(terminal.exports)
    for secret in (
        settings.litellm_api_key,
        settings.litellm_spend_key,
        settings.langfuse_secret_key,
        settings.github_token,
    ):
        assert secret.get_secret_value() not in rendered


# ── FR-21: codex now HAS a terminal, where the registry used to hold none ────


#: The session a parked `codex` attempt recorded, as `thread.started` named it.
CODEX_SESSION = "0199c4a1-6d2e-7f31-8a44-51b6c7d8e9f0"
WORKTREE = "/work/acme/orchestrator/wt/epics-1"


def a_parked_run(attempt: Attempt) -> Run:
    return Run(
        id=attempt.run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="needs_you",
        budget_usd=Decimal("40"),
        created_at=NOW,
        worktree_path=WORKTREE,
        trace_id=TRACEPARENT,
        park_kind="blocked",
        park_path="epics[0].stories[0].build",
        park_reason="intent gap",
    )


def a_parked_attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="blocked",
        harness="codex",
        model="gpt-5-codex",
        session_id=CODEX_SESSION,
        started_at=NOW,
    )


def an_agent_row(attempt: Attempt) -> StepRun:
    return StepRun(
        id=attempt.step_run_id,
        run_id=attempt.run_id,
        seq=1,
        path="epics[0].stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="blocked",
        story_id="7-1",
    )


def a_terminal(settings: Settings) -> object:
    attempt = a_parked_attempt()
    return resume_command(
        TerminalPorts(
            env=build_terminal_env(settings),
            harnesses=build_harnesses(settings, FakeProcessRunner()),
        ),
        a_parked_run(attempt),
        an_agent_row(attempt),
        attempt,
        project_slug="acme",
    )


def test_a_parked_codex_attempt_now_has_a_terminal_command(env: dict[str, str]) -> None:
    """The other half of the row removed from `test_terminal_command.py`'s not-yet-registered
    list: `codex` used to answer `None` because nothing was registered under the name, and the
    replacement claim is that it answers the adapter's own line."""
    terminal = a_terminal(Settings())

    assert terminal is not None
    assert f"codex resume {CODEX_SESSION}" in terminal.command  # type: ignore[attr-defined]
    assert f"cd {WORKTREE}" in terminal.command  # type: ignore[attr-defined]


def test_the_codex_terminal_command_carries_no_secret_value(env: dict[str, str]) -> None:
    """AD-5: a second adapter on screen is a second chance to leak, so it is asserted twice —
    once against the environment builder above, and once against the finished line."""
    settings = Settings()

    terminal = a_terminal(settings)

    assert terminal is not None
    for secret in (
        settings.litellm_api_key,
        settings.litellm_spend_key,
        settings.langfuse_secret_key,
        settings.github_token,
        settings.orchestrator_token,
    ):
        assert secret.get_secret_value() not in terminal.command  # type: ignore[attr-defined]
    assert "GITHUB_TOKEN" not in terminal.command  # type: ignore[attr-defined]


def test_a_parked_local_attempt_now_has_a_terminal_command(env: dict[str, str]) -> None:
    """`local` gains resume in story 3 (2026-09-25 declared behaviour change): the adapter
    now declares `capabilities.resume = True` and `resume_command` returns the `--session` line,
    so `resume_command` here returns a non-None Terminal."""
    settings = Settings()
    attempt = a_parked_attempt().model_copy(update={"harness": "local"})

    terminal = resume_command(
        TerminalPorts(
            env=build_terminal_env(settings),
            harnesses=build_harnesses(settings, FakeProcessRunner()),
        ),
        a_parked_run(attempt),
        an_agent_row(attempt),
        attempt,
        project_slug="acme",
    )

    assert terminal is not None
    assert "--session" in terminal.command  # type: ignore[attr-defined]
    assert CODEX_SESSION in terminal.command  # type: ignore[attr-defined]
