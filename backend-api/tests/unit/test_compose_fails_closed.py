"""Every variable the compose file requires, proved missing one at a time.

`test_compose.py` already runs `docker compose config` with nothing configured and asserts
the project refuses. What it cannot say is *which* variable compose complains about: with
ten required variables missing at once, compose names one of them, and which one is Go map
iteration order — random per process. Some releases print every error and some print the
first (v5.4.0 printed eleven, v5.5.0 printed one, v5.5.1 printed eleven again), so the
reported name is a property of the installed binary, not of this repository.

Removing exactly one variable from the committed contract makes it deterministic. One
missing variable admits one error, so compose has nothing to choose between, and the
assertion holds on every release: this file names the variable, and no other.

The list is read out of `docker-compose.yml` rather than written here, so a service added
later is covered without anyone remembering to add it — which is how `test_compose.py`'s
assertion went stale when story 1.6 added `web-client` and `backend-api` beside `postgres`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT

COMPOSE = REPO_ROOT / "docker-compose.yml"

#: `${VAR:?message}` — the fail-closed form, which is the only form the compose file uses.
#: Comment lines are dropped first: the file explains the form in prose, and a regex cannot
#: tell a reference compose interpolates from one a sentence mentions.
_DECLARATIONS = "\n".join(
    line for line in COMPOSE.read_text().splitlines() if not line.strip().startswith("#")
)
REQUIRED = sorted(set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", _DECLARATIONS)))

#: every reference compose interpolates, guarded or not. `$${VAR}` is escaped — the healthcheck
#: passes it through to the container's shell — so a `$` before the `$` disqualifies a match.
REFERENCED = sorted(set(re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)", _DECLARATIONS)))


def _contract_without(variable: str) -> str:
    """The committed contract, byte for byte, minus the one line that assigns `variable`.

    The file's own text is reused rather than rebuilt from parsed pairs: at least one value
    is single-quoted because it contains shell metacharacters, and re-emitting it would
    change how compose's env-file parser reads it.
    """
    kept = [
        line
        for line in ENV_EXAMPLE.read_text().splitlines()
        if line.partition("=")[0].strip() != variable
    ]
    return "\n".join(kept) + "\n"


def _config(env_file: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        ["docker", "compose", "--env-file", str(env_file), "config", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")},
    )


def test_the_file_requires_the_database_credentials() -> None:
    """A guard on the parametrisation: an empty list would make every test below vacuous."""
    assert {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB"} <= set(REQUIRED)


#: Interpolated bare, because absence is a defined value for it: `${VAR:?}` refuses an empty
#: value too, and `ROOT_TEMPLATES=` means "offer the default list" (Operator instruction
#: 2026-09-22). Named explicitly so a second bare reference still fails below.
UNGUARDED: frozenset[str] = frozenset({"ROOT_TEMPLATES"})


def test_every_reference_is_guarded() -> None:
    """Also a guard: dropping a `:?` would quietly remove that variable from the cases below.

    Read as "no variable is interpolated bare except the ones named above", so a service added
    later cannot arrive with an unguarded reference and no test to say so.
    """
    assert REFERENCED, "nothing is interpolated — the parser is wrong"
    assert set(REFERENCED) - set(REQUIRED) == set(UNGUARDED), sorted(
        set(REFERENCED) - set(REQUIRED) - set(UNGUARDED)
    )
    assert set(REQUIRED) - set(REFERENCED) == set()


#: Both contracts carry the same bare reference, so both have to state the same fallback.
CONTRACTS = (ENV_EXAMPLE, REPO_ROOT / "deploy" / ".env.example")


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_every_unguarded_variable_states_a_default_in_the_contract(contract: Path) -> None:
    """The exception above is only sound while the contract ships a value to fall back to.
    The value is asserted, not just the name: `ROOT_TEMPLATES=` satisfies "is declared" and is
    exactly the undocumented empty string this rules out.
    """
    declared = {
        line.partition("=")[0].strip(): line.partition("=")[2].strip()
        for line in contract.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }

    assert UNGUARDED <= set(declared), sorted(UNGUARDED - set(declared))
    for variable in sorted(UNGUARDED):
        assert declared[variable], f"{variable} is declared with no value in {contract}"


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not on PATH")
@pytest.mark.parametrize("variable", REQUIRED)
def test_removing_one_variable_from_the_contract_refuses_and_names_it(
    variable: str, tmp_path: Path
) -> None:
    """Bare `${VAR}` would interpolate to an empty string and the project would come up."""
    env_file = tmp_path / "one-short.env"
    text = _contract_without(variable)
    assert f"\n{variable}=" not in f"\n{text}", f"{variable} is not declared in {ENV_EXAMPLE}"
    env_file.write_text(text)

    result = _config(env_file)
    output = result.stdout + result.stderr

    assert result.returncode != 0, f"the project loaded without {variable}"
    assert variable in output, output


@pytest.mark.skipif(shutil.which("docker") is None, reason="docker not on PATH")
@pytest.mark.parametrize("variable", REQUIRED)
def test_no_other_variable_is_reported_when_only_one_is_missing(
    variable: str, tmp_path: Path
) -> None:
    """The reason the assertion above is deterministic: nothing else can be complained about.

    If this fails, a variable compose reads is absent from the contract, and the test above
    would be passing on a coincidence rather than on the removal.
    """
    env_file = tmp_path / "one-short.env"
    env_file.write_text(_contract_without(variable))

    result = _config(env_file)
    output = result.stdout + result.stderr
    reported = set(re.findall(r"required variable ([A-Z][A-Z0-9_]*)", output))

    assert reported == {variable}, sorted(reported)
