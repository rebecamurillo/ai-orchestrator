# SPEC — Epic 4: The method opens

Operator-authored skills install into every harness at image build; `agent` steps dispatch any skill or a custom prompt; the spec-gate reviews the spec folder once before the loop; the epic tail pushes before review, generates and runs e2e, and writes a retrospective; `story-run@1` and `task@1` open small entries. Realises features F7 (first — it carries F6's and F8's skills), F6, F8, F11 (IMP-001 B, IMP-002 B1).

## Authority order

1. `ARCHITECTURE-SPINE.md` (2026-09-15) — AD-2, AD-9 (`compose_prompt` the only builder), AD-15 (validator), AD-16 (install path, manifest, `SkillCatalog`), AD-17/FR-31, AD-19. Disagreement → `blocked`.
2. `prd.md` (2026-09-15) — FR-5, FR-14, FR-16, FR-31, §5 non-goals (both softenings), NFR-8.
3. `stories.yaml` in this folder.

## Scope

- Repository-root `ia-agents-skills/` (new; README states the authoring contract) copied beside the BMAD stubs into `~/.claude/skills` and `~/.agents/skills` at image build; `scripts/harness/*.sh install` extended; the build **fails** on a name collision and writes `skills-manifest.json` (the union, per harness home); the gitignore contract extends to the corresponding folders; changes ship by image rebuild, never per Run.
- `SkillCatalog` port exposing the manifest read-only (+ shared fake); pre-flight installed-skill line; `validate.py` stays pure.
- DSL: an `agent` step's `with` declares **exactly one** dispatch form — `skill` (string, the shipped form) or `prompt` / `prompt_file` (read from the working folder); zero or several is a validation error; both forms carry `expect {files, status_in}`; `compose_prompt` gains the second form; `validate.py` also rejects all-digit step ids (guards AD-15's dot-index bijection) and accepts `only:` on `for_each` (plan-time filter).
- `spec-gate` skill (authored in `ia-agents-skills/`) dispatched by the shipped `epic` template after baseline, before the story loop; outcomes: clean → proceed; open questions → one human gate listing every question; formatting → fixed and committed `spec: gate fixes (orchestrator)`.
- Epic tail: push + compare link **before** the final done checkpoint; then `bmad-qa-generate-e2e-tests` dispatch → repository e2e command (`shell`, deterministic) → bounded `on_fail: {redispatch, max}`; then `bmad-retrospective` (headless) into the working folder.
- `story-run@1` (one story via `only:`) and `task@1` (pasted `intent`, plan gate always on, resumed by Continue; never API ingestion).

## Out of scope

The stall/`mode` machinery (epic 3); saved runs (epic 5); any per-story retro build (recorded follow-up only); fetching issues by API (IMP-002 B2, deferred); any second data-collection path beside the trajectory row (AD-19).

## Rules that bind every story

- Anchors read-only; shipped templates are **exemplars** — no unit or e2e test pins their content (standing exemplar-freeze strategy); each template change keeps `templates/*.yaml` valid against `validate.py`.
- TDD with shared fakes; generated contract only; tests the epic's own agents create are not in the frozen set (FR-31) — the e2e generation step must not trip protected paths.
- Skill dispatch is harness-portable: a skill name + an output file contract; nothing harness-specific in application code (AD-10).
- Voice on all gate copy (`spec: gate fixes (orchestrator)` verbatim; questions listed as facts).

## Verification

`make lint` · `make test` · `make e2e-api` · `make e2e-ui` green after every story; the epic's e2e pass exercises: a `skill:`-form and a `prompt:`-form dispatch, the validation error on both-or-neither, an uninstalled-skill pre-flight refusal, and a `story-run@1` plan containing exactly one story frame.
