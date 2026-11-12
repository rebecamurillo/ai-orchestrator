"""The product surface the deployment stack tests drive exists in the product (AD-31).

`deploy-tests/stack/` runs only in `deploy.yml`, never in `make test`, so a renamed route or
setting would surface there at the earliest. Worse, the harness writes a stack's `.env` by
replacing lines of the shipped `.env.example` and *appending* any key it does not find: a
setting renamed in the product leaves the stack test running on the default, silently — the
AC-9 queue built on `MAX_ACTIVE_RUNS`, or the AC-9a refusal built on `DBOS_APPLICATION_VERSION`,
would then prove nothing. This module reads the stack tests as source (it never imports or
runs them) and holds every API path they call against `contracts/openapi.json`, and every
variable they write against `deploy/.env.example` and `deploy/release.env`.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

STACK_DIR = REPO_ROOT / "deploy-tests" / "stack"
OPENAPI = REPO_ROOT / "contracts" / "openapi.json"
DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"
RELEASE_ENV = REPO_ROOT / "deploy" / "release.env"

_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")
_DECLARATION = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=", re.MULTILINE)
_PLACEHOLDER = "\x00"


def _stack_modules() -> list[Path]:
    return sorted(STACK_DIR.glob("*.py"))


def _path_literal(node: ast.expr) -> str | None:
    """A string or f-string beginning with `/api/` or `/healthz`, its fields as a placeholder."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        text = node.value
    elif isinstance(node, ast.JoinedStr):
        text = "".join(
            part.value if isinstance(part, ast.Constant) else _PLACEHOLDER for part in node.values
        )
    else:
        return None
    if not text.startswith(("/api/", "/healthz")):
        return None
    return text.split("?", 1)[0]


def _called_paths(source: str) -> set[str]:
    nodes = list(ast.walk(ast.parse(source)))
    # an f-string's literal pieces are Constants of their own; only the whole string counts
    pieces = {id(part) for node in nodes if isinstance(node, ast.JoinedStr) for part in node.values}
    return {
        path
        for node in nodes
        if id(node) not in pieces and (path := _path_literal(node)) is not None
    }


def _written_env_keys(source: str) -> set[str]:
    """Keys of every dict literal whose literal keys are all ENV_STYLE strings (`**` skipped)."""
    keys: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Dict):
            continue
        written = [k for k in node.keys if k is not None]
        literal = [k.value for k in written if isinstance(k, ast.Constant)]
        if literal and len(literal) == len(written):
            if all(isinstance(k, str) and _ENV_KEY.match(k) for k in literal):
                keys.update(literal)
    return keys


def _route_pattern(template: str) -> re.Pattern[str]:
    return re.compile("^" + re.sub(r"\\\{[^/]+?\\\}", "[^/]+", re.escape(template)) + "$")


def _openapi_routes() -> list[re.Pattern[str]]:
    return [_route_pattern(p) for p in json.loads(OPENAPI.read_text())["paths"]]


def _matches(path: str, routes: list[re.Pattern[str]]) -> bool:
    concrete = path.replace(_PLACEHOLDER, "x")
    return any(route.match(concrete) for route in routes)


def _declared_variables() -> set[str]:
    return set(_DECLARATION.findall(DEPLOY_ENV_EXAMPLE.read_text())) | set(
        _DECLARATION.findall(RELEASE_ENV.read_text())
    )


# ── the committed stack tests ───────────────────────────────────────────────


def test_the_stack_tests_exist_to_be_read() -> None:
    names = {p.name for p in _stack_modules()}
    assert {"harness.py", "conftest.py"} <= names
    assert any(n.startswith("test_") for n in names)


@pytest.mark.parametrize("module", _stack_modules(), ids=lambda p: p.name)
def test_every_api_path_a_stack_test_calls_is_a_route(module: Path) -> None:
    routes = _openapi_routes()
    missing = sorted(
        p.replace(_PLACEHOLDER, "{…}")
        for p in _called_paths(module.read_text())
        if not _matches(p, routes)
    )
    assert missing == [], f"{module.name} calls paths the contract does not hold: {missing}"


@pytest.mark.parametrize("module", _stack_modules(), ids=lambda p: p.name)
def test_every_variable_a_stack_test_writes_is_declared(module: Path) -> None:
    declared = _declared_variables()
    undeclared = sorted(_written_env_keys(module.read_text()) - declared)
    assert undeclared == [], (
        f"{module.name} writes variables neither deploy/.env.example nor deploy/release.env "
        f"declares, so the stack would run on their defaults: {undeclared}"
    )


def test_the_variables_the_survival_proofs_rest_on_are_declared() -> None:
    declared = _declared_variables()
    assert {"MAX_ACTIVE_RUNS", "ORCH_TEST_MODE", "COMPOSE_PROJECT_NAME"} <= declared
    assert "DBOS_APPLICATION_VERSION" in set(_DECLARATION.findall(RELEASE_ENV.read_text()))


# ── the readers themselves, on sources this module owns ─────────────────────


def test_called_paths_reads_constants_and_fstrings_and_drops_the_query() -> None:
    source = (
        'a = "/api/v1/version"\n'
        'b = f"/api/v1/runs/{run_id}/signals"\n'
        'c = "/healthz"\n'
        'd = "/api/v1/runs?status=done"\n'
        'e = "not/a/path"\n'
        'f = f"{base}/api/v1/runs"\n'
    )
    assert _called_paths(source) == {
        "/api/v1/version",
        f"/api/v1/runs/{_PLACEHOLDER}/signals",
        "/healthz",
        "/api/v1/runs",
    }


def test_route_matching_accepts_templates_and_refuses_unknown_and_extra_segments() -> None:
    routes = [_route_pattern("/api/v1/runs/{run_id}/signals"), _route_pattern("/healthz")]
    assert _matches(f"/api/v1/runs/{_PLACEHOLDER}/signals", routes)
    assert _matches("/healthz", routes)
    assert not _matches("/api/v1/runs/signals", routes)
    assert not _matches(f"/api/v1/runs/{_PLACEHOLDER}/signals/x", routes)
    assert not _matches("/api/v1/run", routes)


def test_written_env_keys_takes_env_style_dicts_only() -> None:
    source = (
        'a = {"MAX_ACTIVE_RUNS": "2", "ORCH_TEST_MODE": "1"}\n'
        'b = {"name": "x", "status": "done"}\n'
        'c = {"MIXED": 1, "lower": 2}\n'
        'd = {**other, "SPREAD_KEY": "v"}\n'
        "e = {}\n"
    )
    assert _written_env_keys(source) == {"MAX_ACTIVE_RUNS", "ORCH_TEST_MODE", "SPREAD_KEY"}


def test_declarations_include_commented_out_lines() -> None:
    text = "FOO=1\n# BAR=  # optional\nnot a line\n  BAZ=\n"
    assert set(_DECLARATION.findall(text)) == {"FOO", "BAR", "BAZ"}
