"""`deploy/install.sh doctor | diagnose | harness` — the maintenance half of the installer.

These three commands are what an operator's admin agent runs on a client machine, so what they
have to be is *honest about a machine nobody here can see*. There is no Docker and no instance
in this module: a `docker` shim and a `curl` shim on PATH answer the questions the script asks,
and the script's own control flow is what gets proved — the same technique
`test_deploy_install.py` uses for `docker` and `test_kit_install.py` for `curl`. Running the
real thing against the real daemon is forbidden (hard rule 9; a dry run of the bundle once
recreated the operator's running stack, 2026-09-30).

What is pinned here:

- **`doctor` reads and never writes.** Every check is a question; no `pull`, `up`, `restart`,
  `stop` or `down` reaches docker, whatever it finds. A `fail` exits non-zero and a `warn` does
  not, because a client's script wraps this in a health check.
- **A `fail` line carries its own fix.** A missing `.env` names `./install.sh`; a `change-me`
  left in a REQUIRED variable names that variable; an instance that is not the tag `.env` pins
  names the `upgrade --tag` that reconciles them.
- **No secret reaches the output.** `doctor` reads `ORCHESTRATOR_TOKEN` to authenticate and
  `GITHUB_TOKEN` to check it is not a placeholder; neither value may appear in what a client
  pastes into a bug report.
- **`diagnose` masks by name, not by guess.** A value is printed only when its name is one of
  the non-secret kinds (ports, crons, versions, directories, flags); everything else is masked
  whether or not this module knows it is a credential — which is what keeps a variable added to
  the contract later out of a report.
- **`upgrade` refuses a no-op before it touches anything.** The target equal to the running
  version is the mistake that otherwise costs a pull, a restart and a `pg_dump`.
- **`harness claude --subscription` flips one variable and explains the rest.** It does not
  rewrite `litellm.config.yaml` from bash, and it carries the caveat the platform README
  carries: the gateway half has never been run against a live subscription.

Added under the agent-delivery-kit plan §5 (phase 4, 2026-10-01).
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT, parse_env_example

DEPLOY_DIR = REPO_ROOT / "deploy"
INSTALL = DEPLOY_DIR / "install.sh"
ADMIN_SKILL = DEPLOY_DIR / "kit" / "skills" / "orchestrator-admin"

#: the release the shimmed instance claims to run, and what `VERSION` beside the script says
TAG = "1.0.0-test"
#: distinctive enough that its absence from an output file is a real assertion
GITHUB_TOKEN = "ghp_doctor_never_prints_this_0123456789"
#: the file holds every secret of this stack, so a report built from it is owner-readable only
PRIVATE_MODE = 0o600
#: below this a value is too short for "it is absent from the output" to prove anything
SECRET_MIN_LENGTH = 8

#: How the installer applies a changed `.env` to backend-api
#: (spec-harness-upgrade-survives-redeploy).
RECREATE = "up -d --no-deps --wait --wait-timeout 600 backend-api"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

#: Answers every `docker` shape the three commands use, records argv, and changes nothing.
#: `SHIM_RUNNING` is the running service list — empty means this stack is down.
DOCKER_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_DOCKER_LOG"
case "$*" in
\t"compose version") echo v2.99.0; exit 0 ;;
\t"compose version --short") echo 2.99.0; exit 0 ;;
\t"version --format"*) echo 28.0.0; exit 0 ;;
\t"info --format"*) printf '%s\\n' "${SHIM_DOCKER_ROOT:-}"; exit 0 ;;
\tinfo) exit 0 ;;
\t"image inspect"*) exit "${SHIM_IMAGE_RC:-0}" ;;
\t"system df"*) echo "Images 1.1GB reclaimable 0B"; exit 0 ;;
\t"run --rm "*"--entrypoint cat "*)
\t\tif [ "${SHIM_IMAGE_ENV:-}" = none ]; then
\t\t\techo "cat: /app/deploy/.env.example: No such file or directory" >&2; exit 1
\t\tfi
\t\tif [ "${SHIM_IMAGE_ENV:-}" = broken ]; then
\t\t\techo "Error response from daemon: layer does not exist" >&2; exit 1
\t\tfi
\t\tif [ -n "${SHIM_IMAGE_ENV:-}" ]; then cat "$SHIM_IMAGE_ENV"; exit 0; fi
\t\techo "Unable to find image" >&2; exit 125 ;;
esac
case "$*" in
\t*"up -d --no-deps --wait --wait-timeout 600 backend-api") exit "${SHIM_RECREATE_RC:-0}" ;;
\t*"ps --status running --services"*) printf '%s\\n' ${SHIM_RUNNING:-}; exit 0 ;;
\t*" logs "*) if [ -n "${SHIM_LOGS:-}" ]; then cat "$SHIM_LOGS"; fi; exit 0 ;;
\t*" ps") echo "NAME STATUS"; exit 0 ;;
esac
exit 0
"""

