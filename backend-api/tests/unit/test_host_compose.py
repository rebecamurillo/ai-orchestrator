"""The host stack — LiteLLM and Langfuse — as a document.

`host/README.md` says these two run beside the product rather than inside it, reached through
`host.docker.internal`. `host/docker-compose.yml` is one way to run them on a single machine.
It is deliberately a second compose project: the root file is the product, asserted by
`test_compose.py`, and mixing the two would put a `langfuse/langfuse` image into a file whose
every `image:` must be `postgres:<n>`.

What is worth asserting mechanically is the part that would fail silently:

- **The two files stay separate.** A service added here must not appear there, and this file
  must not be pulled into the root project.
- **Nothing is published beyond the loopback,** and nothing collides with a port the product
  stack or oMLX already holds.
- **No credential is written into the file**, and every one it reads fails closed.
- **The ports agree with what `host/README.md` documents**, because the orchestrator's own
  contract points at those numbers and nothing else checks that they match.

The file is read as YAML rather than as text: substring assertions cannot tell a published
port from a comment about one.
"""

from __future__ import annotations

import re
import shutil
import subprocess

import pytest
import yaml

from tests.unit.conftest import REPO_ROOT

HOST_DIR = REPO_ROOT / "host"
HOST_COMPOSE = HOST_DIR / "docker-compose.yml"
HOST_ENV_EXAMPLE = HOST_DIR / ".env.example"
README = HOST_DIR / "README.md"
ROOT_COMPOSE = REPO_ROOT / "docker-compose.yml"

#: what host/README.md's table promises, and what the orchestrator's contract points at
DOCUMENTED_PORTS = {"langfuse-web": 3000, "litellm": 4000}

#: ports the product stack and oMLX already hold on this machine
PRODUCT_POSTGRES_PORT = 5432
TAKEN = {
    4321: "web-client",
    8000: "backend-api and oMLX",
    PRODUCT_POSTGRES_PORT: "the product's postgres",
}


@pytest.fixture(scope="module")
def compose() -> dict:
    assert HOST_COMPOSE.is_file(), f"{HOST_COMPOSE} is missing"
    document = yaml.safe_load(HOST_COMPOSE.read_text())
    assert isinstance(document, dict)
    return document


@pytest.fixture(scope="module")
def services(compose: dict) -> dict:
    return compose["services"]


def published(service: dict) -> list[str]:
    return [str(entry) for entry in service.get("ports", [])]


# ── the two projects stay apart ──────────────────────────────────────────────


def test_the_host_stack_is_its_own_compose_project(compose: dict) -> None:
    """A shared project name would make `make down` stop Langfuse too."""
    assert compose["name"] == "ai-orchestrator-host"


def test_no_service_is_declared_in_both_files(services: dict) -> None:
    product = set(yaml.safe_load(ROOT_COMPOSE.read_text())["services"])

    assert set(services) & product == {"postgres"}, "only the name postgres may repeat"


def test_the_product_file_never_names_the_host_stack() -> None:
    """`test_compose.py` forbids any image but postgres; keep the two from drifting together."""
    text = ROOT_COMPOSE.read_text()

    for name in ("langfuse", "litellm", "clickhouse", "minio"):
        assert name not in text, name


# ── nothing escapes the loopback, nothing collides ───────────────────────────


@pytest.mark.parametrize("name", sorted(DOCUMENTED_PORTS))
def test_the_documented_services_are_declared(services: dict, name: str) -> None:
    assert name in services


def test_every_published_port_is_bound_to_the_loopback(services: dict) -> None:
    """A bare `3000:3000` would offer Langfuse to every host on the network."""
    entries = [entry for service in services.values() for entry in published(service)]

    assert entries
    for entry in entries:
        assert entry.startswith("'127.0.0.1:") or entry.startswith("127.0.0.1:"), entry


def _host_side_ports(compose_path, contract: dict[str, str]) -> set[int]:
    """The host-side port of every published mapping, with `${VAR}` resolved.

    A mapping is `127.0.0.1:<host>:<container>`, where `<host>` may be a literal, a
    `${VAR:-default}`, or a `${VAR:?message}` whose value only `.env` holds — the last is
    resolved from the committed contract, which is what a developer's `.env` is copied from.
    """
    ports: set[int] = set()
    document = yaml.safe_load(compose_path.read_text())
    for service in document["services"].values():
        for entry in [str(item) for item in service.get("ports", [])]:
            body = entry.split("127.0.0.1:", 1)[1]
            spec = body.rsplit(":", 1)[0]
            if spec.isdigit():
                ports.add(int(spec))
                continue
            name = re.match(r"\$\{([A-Z_][A-Z0-9_]*)", spec)
            assert name, entry
            default = re.search(r":-(\d+)\}", spec)
            # compose reads the env file first and falls back to `:-default`, so resolve in
            # that order — the other way round makes the default mask the real value
            resolved = contract.get(name.group(1)) or (default.group(1) if default else None)
            assert resolved and resolved.isdigit(), f"cannot resolve {entry}"
            ports.add(int(resolved))
    return ports


