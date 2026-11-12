# Setup

`setup/` is the client's. The setup runner reads it at install, at upgrade and on demand,
and records the result in `.orchestrator/setup-run.json` inside the agent home.

## What runs, in which order

1. **BMAD** — `bmad/install.sh`, when `setup/bmad.choice` reads `installed` (a missing file
   reads `installed`); with `removed` the entries BMAD recorded are deleted.
2. **Your scripts** — every executable `*.sh` directly under `setup/`, in name order. A file
   in a subfolder (`examples/`) never runs; a file that is not executable is skipped.
3. **The operator skills** of the image.
4. **The catalog** — `skills-manifest.json` per harness is rewritten.
5. **The record**.

A script is stopped after 600 seconds (`SETUP_SCRIPT_TIMEOUT`). A script that exits non-zero
is reported failed in the record; the next scripts still run.

## What a script gets

- The working directory `/client-setup`, this folder's `setup/`.
- `HOME=/home/agent`, and the asset folders of each harness under it:
  - claude: `.claude/skills`, `.claude/agents`, `.claude/commands`
  - codex: `.agents/skills`, `.codex/prompts`
  - opencode: `.config/opencode/skills`, `.config/opencode/agents`, `.config/opencode/commands`
- `ORCH_SETUP_TRIGGER`: `install`, `upgrade`, `on-demand` or `reset`.
- Internet access.
- No secret, no login, no database and no API of the orchestrator.

Exit 0 is success. The log of each script is `logs/setup/{timestamp}/{script}.log`.

## A clash

The product owns BMAD's recorded entries, every `bmad-*` name and the image's operator
skills. A script that changes or adds one of them has it restored (or removed) after the
script ends, and the script is reported failed with the entry named in the record.

## Copying files into the harnesses

`examples/copy-folder.sh` copies each entry of `setup/assets/<harness>/<asset dir>/` into
`$HOME/<asset dir>`, for claude, codex and opencode. To use it:

1. Copy it to `setup/10-copy-folder.sh` and `chmod +x` the copy.
2. Put files under `setup/assets/<harness>/<asset dir>/`, for example
   `setup/assets/claude/.claude/skills/my-skill/SKILL.md`.

The script records what it copied in `$HOME/<asset dir>/.copy-folder-installed`. An entry
it copied before and that is no longer in `setup/assets/` is removed. An entry of
`setup/assets/` replaces the entry of the same name in `$HOME/<asset dir>`, whoever put it
there; any other entry it did not copy is never touched. Without `setup/assets/` it exits 1 and writes nothing.
