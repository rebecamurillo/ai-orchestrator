"""The e2e gate has a stack of its own, and refuses any other.

`tests/e2e` writes and never cleans up — `test_projects.py` states it in its own docstring,
`test_schemathesis.py` drives every published operation while authenticated, and
`test_clone_check.py` leaves bare fixture repositories and base clones under `WORK_DIR`. That
is right for a suite that has to pass twice against the same stack. What it makes wrong is
running the gate against the stack you develop in, which is what `make e2e-api` did when it
attached to whatever `make up` had left running.

Two mechanisms answer that, and this module asserts both. `make e2e` builds the gate a
compose project of its own — its own database, its own `work` and `agent-home` volumes, its
own published ports — and destroys it with `down -v` however the run ends. And
`scripts/check_e2e_target.sh` refuses to start pytest against a database whose name is not
the gate's, so pointing it at the dev stack fails before a connection is opened rather than
after a hundred rows are written.

Nothing here needs a docker daemon: the overlay is asserted as a document, the way
`test_compose.py` asserts the base file, and the recipes through `make -n`. What a daemon
would add is proof that the merged project starts, which is what `make e2e` itself is.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from cryptography.fernet import Fernet

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

OVERLAY = REPO_ROOT / "docker-compose.e2e.yml"
MAKEFILE = REPO_ROOT / "Makefile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
GUARD = REPO_ROOT / "scripts" / "check_e2e_target.sh"
GENERATOR = REPO_ROOT / "scripts" / "generate-env.sh"

#: The database name the gate builds for itself, and the only shape the guard accepts.
E2E_DATABASE = "orchestrator_e2e"
DEV_DATABASE = "orchestrator"
POSTGRES_CONTAINER_PORT = "5432"

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")
needs_bash = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("openssl") is None,
    reason="bash and openssl are what the generator is written in",
)


class _Tolerant(yaml.SafeLoader):
    """A loader that reads compose's merge tags instead of refusing the document.

    `!override` is meaningful to compose and meaningless to YAML; dropping it here keeps the
    structural assertions readable, and the tag itself is asserted as text below — it has to
    be, since parsing is exactly what discards it.
    """


def _keep_the_node(loader: yaml.Loader, _suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    return loader.construct_scalar(node)


_Tolerant.add_multi_constructor("!", _keep_the_node)


@pytest.fixture(scope="module")
def overlay_text() -> str:
    assert OVERLAY.is_file(), f"{OVERLAY} does not exist"
    return OVERLAY.read_text()


@pytest.fixture(scope="module")
def overlay(overlay_text: str) -> dict[str, Any]:
    # `_Tolerant` derives from `SafeLoader`; the tags it accepts construct nothing.
    document = yaml.load(overlay_text, Loader=_Tolerant)
    assert isinstance(document, dict)
    return document


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    # MAKEFLAGS from the outer make running this suite would leak -n/-s into the child and
    # make every assertion below vacuous.
    env = {**os.environ, "MAKEFLAGS": "", "MFLAGS": ""}
    return subprocess.run(  # fixed argv, no shell
        ["make", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _recipe(target: str) -> str:
    result = _make("-n", target)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _guard(url: str | None, **environment: str) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key != "DATABASE_URL"}
    if url is not None:
        env["DATABASE_URL"] = url
    env.update(environment)
    return subprocess.run(  # fixed argv, no shell
        [str(GUARD)], capture_output=True, text=True, cwd=REPO_ROOT, env=env, check=False
    )


def _url(database: str) -> str:
    return f"postgresql+psycopg://orchestrator:secret@127.0.0.1:5432/{database}"


# ── the overlay: one stack per environment ───────────────────────────────────


def test_the_overlay_publishes_postgres_somewhere_the_dev_stack_is_not() -> None:
    """`docker-compose.yml` writes `127.0.0.1:5432:5432` literally, and a frozen test pins it
    there — so a second project can only exist if the overlay moves the published half."""
    published = str(
        yaml.load(OVERLAY.read_text(), Loader=_Tolerant)["services"]["postgres"]["ports"][0]
    )
    host, container = published.rsplit(":", 1)

    assert container == POSTGRES_CONTAINER_PORT, published
    assert not host.endswith(f":{POSTGRES_CONTAINER_PORT}"), published
    assert host.startswith("127.0.0.1:"), published


def test_the_overlay_replaces_the_lists_it_touches(overlay_text: str) -> None:
    """Without `!override` compose appends, both port lines are published, and the collision
    the overlay exists to remove comes back — silently, at `up` time."""
    for line in ("ports: !override", "env_file: !override"):
        assert line in overlay_text, line


def test_the_gate_stack_reads_the_gate_environment(overlay: dict[str, Any]) -> None:
    """`docker-compose.yml` names `.env` — the dev environment, with the dev database and the
    dev credentials in it. The gate's containers must read their own file instead."""
    env_file = overlay["services"]["backend-api"]["env_file"]

    assert [entry["path"] for entry in env_file] == [".env.e2e"]