#: The two curl shapes the script uses: `-o FILE -w '%{http_code}' URL`, and the same with
#: `-o /dev/null`. A body is served from a file so no JSON has to survive shell quoting.
CURL_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_CURL_LOG"
out=""
url=""
prev=""
for arg in "$@"; do
\tif [ "$prev" = "-o" ]; then out="$arg"; fi
\tcase "$arg" in http*) url="$arg" ;; esac
\tprev="$arg"
done
emit() {
\tif [ -n "$out" ] && [ "$out" != "/dev/null" ] && [ -n "$2" ]; then cp "$2" "$out"; fi
\tprintf '%s' "$1"
\texit 0
}
case "$url" in
\t*/healthz) emit "${SHIM_HEALTHZ_CODE:-200}" "" ;;
\t*/api/v1/ping) emit "${SHIM_PING_CODE:-200}" "" ;;
\t*/api/v1/version) emit "${SHIM_VERSION_CODE:-200}" "${SHIM_VERSION_FILE:-}" ;;
\t*/api/v1/harnesses) emit "${SHIM_HARNESS_CODE:-200}" "${SHIM_HARNESS_FILE:-}" ;;
esac
emit 404 ""
"""

VERSION_BODY = {
    "app_version": TAG,
    "kit_version": TAG,
    "bmad_version": "6.11.0",
    "harness_versions": {"claude": "2.1.258", "codex": "0.152.1", "opencode": "1.18.26"},
}

#: One enabled row and one disabled row whose `lines[]` nest objects of their own — the shape
#: the per-row parser has to survive, since `},{` appears inside a row as well as between rows.
HARNESS_BODY = {
    "items": [
        {
            "name": "claude",
            "enabled": True,
            "last_readiness_at": "2026-10-01T00:00:00Z",
            "failing_check": None,
            "version_pin": "2.1.258",
            "last_readiness_run_id": None,
            "lines": [
                {"check": "cli", "ok": True, "text": "2.1.258"},
                {"check": "trace observed", "ok": True, "text": "ok"},
            ],
            "models": [],
        },
        {
            "name": "codex",
            "enabled": False,
            "last_readiness_at": None,
            "failing_check": "cli: not at pinned version",
            "version_pin": "0.152.1",
            "last_readiness_run_id": None,
            "lines": [{"check": "cli", "ok": False, "text": "not at pinned version"}],
            "models": [],
        },
    ],
    "next_cursor": None,
}


def _run(
    *args: str, cwd: Path, env: dict[str, str] | None = None, answers: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the installer the way a client does — as a command, no shell. `answers` is what the
    operator types at the prompts, one line each."""
    dropped = {"GHCR_TOKEN", "GITHUB_TOKEN", "IMAGE_TAG", "DOCKER_CONFIG"}
    clean = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(cwd / "install.sh"), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**clean, **(env or {})},
        check=False,
        input=answers,
    )


