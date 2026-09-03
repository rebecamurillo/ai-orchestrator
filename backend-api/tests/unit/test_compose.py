"""The database service this story lands.

Story 1.6 adds `web-client` and `backend-api` and makes `make up` real. Everything asserted
here is a property of the `postgres` service itself, so it keeps holding when that happens —
a test that said "postgres is the only service" would be a trap, since anchors are read-only
and 1.6 could not fix it.

Three properties are worth asserting mechanically:

- **The data volume is mounted where `postgres:18` actually keeps it.** The image declares
  its volume at `/var/lib/postgresql` with `PGDATA=/var/lib/postgresql/18/docker`, not at
  the pre-18 `/var/lib/postgresql/data`. Mounting the old path silently gives a database
  that loses its contents.
- **Interpolation fails closed.** Bare `${VAR}` becomes an empty string when the variable is
  unset and postgres starts misconfigured; `${VAR:?message}` refuses (hard rule 7).
- **The file is valid.** Substring assertions cannot see a misspelt key, so `docker compose
  config` is run over it when docker is available. It validates keys, not every value —
  `restart: unless-stoped` passes it — so the values that matter are asserted here too.

The text assertions read the file directly rather than through a YAML library, because no
such library is a declared dependency of this component.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

COMPOSE = REPO_ROOT / "docker-compose.yml"

SERVICE = "postgres"
DATA_VOLUME = "pgdata:/var/lib/postgresql"
DATABASE_VARIABLES = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")


@pytest.fixture(scope="module")
def compose_text() -> str:
    """The file with its comment lines dropped: assertions are about what it declares."""
    assert COMPOSE.is_file(), f"{COMPOSE} is missing"
    kept = [line for line in COMPOSE.read_text().splitlines() if not line.strip().startswith("#")]
    return "\n".join(kept) + "\n"


def _block(text: str, key: str) -> list[str]:
    """The lines indented under a top-level `key:` mapping."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"{key}:")
    block: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        block.append(line)
    return block


def _names(block: list[str]) -> list[str]:
    """The keys declared at the first level of indentation inside a block."""
    return [
        match.group(1)
        for line in block
        if (match := re.fullmatch(r"  ([A-Za-z0-9][\w.-]*):\s*", line.rstrip() + " "))
    ]


# ── what the file declares ───────────────────────────────────────────────────


def test_the_database_service_is_declared(compose_text: str) -> None:
    assert SERVICE in _names(_block(compose_text, "services"))


def test_the_image_is_pinned_to_an_explicit_major_version(compose_text: str) -> None:
    """`postgres` or `postgres:latest` would float; the stack table pins every version."""
    images = re.findall(r"image:\s*(\S+)", compose_text)

    assert images
    for image in images:
        assert re.fullmatch(r"postgres:\d+(\.\d+)*", image), image


def test_the_data_volume_is_mounted_where_postgres_18_keeps_it(compose_text: str) -> None:
    assert DATA_VOLUME in compose_text
    assert "/var/lib/postgresql/data" not in compose_text


def test_the_named_volume_is_declared(compose_text: str) -> None:
    assert "pgdata" in _names(_block(compose_text, "volumes"))


def test_there_is_a_healthcheck(compose_text: str) -> None:
    """`make e2e-api` and 1.6's `depends_on` both need "ready", not "started"."""
    assert "healthcheck:" in compose_text
    assert "pg_isready" in compose_text


def test_the_port_is_published_on_the_loopback_only(compose_text: str) -> None:
    """A bare `5432:5432` would expose the database to every host on the network."""
    published = [line.strip() for line in compose_text.splitlines() if "5432" in line]

    assert published
    for line in published:
        if line.startswith("-"):
            assert "127.0.0.1:5432:5432" in line, line


# ── the credentials come from the environment, not from the file ─────────────


def test_no_credential_is_written_into_the_file(compose_text: str) -> None:
    """Secrets never appear in a compose file (AD-20, hard rule 5)."""
    contract = parse_env_example(ENV_EXAMPLE)

    for name in ("POSTGRES_PASSWORD", "ORCHESTRATOR_TOKEN", "GITHUB_TOKEN"):
        assert contract[name] not in compose_text


@pytest.mark.parametrize("variable", DATABASE_VARIABLES)
def test_the_database_settings_are_interpolated_from_the_env(
    compose_text: str, variable: str
) -> None:
    assert f"${{{variable}" in compose_text


@pytest.mark.parametrize("variable", DATABASE_VARIABLES)
def test_an_unset_variable_refuses_rather_than_interpolating_to_nothing(
    compose_text: str, variable: str
) -> None:
    """Bare `${VAR}` is an empty string when unset, and postgres starts misconfigured."""
    assert f"${{{variable}:?" in compose_text, f"{variable} must use the ${{VAR:?...}} form"


def test_every_variable_the_file_reads_is_in_the_contract(compose_text: str) -> None:
    """A variable compose reads but `.env.example` does not declare would fail silently."""
    contract = set(parse_env_example(ENV_EXAMPLE))
    referenced = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", compose_text))

    assert referenced
    assert referenced <= contract, sorted(referenced - contract)


RESTART_POLICIES = ("no", "always", "on-failure", "unless-stopped")


def test_the_restart_policy_is_one_docker_understands(compose_text: str) -> None:
    """`docker compose config` accepts any string here; a typo would silently mean "no"."""
    policies = re.findall(r"restart:\s*(\S+)", compose_text)

    assert policies
    for policy in policies:
        assert policy in RESTART_POLICIES, policy


# ── the file is valid, not merely full of the right substrings ───────────────


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not on PATH")
def test_the_file_is_a_valid_compose_project() -> None:
    """Every assertion above is a substring; `restart: unless-stoped` would pass them all.

    `--env-file .env.example` resolves the interpolation against the committed contract, so
    the check needs no `.env` and proves the two agree.
    """
    result = subprocess.run(  # fixed argv, no shell
        ["docker", "compose", "--env-file", str(ENV_EXAMPLE), "config", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not on PATH")
def test_the_project_refuses_to_start_with_nothing_configured(tmp_path: Path) -> None:
    """The fail-closed form, proved by running it: no variables, no project.

    Scrubbing the environment is not enough — compose also auto-loads `./.env`, which every
    machine that can actually run the stack has. Pointing `--env-file` at an empty file is
    what makes this deterministic rather than a test that only passes before setup.
    """
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("")

    result = subprocess.run(  # fixed argv, no shell
        ["docker", "compose", "--env-file", str(empty_env), "config", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
    )

    assert result.returncode != 0
    assert "POSTGRES_" in result.stdout + result.stderr
