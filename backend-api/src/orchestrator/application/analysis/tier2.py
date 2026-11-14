"""Tier 2: the repository's own commands, run at base and at head (ARCHITECTURE §7.2, §7.7).

Runs only for a repository whose base declaration says `tier2: true`, inside detached
checkouts of its scratch clone, as the backend's own user, with the Project's environment
minus every orchestrator credential. A command is started once: a timeout or a failure is
recorded with its output and the signals it feeds read `not run`, never a retry.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from orchestrator.application.analysis.classify import classify
from orchestrator.application.analysis.inputs import RepositoryInputs, slug
from orchestrator.application.analysis.summary import not_run
from orchestrator.application.analysis.tier1a import Count, added_line_numbers
from orchestrator.application.analysis.tier2_cases import (
    EXECUTED,
    FAIL_TO_PASS,
    executed_counts,
    fail_to_pass,
    identity,
)
from orchestrator.application.analysis.tier2_reports import (
    Case,
    ReportUnreadable,
    coverage_of,
    new_diagnostics,
    parse_coverage,
    parse_diagnostics,
    parse_junit,
)
from orchestrator.application.metrics.values import na
from orchestrator.domain.entities.analysis import AnalysisArtifact
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.git_analysis import NameStatus
from orchestrator.domain.ports.process import Outcome, ProcessRunner
from orchestrator.domain.ports.workspace import Workspace, WorkspaceError

LINT = "code.linter_warnings_new"
TYPECHECK = "code.typecheck_errors_new"
COVERAGE = "code.coverage_changed_lines"
TIER2_IDS = (LINT, TYPECHECK, COVERAGE, EXECUTED, FAIL_TO_PASS)
NOT_DECLARED = na("tier 2 not declared")
NO_COVERAGE_PATH = na("no coverage report path declared")
NO_TEST_PATH = na("no test report path declared")
OUTPUT_TAIL_CHARS = 1_000_000
#: Application may not import the harness env module; these mirror its forbidden names.
FORBIDDEN_NAMES = ("GITHUB_TOKEN", "DATABASE_URL")
FORBIDDEN_PREFIXES = ("LITELLM_", "LANGFUSE_", "ORCHESTRATOR_", "OTEL_LOG_")
TEST_CLASSES = ("test_unit", "test_e2e", "test_unclassified")


def _na_command(kind: str) -> str:
    return na(f"no {kind} command declared")


def command_env(project_env: Mapping[str, str]) -> dict[str, str]:
    """The Project's variables without any credential of the orchestrator."""
    return {
        name: value
        for name, value in project_env.items()
        if name not in FORBIDDEN_NAMES and not name.startswith(FORBIDDEN_PREFIXES)
    }


@dataclass(frozen=True)
class Tier2Ports:
    runner: ProcessRunner
    timeout_min: float
    project_env: Mapping[str, str] = field(repr=False)


@dataclass(frozen=True)
class Tier2Result:
    counts: tuple[Count, ...] = ()
    words: Mapping[str, str] = field(default_factory=dict)
    artifacts: tuple[AnalysisArtifact, ...] = ()


class _CheckoutFailed(Exception):
    """A checkout could not be made."""


@dataclass
class _Side:
    """What one side's commands left: each kind's output, and why a kind did not finish."""

    name: str
    checkout: Path
    logs: dict[str, str] = field(default_factory=dict)
    failure: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class _Context:
    prepared: RepositoryInputs
    git: Git
    scratch: Path
    scratch_root: Workspace
    ports: Tier2Ports
    relative: str
    new_id: Callable[[], UUID]
    artifacts: list[AnalysisArtifact]


def _run_command(ctx: _Context, side: _Side, kind: str, command: str) -> Outcome:
    """Start once, wait, store the output; never a second start."""
    log = f"{side.name}-{kind}.log"
    handle = ctx.ports.runner.start(
        command,
        cwd=side.checkout,
        env=command_env(ctx.ports.project_env),
        timeout_min=ctx.ports.timeout_min,
        log_path=Path(f"{ctx.scratch}.tier2-logs/{log}"),
    )
    outcome = ctx.ports.runner.wait(handle)
    # Output and reports are the measured repository's bytes: undecodable ones are replaced,
    # never allowed to fail the whole analysis.
    text = ctx.scratch_root.read_lenient(f"{ctx.relative}.tier2-logs/{log}") or ""
    side.logs[kind] = text
    ctx.artifacts.append(
        AnalysisArtifact(
            id=ctx.new_id(),
            analysis_id=ctx.prepared.analysis.id,
            tool=f"tier2:{side.name}:{kind}",
            media_type="text/plain",
            body=text[-OUTPUT_TAIL_CHARS:].encode(),
        )
    )
    return outcome


