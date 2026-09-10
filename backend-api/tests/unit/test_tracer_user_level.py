"""How a `local` attempt is proven observed: by user id, inside its own window (AD-11, 7.3).

`research/tracing.md` §OpenCode: the Langfuse plugin opens one trace per turn, keyed by
OpenCode's own session id, with `userId` taken from `LANGFUSE_USER_ID` — which
`scripts/harness/opencode.sh` binds to `ORCH_RUN_ID`. There is no inbound `TRACEPARENT` and no
seed, so nothing the plugin sends can carry this orchestrator's attempt id. The Run is
therefore the finest identity available, and the only thing separating *this* attempt's
generations from another attempt of the same Run is when they happened.

That is an assumption and the brief marks it one (`[ASSUMPTION: time-window attribution]`).
What is asserted here is what follows from it either way: another Run's user id is never this
attempt's evidence, a generation outside the window is not either, an attempt with no window
answers `False` rather than widening to the whole Run, and a Langfuse that cannot be reached
answers exactly what a not-yet-observed attempt answers (SM-3) instead of raising into a
readiness evaluation.

Also pinned: `codex`'s session-level fallback and `local`'s user-level one are two rules, not
one — a `claude` attempt gets neither, which is what keeps `enabled` meaning the same thing
for the harness this story is not about.

No network: the same lightweight stub shape `test_langfuse_tracer.py` uses (frozen; this is a
sibling), plus a stub `api.observations` that records the query it was asked.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from structlog.testing import capture_logs

from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing.langfuse_tracer import TRACE_OBSERVED, LangfuseTracer
from orchestrator.infrastructure.tracing.session_level import (
    PATH_NONE,
    PATH_PARENTED,
    PATH_SESSION,
    SESSION_LEVEL_HARNESSES,
)
from orchestrator.infrastructure.tracing.user_level import (
    PATH_USER,
    USER_LEVEL_HARNESSES,
    USER_OBSERVATION_PAGE_LIMIT,
    user_level_observed,
)
from tests.unit.fakes.tracer import FakeTracer

RUN_ID = UUID("00000000-0000-0000-0000-00000000f001")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-00000000f002")
OTHER_RUN_ID = UUID("00000000-0000-0000-0000-00000000f003")

STARTED = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
ENDED = STARTED + timedelta(minutes=20)
INSIDE = STARTED + timedelta(minutes=5)
BEFORE = STARTED - timedelta(minutes=5)
AFTER = ENDED + timedelta(minutes=5)

#: `parented`, `session`, `user`, `none` — one per rule, plus the answer none of them gave.
DISTINCT_PATHS = 4


# ── stubs ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _StubObservation:
    id: str
    user_id: str | None = None
    start_time: datetime | None = None
    metadata: Any = None
    parent_observation_id: str | None = None


@dataclass
class _StubObservations:
    data: list[_StubObservation] = field(default_factory=list)
    calls: list[dict[str, Any]] = field(default_factory=list)
    raises: bool = False

    def get_many(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.raises:
            raise RuntimeError("langfuse is unreachable")
        return type("Resp", (), {"data": self.data})()


class _StubApi:
    def __init__(self, observations: _StubObservations) -> None:
        self.observations = observations


class _StubClient:
    def __init__(self, observations: _StubObservations) -> None:
        self.api = _StubApi(observations)


def a_client(observations: _StubObservations) -> Any:
    client = _StubClient(observations)
    return lambda: client


def a_generation(**overrides: Any) -> _StubObservation:
    fields: dict[str, Any] = {
        "id": "gen-1",
        "user_id": str(RUN_ID),
        "start_time": INSIDE,
    }
    fields.update(overrides)
    return _StubObservation(**fields)


def a_tracer(observations: _StubObservations) -> LangfuseTracer:
    tracer = LangfuseTracer(Settings())
    tracer._client = _StubClient(observations)  # type: ignore[assignment]
    return tracer


# ── the two rules are two rules ──────────────────────────────────────────────


def test_the_user_level_rule_is_offered_to_local_alone() -> None:
    assert USER_LEVEL_HARNESSES == frozenset({"local"})


def test_it_is_not_the_same_set_as_the_session_level_fallback() -> None:
    """`codex` falls back to a trace tagged with the attempt; `local` has no such tag to be
    found by. Two rules, and a harness in neither gets the strict parented one (AD-10)."""
    assert USER_LEVEL_HARNESSES & SESSION_LEVEL_HARNESSES == frozenset()


def test_every_path_is_distinguishable_in_the_log() -> None:
    """Four answers, four distinct strings: an Operator reading `path=` must be able to tell
    "the harness parented" from "the fallback carried it" from "nothing did"."""
    assert len({PATH_PARENTED, PATH_SESSION, PATH_USER, PATH_NONE}) == DISTINCT_PATHS


# ── the query ────────────────────────────────────────────────────────────────


def test_the_query_asks_for_this_runs_user_inside_this_attempts_window() -> None:
    observations = _StubObservations([a_generation()])

    user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)

    assert observations.calls == [
        {
            "user_id": str(RUN_ID),
            "from_start_time": STARTED,
            "to_start_time": ENDED,
            "limit": USER_OBSERVATION_PAGE_LIMIT,
        }
    ]


def test_one_generation_of_this_run_inside_the_window_is_evidence() -> None:
    observations = _StubObservations([a_generation()])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is True
    )


def test_another_runs_user_id_is_not_this_attempts_evidence() -> None:
    """The whole point of re-checking what the query returned: the parameter names are
    documented and unobserved (7.4 settles them), and one the API quietly ignored would turn
    "this attempt was observed" into "something of somebody's was"."""
    observations = _StubObservations([a_generation(user_id=str(OTHER_RUN_ID))])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_a_generation_with_no_user_id_at_all_is_not_evidence() -> None:
    observations = _StubObservations([a_generation(user_id=None)])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_a_generation_before_the_attempt_started_is_not_evidence() -> None:
    observations = _StubObservations([a_generation(start_time=BEFORE)])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_a_generation_after_the_attempt_ended_is_not_evidence() -> None:
    """A retry of the same row is a second attempt under the same Run and the same user id;
    without this, its generations would prove the first attempt observed."""
    observations = _StubObservations([a_generation(start_time=AFTER)])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_a_generation_with_no_time_of_its_own_is_not_evidence() -> None:
    observations = _StubObservations([a_generation(start_time=None)])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_an_attempt_with_no_window_is_never_proven_by_this_rule() -> None:
    """Evidence nobody can attribute is not evidence: an unbounded query would accept any
    generation the Run ever made, including another attempt's."""
    observations = _StubObservations([a_generation()])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=None, ended_at=ENDED)
        is False
    )
    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=None)
        is False
    )
    assert observations.calls == []


