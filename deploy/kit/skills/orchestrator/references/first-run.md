# First run — prove the pipeline with one trivial story

The first Run against a freshly wired project should not be real work. It should be the
smallest story a coding agent can finish, so that what you are testing is the plumbing: the
clone, the branch, the dispatch into the harness, the agent's commit, the protected-path
check, the verify commands, the push and the compare link. One file is enough for that. When
this Run reaches `done` the pipeline is proven; when it parks, the park names the one piece
that is not.

This is the same idea as the instance's own harness readiness diagnostic
(`POST /api/v1/harnesses/{name}/readiness`), which runs a one-story fixture the instance
ships. That diagnostic proves the *harness*. This demo proves *this project*: your
repository, your commands, your token, your branch protection.

## Before the demo

All of the `orchestrator` skill's one-time setup, done and green:

1. Handshake passed (`GET /api/v1/version`).
2. Project and repository exist; `POST /api/v1/repositories/{id}/clone-check` is green.
3. The repository is BMAD-initialized: `_bmad/_config/manifest.yaml` exists on the base
   branch and names the instance's `bmad_version`. If not, run
   `POST /api/v1/repositories/{id}/init` first and merge the PR it opens; the dispatched
   agent reads the rendered skills out of `_bmad/`, and without them every story parks
   `misconfigured`.
4. The harness you will use is `enabled` in `GET /api/v1/harnesses`. If it is not, the
   instance's operator runs the readiness diagnostic (`orchestrator-admin`); do not try to
   prove a harness with a project Run.

## Pick the shape

The template follows the repository, not the other way round:

| The registered repository is… | Template | What the demo spec looks like |
| --- | --- | --- |
| a plain repository | `epic` at its latest version | one spec folder: `SPEC.md` + `stories.yaml` |
| a hub whose `repos/*` submodules are the members | `initiative-hub` at its latest version | an initiative folder: `epics.yaml` + one spec folder, the epic pointing at one member |

`epic` is not on the web UI's **New workflow** menu (the operator's `ROOT_TEMPLATES` names
what the menu offers) but it is a root template and `POST /api/v1/runs` accepts it. Read
its inputs from `GET /api/v1/templates/{name}/{version}` as for any template; the names
used below are the ones shipped today and may have moved.

## The files

The shape is `./spec-folder.md`'s, cut down to one capability and one story. Put
the folder somewhere obviously disposable: `demo/orchestrator-first-run/` at the repository
root (plain) or at the hub root (hub). Do **not** create a `stories/` folder — the dev loop
writes it, and a pre-authored story file halts the loop on every story.

`SPEC.md`:

```markdown
---
id: SPEC-orchestrator-first-run
companions: []
---

# Orchestrator first run

One capability, one story, no product change. The Run that executes this spec proves the
orchestrator can clone this repository, dispatch an agent into it, commit the agent's work,
run this repository's own verify commands, and push the branch.

## Capabilities

- **CAP-1** A file `ORCHESTRATOR-DEMO.md` exists at the repository root and contains the
  word `hello`.
  **success:** `test -f ORCHESTRATOR-DEMO.md && grep -q hello ORCHESTRATOR-DEMO.md` exits 0.
```

`stories.yaml`:

```yaml
- id: "1"
  title: Create ORCHESTRATOR-DEMO.md
  description: >
    Create ORCHESTRATOR-DEMO.md at the repository root containing the word hello, so
    SPEC.md's CAP-1 holds and `test -f ORCHESTRATOR-DEMO.md && grep -q hello
    ORCHESTRATOR-DEMO.md` exits 0. Change nothing else. Do not push: the orchestrator
    pushes the branch itself in a later step.
```

Hub shape only, `epics.yaml` beside the spec folder:

```yaml
- id: "1"
  title: Orchestrator first run
  branch: demo/orchestrator-first-run          # required by the list contract; hub runs use the Run's branch input
  spec_folder: first-run                       # bare name: demo/orchestrator-first-run/first-run/
  workdir: repos/<member>                      # the one submodule the file lands in
  install: "<the member's real install command, cd included — or omit>"
  test: "<the member's real test command, cd included — or omit>"
  done_checkpoint: true
```

In the hub shape the story's `description` should say *at the root of the member
repository* rather than *at the repository root*, since the agent is dispatched inside the
submodule and the spec stays at the hub.

**Verify commands are the repository's real ones, or none.** `epic` runs the repository's
registered `install_command` / `unit_test_command` / `quality_gate_command`; the hub epic
runs the `install` / `test` / `quality_gate` strings from `epics.yaml`. A command runs as
`baseline` *before* the story as well as after it, so a check for the demo file itself
(`test -f ORCHESTRATOR-DEMO.md`) fails the baseline and the Run with it. Leave the demo's
own check inside `SPEC.md`, where the agent reads it; let the commands be what they always
are. An omitted command plans `skipped · no command`, and `skipped` is a word on the
result, never a green.

