# Autonomy: who answers a park

`autonomy` in `INITIATIVE.md` is a declared policy, chosen once by the human for the whole
initiative. `assisted` is the default for a client initiative. It never widens mid-Run: if a
park needs more latitude than the level allows, that is the human's decision to make, not
yours.

| park kind | supervised | assisted | auto |
| --- | --- | --- | --- |
| `blocked`, answerable from the spec | ask | answer | answer |
| `blocked`, needs judgement | ask | ask | ask |
| `verify_failed` | ask | diagnose, retry once, then ask | same |
| `protected_path` | ask | ask | accept when within story scope |
| `checkpoint`, `budget`, `merge_conflict`, `push_rejected` | ask | ask | ask |

Any park kind not in the table — `timeout`, `misconfigured`, `plan_stale`, `internal`,
`dependency` — goes to the human at every level: each one says the instance or the spec is
wrong, which no signal fixes.

## What the rows mean

**`blocked`, answerable from the spec.** The agent asked a question whose answer is written
down — in `SPEC.md`, `stories.yaml`, the PRD, the architecture, or the repository's own
`AGENTS.md`. Answer with `answer` `{text}`, quoting the source, and say in your report which
file the answer came from. If you find yourself reasoning towards an answer instead of
reading one, the question needs judgement.

**`blocked`, needs judgement.** A trade-off, a missing requirement, a question about intent,
or anything touching money, credentials or a third party. Ask, at every level, always.

**`verify_failed`.** Diagnose first: `GET /api/v1/runs/{id}/detail` for the step's log tail,
then `GET /api/v1/runs/{id}/steps/{step_path}` for the attempt that failed. **One** `retry`,
and only with the diagnosis in the signal payload so the next attempt is not the same
attempt. Hard rule 7 — no silent retry: a second failure goes to the human with both logs.
A `retry` sent without a diagnosis is a silent retry wearing a payload.

**`protected_path`.** The diff touched a protected file; `alert.payload.hits` lists them.
Under `auto` you may `continue` `{files: [...]}` only when every hit is inside the scope the
story itself declares — a test file the story says it changes, a fixture it says it adds. A
hit outside that scope, an `AGENTS.md`, a `SPEC.md`, `stories.yaml` or `epics.yaml` goes to
the human whatever the level says: those are anchors, and only their owner edits them.

**`checkpoint`.** A declared human gate. The point of the gate is the human; approving it
yourself deletes the feature.

**`budget`.** A `budget_raise` is a spending decision. One budget decision per Run was made
in step 2; a second one is the human's.

**`merge_conflict`, `push_rejected`.** The worktree or the remote moved under the Run. Both
need someone who can see the other side of the merge.

## Sending the signal

Read `admitted_signals` off `GET /api/v1/runs/{id}` (the watcher's payload file carries the
list it saw) and choose only from it. A non-admitted kind answers 409 — that is the API
telling you the state is not what you think, so re-read the Run rather than trying another
kind. Signal shapes are in `../../orchestrator/references/api.md`.

Every signal you send on the human's behalf is reported to them afterwards: the park kind,
the reason, what you sent and why. An autonomy level is permission to act, not permission to
act unobserved.
