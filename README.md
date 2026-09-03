# ai-orchestrator

An orchestrator that runs BMAD dev-loop workflows against other repositories: a Run is planned up front, executed durably, dispatches stories to a coding-agent harness (Claude Code, Codex, OpenCode), verifies with the target repository's own commands, and stops for the operator only at declared checkpoints or when an agent is blocked.

The product is specified, not yet built. Everything that decides what gets built lives under `_bmad-output/planning-artifacts/mvp/`:

| Document | Path |
| --- | --- |
| PRD (build contract, FR-1..FR-33) | `mvp/prd.md` + `mvp/addendum.md` |
| Architecture spine (binding, AD-1..AD-20) | `mvp/architecture/ARCHITECTURE-SPINE.md` |
| Epics and stories (8 epics, 66 stories) | `mvp/epics/epics.md`, `mvp/epics/epics.yaml`, one folder per epic |
| UX experience and visual system | `ux-designs/ux-v1-dev-loop-2026-08-26/`, `ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md` |

## Running it

Configuration is the environment (AD-20): `.env.example` is the contract, `make lint` fails when a
setting exists in one place and not the other. Copy it once, fill it in, and never commit the result.

```bash
cp .env.example .env        # then fill in the tokens and keys
```

Bringing the whole stack up (`make up`) arrives with the container images in story 1.6. Until
then the database runs in compose and backend-api runs on the host.

`DATABASE_URL` in the contract names the compose service (`@postgres:5432`), because that is
what the containers will use. It does not resolve from a shell on this machine, so a host run
overrides it — without that line the process dies in the migration step:

```bash
set -a; . ./.env; set +a                       # the contract both components read
docker compose up -d postgres                  # postgres:18, published on 127.0.0.1:5432

export DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:5432/$POSTGRES_DB"
uv run --locked --directory backend-api python -m orchestrator.main
```

The process logs one `migrations applied` line carrying the Alembic revision and then binds —
it never serves a half-migrated schema. Check the schema with:

```bash
docker compose exec -T postgres psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c 'select * from alembic_version'
```

The gates that decide whether work is done. Epic 1 is being built story by story, so a target
whose story has not landed yet exits non-zero with `not available until story <id>` rather than
silently passing:

```bash
make lint        # ruff · mypy · import-linter · env-contract check   (story 1.1 — works)
make test        # backend unit tests (pytest)                        (story 1.1 — works)
make e2e-api     # httpx scenarios + schemathesis against the stack   (story 1.2 — works)
make openapi     # export contracts/openapi.json, regenerate types    (story 1.3)
make e2e-ui      # playwright against astro preview                   (story 1.3)
make up / down   # docker compose: web-client, backend-api, postgres  (story 1.6)
```

`make e2e-api` needs the database and the application running (above). It reads three
variables from the environment: `ORCHESTRATOR_TOKEN`, which `.env` supplies, and
`BACKEND_API_URL` and `DATABASE_URL`, which a host run overrides — the first because the
contract names the compose service, the second for the same reason the application run
overrides it. The migration scenarios open their own connection, so leaving `DATABASE_URL`
at its contract value fails the gate with `failed to resolve host 'postgres'`. It waits up
to 30 seconds for `/healthz`; it never skips.

```bash
set -a; . ./.env; set +a
export DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:5432/$POSTGRES_DB"
BACKEND_API_URL=http://127.0.0.1:8000 make e2e-api
```

## Setting up the BMAD method on a new machine

The repository commits the method itself (`_bmad/`: config, scripts, manifests, modules) so every clone carries the same version, **6.11.0**. Two things are per machine and git-ignored: the skill stubs Claude Code loads (`.claude/skills/bmad-*`, `.agents/skills/bmad-*`) and your personal install answers (`_bmad/config.user.toml`). Reinstall them once per machine with the steps below.

### 1. Prerequisites

- **git** with access to this repository.
- **Node.js 22 or newer** (the installer runs through `npx`). With nvm: `nvm install 22 && nvm use 22`.
- **uv** (the BMAD scripts run with `uv run`): `brew install uv` on macOS, or see https://docs.astral.sh/uv/.
- **Claude Code** CLI, logged in: https://docs.anthropic.com/en/docs/claude-code — `npm install -g @anthropic-ai/claude-code`, then `claude` and `/login` once.

### 2. Clone and install the skill stubs

```bash
git clone <this repository> ai-orchestrator
cd ai-orchestrator
npx --yes bmad-method@6.11.0 install --directory . --modules bmm --tools claude-code,codex --yes --user-name OptimAI-team
```

The installer writes the skill stubs into `.claude/skills/` (read by Claude Code) and `.agents/skills/` (read by Codex and OpenCode), and regenerates `_bmad/config.user.toml` with your answers. Pin the version exactly: a different `bmad-method` version rewrites the installer-managed files under `_bmad/` and shows up as a diff.

### 3. Check

```bash
git status                                   # must be clean: the committed _bmad/ files match 6.11.0
ls .claude/skills | grep -c '^bmad-'         # 49 skills
uv run _bmad/scripts/resolve_config.py --project-root .   # prints the merged config as JSON
```

Then open Claude Code in the repository and type `/bmad-help`. It reads the planning artifacts and tells you where the project stands and which skill comes next.

### Notes

- Team-wide overrides go in `_bmad/custom/config.toml` (committed). Personal ones go in `_bmad/custom/config.user.toml` (ignored). Never edit `_bmad/config.toml` or `_bmad/config.user.toml` by hand: the installer regenerates them.
- To change an install answer (name, language), re-run the same `install` command with the new flags; prior answers are the defaults.
- Copies of the skills under `~/.claude/skills/` are optional. This repository relies on the project-level ones in `.claude/skills/`.

## Where the work stands

Epics and stories are complete (`mvp/epics/`). Next: `bmad-sprint-planning` to generate the tracking file, then build Epic 1 (repository foundation and quality gates) with `bmad-build`; Epics 2 to 8 are written for unattended `bmad-build-auto` dispatch, one brief per story.
