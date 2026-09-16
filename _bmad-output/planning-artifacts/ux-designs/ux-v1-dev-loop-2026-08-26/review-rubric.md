# Spine Pair Review — ai-orchestrator (v1 dev loop, 2026-09-15 update)

Reviewed: `EXPERIENCE-v1.md` (updated 2026-09-15) against `../ux-ai-orchestrator-2026-08-25/DESIGN.md` (frozen), `.memlog.md`, `.working/RunDetail-v2.html` + `.working/StepRunDetail.html`, `sprint-change-proposal-2026-09-14.md` (F2/F3), `feedback-inventory.md` (items 1, 5, 11, 12, 15, 16), and PRD §4.6.

## Overall verdict

The pair is a usable contract: every F2/F3 scope item lands in a named surface with real behavioral rules, every token reference resolves to a DESIGN.md frontmatter token with a hex, and the new §2.2 stop-zone table reproduces the PRD §4.6 table row for row including the signals-admitted subsets. What stands between this and clean source-extraction is a short list of consistency debts: one stale navigation rule in §4 (Runs) that contradicts §2.3's entry points, the finished `.working/` artboards still described as "pending" from the spine, a naming-rule strain the §2.3 header creates without declaring, and two step-level states §2.3 does not cover.

## 1. Flow coverage — strong

Checked each of items 1, 5, 11, 12, 15 (display side), 16 against a surface/behavior; walked the operator-workflow narrative against the new §2.2/§2.3.

