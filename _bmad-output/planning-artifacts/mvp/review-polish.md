# Polish review — 2026-09-02 pass, prd.md

Lenses: structure, prose (bmad-review). Findings only; no edits made; no semantic changes to requirements proposed. Reader type: humans. Style baseline: Microsoft Writing Style Guide, with the document's own British spelling kept.

Purpose read: this document exists to help the operator-builder and `bmad-create-epics-and-stories` build the MVP dev loop from one settled, testable contract. Structure model: Reference/Database (numbered FRs with an identical Statement → Consequences schema), with a short Strategic/Context head (§0–§2) and a Glossary as the shared index. Word count 11,979 (word_metrics); §3 Glossary 1,130; §2.3 journeys 494.

Each list is ranked most-valuable first. "Replacement" gives the exact text where one applies.

---

## Structure

**S-1. Glossary — `Gate record` and `Status` entries; §4.6 table.** The Stop-kind list exists three times and the two Glossary copies have drifted: both omit `plan_stale`, which the §4.6 table (declared "the only list of Stops") carries. Tag: CONDENSE (~40 words).
- Replacement, `Gate record`: "Events are the Stop kinds of the §4.6 table, the Signals (see **Signal**), and the Run transitions (`start | done | failed | cancelled`)."
- Replacement, `Status`: "…with `needs-you` rendered as `CHK` for the `checkpoint` Stop and `BLK` for every other Stop kind of the §4.6 table;"

**S-2. Glossary entries carrying FR rules that the FRs restate.** Several entries define a term and then repeat a rule owned by an FR; one has drifted. Tag: CONDENSE (~80 words). Specifically:
- `Protected path` (line 74) lists the paths and says "when the Attempt started"; FR-31 owns the list and says "when the **Story's first Attempt** started". Replacement: "**Protected path** — a file an agent must not modify during a Run; the list and the check are FR-31."
- `Harness` (line 69) "A Harness is offered only after its **readiness run** passed (FR-33)" is restated verbatim in FR-14 (line 239, first sentence), in FR-8 pre-flight, and in FR-33's statement. Replacement: cut the first sentence of the FR-14 bullet at line 239 so it reads "A Harness exit caused by the Harness's own budget cap (…) is routed as a budget halt (FR-17), never as a retry."; keep the Glossary pointer.
- `Attempt` (line 78) "the Steps table shows the latest and counts the rest" and "Harness fields are empty on Attempts of non-agent Steps" restate FR-23 (line 355) and FR-25 (line 383). Replacement: end the entry after "(template retry, re-dispatch after an Answer or a verify failure, re-run after interruption)."
- `Worktree` (line 83) "A Run records every Worktree it created" restates FR-9 (line 183). Replacement: cut the sentence.
- `Signal` (line 73) and §4.6 description (line 288) both state validation-against-Status + gate-record write (AD-13). Replacement, Glossary: "Every Signal is validated and recorded as §4.6 states (AD-13)."

**S-3. FR-3 vs FR-4 vs UJ-1 — save refused or save stored?** FR-3: "The default branch must exist on the remote (checked by FR-4) or the save is refused with the reason." FR-4: "A failing check does not block the save: the Repository is stored with status `failed`…" (and UJ-1: "The Project is saved anyway"). Default-branch existence is one of FR-4's three checks, so the two sentences read as contradictory. Tag: QUESTION — for the author to reconcile; no replacement proposed (content is settled).

**S-4. Glossary — `Signal` and `Gate record` list the same nine Signal tokens twice** (lines 73 and 80). Tag: MERGE (~20 words). Covered by the S-1 replacement for `Gate record` ("the Signals (see **Signal**)").

**S-5. FR-14 (line 235, parenthetical) and §8 Resolved (line 468) state the same `--bare` finding twice**, including the version number and the flag list. Tag: CONDENSE (~45 words). Replacement for the FR-14 parenthetical: "*(Why: `--bare` hides the subagent tool and `Write` — §8, resolved. The Claude adapter therefore uses default discovery with an explicit allowlist.)*"

