# MCP: the enhanced path, not the floor

The instance serves the Model Context Protocol at `$ORCHESTRATOR_BASE_URL/mcp`, as a route on
backend-api behind the same `ORCHESTRATOR_TOKEN` as every other call. Its tools are thin: each
one is a single REST operation of the published contract — `version`, `list_templates`,
`get_template`, `preflight_run`, `create_run`, `get_run`, `get_run_detail`, `wait_run_events`,
`send_signal`, `list_queue`, `list_projects` — so there is nothing MCP can do that the API
cannot, and nothing it does differently.

**The `orchestrator` skill remains the floor.** Harness support for remote MCP differs, and the
rules that matter — handshake first, pre-flight before creating a Run, one budget decision per
Run made by a human, Signals chosen from `admitted_signals` — are the skill's, stated in prose
that every harness reads. The tool descriptions repeat them, but a harness without MCP loses no
capability by reading the skill instead. Configure MCP because typed tools are pleasanter than
`curl`, not because anything requires it.

**These files are not installed for you.** `kit/install.sh` projects skills; wiring an MCP
server edits a file that is yours — a project's `.mcp.json`, your `~/.codex/config.toml`, your
`opencode.json` — and often holds servers of your own. Copy the snippet, keep your existing
entries, and restart the harness.

## `claude.json` → the project's `.mcp.json`

Merge the `mcpServers.orchestrator` block into `.mcp.json` at the project root (or into
`~/.claude.json` for every project). Claude Code expands `${VAR}` from the environment, so the
token stays in `.env`/your shell and never in the file. Check it with `/mcp` in a session.

## `codex.toml` → `~/.codex/config.toml`

Append the `[mcp_servers.orchestrator]` table. `bearer_token_env_var` names the variable rather
than carrying the token. Codex reads a literal `url`, so replace the default
`http://127.0.0.1:8000` with the instance's base URL by hand. Remote (streamable-HTTP) MCP
support is version-dependent in Codex: if `codex mcp list` does not show the server, you are on
a build without it — use the skill, which needs nothing.

## `opencode.json` → the project's `opencode.json`

Merge the `mcp.orchestrator` block. opencode substitutes `{env:VAR}` at load time. `enabled:
false` turns it off without deleting it.
