# Spec folder format — what epic and initiative Runs read

The orchestrator does not invent requirements: initiative and epic Runs walk files that
live in a **target repository**. This is their contract, extracted from the orchestrator's
own planner rules (`application/templates/lists.py`, `application/preflight/lists.py`)
and the `spec-gate` step that reviews a folder before any story runs. The BMAD skills that
`repo-init` installs into a target repository (`bmad-spec`,
`bmad-create-epics-and-stories`) generate these files in this shape — prefer generating
over hand-writing.

## Pick the flavor first

There are two ways to run an initiative, and **they read different `epics.yaml`
fields**. Decide which one you are authoring for before writing the file:

| Flavor | Launched via | Repos | Extra `epics.yaml` fields |
| --- | --- | --- | --- |
| **Hub run** (`initiative-hub@1`) — the current multi-repo path | `POST /runs` | one hub repo whose `repos/*` submodules are the members | `workdir`, `install`, `test`, `quality_gate` |
| Single-repo (`initiative@1`) | `POST /runs` | one repo | none |

A file written for one flavor does not run under another: a hub `epics.yaml` without
`workdir` plans, but every epic's setup/verify rows come out `skipped · no command`.

## Layout

```
<initiative_folder>/            # at the hub / target repository
  epics.yaml                    # read by the initiative flavor you chose
  <spec_folder>/                # one per epic — bare name, relative to this folder
    SPEC.md
    stories.yaml
    stories/                    # story files the dev loop writes as it works
      <id>-<slug>.md
```

An `epic` Run takes `spec_folder` directly; the `initiative-hub` template takes the
folder holding `epics.yaml` and joins each epic's `spec_folder` onto it
(`{initiative_folder}/{spec_folder}`) — so **`spec_folder` is a bare folder name relative
to the initiative folder, never a repeated full path**. In a hub run the whole tree above
lives at the hub; the members' code lives in the `repos/*` submodules and specs are never
committed into them.

`epics.yaml` may sit on the base branch while an epic's `stories.yaml` exists only on
that epic's own branch — the planner reads each frame at one consistent commit.

## `epics.yaml`

A YAML **list** (the file's top level is `- …`, not a mapping). List order **is**
execution order.

Core fields, required in **every** flavor:

| field | meaning |
| --- | --- |
| `id` | string; unique; **prefix-free** against every other id (see `stories.yaml`) |
| `title` | one line |
| `branch` | the branch the epic runs on (hub runs ignore it — every epic works on the Run's one `branch` input — but the list contract still requires it) |
| `spec_folder` | bare folder name (relative to the list file) holding `SPEC.md` + `stories.yaml` |

Optional in every flavor: `done_checkpoint: true` — park the Run for the operator after
the epic finishes.

### Hub-run fields (`initiative-hub@1`)

Each entry also carries the member submodule and its **full** commands. The command
strings are the entry's own data, `cd` included — the template never builds
`cd {workdir} && …` for you:

| field | meaning |
| --- | --- |
| `workdir` | repository-relative path of the epic's member submodule, e.g. `repos/api` — required |
| `install` | full setup command, e.g. `cd repos/api && yarn install` — optional |
| `test` | full per-story verify command, `cd` included — optional |
| `quality_gate` | full end-to-end command, `cd` included — optional |

An entry that omits `install`/`test`/`quality_gate` plans that row `skipped · no command`
— never a plan-time error, and never a green gate. The Run itself is launched with
template `initiative-hub@1`: repository = **the hub**, plus inputs `base_branch`,
`branch` (the initiative branch, shared by the hub and every submodule),
`initiative_folder`, `harness`, `model`.

```yaml
- id: "1"
  title: Statistics area
  branch: feat/initiative-stats        # required by the list contract; hub runs work on the Run's branch input
  spec_folder: epic-01-statistics
  workdir: repos/application
  install: "cd repos/application/client && yarn install && cd ../server/functions && yarn install --ignore-engines"
  test: "cd repos/application/client && yarn test --watchAll=false"
  quality_gate: "cd repos/application/client && yarn build && yarn test --watchAll=false"
  done_checkpoint: true
- id: "2"
  title: Notifications
  branch: feat/initiative-stats
  spec_folder: epic-02-notifications
  workdir: repos/functions
  install: "cd repos/functions && npm ci"
  test: "cd repos/functions && npm test"
```

### Single-repo (`initiative@1`)

Just the core fields; each epic runs and pushes on its own `branch`:

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
- `invoke_dev_with` — extra text appended verbatim to the build agent's dispatch prompt
  (a per-story instruction the description should not carry).

```yaml
- id: "1"
  title: Record the notification
  description: >
    Create NOTIFY.md at the repository root so SPEC.md's CAP-1 holds. State the
    mechanism, name the acceptance command.
- id: "2"
  title: Record the plan
  spec_checkpoint: true
  invoke_dev_with: "Prefer the existing PlanStore; do not add a new persistence layer."
  description: >
    Create PLAN.md at the repository root so CAP-2 holds.
```

**Ids are strings, unique, and prefix-free.** A story's file is found by the glob
`{id}-*.md`, so `4-1` and `4-1-a` would both match `4-1-a`'s file and the planner refuses
the list. `4-1` and `4-10` are fine (comparison is on the `-` separator). Quote ids in
YAML (`"1"`, not `1`). The same id rules apply to `epics.yaml`.

**Done detection:** a story whose file `stories/{id}-*.md` carries frontmatter
`status: done` is treated as already finished and skipped — that is how a re-run of an
epic resumes instead of redoing work.

## `SPEC.md`

Markdown with YAML frontmatter, holding the epic's capabilities. The `spec-gate` step (an
agent step at the start of every epic) reviews it together with `stories.yaml` and
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