**S-6. FR-28 restates FR-17.** FR-28 bullet 1 "Run cost = sum of Attempt costs" and bullet 2 "Gateway spend logs are the authoritative figure; harness-reported usage is shown as provisional until the Gateway figure for the Attempt is available" repeat FR-17 bullets 1–2. Tag: CONDENSE (~25 words). Replacement, FR-28 bullet 2: "Spend source and provisional figures: FR-17."

**S-7. Glossary — `Question` (line 77) and FR-16 routing bullet (line 256) repeat the same parenthetical definition verbatim.** Tag: CONDENSE (~12 words). Replacement, FR-16: "`blocked` → Step `blocked`, Run `needs-you`, the Question shown (§3);"

**S-8. §5 Non-goals overlaps §6.2 Out of scope, §2.2, §11 and FR consequences.** Pairs: §5 b1 ↔ §6.2 b1 (spec generation) and §2.2 b3; §5 b3 ↔ §11 Safety (never merges / default branch / force-push); §5 b4 ↔ FR-7 b3 (diagram read-only); §5 b5 ↔ §2.2 b1 and §6.2 b5 (notifications); §5 b8 ↔ FR-30 b1 (skill folders never committed, AD-16). Tag: MERGE §5 into §6.2 as its opening "is-not" bullets, keeping one statement per fact (~60 words). Suggested surviving order in §6.2: the §5 sentences that have no FR home (b2 tests/oracle, b6 not a harness, b7 no session replay) first, then the current deferred list.

**S-9. §12 Platform duplicates NFR-7 and §0's pointer to `addendum.md`/the spine.** Two containers + Postgres + host services appear in both. Tag: MERGE §12 into NFR-7 (~40 words). Replacement for NFR-7's first clause: "the whole MVP is one Docker Compose file on the Mac mini — web-client, backend-api (with every Harness and the method pre-installed, running as one operator's desktop-first web app), Postgres — with LiteLLM, Langfuse, and the model server on the host (Docker on macOS has no GPU);" then delete §12.

**S-10. FR-10 bullet 1 restates FR-8.** "The Story list is read once, at planning, and never re-read during the Run; the rows exist before the first Step starts" = FR-8 bullets 5–6 and the Glossary `Run` entry. Tag: CUT (~25 words), or replace with "Rows and list files are fixed at the plan commit (FR-8)."

**S-11. Terms used in §1–§2.3 before §3 defines them** (`Clone check`, `Pre-flight`, spec checkpoint, `BLK`, **Needs you**, compare link, worktree, re-dispatch, "intent gap" — the last is never defined anywhere). The narrative-first order serves human readers. Tag: PRESERVE the order; add one pointer line under the §2.3 heading. Replacement: "*Capitalised terms and tokens are defined in §3.*"

**S-12. Glossary ordering.** `Attempt` (line 78) sits between `Question` and `Answer` although `Step` (line 63) and `Harness` (line 69) already depend on it; `Stop` (line 84) is last although `Needs you` (line 76) depends on it. Tag: MOVE `Attempt` to directly after `Step`; MOVE `Stop` to directly after `Signal`. 0 words.

**S-13. Glossary bold convention.** Bold marks both a headword and a cross-reference (**Working branch**, **Spec folder**, **Harness**, **Status** inside `Run`; **Clone check**, **Repository initialisation** inside `Repository`; **Attempt** inside `Step`; **Callee Version** inside `Template`; **Session id**, **readiness run** inside `Harness`; **Initiative folder** inside `Initiative`), so a reader cannot tell where a term is defined. Two are bold-as-defined but have no entry: **Working branch** and **Story step** (the latter is acceptably defined inline). Tag: CONDENSE the convention — bold only at an entry's own headword; plain text for cross-references — and add an entry drawn from FR-9/§1: "**Working branch** — the branch a Run commits an epic's Stories to: named by the epic in `epics.yaml` (`initiative`) or given as an Input (`epic`); created from the base branch when it does not exist (FR-9)." (+35 words)

