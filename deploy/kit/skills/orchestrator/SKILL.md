---
name: orchestrator
description: Drive an ai-orchestrator instance over its HTTP API — create projects, register repositories, run the first-run demo that proves the pipeline on one trivial story, launch BMAD workflow runs (story, epic, initiative, repo-init), monitor progress, and respond to checkpoints and blocked runs, and customize the workflow templates to the project's needs. Use when the user asks to run a workflow, dispatch a story or epic to the orchestrator, test or demo the orchestrator on this project, run a smoke test or a first run, check on a run, wire this project into the orchestrator, or change, add or adapt a workflow or one of its steps.
---

# ai-orchestrator client

The orchestrator runs BMAD dev-loop workflows against git repositories: a Run plans every
step up front, dispatches stories to a coding-agent harness (claude, codex, opencode),
verifies with the target repository's own commands, and stops only at declared checkpoints
or when an agent is blocked. You talk to it over HTTP; humans watch the same Runs in its
web UI.

`references/api.md` in this skill is the endpoint reference — read it when you need exact
request fields. `references/spec-folder.md` is the format of the files epic and
initiative Runs read from the target repository (`epics.yaml`, `stories.yaml`,
`SPEC.md`) — **read it before authoring or reviewing those files: there are two
initiative flavors and each reads different `epics.yaml` fields.**
`references/workflows.md` is how to customize a workflow template — read it before
editing or authoring one. `references/project-fields.md` is what every Project and
Repository field does and what to confirm with the user before saving one.
`references/first-run.md` is the demo: one trivial story that
proves the whole pipeline on a freshly wired project — run it before the first real Run.
This file is the protocol — the order things happen in and the rules that keep you from
fighting the machine.

## Connection

Two values, from the project's environment (`.env` or exported):

- `ORCHESTRATOR_BASE_URL` — default `http://127.0.0.1:8000`
- `ORCHESTRATOR_TOKEN` — the single bearer credential

Every call: `Authorization: Bearer $ORCHESTRATOR_TOKEN`. The handshake below is what proves
the pair; `GET /api/v1/ping` proves the token alone and is the fallback for an instance
older than `/api/v1/version`.

`GET /healthz` needs no token (liveness only). Errors are RFC 9457
`application/problem+json`: `{type, title, status, detail, errors[]}` — read `detail` and
`errors[]` before retrying anything. Lists are `{items, next_cursor}`. Ids are UUIDs;
money is a decimal string in USD.

The web UI lives on the same host (default port 4321). The deep link for one Run is
`/workflows/{run_id}` — hand it to the user whenever you name a Run.

## Handshake

**Do this before anything else, every session.** This skill was copied out of one
instance; against a different version it describes an API that is not there.

1. Read `.orchestrator/kit.json` at the project root if it exists — `{kit_version,
   base_url, installed_at, harness}`. It is the version of this copy.
2. `GET /api/v1/version` → `{app_version, kit_version, bmad_version, harness_versions{}}`.
   A 404 means an instance older than the route: fall back to `GET /api/v1/ping`, say so,
   and treat the version as unknown.
3. If `app_version` differs from `kit.json`'s `kit_version`, the kit is stale. Tell the
   user exactly that, print the one line that replaces it, and **stop** — do not call
   anything else against a mismatched instance:

   ```bash
   curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
     "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness <harness>
   ```

   `<harness>` is `kit.json`'s `harness` (`claude`, `codex`, `opencode` or `all`).

`bmad_version` is the BMAD release installed in the instance's harnesses (AD-16). The
orchestrator does not compare it with any repository: preflight has no method-version line.
A BMAD skill renders from the target's own `_bmad/`, so a repository whose manifest names
another version, or none, may render a different workflow than the one you authored for.

## One-time setup: project and repository

**Confirm the fields with the user before the first save.** These settings decide what an
unattended Run may do and what stops it. Walk `references/project-fields.md` with the user
field by field, and before saving say back in one sentence what their `test_globs` choice
means for stops and what a story Run does on its own with these commands. The same walk
applies to a later `PUT`: a change reaches only Runs planned after it.

1. **Project** — `POST /api/v1/projects` with `{name, context_text, context_paths,
   env_vars}`. `context_text`/`context_paths` are what dispatched agents get told about
   the project; `env_vars` are encrypted and injected into harness runs.
