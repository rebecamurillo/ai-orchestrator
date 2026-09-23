"""`fixtures/hub-repo/` as a hub-Run initiative: a hub whose `.gitmodules` declares two
member submodules, each its own bare origin (story H5, SPEC CAP-9, the hub-Run workflow).

The multi-repo sibling of `gates_fixture.py`, reusing its two-topology `_either` (host
process, else `docker compose exec`) and its `show`/`tree` reads — neither depends on the
gates shape, so `HubFixture` subclasses `GatesFixture` for them rather than duplicating the
routing. What it adds is its own `make_hub`, because a hub-Run fixture is three bare origins
wired together, not one.

**Why `file://` submodules work here at all.** `git submodule update --init` refuses the
`file` transport for the clones it starts (CVE-2022-39253) even though a direct `git clone
file://…` — what `clone_base`/`fetch_base` already do for the hub itself, and what every
other e2e fixture in this suite relies on — is always allowed; a *submodule's* clone is
treated as automatic, subordinate traffic, regardless of whether it was `git submodule add`
or `git submodule update --init` that started it, and CVE-2022-39253 turns that off by
default. Two different processes need it relaxed for two different reasons, and each gets it
the narrowest way:

- **This fixture's own `git submodule add`**, used below to wire `repos/alpha` and
  `repos/beta` up against freshly made bare origins, sets `GIT_ALLOW_PROTOCOL=file` on its
  own process only — the same thing `tests/unit/test_subprocess_git_submodules.py`'s
  `run_git` helper already does for its own fixture-building `submodule add`. That is a
  test process's own choice about its own git calls and touches nothing this suite ships.
- **The backend's own `git submodule update --init`**, run when a Run's `git.submodule` row
  executes, is a different process — `infrastructure/git/subprocess_git.py::SubprocessGit`
  — that builds its command environment from scratch and does not read this test's env at
  all (AD-5's whole point). What it *does* read is `GIT_ALLOW_PROTOCOL` out of the backend
  process's own environment, exactly the way `command_environment` already mirrors `PATH` —
  and `docker-compose.e2e.yml` is the only place that variable is ever set on `backend-api`.
  Production's `docker-compose.yml` and every real deployment's `.env` never set it, so a
  real Operator's instance keeps the CVE guard exactly as git ships it; this fixture is what
  the e2e-only relaxation exists for, not something that could reach a production Run.

A single call to a `.gitconfig` written into the *adapter's own* private `HOME` — the route
`test_subprocess_git_submodules.py` uses — was considered and ruled out for e2e: that `HOME`
is a `tempfile.mkdtemp()` the backend process creates for itself at start-up and this test
has no path to it from outside the container, whereas an environment variable on the
container is a route both topologies already share (AD-5's own build-not-inherit rule is
exactly what makes the *adapter's* `HOME` unreachable, and exactly what makes its own
environment the one seam this fixture can still reach into).

**The `poison_alpha` variant.** `members/alpha/.fake-harness/1/attempt-1.protected.yaml`
finishes Story 1 the same way the real scenario does, but edits
`members/alpha/tests/smoke.test.sh` — committed in the seed, so it is one of AD-17's frozen
test files by the time the Story's `build` row first dispatches — instead of leaving it
alone. `make_hub(poison_alpha=True)` copies that file over the real `attempt-1.yaml` at
materialisation time, for a Run whose journey is the protected-path park rather than the
happy path.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from tests.e2e.helpers.gates_fixture import REPO_ROOT, GatesFixture

#: The fixture's source, per topology — `backend-api/Dockerfile` copies the whole `fixtures/`
#: directory, the same way `gates_fixture.py`'s own `SOURCE_HERE`/`SOURCE_IN_CONTAINER` do.
SOURCE_HERE = str(REPO_ROOT / "fixtures" / "hub-repo")
SOURCE_IN_CONTAINER = "/app/fixtures/hub-repo"

#: The one file `make_hub(poison_alpha=True)` swaps in for the real Story-1 scenario.
POISON_SOURCE = "members/alpha/.fake-harness/1/attempt-1.protected.yaml"


@dataclass(frozen=True)
class HubRepos:
    """The three bare origins one `make_hub()` call materialises, by their `file://` URLs."""

    hub: str
    alpha: str
    beta: str


#: One script, run either here or inside the container: `$1` the directory, `$2` this call's
#: own name (so two calls in one test run never collide), `$3` the fixture's source, `$4` the
#: `BMAD_VERSION` the hub's manifest states, `$5` `1` to swap in the poisoned Story-1
#: scenario before the alpha seed is committed, else `0`.
MAKE_HUB_ORIGIN = """
set -e
dir="$1"; name="$2"; source="$3"; version="$4"; poison="$5"
mkdir -p "$dir"
rm -rf "$dir/$name-hub.git" "$dir/$name-hub.seed"
rm -rf "$dir/$name-alpha.git" "$dir/$name-alpha.seed"
rm -rf "$dir/$name-beta.git" "$dir/$name-beta.seed"

