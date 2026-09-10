"""The session-level acceptance path `codex` needs when `TRACEPARENT` is not honoured (7.2).

`research/tracing.md` §Codex read `codex exec`'s inbound-`TRACEPARENT` handling out of the
CLI's own source and marked it "verify day 1"; this story is that day. If the attempt's spans
do parent under the attempt span, nothing here runs — the primary query in
`langfuse_tracer.py` already answers. If they do not, a `codex` attempt is still observable
the way AD-11's universal floor makes every harness observable: every gateway request carries
`langfuse_session_id = run_id` and `langfuse_tags` holding `attempt:{id}`, so Langfuse holds a
trace under the Run's session tagged with the attempt.

The fallback is offered to `codex` alone. AD-10 pins parented spans as `claude`'s rule, and
widening the trace check for a harness this story is not about would change what `enabled`
means for it.

No network: the primary query runs against the same lightweight stub shape
`test_langfuse_tracer.py` uses (that module is frozen; this is its sibling), and the fallback
against a stub `api.trace`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from structlog.testing import capture_logs

from orchestrator.infrastructure.harness.env import attempt_tag
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing.langfuse_tracer import TRACE_OBSERVED, LangfuseTracer
from orchestrator.infrastructure.tracing.session_level import (
    PATH_NONE,
    PATH_PARENTED,
    PATH_SESSION,
    SESSION_LEVEL_HARNESSES,
    session_level_observed,
)
from tests.unit.fakes.tracer import FakeTracer

RUN_ID = UUID("00000000-0000-0000-0000-00000000e001")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-00000000e002")


# ── stubs: the two reads `attempt_observed` can make, and nothing else ──────────────────


@dataclass(frozen=True)
class _StubObservation:
    id: str
    metadata: Any
    parent_observation_id: str | None = None


@dataclass(frozen=True)
class _StubTrace:
    id: str
    observations: list[str] | None = None


class _StubObservations:
    def __init__(self, data: list[_StubObservation]) -> None:
        self._data = data

    def get_many(self, **_kwargs: Any) -> Any:
        return type("Resp", (), {"data": self._data})()


@dataclass
class _StubTraces:
    data: list[_StubTrace] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    raises: bool = False

    def list(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("langfuse is unreachable")
        return type("Resp", (), {"data": self.data})()


class _StubApi:
    def __init__(self, observations: list[_StubObservation], traces: _StubTraces) -> None:
        self.observations = _StubObservations(observations)
        self.trace = traces


class _StubClient:
    def __init__(self, observations: list[_StubObservation], traces: _StubTraces) -> None:
        self.api = _StubApi(observations, traces)


def _tracer(
    observations: list[_StubObservation], traces: _StubTraces
) -> tuple[LangfuseTracer, _StubTraces]:
    tracer = LangfuseTracer(Settings())
    tracer._client = _StubClient(observations, traces)  # type: ignore[assignment]
    return tracer, traces


def _parented() -> list[_StubObservation]:
    mine = _StubObservation(id="span-1", metadata={"attempt_id": str(ATTEMPT_ID)})
    child = _StubObservation(id="span-2", metadata=None, parent_observation_id="span-1")
    return [mine, child]


# ── the port and its one fake ───────────────────────────────────────────────────────────


def test_the_fake_answers_the_scripted_value_whatever_harness_is_named() -> None:
    fake = FakeTracer()
    fake.observed[(RUN_ID, ATTEMPT_ID)] = True

    assert fake.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex") is True


def test_the_fake_records_the_harness_it_was_asked_about() -> None:
    fake = FakeTracer()

    fake.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex")
    fake.attempt_observed(RUN_ID, ATTEMPT_ID)

    assert fake.observed_calls == [(RUN_ID, ATTEMPT_ID, "codex"), (RUN_ID, ATTEMPT_ID, None)]


# ── the real adapter: which path answers ────────────────────────────────────────────────


def test_a_parented_codex_attempt_never_reaches_the_session_query(env: dict[str, str]) -> None:
    tracer, traces = _tracer(_parented(), _StubTraces())

    with capture_logs() as logs:
        observed = tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex")

    assert observed is True
    assert traces.calls == []
    assert [entry["path"] for entry in logs if entry["event"] == TRACE_OBSERVED] == [PATH_PARENTED]


def test_an_unparented_codex_attempt_is_observed_under_the_runs_session(
    env: dict[str, str],
) -> None:
    traces = _StubTraces(data=[_StubTrace(id="t-1", observations=["o-1"])])
    tracer, traces = _tracer([], traces)

    with capture_logs() as logs:
        observed = tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex")

    assert observed is True
    assert [entry["path"] for entry in logs if entry["event"] == TRACE_OBSERVED] == [PATH_SESSION]


def test_the_session_query_names_the_runs_session_and_the_attempts_tag(
    env: dict[str, str],
) -> None:
    tracer, traces = _tracer([], _StubTraces())

    tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex")

    assert len(traces.calls) == 1
    call = traces.calls[0]
    assert call["session_id"] == str(RUN_ID)
    assert call["tags"] == [attempt_tag(str(ATTEMPT_ID))]


def test_a_tagged_trace_holding_no_observation_is_not_an_observation(
    env: dict[str, str],
) -> None:
    """A trace row is not a span. An empty `observations` list is the API saying so."""
    tracer, _ = _tracer([], _StubTraces(data=[_StubTrace(id="t-1", observations=[])]))

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex") is False


def test_a_tagged_trace_that_did_not_expand_its_observations_still_counts(
    env: dict[str, str],
) -> None:
    """`observations` is optional on the API's own model: absent means "not expanded", not
    "none". The trace exists because something was ingested under it."""
    tracer, _ = _tracer([], _StubTraces(data=[_StubTrace(id="t-1", observations=None)]))

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex") is True


def test_nothing_anywhere_answers_false_and_says_so(env: dict[str, str]) -> None:
    tracer, _ = _tracer([], _StubTraces())

    with capture_logs() as logs:
        observed = tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex")

    assert observed is False
    assert [entry["path"] for entry in logs if entry["event"] == TRACE_OBSERVED] == [PATH_NONE]


def test_a_failing_session_query_degrades_rather_than_raising(env: dict[str, str]) -> None:
    tracer, _ = _tracer([], _StubTraces(raises=True))

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="codex") is False


# ── the fallback is codex's alone ───────────────────────────────────────────────────────


def test_claude_is_not_offered_the_fallback(env: dict[str, str]) -> None:
    traces = _StubTraces(data=[_StubTrace(id="t-1", observations=["o-1"])])
    tracer, traces = _tracer([], traces)

    observed = tracer.attempt_observed(RUN_ID, ATTEMPT_ID, harness="claude")

    assert observed is False
    assert traces.calls == []


def test_an_unnamed_harness_is_not_offered_the_fallback(env: dict[str, str]) -> None:
    traces = _StubTraces(data=[_StubTrace(id="t-1", observations=["o-1"])])
    tracer, traces = _tracer([], traces)

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID) is False
    assert traces.calls == []


def test_only_codex_is_in_the_set_as_of_this_story() -> None:
    """`local` joins in 7.3 by its own rule (generations by user id), not by this one."""
    assert set(SESSION_LEVEL_HARNESSES) == {"codex"}


# ── the query helper on its own ─────────────────────────────────────────────────────────


def test_the_helper_reports_false_when_building_the_client_itself_raises() -> None:
    """The accessor is inside the guard, not outside it: `LangfuseTracer` builds its SDK
    client on first use, and a construction that raises must degrade like a failing query."""

    def client_ref() -> Any:
        raise RuntimeError("no client")

    assert session_level_observed(client_ref, RUN_ID, ATTEMPT_ID) is False
