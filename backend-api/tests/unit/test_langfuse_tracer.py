"""`LangfuseTracer` against the real `langfuse` SDK 4.15.1 — no network.

Three techniques, none of them a real round trip:

- `Langfuse.create_trace_id` is a `staticmethod` with no client and no I/O — called directly.
- A real `Langfuse` client built with an `InMemorySpanExporter` records the same span data a
  real OTLP export would carry, without ever opening a socket (verified live: passing a
  `span_exporter` bypasses the SDK's own HTTP exporter entirely) — swapped into
  `LangfuseTracer._client` so `create_run_trace`/`step_span`/`attempt_span` run for real.
- `attempt_observed` needs a response only a real `GET` could answer, so it runs against a
  lightweight stub standing in for `Langfuse.api.observations.get_many`.

Content-logging (`OTEL_LOG_*`) is 5.1's own frozen coverage (`test_harness_env.py`) and is
not re-tested here — see 5.2's Code Map.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from langfuse import Langfuse
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.tracing.langfuse_tracer import LangfuseTracer, _trace_id

RUN_ID = UUID("00000000-0000-0000-0000-0000000000a1")
OTHER_RUN_ID = UUID("00000000-0000-0000-0000-0000000000a2")
STEP_RUN_ID = UUID("00000000-0000-0000-0000-0000000000a3")
ATTEMPT_ID = UUID("00000000-0000-0000-0000-0000000000a4")


def a_run() -> Run:
    return Run(
        id=RUN_ID,
        project_id=UUID("00000000-0000-0000-0000-0000000000b1"),
        repository_id=UUID("00000000-0000-0000-0000-0000000000b2"),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def a_row() -> StepRun:
    return StepRun(
        id=STEP_RUN_ID,
        run_id=RUN_ID,
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
    )


def an_attempt() -> Attempt:
    return Attempt(id=ATTEMPT_ID, run_id=RUN_ID, step_run_id=STEP_RUN_ID, n=1, status="running")


def a_dispatched_attempt() -> Attempt:
    """An `agent` row's attempt once the harness has reported in — `harness`/`model` set,
    unlike `an_attempt()`, so a test can tell "carried" from "always empty"."""
    return Attempt(
        id=ATTEMPT_ID,
        run_id=RUN_ID,
        step_run_id=STEP_RUN_ID,
        n=1,
        status="running",
        harness="claude",
        model="claude-opus-5",
    )


def a_row_in_a_story_frame() -> StepRun:
    return StepRun(
        id=STEP_RUN_ID,
        run_id=RUN_ID,
        seq=1,
        path="stories[0].build",
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
        frame="stories[0]",
        story_id="5-2",
    )


class _RaisingClient:
    """Stands in for a `Langfuse` client whose own SDK call fails for a reason that is not
    "endpoint unreachable" — a bad key format, a future SDK behaviour change, a programming
    error — the case `EXPORT_TIMEOUT_SECONDS`/the SDK's own exporter retry logic does not
    already cover."""

    def start_as_current_observation(self, **_kwargs: Any) -> Any:
        raise RuntimeError("the SDK itself failed to open a span")

    def flush(self) -> None:
        pass


def _raising_observations_client() -> Any:
    """Stands in for a client whose `api.observations.get_many` raises — auth failure or a
    network error distinct from the already-covered refused-connection case."""

    def get_many(**_kwargs: Any) -> Any:
        raise RuntimeError("the query itself failed")

    observations = type("Observations", (), {"get_many": staticmethod(get_many)})()
    api = type("Api", (), {"observations": observations})()
    return type("Client", (), {"api": api})()


def _wired(settings: Settings) -> tuple[LangfuseTracer, InMemorySpanExporter]:
    """A `LangfuseTracer` whose client exports to memory rather than to any network host.

    `LangfuseResourceManager` (verified live) is a process-wide singleton keyed by
    `public_key`: a second `Langfuse(...)` sharing a key that some earlier call already
    built silently reuses *that* client's exporter, ignoring this one's `span_exporter=`.
    A fresh, unique key per call is what keeps this test's in-memory client its own.
    """
    exporter = InMemorySpanExporter()
    tracer = LangfuseTracer(settings)
    tracer._client = Langfuse(
        public_key=f"pk-test-{uuid4()}",
        secret_key=settings.langfuse_secret_key.get_secret_value(),
        base_url=settings.langfuse_base_url,
        environment=settings.langfuse_environment,
        span_exporter=exporter,
    )
    return tracer, exporter


# ── create_trace_id: deterministic, no client, no I/O ────────────────────────────────────


def test_create_trace_id_is_deterministic_by_seed() -> None:
    first = Langfuse.create_trace_id(seed=str(RUN_ID))
    second = Langfuse.create_trace_id(seed=str(RUN_ID))

    assert first == second
    assert len(first) == 32  # noqa: PLR2004 — the W3C trace-id length, spelled out once


def test_create_trace_id_differs_by_seed() -> None:
    assert Langfuse.create_trace_id(seed=str(RUN_ID)) != Langfuse.create_trace_id(
        seed=str(OTHER_RUN_ID)
    )


# ── laziness: trace_url never builds a client; a tracing call does ───────────────────────


def test_trace_url_formats_from_settings_and_builds_no_client(env: dict[str, str]) -> None:
    settings = Settings()
    tracer = LangfuseTracer(settings)

    url = tracer.trace_url("t-1")

    assert url == f"{settings.langfuse_base_url}/project/{settings.langfuse_project_id}/traces/t-1"
    assert tracer._client is None


def test_the_client_is_none_until_first_use(env: dict[str, str]) -> None:
    tracer = LangfuseTracer(Settings())

    assert tracer._client is None

    tracer._client_ref()

    assert tracer._client is not None


# ── an unreachable endpoint: caught inside the SDK, never raised (verified live) ─────────


def test_an_unreachable_langfuse_never_raises_out_of_step_span(env: dict[str, str]) -> None:
    """`EXPORT_TIMEOUT_SECONDS` bounds the SDK's own retry-with-backoff loop; a refused
    connection is caught and logged inside `langfuse`/OTel, so `create_run_trace` and the
    `step_span` context manager (including its own `flush()`) complete normally against a
    port nothing listens on."""
    settings = Settings(langfuse_base_url="http://127.0.0.1:1")
    tracer = LangfuseTracer(settings)
    run, row, attempt = a_run(), a_row(), an_attempt()

    tracer.create_run_trace(RUN_ID, "acme", (), name="run repo-init@1 main")
    with tracer.step_span(run, row, attempt) as span:
        assert span.trace_id == _trace_id(RUN_ID)


# ── create_run_trace / step_span / attempt_span: real client, in-memory exporter ─────────


def test_create_run_trace_returns_the_deterministic_trace_id(env: dict[str, str]) -> None:
    tracer, exporter = _wired(Settings())

    ref = tracer.create_run_trace(RUN_ID, "acme", (), name="run repo-init@1 main")

    assert ref.trace_id == _trace_id(RUN_ID)
    tracer._client.flush()
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "run repo-init@1 main"


def test_create_run_trace_sets_session_id_user_id_and_tags(env: dict[str, str]) -> None:
    """The brief's own binding rule: `session_id = run_id`, `user_id = run_id` — what makes
    Langfuse's Sessions view group every harness call under one Run — plus the identity
    tags, set through the SDK's public `propagate_attributes`, not metadata."""
    tracer, exporter = _wired(Settings())

    tracer.create_run_trace(RUN_ID, "acme", (), name="run repo-init@1 main")

    tracer._client.flush()
    span = exporter.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["session.id"] == str(RUN_ID)
    assert span.attributes["user.id"] == str(RUN_ID)
    assert set(span.attributes["langfuse.trace.tags"]) == {f"run:{RUN_ID}", "project:acme"}
    assert span.attributes["langfuse.trace.name"] == "run repo-init@1 main"


