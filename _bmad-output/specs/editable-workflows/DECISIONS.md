# Editable workflows — orchestrator reconciliation (2026-09-30, draft for the Operator)

Reconciles `PM-CHALLENGE.md` and `ARCH-CHALLENGE.md`. Where the two disagree, the choice
below is the working assumption the UX mockups and the story plan are built on. Every
choice that touches the spine or an anchor is listed at the end for the Operator to ratify;
nothing here is granted until they say so.

## D-1 Parent follows child: unpinned calls, resolved at plan time (Architect, not PM cascade)

- `uses: template` with `version:` omitted = unpinned, resolves to the callee's latest
  stored version at validate time and again at plan time; the resolved snapshot is what
  the Run pins (`run.pinned_versions` + new `run.template_tree`). An integer `version:`
  stays an explicit pin.
- Rejected: the PM's cascade-republish (saving a child auto-saves every caller). With a
  three-level chain one story edit would mint two extra caller versions each time, the
  history becomes noise, and "restore" would cascade again. Unpinned resolution gives the
  same observable behaviour for new Runs with no extra versions.
- Kept from the PM: the impact preview. Before saving a callee, the editor shows which
  callers are unpinned and will follow, and the save-time reverse check refuses a save that
  would strand a caller (callee input mismatch), naming the caller in `errors[]`.
- A planned, queued or running Run is byte-identical across any save (AD-7 already).
  Copy on screen must say "applies to Runs planned after this save".

## D-2 Examples: `origin` column, seed never overrides an operator version, disk catalogue

- `template_version.origin ∈ {shipped, operator, legacy}` + `restored_from`.
- Seeding: same hash → nothing; name with no operator version → insert as shipped; name
  with any operator version → withheld, the file stays readable under Examples with
  "Copy to my workflows".
- Shipped names are editable in place (the PM's read-only + duplicate-as is rejected):
  `INIT_TEMPLATE`, `READINESS_TEMPLATE`, `ROOT_TEMPLATES` resolve by name, so forcing a
  rename would push every customisation into env changes. The first operator save of a
  shipped name claims it; upgrades stop touching it.
- "Copy to my workflows" offers two targets: new version of the same name, or a new name
  (the name line is rewritten server-side).
- `templates/drafts/` stays unseeded and unlisted.

## D-3 Restore = new version equal to version k, `restored_from = k`, full validation

Refused with the validator's errors exactly like a save when the old text no longer
validates (e.g. a pre-2026-09-27 version without `prompts:`). The screen must show the
validation result before the restore lands.

## D-4 Harness/model per agent: template-typed inputs, run-creation only (v1)

- New DSL input types `harness` and `model`; the New workflow form renders every such
  input by type: harness as a select over enabled harnesses, model as a select over the
  probed list (free text when the probe offers none), one control per declared input, so a
  template may declare `plan_model`, `build_model`, `review_model`.
- Pre-flight and `create_run` probe every distinct `(harness, model)` pair over the planned
  agent rows, not only the run-level pair; an unknown pair is a pre-start refusal.
- Deferred (needs an AD-7 carve-out): run-level override map keyed by step path, and
  editing not-yet-dispatched rows mid-Run. The mockups may show the deferred mid-Run
  retarget as a greyed "v2" note only.

## D-5 Helpers: one read-only `GET /capabilities`, derived from the validator's own tables

Step kinds with their `with` keys and gate defaults, input types, expression forms and
entity fields, gates, status tokens, harnesses (enabled, configured models, optional
probe), skills present in the image. No second list anywhere.

## D-6 Surfaces

1. Templates library (`/templates`): MY WORKFLOWS + EXAMPLES, origin, versions, used-by,
   New template.
2. Template editor (`/templates/{name}/{v}`): YAML + validation readout + helper panel +
   versions column with origin/restored-from and Restore; save flow with impact preview
   and the reverse-check refusal.
3. Examples (`/templates/examples/...` or a panel): read-only, diff against my latest,
   Copy to my workflows.
4. New workflow (`/workflows/new`): typed harness/model controls per input, resolved
   tree preview ("will plan from a@3 → b@5 → c@7"), pre-start refusals.
5. Run detail: "planned from" tree line.

## Needs the Operator (never assumed)

- AD-15 rule + Prevents wording (unpinned calls; "after it was planned").
- AD-7 stale `initiative@1 → epic@1 → story@1` sentence; AD-10 probe sentence (every pair).
- Migrations 0021 (origin, restored_from) and 0022 (run.template_tree).
- Test revisions under the declaration, listed in ARCH-CHALLENGE §8.
- AGENTS.md lines that follow; DEPLOY.md upgrade paragraph.
- Whether `templates/drafts/` joins the Examples catalogue (default: no).
