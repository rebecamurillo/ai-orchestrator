# The host side

Three things run on the Mac mini itself rather than in compose, and one job runs against it.
Docker on macOS has no GPU, so the model server has to be a host process; the Gateway holds
keys the containers never see; and Langfuse is a stack of its own. `docker-compose.yml` reaches
all three through `host.docker.internal`, which the `backend-api` service maps with
`extra_hosts: ["host.docker.internal:host-gateway"]`.

Every value below is set on the host. The containers read their own copy of the same names from
`.env`, whose contract is `.env.example` (AD-20). No key is written into a file in this
repository.

| Component | Version | Port | Read by the stack as |
| --- | --- | --- | --- |
| LiteLLM proxy | 1.99.0 | 4000 | `LITELLM_BASE_URL=http://host.docker.internal:4000` |
| Langfuse | 4.27.0 | 3000 | `LANGFUSE_BASE_URL=http://host.docker.internal:3000` |
| oMLX | — | 8000 | reached by LiteLLM, never by a container |

## Running both in Docker on this machine — optional

**This stack is optional.** Nothing in the repository requires it: `make lint`, `make test`,
`make e2e-api`, `make e2e-ui` and `make images` all pass without it, and the product stack
starts and serves without it. It exists for two things — exercising the whole production shape
on one machine before there is a hosted Gateway, and as the reference for what a new instance
has to stand up. Treat it as a worked example of the table above, not as a dependency.

`docker-compose.yml` in this directory runs LiteLLM and Langfuse together. It is a **separate
compose project** (`ai-orchestrator-host`) from the repository root's: different lifecycle, its
own data, and it stays up across a `make down`. The orchestrator reaches it through
`host.docker.internal` exactly as it would reach a Gateway running anywhere else, so nothing
about this is a path production does not have.

### Both stacks run side by side

Every published port is distinct, so `make up` and `make host-up` can be running at once. The
one that would actually be reached for by accident is the database: **the product's postgres
keeps 5432, and this stack's own postgres is published on 5433.** They are separate servers
with separate volumes — the orchestrator's schema is never in the same database as Langfuse's.

`backend-api/tests/unit/test_host_compose.py` resolves the published ports out of both compose
files and fails if any host-side port appears in both, so adding a port to either file is
checked against the other rather than against a list someone has to remember to update.

```bash
make host-up          # generate host/.env, start everything, wait for health
make host-env-sync    # mint the harness key and point the root .env at the stack
make up               # the product stack
make host-doctor      # every harness checks its gateway and its skills
```

`make host-up` calls `host/generate-env.sh`, which writes `host/.env` (mode 600, git-ignored)
with freshly generated secrets. It never overwrites an existing one: regenerating would
invalidate the Langfuse project keys already written into the root `.env` and silently detach
the orchestrator from its own traces. Delete the file deliberately to start over.

`make host-env-sync` is the only thing that writes to the root `.env`. It rewrites exactly six
assignments — the two base URLs, the two Langfuse project keys, and the two Gateway keys — in
place, keeps every other line, and takes a timestamped backup first. `LITELLM_API_KEY` is
minted from the running proxy with `key_type: llm_api`, which is the restriction described
above; on a single-operator machine the spend key is the master key, which is the recorded
exposure rather than the intended split.

| Service | Port | Notes |
| --- | --- | --- |
| Langfuse web | 3000 | first user, org and project provisioned on start |
| LiteLLM | 4000 | the `-database` image, so `/key/generate` and `/spend/logs/v2` work |
| MinIO API / console | 9000 / 9091 | Langfuse's event and media uploads |
| Postgres | 5433 | this stack's own server; 5432 belongs to the product and is never shared |
| ClickHouse, Redis | — | not published; nothing outside the project needs them |

Three things are worth knowing before changing the file:

- **ClickHouse must be 25.12 or newer.** Langfuse 4.27.0's migration 39 declares a full-text
  index as `TYPE text(tokenizer = splitByNonAlpha)`. Every ClickHouse through 25.9 wants that
  tokenizer as a quoted literal and rejects the statement with `Code: 80 ... Expected
  literal`, which fails the migration and leaves `schema_migrations` dirty. Raising the pin is
  fine; lowering it below 25.12 is not.