def test_an_empty_answer_is_not_evidence() -> None:
    observations = _StubObservations([])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_a_langfuse_that_cannot_be_reached_answers_not_observed() -> None:
    """SM-3: tracing is a side channel. A query failure answers exactly what a not-yet-
    observed attempt answers, and never raises into a readiness evaluation."""
    observations = _StubObservations([a_generation()], raises=True)

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )


def test_a_client_that_cannot_even_be_built_answers_not_observed() -> None:
    """The accessor is called inside the guard, not before it: `LangfuseTracer` builds its
    SDK client lazily, and a construction that raised must degrade like a query that did."""

    def exploding() -> Any:
        raise RuntimeError("no keys")

    assert user_level_observed(exploding, RUN_ID, started_at=STARTED, ended_at=ENDED) is False


# ── through the adapter ──────────────────────────────────────────────────────


def test_a_local_attempt_is_observed_through_the_user_level_rule(env: dict[str, str]) -> None:
    tracer = a_tracer(_StubObservations([a_generation()]))

    observed = tracer.attempt_observed(
        RUN_ID, ATTEMPT_ID, harness="local", started_at=STARTED, ended_at=ENDED
    )

    assert observed is True


def test_the_path_that_answered_is_logged(env: dict[str, str]) -> None:
    """The port returns a bool and the readiness line's wording is frozen, so the log is the
    only place an Operator can see which rule proved the attempt."""
    tracer = a_tracer(_StubObservations([a_generation()]))

    with capture_logs() as logs:
        tracer.attempt_observed(
            RUN_ID, ATTEMPT_ID, harness="local", started_at=STARTED, ended_at=ENDED
        )

    lines = [line for line in logs if line["event"] == TRACE_OBSERVED]
    assert [line["path"] for line in lines] == [PATH_USER]


