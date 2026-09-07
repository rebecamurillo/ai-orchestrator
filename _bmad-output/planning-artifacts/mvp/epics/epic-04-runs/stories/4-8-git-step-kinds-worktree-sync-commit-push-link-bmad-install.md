---
status: done
story: "4-8"
epic: 4
title: Git step kinds worktree, sync, commit, push, link, bmad.install
warnings: []
---

# Story 4.8 — Git step kinds `git.worktree`, `git.sync`, `git.commit`, `git.push`, `pr.link`, `bmad.install`

As the Operator,
I want the git half of the dev loop to exist as six small executors over one `Git` port,
So that `repo-init@1` runs end to end and the epic loop's checkout, sync, commit-guard, push
and compare link are ready for the agent step.

## Code Map

- `backend-api/src/orchestrator/domain/ports/git.py` — the port's voice: three conventions in
  the module docstring (a failure is a `GitError`, "not there" is `None`/`False`, a path is a
  `Path` the caller composed). The ten new methods are appended and none of them narrows one
  that is there.
- `backend-api/src/orchestrator/infrastructure/git/subprocess_git.py` (310 lines) — the only
  module that starts a git process, and the AD-5 credential path (`GIT_ASKPASS`, a built
  environment, `-c credential.helper=`). It is already 310 lines, so the new commands land in
  `infrastructure/git/worktrees.py` as a mixin over the same `_run` / `_attempt`.
- `backend-api/src/orchestrator/application/steps/{shell,plan_check,checkpoint}.py` — the
  executor voice 4.7 set: module docstring states the kind's rules, `KIND` beside the class,
  `register(KIND, X())` at the foot, every reason string a module constant.
- `backend-api/src/orchestrator/application/steps/context.py` — `StepContext` (AD-9's own
  field list, closed), `StepPorts` (open, grows additively), `log_path`.
- `backend-api/src/orchestrator/application/use_cases/apply_step_result.py` — AD-8's
  execution writer; the only place a Run's own columns may be written from a `StepResult`.
- `backend-api/src/orchestrator/infrastructure/dbos/walker.py` — `WalkerDeps`, `_walk_ports`;
  `backend-api/src/orchestrator/infrastructure/dbos/startup.py` — `walker_deps`, the one
  place a kind module is imported so its `register(...)` runs.
- `backend-api/tests/unit/fakes/git.py` — the one `Git` fake: scripted answers, a call log,
  a clock that moves per command. Extended additively; no second double.
- `backend-api/tests/e2e/test_clone_check.py::Fixtures` — already makes a bare repository
  under `WORK_DIR/e2e-fixtures` reachable by `file://` from either topology.

## Design Notes

**D1 — Where the Repository's facts reach an executor (spine-first, brief overruled).**
The brief says `git.worktree` reads `with_resolved {base, branch}` and then uses
`repository.install_command`, `repository.default_branch` and the repository URL. Nothing in
`StepContext` carries them today, and neither of the two obvious routes is open:

- AD-9 fixes `StepContext` at `{row, with_resolved, cwd, frame_start_sha, previous_attempt,
  attempt, resume_signal, ports}`. A new field on it would contradict the spine.
- Putting them on the row's `with_resolved` at plan time would require editing
  `tests/unit/application/templates/test_plan_shipped.py::
  test_repo_init_checkout_substitutes_the_base_branch_and_the_literal_branch`, which asserts
  that row's `with_resolved` *equals* `{base, branch}` once `timeout_min` is removed. That is
  an existing test file and none of hard rule 1's three exceptions covers it.

`ports` is the field AD-9 leaves open ("executors are pure over ports"), and `StepPorts` is
this system's own object, documented as growing additively. So `StepPorts` gains
`run_env: RunEnvironment | None` — a frozen snapshot of the one Run's own facts (project and
repository slugs, URL, default branch, install command, the BMAD version this instance runs,
the Run's `spec_folder` input, and `run.worktrees`). **The executor does not fetch it:** the
walker's `attempt_row` step resolves it in `infrastructure/dbos/walker.py` before the
executor runs and hands it over inside `StepPorts`, so "executors never touch a repository"
holds literally. `walk.py` is untouched.

