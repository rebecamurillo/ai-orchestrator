# Staged story flow — plan, revision 2 (2026-10-12)

Revision 1 (2026-10-06, commit 7f90b35) proposed rewriting the shipped `story` /
`initiative-hub-story` in place. The Operator ruled on 2026-10-12: **keep the build-auto flow
as it is; the split dev agents are a new workflow family.** This revision replaces it. Main has
moved since (unattended-hub-run phase 1 and O-1..O-8 landed): literal input defaults are
bound by the planner, resume keeps the model, the stall signal reads model activity, `workdir`
rows get `--add-dir`, the hub story syncs by merge and commits its spec at the hub. Items the
old revision carried that main has since closed are dropped below, not restated.

Status: plan, nothing built. **D-n** items need the Operator.

## 1. Two families, one rule each

| family | method | scope roots on the menu | callees | skills | state |
| --- | --- | --- | --- | --- | --- |
| **auto** (today's files, names unchanged) | one `bmad-build-auto` session per story | `initiative-hub` (hub) · `epic` (single repo, readiness only, off the menu) | `initiative-hub-epic`, `initiative-hub-story`, `story` | BMAD stubs + `spec-gate` | **maintained, not evolved** — fixes only |
| **staged** (new files) | three sessions per story: plan → implement → verify → review | `staged-initiative-hub` (hub) · `staged-initiative-repo` (single repo) | `staged-hub-epic`, `staged-hub-story`, `staged-epic`, `staged-story` | `staged-plan`, `staged-implement`, `staged-review` + `spec-gate` | **the default for new deployments** — where new behaviour lands |

Nothing in the auto family changes: not a row, not an input, not a step id. `test_hub_run.py`,
the readiness fixture (`READINESS_TEMPLATE=epic`), every client's saved version and every
pinned caller keep working untouched. That is the whole point of a second family instead of
an edit.

## 2. What makes the two distinguishable (the maintenance contract) — **D-1**

A template file is plain YAML the DSL does not tag, so the distinction has to be carried by
things a reader and a test can see. Five conventions, all checkable:

1. **The family is the first name segment.** Every staged file, skill and root is `staged-*`;
   siblings sort together in `/templates`, in `GET /api/v1/templates`, and in the menu. The
   auto family keeps its unprefixed names (renaming shipped files would break every install's
   `ROOT_TEMPLATES`, `READINESS_TEMPLATE`, saved versions and pinned callers); its family
   name exists in prose only.
2. **A fixed header block in every shipped file**, the first comment after `description:`:
   ```yaml
   # family: staged · role: story · method: plan/implement/verify/review, one session each
   # called by: staged-hub-epic · calls: — · skills: staged-plan, staged-implement, staged-review
   # sibling: initiative-hub-story (auto) — differs in: build row → plan/implement/review rows,
   #          three model inputs, markers under stories/.auto/
   ```
   The `sibling … differs in` line is the maintenance key: whoever edits one family reads in
   two lines whether the other needs the same change.
3. **`description:` opens with the family word** (`staged: …` / `auto: …`), because the
   description is what the templates list and the kit skills show before the YAML.
4. **No callee is shared across families.** A staged root calls only `staged-*` callees;
   `spec-gate` (a skill, not a template) is the one shared method piece. The DSL names callees
   literally, so sharing an epic file between families would need a callee-name-from-input
   extension (AD-15) — rejected for now: the editor's "which callers follow this save" strip
   and `save_version`'s refusal both rely on literal names.
5. **A `templates/README.md` family table** (file · family · role · calls · on the menu ·
   sibling) plus one unit test that every `templates/*.yaml` appears in it and that every
   `staged-*` file's header carries the four header keys. That test pins names and headers,
   never steps, ordering, counts or graph shape (hard rule 6 stays intact).

The AGENTS.md shipped-template sentence (line 16, anchor) gains the family rule: "the auto
family is maintained, not evolved; new workflow behaviour lands in the staged family" —
Operator edit.

## 3. The staged files

### `staged-story` (single repo) and `staged-hub-story` (hub, every agent row with `workdir`)

| row | kind | model | gate | routes on |
| --- | --- | --- | --- | --- |
| `sync` | git.merge from `{{branch}}` (as the hub story does since T-1) | — | deterministic | — |
| `plan` | agent · skill `staged-plan` · `args {spec_folder, story_id}` · `prompt_extra: {{story.invoke_dev_with}}` | `{{plan_model}}` | liveness | marker `{spec_folder}/stories/.auto/{id}-01-plan.md` — `done` / `blocked` / `ready-for-dev` (checkpoint via `pause_when: story.spec_checkpoint` + `halt`) |
| `implement` | agent · skill `staged-implement` · carries `prompts.redispatch` | `{{build_model}}` | liveness | marker `…/{id}-02-implement.md` |
| `verify` | shell `{{repository.unit_test_command}}` (hub: `{{test}}`) · `on_fail: {redispatch: implement, max: 2}` | — | deterministic | exit code |
| `review` | agent · skill `staged-review` | `{{review_model}}` | liveness | marker `…/{id}-03-review.md` |
| `commit-guard` | git.commit (hub: `workdir`) | — | deterministic | AD-17 check |
| `commit-story` (hub only) | git.commit at the hub, as T-4 | — | deterministic | — |

Limits: `plan_timeout_min` 45, `build_timeout_min` 180 / `build_stall_min` 90,
`review_timeout_min` 60 — number inputs with literal defaults, passed down from the root like
the hub's today. `retry: {max: 1, resume_session: true}` on each agent row.

Why skills and markers, unchanged from revision 1: an own-text `prompt:` is sent verbatim, so
under `workdir` only the skill dispatch sentence gets the absolute spec folder; the fake
harness keys e2e scenarios off that sentence; pre-flight proves an installed skill; and the
`answer` archive moves the row's first `expect.files` match, which must be a marker, never the
spec. The `.auto/` markers are committed with the spec (hub: by `commit-story`).

### `staged-hub-epic` / `staged-epic`

`staged-hub-epic` = today's `initiative-hub-epic` shape (branch in the submodule, setup,
baseline, spec-gate, stories loop → `staged-hub-story`, gen-e2e, commit-e2e, e2e, retro,
commit-retro, merge-hub, push-code, push-hub) with the three model inputs and the three
limit inputs passed through; `spec-gate`, `gen-e2e`, `retro` run on `{{plan_model}}`.
`staged-epic` is the same file without `workdir`/submodule rows: no checkout of its own
(callee-only, `epic` item required), commands from the repository record
(`{{repository.install_command}}` etc.) with the per-epic `install`/`test`/`quality_gate`
fields of `epics.yaml` taking precedence when present — **D-2**: or repository commands only,
which is what `epic.yaml` does today; the data-over-template rule argues for the override.

