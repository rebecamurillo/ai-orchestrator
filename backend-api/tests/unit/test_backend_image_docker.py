"""Docker for Runs: the client in the backend image, the daemon in an optional sidecar.

A target repository whose install, test or quality-gate command runs `docker compose`
(PostGIS integration tests, a full-stack E2E in compose) cannot pass where `docker` exits 127
or finds no daemon. Two halves fix that, and both are textual properties of files `make test`
can read without building or starting anything:

- **The image carries the docker CLI with the compose and buildx plugins, pinned.** The
  version is an `ARG` with a literal default, each download is checked against a literal
  sha256 per architecture (download.docker.com publishes no checksum file to read one from),
  and the plugins land where the CLI looks for them. The client equals the sidecar's
  `docker:<version>-dind`.
- **The agent's CLI is pointed at the sidecar through `$HOME/.docker`.** A `shell` row gets
  `PATH`, `HOME` and `LANG` from the backend and nothing else (`process/runner.py`), so a
  `DOCKER_HOST` on the container would never reach it; a docker context under the agent's
  home does. The entrypoint writes it at every start, after the harness configs and before
  the schema migration.
- **The sidecar is opt-in and its daemon reachable from backend-api alone**: compose profile
  `docker`, `network_mode: service:backend-api`, dockerd on `127.0.0.1:2375` only, `work`
  mounted at the backend's own path so relative bind mounts resolve, 10.x address pools.

Added with feat/docker-for-verify (Operator request, 2026-11-02).
"""

from __future__ import annotations

import re

import pytest

from tests.unit.conftest import REPO_ROOT, parse_env_example
from tests.unit.test_deploy_compose import compose_text as deploy_compose_text
from tests.unit.test_deploy_compose import service as deploy_service
from tests.unit.test_dockerfiles import build_args, code, dockerfile, instructions

ENTRYPOINT = REPO_ROOT / "backend-api" / "docker-entrypoint.sh"
CONTEXT_SCRIPT = REPO_ROOT / "scripts" / "docker_context.sh"
DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"
ROOT_ENV_EXAMPLE = REPO_ROOT / ".env.example"

ENDPOINT = "tcp://127.0.0.1:2375"
PLUGINS = "/usr/local/libexec/docker/cli-plugins"
VERSION_ARGS = ("DOCKER_VERSION", "DOCKER_COMPOSE_VERSION", "DOCKER_BUILDX_VERSION")
CHECKSUM_ARGS = tuple(
    f"{prefix}_SHA256_{arch}"
    for prefix in ("DOCKER", "DOCKER_COMPOSE", "DOCKER_BUILDX")
    for arch in ("AMD64", "ARM64")
)


def joined(text: str) -> str:
    """Continuation lines folded, so one `RUN` reads as one line."""
    return re.sub(r"\\\n", " ", text)


def docker_run() -> str:
    """The one `RUN` that installs the docker client."""
    runs = [run for run in instructions(code(dockerfile("backend-api")), "RUN") if PLUGINS in run]
    assert len(runs) == 1, runs
    return runs[0]


# ── the client in the image ──────────────────────────────────────────────────


@pytest.mark.parametrize("name", VERSION_ARGS)
def test_each_docker_component_is_pinned_to_an_exact_version(name: str) -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", build_args(dockerfile("backend-api")).get(name, ""))


@pytest.mark.parametrize("name", CHECKSUM_ARGS)
def test_each_download_has_a_literal_sha256_per_architecture(name: str) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", build_args(dockerfile("backend-api")).get(name, ""))


def test_every_checksum_is_used_and_checked() -> None:
    run = docker_run()

    for name in CHECKSUM_ARGS:
        assert f"${{{name}}}" in run, name
    assert run.count("sha256sum -c -") == len(VERSION_ARGS)


def test_the_downloads_name_their_pinned_versions() -> None:
    run = docker_run()

    assert "download.docker.com/linux/static/stable/" in run
    assert "docker-${DOCKER_VERSION}.tgz" in run
    assert "docker/compose/releases/download/v${DOCKER_COMPOSE_VERSION}/" in run
    assert "docker/buildx/releases/download/v${DOCKER_BUILDX_VERSION}/" in run


def test_only_the_client_is_extracted_from_the_static_archive() -> None:
    """The archive also carries dockerd, containerd and runc; the daemon is the sidecar's."""
    run = docker_run()

    assert re.search(r"tar -xzf docker\.tgz [^;]*docker/docker;", run)
    assert "dockerd" not in run.replace("download.docker.com", "")


def test_the_plugins_land_where_the_cli_looks_for_them() -> None:
    run = docker_run()

    assert f"plugins={PLUGINS};" in run
    assert '-o "${plugins}/docker-compose"' in run
    assert '-o "${plugins}/docker-buildx"' in run
    assert "docker compose version" in run
    assert "docker buildx version" in run


