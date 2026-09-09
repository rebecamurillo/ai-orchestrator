"""FR-21's resume command: what it says, and — at length — what it cannot say (AD-5).

The command is the one string in this system that is built from an attempt's environment and
then *printed on a screen*. AD-5 says a secret value never appears on screen, in the read
model, in a log, in a fixture or in the OpenAPI contract, so the interesting assertions here
are absences, and they are made three ways rather than one:

1. **By construction.** `infrastructure/harness/env.py::identifiers` and `terminal_contract`
   take no `Settings` parameter at all, and `application/use_cases/terminal.py` imports
   nothing that could reach one. A builder that was never handed a credential cannot leak
   one, and `test_the_builders_take_no_settings_at_all` pins that signature so a later story
   cannot quietly add the argument back.
2. **By substring.** Every secret setting is monkeypatched to a value that occurs nowhere
   else in this repository, `Settings()` is built from those, and the finished command is
   searched for each of them. A sentinel rather than `.env.example`'s own `sk-change-me`,
   because that placeholder is shared between four variables and a match would say nothing.
3. **By name.** Every credential the command needs is present as the shell reference
   `$NAME`, which is what makes the absence of the value a design rather than an omission —
   the container expands it when the Operator pastes the line.

`GITHUB_TOKEN` is asserted absent in both forms — value *and* name — because AD-5 keeps it
out of a harness process entirely, so unlike the Gateway key it must not even be referenced.
"""

from __future__ import annotations

