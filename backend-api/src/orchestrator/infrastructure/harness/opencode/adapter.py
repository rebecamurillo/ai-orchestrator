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

**Resume** (AD-10 amended story 3, 2026-09-25): `opencode run --session {id}` continues a
session at `OPENCODE_VERSION=1.18.26`. `capabilities.resume = True`. `resume()` builds the
invocation via `_resume_argv` (no `-m` flag — the continued session retains its original model
configuration). `resume_command` returns the operator's paste-able line
(`cd {worktree} && opencode run --session {id}`) rather than `None`, so the Run detail shows
the terminal block (FR-21, 6.7). A `session_not_found` exit-1 is a reported failure; the
`session_id` in the result stays the tried id, never replaced by a fresh one (hard rule 7).

**Tracing is by identity, never by parent** (AD-11, `capabilities.native_tracing = False`).
OpenCode honours no inbound `TRACEPARENT` — it still receives one, because the contract is exact
— and the Langfuse plugin opens its own trace per turn keyed by the OpenCode session, carrying
`userId` from `LANGFUSE_USER_ID`. `local_aliases` below is the whole of how the Run gets onto
that trace, and `infrastructure/tracing/user_level.py` is the rule that reads it back.

**A dispatch is two halves** (AD-14, 5.4), exactly as `ClaudeHarness` and `CodexHarness`.
"""

from __future__ import annotations

import json
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
SESSION_FLAG = "--session"

#: The provider id `scripts/harness/opencode.sh configure` writes into `opencode.json`. A model
#: named without it would resolve against whichever provider OpenCode defaults to, which is not
#: the Gateway and therefore not a route this system can attribute spend or traces for (AD-11).
PROVIDER = "litellm"

#: The three harness-native names `scripts/harness/opencode.sh` declares in `HARNESS_ENV_ALIASES`,
#: and the contract names each is derived from. `LANGFUSE_BASEURL` is the Langfuse plugin's own
#: spelling of `LANGFUSE_BASE_URL`; `LANGFUSE_USER_ID` is what puts the Run on every generation
#: the plugin sends (AD-11); `OPENCODE_LANGFUSE_TAGS` is `ORCH_LANGFUSE_TAGS` rendered for the
#: one place OpenCode reads it — see `local_aliases`. `tests/unit/test_local_env_contract.py`
#: holds these against the bash array itself, so a name added to the script and not here fails
#: there.
LANGFUSE_BASE_URL_ALIAS = "LANGFUSE_BASEURL"
LANGFUSE_BASE_URL_SOURCE = "LANGFUSE_BASE_URL"
LANGFUSE_USER_ID_ALIAS = "LANGFUSE_USER_ID"
LANGFUSE_USER_ID_SOURCE = "ORCH_RUN_ID"
LANGFUSE_TAGS_ALIAS = "OPENCODE_LANGFUSE_TAGS"
LANGFUSE_TAGS_SOURCE = "ORCH_LANGFUSE_TAGS"


def config_string_escape(value: str) -> str:
    """`value` as it must be written *inside* a JSON string literal in `opencode.json`.

    `json.dumps` renders the value as a complete JSON string; the slice drops its surrounding
    quotes, because the quotes are already in the config file around the `{env:...}` reference
    this value replaces. Escaping, not quoting, is the point: `"` becomes `\\"` so the string
    the reference sits in survives the substitution.
    """
    return json.dumps(value)[1:-1]


#: The suffix the prompt is written under, beside the attempt's own log — the port's convention.
PROMPT_SUFFIX = ".prompt"


def local_aliases(contract: Mapping[str, str]) -> Mapping[str, str]:
    """The harness-native names a `local` process receives: the plugin's two, the config's one.

    An `AliasBuilder` (`env.py`) exactly: the contract in, the harness's own names out. It needs
    no `Settings` — every value is a contract value — which is what makes it a plain builder
    rather than a factory like `codex_aliases`, and what puts it in `registry.py`'s static
    `ALIASES` table rather than in the instance table `alias_table` builds.

    **The third name is a *rendering* of a contract value, not a copy of one** (fix of
    2026-09-20). OpenCode expands the `{env:NAME}` references in `opencode.json` **textually,
    before it parses the file as JSON(C)**, so a value lands in the config as characters rather
    than as a value. `ORCH_LANGFUSE_TAGS` is a JSON array — `["run:…","attempt:…",…]` — and its
    quotes therefore terminate the JSON string the reference sits in:

        "langfuse_tags": "{env:ORCH_LANGFUSE_TAGS}"
          →  "langfuse_tags": "["run:…", "attempt:…"]"      ← not parseable

    OpenCode answers that with `Error: Config file … is not valid JSON(C)` and exits 1 before it
    reads a prompt, which made *every* `local` dispatch fail on a gateway-enabled install. So the
    script references `OPENCODE_LANGFUSE_TAGS` instead and this builder escapes the value for the
    string position it is substituted into. The two Langfuse plugin names copy their source
    verbatim, because the plugin reads them as environment variables in the ordinary way.

    The other two harnesses need no such rendering and must not have one: Claude builds
    `ANTHROPIC_CUSTOM_HEADERS` as `name: value` lines, and Codex writes the env *name* into its
    TOML (`env_http_headers`) and resolves it per request. Neither ever parses the tag value as
    part of a document, which is why this is an alias and not a change to the contract itself.

    **AD-5 by construction.** The three values are a base URL, a Run id and a tag list, so there
    is no value here a credential could travel in; the plugin reads
    `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` straight off the contract, and the Gateway key
    reaches OpenCode through `"apiKey": "{env:LITELLM_API_KEY}"` in the config file — a *name*,
    never a value (AD-10).

    **No content switch.** `briefs/7-3-opencode-adapter.md` marks it `[verify; else record "no
    content switch"]`, and the record is: the Langfuse plugin documents none. `ORCH_LOG_CONTENT`
    still reaches the process as the contract name it is, and nothing is derived from it — unlike
    Claude Code's `OTEL_LOG_*` pair or Codex's `-c otel.log_user_prompt=true`.
    """
    return {
        LANGFUSE_BASE_URL_ALIAS: contract[LANGFUSE_BASE_URL_SOURCE],
        LANGFUSE_USER_ID_ALIAS: contract[LANGFUSE_USER_ID_SOURCE],
        LANGFUSE_TAGS_ALIAS: config_string_escape(contract[LANGFUSE_TAGS_SOURCE]),
    }


class LocalHarness:
    """OpenCode, non-interactive, in the worktree, under the runner's own deadline."""

    name = "local"
    #: `preassign_session`: OpenCode names its own session. `resume` (story 3, 2026-09-25):
    #: `opencode run --session {id}` continues a session — `True`. `native_tracing`: no inbound
    #: `TRACEPARENT` is honoured — the plugin's own trace is found by user and session (AD-11).
    capabilities = HarnessCapabilities(preassign_session=False, resume=True, native_tracing=False)

    def __init__(self, runner: ProcessRunner, settings: Settings) -> None:
        self.runner = runner
        self.settings = settings
        #: `scripts/harness/opencode.sh` installs the stubs into OpenCode's own config dir,
        #: so this harness stands alone even though it also reads the other two.
        self.skills_dir = settings.agent_home / ".config" / "opencode" / "skills"

    def run(  # noqa: PLR0913 — the port's own signature (AD-10)
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        model: str | None,
        session_id: str,
        budget_usd_remaining: Decimal | None,
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
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
                stall_min=stall_min,
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
        budget_usd_remaining: Decimal | None,
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
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
            argv,
            cwd=cwd,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path,
            stall_min=stall_min,
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
        timeout_min: float | None,
        log_path: Path,
        stall_min: float | None = None,
    ) -> HarnessResult:
        """Continue `session_id` with `message` via `opencode run --session {session_id}` (AD-10).

        Exactly `wait(start_handle)` shaped as a single call: `_resume_argv` builds the argv
        (no `-m` — the session retains its own model), `_record_prompt` writes the message
        beside the log, and the handle carries the known `session_id` so `wait` falls back to
        it when the stream reports none (story 3, 2026-09-25).
        """
        argv = self._resume_argv(cwd, session_id=session_id, message=message)
        self._record_prompt(log_path, message)
        handle = self.runner.start(
            argv,
            cwd=cwd,
            env=env,
            timeout_min=timeout_min,
            log_path=log_path,
            stall_min=stall_min,
        )
        return self.wait(
            HarnessHandle(
                session_id=session_id, log_path=log_path, pid=handle.pid, pgid=handle.pgid, cwd=cwd
            )
        )

    def resume_command(self, cwd: str, session_id: str) -> str | None:
        """The line an Operator can paste to take this session over by hand (FR-21, AD-10).

        `cd {cwd} && opencode run --session {session_id}` — the minimal form; no `--format` or
        `--dir` flags because the operator runs this in their own terminal, not as a
        machine-readable dispatch.
        """
        return f"cd {cwd} && {EXECUTABLE} {RUN} {SESSION_FLAG} {session_id}"

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Wait for the process `start` returned, then read its stream (AD-14, AD-10).

        The wait is guarded because the group is the only handle on the process and this frame
        is the only place that holds it: a `wait` that raises would leave a coding agent running
        in a worktree with nothing left that knows its `pgid`, which is the orphan AD-14 exists
        to prevent. The kill is the runner's own idempotent one, so it is safe on a process that
        already ended, and the exception still reaches the walker.

        The session is the stream's first; then `handle.session_id` when non-empty (resume path,
        where the attempted id is always known); then the store (start path, where `handle.
        session_id` is `""`); then `None` — reported fact, not an exception (story 3, 2026-09-25).
        7.4's `session id recorded` readiness line is what fails on it.
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
        stored = self._stored_session(handle)
        return HarnessResult(
            session_id=captured if captured is not None else (handle.session_id or stored),
            exit_code=outcome.exit_code,
            log_path=handle.log_path,
            usage=usage_from(raw_result),
            timed_out=outcome.timed_out,
            pgid=handle.pgid,
            raw_result=raw_result,
            stalled=outcome.stalled,
            stall_cwd=handle.cwd if outcome.stalled else None,
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

    def _resume_argv(self, cwd: Path, *, session_id: str, message: str) -> list[str]:
        """The resume command line (AD-10, story 3, 2026-09-25).

        No `-m` flag: the continued session retains its original model configuration; forcing a
        model on resume could conflict with what the session already has. `--dir` is kept for
        correctness — it tells OpenCode which directory this is running in, the same rationale
        as in `_argv`.
        """
        return [
            EXECUTABLE,
            RUN,
            FORMAT_FLAG,
            FORMAT_JSON,
            DIR_FLAG,
            str(cwd),
            SESSION_FLAG,
            session_id,
            message,
        ]

    def probe(self) -> ProbeResult:
        return run_probe_script(self.settings.harness_scripts_dir / "opencode.sh")

    def _record_prompt(self, log_path: Path, message: str) -> None:
        """The prompt, beside the log, so an attempt's record holds what was asked."""
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(message, encoding=ENCODING)