**S-14. FR numbering placement.** FR-30 sits between FR-4 and FR-5; FR-31 and FR-33 between FR-17 and FR-18; FR-29 between FR-24 and FR-25; FR-32 after FR-28. Grouping by feature is right (§0 says so) and the numbers are stable ids referenced by §6.1 tiers. Tag: PRESERVE; make the convention explicit in §0. Replacement (append to "features are grouped in §4 with globally numbered FRs"): "— FR numbers are stable identifiers, not reading order; FR-29..FR-33 were added after the first numbering."

**S-15. FR-11 says "no pull request" twice** (line 207 `[NON-GOAL for MVP: creating the pull request]` and line 208 "— links, because no pull request is ever created"). Tag: CUT the line-208 tail (~8 words). Replacement: "Run Status becomes `done`; the card shows `n/n epics · m/m stories · k links`."

**S-16. FR-20 bullet 1 tail "Skip is not offered on a budget halt" restates the §4.6 table note and has drifted** (the note also excludes `plan_stale`). Tag: CUT (~7 words).

**S-17. FR-16 bullet "Every stop above maps to one Stop kind of the §4.6 table; there is no other list of stops."** — the second clause repeats §4.6's own "This table is the only list of Stops". Tag: CONDENSE. Replacement: "Every stop above maps to one Stop kind of the §4.6 table."

**S-18. §9 Assumptions index order.** "§4.4 FR-12" (line 489) precedes "§4.4 FR-10" (line 490). Tag: MOVE the FR-10 line above the FR-12 line. 0 words.

**S-19. §6.1 "Tiers" paragraph (line 434, ~140 words in one paragraph).** Four tiers in one run of text resist scanning. Tag: CONDENSE into four labelled bullets — MUST / SHOULD / COULD / Out of scope — text unchanged. 0 words.

**S-20. FR-19's second bullet (inline Spec-folder editing while parked) is not about "Continue at a Checkpoint"**; it is a general `needs-you` capability referenced as "FR-19 inline edit" in §6.1. The number is anchored, so moving is not worth it. Tag: PRESERVE; retitle. Replacement: "#### FR-19: Continue at a Checkpoint; edit the Spec folder while parked".

**S-21. `[NOTE FOR PM]` and `[NON-GOAL for MVP: …]` tags are used (§6.2, FR-11) but §0 introduces only `[ASSUMPTION]`.** Tag: QUESTION — either introduce them in §0's last sentence ("…inferences are tagged `[ASSUMPTION]` inline and indexed in §9; `[NOTE FOR PM]` marks a scope remark, `[NON-GOAL …]` an explicit exclusion.") or fold the two `[NOTE FOR PM]` remarks into plain bullet text.

Summary: 21 structure recommendations (1 QUESTION on content, 3 PRESERVE). If all cuts/condenses are accepted: about 380 words removed, ~35 added (S-13) — net ≈ 345 words, ≈ 3% of 11,979. No length target was given. Comprehension trade-offs: S-8 and S-9 remove two short self-contained sections that some readers use as quick "what it is not / what it runs on" summaries; S-11 and S-14 deliberately keep structure that looks cuttable.

---

## Prose

**P-1. British spelling — "Realizes" (×8: §4.1, §4.2, §4.3, §4.4, §4.5, §4.6, §4.7, §4.8 descriptions) and "optimize" (§7 "Counter-metrics (do not optimize)").** The document is otherwise British (initialise, colour, honours, apologises, finalises, labelled, cancelled). Replacement: "Realises UJ-…" ×8; "**Counter-metrics (do not optimise)**".

**P-2. UJ-3 card text contradicts the FR-11/FR-22 copy.** UJ-3: "`2/2 epics · 8/8 stories · 2 PRs`"; FR-11 and FR-22: "`n/n epics · m/m stories · k links`" (and FR-11: no pull request is ever created). Replacement: "By evening the card is in **Done** with `2/2 epics · 8/8 stories · 2 links`."

