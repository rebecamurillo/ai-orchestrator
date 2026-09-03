---
story: "4-8"
epic: 4
title: Git step kinds worktree, sync, commit, push, link, bmad.install
requirements: [FR-9, FR-10 (sync, commit-guard), FR-11, FR-30, NFR-3, AR-12, AR-19, AR-21]
binds: [AD-5, AD-9, AD-14, AD-16, AD-17 (seam only)]
---

# Story 4.8 — Git step kinds `git.worktree`, `git.sync`, `git.commit`, `git.push`, `pr.link`, `bmad.install`

As the Operator,
I want the git half of the dev loop to exist as six small executors over one Git port,
So that `repo-init` runs end to end, and the epic loop's checkout, sync, commit-guard, push, and compare link are ready for the agent step.

## Scope

**In:** the rest of the `Git` port (`worktree_add`, `sync`, `status`, `diff_names`, `commit`, `push`, `remove_worktree`, `delete_branch`, `list_files`, `head_sha`) in the subprocess adapter and the fake; executors `application/steps/{git_worktree,git_sync,git_commit,git_push,pr_link,bmad_install}.py`; registry entries; a local-remote e2e test running `repo-init@1` to `done`.
**Out:** protected-path checks inside `git.commit` (Epic 5 fills the seam `ctx.ports.protected_paths`, a no-op rule here), the agent step.

## Binding rules (inlined)

