"""`CodexHarness`: `codex exec --json` through the `ProcessRunner` port (AD-10, AD-14, FR-14).

The invocation is written once, here, and nowhere else:

    codex exec --json -C {worktree} -m {model} -o {log_path}.last.md
               [-c otel.log_user_prompt=true] "{prompt}"

**Every flag above is provisional and is marked as such where it is defined.** This story never
runs the CLI — `briefs/7-1-codex-adapter.md` puts running it in 7.2 — so what is implemented is
the shape that brief documents, with a `[verify]` marker against the argv, the session event,
the resume form and the content switch. `addendum.md` §B records the same list. Story 7.2
settles them against the real Codex CLI at `CODEX_VERSION` on the real host; until it has, none
of these names is a fact, and a green test here is a test of the shape and not of the CLI.

**`--full-auto` is never used** (deprecated), and no sandbox flag is passed either: approvals and
the sandbox are `approval_policy = "never"` and `sandbox_mode = "danger-full-access"` in
`config.toml`, which `scripts/harness/codex.sh configure` writes at container start. The
container is the sandbox (AD-10). Whether `--skip-git-repo-check` is additionally needed under
`cap_drop ALL` is one of the open `[verify]` items and is *not* passed today, because a flag
added on a guess is as wrong as one left out on a guess.

**Static configuration is not this module's** (AD-10). The provider, the gateway base URL, the
five per-attempt headers by environment-variable *name*, and the `[otel]` exporter all live in
`config.toml`; the adapter writes nothing under `AGENT_HOME`. The one file it does write is the
prompt, beside the log, so an attempt's record holds what was asked as well as what came back.
The one *environment* name it adds is `CODEX_HOME`, through `codex_aliases` — see that function.

**The session is captured, not assigned** (`capabilities.preassign_session = False`). Codex names
its own thread, so the `session_id` the caller pre-allocated never reaches the command line, and
`start`'s handle carries no session at all: only `wait`, which reads the stream, can report one.
One consequence follows and is not a defect of this adapter but of the capability: an attempt
whose backend dies between `start` and `wait` has no session to resume, where a `claude` attempt
would have had one written before the process was awaited (AD-14). `resume` is the exception —
it already knows the thread it continued, so it keeps that id when the stream names none.

**A dispatch is two halves** (AD-14, 5.4), exactly as `ClaudeHarness`: `start` hands back a
`HarnessHandle` carrying the process group, `wait` blocks on it and reads the log, and `run` is
`wait(start(...))` — so `application/steps/agent.py` can commit `attempt.pgid` between the two.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from orchestrator.domain.ports.harness import (
    HarnessCapabilities,
    HarnessHandle,
    HarnessResult,
)
from orchestrator.domain.ports.process import Handle, ProcessRunner
from orchestrator.infrastructure.harness.codex.events import (
    events as stream_events,
)
from orchestrator.infrastructure.harness.codex.events import (
    result_object,
    session_id_from,
    usage_from,
)
from orchestrator.infrastructure.harness.env import AliasBuilder
from orchestrator.infrastructure.harness.jsonl import ENCODING, read_text
from orchestrator.infrastructure.settings import Settings

#: The executable `scripts/harness/codex.sh install` puts on `PATH` at `CODEX_VERSION`.
EXECUTABLE = "codex"
#: The non-interactive subcommand, and the one that continues a thread it already opened.
EXEC = "exec"
RESUME = "resume"

#: **Provisional** (addendum §B, 7.2 verifies): the four flags of the documented invocation.
#: `--json` is what makes the run readable at all; `-C` is the worktree, passed even though the
#: `ProcessRunner` already starts the process there, because the brief's shape names it and a
#: harness that resolves paths against its own idea of the directory should be told which one;
#: `-m` is omitted entirely when the Template bound no model; `-o` is where Codex writes the
#: turn's last message, beside the log rather than into it.
JSON_FLAG = "--json"
WORKTREE_FLAG = "-C"
MODEL_FLAG = "-m"
LAST_MESSAGE_FLAG = "-o"
#: The suffix `LAST_MESSAGE_FLAG` points at, beside the attempt's own log.
LAST_MESSAGE_SUFFIX = ".last.md"

#: **Provisional** (addendum §B, 7.2 verifies): the content switch. It is a command-line
#: override and not an environment name — unlike Claude Code's `OTEL_LOG_*` pair — because
#: `config.toml` is static and ships `log_user_prompt = false`, and the Project's setting is
#: per attempt. `-c` takes `key=value`; a value that needed quoting would have to be TOML, but
#: `true` is a bare boolean and does not.
CONFIG_FLAG = "-c"
CONTENT_SWITCH = "otel.log_user_prompt=true"
#: The contract name `env.py` sets from `project.log_prompt_content`, and the value that is on.
LOG_CONTENT_NAME = "ORCH_LOG_CONTENT"
LOG_CONTENT_ON = "1"

#: The suffix the prompt is written under, beside the attempt's own log — the port's convention.
PROMPT_SUFFIX = ".prompt"

#: The environment name `scripts/harness/codex.sh` exports and `configure` writes `config.toml`
#: under, and the directory it names inside `AGENT_HOME`.
CODEX_HOME = "CODEX_HOME"
CODEX_HOME_DIR = ".codex"

#: **Provisional** (addendum §B, 7.2 verifies): what the Operator pastes to take the thread over
#: by hand (FR-21). Interactive `codex resume`, not `codex exec resume`: the point of the line is
#: a terminal session, and the read model wraps it in the container's own `docker compose exec`.
RESUME_COMMAND = "cd {cwd} && codex resume {session_id}"


def codex_aliases(agent_home: Path) -> AliasBuilder:
    """The harness-native names a `codex` process receives, which is `CODEX_HOME` and no other.

    `scripts/harness/codex.sh` declares `HARNESS_ENV_ALIASES=()` — Codex reads the contract
    names directly, through `env_key = "LITELLM_API_KEY"` and an `env_http_headers` map naming
    the five AD-11 headers against `ORCH_*` — so there is no credential to alias and this
    builder carries no value out of the contract at all.

    `CODEX_HOME` is not an alias and is not in that array: the script `export`s it for its own
    `install`/`configure`/`doctor` runs. But a harness process receives exactly what `env_for`
    returns plus the five names the runner re-adds, and `CODEX_HOME` is in neither list, so
    without this the CLI would read `~/.codex` instead of the `config.toml` `configure` wrote.

    A **factory** rather than an `AliasBuilder` directly, because the value is `AGENT_HOME`'s,
    which is a `Settings` field, and `AliasBuilder` takes the contract and nothing else — the
    signature that keeps `env.py` harness-agnostic (AD-5). Binding the path here rather than
    reading a setting inside the builder is what preserves that.
    """
    home = str(agent_home / CODEX_HOME_DIR)

    def aliases(contract: Mapping[str, str]) -> Mapping[str, str]:
        return {CODEX_HOME: home}

    return aliases


class CodexHarness:
    """Codex CLI, non-interactive, in the worktree, under the runner's own deadline."""

    name = "codex"
    #: `preassign_session` is False: the thread is Codex's to name, and this adapter reads it
    #: back out of the stream. `native_tracing` is True on the strength of the `[otel]` block
    #: `configure` writes; whether the inbound `TRACEPARENT` is honoured is source-verified
    #: only (`research/tracing.md` §Codex) and is 7.2's day-1 check.
    capabilities = HarnessCapabilities(preassign_session=False, resume=True, native_tracing=True)

    def __init__(self, runner: ProcessRunner, settings: Settings) -> None:
        self.runner = runner
        self.settings = settings

    def run(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal,
        timeout_min: float,
        log_path: Path,
    ) -> HarnessResult:
        """First dispatch, start to finish: exactly `wait(start(...))` (AD-14)."""
        return self.wait(
            self.start(
                cwd=cwd,
                prompt=prompt,
                env=env,
                model=model,
                session_id=session_id,
                budget_usd_remaining=budget_usd_remaining,
                timeout_min=timeout_min,
                log_path=log_path,
            )
        )

    def start(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal,
        timeout_min: float,
        log_path: Path,
    ) -> HarnessHandle:
        """Start the dispatch and hand its group back before anything waits on it (AD-14).

        `session_id` and `budget_usd_remaining` are accepted because the port declares them and
        used by neither: Codex names its own thread, and the Run's remaining budget is enforced
        by the Gateway's own key budget rather than by a CLI flag this harness has. The handle
        therefore carries no session — `wait` is the half that can report one.
        """
        argv = self._argv(
            [WORKTREE_FLAG, str(cwd)],
            model=model,
            env=env,
            log_path=log_path,
            message=prompt,
        )
        self._record_prompt(log_path, prompt)
        return self._start(argv, cwd=cwd, env=env, timeout_min=timeout_min, log_path=log_path)

    def resume(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        session_id: str,
        message: str,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
    ) -> HarnessResult:
        """Continue the thread this row already opened — `retry`'s path only (AD-10).

        **Provisional** (addendum §B, 7.2 verifies): `codex exec resume {id} --json "{message}"`
        is the brief's documented form, and it is passed exactly, with no worktree, model or
        `-o` flag of its own — a resumed turn runs in the same process group, in the same
        directory the runner starts it in, under the thread's own configuration.
        """
        argv = [EXECUTABLE, EXEC, RESUME, session_id, JSON_FLAG, message]
        self._record_prompt(log_path, message)
        return self.wait(
            self._start(
                argv,
                cwd=cwd,
                env=env,
                timeout_min=timeout_min,
                log_path=log_path,
                session_id=session_id,
            )
        )

    def resume_command(self, cwd: str, session_id: str) -> str:
        """What the Operator pastes to take the thread over by hand (FR-21).

        Identifiers only, and by construction: the two things it interpolates are a path and a
        thread id, so there is no value in it a credential could travel in (AD-5).
        """
        return RESUME_COMMAND.format(cwd=cwd, session_id=session_id)

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Wait for the process `start` returned, then read its stream (AD-14, AD-10).

        The wait is guarded because the group is the only handle on the process and this frame
        is the only place that holds it: a `wait` that raises would leave a coding agent running
        in a worktree with nothing left that knows its `pgid`, which is the orphan AD-14 exists
        to prevent. The kill is the runner's own idempotent one, so it is safe on a process that
        already ended, and the exception still reaches the walker.

        The session is the stream's, falling back to the handle's: a first dispatch's handle
        carries none, so a stream with no `thread.started` reports `None` and 7.2's `session id
        recorded` readiness line is what fails; a `resume`'s handle carries the thread it was
        told to continue, which stays the attempt's session whatever the stream printed.
        """
        try:
            outcome = self.runner.wait(Handle(pid=handle.pid, pgid=handle.pgid))
        except BaseException:
            # BaseException, not Exception: a cancelled walker thread must not orphan a harness
            # either. The group is killed and the original exception re-raised.
            self.runner.kill_group(handle.pgid)
            raise
        stream = stream_events(read_text(handle.log_path))
        raw_result = result_object(stream)
        captured = session_id_from(stream)
        # This adapter is the first that can answer `None`, which is why the port's field is
        # `str | None`: `agent_tail.finish` writes this value straight onto `Attempt.session_id`
        # (itself `str | None`), so "no thread was named" is recorded as the absence it is
        # rather than as an empty string a later `resume` would try to continue.
        return HarnessResult(
            session_id=captured if captured is not None else (handle.session_id or None),
            exit_code=outcome.exit_code,
            log_path=handle.log_path,
            usage=usage_from(raw_result),
            timed_out=outcome.timed_out,
            pgid=handle.pgid,
            raw_result=raw_result,
        )

    def _argv(
        self,
        placement: list[str],
        *,
        model: str | None,
        env: Mapping[str, str],
        log_path: Path,
        message: str,
    ) -> list[str]:
        """The whole command line. Pure: everything it reads is an argument."""
        argv = [EXECUTABLE, EXEC, JSON_FLAG, *placement]
        if model is not None:
            argv += [MODEL_FLAG, model]
        argv += [LAST_MESSAGE_FLAG, f"{log_path}{LAST_MESSAGE_SUFFIX}"]
        if env.get(LOG_CONTENT_NAME) == LOG_CONTENT_ON:
            argv += [CONFIG_FLAG, CONTENT_SWITCH]
        argv.append(message)
        return argv

    def _start(  # noqa: PLR0913 — the runner's own call, one argument per port parameter
        self,
        argv: list[str],
        *,
        cwd: Path,
        env: Mapping[str, str],
        timeout_min: float,
        log_path: Path,
        session_id: str = "",
    ) -> HarnessHandle:
        """The runner's handle, as the port's own: what `wait` needs and nothing more.

        `session_id` defaults to the empty string — the first dispatch's honest answer, since
        the thread does not exist until Codex prints it — and `resume` passes the thread it was
        given, which is the only case where a handle can carry one.
        """
        handle = self.runner.start(
            argv, cwd=cwd, env=env, timeout_min=timeout_min, log_path=log_path
        )
        return HarnessHandle(
            session_id=session_id, log_path=log_path, pid=handle.pid, pgid=handle.pgid
        )

    def _record_prompt(self, log_path: Path, message: str) -> None:
        """The prompt, beside the log, so an attempt's record holds what was asked."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(message, encoding=ENCODING)
