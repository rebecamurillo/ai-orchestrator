"""`deploy/kit/install.sh` — plugging one project repository into a running instance.

A client runs this from inside their own repository, piped out of the instance
(`GET /api/v1/kit/install.sh | bash -s -- --harness claude`), so the kit they get is the one
built into the image that answered. There is no Docker and no network in this module: the
script's own control flow is what needs proving, and a `curl` shim on PATH is enough for all
of it — the same technique `test_deploy_install.py` uses for `docker`.

What is pinned here:

- **The projection is per harness.** `claude` reads `<project>/.claude/skills/`; `codex` and
  `opencode` both read `<project>/.agents/skills/` (`ia-agents-skills/README.md`); `all`
  writes both. Writing the wrong directory is a silent failure — the agent simply never sees
  the skill.
- **Everything it writes is idempotent.** A second run replaces the installed skill, and
  leaves an existing `.env` value alone: the two connection values belong to the project, and
  re-running an installer must never rotate a token a client already uses.
- **`.orchestrator/kit.json` is the version marker** the skill's handshake reads. It carries
  the kit version from `manifest.json` and the harness flag, is meant to be committed, and
  therefore must never carry the token.
- **The probe is `/api/v1/version`, and a skew is named.** The mismatch warning has to print
  the exact line that fixes it. `/api/v1/ping` is the fallback for an instance older than
  the route, not the primary check.
- **The token stays out of the output.** Not in a printed command line, not in a log line,
  not in stdout or stderr — the re-install line keeps `$ORCHESTRATOR_TOKEN` as a variable
  name for exactly that reason.
- **Remote mode installs from the served archive** when no `skills/` sits beside the script,
  which is what the documented one-liner does.

Delivery revised under the Operator decision of 2026-09-30 (agent-delivery-kit plan §1, §3
and §4): the instance serves its own kit, and version skew is unrepresentable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

KIT_DIR = REPO_ROOT / "deploy" / "kit"
INSTALL = KIT_DIR / "install.sh"
MANIFEST = KIT_DIR / "manifest.json"

#: a value distinctive enough that its absence from the output is a real assertion
TOKEN = "tok-never-printed-0123456789"

CLAUDE_SKILLS = ".claude/skills"
#: codex and opencode both read this one (`ia-agents-skills/README.md`)
AGENTS_SKILLS = ".agents/skills"

RE_INSTALL_LINE = (
    'curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" '
    '"$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness'
)

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

#: answers the two shapes the script asks for: `-o FILE URL` alone, and the same with
#: `-w '%{http_code}'`. A body is served from a file so no JSON has to survive shell quoting.
CURL_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_LOG"
out=""
url=""
wants_code=0
prev=""
for arg in "$@"; do
\tif [ "$prev" = "-o" ]; then out="$arg"; fi
\tif [ "$arg" = "-w" ]; then wants_code=1; fi
\tcase "$arg" in http*) url="$arg" ;; esac
\tprev="$arg"
done
emit() {
\tif [ -n "$out" ] && [ -n "$2" ]; then cp "$2" "$out"; fi
\tif [ "$wants_code" = 1 ]; then printf '%s' "$1"; exit 0; fi
\tcase "$1" in 2??) exit 0 ;; esac
\texit 22
}
case "$url" in
\t*/api/v1/version) emit "${SHIM_VERSION_CODE:-200}" "${SHIM_VERSION_FILE:-}" ;;
\t*/api/v1/ping) emit "${SHIM_PING_CODE:-200}" "" ;;
\t*/api/v1/kit/archive) emit "${SHIM_ARCHIVE_CODE:-200}" "${SHIM_ARCHIVE:-}" ;;
esac
emit 404 ""
"""


def _run(
    script: Path, *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run the script the way a client does — as a command, no shell."""
    clean = {
        k: v
        for k, v in os.environ.items()
        if k not in {"ORCHESTRATOR_BASE_URL", "ORCHESTRATOR_TOKEN"}
    }
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**clean, **(env or {})},
        check=False,
    )


def _kit_version() -> str:
    return str(json.loads(MANIFEST.read_text())["kit_version"])


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """The consumer repository: empty, as a fresh checkout is."""
    path = tmp_path / "project"
    path.mkdir()
    return path


@pytest.fixture
def shim(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    """A `curl` on PATH that records its argv and answers canned replies."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "curl").write_text(CURL_SHIM)
    (bin_dir / "curl").chmod(0o755)
    log = tmp_path / "curl.log"
    log.touch()
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "SHIM_LOG": str(log)}
    return bin_dir, log, env