## Where the files go

The planner reads the spec folder from the branch the Run is cut from. Commit the demo
folder on its own branch and push that branch; it becomes the Run's `base_branch`, so the
demo never touches the default branch:

```bash
git switch -c demo/orchestrator-first-run-spec
git add demo/orchestrator-first-run
git commit -m "chore: orchestrator first-run demo spec"
git push -u origin demo/orchestrator-first-run-spec
```

Since the branch was pushed, the clone the orchestrator holds sees it on its next sync.
The Run's own `branch` input is a second, fresh name, for example
`demo/orchestrator-first-run-<yyyymmdd>`: a name that already exists on the remote makes
preflight answer `conflict_consent_required: true`, and a demo should never need that
consent.

## Launch

The `orchestrator` skill's **Launching a Run** section applies in full. For the demo:

1. `GET /api/v1/templates`, then the chosen template's latest version — its `inputs` are
   the list to bind. Expect, for `epic`: `base_branch`, `branch`, `spec_folder`,
   `harness`, `model`, `done_checkpoint`; for `initiative-hub`: `base_branch`, `branch`,
   `initiative_folder`, `harness`, `model`, and the three time limits `build_timeout_min`,
   `build_stall_min`, `epic_timeout_min` (minutes; leave them blank to take the template's
   defaults, 180 / 90 / 60).
2. `POST /api/v1/runs/preflight` with everything you will send. Every `lines[]` entry must
   be `pass` or `skip`; read `rows[]` and confirm it shows exactly one story frame. A
   `plan_error` here names the spec file line at fault.
3. Ask the human for the three decisions the skill never makes alone: `harness`, `model`
   and `budget_usd`. One trivial story costs a small fraction of a real one; the number is
   still theirs. Say `done_checkpoint: "true"` if they want to look before the Run closes.
4. `POST /api/v1/runs` with exactly what was preflighted. Hand back the deep link
   `/workflows/{run_id}`.

## What you will see

`GET /api/v1/runs/{id}/detail` shows the rows in order. For `epic`:

| row | what proves what |
| --- | --- |
| `checkout` | the clone works and the branch was cut from `base_branch` |
| `setup`, `baseline` | the registered commands run in the worktree, or are `skipped · no command` |
| `spec-gate` | an agent was dispatched and read the spec; it writes `spec-gate-result.md` into the folder |
| `stories/1/build` | the agent created the file; `verify` is the registered test command again |
| `gen-e2e`, `e2e`, `retro` | the epic tail: an agent generates tests for the capability and a retrospective into the spec folder — on a one-file story these are small, and they are part of what a real epic does |
| `push` | the orchestrator pushed `branch` with its own credential |
| `link` | `compare_urls` on the Run holds the GitHub compare page |
| `done-checkpoint` | present only when you asked for it; `continue` closes the Run |

Supervise with `orchestrator-watch <run_id>` where it is installed (see
`../../initiative-run/SKILL.md`), or poll at 5 s / 30 s. Expected stops, and what each means:

- **`blocked`, the agent asking about git credentials or a push.** The agent tried to push.
  It must not: answer with the signal `answer` and text saying the orchestrator pushes, the
  agent only commits. If this recurs, the project's own instructions tell agents to push;
  fix them there.
- **`blocked`, a denied tool.** The instance's harness allowlist lacks the command; that is
  `orchestrator-admin`'s change, not an answer per story.
- **`protected_path`.** The agent touched a spec file, an `AGENTS.md`, or a file the
  repository's `test_globs` freeze. A demo story has no reason to; read the diff before any
  `continue`.
- **`verify_failed`.** The registered test command failed after the story. Either the
  command was never green on this branch (check `baseline`'s log) or the agent broke it.
- **`misconfigured`.** Usually the repository is not BMAD-initialized at the instance's
  version, or the spec folder path is wrong. The alert names which.
- **`checkpoint`.** The `done_checkpoint` you asked for. Look, then `continue`.

## Pipeline proven when

- the Run is `done` and `GET /api/v1/runs/{id}/detail` shows the story `done` with its
  verify row green or honestly `skipped · no command`;
- the branch exists on the remote and holds a commit authored by the orchestrator carrying
  `ORCHESTRATOR-DEMO.md` with `hello` in it;
- the compare link opens and shows exactly that change plus the spec folder's own
  additions (`stories/1-*.md`, `spec-gate-result.md`, the retro output, generated tests);
- `spent_usd` is under `budget_usd`.

Report those four lines to the human, with the deep link and the spend.

## Afterwards

Delete the two demo branches on the remote once the human has seen the compare page. Keep
or drop the `demo/` folder as they prefer; nothing else reads it. The Project and the
Repository stay: they are what every real Run uses next.
