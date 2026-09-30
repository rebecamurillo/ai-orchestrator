"""`deploy/docker-compose.yml` — the consumer stack, held to the base stack's standard.

The base `docker-compose.yml` builds from source and `test_compose_services.py` freezes
that (`build:`, never `image:`). The consumer stack is the opposite by design: it exists
for a machine that has no checkout, so it pulls the two published images and must never
carry a `build:` that would silently fall back to a working tree it does not have.

What is asserted, and why each is worth a test rather than a review comment:

- **`image:`, never `build:`.** The whole point of the file. A `build:` stanza would make
  `docker compose up` build from whatever directory the bundle was extracted into.
- **The images are the GHCR names the release workflow pushes, pinned by `IMAGE_TAG`,
  fail-closed.** A bare `${IMAGE_TAG}` interpolates empty and `docker compose pull` would
  ask the registry for `backend-api:` — refused, but with a worse message than compose's.
- **AD-5 unchanged**: the web-client still receives exactly four variables; the backend
  still reads the whole contract, now `required: true` because there is no application
  fallback that names missing fields better than an absent file does.
- **postgres publishes no port.** The consumer machine's own 5432 is not this stack's to
  take (hard rule 9's spirit); nothing outside the compose network needs the database.
- **The application ports bind `${BIND_ADDRESS:-127.0.0.1}`.** Loopback by default; the
  variable is the one deliberate opening, documented in deploy/README.md.
- **Production posture is carried, not overlaid**: query-probe on postgres, rotated logs,
  `restart: always` — docker-compose.prod.yml states the reasons.

The text assertions read the file directly, for the reason `test_compose.py` gives: no
YAML library is a declared dependency of this component.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.conftest import REPO_ROOT, parse_env_example
from tests.unit.test_compose import _block, _names
from tests.unit.test_compose_services import (
    WEB_CLIENT_DEFAULTED,
    WEB_CLIENT_OPTIONAL,
    WEB_CLIENT_SECRETS,
    WEB_CLIENT_VARIABLES,
    mapping_keys,
)

DEPLOY_COMPOSE = REPO_ROOT / "deploy" / "docker-compose.yml"
DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"

APP_SERVICES = ("backend-api", "web-client")
EVERY_SERVICE = ("postgres", *APP_SERVICES)

IMAGE_NAMESPACE = "ghcr.io/optimai-labs/ai-orchestrator"

#: Named volumes the stack declares — the same three as the base stack.
VOLUMES = ("pgdata", "work", "agent-home")


def compose_text() -> str:
    assert DEPLOY_COMPOSE.is_file(), f"{DEPLOY_COMPOSE} is missing"
    kept = [
        line for line in DEPLOY_COMPOSE.read_text().splitlines() if not line.strip().startswith("#")
    ]
    return "\n".join(kept) + "\n"


def service(name: str) -> str:
    """The lines indented under one service, as one string."""
    block = _block(compose_text(), "services")
    start = next(i for i, line in enumerate(block) if line.rstrip() == f"  {name}:")
    body: list[str] = []
    for line in block[start + 1 :]:
        if line.strip() and not line.startswith("    "):
            break
        body.append(line)
    assert body, f"{name}: empty service block"
    return "\n".join(body) + "\n"


# ── the services exist, and are pulled rather than built ─────────────────────


@pytest.mark.parametrize("name", EVERY_SERVICE)
def test_the_service_is_declared(name: str) -> None:
    assert name in _names(_block(compose_text(), "services"))


@pytest.mark.parametrize("name", APP_SERVICES)
def test_the_application_service_is_pulled_not_built(name: str) -> None:
    body = service(name)

    assert "image:" in body
    assert "build:" not in body


@pytest.mark.parametrize("name", APP_SERVICES)
def test_the_image_is_the_published_name_pinned_by_the_release_tag(name: str) -> None:
    """The name the release workflow pushes, and `:?` so an unset tag refuses rather than
    interpolating to an untagged pull."""
    assert f"image: {IMAGE_NAMESPACE}/{name}:${{IMAGE_TAG:?" in service(name)


def test_the_database_image_is_the_same_major_as_the_base_stack() -> None:
    assert "image: postgres:18" in service("postgres")


# ── AD-5, unchanged by the packaging ─────────────────────────────────────────


# The deploy bundle carries the same five the dev stack does (Operator instruction 2026-09-22).
def test_the_web_client_receives_exactly_the_variables_it_needs() -> None:
    assert mapping_keys(service("web-client"), "environment") == (
        WEB_CLIENT_VARIABLES | WEB_CLIENT_OPTIONAL
    )


@pytest.mark.parametrize(
    "variable", ["GITHUB_TOKEN", "LITELLM_SPEND_KEY", "LITELLM_API_KEY", "DATABASE_URL"]
)
def test_the_web_client_never_sees_a_credential_it_has_no_use_for(variable: str) -> None:
    assert variable not in service("web-client"), f"{variable} reaches the browser's origin"


def test_the_backend_reads_the_whole_contract_and_requires_it() -> None:
    """`required: false` on the base stack exists so `docker compose config` validates on
    an unconfigured checkout; a consumer stack with no `.env` has nothing to validate."""
    body = service("backend-api")

    assert "env_file:" in body
    assert ".env" in body
    assert "required: true" in body


def test_the_web_client_reads_no_env_file() -> None:
    assert "env_file" not in service("web-client")


# ── exposure: loopback by default, one deliberate opening ────────────────────


def test_postgres_publishes_no_port() -> None:
    """Only backend-api reaches it, over the compose network; a published 5432 would
    collide with whatever the consumer machine already runs."""
    assert "ports:" not in service("postgres")


@pytest.mark.parametrize("name", APP_SERVICES)
def test_the_application_port_binds_the_bind_address_defaulting_to_loopback(name: str) -> None:
    assert '- "${BIND_ADDRESS:-127.0.0.1}:' in service(name), name


# ── the two tiers, the same split the base stack takes ───────────────────────
#
# Operator decision 2026-09-20, two-tier configuration contract; reaffirmed 2026-09-30:
# `${VAR:?}` is the secret tier's property. A consumer stack that refused to render because
# nobody spelled `WORK_DIR=/work` is the crash-loop that decision removes; a consumer stack
# that came up with a blank `ORCHESTRATOR_TOKEN` is the one it must not create. `IMAGE_TAG`
# is required here and nowhere else: this file is the one that pulls rather than builds.

_DECLARATIONS = "\n".join(
    line for line in DEPLOY_COMPOSE.read_text().splitlines() if not line.strip().startswith("#")
)
REQUIRED = sorted(set(re.findall(r"\$\{([A-Z][A-Z0-9_]*):\?", _DECLARATIONS)))
REFERENCED = sorted(set(re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)", _DECLARATIONS)))
DEFAULTS: dict[str, str] = dict(
    re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*):-([^}]*)\}", _DECLARATIONS)
)

#: The base stack's three secrets, plus the release tag this file exists to pin.
DEPLOY_REQUIRED = frozenset(
    {"ORCHESTRATOR_TOKEN", "ORCHESTRATOR_SESSION_SECRET", "POSTGRES_PASSWORD", "IMAGE_TAG"}
)

#: `${ROOT_TEMPLATES:-}` is deliberately empty — the web-client's own default list.
EMPTY_DEFAULT = frozenset({"ROOT_TEMPLATES"})


def test_the_required_set_is_exactly_the_stack_secrets_and_the_image_tag() -> None:
    assert set(REQUIRED) == set(DEPLOY_REQUIRED)


def test_every_reference_is_one_tier_or_the_other() -> None:
    """A bare `${VAR}` interpolates to an empty string and the stack would start misconfigured."""
    assert REFERENCED, "nothing is interpolated — the parser is wrong"
    assert set(REFERENCED) == set(REQUIRED) | set(DEFAULTS), sorted(
        set(REFERENCED) ^ (set(REQUIRED) | set(DEFAULTS))
    )
    assert set(REQUIRED) & set(DEFAULTS) == set()


def test_every_default_is_the_value_the_consumer_contract_declares() -> None:
    """A consumer with a minimal `.env` must get the stack `deploy/.env.example` describes."""
    contract = parse_env_example(DEPLOY_ENV_EXAMPLE)
    checked = {name: value for name, value in DEFAULTS.items() if name not in EMPTY_DEFAULT}

    assert checked, "nothing carries a default — the parser is wrong"
    for name, default in sorted(checked.items()):
        assert name in contract, f"{name} has a compose default but no contract line"
        assert default == contract[name], (
            f"{name}: compose {default!r}, contract {contract[name]!r}"
        )


@pytest.mark.parametrize("variable", sorted(WEB_CLIENT_SECRETS))
def test_each_web_client_credential_fails_closed(variable: str) -> None:
    assert f"${{{variable}:?" in service("web-client"), variable


@pytest.mark.parametrize("variable", sorted(WEB_CLIENT_DEFAULTED))
def test_each_non_secret_web_client_variable_defaults_to_the_consumer_contract_value(
    variable: str,
) -> None:
    default = parse_env_example(DEPLOY_ENV_EXAMPLE)[variable]

    assert f"${{{variable}:-{default}}}" in service("web-client"), variable


# ── the production posture, carried directly ─────────────────────────────────


def test_postgres_is_probed_with_a_query_not_pg_isready() -> None:
    """`pg_isready` exits 0 against a missing database — docker-compose.prod.yml's reason."""
    body = service("postgres")

    assert "select 1" in body
    assert "pg_isready" not in body