def test_step_span_is_named_by_the_path_and_carries_the_runs_trace_id(env: dict[str, str]) -> None:
    tracer, exporter = _wired(Settings())
    run, row, attempt = a_run(), a_row(), an_attempt()

    with tracer.step_span(run, row, attempt) as span:
        assert span.trace_id == _trace_id(RUN_ID)
        assert span.traceparent == f"00-{span.trace_id}-{span.span_id}-01"

    tracer._client.flush()
    spans = exporter.get_finished_spans()
    assert spans[0].name == "stories[0].build"


def test_step_span_carries_run_id_path_kind_and_attempt_in_metadata(env: dict[str, str]) -> None:
    tracer, exporter = _wired(Settings())
    run, row = a_run(), a_row()
    attempt = an_attempt().model_copy(update={"n": 2})

    with tracer.step_span(run, row, attempt):
        pass

    tracer._client.flush()
    span = exporter.get_finished_spans()[0]
    assert span.attributes is not None
    assert span.attributes["langfuse.observation.metadata.run_id"] == str(RUN_ID)
    assert span.attributes["langfuse.observation.metadata.path"] == "stories[0].build"
    assert span.attributes["langfuse.observation.metadata.kind"] == "agent"
    assert span.attributes["langfuse.observation.metadata.attempt"] == 2  # noqa: PLR2004


