# Agent delivery kit — analysis and plan

Date: 2026-09-30. Status: proposal, revised after Operator review; awaiting decisions (§10).

Scope: how the orchestrator is delivered to a client, how a client's own repositories are
plugged into it, and what agents/skills ship beside the app — install, maintenance,
spec-writing (idea → ready-to-dev), and run supervision.

---

## 1. The delivery verdict: the tarball stops being the path

Today a client touches a release tarball (`get.sh` → GitHub release asset → `install.sh`)
and two GHCR images. The tarball is the wrong unit, structurally:

- **A snapshot competing with a channel.** The images are versioned, pullable and
  upgradeable. The tarball carries the handful of non-image files and diverges from the
  installed copy the moment `install.sh` writes `.env` beside itself. `install.sh upgrade
  --tag` exists because the tarball cannot upgrade — it is already only a bootstrap.
- **It defeats version coupling.** Skills delivered in a tarball are a copy taken at
  download time; nothing keeps them equal to the running instance. AD-16 already forbids
  exactly this for BMAD (`BMAD_VERSION` is the instance's, never "latest").
- **It costs a PAT scope nobody else needs** — `repo` to read the asset, where pulling
  images needs only `read:packages`.

### What replaces it — transport changes, content does not

The client still receives `docker-compose.yml`, `.env.example`, `install.sh`, the
llm-platform stack and the kit. They come **out of the image** instead of out of a
release asset, so they are guaranteed to match the image about to run.

**Problem 1 — bootstrap the server on a bare machine.**

```bash
docker run --rm ghcr.io/optimai-labs/backend-api:1.0.0-beta kit bootstrap | tar x
cd ai-orchestrator && ./install.sh
```

The image is the single versioned unit. Upgrade = new tag, re-extract. Offline =
`docker save` / `docker load`, which is what air-gapped clients actually want.

**Problem 2 — plug a project repository into a running instance.** The instance holds
the version of truth and is already reachable, so it serves its own kit:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
```

Version skew becomes unrepresentable: the kit a project gets is built into the image
that answered. This is the single highest-value change in the plan.

`scripts/bundle.sh` / `make bundle` stays as the offline/procurement escape hatch, not
the documented path. `deploy/get.sh` and the release-asset job are retired.

---

## 2. Repository layout: one folder is the client install

**Decision (Operator, 2026-09-30): everything a client receives lives in one folder.**
Today it is scattered across `deploy/`, `host/`, `plugin/`, root `VERSION`, and a
`bundle.sh` that stitches them, with a dual-path hack in `install.sh` to find `host/` in
both a checkout and a bundle.

`deploy/` is already the bundle root, already documented, and already what `install.sh`
assumes — so it grows into the whole client install rather than a new name being invented:

```
deploy/                      ← the client install, entire; `ls` answers "what do they get"
  install.sh                 install | start | stop | status | logs | upgrade | uninstall | env
  docker-compose.yml         pulls the two GHCR images by IMAGE_TAG
  .env.example               the 50-variable contract
  README.md                  the client's operator guide
  VERSION                    generated from root VERSION at build; never hand-edited
  llm-platform/              was host/  — LiteLLM gateway + Langfuse tracing + their stores
  kit/                       was plugin/ — skills, agents, per-harness installer (§4)
```

What this buys: `bundle.sh` and `kit bootstrap` collapse to `tar -C deploy .`; the
`install.sh` dual path disappears (`llm-platform/` is always beside it); the Dockerfile
copies one folder to serve both `kit bootstrap` and `GET /api/v1/kit/`.

### `host/` → `llm-platform/`

`host` reads as "hosting" or "the machine". The folder is everything that sits between
the orchestrator and the model providers: LiteLLM (gateway, spend metering), Langfuse
(tracing), and their postgres, clickhouse, redis, minio. `llm-platform` names that;
`observability` would misdescribe LiteLLM.

Rename scope: the folder, the `make host-*` targets (→ `make platform-*`), `install.sh`,
`bundle.sh`, `docker-compose.yml`, `README.md`, `DEPLOY.md`, `deploy/README.md`,
`release.yml`, and two lines in `AGENTS.md` (anchor — Operator edit).

**Deliberately not renamed**, each a data-loss or silent-breakage hazard:

- Docker volumes `host-pgdata`, `host-clickhouse-data`, `host-clickhouse-logs`,
  `host-minio` — a new name orphans the existing Langfuse/ClickHouse data on every
  machine that has run the stack. Keep, with a comment naming the mismatch.
- `HOST_*` variables (`HOST_POSTGRES_PORT`, …) — a rename breaks every `.env` on disk by
  silently falling back to defaults. Keep; revisit only with a migration step in
  `install.sh upgrade`.
- Compose project name `aio-host` — same reason (hard rule 9: `up` under a new name would
  not recreate the old one, but the old one would be left running unknown).

**By hand on the Operator's machine:** `host/.env` and `host/backups/` are untracked;
`git mv` will not move them. Move them and the `.gitignore` paths in the same change, or
the local Langfuse config appears to vanish.

---

## 3. Version coupling — make skew unrepresentable

1. **One number.** Root `VERSION` is the image tag. `plugin.json` says `0.1.0` against
   `1.0.0-beta` today — the drift in miniature. Every manifest version is generated from
   `VERSION` at build; a lint check fails on drift (same shape as `check_env_contract.py`).
2. **`GET /api/v1/version`** behind the bearer, like `/ping`: `{app_version,
   kit_version, bmad_version, harness_versions{claude,codex,opencode}, contract_hash}`.
   New router; `make openapi` regen (AD-3). No new setting — the values already live in
   `infrastructure/settings.py`.
3. **The installed kit records its origin** in `.orchestrator/kit.json`
   (`{kit_version, base_url, installed_at, harness}`).
4. **The skill's first rule is a handshake**: call `/version`, compare with `kit.json`,
   on mismatch print the one-line re-install command and stop.
5. **BMAD too**: the spec chain (§6) authors for the instance's `BMAD_VERSION`, now
   exposed by `/version`; the readiness gate checks the target's
   `_bmad/_config/manifest.yaml` equals it (AD-16).

---

## 4. The kit: one folder, three projections, four skills

```
deploy/kit/
  install.sh            --harness claude|codex|opencode|all ; --base-url ; --token
  manifest.json         kit_version (== VERSION), file list, per-harness projection
  .claude-plugin/       plugin.json — so `/plugin marketplace add` still works, generated
  skills/
    orchestrator/         exists — the API protocol, grown into the Lead's runbook
    orchestrator-admin/   NEW — install, harness setup, upgrade, doctor, bug report (§5)
    initiative-spec/      NEW — idea → ready-to-dev (§6)
    initiative-run/       NEW — launch and supervise Runs (§7)
  agents/               Claude-only subagent definitions, projected on install
  mcp/                  phase 6 — per-harness config pointing at $BASE_URL/mcp
```

**Everything is a skill first.** Skills are the only vehicle all three harnesses read.
Claude subagent files, opencode commands and MCP config are *projections* the installer
writes from `--harness` — the same pattern as `bmad-method install --tools …` and as
`scripts/harness/_common.sh` server-side. One pattern, not two.

**MCP: as a `/mcp` route on backend-api, not a separate package.** Same bearer (AD-4),
typed tools, token kept out of shell history (hard rule 5), version coupling for free.
Harness support for remote MCP differs, so the skill stays the floor; MCP is the enhanced
path, phased last.

---

## 5. Client environment, guided setup, and maintenance (`orchestrator-admin`)

### What `install.sh` already does right, and keeps

Of the 50 variables in `deploy/.env.example`:

| class | variables | how |
| --- | --- | --- |
| **generated** | `ORCHESTRATOR_TOKEN`, session secret, Fernet key, Postgres password, `DATABASE_URL`, `IMAGE_TAG` | `openssl rand`; never asked |
| **asked** (2 prompts) | GitHub token; "install the llm-platform stack?" → provider keys, each skippable | explained before asking; `--yes` for unattended |
| **defaulted** | ports, crons, retention, pinned BMAD/harness versions, log level | working defaults |
| **blanked on purpose** | `LITELLM_BASE_URL`, `LANGFUSE_BASE_URL` | empty = off; `sync-env.sh` fills them when the platform is chosen |

`.env` is written once, mode 600, never overwritten. Customise = edit `.env`,
`./install.sh start`. `install.sh env` re-renders without touching the stack.

### Subscriptions — honest state

- **Claude Max/Pro: supported, manual, host half unverified live.** `CLAUDE_SUBSCRIPTION_AUTH=true`,
  LiteLLM config edits, `docker compose exec backend-api claude login`, bind the Run to
  the `claude-subscription` model. Documented in the platform README; the container half
  is unit-tested.
- **Codex and OpenCode: API key only.** No subscription login exists in
  `scripts/harness/codex.sh` or `opencode.sh`.

A client cannot realistically do the Claude flow from a README. Action #2 below absorbs it.

### Actions

| # | Action | Notes |
| --- | --- | --- |
| 1 | **Guided install / `env`** | Walk only the variables a client has an opinion about (ports, default harness+model, budget, retention); leave the rest alone; never echo a secret. |
| 2 | **Harness setup** | On install and on a live instance. Includes the Claude subscription flow end-to-end, verified by the existing harness-readiness probe. |
| 3 | **Upgrade** | `install.sh upgrade --tag` + pre-flight: read `/version`, diff, name what needs a drain (DEPLOY.md §5.1), back up, go; then re-install the kit in every plugged project. |
| 4 | **File a GitHub issue** | Title + body + **redacted** diagnostics. Private repo: `gh` when the user has access, else `issue.md` + prefilled URL. Redaction and template are the value; transport is a flag to flip when public. |
| 5 | **Doctor** | *First to build.* Reachability, token, `/version`, docker + GHCR login, disk, ports, harness readiness, platform on/off, template-store freshness. |
| 6 | **Backup / restore** | pg dump + `work` volume + `.env`; first-class and restorable. |
| 7 | **Rollback** | DEPLOY.md §6 as a command. |
| 8 | **Diagnostic bundle** | Feeds #4; what an Operator asks a client for. |
| 9 | **Secret rotation** | `ORCHESTRATOR_TOKEN`, `GITHUB_TOKEN`, provider keys. |
| 10 | **Models and defaults** | Add/remove a LiteLLM model; instance default harness+model. |
| 11 | **Spend report** | Per project / run, from data the API already returns. |
| 12 | **Garbage collection** | Worktrees, base clones, finished workspaces, superseded image tags. The `work` volume grows unbounded. |
| 13 | **Template store refresh** | After upgrade; stale seeded templates are a known failure. |
| 14 | **Connect a project** | Project + repository + clone-check + `repo-init`, guided. |

Hard rule 9 governs all of it. The script stays the thing that runs; the skill is what
talks the client through it and reads the output when it fails.

---

## 6. Spec writing: idea → ready-to-dev (`initiative-spec`)

### The proposed order is right; three things are missing

BMAD canonical: brainstorm → brief/PRFAQ → **PRD** → **UX** → **architecture** → **epics
and stories** → readiness gate → build. The proposal — intent, business rules, design,
spec + architecture, epics — is that chain. UX after requirements, before architecture,
is correct: a mockup drawn before the requirement is pinned silently *becomes* it.

Missing:

**a. Step 0 — project context.** Read the target's reality first: `AGENTS.md`,
architecture, existing initiative folders, branch state, and which repos are members in a
hub run (`bmad-project-context`, mandatory here, not `anytime`).

**b. Research as a declared branch.** "Is the idea clear?" triggers `bmad-deep-recon`
(market / domain / technical / competitive) or `bmad-forge-idea` when the idea itself is
unproven and should be allowed to die cheaply.

**c. A projection step, and a gate that is not a checklist.** BMAD's epics/stories are
not the hub `epics.yaml` format (`workdir`, `install`, `test`, `quality_gate`; bare
`spec_folder`; prefix-free ids; `{id}.md` story files). Every recorded failure of this
pipeline was a projection defect (story-file namespace collision; an `install` command
shipped without ever being executed). So:

- an explicit projection step, per `kit/skills/orchestrator/references/spec-folder.md`;
- **no command lands in `epics.yaml` that has not been executed successfully in its own
  `workdir` during this step**;
- **the gate is `POST /api/v1/runs/preflight` with the real inputs** — resolve every
  `fail` line, confirm `rows[]` is the intended shape, then declare ready.

### The chain

```
0  context      target repo(s), members, branch state, BMAD_VERSION       → CONTEXT.md
1  intake       clear? → research / forge-idea, or straight on
2  requirements PRD: users, business rules, scope, acceptance              → PRD
3  ux           only if UI in scope; Figma or HTML mockups, committed      → UX-SPEC + mockups/
4  architecture spine: invariants, decisions, trade-offs — validated       → ARCHITECTURE
5  breakdown    epics and stories                                         → epics + stories
6  projection   → epics.yaml / <spec_folder>/{SPEC.md, stories.yaml}
7  gate         preflight against the instance; open questions = 0        → verdict
```

Figma named but unreachable → **stop and ask** for the connector; never improvise from a
screenshot. Default to HTML mockups otherwise. Mockups are committed into the initiative
folder and referenced by story id — a dispatched agent sees only the repository.

### `INITIATIVE.md` — state and pointers, never content

```yaml
---
initiative: stats-area
phase: 4-architecture
branch: feat/initiative-stats
flavor: initiative-hub@1
autonomy: assisted             # supervised | assisted | auto (§7)
artifacts: {prd: PRD.md, ux: UX-SPEC.md, ...}
open_questions: []             # empty is the precondition for auto
decisions: [{date, what, why}]
gate: {verdict: pending, checked_at: null}
runs: []
---
```

Input is an idea (create folder + branch) or an existing folder (resume at `phase`). An
attached initiative branch is fast-forwarded before every dispatch, or a fresh branch
name is taken — the recorded branch traps demand it.

---

## 7. Running the work (`initiative-run`)

1. Readiness — re-run the §6 gate; refuse on non-PASS.
2. Recap and confirm — what will be built; harness, model and **budget** confirmed by a
   human. One budget decision per Run, never invented.
3. Dispatch — preflight, create, hand back `/workflows/{id}`.
4. Supervise — **a watcher, not an always-on agent.** No push channel exists; an idling
   agent burns context to learn nothing.
   - v1: `orchestrator-watch`, a plain poll loop at 5 s / 30 s that notifies and prints
     the park payload; the agent is invoked *on* a park.
   - v2: `GET /api/v1/runs/{id}/events?wait=30` long-poll — one connection, near-free.
   - v3: webhooks, for consumers with an inbound URL only.

**Autonomy is a declared policy.** `autonomy` in `INITIATIVE.md` selects:

| park kind | supervised | assisted | auto |
| --- | --- | --- | --- |
| `blocked`, answerable from the spec | ask | answer | answer |
| `blocked`, needs judgement | ask | ask | ask |
| `verify_failed` | ask | diagnose, retry once, then ask | same |
| `protected_path` | ask | ask | accept when within story scope |
| `checkpoint`, `budget`, `merge_conflict`, `push_rejected` | ask | ask | ask |

Signals always chosen from `admitted_signals`; budget and checkpoint never auto-resolve.

---

## 8. Subagents: fan-out and verification, never elicitation

Pays: recon across submodules; research fan-out; multi-lens spec review; executing each
epic's commands in its own workdir in parallel (§6c); the watcher, so polling noise never
reaches the lead's context. Does not pay: steps 1–4 are conversations with a human.
Skills are written against a *capability* — fan out where supported, sequential otherwise.

---

## 9. Sequenced delivery

| Phase | Lands | Status |
| --- | --- | --- |
| **1** | `/api/v1/version`; manifests held to `VERSION` by `scripts/check_version.py` in `make lint`; `kit.json` + handshake rule in the skill | **landed 2026-09-30** (`feat/agent-delivery-kit`) |
| **2** | Layout: `host/`→`deploy/llm-platform/`, `plugin/`→`deploy/kit/`; `bundle.sh` → `deploy/` alone; dual path removed; `make platform-*`; `AGENTS.md` lines | **landed 2026-09-30** |
| **3** | `kit bootstrap` from the image; `GET /api/v1/kit/{install.sh,archive}`; `kit/install.sh --harness`; `get.sh` + release-asset job retired | **landed 2026-09-30** |
| **4** | `orchestrator-admin`: doctor → upgrade pre-flight → harness setup incl. Claude subscription → guided env → bug report; rest by demand | next |
| **5** | `initiative-spec`: chain, `INITIATIVE.md`, projection step, preflight gate | after 4 |
| **6** | `initiative-run` + `orchestrator-watch`; autonomy table | after 5 |
| **7** | `/mcp` route + harness config projections; long-poll events | last |

Every phase: `make lint`, `make test`; `make openapi` on any API change (AD-3); a
`.env.example` entry for any new setting (hard rule 8); a test module per source module.

Learned landing 1–3: PEP 440 normalises `1.0.0-beta` to `1.0.0b0`, so `app_version()` reads
the `VERSION` file (at `/app/VERSION` in the image, the repository root in a checkout), never
distribution metadata — or the handshake could never match on a pre-release. `settings.py`
sits at exactly 400 lines; the next setting splits it. The image is private, so a client runs
`docker login ghcr.io` once by hand before `kit bootstrap` — `install.sh` does that login
for the pulls, but cannot for the bootstrap that produces it.

## 10. Decisions

Taken (Operator, 2026-09-30):
- One folder is the client install → `deploy/` grows into it.
- `host/` → `llm-platform/`; volumes, `HOST_*` vars and the `aio-host` project name stay.
- `make host-*` → `make platform-*`.
- MCP as a `/mcp` route on backend-api, phase 7.
- `assisted` is the default autonomy for a client initiative.
- `AGENTS.md` edits in phase 2 are authorised (paths; version-drift check as a contract
  statement).

Open:
1. Retire `get.sh` and the release-asset job in `release.yml`, keeping `make bundle` for
   the offline/procurement case only. Recommendation: retire — two paths to the same files
   is the drift this plan eliminates. Cost: a client cannot read the scripts before pulling
   the image until the repo is public.
2. Long-poll `GET /api/v1/runs/{id}/events?wait=30` — one held connection instead of a
   5 s request loop; bounded router change, no new infrastructure. Recommendation: in
   scope at phase 7, never blocking the watcher, which ships on the documented 5 s / 30 s
   cadence first.