**P-3. Signal verbs capitalised inconsistently within one sentence.** FR-8 line 177: "the Operator cancels and starts a new Run, or Continues on the recorded plan". The document's convention capitalises Signal verbs (Retries, Continues, Skips, Cancel). Replacement: "the Operator Cancels and starts a new Run, or Continues on the recorded plan".

**P-4. Glossary-term capitalisation slips** (the document capitalises Glossary terms in use). One row, all locations:
- "verify step" → "verify Step": §2.2 b2 ("every verify step is `skipped`"), SM-C1 heading ("Verify steps `skipped`" → "Verify Steps `skipped`"). Keep the UI string `verify step will be skipped` (FR-3) as is.
- "worktrees"/"worktree" → "Worktrees"/"Worktree": FR-13 b1 ("a Repository's worktrees"), FR-13 b2 ("one worktree per Run").
- "spec folders" → "Spec folders": §5 b8.
- "Step path" → "Step Path": Glossary `Gate record` ("time, Step path, event"); FR-29 already uses "Step Paths".
- "Harness-reported" (FR-17 b2) vs "harness-reported" (FR-28 b2) → "Harness-reported" in both; "harness spans" (FR-27 b2) vs "Harness spans" (FR-33 b2) → "Harness spans".
- "the Run trace" (FR-27 b2) → "the Run's Trace".
- UJ-1 and UJ-2 mix cases: "Rebeca, the sole operator", "creates project *Website*", "two repositories", "per repository", "second repository", "that repository", "both repositories", "The clone check runs", "picks template `initiative` v1", "harness `claude`", "From the board", "opens the board" — while "Project", "Run", and "Pre-flight" in the same paragraphs are capitalised. Replacement: Operator, Project, Repository/Repositories, Clone check, Template, Harness, Board in those spots (or, if the journeys are meant to read as plain narrative, lowercase "Project"/"Run" there too — pick one).
- §12: "one operator" → "one Operator".

**P-5. Glossary `Run` entry — nested parenthetical with an em-dash aside is hard to parse.** Original: "bound to Inputs (Project, Repository, base branch, the folders and branch the Template declares — Initiative folder for `initiative`; **Working branch** and **Spec folder** for `epic` — **Harness**, model, budget, `re_review_done`)". Replacement: "bound to Inputs: Project, Repository, base branch, the folders and branch the Template declares (Initiative folder for `initiative`; Working branch and Spec folder for `epic`), Harness, model, budget, and `re_review_done`."

**P-6. FR-31 b1 — dangling "that existed".** Original: "every `AGENTS.md` that existed, and every file matching the Repository's `test_globs` that existed when the **Story's first Attempt** started." Replacement: "every `AGENTS.md` and every file matching the Repository's `test_globs` that existed when the **Story's first Attempt** started."

**P-7. FR-31 b3 — "either … or … , or" with three options.** Original: "The Operator either *Accepts* the change (…) or reverts on the branch and Retries, or Skips the Story." Replacement: "The Operator *Accepts* the change (…), reverts on the branch and Retries, or Skips the Story."

**P-8. Run-on bullets / single-sentence inventories** (split; text otherwise unchanged):
- FR-16 routing, "any other status…" (line 258, ~95 words): split after "Step `error`;" into a sub-bullet beginning "before parking, the Template's `expect` + `retry {max, prompt}` on the Step applies: …" and a second sub-bullet "when exhausted, Run `needs-you` with reason …".
- §4.6 table note (line 303, four clauses joined by semicolons): render as four bullets, one clause each.
- FR-5 statement (line 135, ~80-word parenthetical): move the parenthetical after a colon — "The system accepts Templates conforming to the DSL v1 and rejects anything else. DSL v1: Inputs of type …; a Step is …; kinds …; one `for_each` construct over a YAML list file; `{{variable}}` substitution only. The full key table is the spine's "Template DSL v1 keys"."
- FR-8 statement (line 160) and FR-23 statement (line 352): Consider: end the sentence after "…create a Run" / "…diagram view (FR-29)" and list the fields as a bulleted inventory?
- FR-14 b5 (line 239): two unrelated sentences in one bullet — resolved by S-2 (cut the first sentence).