def test_a_local_attempt_with_no_generation_of_its_own_is_not_observed(
    env: dict[str, str],
) -> None:
    tracer = a_tracer(_StubObservations([a_generation(user_id=str(OTHER_RUN_ID))]))

    observed = tracer.attempt_observed(
        RUN_ID, ATTEMPT_ID, harness="local", started_at=STARTED, ended_at=ENDED
    )

    assert observed is False


def test_a_claude_attempt_is_never_offered_the_user_level_rule(env: dict[str, str]) -> None:
    """AD-10's rule for `claude` is parented spans, and a fallback applied to whichever
    harness happened to miss would change what `enabled` means for it."""
    observations = _StubObservations([a_generation()])
    tracer = a_tracer(observations)

    observed = tracer.attempt_observed(
        RUN_ID, ATTEMPT_ID, harness="claude", started_at=STARTED, ended_at=ENDED
    )

    assert observed is False
    assert all("user_id" not in call for call in observations.calls)


def test_the_parented_answer_still_wins_when_it_is_available(env: dict[str, str]) -> None:
    """A `local` attempt whose spans somehow did parent needs no fallback, and the log says
    so — the fallback runs only when the primary found nothing."""
    mine = _StubObservation(id="span-1", metadata={"attempt_id": str(ATTEMPT_ID)})
    child = _StubObservation(id="span-2", parent_observation_id="span-1")
    tracer = a_tracer(_StubObservations([mine, child]))

    with capture_logs() as logs:
        observed = tracer.attempt_observed(
            RUN_ID, ATTEMPT_ID, harness="local", started_at=STARTED, ended_at=ENDED
        )

    assert observed is True
    assert [line["path"] for line in logs if line["event"] == TRACE_OBSERVED] == [PATH_PARENTED]


# ── the port's one fake ──────────────────────────────────────────────────────


def test_the_fake_records_the_window_it_was_asked_about() -> None:
    """AD-18: one fake per port. The window is recorded so a use-case test can assert the
    attempt's own times reached the port, without a second double existing."""
    fake = FakeTracer()

    fake.attempt_observed(RUN_ID, ATTEMPT_ID, harness="local", started_at=STARTED, ended_at=ENDED)

    assert fake.observed_windows == [(STARTED, ENDED)]


def test_the_fake_still_answers_the_scripted_value_whatever_window_is_named() -> None:
    """Which rule applies to which harness is the adapter's concern (AD-11), never a port
    behaviour a use case may depend on."""
    fake = FakeTracer()
    fake.observed[(RUN_ID, ATTEMPT_ID)] = True

    assert (
        fake.attempt_observed(
            RUN_ID, ATTEMPT_ID, harness="local", started_at=STARTED, ended_at=ENDED
        )
        is True
    )


# ── shapes nobody has observed yet still answer, never raise ─────────────────


def test_a_naive_timestamp_is_read_as_utc_rather_than_refused() -> None:
    """Langfuse answers UTC and `Attempt.started_at` is aware, so comparing a naive one
    directly would raise `TypeError` — turning a harness that traced perfectly well into an
    exception inside a readiness evaluation."""
    observations = _StubObservations([a_generation(start_time=INSIDE.replace(tzinfo=None))])

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is True
    )


def test_an_observation_this_code_cannot_read_answers_not_observed() -> None:
    """The reading is inside the guard as well as the query: an unobserved API's answer is
    exactly where a shape nobody has seen turns into an exception (SM-3)."""

    class Unreadable:
        @property
        def user_id(self) -> str:
            raise RuntimeError("a shape this code has never seen")

    observations = _StubObservations([Unreadable()])  # type: ignore[list-item]

    assert (
        user_level_observed(a_client(observations), RUN_ID, started_at=STARTED, ended_at=ENDED)
        is False
    )
