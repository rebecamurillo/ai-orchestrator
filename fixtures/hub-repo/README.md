# hub-repo fixture

The hub repository `tests/e2e/test_hub_run.py` drives an `initiative-hub@1` Run against
(story H5). It is the multi-repo sibling of `fixtures/gates-repo/`: a hub whose
`.gitmodules` declares two member submodules, `repos/alpha` and `repos/beta`, each its own
bare origin with a trivially runnable gate command.

## Layout

- `initiatives/demo/epics.yaml` — the two epics this Run walks, in order: `alpha-epic`
  (`repos/alpha`, no `install` — proves the `skipped · no command` row) and `beta-epic`
  (`repos/beta`, `install` declared). `alpha-epic` alone carries `done_checkpoint: true`, so
  the Run parks after it and a `continue` is what lets `beta-epic` start.
- `initiatives/demo/{alpha-epic,beta-epic}/` — each epic's own `SPEC.md`, `stories.yaml`
  (one Story), and `stories/` (the scripted harness writes the Story file there).
- `.fake-harness/attempt-{1,2,3,4}.yaml` — the epic tail's own dispatches (`spec-gate`,
  `retro`), read in order: no story id, so they share one counter, keyed by the hub
  worktree alone. 1 and 2 are `alpha-epic`'s `spec-gate`/`retro`; 3 and 4 are
  `beta-epic`'s.
- `members/alpha/`, `members/beta/` — each member's own seed: a `README.md`, `check.sh` (the
  epic's `test`/`quality_gate` command), `GATE_OK`, and its own `.fake-harness/` — a `1/`
  scenario for the Story `build` row (dispatched inside the submodule) and a root
  `attempt-1.yaml` for `gen-e2e` (also dispatched inside the submodule, but under no story
  id, so it is a separate counter from the Story's).
- `members/alpha/tests/smoke.test.sh` — committed in the seed so it exists at the Story
  frame's first attempt and is therefore one of AD-17's frozen test files;
  `members/alpha/.fake-harness/1/attempt-1.protected.yaml` is the *alternate* Story-1
  scenario `tests/e2e/helpers/hub_fixture.py` swaps in for the protected-path case: it
  edits `tests/smoke.test.sh` instead of leaving it alone, so `commit-guard` parks
  `protected_path` naming `repos/alpha/tests/smoke.test.sh`. It is never read by the `fake`
  harness under its own name — only the fixture script copies it over the real
  `attempt-1.yaml` when asked to.

Nothing here is edited by hand between runs: `tests/e2e/helpers/hub_fixture.py` copies this
directory (and `members/alpha`, `members/beta` as their own repositories) into a scratch
tree, wires `repos/alpha` and `repos/beta` up as real submodules of freshly made bare origins,
writes a `_bmad/_config/manifest.yaml` stating the instance's own `BMAD_VERSION` at the hub,
and pushes the result. This directory is never edited in place.

## Why `file://` submodules work here at all

`git submodule update --init` refuses the `file` transport for the clones it starts
(CVE-2022-39253), and the adapter (`infrastructure/git/subprocess_git.py`) deliberately never
relaxes that for a real deployment. The disposable e2e stack's `docker-compose.e2e.yml` sets
`GIT_ALLOW_PROTOCOL=file` on the `backend-api` container alone, which
`SubprocessGit.command_environment` mirrors into every git command it runs — see that
module's own note. This fixture's own `git submodule add`, used to wire `repos/alpha` and
`repos/beta` up in the first place, sets the same variable for its own process only, the way
`tests/unit/test_subprocess_git_submodules.py`'s `run_git` helper already does.