- Item 1 (full/live logs, step detail): §2.3 — full log for every step kind, cursor-paged, live follow, download raw, AD-1 proxy delivery, three entry points, bookmarkable. Covered.
- Item 5 / 16 (artifacts readable, markdown reader): §2.2 artifact modal — reader view, `RENDERED · SOURCE · RAW`, download. Covered.
- Item 11 (model invisible; layout): model in the header meta line (delta 26), setup at top, diagram central, cost/trace right, artifacts below cost/trace in a modal, steps and gate record as tabs (memlog-recorded consolidation of item 11's "toggle" + "full-width below" into one tabbed region). Covered, deviations documented as decisions.
- Item 12 (diagram colour + iteration boxes): §2.2 diagram + the dialect paragraph; one box per iteration with `k/n steps`, AD-15 aggregate, level-by-level expansion. Covered.
- Item 15 display side (retry prompt visible): §2.3 attempts disclose the dispatch prompt and, for a retry, the exact `retry.prompt` the template declared. Covered.
- Narrative: step 4 ("the diagram is the centerpiece… click the box that is moving to open its step and read the log") and step 5 cohere with the reworked sections.

### Findings
- **high** §4 (Runs, line "Rows link to the run detail scrolled to that path") contradicts §2.3 ("Reached from … a Runs-history row") and F2's stated scope ("clicking any … history row opens a Step-run detail"). The "scrolled to that path" behavior also presupposes the retired always-visible steps table (delta 23 / delta 26). A consumer implementing the Runs surface from §4 wires the wrong link target (EXPERIENCE-v1.md §4). *Fix:* update the §4 sentence to "Rows link to the step-run detail (§2.3)".
- **low** The proposal's F3 says iteration boxes expand "on click/hover"; the spine commits to click-only (memlog decision) but no delta states that hover was considered and dropped (EXPERIENCE-v1.md delta 23). *Fix:* one clause in delta 23 ("hover does not expand — click only").

## 2. Token completeness — strong

Extracted every `{path.to.token}` reference in EXPERIENCE-v1 (12 distinct): `colors.signal-qa`, `colors.signal-blocked`, `colors.signal-infra`, `colors.signal-criterion`, `colors.line`, `colors.line-strong`, `colors.surface`, `colors.text-secondary`, `colors.text-tertiary`, `typography.row-title`, `typography.meta`, `typography.eyebrow`. All resolve to DESIGN.md frontmatter tokens. `signal-criterion` — the blue the dialect revives — exists with hex `#6C8CD5` (DESIGN.md line 29), and the `.working/` artboards use exactly that value (`--blue:#6C8CD5`). No misses.

### Findings
- (none)

## 3. Component coverage — adequate

The five components the update introduces, checked for real behavioral rules:

- **Artifact modal** — strong: open state (reader), format toggle, download, edit precondition (parked + no terminal session), save mechanism with the verbatim commit message, list-files read-only with the `planned at {sha}` line.
- **Tabbed region** — adequate: three named tabs, default tab, per-tab content specified.
- **Group/iteration box** — strong: collapsed content, AD-15 aggregate as the box's token, click grammar, default-expansion rule (path to current step).
- **Follow control** — strong: on by default while running, scroll-up pauses, control resumes, `following · updated hh:mm:ss` line, poll-interval append.
- **Attempts table** — adequate: ordering, selection, columns, prompt disclosure, non-agent-row degradation.

DESIGN.md is frozen this cycle; the gaps below are findings for a future DESIGN.md pass, severity by downstream impact.

### Findings
- **medium** DESIGN.md defines no modal, tab, or group-box component; its only overlay guidance is one sentence in Elevation & Depth ("full-plane panels with a `{colors.line-strong}` frame, not floating cards"), and its Components section has nothing for tab bars or bordered group containers. Story-dev will invent sizing, backdrop, and tab-active treatment (DESIGN.md, Components; future DESIGN.md pass). *Fix:* add `modal`, `tab-bar`, `group-box` component token blocks in the next DESIGN.md cycle; until then the `.working/` artboards are the only visual precedent — promote them (see §5).
- **medium** Whether a group box (collapsed or expanded) carries the aggregate's border colour is not stated in the spine — the Colour bullet says "border + token per node", and whether a group box is a "node" is left open. The artboard answers yes (epic-1 group and story-4-1 group both border amber), so BLK renders three amber borders on the path, while the States bullet says "the stopped node amber" in the singular (EXPERIENCE-v1.md §2.2 diagram Colour/States vs `.working/RunDetail-v2.html`). *Fix:* one sentence: "group boxes are nodes: a box's border carries its AD-15 aggregate colour, so the path to a stop is amber at every level."
- **low** Artifact-modal Save failure (commit rejected, branch moved) has no stated behavior (EXPERIENCE-v1.md §2.2 artifact modal). *Fix:* state the failure line (verbatim git output in the modal, value kept), consistent with the clone-check pattern.
- **low** Follow behavior when the attempt ends mid-follow is unstated (log stops, token flips on next poll?) (EXPERIENCE-v1.md §2.3 Log). *Fix:* one clause: "when the attempt ends, following stops with the final line in view and the token updates on the next poll."

## 4. State coverage — adequate

§2.2 walk: stop zone covers every §4.6 stop kind — blocked, spec/done checkpoint, verify failed 2/2 + re-baseline failed after skip, budget, timeout, push rejected + sync diverged, protected path, the six-condition misconfigured family, plan stale, internal — each with body, primary, and the exact signals the PRD admits (budget and plan-stale correctly omit the skips). `RUN`, `ERR` (terminal, no Retry, `start a new run`), `DON` (summary + compare links + skipped ids), `CAN`, queued (`waiting: …`), terminal-session-in-progress, empty board/failed-fetch (Shell) — all present.

§2.3 walk: running (follow), failed (`ERR`, one red exit line), planned/queued (`no attempts yet`) are covered. Two step-level states are not.

### Findings
- **medium** §2.3 states nothing for a **done** attempt (static log, `DON` token — inferable but unstated) or a **skipped** step (the Steps table links every planned row to §2.3, so `skipped · already done` / `skipped · skipped by operator` rows have a destination page whose content is undefined — no attempts, but is the skip reason shown?) (EXPERIENCE-v1.md §2.3 States). *Fix:* add both to the States line: done = static log, no follow control; skipped = dispatch context + the skip reason in words, no attempts section.
- **low** A blocked/checkpointed step's §2.3 page shows the attempt but the actions live in the run's stop zone; no pointer back is specified (EXPERIENCE-v1.md §2.3). *Fix:* one line: the stopped attempt's row states the stop reason and links "answer on the run" to the run detail.
- **low** Log-unavailable (file rotated/removed for an old run) has no state (EXPERIENCE-v1.md §2.3 Log). *Fix:* a words-only line (`log no longer on disk`), never an error surface.
- **low** With the SESSION tab holding the resume command, the terminal-session-in-progress line lives "under the command block" (in the tab) while the actions it disables sit in the stop zone — the operator sees disabled buttons with the reason one tab away (EXPERIENCE-v1.md §2.2). *Fix:* mirror the one-line reason in the stop zone whenever actions are disabled by a session.

## 5. Visual reference coverage — thin

The two artboards exist and match the spine closely (stop zone above diagram, dialect borders with word tokens, group boxes with `k/n steps`, tabbed region, dot-index URL, attempts table with disclosed retry prompt, follow bar) — but the spine does not reference them: frontmatter still says "RunDetail and RunDiagram artboards are superseded … pending new artboards", §2.2 says "artboard pending", §2.3 says "artboard pending". `diagram-color-dialects.html` is a decision aid and needs no link.

### Findings
- **medium** `.working/RunDetail-v2.html` and `.working/StepRunDetail.html` are unreferenced from the spine, which still claims the artboards are pending — a consumer would not find the only visual precedent for the modal/tab/group-box components DESIGN.md lacks (EXPERIENCE-v1.md frontmatter `screens:` line, §2.2 heading, §2.3 heading). *Fix:* promote both into `screens/` (or the canvas) at Finalize and replace the three "pending" notes with references; regenerate `ai-orchestrator-v1-screens.html` so `RunDetail.dc.html`/`RunDiagram.dc.html` stop presenting the superseded layout as current.

## 6. Bloat & overspecification — strong

The stop table restates PRD §4.6 but adds real rendering content (body-in-place-of-question, primary vs also-offered) — it earns the duplication. The dialect paragraph, deltas 20–26, and the §2.3 spec are each one screen or less. No behavior is specified twice with different words except the §4 line flagged in category 1.

### Findings
- **low** The stop table and the cost kv will be touched again this same cycle by F5's PRD deltas (timeout stop becomes the stall reason `stalled {path}: no activity for {n} min`; budget optional adds `tracked, no cap`), and nothing marks these rows as pending amendment (EXPERIENCE-v1.md §2.2 stop table, summary column). *Fix:* nothing to change now — but the F5 PRD pass must include an EXPERIENCE-v1 touch; note it in the proposal's handoff table.

## 7. Inheritance discipline — adequate

Verified verbatim: all ten §4.6 stop kinds, reason texts, and signal subsets match the PRD table; status tokens match the frozen vocabulary (Run `QUE RUN BLK CHK DON ERR CAN`, step `planned` rendered `QUE`, `CAN` run-only); FR/AD/NFR ids (FR-20, FR-24 poll, AD-1, AD-15, NFR-6, items 1/5/11/12/15/16) are used correctly; delta 22 correctly normalizes the proposal's "orange" to the amber `signal-blocked` token. The label-vs-path rule is applied correctly in the diagram footer (label), Steps tab (path), and gate record (path).

### Findings
- **medium** The §2.3 header prints the step **both** ways — crumb + label line, then "the path in full" — while the naming rule states "A step is never named two ways on one screen" (EXPERIENCE-v1.md §2.3 Header vs "Naming rule: label and path"). The artboard does the same (label in crumb, path as title). *Fix:* declare the exception in the naming rule ("the step-run header is the one surface that prints both: label as the crumb, path as the title") or drop the label from the §2.3 header.
- **medium** (future DESIGN.md pass) DESIGN.md's frozen prose contradicts the dialect: "No other signal colour extends beyond its chip and token" (Colors), `signal-criterion` defined as `CRT · unmatched criterion`, and the Do/Don'ts colour rows. EXPERIENCE-v1 wins for v1 and says so, but a consumer reading DESIGN.md alone gets the old law (DESIGN.md Colors / Do's and Don'ts). *Fix:* in the next DESIGN.md cycle, add the diagram-border exception beside the existing alert-banner/aged-amber exceptions and retire `signal-criterion`'s CRT gloss.

## 8. Shape fit — strong

The lean delta-doc structure still earns its place after the edits: the attention model absorbs the dialect as a named, scoped exception rather than a contradiction; the IA table, depth rule, and modal count were all updated where the new surfaces touch them; deltas 20–26 give a consumer the exact diff from the 09-02 contract with reasons and decision attribution ("operator's call, 2026-09-15"); the memlog's triaged assumptions all landed in the text (dot-index route, default expansion, follow-by-default). §2.2 is now the longest screen spec by far, but it is the product's decision surface — the length is content, not padding.

### Findings
- **low** Three generations of deltas (1–10, 11–19, 20–26) now bind; a consumer must fold 26 deltas to reconstruct current law, and some early deltas are already superseded by later ones (e.g., delta 3's "checkpoints live inside the run detail" now means the stop zone) (EXPERIENCE-v1.md delta sections). *Fix:* nothing this cycle; at the next major rework, fold the deltas into the body and restart the list.
- **low** Frontmatter `status: final` while both new artboards are unpromoted and marked "pending" overstates completion (EXPERIENCE-v1.md frontmatter). *Fix:* resolve with the §5 promotion.

## Mechanical notes

- **Stale navigation rule:** §4 Runs "Rows link to the run detail scrolled to that path" vs §2.3 entry points — the one true cross-reference break (category 1, high).
- **Stale artboard claims:** frontmatter `screens:` line, §2.2 "(RunDetail.dc.html superseded, artboard pending)", §2.3 "(artboard pending)" — all three predate the `.working/` artboards written 2026-09-15 14:17–14:18 (category 5).
- **Frontmatter completeness:** `title`, `status`, `created`, `updated`, `supersedes`, `visual`, `screens`, `aligned-to` all present; `aligned-to` correctly adds the sprint-change proposal. `updated: 2026-09-15` matches the file mtime.
- **Name consistencies verified:** stop reason texts, signals-admitted subsets, and skip-omissions match PRD §4.6 exactly; `Accept changes` is the spine's rendering of PRD's "Continue (accept)" and delta 12 already recorded it; footer format `step 15 of 22` vs voice line `12/22 steps` are two declared formats for two contexts (footer vs box), not a clash.
- **Diagram footer example arithmetic:** the spine's example says `step 15 of 22` while the artboard shows `step 15 of 34` with the epic at `22/34 steps` — illustrative values only, but aligning them at promotion avoids a consumer reading `22` as the run total.
- **Test-ids:** the new-surface prefixes (`wf-tab-<name>`, `wf-artifact-modal[-edit]`, `wf-diagram-node-<path>`, `step-attempt/prompt/log/follow/download`) cover every new interactive element named in §2.2/§2.3; no gaps found.
