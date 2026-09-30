# UX spec — editable workflows

2026-09-30 · Scope: exactly `DECISIONS.md` D-1…D-6 · Mockups: `mockups/01…07` · AC ids from
`PM-CHALLENGE.md` §4. Where DECISIONS supersedes the PM, the screens follow DECISIONS: **D2/D4
(cascade republish) are not designed**, and **B2** is satisfied by *copy*, not *duplicate-to-edit*.

## Cross-screen rules

Register unchanged. No signal colour appears except the refusal text on 02, 04-B, 06-c and the run chip
on 07. `unpinned`, `pinned`, `withheld`, `unvalidated`, `not in probed list` are words, never colour
alone. Uppercase labels only. A resolution reads `name@version`, a list row `name v5`. Every refusal
names cause, place (line · row path · caller), then next action. Each screen's primary action sits in
the surface bar or at the head of its panel, above the fold.

---

## 01 · Templates library — `/templates` (B1; makes A1/A3 visible)

**Purpose.** Replace the redirect-to-first-template with a surface answering what will run, who owns
each name, and what the image ships that is not in use.

**Layout.** Shell. Surface bar `TEMPLATES` · `6 stored · 18 versions · 6 example files` · primary
`NEW TEMPLATE`. Two sections: **MY WORKFLOWS** on a five-field grid `56px 1fr 128px 236px 140px`
(latest · name + description · origin + versions · used-by · last planned run) and **EXAMPLES** on
`1fr 250px 330px` (file + description · state in this store · actions).

**States.** *Populated* — used-by reads `initiative-hub-epic@5 · unpinned`, `epic@1 · pinned`, or
`no caller · started directly`; a template never planned reads `never planned`, not a blank.
*Empty (fresh install)* — `NO WORKFLOW IS STORED`, body states what a template is and that the six
shipped files are listed under Examples; `NEW TEMPLATE` / `BROWSE EXAMPLES` beneath. *Unavailable* —
`TEMPLATES UNAVAILABLE` / "The list could not be read from backend-api. Nothing is stated here about
what this instance stores. Reload the page once the connection is restored." The two are never
collapsed. *Loading* — the bar's count is omitted rather than shown as 0.

**Controls.** Row → editor at `GET /templates/{name}/{latest}`. `NEW TEMPLATE` → editor seeded with a
minimal skeleton at `version: 1`, saved by `POST /templates/{name}/versions`. Example actions →
`GET /examples/{name}` and 05's copy panel. Data: `GET /templates` (+`latest_origin`,
`operator_owned`), `GET /examples`.

**Copy.** "A saved version never changes. A run pins the whole tree when it is planned, so a save
reaches runs planned after it and no others." · "An example is stored under its own name while you hold
no version of that name. Once you save one, seeding withholds the file and the text stays readable
here." · "`templates/drafts/` is not seeded and is not listed."

---

## 02 · Template editor — `/templates/{name}/{version}` (B3, B4, C1–C3; D-1, D-5)

**Layout.** `288px | 1fr | 300px`. Left column stacks **VERSIONS** over **HELPERS** — helpers are used
while typing, so they take the otherwise idle column and the diagram keeps its own. Middle: banner →
toolbar (readout · VALIDATE · SAVE AS V*n+1*) → editor → error list → keyboard line. Right: DIAGRAM then
INPUTS BOUND AT START, unchanged.

**Version row.** `v3 · operator · 2026-09-30 · restored from v1` plus `pinned by n runs`; `RESTORE` on
every row but the open one, which reads `OPEN`. Origins shown verbatim: `shipped`, `operator`, `legacy`.

**Helpers.** Tabs `STEPS · INPUTS · HARNESSES & MODELS · SKILLS · EXPRESSIONS` from `GET /capabilities`.
Each entry names its accepted keys and defaults and carries `INSERT`, dropping a snippet at the cursor.
Footers state the list's size and its source, so no list is ever restated in the web-client. A null
skills manifest reads "The installed-skills manifest could not be read." — never an empty list. A failed
capabilities read renders `HELPERS UNAVAILABLE`; validate and save still work.

