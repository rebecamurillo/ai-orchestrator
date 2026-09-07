"""The durability proof: kill the backend mid-Run, restart it, count what is left
(SPEC CAP-17, FR-12, SM-4, NFR-1).

Every durability rule this system has is asserted over a fake engine in the unit suite —
`start_attempt` closing an interrupted Attempt, the walker re-executing one step whole, the
`recv` a parked Run waits in. What only a real `SIGKILL` settles is that the durable engine
actually recovers: that a workflow whose process died mid-step is picked up again by the
next process, that it resumes at the row it was on rather than at the start of the plan, and
that the child process the dead one had started is not still there beside its replacement.

**Two scenarios, and they fail differently.** The first kills the backend while a row holds a
real child process (`git.worktree` running the Repository's `install_command`); its subject is
the *execution* half of FR-12 — Attempt 1 closed `error`, Attempt 2 opened, rows finished
earlier replayed rather than re-run, and exactly one process group for the Run afterwards. The
second kills it while the Run waits in its single `recv` on a `checkpoint` row; its subject is
the *waiting* half — after the restart the walk waits again, and the Operator's `continue`
still reaches it.

**What the process count can and cannot show, said plainly.** `docker compose kill` SIGKILLs
the container's PID 1, and the kernel then tears down that whole PID namespace: the child the
dead process started is *gone*, not orphaned, and it is the topology that guarantees that, not
any code of this system's. So the count after the restart proves that the process that replaced
it started exactly one group and no second one appeared beside it — a double-start net — and it
does **not** prove that an orphan of the previous process was reaped. The brief allows both
readings ("orphaned or gone as the container restarts"); this is the one a container kill can
actually settle. Proving the reaping half needs a kill that leaves the process table standing,
which is `ProcessRunner.kill_group`'s own unit coverage and, in Epic 5, the `agent` kind's
recorded `pgid`.

**Why this module carries a marker.** It needs a backend it may kill and bring back, which
means a compose container. `make e2e-api` attaches to whatever stack is configured — in CI that
is a backend-api process started from source on the runner, with no container to kill — so the
`durability` marker is deselected there and `make durability` selects it against a stack of its
own. Nothing here skips: a run that cannot find the container fails, naming what is missing.

**What identifies "the Run's process".** The image installs no `procps`, so there is no `ps`;
the reader below walks `/proc` instead. And neither `/bin/sh -c "<install_command>"` nor its
`sleep` child carries the worktree path in its command line, so the Repository is created with
an `install_command` holding a token unique to the scenario — `: <marker>; sleep <n>`, two
commands so no shell can `exec`-optimise the marker away. `RealProcessRunner` starts a string
command with `shell=True, start_new_session=True`, so that `/bin/sh` is the process-group
leader and the token is in its `/proc/<pid>/cmdline`. Counting *distinct process groups* that
carry the token is FR-12's "exactly one Harness process for that Run", read where it lives.

**`attempt.pgid` is deliberately not part of any assertion here.** AD-8 gives that write to the
`agent` executor and the spine's own field list keeps `pgid` "for `agent` rows"; Epic 4 ships no
`agent` step, so no Attempt this epic can produce carries one. The process table is the honest
place to read the same fact.

Both Runs end terminal inside their own scenario, so this module leaves no slot and no
Repository partition held (AD-12) and adds nothing for `test_signals.py`'s sweep to release.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    create_engine_from,
    create_session_factory,
)
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import REPO_ROOT, Fixtures, manifest_stating
from tests.e2e.test_run_creation import (
    BRANCH,
    PROJECTS,
    RUNS,
    TEMPLATES,
    clone_check,
    create_project,
    run_payload,
)

pytestmark = pytest.mark.durability

HTTP_OK = 200
HTTP_CREATED = 201
TIMEOUT_SECONDS = 10.0

#: The service this module kills, and the process manager that owns it.
SERVICE = "backend-api"
COMPOSE = ("docker", "compose")

#: How long the Repository's install command holds the `checkout` row. Long enough to be
#: caught running twice over — once before the kill, once after it — and short enough that
#: both scenarios together stay inside the brief's own five-minute budget. The row's timeout
#: is `git.worktree`'s own default of five minutes, so this never reaches it.
INSTALL_SECONDS = 60

#: Deadlines. The queue polls on its own interval and the engine recovers on its own, so
#: these are how long the gate waits before calling a stall a stall — not expectations.
WALK_TIMEOUT_SECONDS = 120.0
RESTART_TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 0.5

#: How long any one call to the docker daemon may take. Every wait below bounds its polling;
#: without this, one hung `docker` would hang the gate with no deadline at all.
DOCKER_TIMEOUT_SECONDS = 60.0

#: How the "exactly one process group" claim is made: repeatedly, not once.
SAMPLES = 5
SAMPLE_INTERVAL_SECONDS = 1.5

#: Statuses read off the Run.
QUEUED = "queued"
RUNNING = "running"
NEEDS_YOU = "needs_you"
DONE = "done"

#: The rows AD-7 and the two Templates below plan, in order.
PLAN = "plan"
CHECKOUT = "checkout"
PAUSE = "pause"
AFTER = "after"

#: What `start_attempt` leaves on the Attempt a restart interrupted.
ERROR = "error"

#: Gate-record events (AD-8). Their own constants: the Run status tokens above are a different
#: vocabulary that happens to share two spellings, and an assertion reading the wrong one would
#: still pass today and mean nothing tomorrow.
RUN_STARTED = "start"
RUN_FINISHED = "done"

#: Scenario 1: one row that holds a real child process, then one that does not. `git.worktree`
#: runs the Repository's `install_command` inside itself (AD-14), which is what makes the
#: `checkout` row long-lived without an executor written for this test.
INSTALL_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: e2e durability install\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: checkout\n"
    "    uses: git.worktree\n"
    "    with: {{ base: '{{{{base_branch}}}}', branch: '{branch}' }}\n"
    "    gate: deterministic\n"
    "  - id: after\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)

#: Scenario 2: a real `checkpoint` stop, so the kill lands inside the walk's single `recv`,
#: and one row after it so "the walk carried on" is something the rows can show.
CHECKPOINT_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: e2e durability checkpoint\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: pause\n"
    "    uses: checkpoint\n"
    "    gate: human\n"
    "  - id: after\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)

#: Every process group inside the container whose command line carries `$1`, one
#: `<pgid> <cmdline>` line each. `/proc` rather than `ps`, because the image installs no
#: `procps`; the third field after the `)` in `/proc/<pid>/stat` is the process group.
#:
#: The reader excludes its own group. `docker compose exec` gives the exec'd process a group
#: of its own, and that process's command line *is* this script plus the marker — as are the
#: command lines of the short-lived subshells its own `$(...)` substitutions fork before they
#: exec. Excluding the group excludes all of them at once, deterministically.
PROCESS_GROUPS = r"""
marker="$1"
self=$(sed 's/^.*) //' /proc/self/stat | cut -d' ' -f3)
for d in /proc/[0-9]*; do
    [ -r "$d/cmdline" ] || continue
    cmd=$(tr '\0' ' ' < "$d/cmdline" 2>/dev/null)
    case "$cmd" in
        *"$marker"*) ;;
        *) continue ;;
    esac
    pg=$(sed 's/^.*) //' "$d/stat" 2>/dev/null | cut -d' ' -f3)
    if [ -z "$pg" ]; then continue; fi
    if [ "$pg" = "$self" ]; then continue; fi
    echo "$pg $cmd"