# This process's own git calls only (see the module docstring): the fixture's `submodule
# add` below is refused the `file` transport otherwise, the same CVE-2022-39253 guard
# `test_subprocess_git_submodules.py`'s own `run_git` helper works around for its own fixture
# repository, and for the same reason — building a fixture, never a Run.
GIT_ALLOW_PROTOCOL=file
export GIT_ALLOW_PROTOCOL

seed_member () {
  member_name="$1"
  git init --quiet --bare --initial-branch=main "$dir/$name-$member_name.git"
  cp -R "$source/members/$member_name" "$dir/$name-$member_name.seed"
  if [ "$member_name" = "alpha" ] && [ "$poison" = "1" ]; then
    cp "$source/POISON_SOURCE_PLACEHOLDER" \
      "$dir/$name-$member_name.seed/.fake-harness/1/attempt-1.yaml"
  fi
  ( cd "$dir/$name-$member_name.seed" \
    && git init --quiet --initial-branch=main \
    && git config user.email e2e@example.invalid \
    && git config user.name e2e \
    && git add --all \
    && git commit --quiet --message "$member_name member: seed" \
    && git push --quiet "$dir/$name-$member_name.git" main:main )
  git --git-dir="$dir/$name-$member_name.git" symbolic-ref HEAD refs/heads/main
}

seed_member alpha
seed_member beta

git init --quiet --bare --initial-branch=main "$dir/$name-hub.git"
mkdir -p "$dir/$name-hub.seed"
cp -R "$source/." "$dir/$name-hub.seed/"
rm -rf "$dir/$name-hub.seed/members"
mkdir -p "$dir/$name-hub.seed/_bmad/_config"
printf 'installation:\\n  version: %s\\n  installDate: 2026-09-09\\nmodules: []\\n' \\
  "$version" > "$dir/$name-hub.seed/_bmad/_config/manifest.yaml"
cd "$dir/$name-hub.seed"
git init --quiet --initial-branch=main
git config user.email e2e@example.invalid
git config user.name e2e
git add --all
git commit --quiet --message "hub: seed"
git submodule --quiet add "file://$dir/$name-alpha.git" repos/alpha
git submodule --quiet add "file://$dir/$name-beta.git" repos/beta
git commit --quiet --message "hub: add member submodules"
git push --quiet "$dir/$name-hub.git" main:main
git --git-dir="$dir/$name-hub.git" symbolic-ref HEAD refs/heads/main
""".replace("POISON_SOURCE_PLACEHOLDER", POISON_SOURCE)

#: One gitlink entry at a ref, raw: `$1` a repository (bare or a worktree), `$2` the ref,
#: `$3` the gitlink's own path. `ls-tree` needs no working tree, so the bare origin itself is
#: as good a `-C` target as a checkout of it — the same fact `GatesFixture.show`/`tree`
#: already lean on for every read this suite does against a pushed branch rather than a
#: worktree.
GITLINK_AT_REF = """
set -e
git -C "$1" ls-tree "$2" -- "$3"
"""

#: How many whitespace-separated fields one `ls-tree` line carries before the tab-separated
#: path: `{mode} {type} {sha}`.
LS_TREE_FIELDS = 3

#: One branch's whole commit history, subject only: `$1` a repository, `$2` the ref.
#: Diagnostic-only (kept beside `show`/`tree` because it leans on the same bare-repo-as-
#: `-C`-target fact): a failing assertion prints this to say what *is* on a branch rather
#: than only that one file is not.
LOG_AT_REF = """
set -e
git -C "$1" log --oneline "$2"
"""


class HubFixture(GatesFixture):
    """Makes the hub-Run fixture's three origins, and reads any of their branches back."""

    def log(self, repository: str, ref: str) -> str:
        """`git log --oneline` at `ref`, diagnostic — what commits actually landed."""
        arguments = [repository, ref]
        return self._either(LOG_AT_REF, arguments, arguments, f"read the log at {ref}")

    def gitlink_sha(self, repository: str, ref: str, path: str) -> str:
        """The commit sha a gitlink (a submodule pointer, git mode `160000`) records at
        `ref`, or `""` when `path` names no gitlink there — read straight off `ls-tree`'s own
        `{mode} {type} {sha}\\t{path}` line rather than through any working tree."""
        arguments = [repository, ref, path]
        what = f"read the {path} gitlink at {ref}"
        fields = self._either(GITLINK_AT_REF, arguments, arguments, what).split()
        return fields[2] if len(fields) >= LS_TREE_FIELDS else ""

    def make_hub(self, *, poison_alpha: bool = False) -> HubRepos:
        """A fresh hub + two fresh member bare origins, wired together as submodules.

        `poison_alpha`: swap `members/alpha`'s Story-1 scenario for the variant that edits a
        frozen test file, for a Run whose journey is the protected-path park.
        """
        name = f"hub-{uuid4()}"
        poison = "1" if poison_alpha else "0"
        here = [str(self.directory), name, SOURCE_HERE, self.bmad_version, poison]
        inside = [str(self.directory), name, SOURCE_IN_CONTAINER, self.bmad_version, poison]
        self._either(MAKE_HUB_ORIGIN, here, inside, "create the hub fixture")
        return HubRepos(
            hub=self.url(f"{name}-hub"),
            alpha=self.url(f"{name}-alpha"),
            beta=self.url(f"{name}-beta"),
        )