def _version_body(tmp_path: Path, app_version: str) -> str:
    body = tmp_path / "version.json"
    body.write_text(
        json.dumps(
            {
                "app_version": app_version,
                "kit_version": app_version,
                "bmad_version": "6.11.0",
                "harness_versions": {"claude": "1.2.3", "codex": "4.5.6", "opencode": "7.8.9"},
            }
        )
    )
    return str(body)


def _archive(tmp_path: Path) -> str:
    """A real `.tar.gz` of `deploy/kit`, top-level entries as the endpoint serves them."""
    path = tmp_path / "kit.tar.gz"
    with tarfile.open(path, "w:gz") as tar:
        for entry in sorted(KIT_DIR.iterdir()):
            tar.add(entry, arcname=entry.name)
    return str(path)


# ── the script parses ────────────────────────────────────────────────────────


@needs_bash
def test_the_script_parses_and_is_executable() -> None:
    assert INSTALL.is_file()
    assert INSTALL.stat().st_mode & 0o111, "install.sh is not executable"

    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(INSTALL)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@needs_bash
def test_help_names_every_flag(tmp_path: Path) -> None:
    result = _run(INSTALL, "--help", cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    for flag in ("--harness", "--base-url", "--token", "--project"):
        assert flag in result.stdout, flag
    for harness in ("claude", "codex", "opencode", "all"):
        assert harness in result.stdout, harness


@needs_bash
def test_an_unknown_harness_is_refused(project: Path) -> None:
    result = _run(INSTALL, "--harness", "cursor", "--project", str(project), cwd=project)

    assert result.returncode != 0
    assert "--harness" in result.stderr
    assert not (project / CLAUDE_SKILLS).exists()


# ── the per-harness projection ───────────────────────────────────────────────


@needs_bash
def test_claude_writes_only_the_claude_directory(project: Path) -> None:
    result = _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / CLAUDE_SKILLS / "orchestrator" / "SKILL.md").is_file()
    assert not (project / ".agents").exists()


@needs_bash
@pytest.mark.parametrize("harness", ["codex", "opencode"])
def test_codex_and_opencode_share_the_agents_directory(project: Path, harness: str) -> None:
    result = _run(INSTALL, "--harness", harness, "--project", str(project), cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / AGENTS_SKILLS / "orchestrator" / "SKILL.md").is_file()
    assert not (project / ".claude").exists()


@needs_bash
def test_all_is_the_default_and_writes_both(project: Path) -> None:
    result = _run(INSTALL, "--project", str(project), cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / CLAUDE_SKILLS / "orchestrator" / "SKILL.md").is_file()
    assert (project / AGENTS_SKILLS / "orchestrator" / "SKILL.md").is_file()
    assert json.loads((project / ".orchestrator" / "kit.json").read_text())["harness"] == "all"


@needs_bash
def test_the_project_defaults_to_the_working_directory(project: Path) -> None:
    """The documented call is piped into bash from inside the repository, with no path."""
    result = _run(INSTALL, "--harness", "claude", cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / CLAUDE_SKILLS / "orchestrator" / "SKILL.md").is_file()


@needs_bash
def test_a_bare_directory_argument_still_works(project: Path, tmp_path: Path) -> None:
    """The pre-2026-09-30 call was `install.sh /path/to/project`."""
    result = _run(INSTALL, str(project), cwd=tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / CLAUDE_SKILLS / "orchestrator" / "SKILL.md").is_file()


@needs_bash
def test_re_running_replaces_the_installed_copy(project: Path) -> None:
    _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)
    installed = project / CLAUDE_SKILLS / "orchestrator"
    (installed / "stale.md").write_text("from an older kit\n")

    result = _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert not (installed / "stale.md").exists()
    assert (installed / "SKILL.md").is_file()
    assert (installed / "references" / "api.md").is_file()


# ── the two connection values ────────────────────────────────────────────────


@needs_bash
def test_the_connection_values_are_added_once(project: Path) -> None:
    _run(
        INSTALL,
        "--harness",
        "claude",
        "--base-url",
        "http://127.0.0.1:8123",
        "--project",
        str(project),
        cwd=project,
    )
    _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)

    lines = (project / ".env").read_text().splitlines()

    assert lines.count("ORCHESTRATOR_BASE_URL=http://127.0.0.1:8123") == 1
    assert [line for line in lines if line.startswith("ORCHESTRATOR_TOKEN=")] == [
        "ORCHESTRATOR_TOKEN="
    ]


