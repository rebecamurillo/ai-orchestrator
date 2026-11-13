---
title: MCP support by harness
kind: page
audience: any
---
# MCP support by harness

Whether each pinned coding-agent CLI asks an MCP server for its tools, resources and prompts.
`yes` means the CLI sent that method to a stub server; `not observed` means the stub's log held
`initialize` but not that method; `not verified` means no result: no `initialize` in the log, the
CLI absent, or the CLI at another version than its pin; `documented` means the vendor's
documentation states it and it was not run here.

| Harness | CLI version observed | Tools | Resources | Prompts | Evidence |
| --- | --- | --- | --- | --- | --- |
| claude | not run here | documented | documented | documented | Claude Code MCP documentation, not run here: tools as MCP tool calls, resources as `@` mentions, prompts as `/mcp__server__prompt`. |
| codex | `codex-cli 0.167.0` (pin `CODEX_VERSION=0.167.0`) | not verified | not verified | not verified | Exit 124 (timeout); no log file, so the CLI never started its MCP client. Output ended at "Reading additional input from stdin...". |
| opencode | `1.19.5` (pin `OPENCODE_VERSION=1.19.5`) | not verified | not verified | not verified | Exit 124 (timeout); no log file, so the CLI never started its MCP client. No output. |

Every harness reads every page through `read_guide`.

## How this was observed

Run on 2026-11-12 in a `mktemp -d` folder (`<tmp>`, removed afterwards) from the repository
(`<repo>`), with no login and no change outside `<tmp>`. The server was
`<repo>/scripts/mcp_stub_server.py`, which appends each received method to its `--log` file.

- codex: `<tmp>/config.toml` declared `[mcp_servers.stub]` with `command = "python3"` and
  `args = ["<repo>/scripts/mcp_stub_server.py", "--log", "<tmp>/codex.log"]`. Command, run from
  `<tmp>`: `CODEX_HOME="<tmp>" timeout 90 codex exec --skip-git-repo-check "List the MCP resources and prompts you can see, then stop."`.
  Exit code 124. `<tmp>/codex.log` was never created, so the methods logged are none.
- opencode: `<tmp>/opencode/opencode.json` declared `mcp.stub` as `{"type": "local", "command":
  ["python3", "<repo>/scripts/mcp_stub_server.py", "--log", "<tmp>/opencode.log"], "enabled": true}`.
  Command, run from `<tmp>`: `XDG_CONFIG_HOME="<tmp>" timeout 90 opencode run "List the MCP resources and prompts you can see, then stop."`.
  Exit code 124. `<tmp>/opencode.log` was never created, so the methods logged are none.

Neither CLI reached its MCP client within 90 seconds in this environment, so nothing is claimed
about them beyond the row above.
