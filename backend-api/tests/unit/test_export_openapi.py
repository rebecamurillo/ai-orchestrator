"""The contract export, which `make openapi` is a two-line wrapper around (AD-3).

Three properties are load-bearing and none of them is obvious from reading the module:

- **It needs no environment and no database.** `make openapi` runs on a fresh clone with no
  `.env` and no Postgres, so the exporter must build the application without either. The
  test proves it by emptying `os.environ` first — if the exporter ever starts validating
  `Settings` against the environment, this fails rather than the gate failing on someone
  else's machine.
- **Its output is stable.** `schema.d.ts` is committed, so an export whose key order varied
  would show up as a diff on every run and make the drift check in `make lint` meaningless.
- **A failed export does not destroy the committed contract.** `… > contracts/openapi.json`
  truncates the file before the exporter runs; `--output` exists so that the file is
  replaced only once the whole document has been built.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.tools import export_openapi

SENTINEL = '{"kept": true}\n'


@pytest.fixture
def no_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every configuration variable gone — the state of a fresh clone with no `.env`."""
    monkeypatch.setattr(os, "environ", {})


def test_the_document_is_built_without_an_environment(no_environment: None) -> None:
    document = export_openapi.build_document()

    assert document["openapi"].startswith("3.")
    assert document["info"]["title"] == "ai-orchestrator backend-api"


def test_the_document_publishes_the_routes_the_web_client_generates_from(
    no_environment: None,
) -> None:
    paths = export_openapi.build_document()["paths"]

    assert "/healthz" in paths
    assert "/api/v1/ping" in paths


def test_the_document_carries_the_problem_schema(no_environment: None) -> None:
    """web-client renders `detail` and `errors[]`; without the schema it has no type for them."""
    schemas = export_openapi.build_document()["components"]["schemas"]

    assert "ProblemDetail" in schemas
    assert "Pong" in schemas
    assert "Health" in schemas


def test_the_rendering_is_sorted_and_newline_terminated() -> None:
    text = export_openapi.render({"b": 1, "a": {"d": 2, "c": 3}})

    assert text == '{\n  "a": {\n    "c": 3,\n    "d": 2\n  },\n  "b": 1\n}\n'


def test_two_exports_of_the_same_application_are_byte_identical(no_environment: None) -> None:
    first = export_openapi.render(export_openapi.build_document())
    second = export_openapi.render(export_openapi.build_document())

    assert first == second


def test_the_default_destination_is_stdout(
    no_environment: None, capsys: pytest.CaptureFixture[str]
) -> None:
    code = export_openapi.main([])
    written = capsys.readouterr().out

    assert code == 0
    assert json.loads(written)["info"]["title"] == "ai-orchestrator backend-api"
    assert written.endswith("}\n")


def test_output_writes_the_document_to_the_named_file(no_environment: None, tmp_path: Path) -> None:
    destination = tmp_path / "contracts" / "openapi.json"
    destination.parent.mkdir()

    code = export_openapi.main(["--output", str(destination)])

    assert code == 0
    assert json.loads(destination.read_text())["paths"]["/api/v1/ping"]


def test_a_failed_export_leaves_the_committed_contract_untouched(
    no_environment: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "openapi.json"
    destination.write_text(SENTINEL)

    def explode() -> dict[str, object]:
        raise RuntimeError("the application could not be built")

    monkeypatch.setattr(export_openapi, "build_document", explode)

    with pytest.raises(RuntimeError):
        export_openapi.main(["--output", str(destination)])

    assert destination.read_text() == SENTINEL


def test_a_failed_export_leaves_no_temporary_file_behind(
    no_environment: None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "openapi.json"
    destination.write_text(SENTINEL)

    def explode(source: object, target: object) -> None:
        raise OSError("disk full")

    # the temporary file is written before this point, so the cleanup path is what runs
    monkeypatch.setattr(export_openapi.os, "replace", explode)

    with pytest.raises(OSError, match="disk full"):
        export_openapi.main(["--output", str(destination)])

    assert [path.name for path in tmp_path.iterdir()] == ["openapi.json"]
