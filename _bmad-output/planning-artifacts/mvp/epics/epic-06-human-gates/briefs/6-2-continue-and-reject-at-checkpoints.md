---
story: "6-2"
epic: 6
title: Continue and Reject at checkpoints
requirements: [FR-19, NFR-8, UX-DR10 (checkpoint bodies), UX-DR18]
binds: [AD-9, AD-13]
---

# Story 6.2 — Continue and Reject at checkpoints

As the Operator,
I want to read the planned story spec inline at a spec checkpoint and either let the agent implement it or send it back with a reason, and to acknowledge a done checkpoint with one click,
So that the pauses I declared in `stories.yaml` are cheap to clear.

## Scope

**In:** the `continue` effect on an agent row parked `checkpoint` (re-dispatch without the halt suffix), Reject as the `answer` signal at a spec checkpoint, the spec-checkpoint body (planned story file inline) and the done-checkpoint body in `RunDetail`, tests.
**Out:** file editing (6.3; the inline view here is read-only).

## Binding rules (inlined)

- **Continue on an agent row (AD-13).** `signal_run` moves `checkpoint → queued`; the executor's next attempt sees `resume_signal.kind == continue` and dispatches with `compose_prompt` **without** ` Halt after planning.` and without archiving anything: the story file stays at `ready-for-dev`, so build-auto implements without re-planning. New session, same harness.
- **Reject with a reason.** The same `answer` signal as 6.1 while `park_kind == checkpoint` on an agent row: the planned file is archived to `stories/.answers/{id}-attempt-{n}.md` with `## Human Answer`, the condition in the suffix is `spec rejected`, and the story is re-planned with the reason (and, because `spec_checkpoint` is still true, the re-plan halts again at the checkpoint).
- **Done checkpoint.** `continue` on a `checkpoint` row (4.9 already implements the writer); this story adds the body.
- **Spec-checkpoint body (UX-DR10).** Banner `CHK · spec checkpoint`; body: the planned story file rendered inline (`GET /runs/{id}/files?path={spec_folder}/stories/{id}-*.md` — resolve the glob server-side; this story adds a read-only `GET /runs/{id}/files?path=` returning `{path, content, size, mtime}` for a path inside the spec folder, no writes yet), the eyebrow `planned by {harness} · {model} · {time}`; primary *Continue* (`wf-signal-continue`); *Reject with a reason* reveals a textarea (`wf-reject`) with the hint `planned story archived to stories/.answers/{id}-attempt-{n}.md with your reason; story {id} re-planned` and the button *Reject and re-plan*; also *Skip story*, *Skip epic*, *Cancel run*.
- **Done-checkpoint body.** Banner `CHK · done checkpoint`; body: `story {id} · {title} · {attempts} attempts · ${cost} · verify {done | skipped}` and the compare link if the epic is already pushed; primary *Continue*; also *Skip story* (marks the checkpoint row skipped and continues), *Skip epic*, *Cancel run*.
- **Voice:** no "approve"; the button says *Continue*.

## Acceptance criteria

**Given** a Run parked at a spec checkpoint on story `4-2` after attempt 1
**When** `continue` is signalled and the executor resumes on the fakes
**Then** no archive happens, the prompt has no `Halt after planning.` suffix, attempt 2 dispatches with a new session, and the gate record has `continue`.

**Given** the same Run
**When** `answer {text: "split the endpoint in two"}` is signalled
**Then** the file is archived with the reason, the prompt suffix reads `Answer from the operator to the blocking condition "spec rejected": split the endpoint in two` followed by ` Halt after planning.`, and the record has `answer`.

**Given** the spec-checkpoint detail
**When** rendered with a stubbed file
**Then** the story file content is shown inline with the eyebrow, *Continue* is primary, *Reject with a reason* reveals the textarea and hint, and the buttons match `admitted_signals`.

**Given** a done-checkpoint detail
**When** rendered
**Then** the summary line and *Continue* are shown; clicking posts `continue` and the Run resumes at the next story (e2e on the gates fixture, story `3`).

**Given** `GET /runs/{id}/files?path=../x`
**When** called
**Then** 422; a path outside the spec folder → 403.

## Implementation notes

- Executor: `compose_prompt` branch for `continue` (no halt suffix); reuse `_archive_with_answer` from 6.1.
- Backend: `GET /runs/{id}/files` (read) in `api/routers/runs.py` through `Workspace.read`; glob resolution helper.
- `StopBody` cases `checkpoint` (agent row vs checkpoint row decided by `alert.row_kind` — add to the read model).

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-19, §4.6 (`checkpoint` row). Spine AD-13 (`continue`, `answer` at checkpoint). `addendum.md` §D Spec checkpoint. `EXPERIENCE-v1.md` §2.2 stop table.
