---
name: orchestrator
description: Drive an ai-orchestrator instance over its HTTP API — create projects, register repositories, launch BMAD workflow runs (story, epic, initiative, repo-init), monitor progress, and respond to checkpoints and blocked runs. Use when the user asks to run a workflow, dispatch a story or epic to the orchestrator, check on a run, or wire this project into the orchestrator.
---

# ai-orchestrator client

The orchestrator runs BMAD dev-loop workflows against git repositories: a Run plans every
step up front, dispatches stories to a coding-agent harness (claude, codex, opencode),
verifies with the target repository's own commands, and stops only at declared checkpoints
or when an agent is blocked. You talk to it over HTTP; humans watch the same Runs in its
web UI.

`references/api.md` in this skill is the endpoint reference — read it when you need exact
request fields. `references/spec-folder.md` is the format of the files `epic` and
`initiative` Runs read from the target repository (`epics.yaml`, `stories.yaml`,
`SPEC.md`) — read it before authoring or reviewing those files. This file is the
protocol — the order things happen in and the rules that keep you from fighting the
machine.

## Connection

Two values, from the project's environment (`.env` or exported):

- `ORCHESTRATOR_BASE_URL` — default `http://127.0.0.1:8000`
- `ORCHESTRATOR_TOKEN` — the single bearer credential

Every call: `Authorization: Bearer $ORCHESTRATOR_TOKEN`. Prove the pair works before
anything else:

```bash
curl -fsS -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" "$ORCHESTRATOR_BASE_URL/api/v1/ping"
```

`GET /healthz` needs no token (liveness only). Errors are RFC 9457
`application/problem+json`: `{type, title, status, detail, errors[]}` — read `detail` and
`errors[]` before retrying anything. Lists are `{items, next_cursor}`. Ids are UUIDs;
money is a decimal string in USD.

The web UI lives on the same host (default port 4321). The deep link for one Run is
`/workflows/{run_id}` — hand it to the user whenever you name a Run.

## One-time setup: project and repository

1. **Project** — `POST /api/v1/projects` with `{name, context_text, context_paths,
   env_vars}`. `context_text`/`context_paths` are what dispatched agents get told about
   the project; `env_vars` are encrypted and injected into harness runs.
2. **Repository** — `POST /api/v1/projects/{project_id}/repositories` with `{url,
   default_branch, install_command, quality_gate_command, unit_test_command, test_globs,
   package_manager}`. There are no per-repository credentials: the orchestrator clones
   with its own instance-wide `GITHUB_TOKEN`, so the URL must be reachable by that token.
3. **Clone check** — `POST /api/v1/repositories/{id}/clone-check` proves the URL and
   token resolve and creates the base clone. Do not proceed past a failing clone check;
   its `clone_check_lines` and `clone_check_hint` say what to fix.
4. **First time only** — if the target repository has never been BMAD-initialized,
   `POST /api/v1/repositories/{id}/init` starts a `repo-init` Run that bootstraps it as a
   PR. That is a normal Run from there: monitor it like any other.

Projects and repositories are reused across Runs — look before creating:
`GET /api/v1/projects` and `GET /api/v1/projects/{id}` (repositories embedded).

## Launching a Run

Never guess a template's inputs and never skip preflight.

1. **Discover templates** — `GET /api/v1/templates`, then
   `GET /api/v1/templates/{name}/{version}`: the response's `inputs` is the authoritative
   list of what this template takes. Shipped templates (`story`, `story-run`, `epic`,
   `initiative`, `task`, `repo-init`) evolve; read them, don't memorize them.
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
`payload.hits` lists them), `misconfigured`, `plan_stale`, `internal`, `dependency`.

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

## Rules

- Always preflight before creating a Run; resolve every `fail` line first.
- Discover template inputs from the API each time; templates evolve.
- One budget decision per Run, made by a human or from an explicit instruction — never
  invent or silently raise `budget_usd`.
- Poll at 5 s / 30 s; back off, never tighten.
- Choose signals from `admitted_signals`, never from assumption.
- A `blocked` park with a question you cannot answer from project context goes to the
  human, with the deep link.
- The token is a credential: never write it into files, logs, or command lines that get
  committed; read it from the environment at call time.
