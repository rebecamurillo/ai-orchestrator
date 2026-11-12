---
title: Connecting to an instance
kind: page
audience: any
---
# Connecting to an instance

The orchestrator runs BMAD dev-loop workflows against git repositories: a Run plans every
step up front, dispatches stories to a coding-agent harness (claude, codex, opencode),
verifies with the target repository's own commands, and stops only at declared checkpoints
or when an agent is blocked. You talk to it over HTTP; humans watch the same Runs in its
web UI.

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

## Connection

Two values, from the project's environment (`.env` or exported):

- `ORCHESTRATOR_BASE_URL` — default `http://127.0.0.1:8000`
- `ORCHESTRATOR_TOKEN` — the single bearer credential

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

## Handshake

Do this before anything else, every session: call the `version` tool, or `GET /api/v1/version` →
`{app_version, kit_version, bmad_version, harness_versions{}}`, first, then read `/llms.txt`. A 404
means an instance older than the route: fall back to `GET /api/v1/ping`, say so, and treat the version
as unknown.

When the release a project was set up for differs from the instance's `app_version`, tell the user
exactly that and continue the work — a difference is reported, never a stop.

`bmad_version` is the BMAD release installed in the instance's harnesses (AD-16). The
orchestrator does not compare it with any repository: preflight has no method-version line.
A BMAD skill renders from the target's own `_bmad/`, so a repository whose manifest names
another version, or none, may render a different workflow than the one you authored for.

For the instance's host agent, a release difference is often the problem it was called about: report
it as the finding and reconcile it with `./install.sh upgrade` (`host/upgrade`). `./install.sh doctor`
needs no handshake and is the first move when the API does not answer (`host/day-2`).
