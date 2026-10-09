"""The hub-Run initiative workflow, proven end to end on the scripted harness (story H5,
the hub-Run initiative workflow, AD-9/AD-12/AD-14).

H1..H4 built the pieces — `git.submodule`, `workdir` on `git.commit`/`git.push`, `workdir`
on the `agent` kind's dual-tree attempt tracking — and each has unit coverage of its own.
What none of them proves is that the *whole* workflow holds together against a real git
process: a hub repository whose `repos/alpha` and `repos/beta` submodules are two entirely
separate origins, one `initiative-hub@1` Run that walks both epics on a single shared
branch, dispatching each epic's Story *inside* its own member checkout while every spec
artifact — `SPEC.md`, `stories.yaml`, the Story files, the spec-gate result, the retro —
stays at the hub. The model this journey exists to prove: code lands on each member's own
origin, spec artifacts land on the hub's, and the hub never moves a gitlink pointer to get
there.

**One spec module, one journey, following `test_uj3.py`'s own shape.** `started` is the one
fixture that owns the Run's lifecycle (`try`/`finally: cancel`, the way `test_uj3.py`'s
`blocked` fixture does) — every fixture after it is a plain function built on the one before,
so a failure anywhere in the chain still tears the Run down through the fixture that opened
it.

**It runs on the `fake` harness** (AR-14), needs `ORCH_TEST_MODE=1` on the stack exactly like
every other Epic 6 suite, and additionally needs `GIT_ALLOW_PROTOCOL=file` on `backend-api`
— `docker-compose.e2e.yml` sets both, `make e2e` is what uses it. See
`tests/e2e/helpers/hub_fixture.py`'s own module docstring for why the second variable exists
and why it is e2e-only.

**Nothing here pins shipped template content.** This journey *runs* `initiative-hub@1`,
`initiative-hub-epic@1` and `initiative-hub-story@1` by their shipped names and latest
stored version, resolved from the templates API rather than hardcoded — that is what the
story exists to prove, and hard rule 6's "no test may pin shipped template content" is about
step ids, ordering, counts and graph shapes a test asserts on, not about running the
Template at all. The row paths asserted below are exactly the ones this journey polls for,
and no more: neither `initiative-hub@1` nor its callees are referenced by
`test_templates.py`'s frozen `pinned_by == 0` assertions (those name `epic@1` alone), so
pinning them here breaks nothing.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.hub_fixture import HubFixture, HubRepos
from tests.e2e.test_answer_signal import poll_until, step_status
from tests.e2e.test_run_creation import PROJECTS, RUNS, TEMPLATES, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201
TIMEOUT_SECONDS = 10.0

#: The shipped Templates this journey runs, by name — resolved to their latest stored
#: version through the templates API, never hardcoded (see the module docstring).
TEMPLATE_NAME = "initiative-hub"

#: The Run's own inputs (H3's own convention: `branch` shared by the hub and every member,
#: `initiative_folder` naming `epics.yaml` and the two epics' spec folders beneath it).
BRANCH = "initiative/demo"
INITIATIVE_FOLDER = "initiatives/demo"
BASE_BRANCH = "main"

ALPHA_SPEC_FOLDER = f"{INITIATIVE_FOLDER}/alpha-epic"
BETA_SPEC_FOLDER = f"{INITIATIVE_FOLDER}/beta-epic"
ALPHA_WORKDIR = "repos/alpha"
BETA_WORKDIR = "repos/beta"

# ── row paths (`initiative-hub-epic@1`/`initiative-hub-story@1` inlined under `epics[i]`,
# `rows.py`'s own "a call contributes no segment inside a loop") ──────────────────────────
CHECKOUT = "checkout"
SUBMODULES = "submodules"

ALPHA_BRANCH = "epics[0].branch"
ALPHA_SETUP = "epics[0].setup"
ALPHA_BASELINE = "epics[0].baseline"
ALPHA_SPEC_GATE = "epics[0].spec-gate"
ALPHA_STORY_BUILD = "epics[0].stories[0].build"
ALPHA_STORY_VERIFY = "epics[0].stories[0].verify"
ALPHA_STORY_COMMIT_GUARD = "epics[0].stories[0].commit-guard"
ALPHA_GEN_E2E = "epics[0].gen-e2e"
ALPHA_COMMIT_E2E = "epics[0].commit-e2e"
ALPHA_E2E = "epics[0].e2e"
ALPHA_RETRO = "epics[0].retro"
ALPHA_COMMIT_RETRO = "epics[0].commit-retro"
ALPHA_PUSH_CODE = "epics[0].push-code"
ALPHA_PUSH_HUB = "epics[0].push-hub"
ALPHA_AFTER = "epics[0].after"

BETA_BRANCH = "epics[1].branch"
BETA_SETUP = "epics[1].setup"
BETA_STORY_BUILD = "epics[1].stories[0].build"
BETA_STORY_COMMIT_GUARD = "epics[1].stories[0].commit-guard"
BETA_GEN_E2E = "epics[1].gen-e2e"
BETA_E2E = "epics[1].e2e"
BETA_RETRO = "epics[1].retro"
BETA_COMMIT_RETRO = "epics[1].commit-retro"
BETA_PUSH_CODE = "epics[1].push-code"
BETA_PUSH_HUB = "epics[1].push-hub"

#: `git.submodule`'s own "not a workdir" park, matched loosely below.
PROTECTED_HIT = f"{ALPHA_WORKDIR}/tests/smoke.test.sh"


# ── the stack, the fixture, and the two starting points ───────────────────────────────────


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def bmad_version() -> str:
    value = os.environ.get("BMAD_VERSION")
    if not value:
        pytest.fail(
            "BMAD_VERSION is not set: the hub fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return value


@pytest.fixture(scope="module")
def hub(settings: Settings, bmad_version: str) -> HubFixture:
    return HubFixture(settings.work_dir, bmad_version)


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    """Fail by name when the stack is not in test mode, rather than timing out later."""
    response = api.get("/api/v1/harnesses")
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert "fake" in rows, (
        "the `fake` harness is not seeded: this gate needs ORCH_TEST_MODE=1 on the stack "
        "(docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows["fake"]["enabled"] is True, rows["fake"]


@pytest.fixture(scope="module")
def report(request: pytest.FixtureRequest) -> Any:
    """Write past pytest's capture, so a diagnostic prints whether the run around it passes
    or fails — `test_uj3.py`'s own idiom, for the same reason."""
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")

    def write(line: str) -> None:
        if reporter is None:  # pragma: no cover — pytest always registers it
            return
        reporter.write_line(line)

    return write


