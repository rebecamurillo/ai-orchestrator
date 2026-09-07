"""What `env_for` puts in each name, not only which names it puts there (AD-5, AD-10, AD-11).

`test_harness_env_contract.py` proves the key set is the two scripts' own lists. That is the
half a script can check. The other half is the values: `ORCH_TAGS` is what LiteLLM's spend
log is later queried by, `ANTHROPIC_CUSTOM_HEADERS` is what carries the Langfuse session and
the Gateway end-user to every model call an attempt makes, and the content-logging pair is
what decides whether a prompt leaves the container at all. Each is asserted here.

Three rules are asserted by absence, because that is the only way they can be:

- no `GITHUB_TOKEN`, no `LITELLM_SPEND_KEY`, no `DATABASE_URL`, no `ORCHESTRATOR_*` (AD-5);
- no `OTEL_LOG_*` unless the Project asked for content logging;
- a Project variable that names a contract name does not become that name's value — the
  contract wins, so a Project cannot re-point its own attempts at another Run's identifiers.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.claude.adapter import claude_aliases
from orchestrator.infrastructure.harness.env import (
    BASE_NAMES,
    HARNESS_ENV_CONTRACT,
    TAG_POSITIONS,
    env_for,
)
from orchestrator.infrastructure.settings import Settings

PROJECT_SLUG = "acme"
STORY_ID = "5-1"
PROJECT_ENV = {"MY_FLAG": "on", "NPM_CONFIG_REGISTRY": "https://registry.example"}
#: The five header lines, in the order `scripts/harness/claude.sh` documents them.
HEADER_NAMES = (
    "langfuse_session_id",
    "langfuse_tags",
    "x-litellm-end-user-id",
    "x-litellm-session-id",
    "x-litellm-tags",
)


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


@pytest.fixture
def attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="running",
        harness="claude",
        model="claude-opus-5",
    )


@pytest.fixture
def run(attempt: Attempt) -> Run:
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


def build(  # noqa: PLR0913 — one keyword per `env_for` argument a test may vary
    attempt: Attempt,
    run: Run,
    settings: Settings,
    *,
    log_content: bool = False,
    project_env: dict[str, str] | None = None,
    story_id: str | None = STORY_ID,
    traceparent: str = "",
) -> dict[str, str]:
    return env_for(
        attempt,
        run=run,
        project_slug=PROJECT_SLUG,
        project_env=PROJECT_ENV if project_env is None else project_env,
        log_content=log_content,
        settings=settings,
        story_id=story_id,
        traceparent=traceparent,
        aliases=claude_aliases,
    )


# ── the identifiers and the tags ─────────────────────────────────────────────


def test_the_identifiers_name_the_run_the_attempt_the_story_and_the_project(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert result["ORCH_RUN_ID"] == str(run.id)
    assert result["ORCH_ATTEMPT_ID"] == str(attempt.id)
    assert result["ORCH_STORY_ID"] == STORY_ID
    assert result["ORCH_HARNESS"] == "claude"
    assert result["ORCH_PROJECT"] == PROJECT_SLUG


def test_the_tag_string_is_the_five_positions_in_the_documented_order(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert result["ORCH_TAGS"] == (
        f"run:{run.id},attempt:{attempt.id},story:{STORY_ID},harness:claude,project:{PROJECT_SLUG}"
    )


def test_the_langfuse_tags_are_the_same_five_as_a_json_array(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert json.loads(result["ORCH_LANGFUSE_TAGS"]) == result["ORCH_TAGS"].split(",")


def test_a_row_outside_a_story_frame_keeps_the_position_and_leaves_it_empty(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """`StepRun.story_id` is `None` on an `agent` row outside a story frame; the tag string
    still has to parse the same way, so the position stays and the value is empty."""
    result = build(attempt, run, settings, story_id=None)

    assert result["ORCH_STORY_ID"] == ""
    assert ",story:,harness:claude," in result["ORCH_TAGS"]


def test_the_traceparent_key_exists_and_is_empty_until_the_tracer_lands(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """5.2 supplies a value; the key is in the contract, so it exists from this story on."""
    assert build(attempt, run, settings)["TRACEPARENT"] == ""
    assert build(attempt, run, settings, traceparent="00-abc-def-01")["TRACEPARENT"] == (
        "00-abc-def-01"
    )


# ── the gateway, Langfuse and the base names ─────────────────────────────────


def test_the_gateway_and_langfuse_values_come_from_settings(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert result["LITELLM_BASE_URL"] == settings.litellm_base_url
    assert result["LITELLM_API_KEY"] == settings.litellm_api_key.get_secret_value()
    assert result["LANGFUSE_BASE_URL"] == settings.langfuse_base_url
    assert result["LANGFUSE_PUBLIC_KEY"] == settings.langfuse_public_key
    assert result["LANGFUSE_SECRET_KEY"] == settings.langfuse_secret_key.get_secret_value()
    assert result["LANGFUSE_ENVIRONMENT"] == settings.langfuse_environment


def test_home_is_the_agent_home_and_the_terminal_is_dumb(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """`backend-api/Dockerfile` makes `HOME == AGENT_HOME`, so the runner's own `HOME`
    agrees with this one; `TERM=dumb` is what keeps a harness from drawing a UI."""
    result = build(attempt, run, settings)

    assert result["HOME"] == str(settings.agent_home)
    assert result["TERM"] == "dumb"
    assert result["PATH"]
    assert result["LANG"]


# ── the claude aliases ───────────────────────────────────────────────────────


def test_the_anthropic_token_is_the_gateway_key_and_never_an_anthropic_one(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert result["ANTHROPIC_AUTH_TOKEN"] == settings.litellm_api_key.get_secret_value()
    assert "ANTHROPIC_API_KEY" not in result


def test_the_custom_headers_are_the_five_documented_lines_with_the_right_ids(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)
    lines = result["ANTHROPIC_CUSTOM_HEADERS"].split("\n")

    assert [line.split(": ", 1)[0] for line in lines] == list(HEADER_NAMES)
    headers = dict(line.split(": ", 1) for line in lines)
    assert headers["langfuse_session_id"] == str(run.id)
    assert headers["langfuse_tags"] == result["ORCH_LANGFUSE_TAGS"]
    assert headers["x-litellm-end-user-id"] == str(run.id)
    assert headers["x-litellm-session-id"] == str(attempt.id)
    assert headers["x-litellm-tags"] == result["ORCH_TAGS"]


# ── content logging ──────────────────────────────────────────────────────────


def test_content_logging_off_sets_the_switch_to_zero_and_adds_no_otel_names(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert result["ORCH_LOG_CONTENT"] == "0"
    assert "OTEL_LOG_USER_PROMPTS" not in result
    assert "OTEL_LOG_TOOL_CONTENT" not in result


def test_content_logging_on_sets_the_switch_and_both_otel_names(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings, log_content=True)

    assert result["ORCH_LOG_CONTENT"] == "1"
    assert result["OTEL_LOG_USER_PROMPTS"] == "1"
    assert result["OTEL_LOG_TOOL_CONTENT"] == "1"


# ── what is never there ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "forbidden",
    ["GITHUB_TOKEN", "LITELLM_SPEND_KEY", "DATABASE_URL", "ORCHESTRATOR_TOKEN"],
)
def test_a_credential_a_harness_never_receives_is_absent(
    attempt: Attempt, run: Run, settings: Settings, forbidden: str
) -> None:
    assert forbidden not in build(attempt, run, settings)


@pytest.mark.parametrize(
    "forbidden",
    ["GITHUB_TOKEN", "LITELLM_SPEND_KEY", "DATABASE_URL", "ORCHESTRATOR_SECRET_KEY"],
)
def test_a_project_variable_cannot_smuggle_a_forbidden_name_in(
    attempt: Attempt, run: Run, settings: Settings, forbidden: str
) -> None:
    """2.1 refuses these names at the Project; `env_for` refuses them again, because AD-5 is
    a property of the harness environment and not of one form's validation."""
    result = build(attempt, run, settings, project_env={forbidden: "leaked"})

    assert forbidden not in result