- **Only one process may run the ClickHouse migration.** `langfuse-web` and `langfuse-worker`
  both attempt it at start; racing on an empty database leaves `schema_migrations` dirty and
  every later start fails with `Dirty database version N`. The web waits on the worker's
  health for that reason, and recovering from a dirty state means removing the ClickHouse
  volume, not restarting.
- **`make host-down` keeps the volumes.** Only `docker compose -f host/docker-compose.yml
  down -v` drops Langfuse's traces and re-runs the database init.

The proxy runs the committed `litellm.config.yaml` unchanged, mounted read-only, so what runs
here is what this document describes. Real inference still needs a real provider key in
`host/.env`; without one the proxy starts, answers `/health` and lists `/v1/models`, which is
everything the harness `doctor` check asserts.

## LiteLLM

`litellm.config.yaml` in this directory is the starting configuration. Start the proxy with it:

```bash
export LITELLM_MASTER_KEY=…            # generated once, kept in the host keychain
export LITELLM_OTEL_V2=true            # required: the v1 exporter drops the langfuse_* headers
export LANGFUSE_PUBLIC_KEY=…  LANGFUSE_SECRET_KEY=…  LANGFUSE_HOST=http://localhost:3000
export OMLX_BASE_URL=http://localhost:8000/v1
litellm --config host/litellm.config.yaml --port 4000
```

`model_list` is where a model becomes available to a harness. Hosted models are their provider
route; local models are `openai/<alias>` pointed at oMLX with `use_chat_completions_api: true`,
which is what lets Codex's `/v1/responses` calls bridge to a server that speaks chat
completions. `litellm_settings.callbacks: ["langfuse_otel"]` with `LITELLM_OTEL_V2=true` is what
puts the Gateway's own spans on the same Langfuse trace as the harness's (AD-11).

### The two keys

The Gateway needs two, and they are not interchangeable (PRD §8 item 5, AD-5):

| Contract variable | What it is | Who gets it |
| --- | --- | --- |
| `LITELLM_API_KEY` | a virtual key generated with `key_type: llm_api` — model routes only | every harness process, through `HARNESS_ENV_CONTRACT` |
| `LITELLM_SPEND_KEY` | the master key, or a key with the `proxy_admin_viewer` role | backend-api only, to read `/spend/logs/v2` |

```bash
curl -sX POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"key_type": "llm_api", "key_alias": "orchestrator-harnesses"}'
```

`key_type: llm_api` restricts the key to the model routes, so a harness holding it cannot read
another Run's spend. The spend key is the opposite: it reads every user's rows and never enters
a harness environment. Putting the master key in both places works and is a recorded exposure,
not the intended setup.

#### Verified 2026-09-08 (story 5.11)

The separation was checked by calling the running proxy with each key in turn, not inferred
from the configuration. Both commands below are the ones to re-run after rotating a key.

```bash
# 1. mint the harness key (model routes only). Keep the returned `key` as LITELLM_API_KEY.
curl -sX POST http://localhost:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"key_type": "llm_api", "key_alias": "ai-orchestrator-harness"}'

# 2. prove it can reach the model routes …
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $LITELLM_API_KEY" http://localhost:4000/v1/models          # 200

# 3. … and cannot reach spend.
curl -s -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer $LITELLM_API_KEY" \
  "http://localhost:4000/spend/logs/v2?start_date=2026-09-01&end_date=2026-09-09"      # 403

# 4. prove the spend key can.
curl -s -w '\nHTTP %{http_code}\n' \
  -H "Authorization: Bearer $LITELLM_SPEND_KEY" \
  "http://localhost:4000/spend/logs/v2?start_date=2026-09-01&end_date=2026-09-09"      # 200
```

Step 3's body is the proxy's own words, and is what "the harness key cannot read spend" means
in practice:

