# Spec folder format — what `epic` and `initiative` Runs read

The orchestrator does not invent requirements: the `epic` and `initiative` templates walk
files that live in the **target repository**. This is their contract, extracted from the
orchestrator's own planner rules (`application/templates/lists.py`) and the `spec-gate`
step that reviews a folder before any story runs. The BMAD skills that `repo-init`
installs into a target repository (`bmad-spec`, `bmad-create-epics-and-stories`) generate
these files in this shape — prefer generating over hand-writing.

## Layout

```
<initiative_folder>/
  epics.yaml                # read by the `initiative` template
  <spec_folder>/            # one per epic — read by the `epic` template
    SPEC.md
    stories.yaml
    stories/                # story files the dev loop writes as it works
      <id>-<slug>.md
```

An `epic` Run takes `spec_folder` directly; an `initiative` Run takes the folder holding
`epics.yaml` and derives each epic's `spec_folder` from it. `epics.yaml` may sit on the
base branch while an epic's `stories.yaml` exists only on that epic's own branch — the
planner reads each frame at one consistent commit.

## `epics.yaml`

A YAML **list** (the file's top level is `- …`, not a mapping). Per entry, required:

| field | meaning |
| --- | --- |
| `id` | string; unique; **prefix-free** against every other id (see below) |
| `title` | one line |
| `branch` | the branch this epic runs and pushes on |
| `spec_folder` | folder (relative to the list file) holding `SPEC.md` + `stories.yaml` |

Optional: `done_checkpoint: true` — park the Run for the operator after the epic
finishes. List order **is** execution order; earlier entries are the dependency of later
ones.

```yaml
- id: "1"
  title: Observability — step-run detail and the reworked run view
  branch: feat/v2-observability
  spec_folder: epic-01-observability
  done_checkpoint: true
- id: "2"
  title: Fail at the form — live probe and enforced model choice
  branch: feat/v2-probe-form
  spec_folder: epic-02-probe-form
```

## `stories.yaml`

A YAML **list**. Per entry, required: `id`, `title`, `description`. The description is
the story's complete requirement — the dispatched agent works from it plus `SPEC.md` and
the project context, nothing else. Optional flags:

- `spec_checkpoint: true` — park after planning, before implementation, so the operator
  reviews the planned story file.
- `done_checkpoint: true` — park after the story is verified and committed.

```yaml
- id: "1"
  title: Record the notification
  description: >
    Create NOTIFY.md at the repository root so SPEC.md's CAP-1 holds. State the
    mechanism, name the acceptance command.
- id: "2"
  title: Record the plan
  spec_checkpoint: true
  description: >
    Create PLAN.md at the repository root so CAP-2 holds.
```

**Ids are strings, unique, and prefix-free.** A story's file is found by the glob
`{id}-*.md`, so `4-1` and `4-1-a` would both match `4-1-a`'s file and the planner refuses
the list. `4-1` and `4-10` are fine (comparison is on the `-` separator). Quote ids in
YAML (`"1"`, not `1`).

**Done detection:** a story whose file `stories/{id}-*.md` carries frontmatter
`status: done` is treated as already finished and skipped — that is how a re-run of an
epic resumes instead of redoing work.

## `SPEC.md`

Markdown with YAML frontmatter, holding the epic's capabilities. The `spec-gate` step (an
agent step at the start of every `epic` Run) reviews it together with `stories.yaml` and
**blocks the Run** on: literal placeholders (`TBD`, `TODO`, `FIXME`, `???`), unresolved
`open_questions:`/`assumptions:` entries, contradictions between SPEC and story scope, or
a story description that admits two incompatible implementations. It fixes pure
formatting defects (broken YAML, unclosed fences, missing required fields) in place.

Shape that passes the gate: frontmatter with an `id`, a title heading, and a
`## Capabilities` section of `CAP-n` entries, each with an observable **success**
criterion (ideally a command):

```markdown
---
id: SPEC-payments-retry
companions: []
---

# Payment retry

## Capabilities

- **CAP-1** Failed charges retry with exponential backoff, at most 3 times.
  **success:** `pnpm test retry` exits 0.
```

## What refusal looks like

- Planner-level (before the Run starts): a 422 on `POST /runs` (or a `plan_error` in
  preflight) naming the template, line, and the entry at fault — e.g. a missing required
  field, a duplicate id, a non-prefix-free id, a file that is not a list.
- Gate-level (after the Run starts): the Run parks `needs_you` with `park_kind:
  "blocked"` and the gate's questions in the alert; fix the files (optionally through
  `PUT /runs/{id}/files`) and send `continue`.

If preflight passes and spec-gate passes, the format was right.
