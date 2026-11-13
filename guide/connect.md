---
title: Connecting to an instance
kind: page
audience: any
readme: agents
---

The orchestrator runs BMAD dev-loop workflows against git repositories: a Run plans every
step up front, dispatches stories to a coding-agent harness (claude, codex, opencode),
verifies with the target repository's own commands, and stops only at declared checkpoints
or when an agent is blocked. You talk to it over HTTP; humans watch the same Runs in its
web UI.

### What you need

- the instance address, `ORCHESTRATOR_BASE_URL` — default `http://127.0.0.1:8000`;
- optionally the web address, where humans watch Runs (the installer's `--web-url`);
- the token, `ORCHESTRATOR_TOKEN` — the single bearer credential — in an environment variable.

`api` is the endpoint reference — read it when you need exact
request fields. `spec-folder` is the format of the files epic and
initiative Runs read from the target repository (`epics.yaml`, `stories.yaml`,
`SPEC.md`) — **read it before authoring or reviewing those files: there are two
initiative flavors and each reads different `epics.yaml` fields.**
`workflows/customize` is how to customize a workflow template — read it before
editing or authoring one. `projects` is what every Project and
Repository field does and what to confirm with the user before saving one.
`runs/first-run` is the demo: one trivial story that
proves the whole pipeline on a freshly wired project — run it before the first real Run.

### Installing the bootstrap

Run this from inside the project repository, with the two values exported:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness <h> --base-url "$ORCHESTRATOR_BASE_URL"
```

The bootstrap comes out of the instance that answered. Flags:

- `--harness claude|codex|opencode|all` — which agent CLI to set up (default `all`);
- `--base-url URL` — the instance address (overrides `ORCHESTRATOR_BASE_URL`);
- `--web-url URL` — the web address;
- `--token-var NAME` — the environment variable that holds the token, when it is not
  `ORCHESTRATOR_TOKEN`;
- `--project DIR` or `--home` — install into a project (default the current directory) or into
  the user's home;
- `--token` is refused: the installer writes no token, and it leaves `.env` alone.

It writes `.claude/skills/orchestrator/SKILL.md` and/or `.agents/skills/orchestrator/SKILL.md`,
the MCP configuration for each harness, and `.orchestrator/bootstrap.json`, then probes
`/api/v1/version`. From a checkout or the deploy folder, `kit/install.sh` uses the files beside it
and downloads nothing.

### Where the token lives

Export `ORCHESTRATOR_TOKEN` in the shell, or set it in the harness's environment. A project `.env`
is not read by the harness. The configuration the installer writes names the variable, never its value.

### The MCP configuration per harness

- claude: `.mcp.json` in the project, or `$HOME/.claude.json` with `--home`;
- codex: `${CODEX_HOME:-$HOME/.codex}/config.toml`, table `[mcp_servers.orchestrator]` with
  `bearer_token_env_var`; per user;
- opencode: `opencode.json`; when the project has `opencode.jsonc`, no `opencode.json` is written
  and the installer prints the block to add to it by hand.

An existing `orchestrator` entry is left as it is. What each harness supports is the page
`harness-support`.

### The host agent

The instance's host agent installs its own skill from the deploy folder with
`kit/install.sh --project .` (`host/day-2`).

### Moving from the beta.4 kit

A project set up with the beta.4 kit stops at its first upgrade, because that kit's skills hold the old
version stop. Reinstall once with this installer: it removes those skills, `.orchestrator/bin/` and
`kit.json`. After that no upgrade needs a reinstall.

### The one-token risk

There is one token. Every tool added over MCP widens what that one token can do. This is accepted
for the owner's own projects; scoped tokens are a later initiative.

### Talking to the API

Every call: `Authorization: Bearer $ORCHESTRATOR_TOKEN`. The handshake below is what proves
the pair; `GET /api/v1/ping` proves the token alone and is the fallback for an instance
older than `/api/v1/version`.

`GET /healthz` needs no token (liveness only). Errors are RFC 9457
`application/problem+json`: `{type, title, status, detail, errors[]}` — read `detail` and
`errors[]` before retrying anything. Lists are `{items, next_cursor}`. Ids are UUIDs;
money is a decimal string in USD.

The web UI lives on the same host (default port 4321). The deep link for one Run is
`/workflows/{run_id}` — hand it to the user whenever you name a Run.

The instance side of connecting a project is `./install.sh doctor` green first (`host/day-2`); the
Project, Repository, clone check and `repo-init` are `projects`.

### Handshake

Do this before anything else, every session: call the `version` tool, or `GET /api/v1/version` →
`{app_version, bootstrap_contract, guide{index, page_url, resource}, kit_version, bmad_version, bmad_installed, harness_versions{}}`, first, then read `/llms.txt`. A 404
means an instance older than the route: fall back to `GET /api/v1/ping`, say so, and treat the version
as unknown. `kit_version` is always `null`.

When the release a project was set up for differs from the instance's `app_version`, tell the user
exactly that and continue the work — a difference is reported, never a stop.

`bmad_version` is the BMAD release installed in the instance's harnesses (AD-16). The
orchestrator does not compare it with any repository: preflight has no method-version line.
A BMAD skill renders from the target's own `_bmad/`, so a repository whose manifest names
another version, or none, may render a different workflow than the one you authored for.

For the instance's host agent, a release difference is often the problem it was called about: report
it as the finding and reconcile it with `./install.sh upgrade` (`host/upgrade`). `./install.sh doctor`
needs no handshake and is the first move when the API does not answer (`host/day-2`).

### Reading the guide

The guide is open: `/llms.txt` is the index, and `/guide/{id}.md` is one page. Over MCP, the tool
`read_guide` reads it on every harness: with no id it returns the index, with a page id it returns
that page. A harness that supports resources also lists each page as `guide://{id}`, and each
procedure page is a prompt named by its id with `/` replaced by `.` (`runs/launch` is `runs.launch`).

### Contract differences

Compare the `version` answer's `bootstrap_contract` with the number the installed bootstrap states.
When the answer's number is above it, tell the user, naming the code `refusal-bootstrap-contract`
and the page `errors/refusal-bootstrap-contract`, and continue: the installed bootstrap keeps
working, and re-running the installer moves it to the newer contract when convenient. A release
difference is never a stop.