- **Layout (AD-14).** Base clone `/work/{project.slug}/{repository.slug}/base` (blobless, detached HEAD); worktrees `/work/{project.slug}/{repository.slug}/wt/{branch}` (`/` in branch names becomes a directory level); logs as in 4.7. Every git command receives `GITHUB_TOKEN` through `GIT_ASKPASS` only (Epic 2's adapter); `git` runs with `-c credential.helper=` and `-c core.hooksPath=/dev/null` `[ASSUMPTION: repository hooks disabled during orchestrator git commands]`.
- **`git.worktree`** (`with_resolved {base, branch}`): ensure the base clone (`clone_base` when missing, else `fetch_base`); if `wt/{branch}` exists: `status --porcelain` empty → reuse (log `reused worktree`), else `StepResult(error, park Park{misconfigured, "worktree dirty: {path}"})` `[ASSUMPTION: dirty-worktree refusal uses the misconfigured park kind]`; if absent: `branch_exists(origin/{branch})` → `git worktree add wt/{branch} {branch}` tracking origin, `created_branch=false`; else `git worktree add -b {branch} wt/{branch} origin/{base}`, `created_branch=true`. Then append `{branch, path, created_branch, pushed: false}` to `run.worktrees[]` if absent and set `run.worktree_path` (through the `RunRepository` in the same unit of work the walker opened — the executor returns these in `StepResult.run_updates` `[ASSUMPTION: StepResult gains an optional run_updates map applied by apply_step_result]`). If `repository.install_command` is set: run it in the worktree through `ProcessRunner` with the Project env under the row's `timeout_min`, output into the row log; non-zero → `error`, park `Park{misconfigured, "install failed: exit {code}"}`; absent → log `no install_command`. Gate `deterministic`.
- **`git.sync`**: `git fetch origin {branch}` + `git pull --ff-only`; no upstream (`rev-parse --abbrev-ref @{upstream}` fails) → `done` with reason `no upstream · no-op`; non-fast-forward → `error`, park `Park{push_rejected, "sync: branch diverged"}` with the git output; `retry` re-runs it whole.
- **`git.commit`** (commit-guard): `git add -A -- {spec_folder}` when the Run has one, then `git add -A`; nothing staged → `done`, reason `no changes`; else commit with `with_resolved.message` (`story {id}: {title} (orchestrator)` or, after `skip_story`, `story {id}: skipped by operator`) as author `orchestrator <orchestrator@local>`; before committing call `ctx.ports.protected_paths.check(...)` (a no-op returning no hits until Epic 5); a hit → `error`, park `protected_path`. Gate `deterministic`.
- **`git.push`**: refuse when `branch == repository.default_branch` → `error`, park `Park{push_rejected, "push refused: {branch} is the default branch"}`; `git push origin {branch}` (`-u` when `created_branch`); rejection → `error`, park `Park{push_rejected, "push rejected"}` with the git output; success → `done`, set `pushed: true` on the matching `run.worktrees[]` entry (via `run_updates`). Never `--force`.
- **`pr.link`**: compare URL from the repository URL — for `https://github.com/{owner}/{repo}(.git)` or `git@github.com:{owner}/{repo}(.git)` → `https://github.com/{owner}/{repo}/compare/{default_branch}...{branch}`; append to `run.compare_urls[]`; a non-GitHub URL → `done` with reason `no compare link for this host` and no append. Gate `liveness`.
- **`bmad.install`**: run `npx --yes bmad-method@{bmad_version} install --yes --modules bmm --tools claude-code,codex,opencode --directory {worktree}` `[flags to be re-verified against bmad-method 6.11.0 at implementation and recorded in addendum §B]` through `ProcessRunner` (timeout 30 min), then ensure `.gitignore` in the worktree contains the lines `.claude/skills/bmad-*` and `.agents/skills/bmad-*` (append if missing); non-zero → `error`, park `Park{misconfigured, "bmad install failed: exit {code}"}`. Gate `deterministic`. Skill folders are never committed: the following `git.commit` sees them ignored.
- **Retry effects (AD-13):** a `retry` on a `push_rejected` park runs `git.sync` logic first (fetch + ff-only) then the push; the executor reads `ctx.resume_signal`.

## Acceptance criteria

**Given** a local bare "origin" with `main` and a Repository registered on it (no `chore/bmad-init` branch)
**When** a `repo-init@1` Run executes on the real engine in the e2e stack
**Then** rows `plan, checkout, install, commit, push, link` end `done` in order; `run.worktrees` has one entry with `created_branch: true, pushed: true`; the origin has `chore/bmad-init` with a commit `chore: initialise BMAD method (orchestrator)` containing `_bmad/` and the two `.gitignore` lines and no `.claude/` or `.agents/` folders; `run.compare_urls` holds the compare URL when the URL is a GitHub one (asserted with a `github.com` URL on the fake adapter in unit tests).

**Given** an existing clean worktree for the branch
**When** `git.worktree` runs
**Then** it is reused and the log says `reused worktree`; **and** a dirty one parks `misconfigured` with `worktree dirty: {path}`.

**Given** a Repository with `install_command: "false"`
**When** `git.worktree` runs
**Then** the row parks `misconfigured` with `install failed: exit 1` and the output is in the row log.

**Given** a branch created by this Run and never pushed
**When** `git.sync` runs
**Then** it records `no upstream · no-op` and ends `done`.

**Given** a worktree with no changes
**When** `git.commit` runs
**Then** it ends `done` with reason `no changes`; **and** with an untracked file it commits with the resolved message and `spec_folder` staged first (unit test on the fake asserting call order).

**Given** `git.push` with `branch == default_branch`
**When** executed
**Then** it parks `push_rejected` with `push refused: main is the default branch` and no push command runs.

**Given** a push rejected by the remote (non-fast-forward)
**When** executed, then `retry` is signalled
**Then** the first attempt parks `push_rejected` with the git output; the retry attempt fetches and fast-forwards first, then pushes.

## Implementation notes

- Extend `infrastructure/git/subprocess_git.py`; every method returns the combined output for logs; errors carry redacted output.
- `StepResult.run_updates: dict` (worktrees, worktree_path, compare_urls) applied by `apply_step_result` in the same unit of work — a small edit in 4.5's module, with a test.
- e2e helper: `tests/e2e/helpers/local_remote.py` creates the bare repo under a fixtures volume reachable from the backend container by `file://` path.

## Verification

```bash
make lint && make test && make up && make e2e-api
```

## Sources for detail only

PRD FR-9, FR-10 (sync, commit-guard), FR-11, FR-30, FR-20 (retry). Spine AD-14 (layout, reuse rule, `install_command`), AD-16 (`bmad.install`, gitignore), AD-13 (retry syncs first), conventions "Commits & branches". `scripts/harness/_common.sh` for the `bmad-method` install command shape.
