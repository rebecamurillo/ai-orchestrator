---
title: When a Run parks
kind: procedure
audience: any
---
# When a Run parks

`detail.alert` says why: `park_kind` is one of `blocked` (the agent asked a question —
`reason` carries its words), `checkpoint` (a declared human gate), `verify_failed`,
`budget`, `timeout`, `push_rejected`, `protected_path` (the diff touched a protected file;
`payload.hits` lists them), `misconfigured`, `plan_stale`, `internal`, `dependency`,
`merge_conflict` (a `git.merge` row conflicted; the merge is left in the worktree and the
stop admits Retry and Cancel only), `paused` (the Operator asked for a pause; it admits
Continue and Cancel, and only the Operator lifts it).

**Read `admitted_signals` off the Run and choose only from it — never hardcode which
signal a state accepts.** A non-admitted signal answers 409. Then
`POST /api/v1/runs/{id}/signals` with `{kind, payload}`, plus `stop` set to the `park_seq`
you read on `answer`, `retry` and `continue`, so a Run that has moved on refuses it with
409. On that 409, read the Run again and decide again. Omit `stop` only when no `park_seq`
is present:

- `answer` `{text}` — reply to a blocked agent or a spec checkpoint.
- `continue` — approve a checkpoint; for a `protected_path` park, `{files: [...]}`
  records which protected files the operator accepts.
- `retry` — re-run the errored step.
- `skip_story` / `skip_epic` — skip the parked frame (skipped is never green).
- `budget_raise` `{budget_usd}` — must exceed what is already spent.
- `cancel` — any non-terminal Run.
- `start` — launch a Run created with `save: true`.

To edit the spec on a parked Run before continuing: `GET /api/v1/runs/{id}/files` (tree /
`?path=` / `?path=&diff=1`), `PUT /api/v1/runs/{id}/files` `{path, content}` (commits to
the parked worktree as an operator edit), then `answer` or `continue`.

**Escalate to the human instead of deciding yourself** whenever a park involves judgment
about their code or money: protected-path accepts, budget raises beyond what they
authorized, checkpoint approval of a spec or a finished epic, or any `blocked` question
you cannot answer from the project's own context. Give them the `/workflows/{id}` link
and the alert's `reason`; the web UI is built for exactly that review.