2. **Repository** — `POST /api/v1/projects/{project_id}/repositories` with `{url,
   default_branch, install_command, quality_gate_command, unit_test_command, test_globs,
   package_manager}`. There are no per-repository credentials: the orchestrator clones
   with its own instance-wide `GITHUB_TOKEN`, so the URL must be reachable by that token.
   `test_globs` is exactly the list sent — empty freezes no file for the agent; the four
   anchors (`SPEC.md`, `stories.yaml`, `epics.yaml`, `AGENTS.md`) are frozen regardless.
3. **Clone check** — `POST /api/v1/repositories/{id}/clone-check` proves the URL and
   token resolve and creates the base clone. Do not proceed past a failing clone check;
   its `clone_check_lines` and `clone_check_hint` say what to fix.
4. **First time only** — if the target repository has never been BMAD-initialized,
   `POST /api/v1/repositories/{id}/init` starts a `repo-init` Run that bootstraps it as a
   PR. That is a normal Run from there: monitor it like any other.

Projects and repositories are reused across Runs — look before creating:
`GET /api/v1/projects` and `GET /api/v1/projects/{id}` (repositories embedded).

## First run: the demo

Once the setup above is green, prove the pipeline before spending a real budget on it.
`references/first-run.md` is the procedure: a disposable spec folder with one capability
and one story — create `ORCHESTRATOR-DEMO.md` containing `hello` — committed on its own
branch, launched on the `epic` template (plain repository) or `initiative-hub` (hub with
submodules), and watched to `done`. It exercises the clone, the dispatch into the harness,
the agent's commit, the protected-path check, the registered verify commands, the push and
the compare link, with no product change in the way.

- Run it when the user says to test, demo or smoke-test the orchestrator on this project,
  and offer it when a project is wired for the first time.
- It is a normal Run: preflight first, the human sets harness, model and budget, and every
  park is handled by the rules below. A park on the demo is a finding about the setup, not
  about the demo — report what it names.
- The instance's own `POST /api/v1/harnesses/{name}/readiness` is a different check: it
  proves a harness on a fixture the instance ships, not this project.

## Launching a Run

Never guess a template's inputs and never skip preflight.

