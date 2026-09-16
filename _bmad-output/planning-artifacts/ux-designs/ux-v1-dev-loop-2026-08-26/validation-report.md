# Validation Report — ai-orchestrator v1 dev loop (2026-09-15 update, F2/F3)

Reviewed: `EXPERIENCE-v1.md` (updated 2026-09-15) + `../ux-ai-orchestrator-2026-08-25/DESIGN.md` (frozen), by two lenses: rubric walker (`review-rubric.md`) and adversarial (`review-adversarial.md`).

**Synthesis.** The pair is a usable contract: every F2/F3 scope item lands in a named surface with real rules, all 12 token references resolve (the revived blue exists as `signal-criterion #6C8CD5`), and the stop-zone table matches PRD §4.6 row for row. The debts found were consistency, not coverage: one stale navigation rule, two colour-vocabulary holes, a naming-rule strain, two missing step states, and a mock that leaked the diagram-only blue off-diagram. **Every high and medium finding against the spine or mocks was resolved the same session**; the only open items are explicitly deferred (DESIGN.md amendments to the next DESIGN.md cycle; the F5 PRD pass touch; delta folding at the next major rework).

Per-category verdicts: flow **strong** · tokens **strong** · components **adequate** · states **adequate** · visual refs **thin → resolved** · bloat **strong** · inheritance **adequate** · shape **strong**.

## High — all resolved

- **§4 Runs history rows linked to the run detail "scrolled to that path"** (both reviewers) — contradicted §2.3/F2; the target no longer resolved. → §4 now: "Rows link to that step's step-run detail (§2.3)."
- **"DON — green throughout" vs skipped-is-never-green; SKP/CAN had no diagram border colour** — → dialect: SKP/CAN carry the faint grey border and word token only; States: "done nodes green, skipped boxes grey."
- **StepRunDetail mock rendered RUN in blue off-diagram** — the exact leak the dialect forbids. → chip and table token green; "following" line plain; log fills viewport; widths unified.

## Medium — resolved

- Top-zone existence rule vs DON/CAN content placed there → one rule: needs-you/failed = full stop body · done = one-line summary · cancelled = one grey line · queued/running = zone absent.
- Release control one tab away from the actions it re-enables → reason + Release mirrored in the stop zone.
- §5 Templates "left-to-right like 2.3" pointed at the retired section → "like the run diagram (§2.2)".
- Frontmatter claimed PRD alignment while FR-23/FR-29/NFR-6 deltas pend the `bmad-prd` pass → annotated: "states the target, not the current PRD text."
- No width statement vs DESIGN.md 940px `detail-max` → delta 27: 1440px fluid; 940px for prose blocks only.
- Memlog's "full-viewport log" unstated; mock capped at 300px → stated in §2.3; mock fixed.
- §2.3 header printed label + path against the naming rule → rule rescoped: never two ways *in one component*; a detail header pairs label (crumb/eyebrow) + path (title).
- §2.3 missing done-attempt and skipped-step states → both added.
- Group-box border rule unstated → "group boxes are nodes; the path to a stop is amber at every level."
- Artboards unreferenced / "pending" claims stale → promoted to `mockups/`, linked from frontmatter + both section headings.

## Medium — deferred

- **DESIGN.md gaps** (no modal/tab-bar/group-box components; colour prose contradicts the dialect; `signal-criterion` still glossed CRT) → next DESIGN.md cycle. Mitigation: the dialect paragraph names the exact DESIGN.md sentence it amends; the mockups are the visual precedent.

## Low — resolved

- Hover expansion drop now stated in delta 23. · Artifact-modal Save failure behavior stated. · Follow-at-attempt-end stated. · Log-unavailable words-only line stated. · Blocked-step page links "answer on the run". · Test-ids use dot-index paths. · Followed-log exception added to the Refresh rule. · Mock nits (amber word in gate record, footer arithmetic, missing dispatch prompt, header order) fixed.

## Low — deferred

- F5's PRD deltas will touch the stop table / cost kv — the F5 pass must include an EXPERIENCE-v1 touch.
- 27 deltas across three generations — fold into the body at the next major rework.
- Regenerate the `.dc.html` canvas so `RunDetail.dc.html`/`RunDiagram.dc.html` stop presenting the superseded layout (build story).

Artifacts: `review-rubric.md` · `review-adversarial.md` · `validation-report.html` (this file's HTML twin).
