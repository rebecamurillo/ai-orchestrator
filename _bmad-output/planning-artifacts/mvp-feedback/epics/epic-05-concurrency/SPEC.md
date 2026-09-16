# SPEC — Epic 5: Safe concurrency

Different branches of one repository run in parallel behind an informed-consent warning; a Run can be saved without starting and chained with `after: {run_id}`; every waiting condition is a reason text. The one AD-level change of the cycle (AD-12), deliberately last. Realises feature F4.

## Authority order

1. `ARCHITECTURE-SPINE.md` (2026-09-15) — AD-6, AD-8 (terminal fan-out, `engine.enqueue` exception), AD-12 (the whole rule), AD-13 (`start`, `dependency`), AD-14 (held-branch refusal + backstop). Disagreement → `blocked`.
2. `prd.md` (2026-09-15) — FR-8 (save, consent), FR-13, FR-25, §4.6 (`dependency` row), NFR-8.
3. UX authority: EXPERIENCE-v1 §2.1 (decision bar: *Save*, consent warning) and §4 (queue reasons).
4. `stories.yaml` in this folder.

## Scope

- `engine.enqueue(run_id, partition_key = "{repository_id}:{declared branch}")` — the branch the plan's `git.worktree` row was **declared** from, never an allocated fresh name; `initiative` plans use the base branch; the engine port's `partition_key` widens to `str` deliberately; enqueue idempotent on `run_id`; `MAX_ACTIVE_RUNS` unchanged; a `needs_you` Run still holds partition and slot.
- Pre-flight held-branch refusal extended to branches **declared by `git.worktree` rows** of non-terminal Runs; `git.worktree` executor backstop park `misconfigured: branch held by {run}`.
- Shared-repository consent: warning with the facts (which Run, which branch, which Spec folder), explicit confirmation `this can lead to merge conflicts` — never refused, never silently queued.
- *Save*: same planned rows, no enqueue; saved = status `queued`, `engine_ref` null (the null is the saved state — application reads only its presence, content stays adapter-only per AD-6); Queued column, reason `saved — not started`; `start` Signal (valid when `engine_ref` null ∧ status `queued`) — gate event `started_by_operator`, clears `after_run_id`, re-reads the Probe exactly as `create_run` (epic 2's machinery).
- `after: {run_id}` (`run.after_run_id`): the writer applying the predecessor's terminal transition resolves dependents (`engine_ref` null only) in the same unit of work — `done` → idempotent enqueue; `failed | cancelled` → `needs_you`, `park_kind = dependency`, `park_path` null, reason `run {x} ended {status}`; container-start sweep for crash residue; Continue = start anyway (`engine.enqueue`, not `engine.signal`), Cancel with recorded no-ops on missing referents; a dependency park never expires.
- Queue reasons: `branch held by {run}`, `global concurrency, held by {runs}`, `running`, `waiting for your answer`, `waiting for run {x}`, `saved — not started`; `list_queue` appends saved Runs.

## Out of scope

Any new Run or Step status token (everything is a reason text or `park_kind`); a dependency poller or third status writer; release-of-slot-on-park; the probe itself (epic 2); form tooltips (epic 2).

## Rules that bind every story

- Anchors read-only. **The cycle's known anchor revision:** the queue-reason renames (`repository lock held by {label}` → `branch held by {run}`; `held by {labels}` → `held by {runs}`) revise test-pinned verbatim strings in `use_cases/queue.py` tests — allowed **only** as the operator revision of 2026-09-15 (anchor exception 4): the same commit asserts the new strings and the revised test names the decision and its date. No other assertion may be weakened, and this exception is not available for anything else.
- Two-writer rule holds: dependent resolution lives inside `apply_step_result`/`signal_run`'s terminal transitions; `start` and `continue`-on-`dependency` call `engine.enqueue` (AD-8's stated exception).
- TDD with shared fakes; the engine fake extends for partition keys and idempotent enqueue; generated contract only for the payload/route changes; new settings (if any) land in `.env.example` + typed settings together (AD-20).

## Verification

`make lint` · `make test` · `make e2e-api` · `make e2e-ui` green after every story; the epic's e2e pass exercises: two Runs on different branches of one repository running concurrently after consent, a same-branch second Run queued `branch held by {run}`, a saved Run started by Signal, and a dependent enqueued on predecessor `done` / parked `dependency` on predecessor `cancelled`.
