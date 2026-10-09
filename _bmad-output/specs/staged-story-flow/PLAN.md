# Staged story flow — plan (2026-10-06)

Split the one `bmad-build-auto` session per story into three sessions — **plan → implement → review** — each on its own model, and make that the shipped default for the hub flow (`initiative-hub` → `initiative-hub-epic` → `initiative-hub-story`) and the single-repo flow (`epic` → `story`). Motivation (Operator, 2026-09-30 and 2026-10-06): one-session builds run up to an hour, long sessions hallucinate on context, and low-context models fail long instruction sets. Source material: `templates/drafts/story-staged.yaml` (prompts, marker contract, sizing rule).

Status: plan, nothing built. Decisions marked **D-n** need the Operator; everything else follows from them.

## 1. What the shipped story becomes

| row | kind | model | gate | routes on |
| --- | --- | --- | --- | --- |
| `sync` | git.sync | — | deterministic | — |
| `plan` | agent, skill `story-plan` | `{{plan_model}}` | liveness | marker `{spec_folder}/stories/.auto/{id}-01-plan.md`: `done` / `blocked` / `ready-for-dev` (checkpoint when `story.spec_checkpoint`) |
| `implement` | agent, skill `story-implement` | `{{build_model}}` | liveness | marker `…/{id}-02-implement.md`; carries `prompts.redispatch` |
| `verify` | shell `{{repository.unit_test_command}}` (hub: `{{test}}`) | — | deterministic | `on_fail: {redispatch: implement, max: 2}` |
| `review` | agent, skill `story-review` | `{{review_model}}` | liveness | marker `…/{id}-03-review.md` |
| `commit-guard` | git.commit | — | deterministic | AD-17 protected-path check, as today |

"Three parts" = the three agent sessions. The deterministic `verify` row sits between implement and review exactly as it sits after `build` today. The Jev `decide` rows and the `when:`-routed light/deep review pair of the draft are **not** in this scope (they need two new step kinds and the PoC on commit 7a666ce is untested) — see follow-ups.

