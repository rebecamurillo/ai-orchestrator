# Orchestration hardening — post-mortem and improvement proposals

Status: **saved for future planning — no epic cut yet** (Operator, 2026-09-19).
Source: full post-mortem of initiative run `01a0a98b-a156-7169-b266-a15aa9de94a8` (mvp-feedback, epics 1–5, 29 stories, 49 attempts, $321.48) plus a billing-grade CI analysis (139 runs, 2026-09-04 → 09-19). Evidence lives in the run's own `gate_record`/`attempt`/`step_run`/`trajectory` rows, the five branch histories (92 commits, of which 18 post-hoc repairs), and the GitHub Actions job telemetry. The rendered report is the Operator's "mvp-feedback Post-Mortem" artifact (2026-09-19).

## What actually went wrong (the three structural facts)

1. **Every epic branched from the same immutable base.** All five `checkout` steps recorded `base: "main"`; all 29 `git.sync` steps recorded `no upstream · no-op`. Main moved five times mid-initiative; no branch saw any of it. Execution was sequential in wall-clock but parallel in git — full integration cost, zero parallelism benefit. The dependency graph existed only as comments in `epics.yaml` and prose in the SPECs; the machine was never told it. The declared "epics 1+3 are disjoint" was false by 14 shared files; the three *unflagged* pairs (E2∩E3, E3∩E4, E3∩E5) produced the worst defects, including the forked Alembic chain.
2. **The two heaviest gates silently never ran.** `quality_gate_command = unit_test_command = "make lint & make test"` — a single `&` under `sh -c` backgrounds lint and returns only the test status, so lint was non-gating for all 29 verifies and all 5 baselines. Separately, the *seeded* `epic@1` template was an older body than `templates/epic.yaml` at the same version number (the seeder never bumps on content change) and that body has no `e2e` step — 0/29 stories ran e2e while every SPEC demanded it verbatim.
3. **The telemetry said 147/147 green.** All trajectory rows say `verify: done`. Epic 3 — the cleanest on record (1.00 attempts/story, zero parks, $0 waste) — shipped a broken generated contract and an e2e test that could never pass. Green telemetry, broken artifact.

Secondary patterns, all with receipts in the gate record:
- **All 8 blocked parks were anchor-test conflicts or self-contradictory story specs** — never agent confusion. ~25.2 h of the run's 58.7 h wall-clock was operator wait; the longest single stall 8.6 h (story 2-2). Stories 5-3/5-4 reverted ~2,500 lines because their specs' Code Map contradicted their own Boundaries ("irreconcilable without Operator exception 4").
- `accepted_paths` is cumulative for the whole Run: one acceptance at story 1-4 de-protected two files for 25 later stories.
- 4 hard kills at exactly 90.0 min (exit 143) hit epic 5 — the stall detector that fixes this was built by epic 3 but the orchestrator executing the work was the pre-epic deployed build (dev DB still at alembic 0012).
- Waste: $82.93 (26 %) of spend and 13.3 h (40 %) of agent time on attempts ending blocked/error.

## The fixes, one by one (A–I), with the behavior change each implies

**A — Dependency-carrying bases (P0, process/product).** `epics.yaml` gains a real `after:` field; the initiative template passes the predecessor's branch as the successor's base; `git.sync` rebases onto the base's current head instead of silently no-oping; epics run as separate Runs use the existing `after_run_id` (built by story 5-4 — the feature that would have prevented this initiative's failure mode was built by it, last, and never applied to itself). *Behavior:* conflicts surface at story time inside the dev loop where the agent resolves them, not at merge time where the Operator does. Trade-off: an epic inherits its predecessor's unmerged mistakes — guarded by C.

**B — Kill the silently-dead gates (P0, product).** Refuse shell-fragile gate commands (unbracketed `&`) or run gate commands as structured steps; version seeded templates by content hash (bump or refuse on mismatch with the repo file); add `make openapi` drift as a per-story verify sub-step; the epic-tail e2e step fails when its command is blank instead of planning away. *Behavior:* a green verify means the gates ran. Stories get slower and honest; the rework class ($83/26 %) disappears.

**C — Three new preflight lines (P1, product).** *stale base* (n commits behind base → fail past threshold), *alembic heads > 1*, *contended artifacts* (warn when another open branch/Run touched the same files). *Behavior:* bad integrations are refused before any spend; purely earlier information, no dev-loop change.

