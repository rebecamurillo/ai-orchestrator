---
name: spec-gate
description: 'Judge whether an epic spec folder is ready to build from, and record the verdict. Use when the orchestrator dispatches the spec-gate step of an epic, or the user says "run the spec gate on [folder]".'
---

# Spec gate

The check that runs once per epic, before any story of it is dispatched. It answers one
question — **can a development agent build this epic from what is written here, without
asking anyone anything?** — and records the answer where the orchestrator reads it.

You are given a spec folder. It holds `SPEC.md`, `stories.yaml`, and `stories/` with one
file per story.

## What to do

1. Read `SPEC.md`, `stories.yaml`, and every file under `stories/`.
2. Check, and note what you find:
   - every id in `stories.yaml` has a file under `stories/`, and every file is indexed;
   - each story states what to change and how it is verified;
   - the stories do not contradict `SPEC.md` or each other;
   - no story asks for a step an agent cannot perform (a console setting, a signature, a
     release) — those belong to the operator, not to a story;
   - referenced paths and contracts exist, as far as you can see them.
3. **Change nothing.** Do not edit `SPEC.md`, `stories.yaml`, or any story file — they are
   operator-owned anchors, and the orchestrator parks the Run if you touch them. The one
   file you write is the result file below.

## What to write

Write `spec-gate-result.md` in the spec folder you were given, and nothing else:

```markdown
---
status: done
---

# Spec gate — <epic id>

<one paragraph: what you read and what you concluded>

## Findings

- <each observation, or "none">
```

`status` is exactly one of:

- **`done`** — a development agent can build every story from what is written. Findings may
  still be listed; they are notes, not blockers.
- **`blocked`** — at least one story cannot be built as written. Say which story, and what
  is missing, in the first finding. Use this sparingly: a wording preference is a note, a
  missing acceptance criterion is a blocker.

Nothing else belongs in `status`, and the file must open with the fenced frontmatter — the
orchestrator reads that line and nothing else to decide whether the epic proceeds.