done
exit 0
"""


# ── the compose stack, driven from the host side ────────────────────────────────────────


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """One command against the docker daemon, with a deadline of its own (hard rule 7).

    A `docker` that hangs would otherwise hang the gate with no deadline at all: every wait
    below bounds how long it *polls*, none of them bounds one call.
    """
    try:
        return subprocess.run(  # fixed argv, no shell
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=DOCKER_TIMEOUT_SECONDS,
        )
    except OSError as error:
        pytest.fail(f"`{' '.join(command)}` could not be run: {error}")
    except subprocess.TimeoutExpired:
        pytest.fail(f"`{' '.join(command)}` did not return within {DOCKER_TIMEOUT_SECONDS:.0f}s")


def compose(*arguments: str, check: bool = True) -> str:
    """One `docker compose` call against the stack this gate is pointed at.

    The project, the compose files and the environment file all come from the environment
    `make e2e` exports, exactly as `test_repo_init.py::read_back` and
    `test_signals.py::run_check` already rely on. `check=False` hands the output back rather
    than dropping it, so a caller that tolerates a non-zero exit can still report it.
    """
    completed = run([*COMPOSE, *arguments])
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        pytest.fail(f"`docker compose {' '.join(arguments)}` failed: {detail}")
    return completed.stdout if completed.returncode == 0 else _both(completed)


def _both(completed: subprocess.CompletedProcess[str]) -> str:
    """What a command said, wherever it said it — a failure is reported with its output."""
    return f"{completed.stdout}{completed.stderr}".strip()


def container_id() -> str:
    """The backend's container, or a failure naming why this module cannot run at all."""
    named = [line for line in compose("ps", "--quiet", SERVICE).splitlines() if line.strip()]
    if not named:
        pytest.fail(
            f"no `{SERVICE}` container in this compose project: the durability marker kills "
            "and restarts a container, so it needs a compose stack (`make durability`)"
        )
    if len(named) > 1:
        pytest.fail(
            f"this compose project holds {len(named)} `{SERVICE}` containers; the kill and the "
            "restart are both about one, and the proof would be reading a different container "
            "than it killed"
        )
    return named[0].strip()


