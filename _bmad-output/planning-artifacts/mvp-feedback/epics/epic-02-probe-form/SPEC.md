# SPEC — Epic 2: Fail at the form, not in the run

Selecting a harness probes it live and loads its real model list; an unusable harness or invalid model is refused at submission with the specific reason; the readiness Run becomes an informational diagnostic; every input explains itself. Realises features F1 and F10.

## Authority order

1. `_bmad-output/planning-artifacts/mvp/architecture/ARCHITECTURE-SPINE.md` (2026-09-15) — AD-2, AD-3, AD-10 (the probe rule), AD-20. Disagreement → `blocked`.
2. `_bmad-output/planning-artifacts/mvp/prd.md` (2026-09-15) — FR-33, FR-8, FR-14, NFR-8.
3. UX authority: EXPERIENCE-v1 §2.1 (New workflow: probe-gated harness rows, model select, pre-flight readout).
4. `stories.yaml` in this folder.

## Scope

- `probe` verb on each `scripts/harness/<name>.sh` reusing `doctor`'s checks (CLI at the pinned version, credentials valid via one trivial call, Gateway reachable) plus model enumeration.
- `Harness.probe() → ProbeResult{ok, failing_reason?, version, models[]}` on the port; the adapter shells the verb — application code reaches the result only through the port (AD-2). Shared fake in `tests/unit/fakes/`.
- `GET /api/v1/harnesses/{name}/probe`; probe cadence: the form probes on harness **selection and on submit**; `create_run` re-runs the Probe inline once at create — the result nothing re-probes after; other field changes re-run pure `plan_run` only.
- `create_run` and pre-flight read the Probe result; the stored `enabled` flag is read by **neither**; model outside the probed list → 422 naming the list, on every create.
- Readiness demoted: badge (last run time, first failing check) beside a *run readiness* link — informs, never gates; `sync_pins()` resets the badge on a pin change; the Probe's version check is what refuses a drifted CLI; queued and parked Runs keep their harness.
- Form polish: tooltips (why the input matters, what consumes it), mandatory `*` marks, optional inputs saying so in words.

## Out of scope

*Save*, `after:` dependencies, and the shared-repository consent warning (epic 5 owns their mechanism — the budget field's `(optional)` mark arrives with epic 3's story 3-2); any change to the readiness Run's evaluation checks; diagram or run-view surfaces (epic 1).

## Rules that bind every story

- Anchors read-only; TDD with the shared fakes (AD-18); generated contract only (AD-3); no new setting without `.env.example` + typed settings in the same change (AD-20).
- A probe failure is always the specific reason in words — never a bare disabled flag, never an icon (NFR-8).
- The two-writer rule is untouched; nothing here writes a Run or Step status.

## Verification

`make lint` · `make test` · `make e2e-api` · `make e2e-ui` green after every story; the epic's e2e pass exercises: a failing probe blocking submission with its reason, a model outside the list refused 422 server-side, and the readiness badge present but non-gating.