def latest_version(api: httpx.Client, name: str) -> int:
    """The highest stored version of a shipped Template, resolved through the API rather
    than hardcoded — see the module docstring on why this journey may pin the name at all."""
    response = api.get(f"{TEMPLATES}/{name}/versions")
    assert response.status_code == HTTP_OK, response.text
    items = response.json()["items"]
    assert items, f"{name} has no stored versions"
    return max(items)


def origin_path(url: str) -> str:
    """The bare origin's filesystem path, for a direct `git -C` read — `HubRepos`' own URLs
    are `file://{path}`, so stripping the scheme is the path `-C` wants."""
    prefix = "file://"
    assert url.startswith(prefix), url
    return url[len(prefix) :]


def start_hub_run(
    api: httpx.Client, hub: HubFixture, *, poison_alpha: bool = False
) -> tuple[str, HubRepos]:
    """A fresh hub-Run fixture and a Run of `initiative-hub@1`'s latest stored version."""
    project_id = create_project(api)
    repos = hub.make_hub(poison_alpha=poison_alpha)
    # `tests/**` is listed, not assumed: since the Operator decision of 2026-10-06 a
    # Repository freezes exactly the globs it was registered with, and the poisoned Story 1
    # below has to find `members/alpha/tests/smoke.test.sh` frozen to park `protected_path`.
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={"url": repos.hub, "default_branch": BASE_BRANCH, "test_globs": ["tests/**"]},
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    version = latest_version(api, TEMPLATE_NAME)
    started = api.post(
        RUNS,
        json={
            "template_name": TEMPLATE_NAME,
            "template_version": version,
            "project_id": project_id,
            "repository_id": repository_id,
            "base_branch": BASE_BRANCH,
            "budget_usd": "5",
            "harness": "fake",
            "inputs": {"branch": BRANCH, "initiative_folder": INITIATIVE_FOLDER},
        },
    )
    assert started.status_code == HTTP_CREATED, started.text
    return str(started.json()["run"]["id"]), repos