def generation() -> tuple[str, str]:
    """Which container is serving, and when it started — the pair a restart changes.

    Both halves are read because either one alone can stay the same: `docker compose up -d`
    may reuse the container it finds (same id, new start time) or replace it (new id).
    """
    identifier = container_id()
    started = run(["docker", "inspect", "--format", "{{.State.StartedAt}}", identifier])
    if started.returncode != 0:
        pytest.fail(f"docker inspect {identifier} failed: {_both(started)}")
    return identifier, started.stdout.strip()


def kill_backend() -> None:
    """SIGKILL: no shutdown hook runs, nothing is flushed, the child dies with the container."""
    compose("kill", SERVICE)


def restart_backend() -> str:
    """Bring it back, and hand back what compose said.

    `check=False`, because `restart: unless-stopped` may already have started the container
    and a race with the daemon's own restart is not this test's failure. What *is* a failure
    is the backend never answering afterwards — and when that happens the caller reports this
    output with it, rather than leaving a real `docker compose up` error to surface as an
    unexplained timeout two minutes later (hard rule 7).
    """
    return compose("up", "--detach", SERVICE, check=False).strip()


def wait_healthy(client: httpx.Client, restart_output: str = "") -> None:
    """Wait for the new process to answer, the way `conftest.py::stack` waits for the first."""
    deadline = time.monotonic() + RESTART_TIMEOUT_SECONDS
    last = "no attempt completed"
    while time.monotonic() < deadline:
        try:
            response = client.get("/healthz")
        except httpx.HTTPError as error:
            last = f"{type(error).__name__}: {error}"
        else:
            if response.status_code == HTTP_OK:
                return
            last = f"/healthz answered {response.status_code}"
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(
        f"{SERVICE} did not answer /healthz within {RESTART_TIMEOUT_SECONDS:.0f}s of the "
        f"restart — last attempt: {last}; `docker compose up` said: {restart_output or 'nothing'}"
    )


def process_groups(marker: str) -> list[str]:
    """The distinct process groups inside the container carrying `marker`, sorted."""
    output = compose("exec", "-T", SERVICE, "sh", "-c", PROCESS_GROUPS, "sh", marker)
    return sorted({line.split(" ", 1)[0] for line in output.splitlines() if line.strip()})


def wait_for_process(marker: str) -> list[str]:
    """Wait until the row's own process is there, or fail naming what was never seen."""
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    groups: list[str] = []
    while time.monotonic() < deadline:
        groups = process_groups(marker)
        if groups:
            return groups
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(
        f"no process carrying {marker} appeared in the {SERVICE} container within "
        f"{WALK_TIMEOUT_SECONDS:.0f}s: the row is not running its install command"
    )


# ── the stack's own fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture(scope="module")
def sessions(settings: Settings) -> Iterator[Any]:
    engine = create_engine_from(settings)
    try:
        yield create_session_factory(engine)
    finally:
        engine.dispose()


# ── reading the Run back ────────────────────────────────────────────────────────────────