def test_no_orchestrator_name_reaches_a_harness(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    assert not [name for name in build(attempt, run, settings) if name.startswith("ORCHESTRATOR_")]


def test_a_project_variable_never_overrides_a_contract_name(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings, project_env={"ORCH_RUN_ID": "someone-elses-run"})

    assert result["ORCH_RUN_ID"] == str(run.id)


def test_the_project_variables_are_carried_through(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    result = build(attempt, run, settings)

    assert result["MY_FLAG"] == "on"
    assert result["NPM_CONFIG_REGISTRY"] == "https://registry.example"


def test_an_attempt_with_no_harness_recorded_still_renders_the_position(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """`Attempt.harness` is `str | None`; the tag string's five positions do not move."""
    result = build(attempt.model_copy(update={"harness": None}), run, settings)

    assert result["ORCH_HARNESS"] == ""
    assert ",harness:,project:" in result["ORCH_TAGS"]


def test_without_an_alias_builder_the_environment_is_the_contract_alone(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """`aliases` is the harness's own half; a caller that names no harness gets neither
    `ANTHROPIC_AUTH_TOKEN` nor any other native name."""
    result = env_for(
        attempt,
        run=run,
        project_slug=PROJECT_SLUG,
        project_env={},
        log_content=False,
        settings=settings,
    )

    assert set(result) == set(HARNESS_ENV_CONTRACT) | set(BASE_NAMES)


# ── the Project cannot reach past its own variables ──────────────────────────


@pytest.mark.parametrize("name", ["HOME", "PATH", "LANG", "TERM"])
def test_a_project_variable_never_overrides_a_base_name(
    attempt: Attempt, run: Run, settings: Settings, name: str
) -> None:
    """A Project that could set `PATH` could point the harness at a different binary, and
    one that could set `HOME` could point it at a different `~/.claude` — a config file
    this instance did not write. Neither is a Project's to decide."""
    result = build(attempt, run, settings, project_env={name: "/tmp/somewhere-else"})

    assert result[name] != "/tmp/somewhere-else"
    assert result["HOME"] == str(settings.agent_home)
    assert result["TERM"] == "dumb"


@pytest.mark.parametrize("name", ["OTEL_LOG_USER_PROMPTS", "OTEL_LOG_TOOL_CONTENT"])
def test_a_project_variable_cannot_turn_content_logging_on_by_itself(
    attempt: Attempt, run: Run, settings: Settings, name: str
) -> None:
    """AD-5 makes the content-logging switches the instance's, set from
    `project.log_prompt_content`. A Project variable that set one directly would send
    prompts to Langfuse while `ORCH_LOG_CONTENT` still said `0` — the one state that must
    not be reachable, because the switch and the record of the switch would disagree."""
    result = build(attempt, run, settings, project_env={name: "1"})

    assert name not in result
    assert result["ORCH_LOG_CONTENT"] == "0"


def test_the_instance_still_sets_both_switches_when_the_project_asked_for_them(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """The filter runs before the alias builder, so forbidding the name to a Project does
    not forbid it to the harness that the Project's own setting turned on."""
    result = build(
        attempt, run, settings, log_content=True, project_env={"OTEL_LOG_USER_PROMPTS": "0"}
    )

    assert result["ORCH_LOG_CONTENT"] == "1"
    assert result["OTEL_LOG_USER_PROMPTS"] == "1"
    assert result["OTEL_LOG_TOOL_CONTENT"] == "1"


def test_the_two_tag_renderings_are_built_from_one_list(
    attempt: Attempt, run: Run, settings: Settings
) -> None:
    """`ORCH_LANGFUSE_TAGS` is not the joined string split again: a value holding a comma
    would then be two items in one rendering and one in the other."""
    result = build(attempt.model_copy(update={"harness": "a,b"}), run, settings)

    assert json.loads(result["ORCH_LANGFUSE_TAGS"])[3] == "harness:a,b"
    assert len(json.loads(result["ORCH_LANGFUSE_TAGS"])) == len(TAG_POSITIONS)
