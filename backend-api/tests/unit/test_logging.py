"""structlog JSON to stdout at LOG_LEVEL — asserted as an effect, not as a parsed string."""

from __future__ import annotations

import json
import logging

import pytest
import structlog

from orchestrator import main as composition_root
from orchestrator.infrastructure.logging import configure_logging

EXPECTED_ATTEMPT = 2


def _emit(level: str, message: str) -> None:
    getattr(structlog.get_logger("test"), level)(message)


def test_a_record_is_one_json_object_on_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    _emit("info", "planned")

    captured = capsys.readouterr()
    assert captured.err == ""
    record = json.loads(captured.out.strip())
    assert record["event"] == "planned"
    assert record["level"] == "info"


def test_the_timestamp_is_iso_utc(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    _emit("info", "stamped")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["timestamp"].endswith("Z")


def test_bound_context_travels_with_the_record(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    structlog.get_logger("test").bind(run_id="r1", path="build", attempt=2).info("dispatched")

    record = json.loads(capsys.readouterr().out.strip())
    assert record["run_id"] == "r1"
    assert record["path"] == "build"
    assert record["attempt"] == EXPECTED_ATTEMPT


def test_records_below_the_configured_level_are_dropped(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("warning")
    _emit("info", "too quiet")
    _emit("error", "loud enough")

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert [json.loads(line)["event"] for line in lines] == ["loud enough"]


def test_stdlib_records_are_rendered_as_json_too(capsys: pytest.CaptureFixture[str]) -> None:
    """uvicorn and FastAPI log through stdlib; the stream must not be half plain text."""
    configure_logging("info")
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    line = capsys.readouterr().out.strip()
    assert json.loads(line)["event"] == "Application startup complete."


def test_an_unknown_level_is_rejected_rather_than_silently_downgraded() -> None:
    with pytest.raises(ValueError, match="bogus"):
        configure_logging("bogus")


def test_uvicorn_is_not_allowed_to_replace_the_json_logging_config(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """uvicorn calls dictConfig on startup; unless told not to, it undoes configure_logging."""
    captured: dict[str, object] = {}

    def fake_run(app: object, **kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(composition_root.uvicorn, "run", fake_run)
    composition_root.main()

    assert captured["log_config"] is None
