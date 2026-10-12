# Runbooks — the actions that are not install, doctor, upgrade or a bug report

Read the one you need. Every command runs from the directory `install.sh` sits in. Hard rule 9
holds throughout: nothing here stops a host, container or stack the user did not ask to stop,
and the two steps that do (`compose down`, `docker volume rm`) are marked and need their
explicit go-ahead first.

## Rollback

`DEPLOY.md` §6 as commands. Which case applies is a question about the *release*, not about the
machine, and the release notes answer it.

**The release added no migration, or only backward-compatible ones** — a tag change:

```bash
./install.sh upgrade --tag 1.1.0
```

The pre-flight prints `running <newer> → target 1.1.0`, so the downgrade is visible before the
confirm. It still takes a `pg_dump` first, which is what you want.

**The release migrated the schema in a way the old code cannot read** — there is no rollback,
only a restore, and everything written since the dump is lost. Say that in those words, get
the go-ahead, then:

```bash
docker compose down                             # ask first: this stops their instance
docker volume rm <compose-project>_pgdata       # irreversible
docker compose up -d --no-build --wait postgres
docker compose exec -T postgres pg_restore -U orchestrator -d orchestrator --clean --if-exists \
  < backups/<dump>
./install.sh upgrade --tag 1.1.0
```

Alembic refusing to start with `Can't locate revision identified by …` is the **safe** failure,
not a bug: the version table holds a revision the older image's script directory does not
contain. Report it as a blocked rollback, which is what it is.

## Backup and restore

```bash
# backup: the database, plus the .env that holds the key its encrypted columns need
docker compose exec -T postgres pg_dump -U orchestrator -Fc orchestrator \
  > "backups/db-$(date -u +%Y%m%dT%H%M%SZ).dump"
cp .env "backups/env-$(date -u +%Y%m%dT%H%M%SZ).bak"
chmod 600 backups/env-*.bak

# restore into a running database
docker compose exec -T postgres pg_restore -U orchestrator -d orchestrator --clean --if-exists \
  < backups/<dump>
```

Three things to tell them:

- `ORCHESTRATOR_SECRET_KEY` is the Fernet key for Project env vars. A database restored without
  the `.env` that encrypted it has unreadable Project env vars. Back up both or neither — and
  the `.env` copy is a secret, mode 600, never committed.
- The `work` volume (base clones, worktrees, logs) is not in the dump and does not need to be:
  a Run whose output matters is already pushed, and `worktree_gc` sweeps the rest on schedule.
- A restore that has never been performed is not a backup. Rehearsing it once, on a scratch
  compose project, is cheap.

`./install.sh upgrade` already takes a dump into `backups/` before it pulls; that is the one a
rollback restores from.

## Secret rotation

One variable at a time, in `.env`, then `./install.sh start` (which re-reads it), then
`./install.sh doctor`. Never print a rotated value into a chat, a commit, a log or a report.

| Rotating | Also do |
| --- | --- |
| `ORCHESTRATOR_TOKEN` | Re-run `kit/install.sh` in every plugged project, or edit `ORCHESTRATOR_TOKEN` in each project's `.env` by hand — every agent and dashboard holds the old one. It is also the web login. |
| `GITHUB_TOKEN` | Nothing else; the next clone or push uses it. A Run parked on `push_rejected` can be retried after. |
| `ORCHESTRATOR_SESSION_SECRET` | Every browser session is invalidated — they log in again with the same token. |
| `LITELLM_API_KEY` / `LITELLM_SPEND_KEY` | Mint them in LiteLLM first; `llm-platform/sync-env.sh <path>/.env` does both and writes them in. The spend key is backend-only and must never reach a harness. |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | Take the pair from the Langfuse project; traces written before the rotation stay where they are. |
| `POSTGRES_PASSWORD` | Change it in the database too, and keep `DATABASE_URL` in step — the two spellings must agree or the stack will not bind. |
| `ORCHESTRATOR_SECRET_KEY` | **Stop.** This is the Fernet key for every Project env var already stored; rotating it makes them unreadable. It is a re-entry of every Project's env vars, not a rotation. Say so before they touch it. |

## Models and defaults

Two files, and both matter:

