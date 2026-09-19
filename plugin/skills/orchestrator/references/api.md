# ai-orchestrator API reference (condensed)

Base: `$ORCHESTRATOR_BASE_URL` (default `http://127.0.0.1:8000`). Every route below is
under `/api/v1` and needs `Authorization: Bearer $ORCHESTRATOR_TOKEN`, except `GET
/healthz`, which is unprefixed and unauthenticated. The generated OpenAPI contract
(`contracts/openapi.json` in the repository, also served by the instance) is the full
machine-readable source; this file is the working subset.

Conventions: errors are RFC 9457 `application/problem+json` (`NotFound`→404,
`Forbidden`→403, `Conflict`→409, `Invalid`→422); lists are `{items, next_cursor}`; ids
are UUIDv7; times are ISO 8601 UTC with `Z`; money is a decimal string in USD.

## Health and auth

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Liveness, no auth: `{status, version}` |
| GET | `/api/v1/ping` | Proves the bearer token is accepted |

## Projects

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/projects` | List (paged) |
| POST | `/api/v1/projects` | Create → 201 |
| GET | `/api/v1/projects/{id}` | One project, repositories and runs embedded |
| PUT | `/api/v1/projects/{id}` | Full replace of editable fields (incl. the whole env-var set) |
| GET | `/api/v1/projects/{id}/trajectories.jsonl` | Trajectory export (JSONL) |

Create/update body: `{name, context_text, context_paths[], env_vars[{name, value}],
log_prompt_content}`. `env_vars` are encrypted at rest and returned masked.

## Repositories

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/projects/{id}/repositories` | Register → 201 |
| GET | `/api/v1/projects/{id}/repositories` | List under a project |
| GET | `/api/v1/repositories/{id}` | Read one |
| PUT | `/api/v1/repositories/{id}` | Update editable fields |
| POST | `/api/v1/repositories/{id}/clone-check` | Reach the remote, make/refresh the base clone |
| GET | `/api/v1/repositories/{id}/clone-check` | Last stored result (no git) |
| POST | `/api/v1/repositories/{id}/init` | Start a `repo-init` Run → 201; optional body `{harness}` |

Register body: `{url, default_branch, install_command, quality_gate_command,
unit_test_command, test_globs[], package_manager}`. No per-repo credentials — the
instance's `GITHUB_TOKEN` must reach `url`.

## Templates

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/templates` | Names, version lists, latest description |
| GET | `/api/v1/templates/{name}/versions` | Version numbers, ascending |
| POST | `/api/v1/templates/{name}/versions` | Save the next version, body `{yaml}` (`version` must be max+1; versions are immutable) |
| GET/POST | `/api/v1/templates/{name}/validate` | Validate latest / posted `{yaml}` — problems come back as data, never 422 |
| GET | `/api/v1/templates/{name}/{version}` | One version: yaml, `inputs`, `calls`, `called_by`, `pinned_by` |
| GET | `/api/v1/templates/{name}/graph` · `/{version}/graph` | Text / structured step graph |

`inputs` on the version read is the authoritative list of what a Run of it takes.

## Runs

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/runs/preflight` | Dry-run checks + planned rows; all fields optional |
| POST | `/api/v1/runs` | Create + enqueue → 201 `{run, starts_now, waiting}` |
| GET | `/api/v1/runs` | Paged list; `?project_id=` filter; `?view=board` for the kanban shape |
| GET | `/api/v1/runs/{id}` | Summary: status, spend, `admitted_signals` — the cheap poll |
| GET | `/api/v1/runs/{id}/detail` | Everything: steps + log tails, stories, cost, `alert`, `gate_record` |
| GET | `/api/v1/runs/{id}/graph` | The Run's step graph |
| GET | `/api/v1/runs/{id}/steps/{step_path}` | One step with all attempts |
| GET | `/api/v1/runs/{id}/attempts/{attempt_id}/log` | Raw attempt log |
| GET | `/api/v1/runs/{id}/files` | Parked worktree: no `path` → tree; `?path=` → file; `&diff=1` → diff |
| PUT | `/api/v1/runs/{id}/files` | Commit one operator edit `{path, content}` while parked |
| POST | `/api/v1/runs/{id}/signals` | `{kind, payload}` — see below |
| GET | `/api/v1/runs/{id}/signals` | Same read as `GET /runs/{id}` |

Create body (`RunIn`): required `template_name`, `template_version` (int), `project_id`,
`repository_id`, `base_branch`, `budget_usd` (> 0); optional `inputs{}`, `harness`
(`claude` | `codex` | `local`), `model`, `manual_estimate_h`, `re_review_done`,
`conflict_consent`, `save` (persist, don't start), `after_run_id` (needs `save: true`).

Signal kinds: `answer` (`{text}`), `continue` (`{files[]}` for protected-path accepts),
`retry`, `skip_story`, `skip_epic`, `budget_raise` (`{budget_usd}` above current spend),
`cancel`, `start` (a saved Run), `terminal_start` / `terminal_release` /
`terminal_resume` (human-in-terminal flow). Admission depends on status and `park_kind`
— always read `admitted_signals` first; a non-admitted kind answers 409.

## Fleet and harnesses

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/queue` | Every Run the engine holds and why it waits |
| GET | `/api/v1/steps` | Attempt history; filters `project_id`, `status`, `harness` |
| GET | `/api/v1/harnesses` | Installed harnesses |
| GET | `/api/v1/harnesses/{name}/probe` | Live CLI/config probe |
| POST/GET | `/api/v1/harnesses/{name}/readiness` | Run / read the end-to-end readiness diagnostic |

## Status alphabets

- Run: `queued` `running` `needs_you` `done` `failed` `cancelled` (terminal: last three).
- Step: `planned` `queued` `running` `done` `blocked` `checkpoint` `error` `skipped`.
- Park kinds (`alert.park_kind`): `blocked` `checkpoint` `verify_failed` `budget`
  `timeout` `push_rejected` `protected_path` `misconfigured` `plan_stale` `internal`
  `dependency`.
- A parked Run waits up to the instance's `HUMAN_WAIT_SECONDS` (default 30 days), then
  fails.

## Web UI deep links

Same host, default port 4321: `/workflows/{run_id}` (Run progress — the link to hand a
human), `/workflows/{run_id}/steps/{step_path}`, `/workflows/new`, `/projects/{id}`,
`/templates/{name}/{version}`, `/runs` (queue + history), `/` (board).