@pytest.fixture
def bundle(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    """An extracted bundle with both shims on PATH and no `.env` yet."""
    shutil.copy(INSTALL, tmp_path / "install.sh")
    shutil.copy(DEPLOY_DIR / ".env.example", tmp_path / ".env.example")
    shutil.copy(DEPLOY_DIR / "docker-compose.yml", tmp_path / "docker-compose.yml")
    (tmp_path / "VERSION").write_text(f"{TAG}\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("docker", DOCKER_SHIM), ("curl", CURL_SHIM)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)

    docker_config = tmp_path / "dockercfg"
    docker_config.mkdir()
    (docker_config / "config.json").write_text('{"auths": {"ghcr.io": {"auth": "c2VjcmV0"}}}')

    served = tmp_path / "served"
    served.mkdir()
    (served / "version.json").write_text(json.dumps(VERSION_BODY))
    (served / "harnesses.json").write_text(json.dumps(HARNESS_BODY))

    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DOCKER_CONFIG": str(docker_config),
        "SHIM_DOCKER_LOG": str(tmp_path / "docker.log"),
        "SHIM_CURL_LOG": str(tmp_path / "curl.log"),
        "SHIM_RUNNING": "postgres backend-api web-client",
        "SHIM_VERSION_FILE": str(served / "version.json"),
        "SHIM_HARNESS_FILE": str(served / "harnesses.json"),
        "GHCR_TOKEN": GITHUB_TOKEN,
    }
    return tmp_path, env


@pytest.fixture
def installed(bundle: tuple[Path, dict[str, str]]) -> tuple[Path, dict[str, str]]:
    """The same bundle with `.env` rendered, as every day-2 command finds it."""
    path, env = bundle
    result = _run("env", "--yes", cwd=path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    return path, env


def _docker_calls(path: Path) -> str:
    log = path / "docker.log"
    return log.read_text() if log.is_file() else ""


def _secrets(path: Path) -> list[str]:
    """Every value the rendered `.env` must never leak."""
    rendered = parse_env_example(path / ".env")
    return [
        rendered[name]
        for name in (
            "ORCHESTRATOR_TOKEN",
            "ORCHESTRATOR_SESSION_SECRET",
            "ORCHESTRATOR_SECRET_KEY",
            "POSTGRES_PASSWORD",
            "GITHUB_TOKEN",
        )
    ]


# ── doctor ───────────────────────────────────────────────────────────────────


@needs_bash
def test_doctor_without_an_env_file_fails_and_names_the_installer(
    bundle: tuple[Path, dict[str, str]],
) -> None:
    path, env = bundle

    result = _run("doctor", cwd=path, env=env)

    assert result.returncode != 0
    assert "fail" in result.stdout
    assert "./install.sh" in result.stdout
    assert not (path / ".env").exists()


@needs_bash
def test_doctor_on_a_healthy_stack_exits_zero_and_prints_the_version_line(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("doctor", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"running {TAG}" in result.stdout
    assert f"IMAGE_TAG {TAG}" in result.stdout
    assert "6.11.0" in result.stdout, "the pinned bmad version is part of the report"
    assert "2.1.258" in result.stdout, "the pinned harness CLI versions are part of the report"
    assert "0 fail" in result.stdout


@needs_bash
def test_doctor_changes_nothing_it_found(installed: tuple[Path, dict[str, str]]) -> None:
    """Every check is a question (hard rule 9): no command that starts or stops anything."""
    path, env = installed
    before = (path / ".env").read_bytes()

    _run("doctor", cwd=path, env=env)

    calls = _docker_calls(path)
    for forbidden in (" pull", " up ", " restart", " stop", " down", " exec "):
        assert forbidden not in calls, f"doctor ran docker{forbidden}: {calls}"
    assert (path / ".env").read_bytes() == before


@needs_bash
def test_a_placeholder_in_a_required_variable_is_a_fail_naming_it(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    text = (path / ".env").read_text()
    (path / ".env").write_text(
        text.replace(f"GITHUB_TOKEN={GITHUB_TOKEN}", "GITHUB_TOKEN=change-me")
    )

    result = _run("doctor", cwd=path, env=env)

    assert result.returncode != 0
    assert "GITHUB_TOKEN" in result.stdout
    assert "change-me" in result.stdout


@needs_bash
def test_an_instance_behind_image_tag_is_a_warn_with_the_upgrade_command(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """`IMAGE_TAG` was retagged and never restarted — the one skew a client cannot see."""
    path, env = installed
    text = (path / ".env").read_text()
    (path / ".env").write_text(text.replace(f"IMAGE_TAG={TAG}", "IMAGE_TAG=2.0.0"))

    result = _run("doctor", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "warn" in result.stdout
    assert "./install.sh upgrade --tag 2.0.0" in result.stdout
    assert "0 fail" in result.stdout


@needs_bash
def test_a_disabled_harness_is_a_warn_naming_its_failing_check(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("doctor", cwd=path, env=env)

    assert "claude: enabled" in result.stdout
    assert "codex: disabled" in result.stdout
    assert "cli: not at pinned version" in result.stdout
    assert "/api/v1/harnesses/codex/readiness" in result.stdout


@needs_bash
def test_a_dead_api_is_a_fail_naming_the_two_commands(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("doctor", cwd=path, env={**env, "SHIM_HEALTHZ_CODE": "000"})

    assert result.returncode != 0
    assert "/healthz answered 000" in result.stdout
    assert "./install.sh logs" in result.stdout


@needs_bash
def test_a_refused_token_is_a_fail_and_does_not_print_the_token(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("doctor", cwd=path, env={**env, "SHIM_PING_CODE": "401"})

    assert result.returncode != 0
    assert "/api/v1/ping refused the token" in result.stdout
    for secret in _secrets(path):
        assert secret not in result.stdout + result.stderr


@needs_bash
def test_doctor_prints_no_value_the_env_file_keeps_secret(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """A client pastes this output into a bug report verbatim."""
    path, env = installed

    result = _run("doctor", cwd=path, env=env)
    output = result.stdout + result.stderr

    for secret in _secrets(path):
        assert len(secret) >= SECRET_MIN_LENGTH, "too short to prove anything by absence"
        assert secret not in output


@needs_bash
def test_a_taken_port_with_the_stack_down_is_a_fail_that_refuses_to_take_it_over(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("doctor", cwd=path, env={**env, "SHIM_RUNNING": ""})

    assert "WEB_CLIENT_PORT" in result.stdout
    assert "BACKEND_API_PORT" in result.stdout


@needs_bash
def test_a_blank_cron_is_a_fail_naming_the_variable(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    lines = [
        "WORKTREE_GC_CRON=" if line.startswith("WORKTREE_GC_CRON=") else line
        for line in (path / ".env").read_text().splitlines()
    ]
    (path / ".env").write_text("\n".join(lines) + "\n")

    result = _run("doctor", cwd=path, env=env)

    assert result.returncode != 0
    assert "WORKTREE_GC_CRON" in result.stdout
    assert ".env.example" in result.stdout


# ── diagnose ─────────────────────────────────────────────────────────────────


@needs_bash
def test_diagnose_writes_a_masked_report_and_prints_its_path(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("diagnose", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    reports = sorted((path / "diagnostics").glob("*.md"))
    assert len(reports) == 1, reports
    assert str(reports[0]) in result.stdout
    text = reports[0].read_text()
    assert f"app {TAG}" in text
    assert f"IMAGE_TAG  {TAG}" in text
    # the non-secret kinds stay readable: a maintainer cannot reproduce a port they cannot see
    assert "BACKEND_API_PORT=8000" in text
    assert "WORKTREE_GC_CRON=30 3 * * *" in text
    for name in (
        "ORCHESTRATOR_TOKEN",
        "ORCHESTRATOR_SESSION_SECRET",
        "ORCHESTRATOR_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "GITHUB_TOKEN",
        "DATABASE_URL",
    ):
        assert f"{name}=<redacted>" in text, name
    for secret in _secrets(path):
        assert secret not in text
    assert stat.S_IMODE(reports[0].stat().st_mode) == PRIVATE_MODE


@needs_bash
def test_diagnose_redacts_token_shaped_strings_the_containers_logged(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """A log line carries whatever a target repository printed, including its own keys."""
    path, env = installed
    logs = path / "container.log"
    logs.write_text(
        "backend-api  | cloning with ghp_abcdefghijklmnopqrstuvwxyz012345\n"
        "backend-api  | gateway key sk-litellm-abcdef1234567890\n"
        "backend-api  | postgresql+psycopg://orchestrator:hunter2hunter2@postgres:5432/orchestrator\n"
    )

    _run("diagnose", cwd=path, env={**env, "SHIM_LOGS": str(logs)})

    text = next(iter((path / "diagnostics").glob("*.md"))).read_text()
    assert "ghp_abcdefghijklmnopqrstuvwxyz012345" not in text
    assert "sk-litellm-abcdef1234567890" not in text
    assert "hunter2hunter2" not in text
    assert "<redacted>" in text


# ── upgrade pre-flight ───────────────────────────────────────────────────────


@needs_bash
def test_upgrade_to_the_running_version_refuses_before_pulling_anything(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("upgrade", "--tag", TAG, "--yes", cwd=path, env=env)

    assert result.returncode != 0
    assert "already what is running" in result.stderr
    calls = _docker_calls(path)
    assert " pull" not in calls, calls
    assert " up " not in calls, calls
    assert parse_env_example(path / ".env")["IMAGE_TAG"] == TAG


@needs_bash
def test_upgrade_prints_the_running_version_against_the_target(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """The pre-flight line is what the DBOS drain decision is made against."""
    path, env = installed

    result = _run("upgrade", "--tag", "2.0.0", cwd=path, env={**env, "SHIM_RUNNING": ""})

    assert f"running {TAG} → target 2.0.0" in result.stdout


# ── harness ──────────────────────────────────────────────────────────────────


@needs_bash
def test_harness_claude_subscription_flips_the_variable_and_prints_no_secret(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("harness", "claude", "--subscription", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_env_example(path / ".env")["CLAUDE_SUBSCRIPTION_AUTH"] == "true"
    assert "forward_client_headers_to_llm_api" in result.stdout
    assert "claude-subscription" in result.stdout
    assert "litellm.config.yaml" in result.stdout
    assert "never been run against a live" in result.stdout
    for secret in _secrets(path):
        assert secret not in result.stdout + result.stderr


@needs_bash
def test_harness_claude_api_key_flips_it_back(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed
    _run("harness", "claude", "--subscription", "--yes", cwd=path, env=env)

    result = _run("harness", "claude", "--api-key", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_env_example(path / ".env")["CLAUDE_SUBSCRIPTION_AUTH"] == "false"
    assert "ANTHROPIC_API_KEY" in result.stdout


@needs_bash
def test_harness_claude_logs_in_inside_the_container_and_verifies(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("harness", "claude", "--subscription", "--yes", cwd=path, env=env)

    calls = _docker_calls(path)
    assert "exec backend-api claude login" in calls, calls
    # spec-harness-upgrade-survives-redeploy (2026-10-29): applied by recreating backend-api,
    # since `compose restart` keeps the creation-time environment and never re-reads `.env`.
    assert RECREATE in calls, calls
    assert " restart " not in calls, calls
    assert "claude: enabled" in result.stdout


@needs_bash
def test_harness_claude_subscription_explains_a_disabled_row(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    served = path / "served" / "harnesses.json"
    body = json.loads(served.read_text())
    body["items"][0].update(enabled=False, failing_check="not logged in (claude auth status)")
    served.write_text(json.dumps(body))

    result = _run("harness", "claude", "--subscription", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "claude: disabled — not logged in (claude auth status)" in result.stdout
    assert "claude auth status' and refuses there first" in result.stdout


@needs_bash
def test_harness_claude_with_the_stack_down_says_to_start_it_rather_than_failing(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run(
        "harness", "claude", "--subscription", "--yes", cwd=path, env={**env, "SHIM_RUNNING": ""}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "./install.sh start" in result.stdout
    assert "claude login" not in _docker_calls(path)


@needs_bash
def test_harness_codex_is_refused_and_names_the_api_key_path(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """No subscription login exists in `scripts/harness/codex.sh` or `opencode.sh`."""
    path, env = installed

    result = _run("harness", "codex", "--subscription", cwd=path, env=env)

    assert result.returncode != 0
    assert "API key" in result.stderr


@needs_bash
def test_harness_without_a_mode_flag_is_refused(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed

    result = _run("harness", "claude", cwd=path, env=env)

    assert result.returncode != 0
    assert "--subscription" in result.stderr
    assert parse_env_example(path / ".env")["CLAUDE_SUBSCRIPTION_AUTH"] == "false"


# ── the skill that drives them ───────────────────────────────────────────────


def test_the_admin_skill_declares_the_name_its_directory_has() -> None:
    """A SKILL.md whose frontmatter `name` disagrees with its directory never loads."""
    text = (ADMIN_SKILL / "SKILL.md").read_text()
    front = text.split("---")[1]

    assert text.startswith("---\n")
    assert "name: orchestrator-admin" in front
    assert "description:" in front
    for trigger in ("install", "upgrade", "doctor", "healthy", "harness", "bug", "back up"):
        assert trigger in front, trigger


def test_the_admin_skill_states_the_rules_it_cannot_leave_to_the_installer() -> None:
    """Three things the script cannot enforce on an agent's behalf."""
    text = (ADMIN_SKILL / "SKILL.md").read_text()

    assert "Never stop anything the user did not ask you to stop" in text
    assert "has never been run against a live subscription" in text
    assert "DBOS_APPLICATION_VERSION" in text
    assert "references/runbooks.md" in text
    assert (ADMIN_SKILL / "references" / "runbooks.md").is_file()


# ── harness <name> --version: the pin edited, then applied by a recreate ─────
#
# spec-harness-upgrade-survives-redeploy (2026-10-29). Recreating is what
# makes the container's `ensure` reconcile the CLI to the new pin; `compose restart` would keep
# the old environment. The shims stand in for docker and the API.

PIN_VARIABLES = {
    "claude": "CLAUDE_CODE_VERSION",
    "codex": "CODEX_VERSION",
    "opencode": "OPENCODE_VERSION",
}


@needs_bash
@pytest.mark.parametrize(("name", "variable"), sorted(PIN_VARIABLES.items()))
def test_harness_version_writes_the_pin_and_recreates_the_backend(
    installed: tuple[Path, dict[str, str]], name: str, variable: str
) -> None:
    path, env = installed

    result = _run("harness", name, "--version", "9.8.7", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_env_example(path / ".env")[variable] == "9.8.7"
    calls = _docker_calls(path)
    assert RECREATE in calls, calls
    assert " restart " not in calls, calls
    assert f"POST /api/v1/harnesses/{name}/readiness" in result.stdout
    for secret in _secrets(path):
        assert secret not in result.stdout + result.stderr


@needs_bash
def test_harness_version_prints_the_harness_row(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed

    enabled = _run("harness", "claude", "--version", "2.1.260", "--yes", cwd=path, env=env)
    failing = _run("harness", "codex", "--version", "0.200.0", "--yes", cwd=path, env=env)

    assert "claude: enabled" in enabled.stdout
    assert "codex: disabled — cli: not at pinned version" in failing.stdout


@needs_bash
def test_harness_version_keeps_the_trailing_comment(installed: tuple[Path, dict[str, str]]) -> None:
    path, env = installed
    dotenv = path / ".env"
    pin = parse_env_example(dotenv)["CLAUDE_CODE_VERSION"]
    dotenv.write_text(
        dotenv.read_text().replace(
            f"CLAUDE_CODE_VERSION={pin}", f"CLAUDE_CODE_VERSION={pin}  # bumped for a fix"
        )
    )

    result = _run("harness", "claude", "--version", "2.1.260", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "CLAUDE_CODE_VERSION=2.1.260  # bumped for a fix" in dotenv.read_text().splitlines()


@needs_bash
def test_harness_version_with_the_stack_down_writes_the_pin_and_says_start_applies_it(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run(
        "harness",
        "claude",
        "--version",
        "2.1.260",
        "--yes",
        cwd=path,
        env={**env, "SHIM_RUNNING": ""},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_env_example(path / ".env")["CLAUDE_CODE_VERSION"] == "2.1.260"
    assert "./install.sh start" in result.stdout
    assert " up " not in _docker_calls(path)


@needs_bash
def test_harness_version_for_an_unknown_harness_names_the_three(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    before = (path / ".env").read_text()

    result = _run("harness", "gemini", "--version", "1.0.0", "--yes", cwd=path, env=env)

    assert result.returncode == 1
    for name in PIN_VARIABLES:
        assert name in result.stderr
    assert " up " not in _docker_calls(path)
    assert (path / ".env").read_text() == before


@needs_bash
@pytest.mark.parametrize(
    "argv",
    [
        ("--yes", "harness", "claude", "--version"),
        ("harness", "claude", "--version", "--yes"),
        ("harness", "claude", "--version=", "--yes"),
        ("harness", "claude", "--version", "2.1.260", "--subscription", "--yes"),
        ("harness", "claude", "--version", "2.1.260", "--api-key", "--yes"),
        ("harness", "claude", "--version", "latest", "--yes"),
        ("harness", "claude", "--version", "^2.1", "--yes"),
        ("start", "--version", "2.1.260", "--yes"),
        ("upgrade", "--tag", "2.0.0", "--version", "2.1.260", "--yes"),
        ("harness", "claude", "--version", "2.1.260", "--version", "2.1.261", "--yes"),
        ("harness", "claude", "--version=2.1.260", "--version", "2.1.261", "--yes"),
    ],
    ids=[
        "trailing, last argv",
        "followed by a flag",
        "empty",
        "with --subscription",
        "with --api-key",
        "latest",
        "a range",
        "with start",
        "with upgrade",
        "twice",
        "twice, mixed forms",
    ],
)
def test_harness_version_misuse_is_refused_and_writes_nothing(
    installed: tuple[Path, dict[str, str]], argv: tuple[str, ...]
) -> None:
    path, env = installed
    before = (path / ".env").read_text()

    result = _run(*argv, cwd=path, env=env)

    assert result.returncode == 1, result.stdout + result.stderr
    assert "--version" in result.stderr
    assert (path / ".env").read_text() == before
    calls = _docker_calls(path)
    assert " up " not in calls, calls
    assert " pull" not in calls, calls


# ── upgrade moves the harness pins to the release's ─────────────────────────
#
# spec-harness-upgrade-survives-redeploy (2026-10-29): `harness-bin` outlives the image, so the
# new release's CLIs arrive only through the pins its own `/app/deploy/.env.example` carries.

RELEASE_IMAGE = "ghcr.io/rebecamurillo/ai-orchestrator/backend-api:2.0.0"


def _release_env(path: Path, **pins: str) -> Path:
    """The new image's `.env.example`: this bundle's, with the given pins changed."""
    text = (path / ".env.example").read_text()
    contract = parse_env_example(path / ".env.example")
    for variable, value in pins.items():
        text = text.replace(f"{variable}={contract[variable]}", f"{variable}={value}")
    release = path / "release.env.example"
    release.write_text(text)
    return release


@needs_bash
def test_upgrade_rewrites_each_differing_pin_and_prints_it(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    before = parse_env_example(path / ".env")
    release = _release_env(path, CLAUDE_CODE_VERSION="2.1.300", OPENCODE_VERSION="1.20.0")

    result = _run(
        "upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, "SHIM_IMAGE_ENV": str(release)}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    after = parse_env_example(path / ".env")
    assert after["IMAGE_TAG"] == "2.0.0"
    assert after["CLAUDE_CODE_VERSION"] == "2.1.300"
    assert after["OPENCODE_VERSION"] == "1.20.0"
    assert after["CODEX_VERSION"] == before["CODEX_VERSION"]
    assert f"CLAUDE_CODE_VERSION {before['CLAUDE_CODE_VERSION']} → 2.1.300" in result.stdout
    assert f"OPENCODE_VERSION {before['OPENCODE_VERSION']} → 1.20.0" in result.stdout
    assert "CODEX_VERSION" not in result.stdout
    calls = _docker_calls(path)
    assert f"pull {RELEASE_IMAGE}" in calls, calls
    assert f"run --rm --entrypoint cat {RELEASE_IMAGE} /app/deploy/.env.example" in calls, calls
    lines = calls.splitlines()
    read_at = next(i for i, line in enumerate(lines) if line.startswith("run --rm"))
    up_at = next(i for i, line in enumerate(lines) if " up " in line)
    assert read_at < up_at


@needs_bash
def test_upgrade_with_the_release_pins_unchanged_writes_none(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    before = parse_env_example(path / ".env")
    release = _release_env(path)

    result = _run(
        "upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, "SHIM_IMAGE_ENV": str(release)}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    after = parse_env_example(path / ".env")
    for variable in PIN_VARIABLES.values():
        assert after[variable] == before[variable]
        assert f"{variable} " not in result.stdout


@needs_bash
def test_upgrade_with_no_pull_reads_the_local_image(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    release = _release_env(path, CODEX_VERSION="0.200.0")

    result = _run(
        "upgrade",
        "--tag",
        "2.0.0",
        "--yes",
        "--no-pull",
        cwd=path,
        env={**env, "SHIM_IMAGE_ENV": str(release)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_env_example(path / ".env")["CODEX_VERSION"] == "0.200.0"
    calls = _docker_calls(path)
    assert "pull ghcr.io" not in calls, calls
    # `docker run` would otherwise pull an absent image itself
    assert f"run --rm --pull never --entrypoint cat {RELEASE_IMAGE}" in calls, calls


@needs_bash
@pytest.mark.parametrize("missing", ["image", "pin"])
def test_upgrade_dies_before_writing_when_the_image_yields_no_pins(
    installed: tuple[Path, dict[str, str]], missing: str
) -> None:
    path, env = installed
    before = (path / ".env").read_text()
    extra: dict[str, str] = {}
    if missing == "pin":
        release = _release_env(path)
        release.write_text(
            "\n".join(
                line
                for line in release.read_text().splitlines()
                if not line.startswith("CODEX_VERSION=")
            )
        )
        extra["SHIM_IMAGE_ENV"] = str(release)

    result = _run("upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, **extra})

    assert result.returncode == 1, result.stdout + result.stderr
    assert RELEASE_IMAGE in result.stderr
    assert (path / ".env").read_text() == before
    calls = _docker_calls(path)
    assert " up " not in calls, calls
    assert "pg_dump" not in calls, calls


# ── recreate outcomes and the upgrade's pin plan ────────────────────────────
#
# The recreate can be declined or fail, `--version=X` is a form of its own, and `upgrade`
# shows the pin changes before it asks, refuses a `.env` that does not declare a pin, and
# tolerates an older release image.


@needs_bash
def test_harness_version_in_the_equals_form_writes_the_pin(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("harness", "codex", "--version=9.8.7", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert parse_env_example(path / ".env")["CODEX_VERSION"] == "9.8.7"
    assert RECREATE in _docker_calls(path)


@needs_bash
@pytest.mark.parametrize(
    "argv",
    [("harness", "claude", "--version", "2.1.260"), ("harness", "claude", "--subscription")],
    ids=["version", "subscription"],
)
def test_a_declined_recreate_runs_no_up_and_says_so(
    installed: tuple[Path, dict[str, str]], argv: tuple[str, ...]
) -> None:
    path, env = installed

    result = _run(*argv, cwd=path, env=env, answers="n\n")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Not recreated" in result.stdout
    calls = _docker_calls(path)
    assert " up " not in calls, calls
    assert " restart " not in calls, calls


@needs_bash
@pytest.mark.parametrize(
    "argv",
    [("harness", "claude", "--version", "2.1.260"), ("harness", "claude", "--subscription")],
    ids=["version", "subscription"],
)
def test_a_failed_recreate_points_at_the_logs_and_exits_non_zero(
    installed: tuple[Path, dict[str, str]], argv: tuple[str, ...]
) -> None:
    path, env = installed

    result = _run(*argv, "--yes", cwd=path, env={**env, "SHIM_RECREATE_RC": "1"})

    assert result.returncode != 0
    assert "./install.sh logs" in result.stderr
    assert "written" in result.stdout
    assert "claude: enabled" not in result.stdout


@needs_bash
def test_harness_version_says_the_row_reads_disabled_until_readiness_reruns(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """`sync_pins` resets readiness on a pin change; the installer must not imply `enabled`."""
    path, env = installed

    result = _run("harness", "codex", "--version", "0.200.0", "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "disabled until readiness is re-run" in result.stdout


@needs_bash
def test_upgrade_prints_the_planned_pin_changes_before_it_asks(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    before_text = (path / ".env").read_text()
    before = parse_env_example(path / ".env")
    release = _release_env(path, CLAUDE_CODE_VERSION="2.1.300", CODEX_VERSION="0.100.0")

    result = _run(
        "upgrade",
        "--tag",
        "2.0.0",
        cwd=path,
        env={**env, "SHIM_IMAGE_ENV": str(release)},
        answers="n\n",
    )

    assert result.returncode != 0
    assert "upgrade cancelled" in result.stderr
    assert f"CLAUDE_CODE_VERSION {before['CLAUDE_CODE_VERSION']} → 2.1.300" in result.stdout
    downgrade = next(line for line in result.stdout.splitlines() if "CODEX_VERSION" in line)
    assert f"{before['CODEX_VERSION']} → 0.100.0" in downgrade
    assert "downgrade" in downgrade
    claude = next(line for line in result.stdout.splitlines() if "CLAUDE_CODE_VERSION" in line)
    assert "downgrade" not in claude
    assert (path / ".env").read_text() == before_text
    calls = _docker_calls(path)
    assert "pg_dump" not in calls, calls
    assert " up " not in calls, calls


@needs_bash
def test_upgrade_with_a_release_image_without_the_contract_keeps_the_pins(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """An older release ships no `/app/deploy/.env.example`: a rollback to it stays possible."""
    path, env = installed
    before = parse_env_example(path / ".env")

    result = _run(
        "upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, "SHIM_IMAGE_ENV": "none"}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "warning:" in result.stderr
    assert RELEASE_IMAGE in result.stderr
    after = parse_env_example(path / ".env")
    assert after["IMAGE_TAG"] == "2.0.0"
    for variable in PIN_VARIABLES.values():
        assert after[variable] == before[variable]


@needs_bash
def test_upgrade_dies_before_any_write_when_dotenv_declares_no_pin(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    dotenv = path / ".env"
    dotenv.write_text(
        "\n".join(
            line
            for line in dotenv.read_text().splitlines()
            if not line.startswith("CODEX_VERSION=")
        )
        + "\n"
    )
    before = dotenv.read_text()
    release = _release_env(path, CLAUDE_CODE_VERSION="2.1.300")

    result = _run(
        "upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, "SHIM_IMAGE_ENV": str(release)}
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert "CODEX_VERSION" in result.stderr
    assert dotenv.read_text() == before
    calls = _docker_calls(path)
    assert "pg_dump" not in calls, calls
    assert " up " not in calls, calls
    assert not (path / "backups").exists() or not any((path / "backups").iterdir())


@needs_bash
def test_harness_version_at_the_current_pin_recreates_nothing(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    pin = parse_env_example(path / ".env")["CLAUDE_CODE_VERSION"]

    result = _run("harness", "claude", "--version", pin, "--yes", cwd=path, env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"already pinned at {pin}" in result.stdout
    assert " up " not in _docker_calls(path)


@needs_bash
def test_harness_version_prints_this_starts_harness_log_lines(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    logs = path / "backend.log"
    logs.write_text(
        "backend-api-1  | [harness:codex] codex 0.152.1 → 0.200.0\n"
        "backend-api-1  | [harness:claude] claude 2.1.258 at pin\n"
        "backend-api-1  | [harness:codex] codex 0.200.0 at pin\n"
    )

    result = _run(
        "harness",
        "codex",
        "--version",
        "0.200.0",
        "--yes",
        cwd=path,
        env={**env, "SHIM_LOGS": str(logs)},
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "[harness:codex] codex 0.200.0 at pin" in result.stdout
    assert "[harness:claude]" not in result.stdout
    logs_call = next(line for line in _docker_calls(path).splitlines() if " logs " in line)
    assert "--since " in logs_call
    assert logs_call.rstrip().endswith("backend-api")


@needs_bash
def test_harness_version_refused_at_start_warns_and_exits_non_zero(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    logs = path / "backend.log"
    logs.write_text(
        "backend-api-1  | [harness:codex] codex: npm install @openai/codex@0.999.0 failed\n"
        "backend-api-1  | [harness:codex] refused until the next start\n"
    )

    result = _run(
        "harness",
        "codex",
        "--version",
        "0.999.0",
        "--yes",
        cwd=path,
        env={**env, "SHIM_LOGS": str(logs)},
    )

    assert result.returncode != 0
    assert "[harness:codex] refused until the next start" in result.stdout
    assert "warning:" in result.stderr


@needs_bash
def test_upgrade_shows_dockers_own_error_when_the_release_cannot_be_read(
    installed: tuple[Path, dict[str, str]],
) -> None:
    """Only `No such file` means an older release; anything else is a failure, said in full."""
    path, env = installed
    before = (path / ".env").read_text()

    result = _run(
        "upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, "SHIM_IMAGE_ENV": "broken"}
    )

    assert result.returncode == 1, result.stdout + result.stderr
    assert RELEASE_IMAGE in result.stderr
    assert "layer does not exist" in result.stderr
    assert (path / ".env").read_text() == before


@needs_bash
def test_upgrade_without_the_release_contract_names_the_pins_to_set_by_hand(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run(
        "upgrade", "--tag", "2.0.0", "--yes", cwd=path, env={**env, "SHIM_IMAGE_ENV": "none"}
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for variable in PIN_VARIABLES.values():
        assert variable in result.stderr
    assert "by hand" in result.stderr


@needs_bash
def test_upgrade_with_a_missing_image_shows_dockers_output(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed

    result = _run("upgrade", "--tag", "2.0.0", "--yes", cwd=path, env=env)

    assert result.returncode == 1
    assert "Unable to find image" in result.stderr


@needs_bash
@pytest.mark.parametrize(
    ("old", "new", "downgrade"),
    [
        ("2.1.258", "2.1.99", True),
        ("2.1.99", "2.1.258", False),
        ("2.1.300", "2.1.300-beta.1", True),
        ("1.2.3+build-7", "1.2.3", False),
        ("2.1.300-beta.2", "2.1.300-beta.1", True),
        ("2.1.300-beta.1", "2.1.300-beta.2", False),
    ],
)
def test_upgrade_marks_only_a_downgrade(
    installed: tuple[Path, dict[str, str]], old: str, new: str, *, downgrade: bool
) -> None:
    path, env = installed
    dotenv = path / ".env"
    current = parse_env_example(dotenv)["CLAUDE_CODE_VERSION"]
    dotenv.write_text(
        dotenv.read_text().replace(f"CLAUDE_CODE_VERSION={current}", f"CLAUDE_CODE_VERSION={old}")
    )
    release = _release_env(path, CLAUDE_CODE_VERSION=new)

    result = _run(
        "upgrade",
        "--tag",
        "2.0.0",
        cwd=path,
        env={**env, "SHIM_IMAGE_ENV": str(release)},
        answers="n\n",
    )

    line = next(line for line in result.stdout.splitlines() if "CLAUDE_CODE_VERSION" in line)
    assert f"{old} → {new}" in line
    assert ("downgrade" in line) is downgrade


@needs_bash
def test_upgrade_reads_a_dotenv_pin_past_a_one_space_comment(
    installed: tuple[Path, dict[str, str]],
) -> None:
    path, env = installed
    dotenv = path / ".env"
    current = parse_env_example(dotenv)["CLAUDE_CODE_VERSION"]
    dotenv.write_text(
        dotenv.read_text().replace(
            f"CLAUDE_CODE_VERSION={current}", f"CLAUDE_CODE_VERSION={current} # kept by hand"
        )
    )
    before = dotenv.read_text()
    release = _release_env(path)

    result = _run(
        "upgrade",
        "--tag",
        "2.0.0",
        cwd=path,
        env={**env, "SHIM_IMAGE_ENV": str(release)},
        answers="n\n",
    )

    assert "CLAUDE_CODE_VERSION" not in result.stdout
    assert "harness CLI pins: unchanged" in result.stdout
    assert dotenv.read_text() == before
