# Reconciliation — EXPERIENCE-v1.md → PRD (prd.md + addendum.md)

Purpose: every user-facing behaviour, state, screen element, copy rule and qualitative rule in `EXPERIENCE-v1.md` (input), checked against `prd.md` + `addendum.md` (PRD). "Landed" = a FR consequence, NFR, or addendum line makes it a testable/build requirement. "GAP" = the FR/NFR/addendum structure does not carry it — nothing would fail a test suite built strictly from the PRD if this were dropped.

Input: `ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md`.

## Attention model

| UX item | Landed / GAP | Note |
|---|---|---|
| Three-hue signal set (green=RUN, amber=BLK/CHK, red=ERR); grey for QUE/DON/SKP | Landed | FR-22/23 intro ("green running, amber needs you, red failed; nothing else is coloured"), NFR-6 |
| **"Exactly one element per card/row carries a signal colour — the reason it needs you"** | **GAP** | No FR/NFR states this discipline. NFR-6 only says "status is always a word token, never colour alone" — narrower than "at most one coloured element." Nothing in the PRD would catch a card with two amber elements. |
| "Words carry the state... colour only reinforces" (general principle) | Partially landed | NFR-2 codifies this for `skipped`/`unvalidated` specifically; the general principle (applies to every status word, not just those two) is not stated as a standalone rule. |
| Dropped six-colour escalation palette (BGT/RWK/INF/CRT) → collapsed into `BLK` with reason in words | Landed | Glossary "Status" + FR-16/17 route budget halt, verify-fail, blocked all to `needs-you`/BLK with a stated reason string. |
| Explicit enumerated list of where signal colour may appear (chip+token, rail count, column header, 2px banner rule, aged wait, one warning line, login rejection line) — "cards carry no coloured border and no coloured words" (delta #10) | **GAP** | This enumeration is visual-system-adjacent but also constrains *content* (e.g. "no coloured words" on a card) — not mirrored in any FR/NFR. Left entirely to `DESIGN.md`/implementation discretion. |

## Information architecture / shell / depth / refresh

| UX item | Landed / GAP | Note |
|---|---|---|
| 8-surface route map (Login, Workflows, New workflow, Run detail, Projects, New project, Runs, Templates) | Landed | Each surface = a PRD feature section (4.1–4.8); exact URL paths not specified but that's implementation, not a behaviour loss. |
| Rail: Workflows count + "n need you" amber when n>0, Runs; Configure: Projects, Templates | Landed | FR-22: "the rail shows `n need you` in amber only when n > 0." |
| Footer readout `2 running · 1 queued / 2 need you / updated hh:mm:ss · refresh` | Mostly landed | FR-22/24 cover running/queued counts and last-update time. The `· refresh` manual trigger is not required by any FR (only FR-24's failed-fetch retry control is). Minor GAP. |
| No notifications surface — "Needs you" is a column + rail count only | Landed | §5 non-goals ("no notification channel outside the UI"); addendum C rejects a notifications inbox explicitly. |
| Depth cap: Board → Run detail is the maximum | Landed (implicit) | No FR introduces a third level; consistent by omission. |
| New workflow is a page (not modal), **must be bookmarkable and survive a reload** | **GAP** | FR-8 specifies pre-flight behaviour but never requires the form to be a page, bookmarkable, or to retain state across a reload. Only the *save-failure* case for Projects (FR-4: "the form retains every entered value") has an explicit retention requirement — New workflow has no equivalent. |
| Only modal in the app: destructive confirm for Cancel run | Landed | FR-20: "Cancel requires a confirm." Nothing else in the PRD requires a modal, consistent with "only one." |
| Polling 5s while any RUN, else 30s; footer states last update | Landed | FR-24 exactly matches. |
| No content moves under cursor — state swap, not animation | Landed | FR-24: "No content moves under the cursor: updates apply as a state swap without animation." |

## Operator workflow (Flow.dc.html)

| UX item | Landed / GAP | Note |
|---|---|---|
| Login: token once per 30 days | Landed | FR-1 |
| New project fields + save runs Clone check per repository; failing repo blocks save with verbatim git output; form keeps every value | Landed | FR-2, FR-3, FR-4 |
| New workflow fields + pre-flight re-runs on every change; checks list; red line disables Start run and states the fix; Start run enqueues and states whether it starts now or queues behind a named run | Landed | FR-8 (consequences list matches almost 1:1) |
| Board: walk away, colour meaning at a glance; card shows story+step (`story 3-2 · build · claude · 00h 42m`) and story count `5/8` | Partially landed | Story/step line and `n/m stories` are in FR-22's description ("current or last Step, Story progress"). **The harness name on the card (`claude` inline, or "harness name right, tertiary" per screen 2 spec) is not in FR-22's/§4.7's enumerated card fields** (Working branch, Project·Repository, current/last Step, Story progress, Template Version, age) — GAP. |
| Run detail per state: BLK (Question, Answer box, Resume with answer, Skip story, Cancel run, secondary resume command); CHK (story spec file inline, Continue/Cancel run); ERR (failing command+output, Retry step/Cancel run) | Landed | FR-18, FR-19, FR-20, FR-21, FR-23 |
| Done: `DON` card `n/n stories · pushed · PR #` link; merge is human's, in GitHub | Landed | FR-11; §5 non-goals ("never merges") |

## Screens

### Login
| UX item | Landed / GAP | Note |
|---|---|---|
| Centered panel; ACCESS TOKEN input; Enter; hint line (token origin, cookie lifetime); nothing else on page | Landed (mostly) | FR-1 covers auth mechanics; the specific hint-line copy is a design/copy detail, not independently testable — acceptable delegation to visual layer. |
| Rejection: hint line replaced by `token rejected — n attempts left` in red; lockout after 5 failures/15 min | Landed | FR-1 verbatim, incl. `[ASSUMPTION]` tag for the numbers. |

### Workflows board
| UX item | Landed / GAP | Note |
|---|---|---|
| Bar: title, count readout incl. `oldest wait 2d 04h`, project filter, BOARD/LIST toggle, +New workflow | Partially landed | Filtering and LIST alternative covered by FR-22. "Oldest wait" as a surfaced bar metric is not required by any FR — GAP (minor). |
| Five status columns always render; empty column `—`, count 0 | Landed | FR-22 |
| **Empty-board state (`NOTHING RUNNING` + what's queued + link to New workflow) and first-run/zero-project state (`NOTHING REGISTERED` → Projects)** | **GAP** | FR-22 only specifies empty *columns* ("empty ones with `—` and count 0"). It never addresses the all-columns-empty board or the zero-Projects first-run state, both of which have mandated copy and a CTA in the UX spec. |
| Aged wait (>48h) turns age amber | Landed | FR-22 |
| Cards not draggable; whole card → Run detail | Landed | FR-22 |
| `cancelled` runs shown in Failed column with the word `cancelled` | Landed | FR-22 + Assumptions index |
| LIST toggle: same fields as record rows, for >~20 cards | Landed | FR-22 ("a LIST alternative"); exact threshold is UI-level, not a behaviour loss. |

### New workflow
| UX item | Landed / GAP | Note |
|---|---|---|
| Pre-flight lines are `ok / ! / x / —` **words**, never icons | **GAP** | Reinforces the "words carry state" principle for this specific readout; no FR states pre-flight results must render as words rather than icons/symbols. NFR-6 covers status *tokens* generally but doesn't extend explicitly to pre-flight check glyphs. |
| **"What will run" panel** — template step list with the loop expanded to the actual story count, so the operator sees the plan without a gate ceremony | **GAP** | No FR mentions this preview at all. It's a distinct, load-bearing UI element (it's the thing that replaces the old G2 plan-review gate per delta #6) and isn't represented anywhere in FR-8 or elsewhere. |
| Decision bar: Start run / Cancel / one note about queueing | Landed | FR-8 |

### Run detail
| UX item | Landed / GAP | Note |
|---|---|---|
| Header: crumb, chip+token+branch+age, unabridged meta line | Landed | FR-23 ("meta line is never truncated or collapsed"); header content matches FR-23's list. |
| Alert banner only when needs-you/failed: token, one sentence, right-aligned progress+spend | Landed | FR-23 ("an alert banner when the Run needs them or failed"); sentence/layout detail is visual, not a behaviour loss. |
| **Answer box: hint stating exactly where the answer is written and what happens next** (and the mandated copy in Voice: "Appended to `<file>` under `## Human Answers`, status reset to `draft`, story re-dispatched — say the mechanism, every time") | **GAP** | FR-18 specifies the *backend* mechanism (append under `## Human Answers`, status→`draft`, re-dispatch) as a testable consequence, but never requires the **UI to disclose this mechanism to the operator before they submit**. The transparency/honesty-of-mechanism copy rule — arguably the clearest "words carry the state" instance in the whole spec — has no FR home. |
| "Or continue in the session" command block, copy, session lifetime | Landed | FR-21 |
| Steps table columns `# · step · type · gate · status · time · harness · cost` | Landed | FR-23, verbatim match |
| Gate column: `liveness/deterministic/human`, checkpointed story shows `spec checkpoint` in amber | Partially landed | Gate strength values covered by FR-16/Glossary; the specific amber "spec checkpoint" gate-column rendering isn't called out — minor, visual-level. |
| Stories strip (`n/m`, done/current/future cell states) | Landed | FR-23 |
| Artifacts tree at spec-folder scope with changed-since-last-opened chips | Landed | FR-23 ("marks files changed since the Operator last opened this Run") |
| Cost & trace kv (spent/budget ratio, tokens, wall-clock, active operator time, Trace link, branch link) | Landed | FR-23, FR-28 |
| Gate record (append-only: started/blocked/answered/checkpoint continued/cancelled) | Landed | FR-23 references it; FR-18/19/20 each specify "written to the gate record" for their action. |
| State-specific behaviour: RUN (no banner, current row primary, no Answer section); CHK (banner names checkpoint, spec file inline replaces Question); ERR (red banner, last 40 lines of output); DON (banner replaced by one-line PR summary) | Mostly landed | FR-9/10/11/16/19/20/23 cover the mechanics. The **"last 40 lines of output"** specific truncation limit for ERR is not stated in any FR (FR-9/FR-10 just say "command output attached/output as context") — minor GAP. The CHK behaviour of the spec file replacing the Question *in place* is a layout detail, not independently testable. |

### Projects / New project
| UX item | Landed / GAP | Note |
|---|---|---|
| Project list row: name, repositories, runs, **one amber/red count if any** | **GAP (minor)** | No FR requires an aggregate needs-you/failed indicator on the Projects list. |
| Context text + hint that it's injected into every prompt | Landed | FR-2, FR-15 (backend behaviour); UI hint text is a copy detail. |
| Repositories table incl. clone-check status; repo without `quality_gate_command` shows `— none declared` / `verify step will be skipped` | Landed | FR-3 verbatim |
| Credentials kv (token set/scope, litellm key+budget, env var count) | Landed | FR-2 (masked token), addendum G (gateway key per project) |
| New project form + live Clone check readout; failure prints verbatim git output **and a one-line fix** | Partially landed | FR-4 requires verbatim output on failure but does not require a suggested one-line fix (that requirement only appears for the *New workflow* pre-flight, FR-8: "states the fix"). GAP: parity between the two screens' failure copy isn't guaranteed by the PRD. |
| One failing repository blocks Save project; form keeps every value | Landed | FR-4 |

### Runs screen
| UX item | Landed / GAP | Note |
|---|---|---|
| Bar: project filter + status filter (`ALL·QUE·RUN·BLK·ERR·DON`) | Landed | FR-25 ("filtered by Project and Status") |
| Queue section incl. its own parameters in the section head (`concurrency 2 · one active run per repository`) | GAP (minor) | Concurrency behaviour is covered by FR-13; displaying those parameters in the Runs-screen queue header is not required. |
| Blocked run shows `—` position, `waiting for your answer · not queued until then` | Landed | FR-25 |
| History table columns incl. current-rows-promoted emphasis | Partially landed | Column set matches FR-25 exactly; "current rows promoted" (visual emphasis) is not in the FR — minor/visual. |
| Rows link to Run detail **scrolled to that step** | Partially landed | FR-25 requires the link; the deep-link-to-step-position behaviour is not specified — minor. |

### Templates
| UX item | Landed / GAP | Note |
|---|---|---|
| Three columns: versions list, YAML editor, Diagram | Landed | FR-5, FR-6, FR-7 |
| **"Inputs bound at start" table** alongside the diagram | **GAP** | Not mentioned in FR-7 or elsewhere; a distinct UI element with no FR coverage. |
| Bar: validation timestamp, Validate, Save as vN+1; saving never mutates pinned version (hint explains) | Landed | FR-5, FR-6 |
| Escalation edges not drawn — "they all go to Needs you" | Landed (implicit) | Consistent with the collapsed BLK model; no diagram FR requires drawing escalation edges, so nothing contradicts this. |

## State vocabulary

| UX item | Landed / GAP | Note |
|---|---|---|
| `QUE/RUN/BLK/CHK/ERR/DON/SKP/CAN` with Run- and Step-level meanings | Landed | PRD §3 Glossary "Status" entry mirrors this table field-for-field; FR-9/10/11/16/17/19/20 implement each transition. Best-covered section of the whole spec. |
| `SKP` "rendered as the word `skipped`, never green" | Landed | NFR-2, verbatim. |

## Voice

| UX item | Landed / GAP | Note |
|---|---|---|
| **General tone principle: "facts, identifiers, no congratulation"** | **GAP** | This is the single clearest qualitative/tone rule in the document and it has **no NFR or FR home at all**. NFR-2 ("Honesty of status") is adjacent but narrower — it only guarantees `skipped`/`unvalidated` are never rendered green, not that copy throughout the app avoids congratulatory/editorializing language. Nothing in the PRD would catch a "Great job, all done! 🎉" string on the `DON` card. |
| "Appended to `<file>` under `## Human Answers`... — say the mechanism, every time" | See Run-detail GAP above | Same gap as the Answer-box disclosure item; the *backend* mechanism is a tested FR-18 consequence, the *requirement to say it in the UI* is not. |
| "verify step will be **skipped**" (config time) vs "skipped — no `quality_gate_command`" (run time) | Partially landed | Config-time copy is FR-3 verbatim. Run-time copy: FR-9/FR-23 require the word `skipped` to appear but don't mandate the reason-qualified run-time phrasing (`skipped — no quality_gate_command`) — minor GAP. |
| "Starts immediately if the repository is free, otherwise queues behind the run holding it" | Landed | FR-8 |

## Test-ids

| UX item | Landed / GAP | Note |
|---|---|---|
| `<surface>-<component>[-<instance>][-<field>]` grammar, surface prefixes | N/A — out of PRD's scope by design | Explicitly deferred to "when the front-end stories are cut"; not a PRD-level requirement, so not scored as a gap. |

## Deltas from the 2026-08-25 spine

| UX item | Landed / GAP | Note |
|---|---|---|
| 1. Status columns, not pipeline-stage columns | Landed | FR-22; addendum C rejects pipeline-stage columns explicitly. |
| 2. No Notifications surface | Landed | §5 non-goals; addendum C. |
| 3. No G2/G3 pages; checkpoints inside Run detail | Landed | §6.2 out-of-scope; FR-19. |
| 4. Answer box primary, resume command secondary | Landed | addendum C; FR-18, FR-21. |
| 5. Signal palette reduced to green/amber/red+grey | Landed (via NFR-6) | Visual-system detail, correctly left to DESIGN.md; NFR-6 gives the behavioural floor. |
| 6. New workflow is a page w/ pre-flight, replacing G2 plan review | Landed structurally, content GAP | FR-8 covers pre-flight; the "What will run" plan-preview panel that actually replaces the old gate ceremony is the GAP noted above under New workflow. |
| 7. Templates: editable YAML + diagram, versions immutable once pinned | Landed | FR-5, FR-6, FR-7; addendum C. |
| 8. Five equal fluid columns (not fixed+scroll) | N/A — visual-system detail | Correctly left to DESIGN.md/EXPERIENCE-v1.md. |
| 9. Dense tables vs. five-column record row are different components | N/A — visual-system detail | Same. |
| 10. Explicit signal-colour-allowance enumeration | **GAP** | Folded into the Attention-model GAP above (exactly-one-signal-colour discipline). |

## Summary of GAPs (structural, not exhaustive of every minor item)

1. **No general voice/tone NFR** — "facts, identifiers, no congratulation" has no requirement anywhere; nothing enforces non-congratulatory, fact-only copy.
2. **No empty-board / zero-project first-run states** — FR-22 only covers empty columns, not `NOTHING RUNNING` / `NOTHING REGISTERED`.
3. **No "What will run" plan-preview panel** on New workflow — the element that substitutes for the old plan-review gate is unrepresented in FR-8.
4. **No requirement that the Answer box disclose its own mechanism to the operator** — FR-18 tests the backend append/reset/re-dispatch behaviour but not that the UI states it before submission.
5. **No "exactly one signal-coloured element per card/row" discipline** — NFR-6 is weaker (word-token-not-colour-alone) than the UX spec's stricter one-signal-colour rule and its explicit list of allowed colour placements.

Secondary/minor gaps also on record above: harness name missing from the Board card's required-fields list (FR-22/§4.7); New workflow form not required to survive a reload/be bookmarkable; New Project Clone-check failure not required to include a one-line fix (parity gap with New workflow pre-flight); pre-flight results not required to render as words-not-icons; ERR banner's "last 40 lines" truncation limit unstated; several small display-only items (oldest-wait bar metric, project-list aggregate amber/red count, Templates "Inputs bound at start" table, queue-section parameter display, history-row deep-link-to-step, run-time `skipped — no quality_gate_command` phrasing).