def test_a_missing_gate_environment_refuses_rather_than_starting_on_nothing(
    overlay: dict[str, Any],
) -> None:
    """`required: false` here would start a container configured from nowhere (hard rule 7)."""
    assert overlay["services"]["backend-api"]["env_file"][0]["required"] is True


def test_the_overlay_publishes_no_application_port_of_its_own(overlay: dict[str, Any]) -> None:
    """`BACKEND_API_PORT` and `WEB_CLIENT_PORT` are already interpolated by the base file, so
    `.env.e2e` moves them by holding different values. Repeating them here would be a second
    place to change and a second place to forget."""
    assert "ports" not in overlay["services"].get("backend-api", {})
    assert "web-client" not in overlay["services"]


# ── the target: create, run, destroy ─────────────────────────────────────────


@needs_make
def test_the_gate_stack_is_a_compose_project_of_its_own() -> None:
    """Docker namespaces volumes by project: the project name is what separates the two
    databases, the two `work` trees and the two agent homes."""
    recipe = _recipe("e2e")

    assert "-p aio-e2e" in recipe
    assert "--env-file .env.e2e" in recipe
    assert "-f docker-compose.e2e.yml" in recipe


@needs_make
def test_the_gate_stack_is_destroyed_with_its_volumes_however_the_run_ends() -> None:
    """`down` alone would keep `pgdata`, and the next run would inherit the rows this one
    left. The trap is what makes a failed run clean up as thoroughly as a green one."""
    recipe = _recipe("e2e")

    assert "down -v" in recipe
    assert "trap" in recipe
    assert "EXIT" in recipe


@needs_make
def test_the_gate_stack_is_built_from_the_source_in_the_checkout() -> None:
    """Without `--build` the gate answers for yesterday's image."""
    assert "--build" in _recipe("e2e")


@needs_make
def test_the_target_runs_the_gate_rather_than_copying_it() -> None:
    """One definition of the gate, in `e2e-api`; a copy here is a copy that drifts."""
    assert "make e2e-api" in _recipe("e2e")


def test_a_dry_run_of_the_target_starts_nothing() -> None:
    """Make executes any recipe line holding the literal `$(MAKE)` even under `-n`, so
    written that way `make -n e2e` would start containers instead of printing what it would
    do — and so would every assertion in this module."""
    body = MAKEFILE.read_text().split("\ne2e:\n", 1)[1].split("\n\n", 1)[0]

    assert "$(SUBMAKE)" in body
    assert "$(MAKE)" not in body


@needs_make
def test_the_gate_itself_runs_the_guard_first() -> None:
    """`make e2e-api` stays the gate CI runs and the one a shell can run; what it gains is a
    refusal before pytest opens a connection."""
    recipe = _recipe("e2e-api")

    assert "check_e2e_target.sh" in recipe
    assert recipe.index("check_e2e_target.sh") < recipe.index("pytest tests/e2e")


@needs_make
def test_the_dev_stack_is_untouched_by_any_of_this() -> None:
    """`make up` and `make down` still act on the environment the operator selected."""
    for target in ("up", "down"):
        assert "aio-e2e" not in _recipe(target)


# ── the guard: the gate names the only database it may write to ──────────────


def test_the_guard_accepts_the_database_the_gate_builds() -> None:
    assert _guard(_url(E2E_DATABASE)).returncode == 0


def test_the_guard_refuses_the_database_you_develop_against() -> None:
    result = _guard(_url(DEV_DATABASE))

    assert result.returncode != 0
    assert DEV_DATABASE in result.stderr
    assert "make e2e" in result.stderr


def test_the_guard_refuses_a_database_url_it_cannot_read() -> None:
    result = _guard(None)

    assert result.returncode != 0
    assert "DATABASE_URL" in result.stderr


def test_the_guard_never_prints_the_credential_it_read() -> None:
    """A refusal names the database, and a URL carries the password next to it."""
    result = _guard(_url(DEV_DATABASE))

    assert "secret" not in result.stdout + result.stderr


def test_a_query_string_does_not_hide_the_database_name() -> None:
    result = _guard(f"{_url(DEV_DATABASE)}?sslmode=require")

    assert result.returncode != 0
    assert DEV_DATABASE in result.stderr


def test_the_deliberate_override_warns_rather_than_going_quiet() -> None:
    """Pointing the suite at a stack you keep is allowed and is never silent."""
    result = _guard(_url(DEV_DATABASE), E2E_ALLOW_SHARED_STACK="1")

    assert result.returncode == 0
    assert "warning" in result.stderr


