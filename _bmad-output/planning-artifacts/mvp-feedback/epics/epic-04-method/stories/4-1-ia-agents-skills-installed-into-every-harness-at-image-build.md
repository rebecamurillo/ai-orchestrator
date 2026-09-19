---
title: ia-agents-skills installed into every harness at image build
type: feature
created: '2026-09-17'
status: done
baseline_revision: b7ed41ca721396a5b722da2aa44d693ae36b89ea
review_loop_iteration: 0
followup_review_recommended: true
context: []
warnings: []
deferred:
  - summary: >-
      doctor_skill_present not extended to verify operator skills or skills-manifest.json presence
    evidence: |-
      doctor only checks for bmad-build-auto/SKILL.md; a failed operator-skill install
      passes make doctor undetected.
    location: >-
      scripts/harness/_common.sh:doctor_skill_present
    severity: medium
  - summary: >-
      install_operator_skills does not enforce SKILL.md presence before copying a skill directory
    evidence: |-
      README documents SKILL.md as required entry point but install script does not
      validate it; a skill without SKILL.md is copied and listed in the manifest but
      unusable at dispatch time.
    location: >-
      scripts/harness/_common.sh:install_operator_skills
    severity: low
  - summary: >-
      install_operator_skills reports false collision on idempotent re-install outside Docker context
    evidence: |-
      Collision detection checks all dirs already in dest; operator skills installed in a
      prior run match the source names and trigger exit 1. Only reproducible if install()
      is called manually on a machine with a prior install; does not affect docker build.
    location: >-
      scripts/harness/_common.sh:install_operator_skills
    severity: low
---

<intent-contract>

## Intent

**Problem:** Operator-authored skills have no install path; harness `install()` functions only copy BMAD stubs, so custom skills cannot ship via image rebuild, and story 4-2's `SkillCatalog` port has no `skills-manifest.json` to read.

**Approach:** Create `ia-agents-skills/` at the repo root with an authoring-contract README; add `install_operator_skills` to `_common.sh` that detects all name collisions against already-installed stubs (exit 1 listing every collision), copies operator skills, and writes `skills-manifest.json` at the harness-home level; extend claude.sh and codex.sh `install()` to call it; add a Dockerfile `COPY` layer; extend `.gitignore` per AD-16.

## Boundaries & Constraints

**Always:**
- AD-16: operator skills copy into `~/.claude/skills` AND `~/.agents/skills`; any collision between an operator skill directory name and an existing stub directory in the destination must `exit 1` with ALL colliding names named in one message
- `skills-manifest.json` lives at `$(dirname "$dest")/skills-manifest.json` (i.e. `$AGENT_HOME/.claude/skills-manifest.json` and `$AGENT_HOME/.agents/skills-manifest.json`); format: `{"skills":["name1","name2",...]}` sorted alphabetically; written after all skills (BMAD stubs + operator) are present
- `ia-agents-skills/` is committed to the repo and NOT gitignored; a change ships by image rebuild, never per Run
- Shell logic stays in `_common.sh`; per-harness scripts only call the shared function

**Block If:** Any ambiguity about the manifest format cannot be resolved from the story description and AD-16 alone.