def status_of(client: httpx.Client, run_id: str) -> str:
    response = client.get(f"{RUNS}/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def wait_for(client: httpx.Client, run_id: str, targets: set[str]) -> str:
    """Poll until the Run is in one of `targets`, or fail naming where it stopped instead."""
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    status = status_of(client, run_id)
    while status not in targets and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = status_of(client, run_id)
    if status not in targets:
        pytest.fail(
            f"run {run_id} did not reach {sorted(targets)} within "
            f"{WALK_TIMEOUT_SECONDS:.0f}s (last seen: {status})"
        )
    return status


def rows_of(sessions: Any, run_id: str) -> list[Any]:
    with sessions() as session:
        return SQLAlchemyStepRunRepository(session).list_for_run(UUID(run_id))


def attempts_of(sessions: Any, run_id: str, path: str) -> list[Any]:
    """Every Attempt on one row, oldest first — the table FR-12's claims are read from."""
    with sessions() as session:
        rows = SQLAlchemyStepRunRepository(session).list_for_run(UUID(run_id))
        row = next((entry for entry in rows if entry.path == path), None)
        if row is None:
            return []
        return SQLAlchemyAttemptRepository(session).list_for_row(row.id)


#: The columns the story's own acceptance criterion names, in order.
HEADINGS = ("row", "status", "n", "attempt", "started_at", "ended_at")


def attempt_table(sessions: Any, run_id: str) -> str:
    """Every row of the Run with every Attempt on it — printed by each scenario (SPEC CAP-17).

    `ended_at` earns its column: it is the field that shows the Attempt the restart
    interrupted being closed, which is the whole of what the first scenario is about.
    """
    lines = [f"run {run_id}", _line(HEADINGS)]
    with sessions() as session:
        rows = SQLAlchemyStepRunRepository(session).list_for_run(UUID(run_id))
        repository = SQLAlchemyAttemptRepository(session)
        for row in rows:
            attempts = repository.list_for_row(row.id)
            if not attempts:
                lines.append(_line((row.path, row.status, "-", "-", "-", "-")))
            lines.extend(
                _line(
                    (row.path, row.status, str(a.n), a.status, _at(a.started_at), _at(a.ended_at))
                )
                for a in attempts
            )
    return "\n".join(lines)


def _line(cells: tuple[str, ...]) -> str:
    """One row of the table, columns wide enough for an ISO 8601 instant."""
    return "".join(f"{cell:<{WIDTHS[index]}}" for index, cell in enumerate(cells))


#: One width per column of `HEADINGS`; the two timestamps carry a full ISO 8601 instant.
WIDTHS = (12, 12, 4, 12, 34, 34)


def _at(moment: Any) -> str:
    """A nullable timestamp, as text. Both halves of an Attempt's clock may be unset."""
    return moment.isoformat() if moment is not None else "-"


def report(request: pytest.FixtureRequest, sessions: Any, run_id: str) -> None:
    """Put the attempt table on the terminal whether the scenario passed or failed.

    Read here rather than passed in, because the caller is a `finally`: a scenario that
    failed halfway is exactly the one whose table is worth reading, and a table that only
    printed on success would be missing every time it mattered. Its own failure is swallowed
    for the same reason — a reporting error must not replace the failure being reported.
    """
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        return
    try:
        table = attempt_table(sessions, run_id)
    except Exception as error:  # a diagnostic must never mask the diagnosis
        table = f"run {run_id}: could not read the attempt table: {error}"
    reporter.write_line("")
    reporter.write_line(table)


def wait_for_row(sessions: Any, run_id: str, path: str, status: str) -> None:
    """Wait until one row reaches a status, or fail naming what every row was instead."""
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    seen: list[tuple[str, str]] = []
    while time.monotonic() < deadline:
        seen = [(row.path, row.status) for row in rows_of(sessions, run_id)]
        if (path, status) in seen:
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(
        f"row {path} of run {run_id} was never {status} within "
        f"{WALK_TIMEOUT_SECONDS:.0f}s — rows: {seen}"
    )


def wait_for_attempt(sessions: Any, run_id: str, path: str, n: int) -> list[Any]:
    """Wait until the row has at least `n` Attempts — how a resumption is seen, not assumed."""
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    attempts: list[Any] = []
    while time.monotonic() < deadline:
        attempts = attempts_of(sessions, run_id, path)
        if len(attempts) >= n:
            return attempts
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(
        f"row {path} of run {run_id} never opened attempt {n} within "
        f"{WALK_TIMEOUT_SECONDS:.0f}s — it has {len(attempts)}: the walk did not resume"
    )


# ── creating the Run each scenario kills ────────────────────────────────────────────────


def register_repository(client: httpx.Client, project_id: str, url: str, install: str) -> str:
    """A Repository with an `install_command` of this module's own — `create_repository`
    (`test_run_creation.py`) takes none, and the command is the whole point here."""
    response = client.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={"url": url, "default_branch": BRANCH, "install_command": install},
    )
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"])


