# _bmad-output

This folder is BMAD workflow output, **not product documentation**. For what the system
does today, read the code and `templates/*.yaml`; for how to develop here, read the root
`AGENTS.md`. Anything dated in this folder is a point-in-time record.

## What binds

- `architecture/ARCHITECTURE-SPINE.md` — the binding architecture (`AD-n` ids). When code
  and spine disagree, stop and say so.
- `designs/` — the visual and UX baseline for design work: `DESIGN.md` (visual authority,
  instrument-dark tokens), `EXPERIENCE-v1.md` (UX intent), `mockups/`.

## What is pending

- `specs/boot-environment-variables-conditional/PLAN.md` — two-tier boot environment
  contract, planned 2026-09-20, not yet implemented.
- `specs/unattended-hub-run/PLAN.md` — the client's nine change requests from a 64.8 h hub
  Run; templates first, nine small code stories, decisions D-1..D-6 open. Planned 2026-10-09.
- `specs/staged-story-flow/PLAN.md` — the staged story family (plan/implement/review, one
  session each) beside the build-auto flow; revision 2 of 2026-10-12, decisions D-1..D-5 open.
- `implementation-artifacts/post-mortem-2026-09-19.md` — orchestration-hardening fixes
  A–I, saved for future planning; no epic cut yet.
- `implementation-artifacts/deferred-work.md` — the append-only backlog.

## What lives here mechanically

- `implementation-artifacts/epic-5-screens/`, `epic-6-screens/`, `epic-7-screens/` —
  screenshot targets written by `make e2e-ui` (the e2e specs reference these exact paths).
- `implementation-artifacts/epic-7-handoff.md` — cited by `epic-7-screens.spec.ts`.
- Future BMAD skills recreate `planning-artifacts/` (and `sprint-status.yaml` via
  `bmad-sprint-planning`) when a new planning cycle starts.

## Where the history went

The MVP planning cycle (PRD, addendum, 9 epics with stories and briefs, reviews,
reconciles), the v2 mvp-feedback cycle (5 epics, all shipped), the 2026-08-24 long-term
PRD, v1 drafts, UX working files, epic handoffs, and per-story review records were removed
on 2026-09-23 (operator-authorized) because the work shipped and the documents no longer
matched the code. All of it is recoverable from git history before the removal commit.