**D — Merge-per-epic cadence (P1, template/process).** An `await-merge` checkpoint between epics; the next epic bases on merged main. *Behavior:* five small merges during the initiative instead of one repair marathon after it. Overlaps A (A works unattended; D makes main the integration point with the Operator in the loop).

**E — Anchor-revision lists at spec time (P2, process/product).** The story spec must enumerate the anchor tests it will revise; the Operator approves the list once, with the story; the spec-gate refuses specs whose Code Map contradicts their own Boundaries. *Behavior:* the 8 mid-run parks become one upfront approval per story; review moves from interrupt-driven to batch. Stories that already did this (2-3, 2-4, 2-5, 4-4) ran with zero parks.

**F — Scope `accepted_paths` to the story frame (P2, product).** *Behavior:* an acceptance stops leaking across stories and branches; the same file may legitimately re-ask.

**G — Truthful verify telemetry (P2, product).** Record the resolved command and each sub-gate's exit status in the gate record, not one `verify: done` token; a retro verdict requires a post-merge gate run. *Behavior:* the run detail shows which gates ran and their real results; the epic-3 inversion (best telemetry, worst artifact) cannot recur unseen.

**H — CI tiered pipeline (approved).** Measured: 3,806 billed min/mo vs a 3,000 quota (block confirmed by run annotation); 38 % of spend is push+PR double-triggering of identical SHAs (concurrency group keys on `github.ref`, which differs per event); durability (+its cold image build) ran on ~113/118 executed runs; Docker layer cache: 0 `CACHED` layers ever; no paths filters while 28 % of commits are doc-only; no branch protection on main at all. Plan: PR tier (lint+drift, unit+coverage, e2e-api sans durability, e2e-ui ≈ 12.5 min) / merge tier on main (full chain + durability + images, GHA layer cache) / weekly scheduled cold build; plus branch protection with the PR tier required, budget alerts at 50/75/90 %, weekly job-timestamp minute tracking. Lands at ≈ 1,366 min/mo (−64 %). The anchor-free ~60 % (step/job `if:`, buildx cache overlay, `paths-ignore`, timeout 40→25, branch protection) needs no test revision and alone brings burn under quota.
> **Operator declaration (2026-09-19, Rebecam):** the CI trigger shape may change from `push: ['**']` + `pull_request` to `push: [main]` + `pull_request` + `schedule` + `workflow_dispatch`; `backend-api/tests/unit/test_ci_workflow.py:72-73` is revised under this declaration (named and dated in the revised test), asserting the new shape at least as thoroughly, with `README.md`'s Contributing section updated in the same commit.

**I — Operator runbook (approved as a documentation story; no data touched yet).** (1) Fix the Repository row: `quality_gate_command`/`unit_test_command` → `make lint && make test`, and give `quality_gate_command` a distinct e2e command (e.g. `make e2e-api`) so the epic-tail step means something. (2) Redeploy the orchestrator before the next initiative — the runs that built epics 4–5 executed on the pre-epic build and were hard-killed by the bug epic 3 had already fixed. (3) Product-side command validation is fix B's story.

## Scope decisions recorded so far (2026-09-19)

- CI story **in scope, declaration granted** (see H).
- Ops items handled as a **runbook story only** — nothing changed on the dev stack yet.
- Working recommendation for the epic cut when it happens: **A, B, C, E, G + H + I**, with **D deferred** (overlaps A) and **F deferred** (small; can ride any later epic). Not yet ratified — the Operator paused before the P0/P1/P2 selection; treat the recommendation as a default, not a decision.

## When the epic is cut

Follow the house chain: distill this document via `bmad-spec` into the epic folder's `SPEC.md` (authority order → spine ADs touched: AD-3, AD-7, AD-12/13, AD-16, AD-19; new invariants likely needed for template content-hash versioning and dependency-carrying bases — spine touch before stories), then `bmad-create-epics-and-stories` for `stories.yaml` (one entry + SPEC = a story's complete requirements, `invoke_dev_with` naming this folder), then `bmad-sprint-planning` readiness before any dispatch. Suggested epic id 6, branch `feat/v2-hardening-1`, folder `epic-06-trustworthy-green/` beside this file.