# ── the journey: checkout → submodules → alpha epic → alpha's done checkpoint ─────────────


@pytest.fixture(scope="module")
def started(api: httpx.Client, hub: HubFixture, test_mode: None) -> Iterator[dict[str, Any]]:
    """The Run, walked until alpha-epic's `baseline` row is `done` — proving `checkout`,
    `submodules`, alpha's own `branch` checkout and its `setup` skip already ran, in that
    order. `setup`'s own `skipped` is a *plan-time* fact (`rows.py::row_status`: a `shell`
    row with an empty command is born `skipped`, before the walker executes anything), so
    polling for it directly would return on the very first read — `baseline` is the first
    row after it that is actually a runtime fact."""
    run_id, repos = start_hub_run(api, hub)
    try:
        detail = poll_until(
            api,
            run_id,
            lambda detail: step_status(detail, ALPHA_BASELINE) == "done",
            "alpha-epic's baseline gate finishing",
        )
        yield {"id": run_id, "repos": repos, "detail": detail}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def test_checkout_attached_the_declared_branch_by_its_exact_name(started: dict[str, Any]) -> None:
    """AD-7/AD-14: `mode: attach` takes the declared name exactly, never an allocated
    ordinal — the one fact `run.worktrees[]` carries and a git read cannot improve on."""
    detail = started["detail"]
    assert step_status(detail, CHECKOUT) == "done"
    (worktree,) = detail["run"]["worktrees"]

    assert worktree["branch"] == BRANCH
    assert worktree["created_branch"] is True


def test_submodules_were_initialized(started: dict[str, Any]) -> None:
    detail = started["detail"]
    assert step_status(detail, SUBMODULES) == "done"


def test_alpha_epics_own_branch_row_is_done(started: dict[str, Any]) -> None:
    detail = started["detail"]
    assert step_status(detail, ALPHA_BRANCH) == "done"


def test_alpha_epics_setup_is_skipped_for_no_command_not_a_failure(
    started: dict[str, Any],
) -> None:
    """`epics.yaml` leaves alpha-epic's `install` field out on purpose (the fixture's own
    proof of the skip): `run: "{{install}}"` resolves to nothing, which is
    `skip_reason.py::REASON_NO_COMMAND`, never a step that ran a bare `cd`."""
    detail = started["detail"]
    row = next(step for step in detail["steps"] if step["path"] == ALPHA_SETUP)

    assert row["status"] == "skipped"
    assert row["reason"] == "no command"


@pytest.fixture(scope="module")
def alpha_checkpoint(api: httpx.Client, started: dict[str, Any]) -> dict[str, Any]:
    """The same Run, walked on to alpha-epic's own `done_checkpoint` park — everything from
    `baseline` through `push-hub` has already run by the time this row is reached."""
    detail = poll_until(
        api,
        started["id"],
        lambda detail: (
            detail["run"]["status"] == "needs_you"
            and step_status(detail, ALPHA_AFTER) == "checkpoint"
        ),
        "the Run parking at alpha-epic's own done checkpoint",
    )
    return {**started, "detail": detail}


def test_alpha_epics_whole_frame_ran_in_order(alpha_checkpoint: dict[str, Any]) -> None:
    """Every row between `setup` and the done checkpoint is `done` — proof the frame walked
    straight through with no park along the way, before the individual rows are read for
    what each one specifically left behind."""
    detail = alpha_checkpoint["detail"]
    for path in (
        ALPHA_BASELINE,
        ALPHA_SPEC_GATE,
        ALPHA_STORY_BUILD,
        ALPHA_STORY_VERIFY,
        ALPHA_STORY_COMMIT_GUARD,
        ALPHA_GEN_E2E,
        ALPHA_COMMIT_E2E,
        ALPHA_E2E,
        ALPHA_RETRO,
        ALPHA_COMMIT_RETRO,
        ALPHA_PUSH_CODE,
        ALPHA_PUSH_HUB,
    ):
        assert step_status(detail, path) == "done", path