def test_attempt_span_nests_under_the_open_step_span(env: dict[str, str]) -> None:
    tracer, exporter = _wired(Settings())
    run, row, attempt = a_run(), a_row(), an_attempt()

    with tracer.step_span(run, row, attempt) as step:
        with tracer.attempt_span(run, row, attempt) as inner:
            pass

    assert inner.trace_id == step.trace_id
    tracer._client.flush()
    spans = {span.name: span for span in exporter.get_finished_spans()}
    attempt_span = spans["stories[0].build attempt 1"]
    step_span = spans["stories[0].build"]
    assert attempt_span.parent is not None
    assert attempt_span.parent.span_id == step_span.get_span_context().span_id


def test_attempt_span_carries_attempt_id_harness_model_and_story_id_in_metadata(
    env: dict[str, str],
) -> None:
    tracer, exporter = _wired(Settings())
    run, row, attempt = a_run(), a_row_in_a_story_frame(), a_dispatched_attempt()

    with tracer.step_span(run, row, attempt):
        with tracer.attempt_span(run, row, attempt):
            pass

    tracer._client.flush()
    attempt_span = next(
        span for span in exporter.get_finished_spans() if span.name.endswith("attempt 1")
    )
    assert attempt_span.attributes is not None
    prefix = "langfuse.observation.metadata."
    assert attempt_span.attributes[f"{prefix}attempt_id"] == str(ATTEMPT_ID)
    assert attempt_span.attributes[f"{prefix}harness"] == "claude"
    assert attempt_span.attributes[f"{prefix}model"] == "claude-opus-5"
    assert attempt_span.attributes[f"{prefix}story_id"] == "5-2"


def test_attempt_span_omits_harness_and_model_when_the_attempt_has_neither(
    env: dict[str, str],
) -> None:
    """`an_attempt()` (unlike `a_dispatched_attempt()`) leaves `harness`/`model` unset — a
    `None` value is omitted from the exported attributes rather than sent as `"None"`."""
    tracer, exporter = _wired(Settings())
    run, row, attempt = a_run(), a_row(), an_attempt()

    with tracer.step_span(run, row, attempt):
        with tracer.attempt_span(run, row, attempt):
            pass

    tracer._client.flush()
    attempt_span = next(
        span for span in exporter.get_finished_spans() if span.name.endswith("attempt 1")
    )
    assert attempt_span.attributes is not None
    assert "langfuse.observation.metadata.harness" not in attempt_span.attributes
    assert "langfuse.observation.metadata.model" not in attempt_span.attributes
    assert "langfuse.observation.metadata.story_id" not in attempt_span.attributes


# ── tracing is a side channel: the SDK itself raising never breaks a caller (SM-3) ───────


def test_create_run_trace_degrades_when_the_sdk_itself_raises_opening_the_span(
    env: dict[str, str],
) -> None:
    tracer = LangfuseTracer(Settings())
    tracer._client = _RaisingClient()

    ref = tracer.create_run_trace(RUN_ID, "acme", (), name="run repo-init@1 main")

    assert ref.trace_id == _trace_id(RUN_ID)


def test_step_span_degrades_and_still_yields_when_the_sdk_itself_raises(
    env: dict[str, str],
) -> None:
    tracer = LangfuseTracer(Settings())
    tracer._client = _RaisingClient()
    run, row, attempt = a_run(), a_row(), an_attempt()

    with tracer.step_span(run, row, attempt) as span:
        assert span.trace_id == _trace_id(RUN_ID)
        assert span.traceparent.startswith(f"00-{_trace_id(RUN_ID)}-")