**D2 — `protected_paths` is a port, not yet a rule (spine + brief reconciled).** AD-17 puts
the rule in `application/rules/protected_paths.py` (Epic 5). The brief calls the seam
`ctx.ports.protected_paths`. Both are satisfied by declaring the *port* now
(`domain/ports/protected_paths.py`) and leaving `StepPorts.protected_paths = None` for this
epic: `git.commit` reads `()` hits when nothing is wired, and a fake returning hits proves
the `protected_path` park branch. Epic 5 lands the rule and wires it; no shipped code path
changes when it does.

**D3 — `StepResult.run_updates`.** AD-14 gives `git.worktree`, `git.push` and `pr.link`
writes to `run.worktree_path`, `run.worktrees[]` and `run.compare_urls[]`, and AD-8 says an
executor never writes. The result therefore carries a typed `RunUpdates` and
`apply_step_result` applies it through `set_run` in the same unit of work, before it routes —
so the very next row's `RunEnvironment` reads the committed value.

**D4 — the `Git` port's new methods.** AD-14 names `worktree_add`, `sync`, `status`,
`diff_names(from_sha)`, `commit`, `push`, `remove_worktree`, `delete_branch`; the brief adds
`head_sha`, and staging is split out as `stage` so the commit-guard's "`spec_folder` first,
then everything" is a call order a test can assert on the fake. `sync` answers `None` for
"no upstream" (AD-14 calls that a recorded no-op) and raises `GitError` for a non-fast-forward,
whose output is already redacted by the adapter (AD-5).

**D5 — the e2e local remote.** The brief asks for `tests/e2e/helpers/local_remote.py`.
`tests/e2e/test_clone_check.py::Fixtures` already creates a bare repository with `main` under
`WORK_DIR/e2e-fixtures`, registers it by `file://`, and works both in CI and under `make up`.
A second helper would be a second double; `test_repo_init.py` imports `Fixtures`.

**D6 — logs.** `application/` cannot write a file; `ProcessRunner` writes the row log and
`log_path(ctx)` names it. "log `reused worktree`" and "log `no install_command`" are therefore
a `structlog` line *and* `StepResult.reason`, which is the sentence the Operator reads on the
row — testable, and it is where the row's own words already live.

**D7 — a timed-out `install_command` or `bmad.install`.** The brief names only a non-zero
exit. `ProcessRunner.wait` reports a timeout separately and 4.7 already fixed what that means
(`park timeout`, reason `timeout {path} after {n} min`); both kinds follow `shell`, because a
command the runner killed never decided anything.

**D8 — AD-5 is unchanged by this story.** `GITHUB_TOKEN` is read in `infrastructure/settings.py`,
handed to `SubprocessGit.__init__` in `main.py`, and reaches git only through `GIT_ASKPASS` in
`command_environment`. The new commands run through the same `_run`, so they inherit that path
and the redaction with it. `install_command` and `bmad.install` go through `ProcessRunner`
with `env={}` — the Project's env vars are Epic 5's decryption work — so no child process of
this story ever sees a credential.

## Tasks & Acceptance

### Ports and values

- [x] `domain/ports/git.py`: add `worktree_add`, `sync`, `status`, `stage`, `commit`,
      `diff_names`, `push`, `head_sha`, `remove_worktree`, `delete_branch`.
- [x] `domain/ports/protected_paths.py`: `ProtectedPaths.check(changed, accepted) -> tuple[str, ...]`.
- [x] `domain/values.py`: `RunUpdates{worktree_path, worktrees, compare_urls}` and
      `StepResult.run_updates: RunUpdates | None = None`.