@needs_bash
def test_an_existing_value_is_never_overwritten(project: Path) -> None:
    """The two values belong to the project; re-installing must not rotate the token."""
    (project / ".env").write_text(
        "ORCHESTRATOR_BASE_URL=http://elsewhere:9999\nORCHESTRATOR_TOKEN=already-mine\n"
    )

    result = _run(
        INSTALL,
        "--harness",
        "claude",
        "--base-url",
        "http://127.0.0.1:8000",
        "--token",
        TOKEN,
        "--project",
        str(project),
        cwd=project,
    )

    assert "left alone" in result.stdout
    assert (project / ".env").read_text() == (
        "ORCHESTRATOR_BASE_URL=http://elsewhere:9999\nORCHESTRATOR_TOKEN=already-mine\n"
    )
    marker = json.loads((project / ".orchestrator" / "kit.json").read_text())
    assert marker["base_url"] == "http://elsewhere:9999"


@needs_bash
def test_a_dotenv_without_a_final_newline_keeps_its_last_line(project: Path) -> None:
    (project / ".env").write_text("EXISTING=value")

    _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)

    assert "EXISTING=value" in (project / ".env").read_text().splitlines()


# ── the version marker ───────────────────────────────────────────────────────


@needs_bash
def test_the_marker_records_the_manifest_version_the_harness_and_no_token(project: Path) -> None:
    _run(
        INSTALL,
        "--harness",
        "codex",
        "--token",
        TOKEN,
        "--base-url",
        "http://127.0.0.1:8123",
        "--project",
        str(project),
        cwd=project,
    )

    text = (project / ".orchestrator" / "kit.json").read_text()
    marker = json.loads(text)

    assert marker["kit_version"] == _kit_version()
    assert marker["harness"] == "codex"
    assert marker["base_url"] == "http://127.0.0.1:8123"
    assert marker["installed_at"].endswith("Z")
    assert TOKEN not in text


# ── the probe ────────────────────────────────────────────────────────────────


