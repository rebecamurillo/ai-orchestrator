---
title: Harness setup
kind: procedure
audience: host
---

Local agent on the host or the user only.

# Harness setup

`GET /api/v1/harnesses` is the truth: each row carries `enabled`, `failing_check`,
`version_pin`, the readiness `lines[]` and the `models` this instance offers for it.
`GET /api/v1/harnesses/{name}/probe` re-checks the CLI and its config live;
`POST /api/v1/harnesses/{name}/readiness` runs the end-to-end diagnostic, which is what
actually sets `enabled`. `api` has the shapes.

The CLIs ship in the image and run from the `harness-bin` volume (`/opt/harness-cli`). At
every start `backend-api` compares each CLI with its `*_VERSION` (`release.env`, overridden by `.env`): the image's copy
is used when it is at the pin, otherwise one `npm install` of the pin runs — so a CLI upgrade
needs no new image:

```bash
./install.sh harness claude --version 2.1.260   # codex → CODEX_VERSION, opencode → OPENCODE_VERSION
```

It writes the pin into `.env`, recreates `backend-api` (after a confirmation; `--yes` answers
it), prints that harness's start-up log lines (a `refused` one fails the command) and
the harness row. A pin equal to the current one changes nothing. `docker compose restart` never applies a pin: it keeps the
old environment. The change resets that harness's readiness, so re-run it afterwards.
A pin that cannot be installed refuses that harness alone; the API and the other harnesses
keep working. `./install.sh logs` names the harness and both versions. Put back a version
that installs and recreate. An upgrade leaves `.env` alone: a pin set there still overrides the release's.
`host/runbooks`, *Upgrade a harness CLI*, is the full runbook.
Never edit the probe's version check to make a row green.

### Claude Max/Pro subscription instead of an API key

```bash
./install.sh harness claude --subscription      # --api-key goes the other way
```

It sets `CLAUDE_SUBSCRIPTION_AUTH=true` in `.env`, prints the two lines to uncomment in
your gateway's `litellm.config.yaml` and where, runs `docker compose exec backend-api claude
login` when the stack is up (it prints a URL; the **user** completes it in a browser), restarts
`backend-api` after they confirm, then reads `GET /api/v1/harnesses` back.

What it does not do, and you must not either: edit `litellm.config.yaml`. That file is YAML a
human owns; the command prints the exact lines and the path.

Three things to carry honestly:

- **The gateway half has never been run against a live subscription.** The container half is
  unit-tested; the LiteLLM configuration is written from LiteLLM's own guide, and
  the starter's README says so in those words. Do not report it as verified.
- **`forward_client_headers_to_llm_api: true` forwards client headers upstream on every route
  of that proxy**, not only the Claude one. It is acceptable here only because the proxy is
  single-tenant and reachable from the orchestrator alone.
- **A subscription is not metered per request.** The dollar figures a Run shows are computed
  from LiteLLM's price table, not from anything the user is billed. The budget, the cap and the
  budget park all keep working, all on a notional number.

Bind the Run to the model name `claude-subscription`: Claude Code's own default model is not in
`model_list`. If the login expires, the probe runs `claude auth status` and refuses there first
— `not logged in (claude auth status)` — which is the `failing_check` doctor shows. Recover by
re-running the command.

**Codex and OpenCode have no subscription login.** They take an API key, set in
your gateway's environment. The command refuses them rather than pretending.
