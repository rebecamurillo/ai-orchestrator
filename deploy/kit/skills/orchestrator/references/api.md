# ai-orchestrator API reference (condensed)

Base: `$ORCHESTRATOR_BASE_URL` (default `http://127.0.0.1:8000`). Every route below is
under `/api/v1` and needs `Authorization: Bearer $ORCHESTRATOR_TOKEN`, except `GET
/healthz`, which is unprefixed and unauthenticated. The generated OpenAPI contract
(`contracts/openapi.json` in the repository, also served by the instance) is the full
machine-readable source; this file is the working subset.

Conventions: errors are RFC 9457 `application/problem+json` (`NotFound`→404,
`Forbidden`→403, `Conflict`→409, `Invalid`→422); lists are `{items, next_cursor}`; ids
are UUIDv7; times are ISO 8601 UTC with `Z`; money is a decimal string in USD.

## Health, auth and version

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/healthz` | Liveness, no auth: `{status, version}` |
| GET | `/api/v1/ping` | Proves the bearer token is accepted |
| GET | `/api/v1/version` | `{app_version, kit_version, bmad_version, harness_versions{claude, codex, opencode}}` — the handshake |

`app_version` is the image tag the instance runs; `kit_version` is the skills built into it
(the two are one number per release). 404 means an instance older than the route.

## The kit

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/kit/install.sh` | The installer itself, `text/x-shellscript` — pipe it to `bash` |
| GET | `/api/v1/kit/archive` | The whole kit as `.tar.gz`: `install.sh`, `manifest.json`, `skills/`, `.claude-plugin/` |

Re-installing this skill into a project, from inside it:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
```

`--harness claude|codex|opencode|all` picks the directory the skills land in
(`.claude/skills/` or `.agents/skills/`); the installer also writes `.orchestrator/kit.json`.

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
instance's `GITHUB_TOKEN` must reach `url`. `test_globs[]` is stored exactly as sent:
empty freezes no file for the agent (Operator decision 2026-10-06).

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
| GET | `/api/v1/runs/{id}/events` | Change signal; `?wait=0..30` holds the connection, `?since=` carries the last `updated_at` |
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
`conflict_consent`, `save` (persist, don't start), `after_run_ids[]` (needs `save: true`).

Signal kinds: `answer` (`{text}`), `continue` (`{files[]}` for protected-path accepts),
`retry`, `skip_story`, `skip_epic`, `budget_raise` (`{budget_usd}` above current spend),
`cancel`, `start` (a saved Run), `terminal_start` / `terminal_release` /
`terminal_resume` (human-in-terminal flow). Admission depends on status and `park_kind`
— always read `admitted_signals` first; a non-admitted kind answers 409.

### Waiting instead of polling

`GET /api/v1/runs/{id}/events` answers
`{run_id, status, updated_at, changed, admitted_signals, spend_usd, budget_usd, park_kind,
park_path}` — a change signal, not a payload.

- No `wait` (or `wait=0`): the current state, `changed: false`.
- `wait=1..30`: the connection is held that many seconds and answers the moment `status` or
  `updated_at` moves, with `changed: true`. The wait running out is `changed: false`, and the
  next call simply waits again. `wait` above 30 is 422.
- `since=<the previous answer's updated_at>`: the baseline is that timestamp instead of the
  state this request read, so a change made between two calls is answered immediately rather
  than missed. Always pass it when looping.
- Unknown id: 404, immediately — the wait never starts.

One held connection replaces a request every five seconds. Read
`GET /api/v1/runs/{id}/detail` once it says `changed: true`; the park's own payload is there.
An instance older than this route answers 404 for every id, including a Run that exists —
fall back to the 5 s / 30 s poll on `GET /api/v1/runs/{id}`.

### MCP

The same operations are also exposed as MCP tools at `$ORCHESTRATOR_BASE_URL/mcp`
(streamable HTTP, the same bearer, no `/api/v1` prefix): `version`, `list_templates`,
`get_template`, `preflight_run`, `create_run`, `get_run`, `get_run_detail`,
`wait_run_events`, `send_signal`, `list_queue`, `list_projects`. Each tool is one call to the
route above it, so the rules in `SKILL.md` apply unchanged. Per-harness configuration
snippets ship in the kit under `mcp/`; they are not installed automatically.

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
  `dependency` `merge_conflict`.
- A parked Run waits up to the instance's `HUMAN_WAIT_SECONDS` (default 30 days), then
  fails.

## Web UI deep links

Same host, default port 4321: `/workflows/{run_id}` (Run progress — the link to hand a
human), `/workflows/{run_id}/steps/{step_path}`, `/workflows/new`, `/projects/{id}`,
`/templates/{name}/{version}`, `/runs` (queue + history), `/` (board).