@needs_bash
def test_the_probe_calls_version_with_a_bearer_and_prints_the_app_version(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    _, log, env = shim
    env = {**env, "SHIM_VERSION_FILE": _version_body(tmp_path, _kit_version())}

    result = _run(
        INSTALL,
        "--harness",
        "claude",
        "--token",
        TOKEN,
        "--base-url",
        "http://127.0.0.1:8000",
        "--project",
        str(project),
        cwd=project,
        env=env,
    )

    calls = log.read_text()
    assert result.returncode == 0, result.stdout + result.stderr
    assert "http://127.0.0.1:8000/api/v1/version" in calls, calls
    assert f"Authorization: Bearer {TOKEN}" in calls, "the bearer never reached curl"
    assert "/api/v1/ping" not in calls, "ping is the fallback, not the check"
    assert _kit_version() in result.stdout
    assert "warning" not in result.stderr


@needs_bash
def test_a_version_mismatch_warns_with_the_reinstall_line(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    _, _, env = shim
    env = {**env, "SHIM_VERSION_FILE": _version_body(tmp_path, "99.0.0")}

    result = _run(
        INSTALL,
        "--harness",
        "codex",
        "--token",
        TOKEN,
        "--project",
        str(project),
        cwd=project,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "99.0.0" in result.stderr
    assert f"{RE_INSTALL_LINE} codex" in result.stderr


@needs_bash
def test_the_token_reaches_no_output_line(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    """kit.json is committed and a client pastes this output into a bug report."""
    _, _, env = shim
    env = {**env, "SHIM_VERSION_FILE": _version_body(tmp_path, "99.0.0")}

    result = _run(INSTALL, "--token", TOKEN, "--project", str(project), cwd=project, env=env)

    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr


@needs_bash
def test_without_a_token_the_probe_is_skipped_and_says_how_to_set_it(project: Path) -> None:
    result = _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ORCHESTRATOR_TOKEN" in result.stdout
    assert (project / CLAUDE_SKILLS / "orchestrator" / "SKILL.md").is_file()


@needs_bash
def test_a_404_on_version_falls_back_to_ping_and_says_so(
    project: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    """An instance older than the route still answers `/api/v1/ping`."""
    _, log, env = shim
    env = {**env, "SHIM_VERSION_CODE": "404"}

    result = _run(
        INSTALL,
        "--harness",
        "claude",
        "--token",
        TOKEN,
        "--project",
        str(project),
        cwd=project,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "404" in result.stdout
    assert "/api/v1/ping" in log.read_text()
    assert "token accepted" in result.stdout


@needs_bash
def test_a_refused_token_stops_the_script(
    project: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    _, _, env = shim
    env = {**env, "SHIM_VERSION_CODE": "401"}

    result = _run(
        INSTALL,
        "--harness",
        "claude",
        "--token",
        TOKEN,
        "--project",
        str(project),
        cwd=project,
        env=env,
    )

    assert result.returncode != 0
    assert "401" in result.stderr
    assert TOKEN not in result.stderr


# ── remote mode: the kit comes out of the instance ───────────────────────────


@needs_bash
def test_remote_mode_installs_from_the_served_archive(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    """What the documented one-liner does: no `skills/` beside the script, so it fetches."""
    _, log, env = shim
    piped = tmp_path / "piped"
    piped.mkdir()
    shutil.copy(INSTALL, piped / "install.sh")
    env = {
        **env,
        "SHIM_ARCHIVE": _archive(tmp_path),
        "SHIM_VERSION_FILE": _version_body(tmp_path, _kit_version()),
    }

    result = _run(
        piped / "install.sh",
        "--harness",
        "claude",
        "--token",
        TOKEN,
        "--project",
        str(project),
        cwd=project,
        env=env,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "/api/v1/kit/archive" in log.read_text()
    assert (project / CLAUDE_SKILLS / "orchestrator" / "SKILL.md").is_file()
    marker = json.loads((project / ".orchestrator" / "kit.json").read_text())
    assert marker["kit_version"] == _kit_version()


@needs_bash
def test_remote_mode_without_a_token_refuses_and_names_the_flag(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    _, _, env = shim
    piped = tmp_path / "piped"
    piped.mkdir()
    shutil.copy(INSTALL, piped / "install.sh")

    result = _run(
        piped / "install.sh", "--harness", "claude", "--project", str(project), cwd=project, env=env
    )

    assert result.returncode != 0
    assert "--token" in result.stderr
    assert not (project / ".orchestrator").exists()


@needs_bash
def test_an_unreachable_archive_is_reported_with_its_url(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    _, _, env = shim
    piped = tmp_path / "piped"
    piped.mkdir()
    shutil.copy(INSTALL, piped / "install.sh")
    env = {**env, "SHIM_ARCHIVE_CODE": "502"}

    result = _run(
        piped / "install.sh", "--token", TOKEN, "--project", str(project), cwd=project, env=env
    )

    assert result.returncode != 0
    assert "/api/v1/kit/archive" in result.stderr
    assert TOKEN not in result.stderr


# ── the kit's commands ───────────────────────────────────────────────────────
# Added with `orchestrator-watch` (agent-delivery-kit plan phase 6, 2026-10-01).

WATCHER = ".orchestrator/bin/orchestrator-watch"


@needs_bash
def test_the_watcher_lands_executable_with_its_path_line(project: Path) -> None:
    """A watcher that is not executable, or that the client cannot find, supervises nothing."""
    result = _run(INSTALL, "--harness", "claude", "--project", str(project), cwd=project)

    watcher = project / WATCHER
    assert result.returncode == 0, result.stdout + result.stderr
    assert watcher.is_file()
    assert watcher.stat().st_mode & 0o111, "orchestrator-watch is not executable"
    assert str(project / ".orchestrator" / "bin") in result.stdout
    assert "export PATH=" in result.stdout


@needs_bash
def test_remote_mode_installs_the_watcher_from_the_served_archive(
    project: Path, tmp_path: Path, shim: tuple[Path, Path, dict[str, str]]
) -> None:
    _, _, env = shim
    piped = tmp_path / "piped"
    piped.mkdir()
    shutil.copy(INSTALL, piped / "install.sh")
    env = {
        **env,
        "SHIM_ARCHIVE": _archive(tmp_path),
        "SHIM_VERSION_FILE": _version_body(tmp_path, _kit_version()),
    }

    result = _run(
        piped / "install.sh",
        "--harness",
        "claude",
        "--token",
        TOKEN,
        "--project",
        str(project),
        cwd=project,
        env=env,
    )

    watcher = project / WATCHER
    assert result.returncode == 0, result.stdout + result.stderr
    assert watcher.is_file()
    assert watcher.stat().st_mode & 0o111, "orchestrator-watch is not executable"