def test_attempt_span_degrades_and_still_yields_when_the_sdk_itself_raises(
    env: dict[str, str],
) -> None:
    tracer = LangfuseTracer(Settings())
    tracer._client = _RaisingClient()
    run, row, attempt = a_run(), a_row(), an_attempt()

    with tracer.attempt_span(run, row, attempt) as span:
        assert span.trace_id == _trace_id(RUN_ID)


def test_step_span_still_propagates_the_rows_own_exception(env: dict[str, str]) -> None:
    """A row's own failure (`execute(context)` raising inside `with tracer.step_span(...):`)
    is never one of the exceptions this adapter swallows — only the SDK's own count."""
    tracer, exporter = _wired(Settings())
    run, row, attempt = a_run(), a_row(), an_attempt()

    class RowFailed(Exception):
        pass

    with pytest.raises(RowFailed), tracer.step_span(run, row, attempt):
        raise RowFailed("the executor raised")

    tracer._client.flush()
    assert len(exporter.get_finished_spans()) == 1  # closed and exported despite the raise


def test_step_span_still_propagates_the_rows_own_exception_even_when_opening_also_failed(
    env: dict[str, str],
) -> None:
    """The rarer case: the SDK failed to open the span *and* the row's own code then
    raises against the fallback `SpanRef` it was handed — still not swallowed."""
    tracer = LangfuseTracer(Settings())
    tracer._client = _RaisingClient()
    run, row, attempt = a_run(), a_row(), an_attempt()

    class RowFailed(Exception):
        pass

    with pytest.raises(RowFailed), tracer.step_span(run, row, attempt):
        raise RowFailed("the executor raised")


def test_attempt_observed_false_when_the_query_itself_raises(env: dict[str, str]) -> None:
    tracer = LangfuseTracer(Settings())
    tracer._client = _raising_observations_client()

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID) is False


# ── trace_url ──────────────────────────────────────────────────────────────────────────


def test_trace_url_normalizes_a_trailing_slash_on_the_base_url(env: dict[str, str]) -> None:
    settings = Settings(langfuse_base_url="http://host.example/")
    tracer = LangfuseTracer(settings)

    url = tracer.trace_url("t-1")

    assert url == f"http://host.example/project/{settings.langfuse_project_id}/traces/t-1"


# ── attempt_observed: a lightweight stub standing in for a real GET ──────────────────────


@dataclass(frozen=True)
class _StubObservation:
    id: str
    metadata: Any
    parent_observation_id: str | None = None


class _StubObservations:
    def __init__(self, data: list[_StubObservation]) -> None:
        self._data = data

    def get_many(self, **_kwargs: Any) -> Any:
        return type("Resp", (), {"data": self._data})()


class _StubApi:
    def __init__(self, data: list[_StubObservation]) -> None:
        self.observations = _StubObservations(data)


class _StubClient:
    def __init__(self, data: list[_StubObservation]) -> None:
        self.api = _StubApi(data)


def test_attempt_observed_true_when_something_parents_the_attempts_own_span(
    env: dict[str, str],
) -> None:
    tracer = LangfuseTracer(Settings())
    mine = _StubObservation(id="span-1", metadata={"attempt_id": str(ATTEMPT_ID)})
    child = _StubObservation(id="span-2", metadata=None, parent_observation_id="span-1")
    tracer._client = _StubClient([mine, child])

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID) is True


def test_attempt_observed_false_when_nothing_parents_the_attempts_own_span(
    env: dict[str, str],
) -> None:
    tracer = LangfuseTracer(Settings())
    mine = _StubObservation(id="span-1", metadata={"attempt_id": str(ATTEMPT_ID)})
    tracer._client = _StubClient([mine])

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID) is False


def test_attempt_observed_false_when_the_attempts_own_span_never_appears(
    env: dict[str, str],
) -> None:
    tracer = LangfuseTracer(Settings())
    other = _StubObservation(id="span-9", metadata={"attempt_id": "some-other-attempt"})
    tracer._client = _StubClient([other])

    assert tracer.attempt_observed(RUN_ID, ATTEMPT_ID) is False
