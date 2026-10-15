"""The repo-init workflow's AD-16 "only" clause: `_bmad/` and the spec folders, nothing else.

`test_repo_init.py::test_no_skill_folder_was_committed` checks two named prefixes —
`.claude/skills/bmad-*` and `.agents/skills/bmad-*` — are absent from the commit. That is
not what AD-16 promises. AD-16 promises that a target repository "commits `_bmad/` … and its
spec folders **only**" — nothing else the installer writes lands in the commit, whatever it
is called. A prior defect showed the gap between the two: `bmad-method`'s opencode output is
`.opencode/commands/bmad-*.md`, a *commands* folder rather than a *skills* one, so it matched
neither ignored prefix and forty-nine files landed in the commit anyway — invisible to a test
that only ever asked about the two skill patterns by name. This module asks the general
question instead, so a fourth tool, or a renamed one, cannot slip through the same gap again.

This runs its own copy of the suite's repo-init fixture (`tests/e2e/templates/repo-init.yaml`,
Operator ruling 2026-10-15: no test follows a shipped Template), the same way
`test_repo_init.py` does, because the "only"
claim can only be checked over the real `bmad-method` installer's real output, not over a
fake: unit coverage of `_ignore_skill_folders` (`tests/unit/test_bmad_install_executor.py`)
already proves the three lines it knows about are appended correctly, but it cannot prove
that those are the only lines the installer's actual output needed.

**What is allowed to be new on `chore/bmad-init` besides `_bmad/`.** This Run declares no
`spec_folder` — `repo-init`'s inputs are `project`, `repository`, `base_branch`, and the
`harness` and `model` its `context` step dispatches on — so there are no spec folders to
allow here. The `context` step writes `AGENTS.md` when a real harness runs it; the scripted
one this suite dispatches writes nothing, which is why that file is not in `ALSO_ALLOWED`.
`.gitignore` is the one other file the row is meant to
touch — `bmad.install` appends the ignore lines to it itself (AD-16) — and `README.md` is the
one file `tests/e2e/test_clone_check.py::Fixtures.make` already committed to `main` before the
Run ever started, carried onto the branch rather than added by it.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from orchestrator.application.steps.bmad_install import GITIGNORE
from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.templates import save_repo_init
from tests.e2e.test_clone_check import Fixtures
from tests.e2e.test_repo_init import (
    NEEDS_YOU,
    SCRIPTED_HARNESS,
    continued,
    name_of,
    read_back,
    wait_until_terminal,
)
from tests.e2e.test_run_creation import (
    RUNS,
    clone_check,
    create_project,
    create_repository,
    project_id_of,
    run_payload,
)

HTTP_CREATED = 201
TIMEOUT_SECONDS = 10.0

#: What may be new on `chore/bmad-init` besides `_bmad/` itself — see the module docstring.
ALSO_ALLOWED = ("README.md", GITIGNORE)


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> httpx.Client:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture(scope="module")
def origin(api: httpx.Client, fixtures: Fixtures) -> str:
    """A bare repository with `main` and no `_bmad/` — what `repo-init` is for."""
    return fixtures.make()


@pytest.fixture(scope="module")
def initialised(api: httpx.Client, origin: str, settings: Settings) -> dict[str, Any]:
    """The repo-init fixture, run to completion, exactly as `test_repo_init.py` runs it.

    Including its one stop: the `context-review` checkpoint parks the Run before the commit
    this module reads, so a fixture that only waited would read a branch that was never
    pushed. `continued` is that module's own helper, so the two cannot drift.
    """
    project_id = create_project(api)
    repository_id = create_repository(api, project_id, origin)
    clone_check(api, repository_id)
    payload = run_payload(
        save_repo_init(api, "e2e-repo-init-scope"),
        repository_id,
        project_id=project_id_of(api, repository_id),
        harness=SCRIPTED_HARNESS,
    )
    created = api.post(RUNS, json=payload)
    assert created.status_code == HTTP_CREATED, created.text
    run_id = str(created.json()["run"]["id"])
    parked = wait_until_terminal(api, run_id)
    status = continued(api, run_id) if parked == NEEDS_YOU else parked
    return {"id": run_id, "status": status, "origin": origin}


def test_the_commit_adds_nothing_outside_bmad_and_the_spec_folders(
    initialised: dict[str, Any], settings: Settings
) -> None:
    """AD-16's "only" clause, checked in general rather than against two named prefixes."""
    if initialised["status"] != "done":
        pytest.fail(f"repo-init ended {initialised['status']}, not done")

    output = read_back(settings.work_dir, name_of(initialised["origin"]))
    _, _, rest = output.partition("\n--- files ---\n")
    files, _, _gitignore = rest.partition("\n--- gitignore ---\n")
    committed = files.split()

    escaped = [
        path for path in committed if not path.startswith("_bmad/") and path not in ALSO_ALLOWED
    ]
    assert not escaped, escaped
