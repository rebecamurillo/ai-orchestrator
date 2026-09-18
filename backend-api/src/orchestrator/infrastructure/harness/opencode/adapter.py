"""`LocalHarness`: `opencode run --format json` through the `ProcessRunner` port (AD-10, AD-14).

The harness table's row, the Template's `harness:` value and this adapter's `name` are all
`local`; OpenCode is the CLI it drives, which is why the package is `opencode/` and the key is
not. The invocation is written once, here, and nowhere else:

    opencode run --format json --dir {worktree} -m litellm/{model} "{prompt}"

**Every flag above is provisional and is marked as such where it is defined.** This story never
runs the CLI — `briefs/7-3-opencode-adapter.md` puts running it in 7.4, together with the host
model server — so what is implemented is the shape that brief documents, with a `[verify]`
marker against the argv, the session capture, the store fallback and the content switch.
`addendum.md` §B records the same list.

**Static configuration is not this module's** (AD-10). The `litellm` provider, the gateway base
URL, the five per-attempt headers by environment-variable *name*, the Langfuse plugin at
`LANGFUSE_OPENCODE_PLUGIN_VERSION`, one model entry per `LOCAL_MODELS` alias and
`permission: {edit: allow, bash: allow, webfetch: deny}` all live in
`~/.config/opencode/opencode.json`, which `scripts/harness/opencode.sh configure` writes at
container start. The adapter writes nothing under `AGENT_HOME`. There is no `--auto` flag and
none is passed: auto-approval is that `permission` block, and the container is the sandbox.

**The model always carries its provider.** Unlike `codex`, the flag is never dropped when the
Template bound none: OpenCode's own default is whatever its config lists first, and the Gateway
serves a route only for the aliases `LOCAL_MODELS` names — so an unbound model resolves to the
first of those, `litellm/`-prefixed, which is the provider `configure` wrote.

**The session is captured, not assigned** (`capabilities.preassign_session = False`), and it has
two sources rather than one. The stream is the first (`events.py`); the session store is the
fallback (`sessions.py`), which is why `HarnessHandle` carries the worktree — `wait` is the half
that reads, and `start` is the half that was told the directory.

**There is no resume** (`capabilities.resume = False`). `research/tracing.md` §OpenCode and the
brief agree: `opencode run` opens a session, and this system does not continue one across
attempts. `application/steps/agent.py` reads the capability and retries by prepending the retry
prompt to a fresh dispatch (5.5), and `resume_command` is `None` so the Run detail hides the
terminal block entirely (FR-21, 6.7) rather than printing a line that cannot work.

**Tracing is by identity, never by parent** (AD-11, `capabilities.native_tracing = False`).
OpenCode honours no inbound `TRACEPARENT` — it still receives one, because the contract is exact
— and the Langfuse plugin opens its own trace per turn keyed by the OpenCode session, carrying
`userId` from `LANGFUSE_USER_ID`. `local_aliases` below is the whole of how the Run gets onto
that trace, and `infrastructure/tracing/user_level.py` is the rule that reads it back.

**A dispatch is two halves** (AD-14, 5.4), exactly as `ClaudeHarness` and `CodexHarness`.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from orchestrator.domain.ports.harness import HarnessCapabilities, HarnessHandle, HarnessResult
from orchestrator.domain.ports.process import Handle, ProcessRunner
from orchestrator.infrastructure.harness.jsonl import ENCODING, read_text
from orchestrator.infrastructure.harness.opencode.events import (
    events as stream_events,
)
from orchestrator.infrastructure.harness.opencode.events import (
    result_object,
    session_id_from,
    usage_from,
)
from orchestrator.infrastructure.harness.opencode.sessions import (
    session_for_directory,
    store_path,
)
from orchestrator.infrastructure.harness.probe import ProbeResult, run_probe_script
from orchestrator.infrastructure.settings import Settings

#: The executable `scripts/harness/opencode.sh install` puts on `PATH` at `OPENCODE_VERSION`.
EXECUTABLE = "opencode"
#: The non-interactive subcommand.
RUN = "run"

#: **Provisional** (addendum §B, 7.4 verifies): the three flags of the documented invocation.
#: `--format json` is what makes the run readable at all; `--dir` is the worktree, passed even
#: though the `ProcessRunner` already starts the process there, because OpenCode resolves its
#: own project root and should be told which directory that is; `-m` names provider and model
#: together.
FORMAT_FLAG = "--format"
FORMAT_JSON = "json"
DIR_FLAG = "--dir"
MODEL_FLAG = "-m"

#: The provider id `scripts/harness/opencode.sh configure` writes into `opencode.json`. A model
#: named without it would resolve against whichever provider OpenCode defaults to, which is not
#: the Gateway and therefore not a route this system can attribute spend or traces for (AD-11).
PROVIDER = "litellm"

#: The two harness-native names `scripts/harness/opencode.sh` declares in `HARNESS_ENV_ALIASES`,
#: and the contract names each is derived from. `LANGFUSE_BASEURL` is the Langfuse plugin's own
#: spelling of `LANGFUSE_BASE_URL`; `LANGFUSE_USER_ID` is what puts the Run on every generation
#: the plugin sends (AD-11). `tests/unit/test_local_env_contract.py` holds these against the
#: bash array itself, so a name added to the script and not here fails there.
LANGFUSE_BASE_URL_ALIAS = "LANGFUSE_BASEURL"
LANGFUSE_BASE_URL_SOURCE = "LANGFUSE_BASE_URL"
LANGFUSE_USER_ID_ALIAS = "LANGFUSE_USER_ID"
LANGFUSE_USER_ID_SOURCE = "ORCH_RUN_ID"

#: The suffix the prompt is written under, beside the attempt's own log — the port's convention.
PROMPT_SUFFIX = ".prompt"

#: Why `resume` refuses instead of dispatching. `capabilities.resume` is `False`, so
#: `application/steps/agent.py` never calls it; a fresh dispatch here would silently discard the
#: session the caller asked to continue, which is the kind of quiet substitution hard rule 7
#: exists to prevent.
RESUME_UNSUPPORTED = "the local harness declares no resume: retry dispatches a new session"


def local_aliases(contract: Mapping[str, str]) -> Mapping[str, str]:
    """The harness-native names a `local` process receives: the plugin's two, and no other.

    An `AliasBuilder` (`env.py`) exactly: the contract in, the harness's own names out. It needs
    no `Settings` — both values are contract values — which is what makes it a plain builder
    rather than a factory like `codex_aliases`, and what puts it in `registry.py`'s static
    `ALIASES` table rather than in the instance table `alias_table` builds.

    **AD-5 by construction.** The two values are a base URL and a Run id, so there is no value
    here a credential could travel in; the plugin reads `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
    straight off the contract, and the Gateway key reaches OpenCode through
    `"apiKey": "{env:LITELLM_API_KEY}"` in the config file — a *name*, never a value (AD-10).

    **No content switch.** `briefs/7-3-opencode-adapter.md` marks it `[verify; else record "no
    content switch"]`, and the record is: the Langfuse plugin documents none. `ORCH_LOG_CONTENT`
    still reaches the process as the contract name it is, and nothing is derived from it — unlike
    Claude Code's `OTEL_LOG_*` pair or Codex's `-c otel.log_user_prompt=true`.
    """
    return {
        LANGFUSE_BASE_URL_ALIAS: contract[LANGFUSE_BASE_URL_SOURCE],
        LANGFUSE_USER_ID_ALIAS: contract[LANGFUSE_USER_ID_SOURCE],
    }


class LocalHarness:
    """OpenCode, non-interactive, in the worktree, under the runner's own deadline."""

    name = "local"
    #: All three `False`, and each is a claim this adapter makes rather than an omission.
    #: `preassign_session`: OpenCode names its own session. `resume`: there is no resume form,
    #: so `retry` re-dispatches (5.5). `native_tracing`: no inbound `TRACEPARENT` is honoured —
    #: the plugin's own trace is found by user and session instead (AD-11).
    capabilities = HarnessCapabilities(preassign_session=False, resume=False, native_tracing=False)

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
        used by neither: OpenCode names its own session, and the Run's remaining budget is
        enforced by the Gateway's own key budget rather than by a CLI flag this harness has.
        The handle carries the worktree instead, because `wait` may have to ask the session
        store which session was opened in it.
        """
        argv = self._argv(cwd, model=model, message=prompt)
        self._record_prompt(log_path, prompt)
        handle = self.runner.start(
            argv, cwd=cwd, env=env, timeout_min=timeout_min, log_path=log_path
        )
        return HarnessHandle(
            session_id="", log_path=log_path, pid=handle.pid, pgid=handle.pgid, cwd=cwd
        )

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
        """Refuse: this harness declares `capabilities.resume = False` (see `RESUME_UNSUPPORTED`).

        Unreachable in this system — `application/steps/agent.py` asks the capability before it
        ever calls this — and stated as a refusal rather than as a fresh dispatch, because a
        caller that asked to continue a session and silently got a new one would record the
        wrong session id against the attempt and lose the turn's context without saying so.
        """
        raise NotImplementedError(RESUME_UNSUPPORTED)

    def resume_command(self, cwd: str, session_id: str) -> str | None:
        """`None`: there is no line an Operator could paste to take this session over (FR-21).

        The read model hides the whole terminal block for a harness whose `capabilities.resume`
        is `False` (`application/use_cases/terminal.py`), so this is never rendered; answering
        `None` rather than a plausible-looking command is what keeps that true if the read model
        ever asks without checking first.
        """
        return None

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Wait for the process `start` returned, then read its stream (AD-14, AD-10).

        The wait is guarded because the group is the only handle on the process and this frame
        is the only place that holds it: a `wait` that raises would leave a coding agent running
        in a worktree with nothing left that knows its `pgid`, which is the orphan AD-14 exists
        to prevent. The kill is the runner's own idempotent one, so it is safe on a process that
        already ended, and the exception still reaches the walker.

        The session is the stream's, then the store's, then nothing at all — and "nothing at
        all" is a reported fact rather than an exception: 7.4's `session id recorded` readiness
        line is what fails on it.
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
        return HarnessResult(
            session_id=session_id_from(stream) or self._stored_session(handle),
            exit_code=outcome.exit_code,
            log_path=handle.log_path,
            usage=usage_from(raw_result),
            timed_out=outcome.timed_out,
            pgid=handle.pgid,
            raw_result=raw_result,
        )

    def _stored_session(self, handle: HarnessHandle) -> str | None:
        """The session store's answer for the directory this dispatch ran in, or `None`.

        `handle.cwd` is `None` only for a handle some other adapter built, and a store lookup
        with no directory would have to accept any session on the host — so it answers `None`
        rather than widening.
        """
        if handle.cwd is None:
            return None
        return session_for_directory(store_path(self.settings.agent_home), handle.cwd)

    def _argv(self, cwd: Path, *, model: str | None, message: str) -> list[str]:
        """The whole command line. Pure but for the default model, which is a setting."""
        return [
            EXECUTABLE,
            RUN,
            FORMAT_FLAG,
            FORMAT_JSON,
            DIR_FLAG,
            str(cwd),
            MODEL_FLAG,
            f"{PROVIDER}/{model or self.settings.local_models[0]}",
            message,
        ]

    def probe(self) -> ProbeResult:
        return run_probe_script(self.settings.harness_scripts_dir / "opencode.sh")

    def _record_prompt(self, log_path: Path, message: str) -> None:
        """The prompt, beside the log, so an attempt's record holds what was asked."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(message, encoding=ENCODING)
