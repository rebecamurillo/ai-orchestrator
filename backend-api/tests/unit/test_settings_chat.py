"""`CHAT_POLL_SECONDS` and `CHAT_REMINDER_HOURS` (story 3-3, AD-20).

The poll period must divide a minute evenly into a six-field cron (`*/{s} * * * * *`), so
start-up refuses anything but 10, 12, 15, 20 or 30. Blank is the default, as for every
defaulted setting. Both lines are in both env contracts, uncommented.
"""

from __future__ import annotations

import pytest
from check_env_contract import DEFAULT_DEPLOY_ENV_EXAMPLE, parse_env_example
from pydantic import ValidationError

from orchestrator.infrastructure.settings import CHAT_POLL_PERIODS, Settings


def build(env: dict[str, str], monkeypatch: pytest.MonkeyPatch, **extra: str) -> Settings:
    for name, value in {**env, **extra}.items():
        monkeypatch.setenv(name, value)
    return Settings()  # type: ignore[call-arg]


def test_the_contract_polls_every_thirty_seconds_and_reminds_every_four_hours(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build(env, monkeypatch)

    assert (settings.chat_poll_seconds, settings.chat_reminder_hours) == (30, 4)
    assert env["CHAT_POLL_SECONDS"] == "30"
    assert env["CHAT_REMINDER_HOURS"] == "4"


def test_the_deploy_contract_carries_both_lines() -> None:
    pairs = parse_env_example(DEFAULT_DEPLOY_ENV_EXAMPLE)

    assert pairs["CHAT_POLL_SECONDS"] == "30"
    assert pairs["CHAT_REMINDER_HOURS"] == "4"


@pytest.mark.parametrize("seconds", sorted(CHAT_POLL_PERIODS))
def test_every_period_that_divides_a_minute_is_accepted(
    seconds: int, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert build(env, monkeypatch, CHAT_POLL_SECONDS=str(seconds)).chat_poll_seconds == seconds
    assert CHAT_POLL_PERIODS == frozenset({10, 12, 15, 20, 30})


@pytest.mark.parametrize("seconds", ["11", "60", "0", "-30"])
def test_any_other_period_refuses_start_up(
    seconds: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValidationError, match="chat_poll_seconds"):
        build(env, monkeypatch, CHAT_POLL_SECONDS=seconds)


def test_blank_values_are_the_defaults(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = build(env, monkeypatch, CHAT_POLL_SECONDS="", CHAT_REMINDER_HOURS="")

    assert (settings.chat_poll_seconds, settings.chat_reminder_hours) == (30, 4)


@pytest.mark.parametrize(
    "url",
    ["https://user:pw@orch.example.com", "https://ops@orch.example.com", "https://h/@channel"],
)
def test_a_public_base_url_with_an_at_sign_refuses_start_up(
    url: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Run link is the chat post's trusted suffix, sent unneutralised, so it may carry
    neither userinfo nor any other `@` (story 3-3 lead review of the build, 2026-11-02)."""
    with pytest.raises(ValidationError, match="public_base_url"):
        build(env, monkeypatch, PUBLIC_BASE_URL=url)


@pytest.mark.parametrize("url", ["", "https://orch.example.com", "http://[fd00::1]:4321"])
def test_a_public_base_url_without_one_is_accepted(
    url: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert build(env, monkeypatch, PUBLIC_BASE_URL=url).public_base_url == url


def test_a_reminder_period_under_an_hour_refuses_start_up(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValidationError, match="chat_reminder_hours"):
        build(env, monkeypatch, CHAT_REMINDER_HOURS="0")
