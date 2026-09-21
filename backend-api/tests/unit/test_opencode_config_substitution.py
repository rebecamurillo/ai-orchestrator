"""The config `opencode.sh configure` writes, substituted with the values `env_for` builds.

**This is the test the defect of 2026-09-20 got past, and the reason it is shaped this way.**
OpenCode expands the `{env:NAME}` references in `opencode.json` *textually*, before it parses
the file as JSON(C). `ORCH_LANGFUSE_TAGS` is a JSON array, so its quotes terminated the string
the reference sat in, and the CLI answered every dispatch with `not valid JSON(C)` and exit 1
in about a second. Every other gate was green throughout: the script's text was valid, the
file on disk was valid JSON, the adapter's argv was right, the version was pinned, and the
Gateway was reachable. Nothing checked the one thing that was broken — the file *after*
substitution — because that value only exists where the script and the Python builder meet.

So this module puts the two halves together and parses the result. It is the only unit test
that runs a harness script rather than reading it: `test_harness_env_contract.py::bash_array`
deliberately does not invoke a shell, because its question is "what does the declaration a
reader reads say". The question here is different — "does the file this script writes survive
the values this builder produces" — and text cannot answer it.

It drives every `{env:...}` reference the file holds, not only the tag list, so a variable
added later whose value carries a quote fails here rather than in production.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import env_for
from orchestrator.infrastructure.harness.opencode.adapter import (
    LANGFUSE_TAGS_ALIAS,
    LANGFUSE_TAGS_SOURCE,
    local_aliases,
)
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT

OPENCODE_SCRIPT = REPO_ROOT / "scripts" / "harness" / "opencode.sh"

#: `{env:NAME}` as the config file writes it, and as OpenCode finds it.
REFERENCE = re.compile(r"\{env:([A-Za-z_][A-Za-z0-9_]*)\}")

#: The header whose value is a JSON array — the one this defect was about (AD-11).
TAGS_HEADER = "langfuse_tags"

TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
STORY_ID = "7-3"
PROJECT_SLUG = "lesmartines"


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


def an_attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="running",
        harness="local",
        model="local-coder",
    )


def a_run(attempt: Attempt) -> Run:
    return Run(
        id=attempt.run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("40"),
        created_at=datetime(2026, 9, 20, tzinfo=UTC),
    )


def environment(settings: Settings) -> dict[str, str]:
    """Exactly what a `local` attempt's process receives, values and all (AD-10)."""
    attempt = an_attempt()
    return dict(
        env_for(
            attempt,
            run=a_run(attempt),
            project_slug=PROJECT_SLUG,
            project_env={},
            log_content=False,
            settings=settings,
            story_id=STORY_ID,
            traceparent=TRACEPARENT,
            aliases=local_aliases,
        )
    )


def configured(settings: Settings, home: Path) -> str:
    """The text `opencode.sh configure` writes, for an instance with both services on."""
    home.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["/bin/bash", str(OPENCODE_SCRIPT), "configure"],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin",
            "AGENT_HOME": str(home),
            "LITELLM_BASE_URL": settings.litellm_base_url,
            "LANGFUSE_BASE_URL": settings.langfuse_base_url,
            "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
            "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key.get_secret_value(),
            "LOCAL_MODELS": ",".join(settings.local_models),
        },
    )
    assert result.returncode == 0, result.stderr
    return (home / ".config" / "opencode" / "opencode.json").read_text()


def substituted(config: str, env: dict[str, str]) -> str:
    """The file as OpenCode reads it: every reference replaced by its value, then parsed.

    `re.sub` with a plain function rather than a replacement string, because a value holding
    a backslash would otherwise be read as a group reference — which is the same class of bug
    as the one this module exists for.
    """
    return REFERENCE.sub(lambda m: env[m.group(1)], config)


# ── the file the script writes is valid before anything is substituted ───────


def test_the_written_file_is_valid_json_on_its_own(settings: Settings, tmp_path: Path) -> None:
    """The half that was always true, and never the half that mattered."""
    assert json.loads(configured(settings, tmp_path / "agent"))


def test_every_reference_in_the_file_names_a_variable_the_attempt_receives(
    settings: Settings, tmp_path: Path
) -> None:
    """A reference to a name nothing exports resolves to nothing, silently: the header would
    be sent empty and the attribution would just be missing (AD-11)."""
    config = configured(settings, tmp_path / "agent")
    referenced = set(REFERENCE.findall(config))

    assert referenced
    assert referenced <= set(environment(settings))


# ── the file after substitution, which is what OpenCode actually parses ──────


def test_the_file_still_parses_once_the_real_values_are_substituted_in(
    settings: Settings, tmp_path: Path
) -> None:
    """The defect of 2026-09-20, asserted directly. Every reference is driven, not only the
    tag list, so the next value that carries a quote fails here."""
    config = configured(settings, tmp_path / "agent")

    assert json.loads(substituted(config, environment(settings)))


def test_the_tags_header_arrives_as_the_json_array_litellm_reads(
    settings: Settings, tmp_path: Path
) -> None:
    """Escaping is only correct if it round-trips: LiteLLM turns this header into Langfuse
    trace tags by parsing it, so `\\"` in the file must become `"` in the header value and
    the header value must parse back to the five tags `env_for` built (AD-11, FR-26)."""
    env = environment(settings)
    parsed = json.loads(substituted(configured(settings, tmp_path / "agent"), env))
    header = parsed["provider"]["litellm"]["options"]["headers"][TAGS_HEADER]

    assert header == env[LANGFUSE_TAGS_SOURCE]
    assert json.loads(header) == json.loads(env[LANGFUSE_TAGS_SOURCE])
    assert [tag.split(":", 1)[0] for tag in json.loads(header)] == [
        "run",
        "attempt",
        "story",
        "harness",
        "project",
    ]


def test_the_gateway_key_reaches_the_provider_by_name_and_arrives_by_value(
    settings: Settings, tmp_path: Path
) -> None:
    """AD-10 and AD-5 together: the file on disk holds the *name*, and the process OpenCode
    runs in is where the value comes from."""
    config = configured(settings, tmp_path / "agent")
    parsed = json.loads(substituted(config, environment(settings)))

    assert "{env:LITELLM_API_KEY}" in config
    assert settings.litellm_api_key.get_secret_value() not in config
    assert (
        parsed["provider"]["litellm"]["options"]["apiKey"]
        == settings.litellm_api_key.get_secret_value()
    )


# ── the guard against the guard ──────────────────────────────────────────────


def test_the_raw_contract_value_would_still_break_the_file(
    settings: Settings, tmp_path: Path
) -> None:
    """Proves these assertions can fail. Substituting `ORCH_LANGFUSE_TAGS` where the escaped
    alias belongs reproduces the original defect exactly — which is what the shipped config
    did until `OPENCODE_LANGFUSE_TAGS` existed."""
    env = environment(settings)
    raw = {**env, LANGFUSE_TAGS_ALIAS: env[LANGFUSE_TAGS_SOURCE]}

    with pytest.raises(json.JSONDecodeError):
        json.loads(substituted(configured(settings, tmp_path / "agent"), raw))
