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
esac
case "$*" in
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
    *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the installer the way a client does — as a command, no shell."""
    dropped = {"GHCR_TOKEN", "GITHUB_TOKEN", "IMAGE_TAG", "DOCKER_CONFIG"}
    clean = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(cwd / "install.sh"), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**clean, **(env or {})},
        check=False,
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
    assert "restart backend-api" in calls, calls
    assert "claude: enabled" in result.stdout


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