def _execute(
    ctx: _Context, name: str, sha: str, kinds: Sequence[str], files: Mapping[str, str] | None = None
) -> _Side:
    """Check `sha` out beside the scratch clone, install, copy `files`, run each of `kinds`."""
    side = _Side(name, Path(f"{ctx.scratch}.tier2-{name}"))
    if not kinds:
        return side
    try:
        ctx.git.worktree_add(ctx.scratch, side.checkout, f"analysis-tier2-{name}", sha)
    except GitError as error:
        raise _CheckoutFailed from error
    commands = ctx.prepared.declaration.commands
    if "install" in commands:
        outcome = _run_command(ctx, side, "install", commands["install"])
        if outcome.timed_out or outcome.exit_code != 0:
            stop = "timeout" if outcome.timed_out else f"exit {outcome.exit_code}"
            side.failure = {kind: not_run(f"install {stop}") for kind in kinds}
            return side
    for path, text in (files or {}).items():
        try:
            ctx.scratch_root.write(f"{ctx.relative}.tier2-{name}/{path}", text)
        except WorkspaceError, OSError:
            # base holds a file where the added path needs a folder (or the reverse): the
            # file is not copied and its new cases read `absent from the report`
            continue
    for kind in kinds:
        if _run_command(ctx, side, kind, commands[kind]).timed_out:
            side.failure[kind] = not_run("timeout")
    return side


def _failure(kind: str, *sides: _Side) -> str | None:
    return next((s.failure[kind] for s in reversed(sides) if kind in s.failure), None)


def _renames(name_status: Sequence[NameStatus]) -> dict[str, str]:
    return {i.old_path: i.path for i in name_status if i.status == "R" and i.old_path is not None}


def _diagnostics(
    kind: str, metric: str, base: _Side, head: _Side, renames: Mapping[str, str]
) -> Tier2Result:
    if (word := _failure(kind, base, head)) is not None:
        return Tier2Result(words={metric: word})
    found = new_diagnostics(
        parse_diagnostics(base.logs[kind], str(base.checkout)),
        parse_diagnostics(head.logs[kind], str(head.checkout)),
        renames,
    )
    return Tier2Result((Count(metric, None, found, None),))


def _report(ctx: _Context, side: _Side, path: str) -> str | None:
    return ctx.scratch_root.read_lenient(f"{ctx.relative}.tier2-{side.name}/{path}")


def _coverage(ctx: _Context, head: _Side, added: Mapping[str, frozenset[int]]) -> Tier2Result:
    if (word := _failure("coverage", head)) is not None:
        return Tier2Result(words={COVERAGE: word})
    path = ctx.prepared.declaration.commands["coverage_report"]
    text = _report(ctx, head, path)
    if text is None:
        return Tier2Result(words={COVERAGE: not_run(f"no report at {path}")})
    try:
        report = parse_coverage(text)
    except ReportUnreadable:
        return Tier2Result(words={COVERAGE: not_run(f"report unreadable: {path}")})
    covered, instrumented, missing = coverage_of(report, added)
    return Tier2Result(
        (
            Count(COVERAGE, "covered", covered, None),
            Count(COVERAGE, "instrumented", instrumented, None),
            Count(COVERAGE, "not_in_report", missing, None),
        )
    )


def _cases(ctx: _Context, side: _Side) -> list[Case] | str:
    """The side's JUnit cases, or the word for a report that is missing or unreadable."""
    path = ctx.prepared.declaration.commands["test_report_path"]
    text = _report(ctx, side, path)
    if text is None:
        return not_run(f"no report at {path}")
    try:
        return parse_junit(text)
    except ReportUnreadable:
        return not_run(f"report unreadable: {path}")


def _fail_to_pass(ctx: _Context, f2p: _Side, new: Sequence[Case]) -> Tier2Result:
    if (word := _failure("test_report", f2p)) is not None:
        return Tier2Result(words={FAIL_TO_PASS: word})
    produced = _cases(ctx, f2p)
    if isinstance(produced, str):
        return Tier2Result(words={FAIL_TO_PASS: produced})
    counts, body = fail_to_pass(new, produced)
    artifact = AnalysisArtifact(
        id=ctx.new_id(),
        analysis_id=ctx.prepared.analysis.id,
        tool="fail_to_pass",
        media_type="application/json",
        body=body,
    )
    return Tier2Result(counts, artifacts=(artifact,))


def _added_test_files(
    ctx: _Context, name_status: Sequence[NameStatus], head: str
) -> dict[str, str]:
    declaration, hub = ctx.prepared.declaration, ctx.prepared.hub
    files: dict[str, str] = {}
    for item in name_status:
        if (
            item.status in ("A", "R", "C")
            and classify(item.path, declaration, hub=hub) in TEST_CLASSES
        ):
            try:
                text = ctx.git.read_file(ctx.scratch, head, item.path)
            except UnicodeDecodeError:
                continue
            if text is not None:
                files[item.path] = text
    return files


