"""`steps/agent_failure.py`, through `AgentExecutor.execute` (SPEC senior-unblock CAP-5,
story 1-2, 2026-11-02): an attempt that failed after real work parks under the provider's own
words rather than `harness exit {code}`, and an attempt that did not fail is read by nothing."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from typing import Any

from orchestrator.application.rules.routing import HARNESS_EXIT
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_failure import provider_reason
from orchestrator.domain.ports.harness import HarnessResult, HarnessUsage
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import World
from tests.unit.application.steps.agent_tail_fixtures import (
    LOG_PATH,
    SESSION_ID,
    a_story,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.logs import FakeLogReader

OPENROUTER_402 = (
    'API Error: 402 {"error":{"message":"Insufficient credits. This account never has '
    "purchased credits. Make sure your key is on the correct account or org, and if so, "
    'purchase more at https://openrouter.ai/settings/credits","code":402}}'
)
MAX_TAIL = 100
WORKED = HarnessUsage(tokens_in=9000, tokens_out=4200, cost_usd=Decimal("1.5"))
NEVER_REACHED = HarnessUsage(tokens_in=0, tokens_out=0, cost_usd=Decimal(0))


def failed_after_work(  # noqa: PLR0913 — one keyword per fact of the failed attempt
    *,
    exit_code: int | None = 1,
    raw: dict[str, Any] | None = None,
    usage: HarnessUsage | None = WORKED,
    log: list[str] | None = None,
    story: str | None = None,
    with_resolved: dict[str, Any] | None = None,
    logs: bool = True,
) -> World:
    result = HarnessResult(
        session_id=SESSION_ID,
        exit_code=exit_code,
        log_path=LOG_PATH,
        usage=usage,
        raw_result=raw,
    )
    world = a_tail_world(
        story=story, harness=FakeHarness(results=[result]), with_resolved=with_resolved
    )
    if not logs:
        return world
    reader = FakeLogReader(lines_by_path={str(LOG_PATH): log or []})
    ports = replace(world.ctx.ports, logs=reader)
    return replace(world, ctx=replace(world.ctx, ports=ports))


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def parked_reason(result: StepResult) -> str:
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == result.reason
    assert result.reason is not None
    return result.reason


def test_a_credit_error_in_the_result_object_parks_under_its_own_words() -> None:
    raw = {"type": "result", "is_error": True, "result": OPENROUTER_402}

    result = run(failed_after_work(raw=raw))

    reason = parked_reason(result)
    assert reason.startswith("provider error: API Error: 402")
    assert "Insufficient credits" in reason
    assert "harness exit" not in reason


def test_a_credit_error_only_in_the_log_parks_under_its_own_words() -> None:
    log = [
        json.dumps({"type": "assistant", "message": {"content": []}}),
        json.dumps({"type": "result", "is_error": True, "result": OPENROUTER_402}),
    ]

    result = run(failed_after_work(raw=None, log=log))

    assert parked_reason(result).startswith("provider error: API Error: 402")


def test_a_rate_failure_in_stderr_text_parks_under_its_own_words() -> None:
    result = run(failed_after_work(log=["Error: 429 Too Many Requests"]))

    assert parked_reason(result) == "provider error: Error: 429 Too Many Requests"


def test_a_done_file_overruled_by_a_provider_failure_names_it_and_still_takes_the_retry_path() -> (
    None
):
    world = failed_after_work(
        raw={"is_error": True, "result": OPENROUTER_402}, story=a_story("done")
    )

    result = run(world)

    assert result.status == "error"
    assert result.park is None
    assert result.retry is not None
    assert (result.reason or "").startswith("provider error: ")


def test_a_row_that_declares_no_retry_parks_misconfigured_with_the_provider_reason() -> None:
    world = failed_after_work(
        raw={"is_error": True, "result": OPENROUTER_402},
        story=a_story("done"),
        with_resolved=contracted(retry=None),
    )

    assert parked_reason(run(world)).startswith("provider error: ")


def test_a_failure_the_provider_did_not_cause_keeps_the_exit_code() -> None:
    raw = {"is_error": True, "result": "API Error: connection reset"}

    result = run(failed_after_work(raw=raw, log=["segfault"]))

    assert parked_reason(result) == HARNESS_EXIT.format(code=1)


def test_without_a_log_reader_the_result_object_still_decides() -> None:
    raw = {"is_error": True, "result": OPENROUTER_402}

    assert parked_reason(run(failed_after_work(raw=raw, logs=False))).startswith("provider error")
    assert parked_reason(run(failed_after_work(logs=False))) == HARNESS_EXIT.format(code=1)


def test_an_absent_exit_code_is_not_a_failed_attempt() -> None:
    raw = {"is_error": True, "result": OPENROUTER_402}

    result = run(failed_after_work(exit_code=None, raw=raw))

    assert "provider error" not in (result.reason or "")


def test_a_clean_exit_with_a_done_file_is_done_whatever_the_log_says() -> None:
    log = ["Error: 429 rate limit while testing retries"]

    result = run(failed_after_work(exit_code=0, log=log, story=a_story("done")))

    assert result.status == "done"
    assert result.park is None


def test_a_clean_exit_with_no_file_still_reads_no_story_file() -> None:
    result = run(failed_after_work(exit_code=0, log=["Error: 402 Payment Required"]))

    assert parked_reason(result) == "no story file"


def test_a_clean_exit_does_not_read_the_log_at_all() -> None:
    world = failed_after_work(exit_code=0, story=a_story("done"))

    run(world)

    reader = world.ctx.ports.logs
    assert isinstance(reader, FakeLogReader)
    assert reader.calls == []


def test_the_log_is_read_only_after_the_result_object_found_nothing_and_only_its_tail() -> None:
    world = failed_after_work(raw={"is_error": True, "result": OPENROUTER_402})
    run(world)
    reader = world.ctx.ports.logs
    assert isinstance(reader, FakeLogReader)
    assert reader.calls == []

    world = failed_after_work(raw=None, log=["noise"])
    run(world)
    reader = world.ctx.ports.logs
    assert isinstance(reader, FakeLogReader)
    assert [path for path, _ in reader.calls] == [str(LOG_PATH)]
    assert all(0 < lines <= MAX_TAIL for _, lines in reader.calls)


def test_an_agent_that_wrote_a_blocked_file_keeps_its_own_question() -> None:
    log = ["Error: 429 rate limit"]
    story = a_story("blocked", condition="needs a decision")

    result = run(failed_after_work(log=log, story=story))

    assert result.status == "blocked"
    assert result.park is not None
    assert result.park.kind == "blocked"


def test_a_gateway_that_was_never_reached_is_still_the_gateways_reason() -> None:
    raw = {"is_error": True, "result": "API Error: 402 Insufficient credits"}

    result = run(failed_after_work(raw=raw, usage=NEVER_REACHED))

    assert (result.reason or "").startswith("gateway unreachable: ")


def test_the_reason_carries_no_secret_from_the_log() -> None:
    secret = "sk-or-v1-0123456789abcdef0123456789abcdef"
    log = [f"Error: 402 insufficient credits for key {secret}"]

    result = run(failed_after_work(log=log))

    assert secret not in (result.reason or "")
    assert secret not in str(result.park)


def test_provider_reason_is_none_for_a_clean_or_unfinished_attempt() -> None:
    world = failed_after_work(raw={"is_error": True, "result": OPENROUTER_402})
    clean = HarnessResult(session_id=None, exit_code=0, log_path=LOG_PATH, raw_result=None)
    unfinished = HarnessResult(session_id=None, exit_code=None, log_path=LOG_PATH)

    assert provider_reason(world.ctx, clean) is None
    assert provider_reason(world.ctx, unfinished) is None
