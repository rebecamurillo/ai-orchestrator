---
title: Monitoring a Run
kind: procedure
audience: any
---
# Monitoring a Run

There is no push channel — poll, at the UI's own cadence: **5 s while the Run is
`queued`/`running`, 30 s otherwise**. Never tighter.

Where the instance has it, `GET /api/v1/runs/{id}/events?wait=30&since=<last updated_at>`
replaces that loop with one held connection that answers as soon as the Run moves (see
`api`); a 404 for a Run you know exists means an older instance, so fall back to
the cadence above.

- `GET /api/v1/runs/{id}` — status, spend, and `admitted_signals` (cheap; poll this).
- `GET /api/v1/runs/{id}/detail` — everything: steps with log tails, per-story states,
  cost (`spent_usd` vs `budget_usd`, tokens, trace link), the `alert` when parked, and
  the `gate_record` audit trail. Fetch when status changed or you need depth.
- `GET /api/v1/runs/{id}/steps/{step_path}` — one step's attempts, prompts, costs.
- `GET /api/v1/queue` — every Run the engine holds and why each waits.

Run statuses: `queued → running → done | failed | cancelled`, with `needs_you` whenever
the machine stops for a human. Step statuses: `planned queued running done blocked
checkpoint error skipped`.
