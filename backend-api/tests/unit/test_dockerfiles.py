"""The two images, asserted where an image can be asserted without building it.

Building them takes minutes and network, so `make test` cannot; but the properties that
make an image safe are textual, and leaving them to a human reading a diff is exactly what
the constitution says a gate is for. What is checked here:

- **Every base is pinned.** A floating `node:24` or an implicit `:latest` would make the
  stack a different thing on every rebuild, against the Stack table.
- **Neither image ends as root (NFR-3).** The last `USER` decides who the harness runs as.
- **No credential enters a layer (AD-5, hard rule 5).** No contract placeholder value, no
  `ARG` or `ENV` named after a secret — a build argument is visible in `docker history`.
- **The start-up order is the one the story fixed:** every harness configured, then the
  schema brought to head, then the application. A container that served before migrating
  would answer requests against a schema behind the code.
- **`.env` never reaches a build context.** Both `.dockerignore` files exclude it, which is
  the only mechanism that keeps a filled `.env` out of `COPY . .`.
- **Versions are pinned in one place.** The harness CLI versions live in `.env.example` and
  in `scripts/harness/<name>.sh`; a second copy in a Dockerfile would drift.
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example
from tests.unit.test_compose_services import service as compose_service

BACKEND_DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"
WEB_DOCKERFILE = REPO_ROOT / "web-client" / "Dockerfile"
ENTRYPOINT = REPO_ROOT / "backend-api" / "docker-entrypoint.sh"

DOCKERFILES = {"backend-api": BACKEND_DOCKERFILE, "web-client": WEB_DOCKERFILE}
DOCKERIGNORES = {
    "root": REPO_ROOT / ".dockerignore",
    "web-client": REPO_ROOT / "web-client" / ".dockerignore",
}

#: The Stack table's bases for the two images.
EXPECTED_BASES = {"backend-api": "python:3.14-slim-trixie", "web-client": "node:24-bookworm-slim"}

#: Who each image ends as. Neither is root (NFR-3).
EXPECTED_USER = {"backend-api": "agent", "web-client": "node"}

#: Contract variables whose value is a credential. None may be named by an ARG or an ENV.
SECRET_VARIABLES = (
    "ORCHESTRATOR_TOKEN",
    "ORCHESTRATOR_SESSION_SECRET",
    "ORCHESTRATOR_SECRET_KEY",
    "DATABASE_URL",
    "POSTGRES_PASSWORD",
    "GITHUB_TOKEN",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_SECRET_KEY",
)

#: The order `backend-api/docker-entrypoint.sh` must run things in: the CLIs are reconciled
#: with their pins first, and a refused harness does not stop the start
#: (spec-harness-upgrade-survives-redeploy, 2026-10-29).
STARTUP_ORDER = (
    "scripts/harness/ensure-all.sh",
    "configure",
    "alembic upgrade head",
    "orchestrator.main",
)

HARNESSES = ("claude", "codex", "opencode")


def dockerfile(component: str) -> str:
    path = DOCKERFILES[component]
    assert path.is_file(), f"{path} is missing"
    return path.read_text()


def code(text: str) -> str:
    """The file with its whole-line comments dropped.

    Both files explain themselves at length, and an assertion about what runs must not be
    satisfied — or broken — by prose.
    """
    kept = [line for line in text.splitlines() if not line.strip().startswith("#")]
    return "\n".join(kept) + "\n"


def instructions(text: str, keyword: str) -> list[str]:
    """The argument of every `KEYWORD ...` line, comments and continuations aside."""
    joined = re.sub(r"\\\n", " ", text)
    return [
        match.group(1).strip()
        for match in re.finditer(rf"^{keyword}\s+(.*)$", joined, re.MULTILINE | re.IGNORECASE)
    ]


def build_args(text: str) -> dict[str, str]:
    """`ARG NAME=value` defaults, so a `FROM ${IMAGE}` can be resolved to what it pins."""
    found: dict[str, str] = {}
    for declaration in instructions(text, "ARG"):
        name, _, value = declaration.partition("=")
        found[name.strip()] = value.strip()
    return found


def stage_names(text: str) -> set[str]:
    """The names of the build stages, which a later `FROM` may use in place of an image."""
    return {
        match.group(1)
        for match in re.finditer(r"^FROM\s+\S+\s+AS\s+(\S+)", text, re.MULTILINE | re.IGNORECASE)
    }


def resolved_bases(text: str) -> list[str]:
    """Every `FROM` argument that names an image, with its ARG default substituted in."""
    args = build_args(text)
    stages = stage_names(text)
    resolved = []
    for line in instructions(text, "FROM"):
        image = line.split()[0]
        if image in stages:
            continue
        for name, value in args.items():
            image = image.replace(f"${{{name}}}", value).replace(f"${name}", value)
        resolved.append(image)
    return resolved


# ── the bases are pinned ─────────────────────────────────────────────────────


@pytest.mark.parametrize("component", sorted(DOCKERFILES))
def test_the_image_has_a_dockerfile(component: str) -> None:
    assert DOCKERFILES[component].is_file()


@pytest.mark.parametrize("component", sorted(DOCKERFILES))
def test_every_base_image_is_pinned_to_an_explicit_tag(component: str) -> None:
    bases = [image for image in resolved_bases(dockerfile(component)) if "$" not in image]

    assert bases
    for image in bases:
        reference = image.split("@")[0]
        assert ":" in reference, image
        assert not reference.endswith(":latest"), image


@pytest.mark.parametrize("component", sorted(EXPECTED_BASES))
def test_the_base_is_the_one_the_stack_table_names(component: str) -> None:
    assert EXPECTED_BASES[component] in resolved_bases(dockerfile(component))


def test_the_backend_installs_uv_at_the_pinned_version() -> None:
    """0.12.9 is the Stack table's uv; a floating copy would re-resolve the lockfile."""
    assert "ghcr.io/astral-sh/uv:0.12.9" in dockerfile("backend-api")


