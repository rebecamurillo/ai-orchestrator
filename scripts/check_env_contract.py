#!/usr/bin/env python
"""Prove that `.env.example` and the typed settings module say the same thing (AD-20).

`make lint` runs this. It fails in three directions: a `Settings` field with no line in
the contract, a contract variable with no field, and an allowlisted variable that has been
deleted from the contract (compose and the web-client still need it).

This module imports `orchestrator.infrastructure.settings`, so it runs inside the backend
virtualenv — `make lint` invokes it as `uv run --directory backend-api python
../scripts/check_env_contract.py`, which is what puts the package on the path.

It is also the single parser for the contract file: the unit-test fixtures import
`parse_env_example` from here rather than re-implementing it, so the gate and the tests can
never disagree about what the file says.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from orchestrator.infrastructure.settings import Settings

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_EXAMPLE = REPO_ROOT / ".env.example"
DEFAULT_DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"

# Read by docker compose or the web-client; never by a backend-api module.
COMPOSE_ONLY_VARIABLES = {
    "ORCHESTRATOR_SESSION_SECRET",
    "BACKEND_API_URL",
    "WEB_CLIENT_PORT",
    "ROOT_TEMPLATES",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
}

# Read by `deploy/docker-compose.yml` alone; never by the application, never valid in the
# root contract (adding one there would fail this check as a field-less variable).
DEPLOY_ONLY_VARIABLES = {
    "IMAGE_TAG",
    "COMPOSE_PROJECT_NAME",
    "BIND_ADDRESS",
}


class ContractError(Exception):
    """The contract file cannot be read as a contract."""


def _strip_value(value: str) -> str:
    """Take the value, dropping a trailing comment but never a `#` inside the value."""
    value = value.strip()
    if value[:1] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]
    marker = value.find("  #")
    if marker != -1:
        value = value[:marker]
    return value.strip()


def parse_env_example(path: Path = DEFAULT_ENV_EXAMPLE) -> dict[str, str]:
    """Return the `NAME=value` pairs of a contract file.

    Raises `ContractError` on a duplicate or non-uppercase name: both are invisible to a
    naive reader but meaningful at runtime, since `Settings` is case-insensitive and
    compose silently lets the last duplicate win.
    """
    if not path.is_file():
        raise ContractError(f"{path}: contract file not found")

    pairs: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().removeprefix("export ").strip()
        if not name.isidentifier():
            continue
        if not name.isupper():
            raise ContractError(f"{path.name}:{number}: {name}: contract names are uppercase")
        if name in pairs:
            raise ContractError(f"{path.name}:{number}: {name}: declared twice")
        pairs[name] = _strip_value(value)
    return pairs


def settings_variables() -> set[str]:
    """The environment variable names `Settings` reads."""
    return {name.upper() for name in Settings.model_fields}


def env_example_variables(path: Path = DEFAULT_ENV_EXAMPLE) -> set[str]:
    """The variable names declared by the contract file."""
    return set(parse_env_example(path))


def compare(settings: set[str], contract: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (fields not in the contract, contract variables with no field, lost allowlist)."""
    missing = sorted(settings - contract)
    extra = sorted(contract - settings - COMPOSE_ONLY_VARIABLES)
    absent = sorted(COMPOSE_ONLY_VARIABLES - contract)
    return missing, extra, absent


def compare_deploy(contract: set[str], deploy: set[str]) -> tuple[list[str], list[str], list[str]]:
    """Return (contract variables the deploy copy lost, stray deploy variables, lost deploy-only).

    `deploy/.env.example` is the consumer's copy of the contract: every root variable plus
    the deploy-only block, nothing else. Hard rule 8 says a new setting lands in
    `.env.example`; this comparison is what extends that rule to the copy a consumer
    actually fills in.
    """
    missing = sorted(contract - deploy)
    stray = sorted(deploy - contract - DEPLOY_ONLY_VARIABLES)
    absent = sorted(DEPLOY_ONLY_VARIABLES - deploy)
    return missing, stray, absent


def check_deploy(contract: set[str], deploy_path: Path, name: str) -> int:
    """Hold the consumer copy to the contract, silently on agreement.

    `test_env_contract.py` pins the root success line as the whole of stdout, so this
    check writes nothing when the copy agrees and stderr lines when it drifts.
    """
    try:
        deploy = env_example_variables(deploy_path)
    except ContractError as error:
        sys.stderr.write(f"{error}\n")
        return 1

    lost, stray, gone = compare_deploy(contract, deploy)
    deploy_name = f"deploy/{deploy_path.name}"

    for variable in lost:
        sys.stderr.write(f"{variable}: in {name} but missing from {deploy_name}\n")
    for variable in stray:
        sys.stderr.write(f"{variable}: in {deploy_name} but not in {name} or the deploy set\n")
    for variable in gone:
        sys.stderr.write(f"{variable}: deploy-only variable missing from {deploy_name}\n")

    if lost or stray or gone:
        sys.stderr.write(
            f"deploy contract: {len(lost)} lost, {len(stray)} stray, {len(gone)} gone — "
            f"{name} and {deploy_name} change together (hard rule 8)\n"
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the AD-20 environment contract.")
    parser.add_argument("--env-example", type=Path, default=DEFAULT_ENV_EXAMPLE)
    parser.add_argument("--deploy-env-example", type=Path, default=DEFAULT_DEPLOY_ENV_EXAMPLE)
    args = parser.parse_args(argv)

    try:
        contract = env_example_variables(args.env_example)
    except ContractError as error:
        sys.stderr.write(f"{error}\n")
        return 1

    fields = settings_variables()
    missing, extra, absent = compare(fields, contract)
    name = args.env_example.name

    for variable in missing:
        sys.stderr.write(f"{variable}: Settings field has no line in {name}\n")
    for variable in extra:
        sys.stderr.write(f"{variable}: in {name} but no Settings field reads it\n")
    for variable in absent:
        sys.stderr.write(f"{variable}: allowlisted for compose but missing from {name}\n")

    if missing or extra or absent:
        sys.stderr.write(
            f"env contract: {len(missing)} missing, {len(extra)} unexpected, "
            f"{len(absent)} lost — settings and {name} change together (AD-20)\n"
        )
        return 1

    if check_deploy(contract, args.deploy_env_example, name) != 0:
        return 1

    sys.stdout.write(
        f"env contract: {len(fields)} settings fields and {len(contract)} "
        f"{name} variables agree ({len(COMPOSE_ONLY_VARIABLES)} allowlisted)\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
