"""The two application services this story adds, held to the same standard as `postgres`.

`test_compose.py` asserts the properties of the database service and deliberately says
nothing about the other two, because it was written before they existed and an anchor
cannot be revised. This module is the other half. `_block` and `_names` are imported from
it rather than copied, so both modules read the file the same way.

What is asserted, and why each is worth a test rather than a review comment:

- **`build:`, never `image:`.** Beyond taste: `test_compose.py:79` requires every `image:`
  value in the file to match `postgres:<major>`, so an `image:` here breaks a frozen test.
- **The web-client receives exactly four variables (AD-5).** This is the whole of "a
  credential stops at the process that needs it" on the front-end side. A fifth line — the
  database URL, the git token, the spend key — is the failure this test exists to catch.
- **The web-client drops every capability and refuses privilege escalation (NFR-3); the
  backend deliberately does neither.** Operator decision, 2026-09-11: a harness may
  `sudo apt-get` what a target repository's install script needs, wherever real agents
  run — the base stack and production. The e2e overlay re-hardens its own stack
  (`test_compose_sandbox.py` holds that half).
- **`depends_on … service_healthy`**, not `started`: the backend migrates on start, and a
  web-client that came up first would proxy to a socket that is not listening.
- **The volumes the brief names are declared and mounted where the contract says.**
  `agent-home` holds the harness configs and the BMAD stubs; `work` holds the worktrees.
  Mounting either at a literal path would silently diverge from `.env`.

The text assertions read the file directly, for the reason `test_compose.py` gives: no YAML
library is a declared dependency of this component.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example
from tests.unit.test_compose import _block, _names

COMPOSE = REPO_ROOT / "docker-compose.yml"

APP_SERVICES = ("backend-api", "web-client")
EVERY_SERVICE = ("postgres", *APP_SERVICES)

#: AD-5: the whole of what the web-client is given. Not a subset — the set. `ROOT_TEMPLATES`
#: is the fifth and is held separately below: it is not fail-closed (Operator instruction
#: 2026-09-22), so the parametrisation here still covers all four credentials.
WEB_CLIENT_VARIABLES = {
    "ORCHESTRATOR_TOKEN",
    "ORCHESTRATOR_SESSION_SECRET",
    "BACKEND_API_URL",
    "WEB_CLIENT_PORT",
}

#: Given to the web-client too, but interpolated bare.
WEB_CLIENT_OPTIONAL = {"ROOT_TEMPLATES"}

#: The two of the four that are credentials, and so still fail closed. Split out under the
#: Operator decision 2026-09-20, two-tier configuration contract; reaffirmed 2026-09-30.
WEB_CLIENT_SECRETS = {"ORCHESTRATOR_TOKEN", "ORCHESTRATOR_SESSION_SECRET"}

#: The other two: an address and a port, neither a secret, each with the contract's value as
#: its compose fallback. Asserted with the value, which is stronger than the `:?` they used
#: to carry — a default that disagreed with `.env.example` would point the web-client at a
#: backend that is not there.
WEB_CLIENT_DEFAULTED = {
    "BACKEND_API_URL": "http://backend-api:8000",
    "WEB_CLIENT_PORT": "4321",
}

#: Named volumes the stack declares.
VOLUMES = ("pgdata", "work", "agent-home")


def compose_text() -> str:
    assert COMPOSE.is_file(), f"{COMPOSE} is missing"
    kept = [line for line in COMPOSE.read_text().splitlines() if not line.strip().startswith("#")]
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


def mapping_keys(body: str, key: str) -> set[str]:
    """The keys of a mapping declared under `    <key>:` inside a service block."""
    lines = body.splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip() == f"    {key}:")
    found: set[str] = set()
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("      "):
            break
        match = re.fullmatch(r"      ([A-Za-z_][\w.-]*):.*", line.rstrip())
        if match:
            found.add(match.group(1))
    return found


# ── the services exist, and are built rather than pulled ─────────────────────


@pytest.mark.parametrize("name", EVERY_SERVICE)
def test_the_service_is_declared(name: str) -> None:
    assert name in _names(_block(compose_text(), "services"))


@pytest.mark.parametrize("name", APP_SERVICES)
def test_the_application_service_is_built_from_a_dockerfile(name: str) -> None:
    """`image:` here would also break `test_compose.py`'s pinned-version assertion."""
    body = service(name)

    assert "build:" in body
    assert "image:" not in body


