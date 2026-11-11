"""`FsSetupRecord` reads `$AGENT_HOME/.orchestrator/setup-run.json`, never writes it
(story 2, orchestrator-deploy-folder epic 1, 2026-11-11; AD-29, C6)."""

from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path

from structlog.testing import capture_logs

from orchestrator.infrastructure import setup_record as module
from orchestrator.infrastructure.setup_record import RECORD, FsSetupRecord
from tests.unit.fakes.setup_record import setup_run

WARNING = "setup record unreadable"


def _write(home: Path, text: str) -> None:
    (home / RECORD).parent.mkdir(parents=True, exist_ok=True)
    (home / RECORD).write_text(text)


def test_ac6_reads_the_record_under_the_agent_home(tmp_path: Path) -> None:
    run = setup_run()
    _write(tmp_path, run.model_dump_json())

    assert RECORD == Path(".orchestrator") / "setup-run.json"
    assert FsSetupRecord(tmp_path).read() == run


def test_a_missing_file_is_none_and_silent(tmp_path: Path) -> None:
    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert logs == []


def test_not_json_is_none_with_one_warning(tmp_path: Path) -> None:
    _write(tmp_path, "{nope")

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_a_missing_c6_field_is_none_with_one_warning(tmp_path: Path) -> None:
    data = json.loads(setup_run().model_dump_json())
    del data["catalog"]
    _write(tmp_path, json.dumps(data))

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_an_unreadable_path_is_none_with_one_warning(tmp_path: Path) -> None:
    (tmp_path / RECORD).mkdir(parents=True)

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_extra_keys_are_accepted(tmp_path: Path) -> None:
    data = json.loads(setup_run().model_dump_json())
    data["future"] = {"a": 1}
    data["scripts"][0]["extra"] = True
    _write(tmp_path, json.dumps(data))

    assert FsSetupRecord(tmp_path).read() == setup_run()


def test_the_adapter_never_opens_a_file_for_writing() -> None:
    source = Path(module.__file__).read_text()

    for token in ("write_text", "write_bytes", '"w"', "'w'", '"a"', "mkdir", "unlink"):
        assert token not in source


def test_a_naive_timestamp_is_none_with_one_warning(tmp_path: Path) -> None:
    data = json.loads(setup_run().model_dump_json())
    data["at"] = "2026-11-11T08:00:00"
    _write(tmp_path, json.dumps(data))

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_an_out_of_range_timestamp_is_none_with_one_warning(tmp_path: Path) -> None:
    data = json.loads(setup_run().model_dump_json())
    data["at"] = "0001-01-01T00:00:00+01:00"
    _write(tmp_path, json.dumps(data))

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_an_offset_timestamp_reads_as_utc(tmp_path: Path) -> None:
    data = json.loads(setup_run().model_dump_json())
    data["at"] = "2026-11-11T09:00:00+01:00"
    _write(tmp_path, json.dumps(data))

    run = FsSetupRecord(tmp_path).read()

    assert run is not None
    assert run.at == setup_run().at
    assert run.at.utcoffset() == timedelta(0)


def test_deeply_nested_json_is_none_with_one_warning(tmp_path: Path) -> None:
    _write(tmp_path, "[" * 100_000 + "]" * 100_000)

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_a_fifo_is_none_with_one_warning_and_never_blocks(tmp_path: Path) -> None:
    (tmp_path / RECORD).parent.mkdir(parents=True)
    os.mkfifo(tmp_path / RECORD)

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]


def test_an_oversized_file_is_none_with_one_warning(tmp_path: Path) -> None:
    _write(tmp_path, " " * (module.MAX_BYTES + 1))

    with capture_logs() as logs:
        assert FsSetupRecord(tmp_path).read() is None

    assert [log["event"] for log in logs] == [WARNING]