import inspect
import json
import shlex
import subprocess
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.terminal import (
    SESSION_LIFETIME_DAYS,
    TerminalPorts,
    _escaped,
    _single_quoted,
    resume_command,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.env import (
    HARNESS_ENV_CONTRACT,
    IDENTIFIER_NAMES,
    identifiers,
    terminal_contract,
)
from orchestrator.infrastructure.harness.registry import build_harnesses, build_terminal_env
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

PROJECT_SLUG = "acme"
STORY_ID = "5-1"
SESSION = "1f0a0d3c-8b17-4a9e-9c2b-2d4e6f8a0b1c"
WORKTREE = "/work/acme/orchestrator/wt/epics-1"
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
STARTED_AT = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
#: What `scripts/harness/claude.sh` documents and `SESSION_LIFETIME_DAYS` states.
CLAUDE_SESSION_DAYS = 30
#: The single-quoted script is opened and closed once, so a command that carries it holds at
#: least this many `'` characters.
SCRIPT_QUOTES = 2

#: The credential settings, each given a value that occurs nowhere else in this repository.
#: `ORCHESTRATOR_SECRET_KEY` gets a real Fernet key: `Settings` itself does not validate it,
#: but a sentinel that is not base64 would be a different kind of test failure later.
#: What the container's own environment holds for `LITELLM_API_KEY` when the pasted line
#: runs — the value the command must reference and must never contain.
GATEWAY_KEY = "SENTINEL-litellm-virtual-key-a17b"

#: Written as names so no line below has to be read through three levels of escaping.
BACKSLASH = chr(92)
QUOTE = chr(39)

SECRETS = {
    "ORCHESTRATOR_TOKEN": "SENTINEL-orchestrator-token-3f7a",
    "ORCHESTRATOR_SECRET_KEY": "U0VOVElORUwtZmVybmV0LWtleS0wMDAwMDAwMDAwMDAwMDA9",
    "GITHUB_TOKEN": "SENTINEL-github-token-91cd",
    "LITELLM_API_KEY": GATEWAY_KEY,
    "LITELLM_SPEND_KEY": "SENTINEL-litellm-spend-key-c204",
    "LANGFUSE_SECRET_KEY": "SENTINEL-langfuse-secret-key-8e33",
    "DATABASE_URL": "postgresql+psycopg://SENTINEL-db-user:SENTINEL-db-password@db/orchestrator",
}


@pytest.fixture
def settings(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name, value in SECRETS.items():
        monkeypatch.setenv(name, value)
    return Settings()


def an_attempt(harness: str = "claude", **over: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": 1,
        "status": "blocked",
        "harness": harness,
        "model": "claude-opus-5",
        "session_id": SESSION,
        "started_at": STARTED_AT,
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


def a_run(attempt: Attempt, **over: object) -> Run:
    fields: dict[str, object] = {
        "id": attempt.run_id,
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("40"),
        "created_at": datetime(2026, 9, 7, tzinfo=UTC),
        "worktree_path": WORKTREE,
        "trace_id": TRACEPARENT,
        "park_kind": "blocked",
        "park_path": "epics[0].stories[0].build",
        "park_reason": "intent gap",
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(attempt: Attempt, kind: str = "agent") -> StepRun:
    return StepRun(
        id=attempt.step_run_id,
        run_id=attempt.run_id,
        seq=1,
        path="epics[0].stories[0].build",
        label="build",
        kind=kind,
        gate="liveness",
        status="blocked",
        story_id=STORY_ID,
    )


def ports(settings: Settings) -> TerminalPorts:
    """The real registry and the real alias table — nothing about this is a double, because
    the whole claim is about what the *production* wiring produces."""
    return TerminalPorts(
        env=build_terminal_env(settings),
        harnesses=build_harnesses(settings, FakeProcessRunner()),
    )


def build(settings: Settings, *, harness: str = "claude", **run_over: object) -> str:
    attempt = an_attempt(harness)
    run = a_run(attempt, **run_over)
    terminal = resume_command(
        ports(settings), run, a_row(attempt), attempt, project_slug=PROJECT_SLUG
    )
    assert terminal is not None
    return terminal.command


# ── 1. by construction ───────────────────────────────────────────────────────


@pytest.mark.parametrize("builder", [identifiers, terminal_contract])
def test_the_builders_take_no_settings_at_all(builder: object) -> None:
    """The AD-5 argument in one assertion: no `Settings`, no `SecretStr`, no credential."""
    parameters = inspect.signature(builder).parameters  # type: ignore[arg-type]

    assert "settings" not in parameters
    assert [str(p.annotation) for p in parameters.values() if "Settings" in str(p.annotation)] == []


def test_only_the_eight_identifiers_carry_a_value_and_the_rest_are_references() -> None:
    attempt = an_attempt()
    contract = terminal_contract(
        attempt,
        run=a_run(attempt),
        project_slug=PROJECT_SLUG,
        story_id=STORY_ID,
        traceparent=TRACEPARENT,
    )

    assert set(contract) == set(HARNESS_ENV_CONTRACT)
    for name in HARNESS_ENV_CONTRACT:
        if name in IDENTIFIER_NAMES:
            assert contract[name] != f"${name}"
        else:
            assert contract[name] == f"${name}"


def test_the_identifier_names_are_the_ids_and_nothing_configured() -> None:
    """Pinned as a set rather than left to `[:8]`: a name inserted into the contract before
    `LITELLM_BASE_URL` would silently join the list a command may print."""
    assert set(IDENTIFIER_NAMES) == {
        "ORCH_RUN_ID",
        "ORCH_ATTEMPT_ID",
        "ORCH_STORY_ID",
        "ORCH_HARNESS",
        "ORCH_PROJECT",
        "ORCH_TAGS",
        "ORCH_LANGFUSE_TAGS",
        "TRACEPARENT",
    }


# ── 2. by substring: no secret value reaches the command ─────────────────────


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_no_secret_value_occurs_anywhere_in_the_command(name: str, settings: Settings) -> None:
    assert SECRETS[name] not in build(settings)


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_no_secret_value_occurs_in_the_subscription_modes_command(
    name: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other alias table (`CLAUDE_SUBSCRIPTION_AUTH=true`) moves the Gateway key into a
    header, which is exactly where a value would hide if the reference trick had a hole."""
    for secret, value in SECRETS.items():
        monkeypatch.setenv(secret, value)
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")

    command = build(Settings())

    assert SECRETS[name] not in command
    assert "x-litellm-api-key: Bearer $LITELLM_API_KEY" in command


def test_the_command_names_no_github_token_at_all(settings: Settings) -> None:
    """AD-5 keeps it out of every harness environment, so unlike the Gateway key it must not
    even be referenced — the harness has no use for a name it may not receive."""
    assert "GITHUB_TOKEN" not in build(settings)


# ── 3. by name: the credentials are referenced, and the container resolves them ──


def test_the_gateway_key_travels_as_a_shell_reference_inside_a_single_quoted_script(
    settings: Settings,
) -> None:
    command = build(settings)

    assert 'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"' in command
    # single-quoted, so the Operator's own shell leaves `$LITELLM_API_KEY` alone and the
    # container's shell is what expands it — the whole mechanism, in one character
    assert command.count("'") >= SCRIPT_QUOTES
    assert "sh -c '" in command


def test_the_exports_are_the_harnesss_own_alias_list(settings: Settings) -> None:
    """`scripts/harness/claude.sh` declares `HARNESS_ENV_ALIASES=(ANTHROPIC_AUTH_TOKEN=…
    ANTHROPIC_CUSTOM_HEADERS=derived)`, and this command exports exactly those two — because
    it calls the same `AliasBuilder` `test_harness_env_contract.py` holds against that array."""
    command = build(settings)

    assert "export ANTHROPIC_AUTH_TOKEN=" in command
    assert "ANTHROPIC_CUSTOM_HEADERS=" in command
    assert "OTEL_LOG_USER_PROMPTS" not in command
    assert "OTEL_LOG_TOOL_CONTENT" not in command


# ── the command a shell actually reads ───────────────────────────────────────


def _inner_script(command: str) -> str:
    """What `sh -c` is handed, as the Operator's own shell would split it."""
    return shlex.split(command)[-1]


def _exported(command: str, key: str) -> str:
    """What the *inner* shell ends up with for `key` — the command actually run, in `sh`.

    A round trip through two real shells rather than a string assertion, because the bug this
    guards against is invisible to one: `ANTHROPIC_CUSTOM_HEADERS` carries `ORCH_LANGFUSE_TAGS`,
    a JSON array, and an unescaped `"` inside it closes the double-quoted export a character
    early. The command still *parses*; the header just quietly stops being JSON, and AD-11's
    attribution is wrong for every Gateway call made from the terminal.
    """
    script = _inner_script(command)
    head = script.split("; cd ", 1)[0]
    probe = subprocess.run(
        ["/bin/sh", "-c", f'{head}; printf "%s" "${key}"'],
        capture_output=True,
        text=True,
        check=True,
        env={"LITELLM_API_KEY": GATEWAY_KEY, "PATH": "/usr/bin:/bin"},
    )
    return probe.stdout


def test_the_operators_own_shell_reads_the_command_as_one_exec_and_one_script(
    settings: Settings,
) -> None:
    command = build(settings)

    argv = shlex.split(command)

    assert argv[:3] == ["docker", "compose", "exec"]
    assert argv[-3:-1] == ["sh", "-c"]
    assert argv[-4] == "backend-api"


def test_the_container_expands_the_gateway_key_from_its_own_environment(
    settings: Settings,
) -> None:
    """The mechanism, end to end: the value is nowhere in the string, and the container puts
    it in `ANTHROPIC_AUTH_TOKEN` when the line runs."""
    command = build(settings)

    assert GATEWAY_KEY not in command
    assert _exported(command, "ANTHROPIC_AUTH_TOKEN") == GATEWAY_KEY


def test_the_langfuse_tag_header_is_still_json_after_two_shells(settings: Settings) -> None:
    """The regression this test was written for. Asserted by parsing, not by eye: a header
    that is not JSON is a header Langfuse drops, and AD-11's attribution with it."""
    attempt = an_attempt()
    run = a_run(attempt)
    terminal = resume_command(
        ports(settings), run, a_row(attempt), attempt, project_slug=PROJECT_SLUG
    )
    assert terminal is not None

    headers = dict(
        line.split(": ", 1)
        for line in _exported(terminal.command, "ANTHROPIC_CUSTOM_HEADERS").splitlines()
    )

    assert json.loads(headers["langfuse_tags"]) == [
        f"run:{run.id}",
        f"attempt:{attempt.id}",
        f"story:{STORY_ID}",
        "harness:claude",
        f"project:{PROJECT_SLUG}",
    ]
    assert headers["langfuse_session_id"] == str(run.id)
    assert headers["x-litellm-session-id"] == str(attempt.id)


def test_the_five_attribution_headers_survive_the_round_trip(settings: Settings) -> None:
    """AD-11 pins five, and the brief's own last rule is that a Gateway call made from the
    terminal lands its spend on the attempt — which is these headers and nothing else."""
    exported = _exported(build(settings), "ANTHROPIC_CUSTOM_HEADERS")

    names = [line.split(":", 1)[0] for line in exported.splitlines()]
    assert names == [
        "langfuse_session_id",
        "langfuse_tags",
        "x-litellm-end-user-id",
        "x-litellm-session-id",
        "x-litellm-tags",
    ]


def test_a_value_carrying_a_shell_metacharacter_is_escaped_not_executed() -> None:
    """A backtick or a quote in an identifier must reach the harness as text. None can today
    — a slug is `[a-z0-9-]` and the rest are ids — so this drives the escaping directly."""
    assert _escaped(r'a"b') == r"a\"b"
    assert _escaped("a`b") == "a\\`b"
    assert _escaped("a" + BACKSLASH + "b") == "a" + BACKSLASH * 2 + "b"
    # `$` is left alone on purpose: it is the reference the container resolves
    assert _escaped("$LITELLM_API_KEY") == "$LITELLM_API_KEY"


def test_a_single_quote_in_the_script_would_not_break_the_outer_quoting() -> None:
    """Nothing produces one today; the escape is written so that the day something does, the
    command is still one argument rather than a broken paste."""
    quoted = _single_quoted("cd /a" + QUOTE + "b && claude")

    assert quoted == "cd /a" + QUOTE + BACKSLASH + QUOTE + QUOTE + "b && claude"
    assert shlex.split(f"sh -c {QUOTE}{quoted}{QUOTE}")[-1] == "cd /a" + QUOTE + "b && claude"


# ── the command itself ───────────────────────────────────────────────────────


def test_the_command_carries_the_eight_identifier_flags(settings: Settings) -> None:
    attempt = an_attempt()
    run = a_run(attempt)
    terminal = resume_command(
        ports(settings), run, a_row(attempt), attempt, project_slug=PROJECT_SLUG
    )
    assert terminal is not None

    assert terminal.command.count(" -e ") == len(IDENTIFIER_NAMES)
    assert f"-e ORCH_RUN_ID={run.id}" in terminal.command
    assert f"-e ORCH_ATTEMPT_ID={attempt.id}" in terminal.command
    assert f"-e ORCH_STORY_ID={STORY_ID}" in terminal.command
    assert "-e ORCH_HARNESS=claude" in terminal.command
    assert f"-e ORCH_PROJECT={PROJECT_SLUG}" in terminal.command
    assert f"-e TRACEPARENT={TRACEPARENT}" in terminal.command
    assert "-e ORCH_LANGFUSE_TAGS='[" in terminal.command


def test_the_command_execs_the_backend_container_and_resumes_the_session(
    settings: Settings,
) -> None:
    command = build(settings)

    assert command.startswith("docker compose exec -e ORCH_RUN_ID=")
    assert " backend-api sh -c '" in command
    assert command.endswith(f"cd {WORKTREE} && claude --resume {SESSION}'")


def test_a_claude_session_lasts_thirty_days_from_the_attempts_own_start(
    settings: Settings,
) -> None:
    attempt = an_attempt()
    terminal = resume_command(
        ports(settings), a_run(attempt), a_row(attempt), attempt, project_slug=PROJECT_SLUG
    )
    assert terminal is not None

    assert SESSION_LIFETIME_DAYS["claude"] == CLAUDE_SESSION_DAYS
    assert terminal.session_lifetime_ends_at == STARTED_AT + timedelta(days=CLAUDE_SESSION_DAYS)


def test_a_harness_that_states_no_lifetime_answers_null(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `fake` harness resumes but names no session lifetime — the brief's "null for
    others", and the shape Epic 7's `codex` arrives in until it states one."""
    monkeypatch.setenv("ORCH_TEST_MODE", "true")
    settings = Settings()
    attempt = an_attempt("fake")

    terminal = resume_command(
        ports(settings), a_run(attempt), a_row(attempt), attempt, project_slug=PROJECT_SLUG
    )

    assert terminal is not None
    assert terminal.session_lifetime_ends_at is None


def test_in_progress_is_the_runs_own_terminal_session_flag(settings: Settings) -> None:
    attempt = an_attempt()
    row = a_row(attempt)

    open_session = resume_command(
        ports(settings),
        a_run(attempt, terminal_session=True),
        row,
        attempt,
        project_slug=PROJECT_SLUG,
    )
    closed = resume_command(
        ports(settings), a_run(attempt), row, attempt, project_slug=PROJECT_SLUG
    )

    assert open_session is not None and open_session.in_progress is True
    assert closed is not None and closed.in_progress is False


# ── the five `None` cases ────────────────────────────────────────────────────


def test_a_park_row_that_is_not_an_agent_row_has_no_terminal(settings: Settings) -> None:
    attempt = an_attempt()

    assert (
        resume_command(
            ports(settings),
            a_run(attempt),
            a_row(attempt, kind="shell"),
            attempt,
            project_slug=PROJECT_SLUG,
        )
        is None
    )


def test_a_run_with_no_park_row_has_no_terminal(settings: Settings) -> None:
    attempt = an_attempt()

    assert (
        resume_command(ports(settings), a_run(attempt), None, attempt, project_slug=PROJECT_SLUG)
        is None
    )


def test_a_row_that_never_ran_an_attempt_has_no_terminal(settings: Settings) -> None:
    attempt = an_attempt()

    assert (
        resume_command(
            ports(settings), a_run(attempt), a_row(attempt), None, project_slug=PROJECT_SLUG
        )
        is None
    )


def test_an_attempt_with_no_session_id_has_no_terminal(settings: Settings) -> None:
    attempt = an_attempt(session_id=None)

    assert (
        resume_command(
            ports(settings), a_run(attempt), a_row(attempt), attempt, project_slug=PROJECT_SLUG
        )
        is None
    )


def test_a_run_with_no_worktree_has_no_terminal(settings: Settings) -> None:
    attempt = an_attempt()

    assert (
        resume_command(
            ports(settings),
            a_run(attempt, worktree_path=None),
            a_row(attempt),
            attempt,
            project_slug=PROJECT_SLUG,
        )
        is None
    )


@pytest.mark.parametrize("harness", ["local", "codex", ""])
def test_a_harness_the_registry_does_not_hold_has_no_terminal(
    harness: str, settings: Settings
) -> None:
    """Epic 7's harnesses, and a row that recorded none at all: `local` is the brief's own
    example, and the answer is `terminal: null` rather than a command for a CLI that is not
    installed."""
    attempt = an_attempt(harness)

    assert (
        resume_command(
            ports(settings), a_run(attempt), a_row(attempt), attempt, project_slug=PROJECT_SLUG
        )
        is None
    )


def test_a_harness_that_cannot_resume_has_no_terminal(settings: Settings) -> None:
    """The capability is asked, never assumed (`domain/ports/harness.py`)."""

    class CannotResume:
        name = "claude"
        capabilities = type("Caps", (), {"resume": False})()

        def resume_command(self, cwd: str, session_id: str) -> str:  # pragma: no cover
            raise AssertionError("a harness that cannot resume is never asked for a command")

    attempt = an_attempt()
    no_resume = TerminalPorts(
        env=build_terminal_env(settings),
        harnesses={"claude": CannotResume()},  # type: ignore[dict-item]
    )

    assert (
        resume_command(no_resume, a_run(attempt), a_row(attempt), attempt, project_slug="acme")
        is None
    )