def test_the_backend_syncs_the_committed_lockfile() -> None:
    text = dockerfile("backend-api")

    assert "uv sync --locked" in text
    assert "--no-dev" in text


# ── neither image ends as root ───────────────────────────────────────────────


@pytest.mark.parametrize("component", sorted(EXPECTED_USER))
def test_the_image_ends_as_a_non_root_user(component: str) -> None:
    users = instructions(dockerfile(component), "USER")

    assert users, f"{component}: no USER instruction at all"
    assert users[-1] == EXPECTED_USER[component]


def test_the_backend_installs_every_harness_as_that_user() -> None:
    """`install` writes the BMAD stubs under AGENT_HOME; running it as root would lock them."""
    text = dockerfile("backend-api")
    at_install = text.index("scripts/harness/claude.sh install")
    last_user_before = [
        match.group(1) for match in re.finditer(r"^USER\s+(\S+)", text[:at_install], re.MULTILINE)
    ]

    assert last_user_before[-1] == "agent"
    for harness in HARNESSES:
        assert f"scripts/harness/{harness}.sh install" in text


# ── no credential in a layer ─────────────────────────────────────────────────


@pytest.mark.parametrize("component", sorted(DOCKERFILES))
@pytest.mark.parametrize("variable", SECRET_VARIABLES)
def test_no_build_argument_or_environment_names_a_credential(component: str, variable: str) -> None:
    """`ARG SECRET` puts the value in `docker history`; `ENV SECRET` puts it in the image."""
    text = dockerfile(component)

    for declaration in instructions(text, "ARG") + instructions(text, "ENV"):
        assert not declaration.startswith(variable), declaration


@pytest.mark.parametrize("component", sorted(DOCKERFILES))
def test_no_contract_placeholder_value_appears(component: str) -> None:
    contract = parse_env_example(ENV_EXAMPLE)
    text = dockerfile(component)

    for variable in SECRET_VARIABLES:
        assert contract[variable] not in text, variable


@pytest.mark.parametrize("component", sorted(DOCKERIGNORES))
def test_the_build_context_excludes_a_filled_env_file(component: str) -> None:
    path = DOCKERIGNORES[component]
    assert path.is_file(), f"{path} is missing"

    patterns = [line.strip() for line in path.read_text().splitlines()]

    assert ".env" in patterns, f"{path}: a filled .env would be copied into a layer"