def new_repository(
    api: httpx.Client, fixtures: Fixtures, settings: Settings, install: str = ""
) -> tuple[str, str]:
    """A fresh Project and a fresh bare `file://` origin, one pair per scenario, so the two
    Runs this module creates never contend for the same Repository partition (AD-12)."""
    project_id = create_project(api)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository_id = register_repository(api, project_id, url, install)
    clone_check(api, repository_id)
    return project_id, repository_id


def start_run(api: httpx.Client, template: str, repository_id: str, project_id: str) -> str:
    """Save a Template of this scenario's own, then create and enqueue the Run on it."""
    name = f"e2e-durability-{uuid4().hex}"
    yaml = template.format(name=name, branch=f"e2e-durability-{uuid4().hex[:8]}")
    saved = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": yaml})
    assert saved.status_code == HTTP_CREATED, saved.text
    created = api.post(RUNS, json=run_payload(name, repository_id, project_id=project_id))
    assert created.status_code == HTTP_CREATED, created.text
    return str(created.json()["run"]["id"])


# ── scenario 1: killed while a row holds a process ──────────────────────────────────


#: The statuses a scenario's own Run may end in. `needs_you` is *accepted* rather than waited
#: past, so a Run that parks is reported by the test that names it instead of eating the whole
#: deadline — and `release` below is what stops that acceptance leaking a held slot.
ENDINGS = frozenset({DONE, "failed", "cancelled", NEEDS_YOU})


def release(api: httpx.Client, run_id: str) -> None:
    """Cancel a Run this module left non-terminal, so the stack it hands back is free.

    A Run in `needs_you` (or still `queued` behind it) holds its slot and its Repository
    partition for the rest of the stack's life (AD-12), which is exactly the property
    `tests/e2e/test_signals.py`'s own sweep exists to protect. Every scenario here ends its
    Run on the happy path; this is what keeps the *unhappy* path from leaving one behind.
    Best-effort by design: a Run that is already terminal refuses the signal with 409, and
    that refusal is the answer, not a failure.
    """
    api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def held_run_ids(api: httpx.Client) -> list[str]:
    """Every Run the stack is holding a slot for, across every page of the list."""
    held: list[str] = []
    cursor: str | None = None
    while True:
        parameters = {"cursor": cursor} if cursor else {}
        response = api.get(RUNS, params=parameters)
        assert response.status_code == HTTP_OK, response.text
        body = response.json()
        held.extend(run["id"] for run in body["items"] if run["status"] in (QUEUED, NEEDS_YOU))
        cursor = body.get("next_cursor")
        if not cursor:
            return held


def _every(count: int, seconds: float) -> Iterator[int]:
    """`count` moments, `seconds` apart, starting now — a sampler, not a wait."""
    for index in range(count):
        if index:
            time.sleep(seconds)
        yield index


@pytest.fixture(scope="module")
def interrupted(
    request: pytest.FixtureRequest,
    api: httpx.Client,
    fixtures: Fixtures,
    settings: Settings,
    sessions: Any,
) -> Iterator[dict[str, Any]]:
    """One Run, killed while `checkout` runs its install, brought back, and watched to `done`.

    Everything the scenario observes is gathered here, once: the tests below are assertions
    over it, not seven kills. The container is resolved first, so a run with no stack to kill
    fails before it has created a Project in somebody's database — and the teardown reports
    the attempt table and releases the Run however this ends, because a scenario that failed
    halfway is the one whose table is worth reading and whose Run is worth releasing.
    """
    before = generation()
    marker = f"aio-durability-{uuid4().hex}"
    project_id, repository_id = new_repository(
        api, fixtures, settings, f": {marker}; sleep {INSTALL_SECONDS}"
    )
    run_id = start_run(api, INSTALL_TEMPLATE, repository_id, project_id)
    try:
        wait_for_row(sessions, run_id, CHECKOUT, RUNNING)
        before_groups = wait_for_process(marker)
        plan_before = attempts_of(sessions, run_id, PLAN)

        kill_backend()
        restart = restart_backend()
        wait_healthy(api, restart)
        after = generation()

        wait_for_attempt(sessions, run_id, CHECKOUT, 2)
        wait_for_process(marker)
        samples = [len(process_groups(marker)) for _ in _every(SAMPLES, SAMPLE_INTERVAL_SECONDS)]

        yield {
            "id": run_id,
            "marker": marker,
            "status": wait_for(api, run_id, ENDINGS),
            "before_groups": before_groups,
            "samples": samples,
            "generations": (before, after),
            "plan_before": plan_before,
        }
    finally:
        report(request, sessions, run_id)
        release(api, run_id)


