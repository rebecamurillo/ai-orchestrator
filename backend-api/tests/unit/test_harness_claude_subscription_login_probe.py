"""`claude.sh probe`'s subscription-auth login check (readiness simplification, 2026-09-23).

`probe_gateway_models` (`_common.sh`) tests the Gateway's own key, `LITELLM_API_KEY`. In
subscription mode (`CLAUDE_SUBSCRIPTION_AUTH=true`) `claude -p` never receives that key — it
authenticates through `claude login`'s own OAuth session instead (AD-10) — so the Gateway
check cannot see a missing or expired login. Before this change that gap was only caught deep
into a dispatched readiness Run (an `epic@1` Run against the fixture repo), slowly: the
Operator watched Claude "blocked" on auth for minutes before the Run finally failed. `probe()`
now runs `claude auth status` first, so `POST /harnesses/claude/readiness` (which re-checks
the Probe before ever dispatching, `use_cases/harness_readiness.start`) refuses immediately
instead.

Coverage here is the script's own logic in isolation, against a fake `claude` executable —
`test_harness_scripts_probe.py` only asserts the `probe()` function and dispatcher entry
exist; nothing before this module exercised the real bash logic end to end.
"""

from __future__ import annotations

import os
import stat
import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_SCRIPT = REPO_ROOT / "scripts" / "harness" / "claude.sh"
PINNED_VERSION = "2.1.258"
#: `probe_claude_login`'s own bound (10s) plus generous headroom for bash/python start-up and
#: a loaded CI runner — this is a smoke bound, not a precision timing assertion.
STALL_BOUND_SECONDS = 25

pytestmark = pytest.mark.skipif(
    not CLAUDE_SCRIPT.is_file(), reason="scripts/harness/claude.sh is missing"
)


def _fake_claude(
    bin_dir: Path,
    *,
    body: str = '{"loggedIn": true}',
    exit_code: int = 0,
    delay_seconds: float = 0.0,
) -> Path:
    """A `claude` stand-in: `--version` reports the pinned version; `auth status` records
    that it was called (so a test can prove it never was) and answers with `body`."""
    marker = bin_dir / "auth-status-called"
    script = bin_dir / "claude"
    script.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then\n'
        f"  printf '{PINNED_VERSION} (Claude Code)\\n'\n"
        "  exit 0\n"
        "fi\n"
        'if [ "$1" = "auth" ] && [ "$2" = "status" ]; then\n'
        f'  touch "{marker}"\n'
        f"  sleep {delay_seconds}\n"
        f"  printf '%s' '{body}'\n"
        f"  exit {exit_code}\n"
        "fi\n"
        'echo "fake claude: unexpected invocation: $*" >&2\n'
        "exit 99\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


def _run_probe(bin_dir: Path, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HOME": os.environ.get("HOME", "/tmp"),
        "CLAUDE_CODE_VERSION": PINNED_VERSION,
        # Declared blank = disabled (`litellm_enabled`) — the login check must stand on its
        # own, never depend on (or be masked by) the Gateway path.
        "LITELLM_BASE_URL": "",
        "LANGFUSE_BASE_URL": "",
        **extra_env,
    }
    return subprocess.run(
        ["bash", str(CLAUDE_SCRIPT), "probe"],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )


def test_the_login_check_never_runs_outside_subscription_mode(tmp_path: Path) -> None:
    """`CLAUDE_SUBSCRIPTION_AUTH` unset is API-key mode (the `.env.example` default) — the
    Gateway key check already covers that mode's real credential; `claude auth status` must
    not run at all."""
    _fake_claude(tmp_path, exit_code=1, body="")

    result = _run_probe(tmp_path, {})

    assert not (tmp_path / "auth-status-called").exists()
    assert '"ok":true' in result.stdout, result.stdout + result.stderr


def test_a_logged_out_subscription_fails_the_probe_with_a_naming_reason(tmp_path: Path) -> None:
    _fake_claude(tmp_path, body='{"loggedIn": false}')

    result = _run_probe(tmp_path, {"CLAUDE_SUBSCRIPTION_AUTH": "true"})

    assert (tmp_path / "auth-status-called").exists()
    assert '"ok":false' in result.stdout, result.stdout + result.stderr
    assert "not logged in" in result.stdout


def test_a_logged_in_subscription_passes_the_probe(tmp_path: Path) -> None:
    _fake_claude(tmp_path, body='{"loggedIn": true}')

    result = _run_probe(tmp_path, {"CLAUDE_SUBSCRIPTION_AUTH": "true"})

    assert '"ok":true' in result.stdout, result.stdout + result.stderr


def test_a_stalled_login_check_cannot_slow_the_probe_down(tmp_path: Path) -> None:
    """The exact failure the Operator reported: Claude was blocked on auth but took too long
    to return. `claude auth status` itself must be timeout-bounded, not just fast when it
    behaves."""
    _fake_claude(tmp_path, body='{"loggedIn": true}', delay_seconds=60)

    started = time.monotonic()
    result = _run_probe(tmp_path, {"CLAUDE_SUBSCRIPTION_AUTH": "true"})
    elapsed = time.monotonic() - started

    assert elapsed < STALL_BOUND_SECONDS, (
        f"probe took {elapsed:.1f}s — a stalled CLI must not slow it down"
    )
    assert '"ok":false' in result.stdout, result.stdout + result.stderr
    assert "timed out" in result.stdout


def test_malformed_login_status_output_fails_the_probe_with_a_naming_reason(
    tmp_path: Path,
) -> None:
    """A CLI incompatibility (renamed subcommand, an update banner on stdout) must be
    distinguishable from an actual logged-out session, not folded into the same reason."""
    _fake_claude(tmp_path, body="not json")

    result = _run_probe(tmp_path, {"CLAUDE_SUBSCRIPTION_AUTH": "true"})

    assert '"ok":false' in result.stdout, result.stdout + result.stderr
    assert "cli error" in result.stdout
