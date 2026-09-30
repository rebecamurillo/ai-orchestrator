# PM challenge — editable workflows in a deployed instance

Date: 2026-09-30 · Status: challenge, not a spec · Audience: Operator
Scope input: the Operator's four asks (edit workflows; edit harness/model per agent; turn `templates/` into examples; parent follows the new child).

---

## 1. Problem statement and who it serves

**Who.** One deployed instance, one Operator, one bearer token (AD-4/AD-5). No multi-user, no authorship, no approvals — so the feature needs provenance, not identity.

**What is actually blocking production.** Four concrete defects, not a missing capability:

1. **The upgrade defect.** Shipped callers pin callees literally: `templates/initiative-hub.yaml:75-78` pins `initiative-hub-epic` at `version: 1`. `seed_shipped` (`backend-api/src/orchestrator/application/use_cases/templates.py:301-319`) inserts a changed shipped file at `max(existing) + 1` **per store**. On an install where the Operator already saved an edit to `initiative-hub-epic` (now v2), the freshly seeded `initiative-hub` still resolves `@1`. The upgraded install silently runs the stale callee; a fresh install does not. Same image, two behaviours.
2. **Examples and operator edits share one namespace.** `latest_version` (`templates.py:173-183`) — what `ROOT_TEMPLATES`, `INIT_TEMPLATE` and `/workflows/new` all resolve — alternates owners across upgrades: v3 mine, v4 the image's, v5 mine. Nothing on the row says which.
3. **No per-agent harness/model without hand-editing YAML.** The mechanism exists — `application/steps/agent.py:99-100,243-244,341` reads `harness`/`model` off the row's `with_resolved`, and `templates/drafts/story-staged.yaml` declares `plan_model`/`build_model`/`review_model` — but `/workflows/new` offers exactly one run-level harness and model (`web-client/src/pages/workflows/new.astro`). And only that run-level pair is probed (`create_run.py`); a per-step harness the instance lacks surfaces at dispatch as a park (`agent.py:116`).
4. **No restore, no diff, no create.** The Templates screen (`web-client/src/pages/templates/[name]/[version].astro`, `islands/TemplateEditor.tsx`) validates, saves v n+1 and lists versions — no create, no diff, no restore. The API already creates a new name (`_next_version` returns `1` for an unknown one); the UI has no door to it.

Everything else the Operator asked for is already true and only needs to be *stated*: saves are immutable versions, and a Run pins its whole tree at creation (AD-7, AD-15), so **a save already cannot touch a planned or running Run**. Ask 1 is largely shipped; it is ask 3 and ask 4 that are unbuilt.

---

## 2. Challenging the four asks

### Ask 1 — "a new edition applies to NEW runs only"

**Already the invariant, by construction.** `create_run` persists every `step_run` row with its `with_resolved` before `engine.enqueue` (AD-7); `run.pinned_versions` records the whole tree (AD-15). Nothing re-reads a template after planning. The hidden assumption worth naming: *"new run" means "planned after the save"*, not "started after it" — a Run created with `save=True` and started later by the `start` signal was planned at save time and keeps its old tree. Correct, and the one case that will surprise, so say it on screen.

**Recommended reading:** no engine work. One UI sentence on the Save confirmation ("applies to runs planned from now on; runs already planned, including saved-not-started ones, keep their pinned versions") and a "create a template" affordance. Ask 1's real cost is ask 3's.

### Ask 2 — "edit the harness and the model used for each agent in a workflow run"

Three readings, and the Operator's phrasing does not choose between them.

| Reading | What it costs | Verdict |
| --- | --- | --- |
| (a) at run creation — override per agent step | template declares model inputs; form renders them; preflight probes each | **v1** |
| (b) mid-run, for rows not yet dispatched | rewriting `with_resolved` on planned rows | **defer** |
| (c) both | (a)+(b) | no |

**Why (b) is deferred — stated as a conflict.** AD-7 plans a Run *completely, purely* before enqueue and explicitly prevents "plans that change on recovery or with a later repository edit". Mutating a planned row's `with_resolved` mid-run is exactly that, and adds a writer of plan data outside `plan_run`. **This conflicts with the Operator's ask; I am not resolving it silently.** If mid-run override is required it needs a spine amendment naming that writer and its unit of work — propose it separately.