def test_the_backend_really_died_and_came_back(interrupted: dict[str, Any]) -> None:
    """Everything below is only evidence if the process was actually replaced."""
    before, after = interrupted["generations"]

    assert after != before, f"the {SERVICE} container was not restarted: still {before}"


def test_the_run_resumes_after_the_restart_and_reaches_done(
    interrupted: dict[str, Any], sessions: Any
) -> None:
    """FR-12's headline: a killed Run is finished by the process that comes after it."""
    if interrupted["status"] != DONE:
        pytest.fail(ended_badly(sessions, interrupted))
    assert [row.status for row in rows_of(sessions, interrupted["id"])] == [DONE] * 3


def ended_badly(sessions: Any, scenario: dict[str, Any]) -> str:
    """Why a Run did not reach `done`, read off the Run itself rather than guessed."""
    run = run_of(sessions, scenario["id"])
    if run is None:
        return f"run {scenario['id']} ended {scenario['status']} and its row is not in the database"
    return (
        f"run ended {scenario['status']} after the restart: "
        f"{run.park_kind} at {run.park_path} — {run.park_reason}"
    )


def test_a_row_finished_before_the_kill_is_not_re_executed(
    interrupted: dict[str, Any], sessions: Any
) -> None:
    """The `plan` row was `done` when the process died. Replay hands its recorded step output
    back rather than running it again, so it still holds exactly the one Attempt."""
    assert [attempt.n for attempt in interrupted["plan_before"]] == [1]
    assert [attempt.n for attempt in attempts_of(sessions, interrupted["id"], PLAN)] == [1]


def test_the_interrupted_row_records_its_lost_attempt_and_the_one_that_replaced_it(
    interrupted: dict[str, Any], sessions: Any
) -> None:
    """`start_attempt` finds the row `running` with an Attempt that never ended, closes it
    `error`, and numbers the next one after it — which is what makes the kill visible.

    The Attempt carries no reason column (`domain/entities/attempt.py`), so `error` plus a
    closed `ended_at` is the whole of what the interruption stores; the word `interrupted`
    itself is a log line in `start_attempt`, not a field.
    """
    attempts = attempts_of(sessions, interrupted["id"], CHECKOUT)

    assert [attempt.n for attempt in attempts] == [1, 2]
    assert attempts[0].status == ERROR
    assert attempts[0].ended_at is not None
    assert attempts[1].status == DONE


def test_no_other_row_of_the_interrupted_run_ran_twice(
    interrupted: dict[str, Any], sessions: Any
) -> None:
    """The rows either side of the interrupted one ran once each: the restart re-executed the
    step that was in flight and replayed the rest."""
    once = [row.path for row in rows_of(sessions, interrupted["id"]) if row.path != CHECKOUT]

    for path in once:
        assert [a.n for a in attempts_of(sessions, interrupted["id"], path)] == [1], path


def test_exactly_one_process_group_carries_the_run_after_the_restart(
    interrupted: dict[str, Any],
) -> None:
    """One group before the kill, and one after it, at every sample.

    What this proves is the double-start net: the process that replaced the dead one started
    exactly one group and nothing appeared beside it. It does not prove an orphan was reaped —
    killing the container tears down its PID namespace, so the previous child is gone before
    any code of ours could reap it. The module docstring says so at length; the test name says
    "carries the Run", not "no orphan survived", for the same reason.
    """
    assert len(interrupted["before_groups"]) == 1, interrupted["before_groups"]
    assert interrupted["samples"] == [1] * SAMPLES, interrupted["samples"]