- **`llm-platform/litellm.config.yaml`** — `model_list` is which models exist at all. A model
  named anywhere else and absent here answers 404 at dispatch time. Restart the gateway after
  an edit: `./install.sh start --with-platform`.
- **`.env`** — `READINESS_MODELS` is the default model per harness
  (`claude=…,codex=…,local=…`), and **every model it names must exist in `model_list` or
  backend-api refuses to start.** `LOCAL_MODELS` is the alias list the `local` harness is
  offered.

A Run's own `harness` and `model` are per-Run inputs and override the defaults, so a change
here does not touch a Run that named a model. `GET /api/v1/harnesses` shows each harness's
`models` as the instance currently offers them; an empty list means that harness takes a
free-text model name.

## Spend

Report only what the API returns.

- `GET /api/v1/runs/{id}` — `budget_usd`, `spend_usd`.
- `GET /api/v1/runs/{id}/detail` — `cost` carries `spent_usd`, `budget_usd`, `tokens_in`,
  `tokens_out`, `wall_clock_seconds`, `active_seconds`, `provisional`, `trace_url`.
- `GET /api/v1/runs?project_id=…` — the same summaries for a project.
- `GET /api/v1/runs/{id}/steps/{step_path}` — per-attempt costs, when the question is *which
  step* spent it.

Sum what you are given. Do not model a price, extrapolate a month, or compare against a
provider's bill. `provisional: true` means the gateway was off or has not reported yet and the
figure is an estimate — say so whenever you quote it. With a Claude subscription every figure
is notional, computed from LiteLLM's price table rather than from anything billed.

## Garbage collection

The `work` volume grows without bound: base clones, a worktree per Run, logs.

- `WORKTREE_RETENTION_DAYS` and `WORKTREE_GC_CRON` in `.env` are the sweep — a terminal Run's
  worktrees and logs are kept that long, then `worktree_gc` removes them on that schedule.
  Lowering the retention is the first lever and needs only `./install.sh start`.
- Superseded image tags are the other half and are **not** swept. `docker image rm` on an old
  `ghcr.io/rebecamurillo/ai-orchestrator/*` tag is the fix — **ask first, every time**: the
  image you remove is the rollback that is no longer available.
- `./install.sh doctor` reports free space on the docker data root and warns above 90 %.
- Never `docker compose down -v`. That deletes the database.

## Harness tool allowlist

The claude harness runs with `--permission-mode dontAsk` and the list in `CLAUDE_ALLOWED_TOOLS`
(instance `.env`): a shell command outside it is denied outright, and the agent parks
`blocked` saying so. The symptom is every story parking at the same command — typically the
target repository's package manager or test runner.

The shipped default allows `Bash` whole — the container is the sandbox, and `git push` stays
denied by the adapter — so a fresh install never parks on a denied shell command. An
instance that narrowed the list (installs before 2026-10-09 shipped a list of command
families: `Bash(yarn *)`, `Bash(npx *)`, …) must cover the toolchain of every repository it
builds, or go back to `Bash`. Edit the quoted value in `.env`, then `./install.sh start`. It
is read at start-up, so the restart is required — say what is running and let the user choose
the moment. A template cannot widen this list, and answering the park does not either.

## Template refresh

Shipped templates are seeded at boot (`seed_shipped`): every shipped file is validated and
inserted only when its content hash is new. So an upgrade that changed a template takes effect
on the next start, with no command of its own, and a file that fails validation stops start-up
outright with the file named rather than serving a half-seeded store. A booted instance
therefore has a consistent store.

The symptom of a stale one is a Run planning steps that do not match the template shipped with
the running image — a step that should not be there, or an input the UI does not offer. Check
the instance, not the file on disk: `GET /api/v1/templates`, then
`GET /api/v1/templates/{name}/{version}`, and compare the version number against what the new
release ships. If they disagree, the instance is not running the image you think it is —
`./install.sh doctor`'s version line is where that shows up.

An upgrade also stores each changed shipped template as a new version above any the user
saved, so their customization is no longer the latest. After an upgrade, list the versions of
every template they edited and, where a shipped one landed on top, re-apply the edit as the
next version. Editing itself — the format, the validate-and-save loop, what a save reaches —
is `../../orchestrator/references/workflows.md`.
