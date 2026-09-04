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

## Langfuse

Langfuse 4.27.0, self-hosted with its own compose file, on port 3000. The stack sends traces to
`$LANGFUSE_BASE_URL/api/public/otel` over HTTP/protobuf, authenticated with a Basic header
derived from `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`. `scripts/harness/_common.sh`
derives that header at container start; nothing writes a key into a config file.

Create one project, take its public and secret keys, and put them in `.env`.
`LANGFUSE_ENVIRONMENT` separates this instance's traces from anything else sending to the same
server.

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