def test_the_client_is_installed_as_root_before_the_harness_layer() -> None:
    text = joined(code(dockerfile("backend-api")))
    at = text.index(PLUGINS)

    assert at < text.index("USER agent")
    assert at < text.index("scripts/harness/claude.sh install")


def test_the_client_equals_the_sidecar_daemon() -> None:
    version = build_args(dockerfile("backend-api"))["DOCKER_VERSION"]

    assert f"image: docker:{version}-dind" in deploy_service("docker")


# ── the agent's CLI finds the daemon ─────────────────────────────────────────


def test_the_context_script_is_in_the_image_and_executable() -> None:
    assert CONTEXT_SCRIPT.stat().st_mode & 0o111
    assert "scripts/docker_context.sh /app/scripts/docker_context.sh" in " ".join(
        instructions(dockerfile("backend-api"), "COPY")
    )


def test_the_entrypoint_points_the_cli_after_configure_and_before_migrating() -> None:
    lines = [line.strip() for line in code(ENTRYPOINT.read_text()).splitlines()]
    at = lines.index("scripts/docker_context.sh")
    configure_at = max(i for i, line in enumerate(lines) if "configure" in line)

    assert configure_at < at < lines.index("alembic upgrade head")


def test_the_script_and_the_sidecar_name_one_endpoint() -> None:
    assert f'ENDPOINT="{ENDPOINT}"' in CONTEXT_SCRIPT.read_text()
    assert f"--host={ENDPOINT}" in deploy_service("docker")


# ── the sidecar: opt-in, reachable from backend-api alone ────────────────────


def test_the_sidecar_is_behind_a_profile_so_it_is_off_by_default() -> None:
    assert 'profiles: ["docker"]' in deploy_service("docker")


def test_the_switch_is_off_in_both_contracts() -> None:
    for path in (ROOT_ENV_EXAMPLE, DEPLOY_ENV_EXAMPLE):
        assert parse_env_example(path)["VERIFY_DOCKER"] == "false", path


def test_the_sidecar_shares_backend_api_network_namespace() -> None:
    """A port a test publishes appears on backend-api's localhost, where its scripts look."""
    body = deploy_service("docker")

    assert "network_mode: service:backend-api" in body
    assert "ports:" not in body


def test_dockerd_listens_on_loopback_only_without_tls() -> None:
    """`dockerd` first: given bare flags, the dind entrypoint prepends `tcp://0.0.0.0:2375`,
    which every container on the compose network could reach."""
    body = deploy_service("docker")
    command = re.search(r"command:\n((?:\s+- .*\n)+)", body)
    assert command is not None
    argv = [line.strip().removeprefix("- ") for line in command.group(1).splitlines()]

    assert argv[0] == "dockerd"
    assert [arg for arg in argv if arg.startswith("--host")] == [f"--host={ENDPOINT}"]
    assert "--tls=false" in argv
    assert 'DOCKER_TLS_CERTDIR: ""' in body
    assert "0.0.0.0" not in body


def test_the_daemon_networks_stay_off_the_compose_ranges() -> None:
    body = deploy_service("docker")

    assert re.search(r"--bip=10\.\d+\.\d+\.\d+/\d+", body)
    assert re.search(r"--default-address-pool=base=10\.\d+\.\d+\.\d+/\d+,size=\d+", body)


def test_the_work_volume_is_mounted_where_backend_api_mounts_it() -> None:
    """A compose file's relative bind mount resolves on the daemon's filesystem."""
    mount = "- work:${WORK_DIR:-/work}"

    assert mount in deploy_service("backend-api")
    assert mount in deploy_service("docker")


def test_the_image_cache_has_its_own_declared_volume() -> None:
    assert "- docker-data:/var/lib/docker" in deploy_service("docker")
    assert re.search(r"^  docker-data:\s*$", deploy_compose_text(), re.MULTILINE)


def test_the_sidecar_is_privileged_and_the_backend_is_not() -> None:
    assert "privileged: true" in deploy_service("docker")
    assert "privileged" not in deploy_service("backend-api")


def test_the_sidecar_follows_a_backend_api_recreate() -> None:
    assert re.search(
        r"depends_on:\s*\n\s*backend-api:\s*\n\s*condition: service_started\s*\n\s*restart: true",
        deploy_service("docker"),
    )


def test_the_sidecar_is_probed_on_its_own_listener() -> None:
    body = deploy_service("docker")

    assert "healthcheck:" in body
    assert f'"--host", "{ENDPOINT}", "version"' in body


def test_the_sidecar_carries_the_production_posture() -> None:
    body = deploy_service("docker")

    assert "restart: always" in body
    assert "logging:" in body