```json
{"detail":"Virtual key is not allowed to call this route. Only allowed to call routes: ['llm_api_routes']. Tried to call route: /spend/logs/v2"}
```

`start_date` and `end_date` are required by `/spend/logs/v2`; omitting them answers `400`, not
`401`, which is why a probe that omits them proves nothing about authorisation.

### Upstream provider keys are not optional for a readiness run

`host/.env` ships `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `OMLX_API_KEY` as `not-set`, and
its own comment says the proxy still starts, answers `/health` and lists `/v1/models` without
them — which is all `scripts/harness/<name>.sh doctor` checks. That is enough to bring the
stack up and **not** enough to run a harness: every entry in `model_list` fails at the first
completion. Observed 2026-09-08 with the harness key:

| Model | Result |
| --- | --- |
| `claude-sonnet-4-6` | `401` — upstream Anthropic: `invalid x-api-key` |
| `gpt-5.4` | `401` — upstream OpenAI: `Incorrect API key provided: not-set` |
| `local-coder`, `local-general` | `404` — `OMLX_BASE_URL` resolves to the orchestrator's own API port; oMLX is not running |

So before `POST /harnesses/{name}/readiness` can reach `enabled`, at least one of these has to
be a real credential (or oMLX has to be up on a port nothing else holds). `curl -s -H
"Authorization: Bearer $LITELLM_API_KEY" -X POST http://localhost:4000/v1/messages -H
'anthropic-version: 2023-06-01' -d '{"model":"<name>","max_tokens":16,"messages":[{"role":
"user","content":"say pong"}]}'` is the one-line check that a model is actually completable —
`/v1/models` listing it is not the same thing.

Claude Code additionally asks for **its own default model** when the Template binds none; on
2.1.258 that is `claude-opus-5`, which this `model_list` does not serve, so the call fails with
`Invalid model name passed in model=claude-opus-5` even when the upstream key is good. Either
add that name to `model_list` or bind a model on the Run.

### Or authenticate on a Claude subscription instead (`CLAUDE_SUBSCRIPTION_AUTH`)

The section above needs a provider API key. If you have a Claude Max or Pro subscription and
would rather spend that than an API key, the Gateway can forward Claude Code's own OAuth
token upstream instead — this is the one path to a green `claude` readiness run that needs no
`ANTHROPIC_API_KEY` at all.

It is a *different* authentication topology, not an extra header, and the difference is which
credential holds `Authorization`:

| | API-key mode (default) | Subscription mode |
| --- | --- | --- |
| `Authorization` carries | the Gateway virtual key, via `ANTHROPIC_AUTH_TOKEN` | Claude Code's subscription OAuth token |
| the virtual key travels in | `Authorization` | `x-litellm-api-key` — because `Authorization` is taken |
| LiteLLM reaches Anthropic with | `ANTHROPIC_API_KEY` from `host/.env` | the forwarded OAuth token |

Four steps, and the first two are on this host:

1. In `host/litellm.config.yaml`, uncomment `forward_client_headers_to_llm_api: true` under
   `general_settings` and the `claude-subscription` entry in `model_list`. Restart the proxy.
2. Note what that switch does: it forwards client headers upstream for **every** route on
   this proxy, not only the Claude one. This proxy is single-tenant and reachable only from
   the orchestrator (see *Egress*), which is what makes it acceptable here.
3. Set `CLAUDE_SUBSCRIPTION_AUTH=true` in the stack's own `.env` and restart `backend-api`.
   The adapter then stops exporting `ANTHROPIC_AUTH_TOKEN` — set, it would override the
   login and the subscription would never be used — and moves the virtual key into the
   `x-litellm-api-key` header.
4. Log Claude Code in, once, inside the container:
   `docker compose exec backend-api claude login` (it prints a URL to open, and stores the
   credentials under `AGENT_HOME`, which is a named volume and survives `make down`). Then
   bind the Run to the `claude-subscription` model name — Claude Code's own default model is
   not in `model_list`, the same trap the section above describes.