### `staged-initiative-hub` / `staged-initiative-repo`

`staged-initiative-hub` = today's `initiative-hub` root with the new callee and inputs
`plan_model`, `build_model`, `review_model` (string, optional) and the limits. `staged-
initiative-repo` is its single-repository twin: attach-checkout of `{{branch}}`, setup,
`epics` loop over `{{initiative_folder}}/epics.yaml` → `staged-epic`, one branch for every
epic, `pause_after_item_when: epic.done_checkpoint`. It gives the single-repo flow an
initiative level again, on the hub's one-branch convention rather than the retired fan-in one;
an initiative of one epic is an `epics.yaml` with one entry. `epics.yaml` keeps the list
contract (`id`, `title`, `branch`, `spec_folder` — `lists.py::REQUIRED_FIELDS`; `branch`
unused, as in the hub flow). **D-3**: confirm this is the "repo initiative build" wanted, or
drop the root and keep only the hub one.

### Model inputs — **D-4**

`plan_model`, `build_model`, `review_model` on every staged file; `model` stays the Run-level
field (used by nothing in the staged family unless the fallback below exists; `harness` as
today). Main binds **literal** defaults only (`templates/defaults.py` skips `{{…}}` on
purpose). Options:
- (a) **recommended** — O-1: `with_defaults` also binds an expression default of the form
  `{{<input>}}` whose referent is already bound, one pass, no chaining; validator refuses a
  default that names an input which itself has a default. Then
  `plan_model: {type: string, default: "{{model}}"}` makes one `model` enough and three
  fields a refinement. W-1: `catalog.ts::initialOf` must not prefill an expression default
  (it would submit `{{model}}` literally); show it as the placeholder "defaults to model".
  Spine: one sentence in the DSL `default?` cell — Operator paste.
- (b) no fallback: the three inputs blank → harness default model. On a Gateway install that is
  the documented "Invalid model name" failure; rejected unless the Operator prefers no code.

### Trajectory and alert — O-2 (still open on main)

`record_trajectory` and `run_views_alert._checkpoint_story` take the frame's *first* agent
row; with three agent rows they would record the plan session alone and the trajectory's
done-check would fire early. Aggregate over every agent row in `seq` order; `AttemptRecord`
gains `row` and `model` (JSON column; verify no migration). `harness_readiness_evaluate`
already takes the last done row. Nothing in the auto family is affected by this change.

## 4. Work order