- [x] `application/steps/context.py`: `RunEnvironment`, `StepPorts.run_env`,
      `StepPorts.protected_paths`, `base_dir(env, work_dir)`, `worktree_path(env, work_dir, branch)`.

### Executors

- [x] `application/steps/git_worktree.py` — ensure base clone, reuse/refuse/create the
      worktree, `run_updates`, `install_command`.
- [x] `application/steps/git_sync.py` — fetch + ff-only, no upstream, diverged.
- [x] `application/steps/git_commit.py` — spec folder staged first, nothing staged, the
      protected-path seam, the commit.
- [x] `application/steps/git_push.py` — default-branch refusal, retry syncs first, `-u` on a
      created branch, rejection, `pushed: true`.
- [x] `application/steps/pr_link.py` — the two GitHub URL shapes, and any other host.
- [x] `application/steps/bmad_install.py` — `npx bmad-method@{version} install …`, the two
      `.gitignore` lines.
- [x] `infrastructure/dbos/startup.py` imports all six; `walker_deps` wires `run_environment`.

### Writers and wiring

- [x] `application/use_cases/apply_step_result.py` applies `result.run_updates`.
- [x] `infrastructure/git/worktrees.py` — the ten commands; `SubprocessGit` mixes them in.
- [x] `infrastructure/db/environment.py` — `read_run_environment(session_factory, bmad_version, run_id)`.
- [x] `infrastructure/dbos/walker.py` — `WalkerDeps.run_environment`, resolved in `attempt_row`.
- [x] `tests/unit/fakes/git.py` — the ten methods, additively.

### Acceptance criteria

1. **Given** a local bare origin with `main` and a Repository registered on it (no
   `chore/bmad-init`), **when** a `repo-init@1` Run executes on the real engine in the e2e
   stack, **then** rows `plan, checkout, install, commit, push, link` end `done` in order;
   `run.worktrees` has one entry with `created_branch: true, pushed: true`; the origin holds
   `chore/bmad-init` with a commit `chore: initialise BMAD method (orchestrator)` containing
   `_bmad/` and the two `.gitignore` lines and no `.claude/` or `.agents/` folder.
2. **Given** a `github.com` repository URL on the fake adapter, **when** `pr.link` runs,
   **then** `run.compare_urls` holds `https://github.com/{owner}/{repo}/compare/{default}...{branch}`;
   **and** a non-GitHub URL ends `done` with reason `no compare link for this host` and appends nothing.
3. **Given** an existing clean worktree for the branch, **when** `git.worktree` runs, **then**
   it is reused and the row reads `reused worktree`; **and** a dirty one parks `misconfigured`
   with `worktree dirty: {path}`.
4. **Given** a Repository with `install_command: "false"`, **when** `git.worktree` runs,
   **then** the row parks `misconfigured` with `install failed: exit 1` and `output_ref` is the row log.
5. **Given** a branch created by this Run and never pushed, **when** `git.sync` runs, **then**
   it ends `done` with reason `no upstream · no-op`.
6. **Given** a worktree with no changes, **when** `git.commit` runs, **then** it ends `done`
   with reason `no changes`; **and** with a change it stages `spec_folder` first and then
   everything, and commits the resolved message.
7. **Given** `git.push` with `branch == default_branch`, **when** executed, **then** it parks
   `push_rejected` with `push refused: main is the default branch` and no push command runs.
8. **Given** a push the remote rejects, **when** executed and then `retry` is signalled,
   **then** the first attempt parks `push_rejected` with the git output in `output_ref`, and
   the retry attempt syncs before it pushes.

## Verification

```bash
make lint && make test && make openapi && PATH="$HOME/.docker/bin:$PATH" make e2e
```

`make e2e-ui` is not run: no hand-written web-client file changes, and the operator's dev
stack holds 127.0.0.1:4321.

## Spec Change Log