# ── the environment files: one per environment, generated, never committed ───


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    """The two files the generator reads, in the layout it resolves from its own location."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(GENERATOR, tmp_path / "scripts" / GENERATOR.name)
    shutil.copy(ENV_EXAMPLE, tmp_path / ".env.example")
    return tmp_path


def _generate(checkout: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        [str(checkout / "scripts" / GENERATOR.name), *args],
        capture_output=True,
        text=True,
        cwd=checkout,
        check=False,
    )


@needs_bash
def test_the_gate_environment_names_a_database_of_its_own(checkout: Path) -> None:
    assert _generate(checkout, "e2e").returncode == 0
    written = parse_env_example(checkout / ".env.e2e")

    assert written["POSTGRES_DB"] == E2E_DATABASE
    assert written["DATABASE_URL"].endswith(f"/{E2E_DATABASE}")


@needs_bash
def test_the_gate_environment_names_its_own_compose_project(checkout: Path) -> None:
    _generate(checkout, "e2e")
    written = parse_env_example(checkout / ".env.e2e")

    assert written["COMPOSE_PROJECT_NAME"] == "aio-e2e"
    assert written["E2E_POSTGRES_PORT"] != POSTGRES_CONTAINER_PORT


@needs_bash
def test_the_gate_environment_binds_ports_the_dev_stack_does_not(checkout: Path) -> None:
    """The two stacks run at once, or the gate is something you stop working to run."""
    _generate(checkout, "e2e")
    written = parse_env_example(checkout / ".env.e2e")
    contract = parse_env_example(ENV_EXAMPLE)

    for variable in ("BACKEND_API_PORT", "WEB_CLIENT_PORT"):
        assert written[variable] != contract[variable], variable


@needs_bash
def test_the_gate_environment_can_actually_encrypt(checkout: Path) -> None:
    """The committed placeholder is not a Fernet key: with it every write to
    /api/v1/projects answers 500 and the suite would pass over an API that never worked."""
    _generate(checkout, "e2e")
    written = parse_env_example(checkout / ".env.e2e")

    Fernet(written["ORCHESTRATOR_SECRET_KEY"].encode())


@needs_bash
def test_the_gate_environment_holds_no_real_credential(checkout: Path) -> None:
    """AD-5: the disposable stack talks to no gateway and clones no private repository, so
    the git and gateway placeholders stay exactly as committed."""
    _generate(checkout, "e2e")
    written = parse_env_example(checkout / ".env.e2e")
    contract = parse_env_example(ENV_EXAMPLE)

    for variable in ("GITHUB_TOKEN", "LITELLM_API_KEY", "LITELLM_SPEND_KEY", "LANGFUSE_SECRET_KEY"):
        assert written[variable] == contract[variable], variable


@needs_bash
def test_the_gate_environment_declares_every_variable_the_contract_does(checkout: Path) -> None:
    """Generated from `.env.example`, so a variable added to the contract is never dropped."""
    _generate(checkout, "e2e")
    written = parse_env_example(checkout / ".env.e2e")

    assert set(parse_env_example(ENV_EXAMPLE)) <= set(written)


@needs_bash
def test_an_existing_gate_environment_is_never_rewritten(checkout: Path) -> None:
    """Ports and keys an operator changed survive the next `make e2e`."""
    _generate(checkout, "e2e")
    first = (checkout / ".env.e2e").read_text()
    result = _generate(checkout, "e2e")

    assert result.returncode == 0
    assert (checkout / ".env.e2e").read_text() == first


@needs_bash
def test_the_dev_environment_names_its_compose_project(checkout: Path) -> None:
    """Without it compose falls back to the directory name, so a second clone of this
    repository would silently be a different project with empty volumes."""
    assert _generate(checkout, "dev").returncode == 0

    assert parse_env_example(checkout / ".env")["COMPOSE_PROJECT_NAME"] == "aio-dev"


@needs_bash
def test_the_dev_environment_keeps_the_values_it_already_holds(checkout: Path) -> None:
    """The operator's `.env` holds real tokens; it is completed, never rewritten."""
    (checkout / ".env").write_text("ORCHESTRATOR_TOKEN=the-one-i-already-had\n")
    _generate(checkout, "dev")
    written = parse_env_example(checkout / ".env")

    assert written["ORCHESTRATOR_TOKEN"] == "the-one-i-already-had"
    assert written["COMPOSE_PROJECT_NAME"] == "aio-dev"


@needs_bash
def test_naming_the_dev_project_twice_does_not_name_it_twice(checkout: Path) -> None:
    """`parse_env_example` raises on a duplicate, which is what makes this assertable."""
    _generate(checkout, "dev")
    assert _generate(checkout, "dev").returncode == 0

    assert parse_env_example(checkout / ".env")["COMPOSE_PROJECT_NAME"] == "aio-dev"


# ── the pipeline runs the same gate against the same shape of database ───────


def test_the_pipeline_builds_the_gate_a_database_of_its_own() -> None:
    """CI and a shell run one gate; the guard would refuse the pipeline too if it did not."""
    assert f"POSTGRES_DB={E2E_DATABASE}" in WORKFLOW.read_text()
