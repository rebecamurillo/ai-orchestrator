---
title: Models a Run can use
kind: page
audience: any
---
# Models a Run can use

Ask the instance, never guess a model name: `GET /api/v1/harnesses/{name}/models`, or the MCP
tool `list_models`. The answer is `{harness, source, models, note, code, guide}`, and `source`
says where the list comes from.

- `litellm`: the instance's LiteLLM key's own `GET /v1/models`, read at most once per 60
  seconds. The note reads "the models this instance's LiteLLM key may use"; an empty list
  stays `litellm` with the note "LiteLLM lists no model for this instance's key".
- `configured`: the `local` harness answers `LOCAL_MODELS`, the aliases the host serves. No
  note.
- `none`: no LiteLLM gateway is configured, so the harness cannot list its models here. The
  note names the harness and carries `refusal-models-unlisted` with its page
  `errors/refusal-models-unlisted`. Ask the user for a model name the harness accepts; never
  invent one.

When a gateway is configured but cannot be read, the route answers 503 with
`refusal-models-gateway-unreachable` (page `errors/refusal-models-gateway-unreachable`). The
list is then unknown, and nothing is guessed in its place.

An unknown harness name is 404.

Changing the default models or LiteLLM's model list is local-only: it is done on the host
(`host/rules`), and no tool does it from here.

## Harness CLIs

Whether each pinned harness CLI lists its models without credentials and without a model call.
`not verified` means the CLI was absent or at another version than its pin; none applies here.

| CLI | Version observed (pin) | Command tried | Exit code | Model list without credentials | Date |
| --- | --- | --- | --- | --- | --- |
| claude | `2.1.319 (Claude Code)` (pin `CLAUDE_CODE_VERSION=2.1.319`) | none documented | n/a | no: no listing command documented | 2026-11-12 |
| codex | `codex-cli 0.167.0` (pin `CODEX_VERSION=0.167.0`) | none documented | n/a | no: no listing command documented | 2026-11-12 |
| opencode | `1.19.5` (pin `OPENCODE_VERSION=1.19.5`) | `opencode models` | 0 | yes | 2026-11-12 |

The instance does not use these commands; its answer comes from LiteLLM or `LOCAL_MODELS` (see above).

### How this was observed

Run on 2026-11-12 in a `mktemp -d` folder (`<tmp>`, removed afterwards). Every command ran as
`env -i PATH="$PATH" HOME="<tmp>" CODEX_HOME="<tmp>" XDG_CONFIG_HOME="<tmp>" TERM=dumb timeout 30 <command> </dev/null`,
so no login and no key variable of the calling environment was read. No credential was supplied.
A subcommand was run when its name or one-line description in `--help` mentioned "model" and its
own help said it prints the available models.

- claude: `claude --version` exit 0; `claude --help` exit 0. No subcommand name or description
  mentions "model", so no subcommand help and no listing command was run.
- codex: `codex --version` exit 0 (it also printed a warning that it could not create PATH
  aliases under `/tmp`); `codex --help` exit 0. No subcommand name or description mentions
  "model", so no subcommand help and no listing command was run.
- opencode: `opencode --version` exit 0; `opencode --help` exit 0; `opencode mcp --help` exit 0
  (matched on "Model Context Protocol"; it lists MCP servers, not models, so it was not run);
  `opencode models --help` exit 0 (description "list all available models", which justified
  running it); `opencode models` exit 0, three runs. It printed 9 to 12 `provider/model` names,
  all under the `opencode/` provider, and the names differed between runs. Its help says the
  list is cached from `models.dev` (`--refresh`), so the output may come from a network fetch the
  CLI made on its own; no instance was called.