**Never:**
- Do not call `install_operator_skills` from `opencode.sh`; OpenCode reads `~/.claude/skills` and `~/.agents/skills` which are already covered by claude.sh and codex.sh
- Do not add application-layer Python code (SkillCatalog port is story 4-2's scope)
- Do not install operator skills per Run or inject them into a running container
- Do not pin or test shipped template content

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| No operator skills | `ia-agents-skills/` has no subdirectories (only README.md) | Install succeeds; manifest written with BMAD stub names only | No error |
| Clean install | One or more skill dirs in `ia-agents-skills/`; no name matches any existing stub in dest | Skills copied; manifest contains union of stubs + operator skills, sorted | No error |
| Single collision | One operator skill dir name matches an installed stub dir in dest | `exit 1`; error message names the colliding skill | Build fails, skill name in output |
| Multiple collisions | Two or more operator skill dir names collide with installed stubs | `exit 1`; ALL colliding names listed in one message | All names in one error |

</intent-contract>

## Code Map

- `scripts/harness/_common.sh:52-63` — `bmad_install_global_skills($tools, $dest)`: installs BMAD stubs into dest; `install_operator_skills` is added immediately after (line 64+) and called after this in each harness
- `scripts/harness/claude.sh:18-21` — `install()`: extend to add `install_operator_skills /app/ia-agents-skills "${AGENT_HOME}/.claude/skills"` after the `bmad_install_global_skills` call (line 20)
- `scripts/harness/codex.sh:12-15` — `install()`: extend to add `install_operator_skills /app/ia-agents-skills "${AGENT_HOME}/.agents/skills"` after the `bmad_install_global_skills` call (line 14)
- `backend-api/Dockerfile:131-142` — fixtures COPY at line 135; harness install RUN at line 142; `COPY --chown=agent:agent ia-agents-skills /app/ia-agents-skills` inserted between those two
- `.gitignore:7` — `.claude/skills/bmad-*` already present; `.agents/skills/bmad-*` is the gap per AD-16 gitignore contract
- `backend-api/tests/unit/test_harness_scripts.py:88-96` — `_run()` helper and subprocess pattern that `test_install_operator_skills.py` follows

## Tasks & Acceptance

**Execution:**
- `ia-agents-skills/README.md` -- CREATE -- authoring contract: one directory per skill; directory name must not collide with BMAD stubs (collision fails the image build, build output names the colliding skill); every skill must have a `SKILL.md` entry point; changes ship by image rebuild only, never per Run
- `scripts/harness/_common.sh` -- ADD `install_operator_skills` function after `bmad_install_global_skills` (after line 63) -- `$1` = operator skills source path, `$2` = dest skills dir; collect ALL collision names before deciding to exit; copy each source subdir to dest; write sorted `{"skills":[...]}` JSON to `$(dirname "$2")/skills-manifest.json` enumerating every skill dir in dest
- `scripts/harness/claude.sh` -- EXTEND `install()` at line 20 -- add `install_operator_skills /app/ia-agents-skills "${AGENT_HOME}/.claude/skills"` on the line after the existing `bmad_install_global_skills` call
- `scripts/harness/codex.sh` -- EXTEND `install()` at line 14 -- add `install_operator_skills /app/ia-agents-skills "${AGENT_HOME}/.agents/skills"` on the line after the existing `bmad_install_global_skills` call
- `backend-api/Dockerfile` -- INSERT `COPY --chown=agent:agent ia-agents-skills /app/ia-agents-skills` between the fixtures COPY (line 135) and the harness install RUN (line 142) -- makes operator skills available during `agent`-user image build
- `.gitignore` -- ADD `.agents/skills/bmad-*` immediately after line 7 (`.claude/skills/bmad-*`) -- extends the gitignore contract to the Codex/OpenCode skills path per AD-16
- `backend-api/tests/unit/test_install_operator_skills.py` -- CREATE -- subprocess tests using bash + tmp dirs: (a) clean install copies skills and writes manifest containing all names sorted; (b) single-collision exits 1 and names the colliding skill in stderr; (c) multiple-collisions exits 1 and lists all names in one message; (d) empty `ia-agents-skills/` (no subdirs) produces a manifest with only BMAD-stub entries; wrapper script sources `_common.sh` then calls `install_operator_skills`

**Acceptance Criteria:**
- Given `ia-agents-skills/` contains a skill whose directory name matches an already-installed BMAD stub directory in `~/.claude/skills`, when `scripts/harness/claude.sh install` runs, then the command exits non-zero and its combined output contains the colliding skill name
- Given `ia-agents-skills/` contains two skills that both collide with BMAD stubs, when `scripts/harness/claude.sh install` runs, then the command exits non-zero and both colliding names appear in the output in a single error message
- Given `ia-agents-skills/` contains one or more skills with no name collision, when all harness install scripts run, then `$AGENT_HOME/.claude/skills-manifest.json` and `$AGENT_HOME/.agents/skills-manifest.json` each exist and each contains a `{"skills":[...]}` JSON array with all installed skill names sorted alphabetically
- Given `ia-agents-skills/` has no subdirectories (only `README.md`), when the harness install scripts run, then both manifest files exist and contain only the BMAD stub skill names; no error is raised
- Given a git working tree with BMAD stubs installed under `.agents/skills/`, when the gitignore rules are applied, then entries matching `.agents/skills/bmad-*` are ignored (symmetry with `.claude/skills/bmad-*`)

## Design Notes

`skills-manifest.json` is written at `$(dirname "$dest")/skills-manifest.json` — one level above the skills directory — so the per-harness path is `$AGENT_HOME/.claude/skills-manifest.json` and `$AGENT_HOME/.agents/skills-manifest.json`. This matches AD-16's "per harness home" phrasing and gives story 4-2's `SkillCatalog` two predictable paths to read, one per skills root.

Collision detection collects all collisions before calling `exit 1` so an operator fixing a collision sees every problem in one build, not one per rebuild.

## Verification

**Commands:**
- `make lint` -- expected: `bash -n` passes for all harness scripts; no ruff/mypy/import-linter violations
- `make test` -- expected: green including new `test_install_operator_skills.py`

## Spec Change Log

## Review Triage Log

### 2026-09-17 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 4: (high 0, medium 2, low 2)
- defer: 3: (high 0, medium 1, low 2)
- reject: 8
- addressed_findings:
  - `[medium]` `[patch]` JSON special characters in skill names could produce malformed manifest JSON — added `\` and `"` escaping in the manifest-building loop in `_common.sh`
  - `[medium]` `[patch]` No test verifying that `claude.sh`/`codex.sh install()` actually calls `install_operator_skills` — added `test_harness_install_calls_install_operator_skills` parametrized over both harnesses in `test_install_operator_skills.py`
  - `[low]` `[patch]` README listed `make up` as primary rebuild command (does not rebuild images) — fixed to `docker compose build backend-api && make up`
  - `[low]` `[patch]` Collision tests asserted `returncode != 0` instead of exactly `1` — corrected to `returncode == 1`

## Auto Run Result

Status: done

**Summary:** Created `ia-agents-skills/` at repo root with authoring-contract README; added `install_operator_skills` function to `_common.sh` with full collision detection, operator-skill copy, and sorted `skills-manifest.json` write; extended `claude.sh` and `codex.sh` `install()` to call it; added Dockerfile `COPY` layer; extended `.gitignore` with `.agents/skills/bmad-*`; added `test_install_operator_skills.py` covering all I/O matrix rows plus harness wiring.

**Files changed:**
- `ia-agents-skills/README.md` — new; operator skill authoring contract
- `scripts/harness/_common.sh` — added `install_operator_skills` function (collision detection, copy, manifest write with JSON escaping)
- `scripts/harness/claude.sh` — `install()` extended to call `install_operator_skills`
- `scripts/harness/codex.sh` — `install()` extended to call `install_operator_skills`
- `backend-api/Dockerfile` — added `COPY --chown=agent:agent ia-agents-skills /app/ia-agents-skills` before harness install RUN
- `.gitignore` — added `.agents/skills/bmad-*` (AD-16 gitignore contract extension)
- `backend-api/tests/unit/test_install_operator_skills.py` — new; 7 tests covering clean install, single collision, multiple collision, empty operator skills, gitignore symmetry, harness wiring for claude and codex

**Review findings breakdown:** 4 patches applied (0 high, 2 medium, 2 low); 3 items deferred; 8 rejected.

**Followup review recommended:** true — score 3×2 + 1×2 = 8 (≥ 5 threshold), driven by 2 medium patches (JSON escaping gap and missing harness-call test).

**Verification performed:**
- `make lint`: PASS (ruff format+lint, mypy, import-linter, env-contract, test-pairs, gen:api, tsc, eslint, prettier — all green)
- `make test`: PASS — 6308 backend tests passed (23 skipped), 1348 web-client tests passed; domain+application at 100% branch coverage

**Residual risks:**
- `opencode.sh` deliberately not wired (intent constraint); operator skills reach OpenCode via `~/.agents/skills` installed by `codex.sh`
- `doctor_skill_present` does not check operator skills or manifest (deferred)
