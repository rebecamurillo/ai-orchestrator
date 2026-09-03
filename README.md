# ai-orchestrator

An orchestrator that runs BMAD dev-loop workflows against other repositories: a Run is planned up front, executed durably, dispatches stories to a coding-agent harness (Claude Code, Codex, OpenCode), verifies with the target repository's own commands, and stops for the operator only at declared checkpoints or when an agent is blocked.

The product is specified, not yet built. Everything that decides what gets built lives under `_bmad-output/planning-artifacts/mvp/`:

| Document | Path |
| --- | --- |
| PRD (build contract, FR-1..FR-33) | `mvp/prd.md` + `mvp/addendum.md` |
| Architecture spine (binding, AD-1..AD-20) | `mvp/architecture/ARCHITECTURE-SPINE.md` |
| Epics and stories (8 epics, 66 stories) | `mvp/epics/epics.md`, `mvp/epics/epics.yaml`, one folder per epic |
| UX experience and visual system | `ux-designs/ux-v1-dev-loop-2026-08-26/`, `ux-designs/ux-ai-orchestrator-2026-08-25/DESIGN.md` |

## Setting up the BMAD method on a new machine

The repository commits the method itself (`_bmad/`: config, scripts, manifests, modules) so every clone carries the same version, **6.11.0**. Two things are per machine and git-ignored: the skill stubs Claude Code loads (`.claude/skills/bmad-*`, `.agents/skills/bmad-*`) and your personal install answers (`_bmad/config.user.toml`). Reinstall them once per machine with the steps below.

### 1. Prerequisites

- **git** with access to this repository.
- **Node.js 22 or newer** (the installer runs through `npx`). With nvm: `nvm install 22 && nvm use 22`.
- **uv** (the BMAD scripts run with `uv run`): `brew install uv` on macOS, or see https://docs.astral.sh/uv/.
- **Claude Code** CLI, logged in: https://docs.anthropic.com/en/docs/claude-code — `npm install -g @anthropic-ai/claude-code`, then `claude` and `/login` once.

### 2. Clone and install the skill stubs

```bash
git clone <this repository> ai-orchestrator
cd ai-orchestrator
npx --yes bmad-method@6.11.0 install --directory . --modules bmm --tools claude-code,codex --yes --user-name OptimAI-team
```

The installer writes the skill stubs into `.claude/skills/` (read by Claude Code) and `.agents/skills/` (read by Codex and OpenCode), and regenerates `_bmad/config.user.toml` with your answers. Pin the version exactly: a different `bmad-method` version rewrites the installer-managed files under `_bmad/` and shows up as a diff.

### 3. Check

```bash
git status                                   # must be clean: the committed _bmad/ files match 6.11.0
ls .claude/skills | grep -c '^bmad-'         # 49 skills
uv run _bmad/scripts/resolve_config.py --project-root .   # prints the merged config as JSON
```

Then open Claude Code in the repository and type `/bmad-help`. It reads the planning artifacts and tells you where the project stands and which skill comes next.

### Notes

- Team-wide overrides go in `_bmad/custom/config.toml` (committed). Personal ones go in `_bmad/custom/config.user.toml` (ignored). Never edit `_bmad/config.toml` or `_bmad/config.user.toml` by hand: the installer regenerates them.
- To change an install answer (name, language), re-run the same `install` command with the new flags; prior answers are the defaults.
- Copies of the skills under `~/.claude/skills/` are optional. This repository relies on the project-level ones in `.claude/skills/`.

## Where the work stands

Epics and stories are complete (`mvp/epics/`). Next: `bmad-sprint-planning` to generate the tracking file, then build Epic 1 (repository foundation and quality gates) with `bmad-build`; Epics 2 to 8 are written for unattended `bmad-build-auto` dispatch, one brief per story.