def test_alpha_epics_done_checkpoint_parks_with_continue_offered(
    alpha_checkpoint: dict[str, Any],
) -> None:
    detail = alpha_checkpoint["detail"]
    assert detail["alert"]["park_kind"] == "checkpoint"
    assert detail["alert"]["row_kind"] == "checkpoint"
    assert "continue" in detail["admitted_signals"]


def test_the_spec_gate_result_is_readable_at_its_hub_path_through_the_files_endpoint(
    api: httpx.Client, alpha_checkpoint: dict[str, Any]
) -> None:
    """The `spec-gate` row carries no `workdir`, so it dispatches at the hub root and its
    `expect.files` reads it there — the direct proof the fake harness wrote to the HUB path
    named in the dispatch sentence, not into `repos/alpha`."""
    response = api.get(
        f"{RUNS}/{alpha_checkpoint['id']}/files",
        params={"path": f"{ALPHA_SPEC_FOLDER}/spec-gate-result.md"},
    )
    assert response.status_code == HTTP_OK, response.text
    assert "status: done" in response.json()["content"]


def test_the_member_origins_alpha_branch_holds_the_code_commit_and_the_e2e_commit(
    hub: HubFixture, alpha_checkpoint: dict[str, Any], report: Any
) -> None:
    """(a) the proof the code landed on the *member's own* origin: `push-code` pushed
    `initiative/demo` to `repos/alpha`'s own bare origin, independent of the hub's.

    **Known defect, confirmed by direct reproduction (story H5, 2026-09-23; reported, not
    fixed here — out of this story's scope, see the hand-back).** `gen-e2e`'s own commit is
    currently orphaned rather than reaching the branch: `agent_workdir.verify()` calls
    `Git.submodule_update` on *every* `workdir` agent row to confirm the folder is still an
    initialized submodule, and `git submodule update` (default checkout mode) unconditionally
    resets the submodule to the commit recorded in the **hub's own index** — which nothing
    ever advances, because AD-14's gitlink exclusion keeps every hub-level commit from
    touching it. The result: any workdir dispatch that runs after an earlier one already
    committed inside the same submodule (`gen-e2e` after `commit-guard`, here) finds its
    submodule silently reset and HEAD detached at the stale gitlink SHA before it writes
    anything — so `tests/e2e_generated.test.sh` lands on an orphaned commit `push-code`'s own
    branch ref never points at, while `src/alpha_feature.py` (committed *before* that reset,
    while `HEAD` was still on `initiative/demo`) reaches the branch and is pushed correctly.
    Reproduced directly against `SubprocessGit`: a second `submodule_update(wt)` call after a
    `workdir` commit leaves `git -C repos/alpha rev-parse --abbrev-ref HEAD` reading `HEAD`
    (detached) at the gitlink's original SHA, with the `initiative/demo` branch ref itself
    left correctly pointing at the newer commit — exactly what this assertion catches.
    """
    alpha_origin = origin_path(alpha_checkpoint["repos"].alpha)
    report(f"\n[hub-run diagnostic] alpha origin log:\n{hub.log(alpha_origin, BRANCH)}")
    report(f"[hub-run diagnostic] alpha origin tree:\n{hub.tree(alpha_origin, BRANCH)}")

    work = hub.show(alpha_origin, BRANCH, "src/alpha_feature.py")
    generated = hub.show(alpha_origin, BRANCH, "tests/e2e_generated.test.sh")

    assert "alpha feature work" in work
    assert generated.strip()


