"""`fixtures/gates-repo/` as a repository the running backend can clone (SPEC CAP-1, AR-14).

The readiness fixture is materialised at container start by `scripts/readiness_fixture.sh`,
because a readiness Run may be started by an Operator at any moment. This one is materialised
by the test that needs it, for the opposite reason: an Epic 6 scenario wants a *fresh* origin
per run — its Run writes commits onto a branch, and a second run of the same suite against
the same stack must not find the first one's work already there.

**Both topologies, the same way `tests/e2e/test_clone_check.py::Fixtures` does it.** Under
CI the backend is a process on this machine, so writing `WORK_DIR` directly is writing its
filesystem; under `make up` / `make e2e` only the named volumes are shared, so the same
script runs through `docker compose exec -T backend-api`. Each route is tried in turn and a
failure of both is reported with what each said — never skipped, because a gate that skips
when the stack is missing reports success for a suite that ran nothing.

**The `_bmad/` manifest is written here, not committed.** Pre-flight requires
`_bmad/_config/manifest.yaml` at `plan_ref` stating exactly this instance's `BMAD_VERSION`
(AD-16), and a committed one would go stale at the next pin bump and disable every Run
against this fixture. The scripted `fake` harness never reads `_bmad/` — it applies a YAML
scenario and nothing else — so the manifest is all the fixture needs, and `npx bmad-method
install` (30 s and a network) is not.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

#: Where this suite's bare repositories live — the same directory `Fixtures` uses, under the
#: work directory both topologies share.
FIXTURE_DIRECTORY = "e2e-fixtures"

REPO_ROOT = Path(__file__).resolve().parents[4]

#: `test_durability.py`'s own bound, for the same `docker compose exec` route.
DOCKER_TIMEOUT_SECONDS = 60.0

#: The fixture's source, per topology: the checkout on this host, `/app/fixtures` in the
#: image (`backend-api/Dockerfile` copies the whole directory).
SOURCE_HERE = str(REPO_ROOT / "fixtures" / "gates-repo")
SOURCE_IN_CONTAINER = "/app/fixtures/gates-repo"

BRANCH = "main"

#: The shipped Template this fixture is run through, and the line naming it.
EPIC_TEMPLATE = REPO_ROOT / "templates" / "epic.yaml"
NAME_LINE = "name: epic\n"


def epic_template_as(name: str) -> str:
    """`templates/epic.yaml` under a name of this suite's own.

    A Run cannot be started on `epic@1` itself: `pinned_versions` records every version a
    Run pinned, root or callee, and `tests/e2e/test_templates.py` asserts that nothing pins
    `epic@1` — an assertion that has to keep holding when this suite runs twice against the
    same stack. Saving the same plan under a fresh name pins that name instead, and leaves
    the shipped Template's own read model exactly as the frozen test found it. The plan is
    copied rather than written out here so this fixture cannot drift from the real one.
    """
    yaml = EPIC_TEMPLATE.read_text()
    if NAME_LINE not in yaml:
        pytest.fail(f"{EPIC_TEMPLATE} no longer opens with {NAME_LINE!r}")
    return yaml.replace(NAME_LINE, f"name: {name}\n", 1)


#: One script, run either here or inside the container: `$1` is the directory, `$2` the
#: repository name, `$3` the fixture source, `$4` the `BMAD_VERSION` the manifest states.
MAKE_GATES_ORIGIN = """
set -e
dir="$1"; name="$2"; source="$3"; version="$4"
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare --initial-branch=main "$dir/$name.git"
cp -R "$source" "$dir/$name.seed"
cd "$dir/$name.seed"
mkdir -p _bmad/_config
printf 'installation:\\n  version: %s\\n  installDate: 2026-09-09\\nmodules: []\\n' \\
  "$version" > _bmad/_config/manifest.yaml
git init --quiet --initial-branch=main
git config user.email e2e@example.invalid
git config user.name e2e
git add --all
git commit --quiet --message "gates fixture: seed"
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""

#: Read one path out of a Run's own worktree at a ref: `$1` worktree, `$2` ref, `$3` path.
#: `git show` rather than `cat`, so what is asserted is what the *branch* holds — a file the
#: harness left uncommitted is not on the branch and must not read as though it were.
SHOW_AT_REF = """
set -e
git -C "$1" show "$2:$3"
"""

#: Every path the branch holds at a ref, one per line: `$1` worktree, `$2` ref.
LIST_AT_REF = """
set -e
git -C "$1" ls-tree -r --name-only "$2"
"""


class GatesFixture:
    """Makes the gates origin where the backend can reach it, and reads its branch back."""

    def __init__(self, work_dir: Path, bmad_version: str) -> None:
        self.directory = work_dir / FIXTURE_DIRECTORY
        self.bmad_version = bmad_version

    def url(self, name: str) -> str:
        """The URL a Repository is registered with — the same string in both topologies."""
        return f"file://{self.directory}/{name}.git"

    def make(self) -> str:
        """A fresh bare origin holding `fixtures/gates-repo/` on `main`. Returns its URL."""
        name = f"gates-{uuid4()}"
        here = [str(self.directory), name, SOURCE_HERE, self.bmad_version]
        inside = [str(self.directory), name, SOURCE_IN_CONTAINER, self.bmad_version]
        self._either(MAKE_GATES_ORIGIN, here, inside, "create the gates fixture")
        return self.url(name)

    def show(self, worktree: str, ref: str, path: str) -> str:
        """One file's contents at `ref` in `worktree`, or a failure naming both routes."""
        arguments = [worktree, ref, path]
        return self._either(SHOW_AT_REF, arguments, arguments, f"read {path} at {ref}")

    def tree(self, worktree: str, ref: str) -> tuple[str, ...]:
        """Every path the branch holds at `ref`, so an absence can be asserted by name."""
        arguments = [worktree, ref]
        listed = self._either(LIST_AT_REF, arguments, arguments, f"list {ref}")
        return tuple(line.strip() for line in listed.splitlines() if line.strip())

    def _either(self, script: str, here: list[str], inside: list[str], what: str) -> str:
        """Run `script` on this host, else in the container; fail naming both refusals."""
        refusals: list[str] = []
        routes = (
            (["sh", "-c", script, "sh", *here], "on this host"),
            (
                [
                    *("docker", "compose", "exec", "-T", "backend-api"),
                    *("sh", "-c", script, "sh", *inside),
                ],
                "in the backend-api container",
            ),
        )
        for command, where in routes:
            try:
                # bounded (Operator revision, 2026-09-16): `docker compose exec` against an
                # unhealthy container blocks with no ceiling of its own
                done = subprocess.run(  # fixed argv, no shell
                    command,
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=DOCKER_TIMEOUT_SECONDS,
                )
            except OSError as error:
                refusals.append(f"{where}: {error}")
                continue
            except subprocess.TimeoutExpired:
                refusals.append(f"{where}: no answer within {DOCKER_TIMEOUT_SECONDS:.0f}s")
                continue
            if done.returncode == 0:
                return done.stdout
            refusals.append(f"{where}: {(done.stderr or done.stdout).strip()}")
        pytest.fail(f"no route to {what}: " + " | ".join(refusals))
