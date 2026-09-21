"""`FakeHarness`: the scripted coding agent that makes the dev loop testable (AR-14, AD-10).

The point of it is that everything *around* a harness — the archive, the re-dispatch, the
routing, the checkpoints, the commit guard — is what this system actually is, and none of it
can be proven end to end against a real model: a Run driven by `claude` costs money, takes
minutes, and reaches a different state each time. This adapter reads a YAML scenario out of
the target repository and does exactly what it says, so `make e2e` can walk a Run through
`blocked → answer → done` deterministically, on the compose stack, in seconds.

**It is registered only under `ORCH_TEST_MODE`** (`infrastructure/harness/registry.py`), and
its `harness` row is seeded enabled only there too. With test mode off the name resolves to
nothing, pre-flight's harness line fails for it, and `create_run` refuses — so `fake` is not
something an Operator can reach, and the shipped Templates never had to offer it.

**It is a real process, not a stub.** AD-14 wants every harness in its own process group,
with the `pgid` recorded before anything waits on it, so that a backend killed mid-attempt
knows what to reap. A fake that only wrote files and returned would hand the executor an
invented `pgid` and a group `kill_group` could not reach — an orphan-control hazard that
would show up as a flake in exactly the durability tests this harness exists to support. So
the scripted *file* effects happen in `start`, before any process exists, and then one real
`sh` script goes through the same `ProcessRunner` the Claude adapter uses: it sleeps for the
scenario's `sleep_seconds` (which is how a timeout scenario runs past `timeout_min`), makes
the scenario's commit, prints the result envelope, and exits with the scenario's code.

**The shape is the port's, not a shortcut through it** (AD-10, 5.4): `start` hands back a
`HarnessHandle`, `wait` blocks on it and reads the log, `run` is exactly `wait(start(...))`,
and `resume` is `wait` over the same private start — the same three-way split
`ClaudeHarness` has, for the same reason. `wait` reads `usage` back out of the log through
`claude/result.py`'s parser rather than out of a field kept in memory: the envelope this
harness prints is the same shape a real one prints, so the path under test is the real one.

**`delete:` is applied before anything is written** (6.8). `scenario.py`'s schema carries a
list of worktree-relative paths this dispatch removes, which is how a scenario makes the
target repository's own quality gate fail: the gate reads a file, and a `verify` failure is
that file being *gone*, not being different. Deletes run first so a scenario that deletes and
re-creates the same path ends with the write; a path that names a directory or is already
absent is skipped rather than reported, the same silence every other scenario key keeps.
`scenario._deletes` has already dropped anything that could reach outside the worktree.

**It reads no model and never leaves the worktree.** `model` and `budget_usd_remaining` are
accepted because the port declares them and ignored because a scenario decides everything;
`native_tracing` is `False`, so the attempt's span is the orchestrator's own (AD-11).
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path

from orchestrator.domain.ports.harness import (
    HarnessCapabilities,
    HarnessHandle,
    HarnessResult,
    ProbeResult,
)
from orchestrator.domain.ports.process import Handle, ProcessRunner
from orchestrator.infrastructure.harness.claude.result import (
    ENCODING,
    read_text,
    result_object,
    usage_from,
)
from orchestrator.infrastructure.harness.fake import scenario as scenarios
from orchestrator.infrastructure.settings import Settings

#: The registry key, the `attempt.harness` value, and the `harness` row's name.
NAME = "fake"

#: The identity the scenario's commit is made under. Named, and not the orchestrator's own,
#: so a commit this harness made is distinguishable from one the orchestrator made — which
#: is the same distinction `application/steps/agent.py`'s two commit messages draw.
COMMIT_NAME = "fake"
COMMIT_EMAIL = "fake@local"
#: What a scenario's `commit: true` writes. `story {id}: …` is the shipped convention.
COMMIT_MESSAGE = "story {story_id}: fake"

#: Where the Story file a scenario writes lands — the path the row's liveness glob asks for.
STORY_FILE = "{spec_folder}/stories/{story_id}-{slug}.md"

#: The suffixes written beside the attempt's log: the prompt (the port's own convention) and
#: the script this dispatch ran, kept so a failing e2e scenario can be read afterwards.
PROMPT_SUFFIX = ".prompt"
SCRIPT_SUFFIX = ".fake.sh"

#: The result envelope the script prints, in the shape `claude/result.py` already parses.
RESULT_TYPE = "result"
SUCCESS = "success"

#: The line the operator would paste. There is no interactive `fake` session to take over,
#: so it names the scenario directory instead of a command that does not exist (FR-21).
RESUME_COMMAND = "cd {cwd} && cat .fake-harness/*/attempt-*.yaml  # session {session_id}"


class FakeHarness:
    """The `Harness` port over a scenario file. Decides nothing; the scenario decides."""

    name = NAME
    capabilities = HarnessCapabilities(preassign_session=True, resume=True, native_tracing=False)

    #: The fake harness installs no skills, so it renders no workflow (AD-16 pins the real
    #: ones into the image; nothing puts them where this adapter runs).
    skills_dir = None

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
        """Apply the scenario's writes, then start its process and hand back the group."""
        return self._dispatch(
            cwd=cwd,
            prompt=prompt,
            env=env,
            session_id=session_id,
            timeout_min=timeout_min,
            log_path=log_path,
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
        """The next scenario for the same story, under the session already opened."""
        return self.wait(
            self._dispatch(
                cwd=cwd,
                prompt=message,
                env=env,
                session_id=session_id,
                timeout_min=timeout_min,
                log_path=log_path,
            )
        )

    def wait(self, handle: HarnessHandle) -> HarnessResult:
        """Wait for the scripted process, then read its log (AD-14, AD-10).

        Guarded exactly as `ClaudeHarness.wait` is: this frame holds the only reference to
        the group, so an exception escaping without a kill is the orphan AD-14 forbids.
        """
        try:
            outcome = self.runner.wait(Handle(pid=handle.pid, pgid=handle.pgid))
        except BaseException:
            self.runner.kill_group(handle.pgid)
            raise
        raw_result = result_object(read_text(handle.log_path))
        return HarnessResult(
            session_id=handle.session_id,
            exit_code=outcome.exit_code,
            log_path=handle.log_path,
            usage=usage_from(raw_result),
            timed_out=outcome.timed_out,
            pgid=handle.pgid,
            raw_result=raw_result,
            stalled=outcome.stalled,
            stall_cwd=handle.cwd if outcome.stalled else None,
        )

    def probe(self) -> ProbeResult:
        """Return a fixed ok ProbeResult — the fake harness is always ready (dev-mode only)."""
        return ProbeResult(
            ok=True, failing_reason=None, version="0.0.0-fake", models=["fake-model"]
        )

    def resume_command(self, cwd: str, session_id: str) -> str:
        """FR-21's paste line. There is no interactive session here, so it names the script."""
        return RESUME_COMMAND.format(cwd=cwd, session_id=session_id)

    def _dispatch(  # noqa: PLR0913 — one argument per fact the two entry points share
        self,
        *,
        cwd: Path,
        prompt: str,
        env: Mapping[str, str],
        session_id: str,
        timeout_min: float,
        log_path: Path,
    ) -> HarnessHandle:
        """Read the next scenario for this story, write what it writes, start what it runs."""
        dispatch = scenarios.dispatch_of(prompt)
        which = scenarios.next_attempt(self.settings.work_dir, cwd, dispatch.story_id)
        scenario = scenarios.load(scenarios.scenario_path(cwd, dispatch.story_id, which))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        Path(f"{log_path}{PROMPT_SUFFIX}").write_text(prompt, encoding=ENCODING)
        _apply(cwd, dispatch, scenario, prompt)
        script = Path(f"{log_path}{SCRIPT_SUFFIX}")
        script.write_text(_script(cwd, dispatch.story_id, scenario), encoding=ENCODING)
        handle = self.runner.start(
            ["sh", str(script)], cwd=cwd, env=env, timeout_min=timeout_min, log_path=log_path
        )
        return HarnessHandle(
            session_id=session_id, log_path=log_path, pid=handle.pid, pgid=handle.pgid
        )


def _apply(
    cwd: Path, dispatch: scenarios.Dispatch, scenario: scenarios.Scenario, prompt: str
) -> None:
    """The scenario's writes, into the worktree, before any process exists.

    Done here rather than in the script because the content is arbitrary text from a YAML
    document: shelling it out would make every scenario a quoting problem, and the point of
    this harness is that a test can write what it means.
    """
    for path in scenario.delete:
        _remove(cwd / path)
    for spec in scenario.files:
        _write(cwd / spec.path, spec.content)
    story = scenario.story_file
    if story is None:
        return
    target = cwd / STORY_FILE.format(
        spec_folder=dispatch.spec_folder, story_id=dispatch.story_id, slug=story.slug
    )
    body = story.content
    if scenario.echo_prompt:
        body = f"{body.rstrip(chr(10))}\n\n## Prompt\n\n{prompt}\n"
    _write(target, body)


def _write(target: Path, content: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding=ENCODING)


def _remove(target: Path) -> None:
    """One `delete:` entry, if it names a file that is there (6.8).

    Files only, and never a directory: a scenario removing a tree would be removing the
    `.fake-harness/` directory it is itself read from one typo later, and no scenario this
    harness exists for needs it. `missing_ok` covers the second dispatch of a scenario that
    already deleted the path, which is the ordinary case for a `default.yaml`.
    """
    if target.is_dir():
        return
    target.unlink(missing_ok=True)


def _script(cwd: Path, story_id: str, scenario: scenarios.Scenario) -> str:
    """The one process this dispatch runs, as a shell script beside the log.

    A file rather than `sh -c`: every value in it is quoted with `shlex.quote`, and a script
    on disk is readable afterwards, which is what makes a failed e2e scenario diagnosable.
    No `set -e` — the commit is allowed to find nothing to commit, and the exit code the
    scenario declared is the one the process must leave with either way.
    """
    lines = ["#!/bin/sh", "# written by the fake harness (AR-14)", "set -u"]
    if scenario.sleep_seconds > 0:
        lines.append(f"sleep {shlex.quote(str(scenario.sleep_seconds))}")
    if scenario.commit:
        repository = shlex.quote(str(cwd))
        message = shlex.quote(COMMIT_MESSAGE.format(story_id=story_id))
        lines += [
            f"git -C {repository} add -A || true",
            f"git -C {repository} -c user.name={shlex.quote(COMMIT_NAME)} "
            f"-c user.email={shlex.quote(COMMIT_EMAIL)} commit -q -m {message} || true",
        ]
    envelope = _envelope(scenario)
    if envelope is not None:
        lines.append(f"printf '%s\\n' {shlex.quote(envelope)}")
    lines.append(f"exit {scenario.exit_code}")
    return "\n".join([*lines, ""])


def _envelope(scenario: scenarios.Scenario) -> str | None:
    """The result object the script prints, or `None` for a scenario reporting no usage.

    `None` is an ordinary outcome, not a gap: AD-11 treats a harness that printed no figures
    as unmeasured, and a fake that always printed zeroes would have them read as measured.
    """
    usage = scenario.usage
    if usage is None:
        return None
    return json.dumps(
        {
            "type": RESULT_TYPE,
            "subtype": SUCCESS,
            "total_cost_usd": str(usage.cost_usd),
            "usage": {"input_tokens": usage.tokens_in, "output_tokens": usage.tokens_out},
        }
    )