@pytest.mark.parametrize(
    ("name", "context", "dockerfile"),
    [
        # the backend needs two trees, so its context is the repository root
        ("backend-api", ".", "backend-api/Dockerfile"),
        # the web-client needs only itself, and its `dockerfile:` is relative to that
        ("web-client", "./web-client", "Dockerfile"),
    ],
)
def test_the_service_names_its_context_and_its_dockerfile(
    name: str, context: str, dockerfile: str
) -> None:
    """The two are one fact: `dockerfile: Dockerfile` resolves only against `./web-client`."""
    body = service(name)

    assert f"context: {context}" in body
    assert f"dockerfile: {dockerfile}" in body


# ── AD-5: the web-client gets five variables, and no other ───────────────────


def test_the_web_client_receives_exactly_the_variables_it_needs() -> None:
    assert mapping_keys(service("web-client"), "environment") == (
        WEB_CLIENT_VARIABLES | WEB_CLIENT_OPTIONAL
    )


def test_the_split_of_the_four_is_exhaustive() -> None:
    """A guard on the two parametrisations below: between them they still cover all four."""
    assert WEB_CLIENT_SECRETS | set(WEB_CLIENT_DEFAULTED) == WEB_CLIENT_VARIABLES
    assert not (WEB_CLIENT_SECRETS & set(WEB_CLIENT_DEFAULTED))


@pytest.mark.parametrize("variable", sorted(WEB_CLIENT_SECRETS))
def test_each_web_client_credential_fails_closed(variable: str) -> None:
    """Bare `${VAR}` is an empty string when unset, and the server would start unauthenticated.

    Revised under the Operator decision 2026-09-20, two-tier configuration contract;
    reaffirmed 2026-09-30: this ran over all four. The two that left are covered by the case
    below, which asserts the *value* of the default they now carry — more than the `:?` form
    said — and the guard above keeps the pair exhaustive.
    """
    assert f"${{{variable}:?" in service("web-client"), variable


@pytest.mark.parametrize(("variable", "default"), sorted(WEB_CLIENT_DEFAULTED.items()))
def test_each_non_secret_web_client_variable_defaults_to_the_contract_value(
    variable: str, default: str
) -> None:
    """Never bare, and never a second opinion about where the backend lives."""
    assert f"${{{variable}:-{default}}}" in service("web-client"), variable
    assert parse_env_example(ENV_EXAMPLE)[variable] == default


def test_the_optional_set_is_the_one_variable_it_was_opened_for() -> None:
    """Bounded by enumeration, not by spelling: a name check like "contains TOKEN" passes for
    `DATABASE_URL`. Adding a second member has to be a visible edit to this line."""
    assert WEB_CLIENT_OPTIONAL == {"ROOT_TEMPLATES"}
    assert not (WEB_CLIENT_OPTIONAL & WEB_CLIENT_VARIABLES)


@pytest.mark.parametrize("variable", sorted(WEB_CLIENT_OPTIONAL))
def test_each_optional_web_client_variable_defaults_to_empty(variable: str) -> None:
    """`${VAR:-}` and nothing else: a default here could disagree with the application's."""
    assert f"{variable}: ${{{variable}:-}}" in service("web-client"), variable


@pytest.mark.parametrize(
    "variable", ["GITHUB_TOKEN", "LITELLM_SPEND_KEY", "LITELLM_API_KEY", "DATABASE_URL"]
)
def test_the_web_client_never_sees_a_credential_it_has_no_use_for(variable: str) -> None:
    assert variable not in service("web-client"), f"{variable} reaches the browser's origin"


def test_the_web_client_reads_no_env_file() -> None:
    """`env_file` is all-or-nothing; it would hand the front-end the whole contract."""
    assert "env_file" not in service("web-client")