def test_the_root_context_excludes_the_trees_that_do_not_belong_in_an_image() -> None:
    patterns = {line.strip() for line in DOCKERIGNORES["root"].read_text().splitlines()}

    assert {".git", "node_modules", "dist"} <= patterns


# ── the versions are pinned in one place ─────────────────────────────────────


@pytest.mark.parametrize("component", sorted(DOCKERFILES))
def test_no_harness_version_is_re_pinned_in_a_dockerfile(component: str) -> None:
    """`.env.example` and `scripts/harness/<name>.sh` pin them; a third copy would drift."""
    contract = parse_env_example(ENV_EXAMPLE)
    text = dockerfile(component)

    for variable in ("CLAUDE_CODE_VERSION", "CODEX_VERSION", "OPENCODE_VERSION", "BMAD_VERSION"):
        assert contract[variable] not in text, f"{variable} is pinned in two places"


#: The pins `.env` sets and the image build honours (spec-harness-upgrade-survives-redeploy).
HARNESS_PINS = ("CLAUDE_CODE_VERSION", "CODEX_VERSION", "OPENCODE_VERSION")


@pytest.mark.parametrize("variable", HARNESS_PINS)
def test_each_harness_pin_is_a_valueless_build_argument(variable: str) -> None:
    """Valueless, so an unset argument falls back to the harness script's default."""
    args = build_args(dockerfile("backend-api"))

    assert variable in args, f"ARG {variable} is not declared"
    assert args[variable] == "", f"ARG {variable} carries a literal"


def compose_backend_build_args() -> list[str]:
    """The entries under `args:` in the dev compose file's backend-api `build:`."""
    lines = compose_service("backend-api").splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "args:")
    indent = len(lines[start]) - len(lines[start].lstrip())
    entries = []
    for line in lines[start + 1 :]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        if line.strip():
            entries.append(line.strip())
    return entries


@pytest.mark.parametrize("variable", HARNESS_PINS)
def test_compose_passes_each_pin_to_the_build_by_name(variable: str) -> None:
    """A bare name: compose resolves it from `.env`, and omits it where `.env` does not set it."""
    assert f"- {variable}" in compose_backend_build_args()


@pytest.mark.parametrize("variable", ["AGENT_HOME", "WORK_DIR"])
def test_the_path_the_image_builds_is_the_path_the_contract_mounts(variable: str) -> None:
    """The named volumes are mounted at `${AGENT_HOME}` and `${WORK_DIR}` from `.env`. If the
    image built its home somewhere else, the volume would mount over an empty directory and
    the BMAD stubs installed at build time would not be there — at run time, with no gate
    between the two values."""
    contract = parse_env_example(ENV_EXAMPLE)

    assert build_args(dockerfile("backend-api")).get(variable) == contract[variable]


def test_the_node_runtime_the_backend_carries_is_pinned_exactly() -> None:
    """The CLIs run on it; `24` alone would move under the image."""
    version = build_args(dockerfile("backend-api")).get("NODE_VERSION", "")

    assert re.fullmatch(r"\d+\.\d+\.\d+", version), version


# ── the entrypoint: configure, migrate, serve ────────────────────────────────


def test_the_entrypoint_is_committed_and_executable() -> None:
    assert ENTRYPOINT.is_file()
    assert ENTRYPOINT.stat().st_mode & stat.S_IXUSR
    assert ENTRYPOINT.stat().st_mode & stat.S_IXOTH


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
def test_the_entrypoint_parses() -> None:
    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(ENTRYPOINT)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_the_entrypoint_fails_on_the_first_error() -> None:
    """Without this, a failed `configure` would be logged and the process would serve anyway."""
    assert "set -euo pipefail" in ENTRYPOINT.read_text()


def test_the_backend_image_runs_the_entrypoint() -> None:
    assert "docker-entrypoint.sh" in " ".join(instructions(dockerfile("backend-api"), "ENTRYPOINT"))


def test_the_entrypoint_configures_then_migrates_then_serves() -> None:
    text = code(ENTRYPOINT.read_text())
    positions = [text.index(step) for step in STARTUP_ORDER]

    assert positions == sorted(positions), STARTUP_ORDER