1. **Discover templates** — `GET /api/v1/templates`, then
   `GET /api/v1/templates/{name}/{version}`: the response's `inputs` is the authoritative
   list of what this template takes. Shipped templates come in two families — `staged-*`
   (three agent sessions per story: plan, implement, review, each on its own model) and
   the build-auto family (`initiative-hub` and its callees, one session per story), plus
   `repo-init`, `agent-smoke`, and the single-repository `epic`/`story` kept for harness
   readiness. They evolve; read them, don't memorize them.
   - **Multi-repo initiative, hub style (the default)**: template `staged-initiative-hub`
     (or `initiative-hub` for the one-session flow) with repository = the hub repo whose
     `repos/*` submodules are the members; inputs include `branch` (the one initiative
     branch shared by hub and submodules) and `initiative_folder`. The `epics.yaml` it
     reads needs per-epic `workdir` + full `install`/`test`/`quality_gate` commands — see
     `references/spec-folder.md`.
   - **Single-repository initiative**: template `staged-initiative-repo` with the plain
     repository; same `epics.yaml` shape without `workdir` or commands (the repository
     record's own commands run).
   - **Staged models**: a `staged-*` root takes `model` (implements), `plan_model` (plans,
     and runs the epic's spec-gate / gen-e2e / retro) and `review_model` (reviews); the
     last two are required. Ask the human for all three.
2. **Preflight** — `POST /api/v1/runs/preflight` with everything you plan to send
   (`template_name`, `template_version`, `project_id`, `repository_id`, `base_branch`,
   `inputs`, `harness`, `model`, `budget_usd`). Every field is optional there — missing
   ones make dependent checks `skip`, not fail. Read the answer:
   - `lines[]` — each check with `status` and a `fix` when it fails; resolve every `fail`.
   - `start_allowed` and `queue_note` — whether and when it would start.
   - `rows[]` — the planned steps; `plan_error` names the exact template line otherwise.
   - `conflict_consent_required` — if true, creating the Run needs
     `conflict_consent: true` (a branch conflict the operator accepts knowingly).
3. **Create** — `POST /api/v1/runs`. Required: `template_name`, `template_version`,
   `project_id`, `repository_id`, `base_branch`, and a positive `budget_usd` — a Run
   cannot start without a budget. Optional: `inputs` (what step 1 discovered), `harness`
   (`claude` | `codex` | `local`; null takes the instance default), `model`,
   `save: true` (persist without starting; launch later with the `start` signal),
   `after_run_ids` (fan in behind one or more predecessors; requires `save: true`).
   A failed preflight line answers 409; an unbuildable plan answers 422 with structured
   `errors[]` naming template, version and line.

## Monitoring

There is no push channel — poll, at the UI's own cadence: **5 s while the Run is
`queued`/`running`, 30 s otherwise**. Never tighter.

Where the instance has it, `GET /api/v1/runs/{id}/events?wait=30&since=<last updated_at>`
replaces that loop with one held connection that answers as soon as the Run moves (see
`references/api.md`); a 404 for a Run you know exists means an older instance, so fall back to
the cadence above.

- `GET /api/v1/runs/{id}` — status, spend, and `admitted_signals` (cheap; poll this).
- `GET /api/v1/runs/{id}/detail` — everything: steps with log tails, per-story states,
  cost (`spent_usd` vs `budget_usd`, tokens, trace link), the `alert` when parked, and
  the `gate_record` audit trail. Fetch when status changed or you need depth.
- `GET /api/v1/runs/{id}/steps/{step_path}` — one step's attempts, prompts, costs.
- `GET /api/v1/queue` — every Run the engine holds and why each waits.

Run statuses: `queued → running → done | failed | cancelled`, with `needs_you` whenever
the machine stops for a human. Step statuses: `planned queued running done blocked
checkpoint error skipped`.

## When a Run parks (`needs_you`)

`detail.alert` says why: `park_kind` is one of `blocked` (the agent asked a question —
`reason` carries its words), `checkpoint` (a declared human gate), `verify_failed`,
`budget`, `timeout`, `push_rejected`, `protected_path` (the diff touched a protected file;
`payload.hits` lists them), `misconfigured`, `plan_stale`, `internal`, `dependency`,
`merge_conflict` (a `git.merge` row conflicted; the merge is left in the worktree and the
stop admits Retry and Cancel only).

**Read `admitted_signals` off the Run and choose only from it — never hardcode which
signal a state accepts.** A non-admitted signal answers 409. Then
`POST /api/v1/runs/{id}/signals` with `{kind, payload}`:

- `answer` `{text}` — reply to a blocked agent or a spec checkpoint.
- `continue` — approve a checkpoint; for a `protected_path` park, `{files: [...]}`
  records which protected files the operator accepts.
- `retry` — re-run the errored step.
- `skip_story` / `skip_epic` — skip the parked frame (skipped is never green).
- `budget_raise` `{budget_usd}` — must exceed what is already spent.
- `cancel` — any non-terminal Run.
- `start` — launch a Run created with `save: true`.

To edit the spec on a parked Run before continuing: `GET /api/v1/runs/{id}/files` (tree /
`?path=` / `?path=&diff=1`), `PUT /api/v1/runs/{id}/files` `{path, content}` (commits to
the parked worktree as an operator edit), then `answer` or `continue`.

**Escalate to the human instead of deciding yourself** whenever a park involves judgment
about their code or money: protected-path accepts, budget raises beyond what they
authorized, checkpoint approval of a spec or a finished epic, or any `blocked` question
you cannot answer from the project's own context. Give them the `/workflows/{id}` link
and the alert's `reason`; the web UI is built for exactly that review.

## Customizing a workflow

The workflows are templates stored in the instance, and they are meant to be adapted to the
project: add or move a verify command, add a checkpoint, give a step its own model, change
a timeout, reword what agents are told. `references/workflows.md` is the guide — the file
format, the step kinds, and the loop:

1. Read the latest version from the instance (`GET /api/v1/templates/{name}/{version}`).
2. Edit the YAML; set its `version:` to `max + 1`.
3. `POST /api/v1/templates/{name}/validate` until `errors` is empty.
4. Show the human the diff and which callers follow it; save only on their go-ahead
   (`POST /api/v1/templates/{name}/versions`, or **Save as v{n+1}** at `/templates`).
5. Preflight a Run on the new version and read `rows[]` before starting anything.

A save reaches only Runs planned afterwards; a parked Run keeps the template it was planned
from. Prefer changing data the template already reads (the repository's commands,
`epics.yaml` fields) over editing the template when that is enough.

## Rules

- Handshake first; a mismatched version stops you.
- Always preflight before creating a Run; resolve every `fail` line first.
- Discover template inputs from the API each time; templates evolve.
- A template save is the human's decision: validate, show the diff, wait for the go-ahead.
- One budget decision per Run, made by a human or from an explicit instruction — never
  invent or silently raise `budget_usd`.
- Poll at 5 s / 30 s; back off, never tighten.
- Choose signals from `admitted_signals`, never from assumption.
- A `blocked` park with a question you cannot answer from project context goes to the
  human, with the deep link.
- The token is a credential: never write it into files, logs, or command lines that get
  committed; read it from the environment at call time.
