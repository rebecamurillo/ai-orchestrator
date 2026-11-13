# MCP: the enhanced path, not the floor

The instance serves the Model Context Protocol at `$ORCHESTRATOR_BASE_URL/mcp`, as a route on
backend-api behind the same `ORCHESTRATOR_TOKEN` as every other call. Its tools are thin: each
one is a single REST operation of the published contract, so there is nothing MCP can do that
the API cannot, and nothing it does differently. MCP and REST stay one operation each.

**The guide is the floor.** Without MCP, an agent reads the same rules over `GET /llms.txt` and
`GET /guide/{id}.md`; with MCP, `read_guide` reaches every page. Harness support for remote MCP
differs, so a harness without it loses no capability.

## What the installer does with these files

The three files are the templates `kit/install.sh` renders: the base URL is written as a
literal, the token as a variable reference (`${VAR}`, `bearer_token_env_var`, `{env:VAR}`),
never as a value. The installer merges the rendered block into the harness's own file and keeps
every other server and key as it is:

| Template | Merged into | `--harness` |
| --- | --- | --- |
| `claude.json` | `.mcp.json` in the project (`~/.claude.json` with `--home`) | `claude` |
| `codex.toml` | `${CODEX_HOME:-~/.codex}/config.toml` | `codex` |
| `opencode.json` | `opencode.json` in the project | `opencode` |

A file that already declares `orchestrator` is kept as it is. An `opencode.jsonc` is not
written to; the installer prints the block to add by hand. Restart the harness afterwards;
`/mcp` in a Claude Code session and `codex mcp list` show the server. Remote (streamable-HTTP)
MCP support is version-dependent in Codex: a build without it does not list the server, and the
guide over `/llms.txt` needs nothing.
