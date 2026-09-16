# SPEC — Epic 1: See every Run clearly

The Operator answers "it failed, why?" and "where is the run?" entirely from the screen: a bookmarkable Step-run detail with every attempt's prompt, verbatim result, and full live log; the Run detail reworked around the embedded status-coloured diagram; artifacts readable in a modal. Realises features F2 and F3 of the approved mvp-feedback cycle.

## Authority order

1. `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` (2026-09-15) — AD-1, AD-3, AD-13, AD-15 bind every story here. Where a story and the spine disagree, stop and report `blocked`.
2. `_bmad-output/planning-artifacts/mvp/prd.md` (2026-09-15) — FR-23, FR-24, FR-25, FR-29, FR-33 context, **FR-34** (new), NFR-2, NFR-6 (diagram exemption), NFR-8.
3. UX authority: `_bmad-output/planning-artifacts/ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md` §2.2 (Run detail), §2.3 (Step-run detail) and the approved artboards in `mockups/`.
4. `stories.yaml` in this folder — a story's entry is its complete requirements together with this file.

## Scope

- New API route `GET /api/v1/runs/{id}/attempts/{attempt_id}/log` (cursor paging, download; `log no longer on disk` in words). All delivery through the web-client proxy — the browser never reaches the log volume (AD-1).
- New page `workflows/[id]/steps/[...path]` + island `StepDetail`; the bracket↔dot-index Path bijection in exactly one web-client util (encode and decode); the API is always called with canonical bracket Paths (AD-15).
- Run detail layout rework: stop zone top → central diagram → summary column (cost/trace, setup context **including model**) → one bottom tabbed region, gate record default. `?view=diagram` retired, redirecting to the Run detail.
- Diagram dialect per the AD-15 token→colour map (`done`→green, `running`→blue `signal-criterion`, `error`→red, `blocked|checkpoint`→amber, `planned|queued`→grey, `skipped|cancelled`→faint grey — never green); `graph.py` computes `k/n steps` into the `groups` payload (k = rows `done`, n = rows not `skipped`, no count when all skipped); one level per click, never hover; leaf → Step-run detail.
- Artifact modal: reader view (markdown rendered, YAML/code highlighted), `RENDERED · SOURCE · RAW`, download; edit-while-parked through the existing `PUT /runs/{id}/files`; planned list files read-only `planned at {sha}`.

## Out of scope

Signal actions on the Step-run detail (stops link back to the Run detail's stop zone); reply-or-restart mode (epic 3); probe/readiness surfaces (epic 2); Save/consent (epic 5); any new status token — statuses render stored tokens only.

## Rules that bind every story

- Anchors are read-only (root AGENTS.md rule 1); a story that conflicts with one reports `blocked`.
- TDD (AD-18): tests exist and fail before implementation; unit tests use the shared fakes in `tests/unit/fakes/`; no new doubles for ported dependencies.
- The contract is generated (AD-3): any route change runs `make openapi` and `pnpm gen:api`; `src/api/schema.d.ts` is never edited by hand.
- Two-writer rule untouched (AD-8): this epic reads state; it writes no status anywhere.
- Voice (NFR-8): copy states facts and mechanisms; `skipped`/`unvalidated` are words, never green (NFR-2).
- `signal-criterion` (#6C8CD5, DESIGN.md) enters the web-client tokens for exactly the diagram surface.

## Verification

`make lint` and `make test` green after every story; `make e2e-api` and `make e2e-ui` green (both landed); the epic's e2e pass exercises: log follow on a running attempt, the dot-index route round-trip, the `?view=diagram` redirect, and the artifact modal read-only list files.