def test_the_backend_reads_the_whole_contract() -> None:
    """It is the process that holds every credential, so it is the one given `.env`."""
    body = service("backend-api")

    assert "env_file:" in body
    assert ".env" in body


def test_the_backend_env_file_is_optional_so_config_still_validates_without_one() -> None:
    """`test_compose.py:182` runs `docker compose config` on a machine with no `.env`; a
    required `env_file` would abort it before the interpolation errors it asserts on."""
    assert "required: false" in service("backend-api")


# ── NFR-3 hardening ──────────────────────────────────────────────────────────


def test_the_web_client_drops_every_capability() -> None:
    assert re.search(r"cap_drop:\s*\n\s*- ALL", service("web-client"))


def test_the_web_client_refuses_privilege_escalation() -> None:
    assert "no-new-privileges:true" in service("web-client")


def test_the_backend_is_not_hardened_here() -> None:
    """Operator decision, 2026-09-11 (revising the original NFR-3 assertion): the backend
    is the sandbox real agents run in, so `sudo apt-get` must work in every stack that
    runs them — the base stack and production. The e2e gate's stack is the one that never
    does, and `docker-compose.e2e.yml` re-hardens it; `test_compose_sandbox.py` asserts
    that half, so the hardening moved rather than vanished."""
    body = service("backend-api")

    assert "cap_drop" not in body
    assert "no-new-privileges" not in body


@pytest.mark.parametrize("name", APP_SERVICES)
def test_the_filesystem_is_writable_and_says_so(name: str) -> None:
    """Worktrees and harness configs are written at run time; the brief makes it explicit."""
    assert "read_only: false" in service(name), name


@pytest.mark.parametrize("name", APP_SERVICES)
def test_the_service_has_a_healthcheck(name: str) -> None:
    assert "healthcheck:" in service(name), name


def test_the_backend_healthcheck_probes_healthz() -> None:
    assert "/healthz" in service("backend-api")


def test_the_web_client_healthcheck_probes_the_one_page_that_needs_no_session() -> None:
    """Every other route redirects to `/login` (1.5), so any of them would prove nothing."""
    assert "/login" in service("web-client")


@pytest.mark.parametrize(
    ("name", "dependency"), [("backend-api", "postgres"), ("web-client", "backend-api")]
)
def test_the_service_waits_for_its_dependency_to_be_healthy(name: str, dependency: str) -> None:
    body = service(name)

    assert re.search(rf"depends_on:\s*\n\s*{dependency}:\s*\n\s*condition: service_healthy", body)


def test_the_backend_can_reach_the_host_gateway() -> None:
    """LiteLLM, Langfuse and the model server run on the host, outside compose (AD-11, AD-20)."""
    assert "host.docker.internal:host-gateway" in service("backend-api")


# ── the volumes the brief names ──────────────────────────────────────────────


@pytest.mark.parametrize("name", VOLUMES)
def test_the_named_volume_is_declared(name: str) -> None:
    assert name in _names(_block(compose_text(), "volumes"))


@pytest.mark.parametrize(
    ("volume", "variable"), [("work", "WORK_DIR"), ("agent-home", "AGENT_HOME")]
)
def test_the_volume_is_mounted_where_the_contract_puts_it(volume: str, variable: str) -> None:
    """A literal path here would diverge from `.env` the day either value changed."""
    assert f"- {volume}:${{{variable}" in service("backend-api")


def test_the_web_client_persists_nothing() -> None:
    """It holds no state: the session is a signed cookie, and the contract is generated."""
    assert "volumes:" not in service("web-client")


# ── still no credential in the file ──────────────────────────────────────────


def test_the_new_services_write_no_credential_into_the_file() -> None:
    contract = parse_env_example(ENV_EXAMPLE)
    text = compose_text()

    for variable in ("ORCHESTRATOR_TOKEN", "ORCHESTRATOR_SESSION_SECRET", "LITELLM_API_KEY"):
        assert contract[variable] not in text, variable