| # | story | owner | gate |
| --- | --- | --- | --- |
| 0 | Operator: D-1..D-4; AGENTS.md family sentence; spine sentence if D-4(a) | Operator | — |
| 1 | O-1 expression defaults + W-1 placeholder (skip if D-4(b)) | Sonnet subagent | `make lint test` |
| 2 | O-2 multi-agent-row trajectory and checkpoint story | Sonnet subagent | `make lint test` |
| 3 | Skills `ia-agents-skills/staged-plan`, `staged-implement`, `staged-review` (prose from `drafts/story-staged.yaml`: spec shape + size rule + marker; tests-first + `baseline_revision` + redispatch handling; sized triage, `bad_spec`/`intent_gap` block, never re-implement) and a unit test that every operator skill dir has a `SKILL.md` whose `name` is the dir | me | `make lint test` |
| 4 | The six `staged-*` templates with the §2 headers; `templates/README.md` family table + its test; `drafts/story-staged.yaml` cut to the F-1 delta (decide/`when` rows) | me | `make lint test` (shipped smoke, graph, tree tests) |
| 5 | e2e: `test_staged_hub_run.py` on the hub fixture with its own scenario set (`members/*/.fake-harness-staged/1/attempt-1..3.yaml`, swapped in by `hub_fixture.py` the way `.protected` is), polling `…stories[0].plan/implement/review`; the auto journey and its scenarios untouched | me | `make e2e` |
| 6 | Menu and docs: `ROOT_TEMPLATES=staged-initiative-hub,staged-initiative-repo,initiative-hub,repo-init,agent-smoke` in both `.env.example`s (**D-5**: order = menu order; staged first); kit `orchestrator/SKILL.md` + `references/first-run.md` + `workflows.md` ("Families" section, three model inputs), `initiative-run/SKILL.md`; `deploy/README.md`; `README.md` menu lines; `_bmad-output/README.md` index | me | `make lint` |
| 7 | First real Run per root on the dev stack after an image rebuild (skills ship in the image; `skills_install` syncs the volume at boot): spec-checkpoint resume on `plan`, redispatch reaching `implement`, protected park + `continue` across three rows, trajectory row shape | me + Operator | observed |

Branch `feat/staged-family` off main; one commit per green story.

## 5. Carried hazards and follow-ups

- AD-17 freezes `repository.test_globs` at the frame's first attempt (`plan`); tests written
  by `implement` are new files, edits to listed ones park at `commit-guard` as today.
- Each skill dispatch advances the fake-harness per-story counter; staged scenarios must
  account for three base dispatches plus any retry.
- Three sessions re-read context; the plan's `context:` list is what keeps implement and
  review cheap — the skills insist on it.
- F-1 `uses: decide` + `when:` on agent rows (Jev spec gate, S/M/L router) — the draft's
  remaining delta; F-2 light/deep review on two models; F-4 per-epic model overrides in
  `epics.yaml` (trivial once D-4 is in).
- Closed on main since revision 1, no longer owed here: retry model downgrade (O-2 of
  unattended-hub-run), stall signal on read-only phases (O-1), hub sync/commit-story
  (T-1/T-4), per-Run limits (O-7).

## 6. Built (2026-10-12, branch `feat/staged-family`)

Stories 3, 4 and 6 of §4 landed (commits `00c33e6`, `457379e`, `0ed3904`): the three skills,
the six `staged-*` templates with their family headers, `templates/README.md` and the two
tests that pin names and headers, the menu (`ROOT_TEMPLATES`, staged roots first) and the
operator and kit docs. `make lint` and `make test` green.

Decided while building, without the Operator in the loop:
- **D-4 → no planner change.** `templates/defaults.py` binds literal defaults only, and
  `test_with_defaults_applies_literals_only` pins that from the 2026-10-09 ruling — not a
  behaviour change this work declares. Instead the Run's own `model` is the implementer's,
  and `plan_model` / `review_model` are `required: true` on the two roots. Root required-ness
  is enforced by the form, not by the planner: a Run created over the API with a blank one
  falls to the harness default model. O-1 (expression defaults) stays available as a later
  refinement that would make one `model` enough.
- **D-2 → repository commands.** `staged-epic` runs the repository record's own commands;
  `epics.yaml` carries no per-epic command for the single-repository root.
- **D-3 → both roots**, `staged-initiative-repo` included.

Still owed: O-2 (trajectory and checkpoint alert aggregate over a frame's agent rows — today
they record the `plan` row alone); a staged e2e journey with its own fixture scenario set;
an image rebuild so the skills reach the agent-home volume (`skills_install` syncs at boot);
the AGENTS.md line-16 family sentence (anchor); a web-client restart to read the new
`ROOT_TEMPLATES` in the local `.env`.