def _static_words(commands: Mapping[str, str]) -> dict[str, str]:
    """Signals that cannot run because the declaration lacks a command or a report path."""
    words = {
        metric: _na_command(kind)
        for metric, kind in ((LINT, "lint"), (TYPECHECK, "typecheck"))
        if kind not in commands
    }
    if "coverage" not in commands:
        words[COVERAGE] = _na_command("coverage")
    elif "coverage_report" not in commands:
        words[COVERAGE] = NO_COVERAGE_PATH
    if "test_report" not in commands:
        words[EXECUTED] = words[FAIL_TO_PASS] = _na_command("test_report")
    elif "test_report_path" not in commands:
        words[EXECUTED] = words[FAIL_TO_PASS] = NO_TEST_PATH
    return words


KINDS = (
    ("lint", LINT),
    ("typecheck", TYPECHECK),
    ("coverage", COVERAGE),
    ("test_report", EXECUTED),
)


def collect_tier2(
    prepared: RepositoryInputs,
    *,
    git: Git,
    scratch_root: Workspace,
    ports: Tier2Ports | None,
    new_id: Callable[[], UUID],
) -> Tier2Result:
    declaration = prepared.declaration
    if not declaration.tier2:
        return Tier2Result(words=dict.fromkeys(TIER2_IDS, NOT_DECLARED))
    analysis = prepared.analysis
    scratch, base_sha, head_sha = prepared.scratch, analysis.base, analysis.head
    if ports is None or scratch is None or base_sha is None or head_sha is None:
        return Tier2Result(words=dict.fromkeys(TIER2_IDS, not_run("no command runner")))
    words = _static_words(declaration.commands)
    ctx = _Context(
        prepared,
        git,
        scratch,
        scratch_root,
        ports,
        f"{analysis.id}/{slug(analysis.repository_path)}",
        new_id,
        [],
    )
    active = [(kind, metric) for kind, metric in KINDS if metric not in words]
    head_kinds = [kind for kind, _ in active]
    base_kinds = [kind for kind in head_kinds if kind != "coverage"]
    counts: list[Count] = []
    try:
        name_status = git.diff_name_status(scratch, base_sha, head_sha)
        renames = _renames(name_status)
        base = _execute(ctx, "base", base_sha, base_kinds)
        head = _execute(ctx, "head", head_sha, head_kinds)
        parts: list[Tier2Result] = []
        for kind, metric in (("lint", LINT), ("typecheck", TYPECHECK)):
            if metric not in words:
                parts.append(_diagnostics(kind, metric, base, head, renames))
        if COVERAGE not in words:
            added = added_line_numbers(git.diff_text(scratch, base_sha, head_sha, ()))
            production = {
                p: n
                for p, n in added.items()
                if classify(p, declaration, hub=prepared.hub) == "production"
            }
            parts.append(_coverage(ctx, head, production))
        if EXECUTED not in words:
            parts.extend(_tests(ctx, (base, head), renames, (name_status, base_sha, head_sha)))
    except _CheckoutFailed:
        failed = {metric: not_run("checkout failed") for _, metric in active}
        if EXECUTED not in words:
            failed[FAIL_TO_PASS] = not_run("checkout failed")
        parts = [Tier2Result(words=failed)]
    for part in parts:
        counts.extend(part.counts)
        words.update(part.words)
    return Tier2Result(
        tuple(counts), words, tuple(ctx.artifacts) + tuple(a for p in parts for a in p.artifacts)
    )


def _tests(
    ctx: _Context,
    sides: tuple[_Side, _Side],
    renames: Mapping[str, str],
    diff: tuple[Sequence[NameStatus], str, str],
) -> list[Tier2Result]:
    base, head = sides
    name_status, base_sha, head_sha = diff
    if (word := _failure("test_report", base, head)) is not None:
        return [Tier2Result(words={EXECUTED: word, FAIL_TO_PASS: word})]
    before, after = _cases(ctx, base), _cases(ctx, head)
    if isinstance(before, str) or isinstance(after, str):
        word = before if isinstance(before, str) else str(after)
        return [Tier2Result(words={EXECUTED: word, FAIL_TO_PASS: word})]
    f2p = _execute(
        ctx, "f2p", base_sha, ["test_report"], _added_test_files(ctx, name_status, head_sha)
    )
    known = {identity(c, renames) for c in before}
    new = [c for c in after if identity(c, {}) not in known]

    def of(file: str | None) -> str:
        return (
            "unclassified"
            if file is None
            else classify(file, ctx.prepared.declaration, hub=ctx.prepared.hub)
        )

    counts = executed_counts(before, after, renames, of)
    return [Tier2Result(counts), _fail_to_pass(ctx, f2p, new)]