def test_the_run_records_one_worktree_across_both_attempts(
    interrupted: dict[str, Any], sessions: Any
) -> None:
    """`git.worktree` reuses the worktree its lost attempt made and appends no second entry."""
    run = run_of(sessions, interrupted["id"])

    assert run is not None
    assert len(run.worktrees) == 1
    assert run.worktree_path == run.worktrees[0].path


def test_the_gate_record_opens_once_and_closes_once(
    interrupted: dict[str, Any], sessions: Any
) -> None:
    """A restart is not a second beginning: the Run started once and finished once (AD-8)."""
    events = [record.event for record in records_of(sessions, interrupted["id"])]

    assert events.count(RUN_STARTED) == 1
    assert events.count(RUN_FINISHED) == 1
    assert events[0] == RUN_STARTED
    assert events[-1] == RUN_FINISHED


def run_of(sessions: Any, run_id: str) -> Any:
    with sessions() as session:
        return SQLAlchemyRunRepository(session).get(UUID(run_id))


def records_of(sessions: Any, run_id: str) -> list[Any]:
    with sessions() as session:
        return SQLAlchemyGateRecordRepository(session).list_for_run(UUID(run_id))


# ── scenario 2: killed while the Run waits for the Operator ──────────────────────────────


@pytest.fixture(scope="module")
def parked(
    request: pytest.FixtureRequest,
    api: httpx.Client,
    fixtures: Fixtures,
    settings: Settings,
    sessions: Any,
) -> Iterator[dict[str, Any]]:
    """One Run parked on a real `checkpoint`, killed inside its `recv`, restarted, continued.

    The wait is ended by the signal, not by `HUMAN_WAIT_SECONDS` — the deadline stays at
    whatever the stack is configured with, so nothing here depends on shortening it. The
    container is resolved first, and the Run released afterwards, for the reasons
    `interrupted`'s own docstring gives.
    """
    before = generation()
    project_id, repository_id = new_repository(api, fixtures, settings)
    run_id = start_run(api, CHECKPOINT_TEMPLATE, repository_id, project_id)
    try:
        wait_for(api, run_id, {NEEDS_YOU})

        kill_backend()
        restart = restart_backend()
        wait_healthy(api, restart)
        after = generation()

        still_parked = status_of(api, run_id)
        resumed = api.post(f"{RUNS}/{run_id}/signals", json={"kind": "continue", "payload": {}})
        if resumed.status_code != HTTP_OK:
            # reported here rather than as a two-minute walk stall: a refused signal and a
            # walk that never woke up are different bugs, and only one of them is about `recv`
            pytest.fail(f"`continue` was refused after the restart: {resumed.text}")

        yield {
            "id": run_id,
            "status": wait_for(api, run_id, ENDINGS),
            "still_parked": still_parked,
            "signal": resumed,
            "generations": (before, after),
        }
    finally:
        report(request, sessions, run_id)
        release(api, run_id)


def test_a_parked_run_survives_the_restart_and_is_still_waiting(parked: dict[str, Any]) -> None:
    """The `recv` half of FR-12: the walk woke up again on the row it was parked on, and the
    Operator's signal was still admitted (409 would mean the Run had moved)."""
    before, after = parked["generations"]

    assert after != before, f"the {SERVICE} container was not restarted: still {before}"
    assert parked["still_parked"] == NEEDS_YOU
    assert parked["signal"].json()["status"] == RUNNING


def test_the_continued_run_finishes_with_no_row_run_twice(
    parked: dict[str, Any], sessions: Any
) -> None:
    """No repeated row: every row of the plan ran exactly once, across the restart."""
    if parked["status"] != DONE:
        pytest.fail(ended_badly(sessions, parked))
    rows = rows_of(sessions, parked["id"])

    assert [row.path for row in rows] == [PLAN, PAUSE, AFTER]
    assert [row.status for row in rows] == [DONE] * 3
    for row in rows:
        assert [attempt.n for attempt in attempts_of(sessions, parked["id"], row.path)] == [1]


def test_neither_run_leaves_a_slot_held(
    parked: dict[str, Any], interrupted: dict[str, Any], api: httpx.Client
) -> None:
    """Twice-runnable: this module hands the stack back with neither of its Runs queued or
    parked, so a second `pytest tests/e2e` starts with every slot free (AD-12). Both Runs,
    across every page — the interrupted one is the one that can actually be left held."""
    mine = {parked["id"], interrupted["id"]}

    assert not mine.intersection(held_run_ids(api))
