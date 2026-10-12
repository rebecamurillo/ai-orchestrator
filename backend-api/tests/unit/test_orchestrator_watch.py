"""`deploy/kit/bin/orchestrator-watch` — the client-side watcher for one Run.

Phase 6 of the agent-delivery-kit plan (2026-10-01) ships a poll loop, not an always-on
agent: there is no push channel, and an idling agent burns context to learn nothing. The
script is what an `initiative-run` agent calls, so its **exit codes are its API** — the
caller branches on them without parsing anything.

There is no network and no instance here. A `curl` shim on PATH answers canned JSON per URL
from files and records its argv, the same technique `test_kit_install.py` uses; a `sleep`
shim records the seconds asked for, so a cadence can be asserted without any test waiting.

What is pinned:

- **The exit codes.** 0 `done`, 2 `needs_you`, 3 `failed`/`cancelled`, 1 an HTTP or usage
  error. A caller that mistakes a park for a success supervises nothing.
- **The park payload.** `.orchestrator/runs/<run_id>.json` is the file an agent is invoked
  on, so it carries the park kind, the reason, the admitted signals and the deep link — and
  never the token, because that file sits inside the client's repository.
- **The minimum cadence is enforced, not advisory.** The instance is shared; a client that
  can poll at 1 s will.
- **The token reaches no output line.** A client pastes this output into a bug report.
- **`--notify` degrades in silence** where no notifier exists, which is every CI box.
- **Notification is the default** (K-1 of `_bmad-output/specs/unattended-hub-run/PLAN.md`,
  2026-10-09): a client that parks overnight learns of it from the desktop, not from a
  terminal it left open; `--no-notify` is the opt-out.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

WATCH = REPO_ROOT / "deploy" / "kit" / "bin" / "orchestrator-watch"

RUN_ID = "0193f0c8-1d2b-7000-8000-00000000abcd"

#: distinctive enough that its absence from the output is a real assertion
TOKEN = "tok-never-printed-0123456789"

#: the one line the script prints per status change
LINE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z  (\S+)  (\S+)$")

#: the exit codes, which are this script's API
DONE = 0
HTTP_ERROR = 1
PARKED = 2
TERMINAL_FAILURE = 3

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

#: Answers `-o FILE -w '%{http_code}' URL`. Summary bodies are a `:`-separated queue, one per
#: call, the last repeating — that is how a Run is made to change status mid-loop.
CURL_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_LOG"
out=""
url=""
prev=""
for arg in "$@"; do
\tif [ "$prev" = "-o" ]; then out="$arg"; fi
\tcase "$arg" in http*) url="$arg" ;; esac
\tprev="$arg"
done
case "$url" in
\t*/detail)
\t\tif [ -n "${SHIM_DETAIL:-}" ] && [ -n "$out" ]; then cp "$SHIM_DETAIL" "$out"; fi
\t\tprintf '%s' "${SHIM_DETAIL_CODE:-200}"
\t\texit 0 ;;
esac
n=0
if [ -s "$SHIM_COUNT" ]; then n="$(cat "$SHIM_COUNT")"; fi
i=0
pick=""
old_ifs="$IFS"
IFS=":"
for f in ${SHIM_SUMMARY_FILES:-}; do
\tpick="$f"
\tif [ "$i" -ge "$n" ]; then break; fi
\ti=$((i + 1))
done
IFS="$old_ifs"
printf '%s' "$((n + 1))" > "$SHIM_COUNT"
if [ -n "$pick" ] && [ -n "$out" ]; then cp "$pick" "$out"; fi
printf '%s' "${SHIM_SUMMARY_CODE:-200}"
"""