def test_the_hub_origins_branch_holds_the_spec_artifacts_and_no_other_epics_work(
    hub: HubFixture, alpha_checkpoint: dict[str, Any]
) -> None:
    """(b), the first half: the hub origin's own `initiative/demo` holds alpha-epic's spec
    artifacts — the spec-gate result, the Story file, the retro — all of them hub-side, none
    of them requiring a read of `repos/alpha`'s own history."""
    hub_origin = origin_path(alpha_checkpoint["repos"].hub)
    tree = hub.tree(hub_origin, BRANCH)

    assert f"{ALPHA_SPEC_FOLDER}/spec-gate-result.md" in tree
    assert f"{ALPHA_SPEC_FOLDER}/stories/1-work.md" in tree
    assert f"{ALPHA_SPEC_FOLDER}/retro.md" in tree

    story = hub.show(hub_origin, BRANCH, f"{ALPHA_SPEC_FOLDER}/stories/1-work.md")
    assert "status: done" in story


def test_the_hub_never_moves_the_alpha_gitlink_pointer(
    hub: HubFixture, alpha_checkpoint: dict[str, Any]
) -> None:
    """(b), the second half — the model's own guarantee: `Git.stage`'s "everything" call
    excludes every gitlink the tree records (AD-14), so `commit-retro`'s sweep never advances
    `repos/alpha` past whatever it was pointed at when the fixture wired the submodule up.
    The base branch's own gitlink sha is the fixture's original one; the pushed initiative
    branch's has to be byte-for-byte the same."""
    hub_origin = origin_path(alpha_checkpoint["repos"].hub)

    original = hub.gitlink_sha(hub_origin, BASE_BRANCH, ALPHA_WORKDIR)
    after = hub.gitlink_sha(hub_origin, BRANCH, ALPHA_WORKDIR)

    assert original
    assert after == original


# ── continue: beta epic runs, sequentially, and the Run ends done ─────────────────────────


@pytest.fixture(scope="module")
def continued(api: httpx.Client, alpha_checkpoint: dict[str, Any]) -> dict[str, Any]:
    """*Continue* at alpha-epic's done checkpoint, walked on until the Run is terminal —
    beta-epic carries no `done_checkpoint`, so nothing stops it before the Run finishes."""
    run_id = alpha_checkpoint["id"]
    response = api.post(f"{RUNS}/{run_id}/signals", json={"kind": "continue"})
    assert response.status_code == HTTP_OK, response.text
    detail = poll_until(
        api,
        run_id,
        lambda detail: detail["run"]["status"] in ("done", "failed", "cancelled"),
        "the Run finishing after alpha-epic's continue",
    )
    return {**alpha_checkpoint, "detail": detail, "signalled": response.json()["status"]}


def test_beta_epic_ran_sequentially_after_alpha_and_the_run_ends_done(
    continued: dict[str, Any],
) -> None:
    """(d) sequential, and (e) terminal: beta-epic's whole frame is `done`, and so is the
    Run — list order is the dependency `initiative-hub@1`'s own `epics` loop states."""
    detail = continued["detail"]
    assert continued["signalled"] == "running"
    assert detail["run"]["status"] == "done"
    for path in (
        BETA_BRANCH,
        BETA_SETUP,
        BETA_STORY_BUILD,
        BETA_STORY_COMMIT_GUARD,
        BETA_GEN_E2E,
        BETA_E2E,
        BETA_RETRO,
        BETA_COMMIT_RETRO,
        BETA_PUSH_CODE,
        BETA_PUSH_HUB,
    ):
        assert step_status(detail, path) == "done", path


def test_beta_epics_setup_actually_ran_its_declared_install(continued: dict[str, Any]) -> None:
    """The fixture's own asymmetry, the other way round: `beta-epic` *does* declare
    `install`, so its `setup` row is a real `done` shell row, not a second skip."""
    row = next(step for step in continued["detail"]["steps"] if step["path"] == BETA_SETUP)
    assert row["status"] == "done"


