"""`scripts/readiness_fixture.sh`: the bare origin it seeds has to answer `HEAD` (SPEC CAP-8).

The readiness fixture exists so that `POST /harnesses/{name}/readiness` has a repository to
clone, and the first line of the clone check is `Git.ls_remote(url)` with no ref — which the
adapter runs as `git ls-remote -- <url> HEAD` (`infrastructure/git/subprocess_git.py`). A
bare repository whose `HEAD` is a symbolic ref to a branch nothing ever creates answers that
with **no lines**, and `application/use_cases/clone_check.py::_reachable` reads no answer as
`the remote answered no refs` — a failed check, and a `422` on the readiness request.

`git init --bare` without `-b` points `HEAD` at whatever `init.defaultBranch` says, which is
`master` wherever nobody configured otherwise — the backend image among them. The fixture
then builds and pushes `main`, and `HEAD` is left dangling.

Two halves, both needed. The textual one is the guard: it reads the committed script and
asserts the flag is there, so a later edit that drops it fails here rather than in a
readiness Run nobody is watching. The behavioural one is the reason: it drives real `git` in
`tmp_path` and shows what the two `HEAD`s actually answer, so the guard is not a rule whose
justification has to be taken on trust.

`init.defaultBranch` is set explicitly on every `git init` below rather than left to the
machine: a developer whose global config already says `main` would otherwise see the
unpatched case pass, which is exactly how this defect survived Epic 5's own run of the gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "readiness_fixture.sh"

#: The branch the fixture builds, pushes, and the readiness Project's Repository names.
MAIN = "main"
#: What `init.defaultBranch` says on a machine nobody configured — the image's own answer.
UNCONFIGURED_DEFAULT = "master"

#: The `git init --bare` line of the script, wherever it sits in the file.
BARE_INIT = re.compile(r"^\s*git init --bare\b.*$", re.MULTILINE)


@pytest.fixture(autouse=True)
def git_binary() -> str:
    """`git` is a requirement of this module, not a condition on running it.

    The behavioural half is the whole justification for the textual half; skipping it on a
    machine without `git` would leave the guard asserting a flag for no stated reason.
    """
    found = shutil.which("git")
    if found is None:
        pytest.fail("git is not on PATH: this module drives real `git` to show what HEAD answers")
    return found


def git(*args: str, cwd: Path | None = None) -> str:
    """One `git` command, with the two identity variables every commit here needs."""
    result = subprocess.run(
        ["git", "-c", "user.email=orchestrator@localhost", "-c", "user.name=orchestrator", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def bare_origin(root: Path, name: str, *, default_branch: str) -> Path:
    """A bare repository created the way the script's `git init --bare` line creates one."""
    origin = root / name
    git("-c", f"init.defaultBranch={default_branch}", "init", "--bare", "-q", str(origin))
    return origin


def push_main(root: Path, origin: Path) -> None:
    """Build one commit on `main` and push it, exactly as the fixture script does."""
    work = root / f"work-{origin.name}"
    git("init", "-q", "-b", MAIN, str(work))
    (work / "README.md").write_text("readiness fixture\n")
    git("add", "-A", cwd=work)
    git("commit", "-q", "-m", "seed", cwd=work)
    git("push", "-q", "-f", str(origin), MAIN, cwd=work)


def head_lines(origin: Path) -> int:
    """What the clone check's first line asks: `git ls-remote -- <url> HEAD`, in lines."""
    answer = git("ls-remote", "--", f"file://{origin}", "HEAD")
    return len([line for line in answer.splitlines() if line.strip()])


# ── the guard ───────────────────────────────────────────────────────────────


def test_the_script_creates_the_bare_origin_on_main() -> None:
    """The committed script's own `git init --bare` line carries `-b main`."""
    line = BARE_INIT.search(SCRIPT.read_text())

    assert line is not None, f"{SCRIPT} has no `git init --bare` line"
    assert "-b main" in line.group(0), line.group(0)


def test_the_script_is_the_one_the_entrypoint_runs() -> None:
    """The guard above is worth nothing if it reads a file no container executes."""
    entrypoint = (REPO_ROOT / "backend-api" / "docker-entrypoint.sh").read_text()

    assert "scripts/readiness_fixture.sh" in entrypoint


# ── the reason ──────────────────────────────────────────────────────────────


def test_a_bare_origin_left_on_the_unconfigured_default_answers_no_head(tmp_path: Path) -> None:
    """`git init --bare` with no `-b`: HEAD points at a `master` the fixture never creates,
    so the clone check's first line gets nothing back and reports `no refs`."""
    origin = bare_origin(tmp_path, "unpatched.git", default_branch=UNCONFIGURED_DEFAULT)
    push_main(tmp_path, origin)

    assert head_lines(origin) == 0


def test_a_bare_origin_created_on_main_answers_exactly_one_head(tmp_path: Path) -> None:
    origin = bare_origin(tmp_path, "patched.git", default_branch=UNCONFIGURED_DEFAULT)
    git("--git-dir", str(origin), "symbolic-ref", "HEAD", f"refs/heads/{MAIN}")
    push_main(tmp_path, origin)

    assert head_lines(origin) == 1


def test_the_branch_itself_is_there_either_way(tmp_path: Path) -> None:
    """The defect is `HEAD` alone: `main` is pushed and found in both repositories, which is
    why the clone check's *later* branch line passed while its first line failed."""
    origin = bare_origin(tmp_path, "either.git", default_branch=UNCONFIGURED_DEFAULT)
    push_main(tmp_path, origin)

    assert git("ls-remote", "--heads", "--", f"file://{origin}", MAIN).strip() != ""
