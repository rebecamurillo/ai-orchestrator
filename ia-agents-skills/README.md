# ia-agents-skills — Operator Skill Authoring Contract

This directory holds operator-authored skills that are installed into every harness at image build time. Changes ship by rebuilding the image; there is no per-Run install path.

## Rules

- **One directory per skill.** Each skill lives in its own subdirectory directly under `ia-agents-skills/`. Files at the root (like this `README.md`) are ignored by the install script.
- **Entry point required.** Every skill directory must contain a `SKILL.md` file. That is the entry point the harness discovers.
- **No name collision with BMAD stubs.** The directory name must not match any BMAD stub directory already installed in the destination skills directory (`~/.claude/skills` or `~/.agents/skills`). A collision causes the image build to fail and the build output names every colliding skill in one message.
- **Ships by image rebuild only.** To add, update, or remove a skill: edit this directory and rebuild the image. Skills are never injected into a running container or installed per Run.

## Install targets

The install script (`scripts/harness/_common.sh: install_operator_skills`) copies every subdirectory here into:

- `~/.claude/skills` (read by Claude Code)
- `~/.agents/skills` (read by Codex and OpenCode)

A `skills-manifest.json` is written one level above each skills directory after all skills (BMAD stubs and operator skills) are present. Its format is `{"skills":["name1","name2",...]}` sorted alphabetically.

## Adding a skill

1. Create a subdirectory here: `ia-agents-skills/<your-skill-name>/`
2. Add a `SKILL.md` entry point inside it.
3. Rebuild the backend image: `docker compose build backend-api`, then `make up` to restart.