def test_the_member_origins_beta_branch_holds_the_code_commit_and_the_e2e_commit(
    hub: HubFixture, continued: dict[str, Any], report: Any
) -> None:
    """`alpha`'s sibling — the same known `agent_workdir.verify()` defect documented on
    `test_the_member_origins_alpha_branch_holds_the_code_commit_and_the_e2e_commit` applies
    here too, and for the same reason (`gen-e2e` after `commit-guard`, inside `repos/beta`)."""
    beta_origin = origin_path(continued["repos"].beta)
    report(f"\n[hub-run diagnostic] beta origin log:\n{hub.log(beta_origin, BRANCH)}")
    report(f"[hub-run diagnostic] beta origin tree:\n{hub.tree(beta_origin, BRANCH)}")

    work = hub.show(beta_origin, BRANCH, "src/beta_feature.py")
    generated = hub.show(beta_origin, BRANCH, "tests/e2e_generated.test.sh")

    assert "beta feature work" in work
    assert generated.strip()


def test_the_hub_origins_branch_holds_betas_spec_artifacts_too(
    hub: HubFixture, continued: dict[str, Any]
) -> None:
    hub_origin = origin_path(continued["repos"].hub)
    tree = hub.tree(hub_origin, BRANCH)

    assert f"{BETA_SPEC_FOLDER}/spec-gate-result.md" in tree
    assert f"{BETA_SPEC_FOLDER}/stories/1-work.md" in tree
    assert f"{BETA_SPEC_FOLDER}/retro.md" in tree


def test_the_hub_never_moves_the_beta_gitlink_pointer_either(
    hub: HubFixture, continued: dict[str, Any]
) -> None:
    hub_origin = origin_path(continued["repos"].hub)

    original = hub.gitlink_sha(hub_origin, BASE_BRANCH, BETA_WORKDIR)
    after = hub.gitlink_sha(hub_origin, BRANCH, BETA_WORKDIR)

    assert original
    assert after == original


def test_the_run_never_planned_a_checkpoint_row_for_beta(continued: dict[str, Any]) -> None:
    """`beta-epic` declares no `done_checkpoint`, so `pause_after_item_when` never fires for
    it — no `epics[1].after` row exists at all, which is a different fact from one that
    exists and reads `skipped`."""
    detail = continued["detail"]
    assert step_status(detail, "epics[1].after") is None


# ── the protected-path case (item 4): a separate, short-lived Run of its own ──────────────
#
# Started only once the journey Run above is terminal, so this module never holds more than
# one of `MAX_ACTIVE_RUNS`'s global slots at a time (AD-12) — the same discipline
# `test_uj3.py`'s own scenario D keeps.


@pytest.fixture(scope="module")
def protected_path_park(
    api: httpx.Client, hub: HubFixture, continued: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """A fresh hub-Run, `alpha`'s Story 1 poisoned to edit a frozen test file, walked until
    `commit-guard` parks `protected_path`."""
    run_id, repos = start_hub_run(api, hub, poison_alpha=True)
    try:
        detail = poll_until(
            api,
            run_id,
            lambda detail: (
                detail["run"]["status"] == "needs_you"
                and (detail["alert"] or {}).get("park_kind") == "protected_path"
            ),
            "the Run parking protected_path on alpha-epic's Story 1",
        )
        yield {"id": run_id, "repos": repos, "detail": detail}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def test_editing_a_frozen_member_test_file_parks_protected_path_naming_it(
    protected_path_park: dict[str, Any],
) -> None:
    """AD-17's amendment, proven for a `workdir` row: `tests/smoke.test.sh` is committed in
    the member's own seed, so it is frozen at Story 1's first attempt, and the poisoned
    scenario editing it — leaving it uncommitted — is exactly what `commit-guard` (H4's own
    `workdir` branch of `git.commit`) parks on, naming the hit `repos/alpha`-prefixed."""
    detail = protected_path_park["detail"]
    hits = [hit["path"] for hit in detail["alert"]["payload"]["hits"]]

    assert detail["alert"]["park_kind"] == "protected_path"
    assert PROTECTED_HIT in detail["alert"]["reason"]
    assert PROTECTED_HIT in hits
    assert step_status(detail, ALPHA_STORY_BUILD) == "done"
    assert step_status(detail, ALPHA_STORY_VERIFY) == "done"
    assert step_status(detail, ALPHA_STORY_COMMIT_GUARD) == "error"