**What this changes about money.** A subscription is not metered per request, so the dollar
figures LiteLLM writes to `/spend/logs/v2` are computed from its price table rather than from
anything you are billed. The Run budget, the `--max-budget-usd` cap and the FR-17 park all go
on working, and all of them are then enforcing a notional cost. Nothing in the orchestrator
changes to reflect that — deliberately, and recorded here so the numbers on screen are read
for what they are.

**Unverified end to end.** The repo half is tested
(`backend-api/tests/unit/test_harness_env_subscription.py`); the host half above is written
from LiteLLM's own guide and has not been run against a live subscription here.

## Langfuse

Langfuse 4.27.0, self-hosted with its own compose file, on port 3000. The stack sends traces to
`$LANGFUSE_BASE_URL/api/public/otel` over HTTP/protobuf, authenticated with a Basic header
derived from `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. `scripts/harness/_common.sh`
derives that header at container start; nothing writes a key into a config file.

Create one project, take its public and secret keys, and put them in `.env`.
`LANGFUSE_ENVIRONMENT` separates this instance's traces from anything else sending to the same
server.

### `events_only` mode blocks the readiness trace check (observed 2026-09-08)

This instance answers every public **read** API with

```
404 {"message":"This endpoint is not available on deployments running in Langfuse v4 events_only mode…"}
```

— `GET /api/public/traces`, `GET /api/public/traces/{id}` and `GET /api/public/observations`
alike. OTLP **ingestion** is unaffected; only reading back is gone.

That matters beyond the UI. `Tracer.attempt_observed(run_id, attempt_id)` — the readiness
check that proves the harness's spans landed under the attempt span (AD-10, AD-11, PRD §8
item 2) — is implemented as `api.observations.get_many(trace_id=…)` and answers `False` on any
query failure rather than raising (SM-3, deliberate). So on a deployment in this mode the
readiness line `trace observed` can never be `ok`, and `POST /harnesses/{name}/readiness` can
never reach `enabled`, however well tracing itself is working.

`GET /api/public/health` and `GET /api/public/projects` both still answer `200`, so a
credential check passes and gives no hint of this. Check it directly:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
  "http://localhost:3000/api/public/observations?limit=1"        # 200 = readable, 404 = events_only
```

Either run this Langfuse outside `events_only` mode, or `attempt_observed` needs a source
other than the read API. Recorded, not decided.

## oMLX

The local model server, port 8000, serving the aliases listed in `LOCAL_MODELS`. It is reached
by LiteLLM only — no container talks to it directly, which is why it has no entry in the
environment contract beyond those aliases. Raise the wired GPU limit before loading a large
model:

```bash
sudo sysctl iogpu.wired_limit_mb=43008
```

## Egress

NFR-4 limits the containers' outbound traffic to the git host, the package registries, the
Gateway, Langfuse and the model server. In the MVP this is a host firewall rule, written once
and not enforced by the containers — the allowlist below is the rule's content, and nothing in
the stack fails if it is absent.

- `github.com`, `api.github.com`, `codeload.github.com`
- `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`
- `host.docker.internal` on 4000 (Gateway), 3000 (Langfuse)

## Backups

The whole database — schemas `public` and `dbos` together, because a Run's rows and its engine
state have to be restored as one — dumped nightly into `host/backups/`, 14 days kept. The
directory is tracked; its contents are ignored (`.gitignore`).

```cron
# m h  dom mon dow
  0 3  *   *   *   cd /path/to/ai-orchestrator && ./host/backup.sh
```

```bash
#!/usr/bin/env bash
# host/backup.sh — write it once, on the host; it is not committed, because it names paths
set -euo pipefail
set -a; . ./.env; set +a
out="host/backups/orchestrator-$(date -u +%Y-%m-%d).sql"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" > "$out"
find host/backups -name 'orchestrator-*.sql' -mtime +14 -delete
```

`agent-home` is not backed up: it holds harness sessions and the BMAD skill stubs, both of which
the image rebuilds. Losing it loses resumable harness sessions, which PRD §5 accepts.