@pytest.mark.parametrize("name", EVERY_SERVICE)
def test_the_service_restarts_always(name: str) -> None:
    assert "restart: always" in service(name), name


@pytest.mark.parametrize("name", EVERY_SERVICE)
def test_the_service_rotates_its_logs(name: str) -> None:
    """An anchor or an alias of the shared `logging` block; either way the key is present."""
    assert "logging:" in service(name), name


# ── the sandbox posture, carried directly ────────────────────────────────────


def test_the_web_client_is_hardened_and_the_backend_is_not() -> None:
    """Operator decision, 2026-09-11: the backend is the sandbox real agents run in."""
    assert re.search(r"cap_drop:\s*\n\s*- ALL", service("web-client"))
    assert "no-new-privileges:true" in service("web-client")
    assert "cap_drop" not in service("backend-api")


@pytest.mark.parametrize(
    ("name", "dependency"), [("backend-api", "postgres"), ("web-client", "backend-api")]
)
def test_the_service_waits_for_its_dependency_to_be_healthy(name: str, dependency: str) -> None:
    assert re.search(
        rf"depends_on:\s*\n\s*{dependency}:\s*\n\s*condition: service_healthy", service(name)
    )


def test_the_backend_can_reach_the_host_gateway() -> None:
    assert "host.docker.internal:host-gateway" in service("backend-api")


# ── the volumes, mounted where the contract puts them ────────────────────────


@pytest.mark.parametrize("name", VOLUMES)
def test_the_named_volume_is_declared(name: str) -> None:
    assert name in _names(_block(compose_text(), "volumes"))


@pytest.mark.parametrize(
    ("volume", "variable"), [("work", "WORK_DIR"), ("agent-home", "AGENT_HOME")]
)
def test_the_volume_is_mounted_where_the_contract_puts_it(volume: str, variable: str) -> None:
    assert f"- {volume}:${{{variable}" in service("backend-api")


# ── still no credential in the file ──────────────────────────────────────────


def test_the_consumer_stack_writes_no_credential_into_the_file() -> None:
    contract = parse_env_example(DEPLOY_ENV_EXAMPLE)
    text = compose_text()

    for variable in ("ORCHESTRATOR_TOKEN", "ORCHESTRATOR_SESSION_SECRET", "LITELLM_API_KEY"):
        assert contract[variable] not in text, variable