**What the Operator actually wants, cheaply.** "Change the model mid-run" means "this park would clear on a better model". Reachable without touching the plan: let the `retry` signal carry an optional `{harness, model}` applied to **the next attempt only**, recorded on the `attempt` row, which already stores both (`agent.py:243-244`). The plan stays frozen; the history says which attempt ran on what. Recommend as v1.5 — it changes an attempt, not a row, so it is not an AD-7 amendment.

**Answers to the specific edge questions.**
- *A running or already-dispatched step:* never affected, by either path. An override changes the next attempt, not the live process.
- *Template-declared `retry: {max, prompt}` and `on_fail` redispatch:* unchanged — they reuse the row's own `with_resolved` (hard rule 7: the only automatic retry is the bounded declared one).
- *Operator `retry` after a park:* the one place an override applies.
- *Unknown harness/model:* must be refused **before** the Run starts. Extend the `create_run` probe from the run-level pair to every distinct `(harness, model)` the plan's agent rows resolve to, as a preflight line. This converts a mid-run park into a pre-start refusal and is the single highest-value item in ask 2.

### Ask 4 — "when a child is modified, the parent uses the new one"

**For new runs only**, identical to ask 1: a planned Run's tree is what `pinned_by` counts. Re-resolving a callee for a live Run would make two Runs of one root execute different graphs with no record of why. Not negotiable.

**How to get it without breaking AD-15.** AD-15 rejects a non-literal `version:` because `TemplateVersion.calls` — the list cycle and depth detection walk without re-reading a callee — must be knowable at save time. So **`version: latest` is the wrong fix; I recommend against it.**

Instead: **cascade republish.** Saving callee `C` as v*N* also saves a new version of every template whose *latest* version pins `C` older, pin rewritten to *N*, recursively, bottom-up, in one transaction. Pins stay literal, `calls` stays accurate, frozen versions stay frozen, and new Runs pick the chain up because every dispatch path already resolves `latest_version`. The Operator sees an impact preview before confirming.

Rejected alternative: omit `version:` and have the server normalise the text on save — it breaks "`yaml` is the exact text the Operator saved … line numbers in a `ValidationError` refer to it" (`domain/entities/template.py`), which the editor's error list depends on. Cost accepted: version numbers inflate; a `reason` per version keeps the history readable.

**What "restore" must mean.** Under immutability, restore is **not** a pointer move and **not** a delete. Restoring v*k* saves a **new** version v*n+1* whose YAML equals v*k*'s, carrying provenance `restored_from: k`. It goes through the same validate-and-cascade path as any save — so a restore of an old root whose pins are stale is itself pin-rewritten forward, which is the behaviour the Operator wants and the only one that cannot resurrect a stale tree. The UI shows the diff before confirming.

### Ask 3 — `templates/` as examples: what happens on upgrade

| Option | Verdict |
| --- | --- |
| (i) examples read-only; edits are duplicates under a user-owned name | **recommended** |
| (ii) edits become versions of the same name; re-seed never overwrites | **reject — this is today, and it is defect 2** |
| (iii) namespace `examples/` in the name | reject |

(ii) is the status quo, and it is defect 2. (iii) puts a `/` into a value that is a Postgres key, a URL segment (`/templates/[name]/[version]`), a `uses: template` `name:`, and a `ROOT_TEMPLATES` entry — four surfaces changed for a distinction a column gives free.

**Recommend (i):** an `origin` column, `shipped | operator`. `seed_shipped` only writes `shipped`; `save_version` on a shipped name refuses 409 naming the duplicate action; the screen's primary action on a shipped template is **DUPLICATE AS…**, creating an `operator` template at v1. Names never collide, and an upgrade can only add versions to shipped names.

Two consequences up front: a duplicate is **shallow** by default (new root, callee pins unchanged, so it calls the shipped callees and the cascade keeps them current), with an explicit "duplicate the whole tree" option. And `origin` must be a **column, not a name list in code** — the Operator ruling of 2026-09-30 forbids hardcoded template names in product code.