def test_the_entrypoint_reconciles_every_harness_cli_before_configuring() -> None:
    """A command line of its own, not a substring: it runs before the first `configure`."""
    lines = [line.strip() for line in code(ENTRYPOINT.read_text()).splitlines()]
    ensure_at = lines.index("scripts/harness/ensure-all.sh")
    configure_at = next(
        i for i, line in enumerate(lines) if re.search(r"\.sh\S*\s+configure\b", line)
    )

    assert ensure_at < configure_at, lines


def test_the_harness_prefix_precedes_the_npm_prefix_on_path() -> None:
    """The volume's CLIs win over anything an agent installs into NPM_CONFIG_PREFIX."""
    text = dockerfile("backend-api")
    match = re.search(r"PATH=(\S+)", text)
    assert match
    directories = match.group(1).split(":")

    assert "/opt/harness-cli/bin" in directories
    assert directories.index("/opt/harness-cli/bin") < directories.index("/opt/npm-global/bin")
    assert "NPM_CONFIG_PREFIX=/opt/npm-global" in text


def test_the_harness_prefix_is_created_for_the_agent_user() -> None:
    """A named volume takes its ownership from the image's directory on first creation."""
    text = code(dockerfile("backend-api"))

    assert re.search(r"mkdir -p [^;]*/opt/harness-cli", text)
    assert re.search(r"chown -R agent:agent [^;]*/opt/harness-cli", text)


def test_the_image_copy_is_created_for_the_agent_user_and_seeds_the_volume() -> None:
    """`install` writes `/opt/harness-image`, never mounted; the build copies it into
    `/opt/harness-cli` so a fresh `harness-bin` volume is seeded with the same CLIs."""
    text = code(dockerfile("backend-api"))

    assert re.search(r"mkdir -p [^;]*/opt/harness-image", text)
    assert re.search(r"chown -R agent:agent [^;]*/opt/harness-image", text)
    install_at = text.index("scripts/harness/opencode.sh install")
    copy = re.search(r"cp -a /opt/harness-image/\. /opt/harness-cli/", text)
    assert copy
    assert copy.start() > install_at
    assert "/opt/harness-image/bin" not in text, "the image copy is never on PATH"


def test_the_entrypoint_configures_every_harness() -> None:
    text = code(ENTRYPOINT.read_text())

    assert all(harness in text for harness in HARNESSES)
    assert "configure" in text


def test_the_application_replaces_the_entrypoint_process() -> None:
    """Without `exec`, the container's PID 1 is the shell and SIGTERM never reaches uvicorn."""
    assert re.search(r"^exec .*orchestrator\.main", code(ENTRYPOINT.read_text()), re.MULTILINE)


# ── the web-client image serves what 1.3 built ───────────────────────────────


def test_the_web_client_serves_the_standalone_entry() -> None:
    text = dockerfile("web-client")

    assert "dist/server/entry.mjs" in text


def test_the_web_client_installs_from_the_committed_lockfile() -> None:
    assert "--frozen-lockfile" in dockerfile("web-client")


def test_the_web_client_runtime_carries_no_dev_dependency() -> None:
    """Playwright and the linters have no business in the image the Operator runs."""
    assert "--prod" in dockerfile("web-client")


def test_the_web_client_binds_every_interface_inside_the_container() -> None:
    """`astro.config.mjs` pins 127.0.0.1 for the developer servers; the container is reached
    from the compose network, so the standalone entry needs HOST."""
    assert re.search(r"HOST=0\.0\.0\.0", dockerfile("web-client"))


def test_the_web_client_port_comes_from_the_contract() -> None:
    assert "WEB_CLIENT_PORT" in dockerfile("web-client")


def test_the_backend_does_not_start_uvicorn_itself() -> None:
    """`main()` owns the bind: it reads `settings.backend_api_port` and passes `log_config=None`.
    A `uvicorn` command line in the image would take a second, different set of decisions."""
    text = code(Path(BACKEND_DOCKERFILE).read_text()) + code(ENTRYPOINT.read_text())

    assert "uvicorn" not in text