SLEEP_SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$1" >> "$SLEEP_LOG"
"""

#: everything the script shells out to, so a restricted PATH can still run it
TOOLS = ("bash", "cat", "cp", "date", "env", "grep", "head", "mkdir", "mktemp", "rm", "sed", "tr")


class Sandbox:
    """A PATH with the two shims on it, the logs they write, and the project directory."""

    def __init__(self, tmp_path: Path, *, restricted: bool) -> None:
        self.bin = tmp_path / "bin"
        self.bin.mkdir()
        for name, body in (("curl", CURL_SHIM), ("sleep", SLEEP_SHIM)):
            (self.bin / name).write_text(body)
            (self.bin / name).chmod(0o755)
        if restricted:
            for tool in TOOLS:
                found = shutil.which(tool)
                if found is None:  # pragma: no cover - a box this thin cannot run the suite
                    pytest.skip(f"{tool} is not on PATH")
                (self.bin / tool).symlink_to(found)
            path = str(self.bin)
        else:
            path = f"{self.bin}:{os.environ['PATH']}"
        self.curl_log = tmp_path / "curl.log"
        self.curl_log.touch()
        self.sleep_log = tmp_path / "sleep.log"
        self.sleep_log.touch()
        self.count = tmp_path / "count"
        self.count.touch()
        self.project = tmp_path / "project"
        self.project.mkdir()
        self.env = {
            "PATH": path,
            "SHIM_LOG": str(self.curl_log),
            "SHIM_COUNT": str(self.count),
            "SLEEP_LOG": str(self.sleep_log),
        }

    def serves(self, *bodies: dict[str, object], detail: dict[str, object] | None = None) -> None:
        files: list[str] = []
        for index, body in enumerate(bodies):
            path = self.project.parent / f"summary-{index}.json"
            path.write_text(json.dumps(body, indent=2))
            files.append(str(path))
        self.env["SHIM_SUMMARY_FILES"] = ":".join(files)
        if detail is not None:
            path = self.project.parent / "detail.json"
            path.write_text(json.dumps(detail, indent=2))
            self.env["SHIM_DETAIL"] = str(path)

    def run(self, *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
        clean = {
            k: v
            for k, v in os.environ.items()
            if k
            not in {"PATH", "ORCHESTRATOR_BASE_URL", "ORCHESTRATOR_TOKEN", "ORCHESTRATOR_WEB_URL"}
        }
        return subprocess.run(  # fixed argv, no shell
            ["bash", str(WATCH), *args],
            capture_output=True,
            text=True,
            cwd=self.project,
            env={**clean, **self.env, **extra},
            check=False,
        )

    @property
    def sleeps(self) -> list[str]:
        return self.sleep_log.read_text().split()

    @property
    def calls(self) -> str:
        return self.curl_log.read_text()


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    return Sandbox(tmp_path, restricted=False)


def summary(status: str, **over: object) -> dict[str, object]:
    body: dict[str, object] = {
        "id": RUN_ID,
        "status": status,
        "template": "initiative-hub",
        "version": 1,
        "branch": "feat/initiative-stats",
        "budget_usd": "25.00",
        "spend_usd": "3.40",
        "admitted_signals": ["answer", "cancel"],
    }
    return {**body, **over}


def detail(park_kind: str, reason: str) -> dict[str, object]:
    """Shaped like the real one: a step row carries `reason` too, and prints first."""
    return {
        "id": RUN_ID,
        "steps": [{"path": "epics[0].stories[2]", "status": "blocked", "reason": "a step reason"}],
        "alert": {"token": "stop-token", "reason": reason, "park_kind": park_kind, "payload": {}},
    }


def statuses_of(stdout: str) -> list[str]:
    """The status of every change line the script printed, in order."""
    found = (LINE.match(line) for line in stdout.splitlines())
    return [match.group(1) for match in found if match is not None]


def bearer(token: str = TOKEN) -> dict[str, str]:
    return {"ORCHESTRATOR_TOKEN": token, "ORCHESTRATOR_BASE_URL": "http://127.0.0.1:8000"}


# ── the script parses ────────────────────────────────────────────────────────


@needs_bash
def test_the_script_parses_and_is_executable() -> None:
    assert WATCH.is_file()
    assert WATCH.stat().st_mode & 0o111, "orchestrator-watch is not executable"

    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(WATCH)], capture_output=True, text=True, check=False
    )
    assert result.returncode == DONE, result.stderr


@needs_bash
def test_help_names_every_flag_the_codes_and_the_web_url(box: Sandbox) -> None:
    result = box.run("--help")

    assert result.returncode == DONE, result.stderr
    flags = (
        "--base-url",
        "--interval-active",
        "--interval-idle",
        "--once",
        "--notify",
        "--no-notify",
    )
    for flag in flags:
        assert flag in result.stdout, flag
    assert "ORCHESTRATOR_WEB_URL" in result.stdout
    assert "4321" in result.stdout and "8000" in result.stdout
    for code in ("0", "1", "2", "3"):
        assert code in result.stdout, code


@needs_bash
def test_no_run_id_refuses_with_the_usage(box: Sandbox) -> None:
    result = box.run()

    assert result.returncode == HTTP_ERROR
    assert "orchestrator-watch <run_id>" in result.stderr


@needs_bash
def test_without_a_token_it_says_where_to_put_one(box: Sandbox) -> None:
    result = box.run(RUN_ID)

    assert result.returncode == HTTP_ERROR
    assert "ORCHESTRATOR_TOKEN" in result.stderr
    assert box.calls == ""


# ── the terminal states, each with its own code ──────────────────────────────


@needs_bash
def test_a_done_run_prints_one_line_and_exits_zero(box: Sandbox) -> None:
    box.serves(summary("done", spend_usd="7.10"))

    result = box.run(RUN_ID, "--once", **bearer())

    lines = [line for line in result.stdout.splitlines() if line]
    assert result.returncode == DONE, result.stdout + result.stderr
    assert len(lines) == 1, lines
    match = LINE.match(lines[0])
    assert match is not None, lines[0]
    assert (match.group(1), match.group(2)) == ("done", "7.10/25.00")
    assert f"{box.calls.count('/api/v1/runs/' + RUN_ID)}" == "1"
    assert "/detail" not in box.calls, "a done Run needs no detail read"


@needs_bash
@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_a_failed_or_cancelled_run_exits_three(box: Sandbox, status: str) -> None:
    box.serves(summary(status))

    result = box.run(RUN_ID, **bearer())

    assert result.returncode == TERMINAL_FAILURE, result.stdout + result.stderr
    assert status in result.stdout


@needs_bash
def test_once_on_a_running_run_reports_and_exits_zero(box: Sandbox) -> None:
    box.serves(summary("running"))

    result = box.run(RUN_ID, "--once", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert "running" in result.stdout
    assert box.sleeps == [], "--once never waits"


# ── a park: exit 2, the payload, the deep link ───────────────────────────────


@needs_bash
def test_needs_you_exits_two_with_the_park_kind_the_reason_and_the_deep_link(
    box: Sandbox,
) -> None:
    question = "which column holds the invoice total?"
    box.serves(summary("needs_you"), detail=detail("blocked", question))

    result = box.run(RUN_ID, **bearer())

    assert result.returncode == PARKED, result.stdout + result.stderr
    assert "blocked" in result.stdout
    assert question in result.stdout
    assert "a step reason" not in result.stdout, "the alert's reason, not a step's"
    assert "answer cancel" in result.stdout
    assert f"http://127.0.0.1:4321/workflows/{RUN_ID}" in result.stdout


@needs_bash
def test_the_park_payload_is_written_without_the_token(box: Sandbox) -> None:
    box.serves(summary("needs_you"), detail=detail("protected_path", "tests/test_x.py touched"))

    result = box.run(RUN_ID, **bearer())

    written = box.project / ".orchestrator" / "runs" / f"{RUN_ID}.json"
    assert result.returncode == PARKED, result.stdout + result.stderr
    assert TOKEN not in written.read_text()
    payload = json.loads(written.read_text())
    assert payload["run_id"] == RUN_ID
    assert payload["status"] == "needs_you"
    assert payload["park_kind"] == "protected_path"
    assert payload["reason"] == "tests/test_x.py touched"
    assert payload["admitted_signals"] == ["answer", "cancel"]
    assert payload["spend_usd"] == "3.40"
    assert payload["budget_usd"] == "25.00"
    assert payload["url"] == f"http://127.0.0.1:4321/workflows/{RUN_ID}"
    assert payload["observed_at"].endswith("Z")


@needs_bash
def test_the_web_url_overrides_the_port_rewrite(box: Sandbox) -> None:
    box.serves(summary("needs_you"), detail=detail("checkpoint", "approve the spec"))

    result = box.run(
        RUN_ID,
        "--base-url",
        "https://orchestrator.internal:9443",
        **bearer(),
        ORCHESTRATOR_WEB_URL="https://orchestrator.internal/",
    )

    assert result.returncode == PARKED, result.stdout + result.stderr
    assert f"https://orchestrator.internal/workflows/{RUN_ID}" in result.stdout
    assert "https://orchestrator.internal:9443/api/v1/runs" in box.calls


# ── the connection values ────────────────────────────────────────────────────


@needs_bash
def test_the_connection_is_read_from_the_project_dotenv(box: Sandbox) -> None:
    """What the kit installer writes is what the watcher reads — no exported variables."""
    dotenv = "ORCHESTRATOR_BASE_URL=http://127.0.0.1:8123  # the instance\n"
    (box.project / ".env").write_text(f"{dotenv}ORCHESTRATOR_TOKEN={TOKEN}\n")
    box.serves(summary("done"))

    result = box.run(RUN_ID, "--once")

    assert result.returncode == DONE, result.stdout + result.stderr
    assert f"http://127.0.0.1:8123/api/v1/runs/{RUN_ID}" in box.calls
    assert f"Authorization: Bearer {TOKEN}" in box.calls


# ── errors name the URL and the code, never the token ────────────────────────


@needs_bash
def test_a_refused_token_exits_one_naming_the_url_and_the_code(box: Sandbox) -> None:
    box.serves(summary("running"))

    result = box.run(RUN_ID, **bearer(), SHIM_SUMMARY_CODE="401")

    assert result.returncode == HTTP_ERROR
    assert f"http://127.0.0.1:8000/api/v1/runs/{RUN_ID}" in result.stderr
    assert "401" in result.stderr
    assert TOKEN not in result.stderr
    assert TOKEN not in result.stdout


@needs_bash
def test_the_token_reaches_no_output_line(box: Sandbox) -> None:
    """A client pastes this output into a bug report, and the payload file is committed."""
    box.serves(summary("needs_you"), detail=detail("blocked", "a question"))

    result = box.run(RUN_ID, "--notify", **bearer())

    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr


# ── the cadence is a floor, not a suggestion ─────────────────────────────────


@needs_bash
def test_an_active_interval_below_the_minimum_is_raised_to_it(box: Sandbox) -> None:
    box.serves(summary("running"), summary("done"))

    result = box.run(RUN_ID, "--interval-active", "1", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert box.sleeps == ["5"], box.sleeps
    assert "minimum" in result.stderr


@needs_bash
def test_an_idle_interval_below_the_minimum_is_raised_to_it(box: Sandbox) -> None:
    """A status this version does not know is polled at the idle cadence, not the active one."""
    box.serves(summary("a_status_from_a_newer_instance"), summary("done"))

    result = box.run(RUN_ID, "--interval-idle", "2", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert box.sleeps == ["30"], box.sleeps
    assert "minimum" in result.stderr


@needs_bash
def test_an_interval_above_the_minimum_is_honoured(box: Sandbox) -> None:
    box.serves(summary("running"), summary("done"))

    result = box.run(RUN_ID, "--interval-active", "60", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert box.sleeps == ["60"], box.sleeps


@needs_bash
def test_a_nonsense_interval_is_refused(box: Sandbox) -> None:
    result = box.run(RUN_ID, "--interval-active", "soon", **bearer())

    assert result.returncode == HTTP_ERROR
    assert "--interval-active" in result.stderr


@needs_bash
def test_only_a_status_change_prints_a_line(box: Sandbox) -> None:
    box.serves(summary("running"), summary("running"), summary("done"))

    result = box.run(RUN_ID, "--interval-active", "5", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert statuses_of(result.stdout) == ["running", "done"], result.stdout


# ── --notify degrades in silence ─────────────────────────────────────────────


@needs_bash
def test_notify_is_silent_where_no_notifier_exists(tmp_path: Path) -> None:
    """Every CI box, and any Linux desktop without libnotify."""
    box = Sandbox(tmp_path, restricted=True)
    assert shutil.which("osascript", path=str(box.bin)) is None
    assert shutil.which("notify-send", path=str(box.bin)) is None
    box.serves(summary("done", spend_usd="1.00"))

    result = box.run(RUN_ID, "--once", "--notify", **bearer())

    lines = [line for line in result.stdout.splitlines() if line]
    assert result.returncode == DONE, result.stdout + result.stderr
    assert len(lines) == 1, lines
    assert statuses_of(result.stdout) == ["done"]
    assert result.stderr == ""


# ── notification is the default ──────────────────────────────────────────────


NOTIFY_SHIM = """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$NOTIFY_LOG"
"""


def _with_notifier(tmp_path: Path) -> tuple[Sandbox, Path]:
    box = Sandbox(tmp_path, restricted=True)
    log = tmp_path / "notify.log"
    log.touch()
    (box.bin / "notify-send").write_text(NOTIFY_SHIM)
    (box.bin / "notify-send").chmod(0o755)
    box.env["NOTIFY_LOG"] = str(log)
    return box, log


@needs_bash
def test_a_status_change_notifies_without_any_flag(tmp_path: Path) -> None:
    """K-1 (2026-10-09): the client that forgot the flag is the one asleep at the park."""
    box, log = _with_notifier(tmp_path)
    box.serves(summary("done", spend_usd="1.00"))

    result = box.run(RUN_ID, "--once", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert log.read_text().splitlines() == [f"ai-orchestrator Run {RUN_ID} is done"]


@needs_bash
def test_no_notify_prints_only(tmp_path: Path) -> None:
    box, log = _with_notifier(tmp_path)
    box.serves(summary("done", spend_usd="1.00"))

    result = box.run(RUN_ID, "--once", "--no-notify", **bearer())

    assert result.returncode == DONE, result.stdout + result.stderr
    assert statuses_of(result.stdout) == ["done"]
    assert log.read_text() == ""