**P-9. Serial comma dropped in two lists** (the document otherwise uses it). FR-14 b6: "the Run, Attempt, Story, Harness and Project identifiers" → "the Run, Attempt, Story, Harness, and Project identifiers". §4.6 description: "FR-16, FR-17, FR-31 and the glossary refer to it" → "FR-16, FR-17, FR-31, and the glossary refer to it".

**P-10. §11 Cost — garden-path clause.** Original: "an agent that calls the Gateway without the attribution headers its Harness config sets spends outside the halt". Replacement: "an agent that calls the Gateway without the attribution headers set by its Harness config spends outside the halt".

**P-11. FR-2 b2 — misplaced "only".** Original: "returned by API responses after save only masked to their last four characters". Replacement: "returned by API responses after save masked to their last four characters only".

**P-12. FR-10 sync bullet — "then Retries: Retry fetches again".** Replacement: "…never in the Worktree, then Retries; the Retry fetches again and fast-forwards."

**P-13. "intent gap" used as a concept but never defined** (UJ-3 card text — fine as the agent's own blocking-condition text — and the FR-18 assumption "resolves the intent gap on re-planning"; §9 line 491 repeats it). Replacement in FR-18 and §9: "resolves the blocking condition on re-planning".

**P-14. `retry` key set abbreviated inconsistently.** FR-5 declares "`retry {max, prompt, resume_session}`"; FR-16 writes "`retry {max, prompt}`" and then describes session resumption in prose. Consider: "`retry {max, prompt, resume_session}`" in FR-16 so the key that governs "resuming the same session where the Harness allows it" is visible?

**P-15. Column-name markup varies.** UJs bold the columns (**Running**, **Queued**, **Needs you**, **Done**); FR-22 backticks them (`Queued · Running · Needs you · Done · Failed`) and then writes "under Failed" plain. Replacement: pick one — bold, as in the journeys and the Glossary headword `Needs you` — and use it in FR-22 ("Columns **Queued · Running · Needs you · Done · Failed** always render…; `cancelled` Runs appear under **Failed**").

**P-16. Capital after a tag.** §6.2: "`[NOTE FOR PM]` this is the first thing…" → "`[NOTE FOR PM]` This is the first thing…"; "`[NOTE FOR PM]` cheap to add…" → "`[NOTE FOR PM]` Cheap to add…".

**P-17. Product and format names.** NFR-7 "one docker-compose file" → "one Docker Compose file" (the file is `docker-compose.yml`, but the product name is Docker Compose; FR-21 already uses `docker compose exec`). FR-32 b2 "a JSON-lines download" → "a JSON Lines download". §6.2 b3 "front-end and back-end" → "frontend and backend" (matches "backend container", "backend-api" elsewhere).

**P-18. FR-14 b1 — "HALTs" as a verb.** Consider: "`bmad-build-auto` halts with `blocked · no subagents` without the first"?

**P-19. FR-27 statement — "session id" is the Langfuse session here, not the Glossary `Session id`.** Consider: "join by the Run's trace context or Langfuse session id"?

**P-20. §6.1 Tiers — unclear phrase.** Original: "Template `initiative` (FR-29's initiative root with it)". Replacement: "Template `initiative` (and, with it, the initiative root node of FR-29)".

**P-21. Consider:** FR-8 first mention of *re-review done Stories* could bridge to the Input key the Glossary names — "*re-review done Stories* (`re_review_done`)" — so the label and the key are linked once?

Summary: 21 prose rows (4 phrased as Consider). Applying P-1..P-4 and P-9 alone resolves every spelling and token inconsistency found; the remainder are sentence-level clarity fixes within the existing structure.