**Diagram.** Callee nodes read `initiative-hub-epic@5` with a marker box: `unpinned` (accent hairline)
or `pinned` (plain hairline). Legend: "*unpinned* — the call writes no `version:`; the number shown is
what it resolves to now." / "*pinned* — the call writes an integer `version:` and never moves."

**States.** *(a) Valid* — readout `valid · 0 errors · 14:07:31 — save enabled`; error area reads
`0 errors · 0 unvalidated steps — every step declares a gate.` SAVE enabled.
*(b) Invalid* — readout `2 errors · 14:09:06 — save disabled until both are cleared` in
`--color-signal-failed`; SAVE disabled; errors in order:

1. `line 36 · unknown key · prompts.redispatched` — "A prompts block accepts dispatch · rendered ·
   answer · halt · redispatch. Nothing is stored while an error stands."
2. `caller ·` **"saving initiative-hub-story v4 would strand initiative-hub-epic v5: callee input
   mismatch `workdir` (line 41)"** — then the way out: "initiative-hub-epic v5 calls this template
   unpinned, so it would resolve to v4 on its next run and bind an input v4 no longer declares. Either
   keep the `workdir` input, or pin that call to `version: 3`, save v4, then re-save the caller
   unpinned." with `OPEN INITIATIVE-HUB-EPIC V5 AT LINE 41`.

In (b) the diagram states it is showing the last text that validated, not what Save would store.
*Unavailable* — a failed version read keeps the page's existing `TEMPLATE UNAVAILABLE` readout.

**Controls.** VALIDATE → `POST /templates/{name}/validate`. SAVE → 03, then
`POST /templates/{name}/versions` (422 carries `errors[].template` for the reverse check). RESTORE → 04,
then `POST /templates/{name}/{k}/restore`. Diagram → `GET /templates/{name}/{v}/graph`.

---

## 03 · Save impact preview (D1; states B5)

**Layout.** A full-plane panel (`--color-line-strong` frame, `--detail-max`), never a floating card:
head, four blocks, action row. Reached only when the text validates and the reverse check passes, so it
has no refusal state.