Per-row settings: `retry: {max: 1, resume_session: true}` on each agent row; timeouts plan 30 / implement 90 / review 45 min; `stall_min` equal to the timeout on `plan` and `review` (read-heavy phases write no files, and the stall detector watches files — a healthy review has been SIGTERM'd before).

The spec checkpoint keeps today's mechanism: `pause_when: story.spec_checkpoint` on `plan`, a `halt` clause, `checkpoint: [ready-for-dev]`. The `.answers/` archive, retry prompt and `misconfigured_when` sentences all keep working because routing stays file-based per row.

## 2. Decisions

**D-1 — prompts live in three operator skills, not inline `prompt:` text.** `ia-agents-skills/story-plan`, `story-implement`, `story-review`, each a `SKILL.md` with `args: {folder, story_id}` on the `spec-gate` precedent (no `workflow.md`, so `agent_render` skips rendering). Templates dispatch them with the existing skill form and the same dispatch sentence. Why not the draft's inline prompts:
- Under `workdir` (every hub story row) only the dispatch sentence gets `spec_folder` absolutised (`steps/agent_workdir.py::prompt_scope`); an own-text `prompt:` is sent verbatim (`agent_prompt._base`), so a submodule-rooted agent would be handed a hub-relative path. Fixing that means a new `_fill` pass over own text — an orchestrator change for no gain.
- The fake harness keys its scenarios off that sentence (`fake/scenario.py::DISPATCH_PATTERN`); own-text rows would break `make e2e` for every story row.
- Pre-flight's installed-skill line proves the method is present before a Run starts; inline text proves nothing.
- Prose stays Template-declared where the 2026-09-27 ruling put it: the dispatch/answer/halt/redispatch clauses are in the file; the method is in the skill, as for `spec-gate` and `bmad-build-auto` today.
Cost: the method ships by image rebuild, not by a template save (`ia-agents-skills/README.md`). The prompt text is lifted from the draft (plan: spec shape, size rule, marker; implement: tests first, baseline_revision, marker, redispatch handling; review: triage categories, patch/bad_spec/intent_gap/defer, marker).

**D-2 — markers under `stories/.auto/`, not the spec file.** An `answer` on a blocked row archives the row's first `expect.files` match to `.answers/` and re-dispatches fresh (`agent_answer.py`). Routing `implement`/`review` on the spec file would archive the spec itself on a block. The markers are small, one per stage, overwritten on retry, and committed by `commit-guard` (hub: swept by `commit-retro` with the rest of the hub spec folder). The spec file keeps `status:` for the planner's already-done skip, the trajectory's `story_file`, and the UI.

**D-3 — review is sized by prose, on one model.** `story-plan` writes `size: S | M | L` into the spec frontmatter (the draft's rule); `story-review` re-sizes from the real diff (may raise, never lower) and scales its own method: S one pass, M three passes (correctness, edge cases, verification gaps), L the three passes plus the lens set run as subagents when the harness has them and sequentially otherwise — self-contained, never reading `bmad-build-auto`'s step files. `bad_spec` and `intent_gap` **block**; the review never reverts or re-implements. Paying for the strong model only on L needs the `when:` row and a decision step — follow-up F-1.

**D-4 — three model inputs with a declared fallback to `model`.** Every file in both chains declares `plan_model`, `build_model`, `review_model` (`type: string, required: false, default: "{{model}}"`) and passes them down; `model` stays the Run-level field, still used by `spec-gate`, `gen-e2e`, `retro`. This needs orchestrator change **O-1**, because today a declared `default` is validated (`templates/inputs.py`, `expressions._check_defaults`) and then ignored by the planner (`plan.py::root_scope` binds only what the Run carries; `epic.yaml`'s own `done_checkpoint` comment records this). Without O-1 a blank per-stage field falls to the harness's own default model, which on a Gateway install is the documented "Invalid model name" failure (README troubleshooting) — a trap for every Run that sets only `model`. Readiness (`harness_readiness.py`) passes only `branch`, `spec_folder` and `model`, so it needs the fallback too; product code naming the three inputs is ruled out (no template input names in code, 2026-09-30). Rejected alternatives: required inputs (readiness breaks); blank = harness default, documented (the trap above).

**D-5 — the shipped files are edited in place, no new template names.** `seed_shipped` inserts a changed file as the next version by content hash on first boot; callers are unpinned since 34d326b, so `epic` and `initiative-hub-epic` follow the new `story` / `initiative-hub-story` at plan time. New installs get the split out of the box; upgraded installs get it on the first boot of the new image, above any Operator-saved version (already documented in `deploy/README.md`, "Editing the workflow templates"). The `version:` header stays `1` (seeding ignores it). Prerequisite: merge `feat/unpinned-template-callees` to main first (gates green on 2026-10-02; `make e2e` still owed) — without it the hub chain keeps pinning `initiative-hub-story@1`. No `DBOS_APPLICATION_VERSION` bump: the walker's step sequence does not change.

**D-6 — readiness runs the split too.** `READINESS_TEMPLATE=epic` dispatches three real sessions on the HELLO.md fixture instead of one. It proves the plumbing better (three session ids, three attributions) and costs roughly three cheap dispatches; `harness_readiness_evaluate` already selects "the last done agent row" by kind. If the Operator wants readiness to stay one dispatch, the alternative is a dedicated readiness template named in `READINESS_TEMPLATE` — not recommended, it would be the one shipped file still running the old method.

## 3. Orchestrator changes (small, each its own story, TDD)

**O-1 — planner applies declared input defaults.** `root_scope` (root inputs) and the callee binding in `rows.py`/`calls.py` bind a declared default when the input is unbound or blank, resolving `{{ }}` against the inputs already bound, one pass. Validator rule: a default may reference only inputs that declare no default themselves (`expressions._check_defaults` is the hook). Unit tests under `tests/unit/application/templates/` on fixture templates the test owns; `harness`'s `default: claude` is unaffected (always bound by `create_run`). Spine: the DSL `default?` cell and AD-7 gain one sentence — Operator paste, anchor. The `done_checkpoint` comment in `epic.yaml` is rewritten (it says the planner never applies defaults).

**W-1 — New Run form.** `web-client/src/lib/newwf/catalog.ts::initialOf` prefills a text field with the declared default; a default of `{{model}}` would be submitted literally. Change: an expression default becomes a placeholder ("defaults to model"), never a value; vitest in `src/lib` (90 % lines). The three fields render automatically (`deriveFields` lists every string input not form-owned); no schema change, `InputDeclOut.default` already exists.

**O-2 — a story frame with several agent rows.** `record_trajectory` takes the frame's *first* agent row as "the build row" (`_row(rows, AGENT_KIND)`): attempts, cost, tokens, wall clock and model would record the plan session only, and the done-check would fire before implement and review ran. Change: aggregate over every agent row of the frame in `seq` order (attempts concatenated, sums over all, harness/model = latest non-empty, all agent rows `done`), `AttemptRecord` gains `row` (step id) and `model` so the per-stage split is readable in the export (JSON column, no migration expected — verify against `infrastructure/db/models/trajectory.py`). Same first-row read in `run_views_alert._checkpoint_story` (attempt count). `harness_readiness_evaluate` already handles it. Unit tests with the shared fakes; `test_trajectory_export` e2e is read-only over the shape.

## 4. Work order

| # | story | owner / model | gate |
| --- | --- | --- | --- |
| 0 | Operator: ratify D-1…D-6; paste the O-1 spine sentence; merge `feat/unpinned-template-callees` to main (run `make e2e` there) | Operator | — |
| 1 | O-1 planner defaults + W-1 form placeholder | Sonnet subagent from this spec; I review | `make lint test` |
| 2 | O-2 trajectory and checkpoint-story aggregation | Sonnet subagent | `make lint test` |
| 3 | Skills `story-plan`, `story-implement`, `story-review` in `ia-agents-skills/` (prose from the draft; `{folder}` absolute under hub; marker contract; a unit test that every operator skill dir has a `SKILL.md` whose `name` is the dir) | me (prose) | `make lint test` |
| 4 | Templates: `story.yaml`, `initiative-hub-story.yaml` rewritten to §1; `epic.yaml`, `initiative-hub-epic.yaml`, `initiative-hub.yaml` declare and pass the three model inputs; `drafts/story-staged.yaml` trimmed to the F-1 delta (decide/when rows) so it no longer duplicates the prompts | me | `make lint test` (shipped smoke, graph, tree tests are shape-free) |
| 5 | e2e: `fixtures/hub-repo/members/*/.fake-harness/1/` gets `attempt-1..3.yaml` (plan writes spec + marker 01; implement writes the code change + marker 02; review writes marker 03) and the `.protected` variant moves to the implement attempt; `tests/e2e/test_hub_run.py` row paths `…stories[0].build` → `plan`/`implement`/`review`. **Hard rule 1 (b):** this story declares the new shape; cite it in the hand-back. `test_run_persistence.py` uses the name `story` as data only; `gates-repo`, UJ-3 and durability own their template text — untouched | me | `make e2e`, `make durability` |
| 6 | Docs: `deploy/kit/skills/orchestrator/references/first-run.md` (input lists), `references/workflows.md` (example file, "own model per step"), `orchestrator/SKILL.md` and `initiative-run/SKILL.md` (three model decisions), `deploy/README.md` ("Editing the workflow templates": the three stages and that the method ships in the image), `README.md` Run-creation walkthrough; `ia-agents-skills/README.md` unchanged (no list) | me | `make lint` (prettier) |
| 7 | First real Run on the dev stack: one small story on `claude`, `plan_model` strong / `build_model` cheap / `review_model` strong. Checks owed: spec-checkpoint resume on `plan`; redispatch clause reaching `implement`; protected-path park and `continue` across three rows; stall detector quiet on `plan`/`review`; readiness Run end to end; image rebuilt so the skills land (`skills_install` syncs the volume at boot) | me + Operator | observed |

Branch: `feat/staged-story-flow` off main after step 0; one commit per green story; PR at the end.

## 5. Known hazards to carry

- **Retry/resume downgrades the model** (open defect, memory 2026-10): the row's declared model holds on attempt 1 only. With three rows per story it bites three times as often; fix before relying on the split in production (follow-up F-3, not in this scope).
- **Test freeze is per frame**: AD-17 freezes `repository.test_globs` at the frame's first attempt — the `plan` row. Tests the `implement` row writes are new files (always free); edits to existing tests park at `commit-guard` exactly as today, and the `review` row's patches too.
- **Fake-harness counters**: each dispatch with the story-id sentence advances the per-story counter; a retry or redispatch consumes the next `attempt-k.yaml`, as it does for `build` today. Fixture authors must account for three base dispatches.
- **Hub `commit-retro`** sweeps the `.auto/` markers with the spec folder; nothing else needs them committed sooner.
- **Three sessions re-read context**: the plan's `context:` list is what keeps implement and review cheap — the skills must insist on it.

## 6. Follow-ups (out of scope)

- **F-1** `uses: decide` + `when:` on agent rows (the draft's Jev spec-gate and S/M/L router) — needs the 7a666ce PoC tested, two new kinds in `KIND_META`, spine amendment.
- **F-2** light/deep review pair on different models (depends on F-1).
- **F-3** the retry-model defect above.
- **F-4** per-epic model overrides in `epics.yaml` (`plan_model` etc. per entry) — trivial once D-4 is in; not asked for.