def _contract(path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        name, _, rest = line.partition("=")
        values[name] = rest.split("#")[0].strip().strip("'\"")
    return values


def test_the_two_stacks_can_run_at_the_same_time() -> None:
    """Both compose projects on one machine: no host-side port may appear in both.

    Resolved from the two files rather than from a list kept here, so adding a published
    port to either one is checked against the other instead of against a stale constant.
    """
    product = _host_side_ports(ROOT_COMPOSE, _contract(REPO_ROOT / ".env.example"))
    host = _host_side_ports(HOST_COMPOSE, _contract(HOST_ENV_EXAMPLE))

    assert product, "the product stack publishes nothing — the parser is wrong"
    assert host, "the host stack publishes nothing — the parser is wrong"
    assert not (product & host), sorted(product & host)


def test_the_two_databases_are_reachable_at_different_ports() -> None:
    """The one collision that would actually be reached for: two postgres on 5432."""
    product = _host_side_ports(ROOT_COMPOSE, _contract(REPO_ROOT / ".env.example"))
    host_default = _contract(HOST_ENV_EXAMPLE)["HOST_POSTGRES_PORT"]

    assert PRODUCT_POSTGRES_PORT in product, "the product's postgres moved; this checks nothing now"
    assert int(host_default) != PRODUCT_POSTGRES_PORT


def test_no_published_port_collides_with_something_already_running(services: dict) -> None:
    """oMLX is a host process on 8000 and is in no compose file, so it is named here."""
    host_ports = _host_side_ports(HOST_COMPOSE, _contract(HOST_ENV_EXAMPLE))

    collisions = {port: TAKEN[port] for port in host_ports & set(TAKEN)}
    assert not collisions, collisions


@pytest.mark.parametrize(("name", "port"), sorted(DOCUMENTED_PORTS.items()))
def test_the_published_port_is_the_one_the_readme_documents(
    services: dict, name: str, port: int
) -> None:
    """The orchestrator's contract points at these numbers; nothing else checks they agree."""
    entries = published(services[name])

    assert entries, name
    assert any(f":-{port}}}:" in entry or f":{port}:" in entry for entry in entries), entries


# ── credentials ──────────────────────────────────────────────────────────────


#: an environment key holding one of these must never carry a literal value
CREDENTIAL_SHAPED = ("PASSWORD", "SECRET", "KEY", "SALT", "MASTER")


def test_no_credential_is_written_into_the_file(services: dict) -> None:
    """Every secret is interpolated from host/.env, which is generated and git-ignored.

    Read from the parsed environment rather than the file's text: a literal password is a
    *value*, and a substring search cannot tell one from the word appearing in a comment.
    """
    literals = []
    for name, service in services.items():
        for key, value in (service.get("environment") or {}).items():
            if not any(word in key.upper() for word in CREDENTIAL_SHAPED):
                continue
            if not isinstance(value, str) or "${" not in value:
                literals.append(f"{name}.{key} = {value!r}")

    assert not literals, "these carry a literal instead of an interpolation:\n" + "\n".join(
        literals
    )


def test_no_key_shaped_string_appears_anywhere_in_the_file() -> None:
    """The generated key prefixes, in case one is ever pasted in while debugging."""
    text = HOST_COMPOSE.read_text()

    for prefix in ("sk-lf-", "pk-lf-", "sk-ant-", "sk-proj-"):
        assert prefix not in text, prefix


def test_every_secret_the_file_reads_fails_closed() -> None:
    """Bare `${VAR}` is an empty string when unset; postgres would start misconfigured."""
    text = HOST_COMPOSE.read_text()
    secrets = (
        "HOST_POSTGRES_PASSWORD",
        "CLICKHOUSE_PASSWORD",
        "MINIO_ROOT_PASSWORD",
        "LANGFUSE_SALT",
        "LANGFUSE_ENCRYPTION_KEY",
        "NEXTAUTH_SECRET",
        "LITELLM_MASTER_KEY",
        "LANGFUSE_INIT_PROJECT_PUBLIC_KEY",
        "LANGFUSE_INIT_PROJECT_SECRET_KEY",
        "LANGFUSE_INIT_USER_PASSWORD",
    )

    for name in secrets:
        assert f"${{{name}:?" in text, f"{name} must use the ${{VAR:?...}} form"


def test_every_variable_the_file_reads_is_declared_in_its_own_example() -> None:
    """A variable read but never declared would interpolate to nothing at the first start."""
    declared = {
        line.partition("=")[0]
        for line in HOST_ENV_EXAMPLE.read_text().splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    }
    referenced = set(re.findall(r"\$\{([A-Z][A-Z0-9_]*)", HOST_COMPOSE.read_text()))

    assert referenced
    assert referenced <= declared, sorted(referenced - declared)


def test_the_host_contract_is_not_the_orchestrator_contract() -> None:
    """Two files, two purposes: `make lint` checks the root one against the settings module."""
    root = {
        line.partition("=")[0]
        for line in (REPO_ROOT / ".env.example").read_text().splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    }
    host = {
        line.partition("=")[0]
        for line in HOST_ENV_EXAMPLE.read_text().splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    }

    assert not (root & host), sorted(root & host)


# ── it parses, and the scripts run ───────────────────────────────────────────


SCRIPTS = ("generate-env.sh", "sync-env.sh", "initdb/10-create-databases.sh")


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
@pytest.mark.parametrize("script", SCRIPTS)
def test_the_scripts_parse_and_are_executable(script: str) -> None:
    path = HOST_DIR / script

    assert path.is_file(), f"{path} is missing"
    assert path.stat().st_mode & 0o111, f"{script} is not executable"

    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_the_generator_never_overwrites_an_existing_file() -> None:
    """Regenerating would invalidate the project keys already written into the root .env."""
    text = (HOST_DIR / "generate-env.sh").read_text()

    assert 'if [[ -f "$target" ]]; then' in text
    assert "leaving it alone" in text


def test_only_one_script_writes_to_the_root_env() -> None:
    """A second writer would make it impossible to say where a value came from."""
    writers = [
        path.name
        for path in HOST_DIR.glob("*.sh")
        if re.search(r'root_env|"\$\{root\}/\.env"', path.read_text())
    ]

    assert writers == ["sync-env.sh"], writers
