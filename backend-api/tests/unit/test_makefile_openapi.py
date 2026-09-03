"""The `openapi` gate this story lands, held to the standard 1.1 and 1.2 set.

Root `AGENTS.md` hard rule 1: the commit that retires a target's pending entry adds the
test that the landed gate actually runs. Without this module `openapi` could be dropped
from `PENDING_TARGETS` and left as a recipe that does nothing, and `make test` would still
be green — the gate would have "landed" by disappearing.

`_make` and `_uv_invocations` are imported from the frozen 1.1 module rather than copied.
`_uv_invocations` matches on the executable's basename because `$(UV)` expands to an
absolute path inside `uv run`; a `startswith("uv run")` filter would match nothing and make
every assertion below vacuous. That bug shipped once already.
"""

from __future__ import annotations

import json
import shutil

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import PENDING_TARGETS, _make, _uv_invocations

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

MAKEFILE = REPO_ROOT / "Makefile"
TARGET = "openapi"
CONTRACT = REPO_ROOT / "contracts" / "openapi.json"

# both halves of AD-3: backend-api exports the contract, web-client generates from it
OPENAPI_SUBGATES = (
    "orchestrator.tools.export_openapi",
    "../contracts/openapi.json",
    "gen:api",
)


def _recipe() -> str:
    result = _make("-n", TARGET)

    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_the_target_is_no_longer_pending() -> None:
    """The story that lands a gate is the story that retires its pending entry."""
    assert TARGET not in PENDING_TARGETS


def test_the_target_no_longer_refuses() -> None:
    result = _make("-n", TARGET)

    assert "not available until story" not in result.stdout + result.stderr


def test_the_recipe_actually_invokes_uv() -> None:
    """Guards the assertions below: an empty match list would make them all vacuous."""
    assert _uv_invocations(_recipe())


@pytest.mark.parametrize("subgate", OPENAPI_SUBGATES)
def test_the_recipe_runs_both_halves_of_the_pipeline(subgate: str) -> None:
    assert subgate in _recipe()


def test_the_recipe_runs_the_exporter_inside_the_backend_package() -> None:
    """Without `--directory backend-api` the package is not importable and `../` is wrong."""
    for line in _uv_invocations(_recipe()):
        assert "--directory backend-api" in line, line


def test_the_recipe_refuses_to_re_resolve_the_committed_lockfile() -> None:
    """Without `--locked` the gate could run against a silently re-resolved dependency set."""
    for line in _uv_invocations(_recipe()):
        assert "--locked" in line, line


def test_the_recipe_never_truncates_the_contract_before_building_it() -> None:
    """`> contracts/openapi.json` would empty the committed file even when the export fails."""
    assert "> contracts/openapi.json" not in _recipe()
    assert "--output" in _recipe()


def test_the_target_is_still_declared_phony() -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    assert TARGET in phony.split()


def test_the_exported_contract_is_committed_and_describes_the_api() -> None:
    """A recipe pointing at a file nobody committed would leave web-client ungeneratable."""
    document = json.loads(CONTRACT.read_text())

    assert document["openapi"].startswith("3.")
    assert {"/healthz", "/api/v1/ping"} <= set(document["paths"])
    assert "ProblemDetail" in document["components"]["schemas"]


def test_the_generated_types_are_committed_beside_the_contract() -> None:
    schema = REPO_ROOT / "web-client" / "src" / "api" / "schema.d.ts"

    assert schema.is_file()
    assert "GENERATED" in schema.read_text().splitlines()[0]