**Plus the seeder pin fix — the actual upgrade defect.** `seed_shipped` already loops until each file's callees are stored; it must also record the version each callee landed at and rewrite the caller's pins to it before validating and inserting. Rewriting changes the text, so hash dedupe (`_seed_file`, `templates.py:303-307`) must move to the **file-as-shipped** digest, stored beside the rewritten text: one column, one migration. Without this, (i) alone does not fix defect 1.

---

## 3. Non-goals for v1

Multi-user, authorship, roles, approvals. A drag-and-drop builder (helpers are autocomplete, snippets and pickers, not a canvas). Mid-run editing of any planned row's `with_resolved`, prompts included. Template deletion (no route exists; do not add one — a frozen version may be pinned by a Run). Import/export to files; git-backed templates. Cross-instance sharing or a registry. Branching or forking version trees — one ascending line per name. `version: latest` in the DSL. Per-step budget overrides. Editing `templates/*.yaml` on a deployed host as a supported path.

---

## 4. Epics, stories, acceptance criteria

### Epic A — Ownership and upgrade safety (unblocks production)

**A1 · A template row records its origin.**
Given a fresh start-up, When `seed_shipped` stores a shipped file, Then the row's `origin` is `shipped`.
Given a version saved through `POST /templates/{name}/versions` for a name nothing stores, When it is stored, Then `origin` is `operator`.
Given a `shipped` name, When `POST /templates/{name}/versions` is called for it, Then the response is 409 and no version is written. *(Behaviour change — declare it in the story; existing save tests must be revised under hard rule 1 with the Operator's authorisation.)*

**A2 · The seeder rewrites callee pins to what it actually stored.**
Given a fixture caller pinning callee `c@1` and a store already holding `c@2`, When the seeder runs, Then the stored caller's `calls` name `c` at the version the seeder stored or matched in that pass, never `1`.
Given an unchanged shipped file, When the instance restarts twice, Then no new version is inserted on the second boot (dedupe on the shipped-file digest, not the rewritten text).
*Tests use fixture templates the test owns — hard rule 6 forbids pinning `templates/*.yaml` content.*

**A3 · Upgrade is provably inert.**
Given a store with operator templates and an image whose `templates/` changed, When the instance restarts, Then every `operator` name's `latest_version` is unchanged and every previously planned Run's `pinned_versions` is unchanged.

### Epic B — Authoring UX

**B1 · Create a template.** Given the Templates screen, When the Operator names a new template and saves valid YAML, Then v1 is stored with `origin=operator` and the screen opens it.
**B2 · Duplicate an example.** Given a `shipped` template, When the Operator duplicates it under a new name, Then an `operator` v1 is stored whose YAML equals the source, whose callee pins are unchanged, and whose provenance names source `name@version`.
**B3 · Validate before save (negative).** Given YAML with an unknown step kind, an unbound variable, a cycle, or depth > 3, When Save is pressed, Then the response is 422 with `errors[]` carrying line and reason, **and no version is stored** — `list_versions` is unchanged.
**B4 · Diff and restore.** Given two versions, When the Operator opens the diff, Then the YAML difference is shown. When the Operator restores v*k*, Then a new version is stored whose YAML equals v*k*'s, carrying `restored_from: k`, and v*k* itself is unchanged.
**B5 · A save cannot touch a live Run (negative).** Given a Run in `running` or `queued` planned from `t@2`, When `t@3` is saved, Then that Run's `pinned_versions`, its `step_run` rows and their `with_resolved` are byte-identical before and after.

### Epic C — Helpers (pickers)

**C1 · Step-kind picker.** Given the editor, When the Operator opens the kind helper, Then it lists exactly the kinds the executor registry holds (`agent`, `shell`, `checkpoint`, `git.sync|worktree|commit|push|merge|submodule`, `bmad.install`, `plan.check`, `pr.link`) plus `template`, read from a new read-only route — never a list duplicated in the web-client.
**C2 · Harness and model pickers.** Given the helper, Then harnesses come from `GET /harnesses` and models from `GET /harnesses/{name}/probe`; a probe returning an empty `models` list (gateway disabled) shows a free-text field and states why.
**C3 · Skill picker.** Given the helper, Then skill names come from the installed-skills manifest via a new read-only route over the existing `SkillCatalog` port; an unavailable manifest is stated, not hidden.
*Every new route ships with `make openapi` + `pnpm gen:api` in the same change (AD-3).*

### Epic D — Callee currency

**D1 · Impact preview.** Given a callee about to be saved, When Save is pressed, Then the screen first lists every template whose latest version pins it and the version each would receive.
**D2 · Cascade republish.** Given caller `p@3` pinning `c@2`, When `c@3` is saved, Then `p@4` is stored with the pin rewritten and a `reason` naming the callee bump, in the same transaction; `p@3` and `c@2` are unchanged.
**D3 · New runs follow, old runs do not.** Given a Run planned from `p@3`, When the cascade produces `p@4`, Then that Run is unchanged and a Run started afterwards from the name `p` pins `p@4`.
**D4 · Cascade refuses rather than half-applies (negative).** Given a cascade that would produce an invalid caller, Then nothing is stored — neither the callee nor any caller — and the refusal names the template and line.

### Epic E — Harness and model per agent

**E1 · Declared model inputs on the New-run form.** Given a template declaring several model/harness inputs, When `/workflows/new` renders it, Then each is offered with its default, and the chosen values reach the plan's agent rows through the template's own `{{…}}` substitution — no new addressing scheme.
**E2 · Preflight probes every agent row (negative).** Given a plan whose agent rows resolve to a harness the instance lacks or a model absent from that harness's probed list, When the Run is started, Then it is refused before any row runs, naming the row path, the harness and the model. Given all values probe clean, Then no refusal.
**E3 · Retry with an override.** Given a parked agent row, When the Operator sends `retry` with `{harness, model}`, Then the next attempt records those values and the row's `with_resolved` is unchanged. Given `retry` without them, Then the row's own values are used.
**E4 · Ship the staged story template.** `templates/drafts/story-staged.yaml` moves up one level once E1–E2 land, as the example that exercises per-step models.

---

## 5. Risks and open questions (each with my default)

1. **Are shipped templates read-only?** *Default: yes — duplicate to edit.* This is the whole of ask 3's value; without it the upgrade story stays ambiguous.
2. **Does making `save_version` refuse a shipped name need an anchor/test authorisation?** *Default: yes — the story declares the behaviour change and the Operator authorises the test revision (hard rule 1).* Work can be written test-first regardless.
3. **Is the cascade automatic or opt-in?** *Default: automatic, with a mandatory impact preview.* Opt-in reproduces the stale-callee defect by inattention.
4. **Is cascade version inflation acceptable?** *Default: yes.* Rows are cheap; a `reason` per version keeps the history legible.
5. **Does the cascade need a spine amendment?** *Default: no for AD-15 (pins stay literal), but one added sentence noting that a save may create versions of other templates.* Ratify it rather than infer it.
6. **Mid-run harness/model change — in or out?** *Default: out; `retry` with an override is v1's answer.* In requires an AD-7 amendment naming a plan-data writer, which I recommend against.
7. **Do we need template archive/hide?** *Default: no delete, no archive in v1.* Revisit if the store becomes unreadable.
8. **Any new settings?** *Default: none.* `TEMPLATES_DIR` and `ROOT_TEMPLATES` cover it. If one is added it goes to the typed settings module and `.env.example` in the same change (hard rule 8).

---

## 6. Success metrics

1. **Upgrade is inert.** An e2e that seeds fixtures, saves operator edits, re-seeds a bumped fixture set, and asserts that every operator name's `latest_version` and every planned Run's `pinned_versions` are unchanged. Currently fails by construction; must pass.
2. **No stale callee, ever.** For every stored template's latest version, each pin names its callee's latest version. Checkable as one query; target 100 %.
3. **Zero filesystem edits.** An Operator creates, validates, saves and starts a custom workflow through the UI alone — no host file edit, no restart. Target: the path exists and is exercised by one e2e.
4. **Nothing invalid is ever stored.** Start-up re-validates every stored version without error. Already true; must stay true after the cascade lands.
5. **Unknown harness/model is refused before dispatch.** Zero `harness misconfigured` parks originating from a value that was knowable at pre-flight.
6. **Restore is one action and is faithful.** Restoring v*k* yields a version whose pinned tree equals the tree a Run started at v*k* would have had, with the callee pins moved forward.