**Copy.** Title **"This saves initiative-hub-story v4."** *Callers that resolve it unpinned and will
plan from v4 on their next run*: `initiative-hub-epic · latest v5 · calls it directly, line 88, no
version: written`; `initiative-hub · latest v3 · reaches it through initiative-hub-epic, which it also
calls unpinned`. *Callers pinned to an older version*: "None." *Runs*: **"Runs planned, queued or
running are unchanged."** with `4 unchanged / 2 running / 1 saved but not yet started — planned at save
time, so it keeps v3`. *What is written*: one row, origin operator, `version:` rewritten, "No other
template gains a version".

**Post-save readout.** `initiative-hub-story v4 is stored.` · `origin operator · validated 0 errors ·
pinned by 0 runs · v3 unchanged and still pinned by 4 runs` · the resolved tree · three next actions.

**Controls.** `SAVE V4` → `POST /templates/{name}/versions`; `BACK TO EDITOR` / Esc returns with the
text intact. A greyed v2 note names the pinned-caller re-point that is out of scope.

---

## 04 · Version history, diff and restore (B4; D-3)

**Layout.** `400px | 1fr`. Left: history rows `pick · ver · origin/date/provenance · action`, two rows
markable A and B. Right: unified diff with hunk headers naming the region and its lines.

**Diff rendering.** Added lines are `--color-text` with a 2px `--color-line-strong` rule at the left;
removed lines are `--color-text-tertiary` with none. The `+`/`-` glyphs carry the meaning: no fills, no
colour.

**States.** *Validates* — `valid · 0 errors · 0 unvalidated steps · checked 14:22:08 against this
instance's validator and store`; title **"Restoring v2 creates v6 from v2."**; then what follows v6
(unpinned callers, runs unchanged, and that v2's own explicit pins come back with its text).
`RESTORE AS V6` enabled → `POST /templates/{name}/2/restore`.
*Does not validate* — readout `1 error · checked 14:24:51 — restore disabled`; the error reads
**"v2 no longer validates: line 23 · agent step needs prompts.dispatch"**, then why ("The validator
began requiring a `prompts.dispatch` clause on every agent step on 2026-09-27; v2 was saved on
2026-09-26, before that") and that v2 and its runs are unaffected. `RESTORE AS V6` disabled;
`OPEN V2 IN EDITOR` is the offered path — "What you save becomes v6". Footer `422 · nothing was
written · the version list is unchanged`.
*Loading* — `validating v2 …`, RESTORE disabled. Restore is never enabled on an unknown result.

---

## 05 · Example, diff and copy (B2; shows A1/A3)

**Layout.** Detail header (crumb · name · `read-only` marker · dense meta: file path, image tag, digest,
state in this store, description), two equal columns — the example YAML and the diff against my latest
of that name — then the copy panel.

**States.** *Withheld* — "withheld · you own initiative-hub (latest v3 · operator, saved 2026-09-29).
Seeding did not replace your version and will not: a name with any operator version stays yours."
*Stored* — `stored as v1`; the diff column reads `identical to initiative-hub v1` on a hash match.
*No stored version of that name* — "you hold no version of this name — nothing to compare"; the first
copy target becomes `as version 1 of initiative-hub`. *Unavailable* — `EXAMPLE UNAVAILABLE · the file
could not be read from backend-api`.

**Copy panel.** Two radio targets: **"as version 4 of initiative-hub"** (v3 stays; the name resolves to
v4 for runs planned afterwards) and **"as a new name"** with a text field (placeholder `lower-case
slug: a–z, 0–9 and hyphens`; nothing resolves it yet). Beneath: **"The `name:` and `version:` lines are
rewritten server-side to the target you chose; every other line is stored byte for byte, comments
included. The rewritten text is validated before it is stored — including the check that no caller
would be stranded. A copy that does not validate is refused with its line and reason, and nothing is
written."** `COPY AS INITIATIVE-HUB V4` → `POST /templates/{name}/versions`.

---

## 06 · New workflow, typed inputs — `/workflows/new` (E1, E2; D-4)

**Layout.** The existing `190px 1fr 1fr` grid; form spans columns 1–2, side column holds **WILL PLAN
FROM**, **PRE-FLIGHT**, **PLAN**. A `HARNESS AND MODELS — DECLARED BY THE TEMPLATE` divider marks the
typed block as the template's own inputs rather than run settings.

**Controls.** A `harness` input renders a select over `GET /harnesses`, readiness inline per option
(`claude — enabled · probe ok 09:41:02 · v2.4.1`); one that is not enabled is disabled and carries its
failing check. A `model` input renders a select from `GET /harnesses/{harness}/probe`, keyed to the
harness input beside it, `— (harness default)` last. Start → `POST /runs`.

**States.** *(a) Ready* — `WILL PLAN FROM: initiative-hub@3 → initiative-hub-epic@5 →
initiative-hub-story@4`, with "Both calls are unpinned, so each resolved to its callee's latest stored
version just now." Pre-flight ends with `AGENT PAIRS · every distinct (harness, model) the plan
resolves`: `claude · claude-opus-5 — ok`, `claude · claude-sonnet-5 — ok`, "2 distinct pairs over 118
agent rows. Each harness was probed once." START enabled.
*(b) No probed list* — model inputs become text fields labelled "Free text: opencode's probe returned
no model list, so this instance holds no list to choose from. The name is passed to the harness as typed
and cannot be checked before the run starts." Pair lines read `not checked · no probed list`; START
stays enabled — nothing is known to be wrong.
*(c) Refused* — the select shows the stale value as `o5-mini — not in codex's probed list`, field note
"codex publishes o5 · o5-codex. Choose one of those, or choose a harness that serves o5-mini." A refusal
block (2px `--color-signal-failed` left rule — the one place a signal colour exceeds 7px) reads
**"This run is refused before any row runs: 1 of the 3 distinct agent pairs the plan resolves is unknown
to its harness."** then the row path (`epics.epic.stories.story.build` and 33 further rows), the
published list, and "Nothing is written: no run, no step rows, no worktree." START and SAVE WITHOUT
STARTING disabled. A probe that does not answer reads `probe did not answer` and also disables START.
*Unavailable / empty* — the existing `TEMPLATES UNAVAILABLE` and `NO TEMPLATE TO BIND` readouts stand.

---

## 07 · Run detail — planned from (supports B5; D-1)

**Layout.** Header and summary region only; stop zone, diagram, tabs and artifact tree are untouched.
`PLANNED FROM` is a new section left of the summary grid: one row per node, indented by depth, each with
its step path and how it was fixed (`pinned at plan time` / `resolved, then pinned`). The aside gains
`TEMPLATES` and `AGENT PAIRS IN THIS PLAN`.

**Copy.** **"This tree is frozen for this run.** Every one of its 431 step rows was written with its
resolved values before the first row ran, and nothing re-reads a template afterwards.
initiative-hub-story is now at v5; this run keeps v4 until it ends." Greyed v2 note: **"v2 — not in this
release · Retarget planned rows: change the harness or model of a row this run has not dispatched yet,
from this screen."** Data: `GET /runs/{id}` (+`template_tree`); a run whose tree is `{}` falls back to
the flat `pinned_versions` line, labelled `flat list — this run predates the tree record`.

---

## Validation, keyboard and focus (editor)

Validation runs on VALIDATE, 800 ms after the last keystroke, and as the first step of Ctrl/Cmd+S; the
readout always states a time, so a stale result reads stale. **SAVE is disabled whenever
`errors.length > 0`** and while a request is in flight; `unvalidated` paths are reported but never
disable SAVE — an ungated step is a fact, not an error. **Ctrl/Cmd+S** validates then saves if clean;
if not, focus moves to the first error row and the readout announces the count. **Esc** closes the
impact preview and returns the caret to its last position. Helper `INSERT` inserts at the cursor and
returns focus to the editor; the panel never steals focus on a tab change, and its tabs are a real
`role="tablist"` with arrow-key movement. An error row links to its line.

## Accessibility

Every state is carried by a word as well as by any colour: `ok`, `not in probed list`, `save disabled`,
`unpinned`, `pinned`, `withheld`, `read-only`. Contrast: `--color-text` on `--color-bg` ≈ 13:1,
`--color-text-secondary` ≈ 6.5:1, `--color-text-tertiary` ≈ 3.3:1 — tertiary only for labels, meta and
notes at ≥ 11px, never an error string or a control label. `--color-signal-failed` on
`--color-surface` ≈ 4.6:1, always colouring a word that already says the state. Focus ring: 1px
`--color-accent` outline at 1px offset, never removed. A disabled control keeps its label and sits
beside the readout that says why. Diff, YAML and pre-flight lists read in linear order: the glyph
precedes its line, and a hunk header heads the lines beneath it.

## Open UX questions for the Operator (with my default)

1. **The library uses its own row grid, not `--record-grid`** — a template name needs the wide column.
   *Default: allow it, recording the exception in DESIGN.md.* The alternative truncates
   `initiative-hub-story` at 128px.
2. **The impact preview lists transitive callers**, labelled "reaches it through …". *Default: keep
   them, labelled.* Direct-only would hide the caller runs are actually started from.
3. **Copy offers "as version n of the same name" first.** *Default: keep it first — it is the "take the
   upgrade" move; "as a new name" is second.*
4. **`legacy` origin is shown verbatim** rather than rendered as `shipped`. *Default: show `legacy`* —
   it is true, and the seeder's behaviour is stated beside it.
5. **HELPERS lives under VERSIONS in the left column**, not a fourth column or a drawer. *Default: left
   column.* If diagram and helpers must be visible at once, helpers move right and the inputs table goes
   below the diagram.
6. **A free-text model input keeps START enabled** (06-b). *Default: enabled, with the "cannot be
   checked" label* — a harness with no published list is a known instance shape, not a fault.