- **D1 rewritten during planning.** The brief has `git.worktree` read `repository.install_command`
  off nothing in particular. `StepContext` is closed by AD-9 and the row's `with_resolved` is
  closed by an existing planner test, so the facts arrive through `StepPorts.run_env`, resolved
  by the walker. Recorded in Design Notes; no anchor was touched.
- **D2**: the brief's `ctx.ports.protected_paths` and the spine's `rules/protected_paths.py` are
  reconciled as "port now, rule in Epic 5".
- **D4 · `Git.sync`'s upstream question.** AD-14 words it as `rev-parse --abbrev-ref @{upstream}`
  failing. That is the *case* it means, not the command: `git worktree add -b {branch} …
  origin/{base}` sets the new branch's upstream to `origin/{base}`, so `@{upstream}` answers for
  exactly the branch that was never pushed and the fetch after it then fails on a ref the remote
  does not hold. `ls-remote --heads origin {branch}` asks the question the rule is about. Found by
  `tests/unit/test_subprocess_git_worktrees.py`, not by reading.
- **D5**: `tests/e2e/helpers/local_remote.py` was not created; `test_clone_check.py::Fixtures`
  already is that helper, in both topologies.
- **The base clone's `HEAD` is detached inside `worktree_add`.** AD-14 requires a detached `HEAD`
  "so any branch, the default one included, can be added as a worktree", and 4.3's `clone_base`
  leaves it symbolic on the default branch — `git worktree add … main` then refuses, because the
  base clone itself holds `main`. Fixed where the requirement is used rather than by editing
  `clone_base`, whose own tests pin its flags.

## Auto Run Result

Status: done
Blocking condition: none

Gates, all run against this commit:

- `make lint` — pass (ruff, mypy strict on `domain`+`application`, 4 import-linter contracts kept,
  env contract 27/33, test pairs 129/129, astro check, eslint, prettier, web test pairs 42/42).
- `make test` — pass. 3768 backend unit tests, 23 skipped; `domain` + `application` at **100 %
  branch coverage** (`--fail-under=100`); 722 web-client tests.
- `make openapi` — pass, no drift (`contracts/openapi.json` and `schema.d.ts` unchanged: this story
  adds no API surface).
- `make e2e` — pass. Built and destroyed its own stack; **130 tests passed**, 7 of them the new
  `tests/e2e/test_repo_init.py`.
- `make e2e-ui` — not run. No hand-written web-client file changed, and the operator's own dev
  stack holds `127.0.0.1:4321`.

**The headline acceptance holds.** `repo-init@1` runs `plan → checkout → install → commit → push
→ link`, every row `done`, against a local bare `file://` origin in the e2e stack:
`run.worktrees` carries one entry with `created_branch: true, pushed: true`, the origin holds
`chore/bmad-init` with the commit `chore: initialise BMAD method (orchestrator)` containing
`_bmad/` and the two `.gitignore` lines and no committed skill folder. `pr.link` records
`no compare link for this host` for the `file://` origin; the compare URL itself is asserted
against a `github.com` URL on the fake in `tests/unit/test_pr_link_executor.py`.

Deferred, for the next story:

- `Git.remove_worktree` and `Git.delete_branch` exist, are tested against real git, and are called
  by nothing yet — 4.9's `cancel` is their first caller (AD-13).
- `Git.diff_names` and `Git.head_sha` likewise: AD-17's protected-path rule (Epic 5) is their
  first caller, and `attempt.start_sha` / `end_sha` are still written by nobody.
- `StepPorts.protected_paths` is `None` throughout Epic 4; Epic 5 wires
  `application/rules/protected_paths.py` into it and changes no line of `steps/git_commit.py`.
- Project env vars still do not reach a child process (`env={}` in `git.worktree`'s install and in
  `bmad.install`); that is Epic 5's decryption work.
- The e2e suite is still not twice-runnable against one stack — `test_engine_walker.py` parks a Run
  nothing can release until 4.9's signals endpoint. `make e2e` builds its own stack, which is why
  the gate passes. This story's own Run is terminal and holds nothing.
