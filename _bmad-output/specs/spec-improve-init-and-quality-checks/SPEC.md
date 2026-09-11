---
id: SPEC-improve-init-and-quality-checks
companions:
  - brownfield.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when this spec and the code disagree.

# Improve repo-init and quality checks

## Why

A pain to solve, found in the first full test run before production. Two gaps: a `repo-init` Run installs the BMAD method but never initializes the repository's project context, so every later agent works a repository with no `AGENTS.md` behind it; and the quality gates are mis-tiered — the slow `quality_gate_command` ran per Story while nothing verified an epic end to end. A first attempt (`feat/improve-init-and-quality-checks`) fails its own quality checks and is abandoned, not debugged: this is a fresh build from `main`, developed through the orchestrator with TDD respected. `brownfield.md` records what that branch attempted and what the engine already provides — as reference, never as a baseline to cherry-pick.

## Capabilities

- **CAP-1** — repo-init context bootstrap with a human Q&A loop
  - **intent:** A `repo-init` Run dispatches an agent step that runs the `bmad-project-context` skill against the target repository; when the skill leaves open questions, the agent writes them to an artifact file and stops for human review; the Operator's reply reaches the next dispatch of the same step; the loop repeats until no questions remain, and a `context-review` checkpoint before the commit remains the final human gate. The dispatch prompt states this contract explicitly: run `bmad-project-context`; if open questions, write them to the artifact and stop for review; otherwise finish.
  - **success:** Against a repository the skill cannot resolve alone, the Run parks `needs_you` with the questions readable in the Run's artifacts; the Operator's reply is present in the redispatched agent's prompt; a Run that takes N reply rounds still ends `done` with `AGENTS.md` committed on `chore/bmad-init` and a PR link; a repository with no questions passes through with a single dispatch plus the final checkpoint.

- **CAP-2** — per-Story unit gate with fix-it context
  - **intent:** The Story `verify` step runs `{{repository.unit_test_command}}`; on failure it redispatches the build agent, whose prompt context frames the failure as "the unit test gate is failing — this may be your implementation or a regression; investigate and fix" alongside the facts (command, exit code, log tail).
  - **success:** A Story whose implementation breaks a unit test redispatches once; the redispatched agent's Story file carries the failing command, exit code, log tail, and the investigate-and-fix framing; a second failure escalates as today.

- **CAP-3** — per-epic e2e gate with an investigate-and-fix agent
  - **intent:** After all Stories of an epic, the epic Run executes `{{repository.quality_gate_command}}`; on failure it dispatches an agent whose task is to investigate why the e2e gate fails and fix it, carrying the gate's failure context; the gate re-runs after the fix.
  - **success:** An epic Run whose e2e gate fails dispatches the fix agent with the failure context; a fixed gate goes green and the Run pushes; after one fix round with the gate still red, the Run parks `needs_you` with the last failure readable.

- **CAP-4** — template-change-proof test strategy
  - **intent:** No unit or e2e test fails because a shipped `templates/*.yaml` changed. Content-level coverage (rows, ordering, parameters) runs against frozen exemplar copies; tests that read the real `templates/` dir assert invariants only (seeds, validates, graph self-contained, trees resolve). The strategy holds when templates become versioned: a new version seeded by `seed_shipped` must not fail any existing unit or e2e test.
  - **success:** Editing any shipped template's steps (add, remove, reorder, reparameterize) leaves `make test` and `make e2e-api` green without touching a test file; the e2e suite no longer pins `repo-init@1`'s row order or stop row.

## Constraints

- CAP-1's signal is an output-file contract mirroring Story files: the context step declares an artifact plus a status (`open-questions` | `done`) the routing can read, `escalate_when` parks the Run, and the Operator's reply travels the existing Epic 6 Answer path (AD-13, FR-18) into the redispatch — no new park kinds. The `context-review` checkpoint fires even when there were zero question rounds. AD-8's two status writers hold throughout.
- CAP-3's fix loop is bounded at **1**: one fix agent, one gate re-run, then `needs_you` — consistent with the Story verify redispatch bound.
- Template DSL: `on_fail: {redispatch, max}` targets only an *earlier `agent` step* (`BAD_REDISPATCH`). CAP-3 either extends the DSL or shapes its steps to honor that rule — in both cases `validate`/`plan`/`rows` remain the single place the rule lives, and the extension is exercised through exemplars, not by pinning shipped content.
- CAP-4 lands first: the test-strategy story precedes every story that edits a shipped template, so no later story trades a red gate against test edits. The strategy is re-derived through TDD, not cherry-picked; `feat/improve-init-and-quality-checks` is read-only reference. Where an existing pinning test must change, that is an operator-authorized anchor edit resolved through the protected-path park, on record per edit.
- Redispatch and prompt copy states facts and mechanisms (NFR-8): the CAP-2 framing sentence is normative in meaning, illustrative in wording.
- The build runs as an orchestrator epic on a fresh branch from `main`; epic 8 runs in parallel and its merge is sequenced before this branch's. This work does not touch epic 8's surfaces: web-client, Run/Board read models, the graph endpoint, login.
- Hard rules of `AGENTS.md` apply unchanged; `templates/*.yaml` stay at `version: 1` for this cut.

## Non-goals

- No template versioning workflow or UI (post-cut; only the test strategy must already survive it).
- No debugging or salvaging of `feat/improve-init-and-quality-checks`; nothing is cherry-picked from it.
- No changes to epic 8 scope or its read models; no parallel-epic execution.
- No new harness kinds, no new data-collection paths (AD-19's trajectory row stays the only one).
- No automated answering of the context agent's questions — the loop exists precisely so a human answers.

## Success signal

A fresh repository goes through `repo-init` with two question rounds and ends with `AGENTS.md` on a PR; a Story that breaks a unit test fixes itself on the one redispatch; an epic whose e2e gate fails goes green through the fix agent and pushes; then an Operator edits `templates/epic.yaml`, restarts the stack, and `make test` and `make e2e-api` both pass untouched.

## Assumptions

- The Operator's quoted redispatch wording is illustrative; exact copy follows NFR-8.
- `Repository.unit_test_command` and `install_command` already exist on `main`; no schema or contract change is needed for the gate re-tiering.
