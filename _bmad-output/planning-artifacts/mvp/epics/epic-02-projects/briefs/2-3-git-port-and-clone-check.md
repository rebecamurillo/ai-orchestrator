---
story: "2-3"
epic: 2
title: Git port, base clone layout, and the Clone check
requirements: [FR-4, FR-30 (method version cell), NFR-3, AR-7, AR-19, AR-21]
binds: [AD-2, AD-5, AD-14, AD-16, AD-18]
---

# Story 2.3 — Git port, base clone layout, and the Clone check

As the Operator,
I want every Repository checked when I save the Project and on demand: can the instance token reach it, does the default branch exist, which method version does it carry,
So that credential and URL problems surface at configuration time instead of hours into a Run (SM-5).

## Scope

**In:** `domain/ports/git.py` (the subset needed now), `infrastructure/git/` subprocess adapter with `GIT_ASKPASS`, the `/work/{project.slug}/{repository.slug}/base` layout, `use_cases/projects.run_clone_check`, running it for every Repository on Project create/update and on `POST /api/v1/repositories/{id}/clone-check`, `tests/unit/fakes/git.py`, an e2e test against a local bare repository.
**Out:** worktrees, sync, commit, push (Epic 4); the daily re-check job (Epic 4); UI (2.4, 2.5).

## Binding rules (inlined)

- **Port (AD-14).** `Git` protocol in `domain/ports/git.py` with, for this story: `ls_remote(url, ref) -> RemoteRef | None`, `clone_base(url, dest) -> CloneResult{seconds, bytes}`, `fetch_base(dest, branch) -> None`, `branch_exists(dest, branch) -> bool`, `read_file(dest, ref, path) -> str | None`. Later stories add the rest; keep the protocol open for extension. Every method raises `GitError{command, exit_code, output}` on failure with the verbatim combined output (token redacted, see below).
- **Token per command (AD-5).** The adapter passes `GITHUB_TOKEN` through `GIT_ASKPASS` pointing at a tiny script that prints the token from an environment variable set only for that subprocess, together with `GIT_TERMINAL_PROMPT=0`. The token is never written into the URL, the git config, a file under `/work`, or a log line; the adapter redacts the token value from any output before raising. `git` runs with `-c credential.helper=` to disable stored helpers.
- **Base clone layout.** `/work/{project.slug}/{repository.slug}/base` `[ASSUMPTION: slug paths]`; `WORK_DIR` from settings. The base clone is `git clone --no-checkout --filter=blob:none <url> base` (blobless partial clone, so any branch can be added as a worktree later; this satisfies the PRD's "shallow clone" line) `[ASSUMPTION: blobless partial clone instead of --depth 1]`, HEAD detached at `origin/{default_branch}` after fetch. When `base` already exists the check runs `fetch_base` instead of cloning.
- **Checks, in order, each its own line** `{name, status: ok | failed, seconds, output}`: (1) `ls-remote` — `git ls-remote --heads <url>` succeeds; (2) `clone` — base clone or fetch succeeds (size and seconds recorded); (3) `default branch` — `refs/heads/{default_branch}` present in the ls-remote output; (4) `method version` — `read_file(base, "origin/{default_branch}", "_bmad/_config/manifest.yaml")`, parse `installation.version`; result `bmad_version` = that version when equal to `settings.BMAD_VERSION`, `outdated` when different, `missing` when the file is absent. Line 4 is informational: it never sets `status: failed`. The check stops at the first failed line among 1–3.
- **Result ownership (AD-14).** `repository.clone_check = {status, at, output, bmad_version, lines[]}` is written only by `run_clone_check`; `status` is `failed` when any of lines 1–3 failed, else `ok`; `output` is the verbatim output of the failed command, else empty. A failing check never blocks the Project save (the save use case runs the checks after committing the Project and Repositories, then commits the results).
- **Fix hint (FR-4, UX-DR13).** The use case derives `hint` from the output: output containing `Authentication failed` or `could not read Username` → `the instance's GitHub token has no access to this repository`; `Repository not found` → `repository not found: check the URL`; default branch line failed → `branch {default_branch} does not exist on origin`; otherwise empty.
- **Layering (AD-2).** No `subprocess`, `os`, `shutil` outside `infrastructure/git/`; the use case receives `Git`, `Clock`, `Settings`-derived values (`work_dir`, `bmad_version`) through its arguments.
- **Timeouts.** Each git command runs with a 120 s timeout; expiry is a failed line with output `timeout after 120 s`.

## Acceptance criteria

**Given** a Project saved with two Repositories, one reachable and one whose URL does not exist
**When** the save completes
**Then** the first Repository reads `clone_check.status: ok` with four lines and `bmad_version` set, the second reads `failed` with line 1 failed, the verbatim git output, and a non-empty `hint`; the Project and both Repositories are stored.

**Given** a Repository whose default branch is missing on origin
**When** `POST /api/v1/repositories/{id}/clone-check` runs
**Then** lines 1 and 2 are `ok`, line 3 is `failed` with `hint: branch … does not exist on origin`, `status: failed`.

**Given** a repository with `_bmad/_config/manifest.yaml` at `installation.version: 6.11.0` and `BMAD_VERSION=6.11.0`
**When** checked
**Then** `bmad_version` is `6.11.0`; with `BMAD_VERSION=6.12.0` it is `outdated`; without the file it is `missing`; `status` is `ok` in all three cases.

**Given** any git command run by the adapter
**When** the process environment and the filesystem under `/work` are inspected during and after the check
**Then** `GITHUB_TOKEN` appears in no file, no git config, no URL, and no log line; a failing command's stored output has the token value replaced by `***` if it ever appears.

**Given** `base` already exists from a previous check
**When** the check runs again
**Then** it fetches instead of cloning and line 2 says `fetched` with the seconds.

**Given** the unit suite
**When** run
**Then** the use case is covered on the fake `Git` for every branch above (ok, each failing line, each `bmad_version` value, existing base) without a network.

**Given** the e2e suite
**When** run
**Then** it creates a local bare repository with a `_bmad/_config/manifest.yaml` on `main`, registers it by `file://` URL, and gets `ok` with the version; a second registration with a wrong URL gets `failed`.

## Implementation notes

- `infrastructure/git/subprocess_git.py` (the adapter), `infrastructure/git/askpass.sh` (installed with the package), `infrastructure/git/redact.py`.
- `domain/ports/git.py` dataclasses `RemoteRef`, `CloneResult`, `GitError`.
- `application/use_cases/projects.py`: `run_clone_check(repository_id, *, git, clock, work_dir, bmad_version, repos, uow) -> CloneCheck`; `save_project` calls it for each Repository after commit.
- Router: `POST /api/v1/repositories/{id}/clone-check` → 200 with the Repository read model.
- `tests/unit/fakes/git.py`: scripted responses per method, records calls; `tests/e2e/test_clone_check.py` uses `tmp_path`-created bare repos reachable from the backend (the e2e job mounts a fixtures directory or creates the bare repo through a helper endpoint guarded to test mode `[ASSUMPTION: a `file://` fixture is acceptable for e2e]`).

## Verification

```bash
make lint && make test && make openapi && make e2e-api
```

## Sources for detail only

PRD FR-4, FR-30 (row method cell), NFR-3, SM-5. Spine AD-5, AD-14, AD-16, Structural Seed (`/work` layout). `_bmad/_config/manifest.yaml` format: `installation.version`.
