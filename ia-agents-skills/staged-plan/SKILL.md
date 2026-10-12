---
name: staged-plan
description: Stage 1 of the staged story flow — read one story's entry and its epic spec, investigate the code it touches, and write the story spec (intent contract, code map, tasks, verification, size). Writes a spec, never code.
args:
  spec_folder: "Path to the spec folder holding SPEC.md, stories.yaml and stories/ (absolute when the dispatch runs inside a submodule)"
  story_id: "The id of the one stories.yaml entry this dispatch plans"
---

# Staged plan

You are the planner for exactly one story. You write a spec. You do not write code. You do
not ask questions. The working directory is the repository the story will be built in; the
spec folder may lie outside it (a hub repository) — always use the spec folder path exactly
as the dispatch sentence names it.

This skill is stage 1 of the `staged-*` templates. The orchestrator routes this dispatch on
the **marker file** written in step 5, never on the spec file: the marker's frontmatter
`status` is `done`, `blocked` or `ready-for-dev`.

## On activation

Read `spec_folder` and `story_id` from the dispatch sentence (`spec folder <path>, story id
<id>.`). Either missing: write nothing else, write the marker (step 5) with `status: blocked`
and `Blocking condition: missing spec_folder or story_id`, and stop.

## 1. Resolve the story

- Read `{spec_folder}/stories.yaml`. Missing or unparseable → BLOCKED, `no stories.yaml
  found`. Take the entry whose `id` is `{story_id}`: its `title`, `description`, and `size` if
  the operator set one. No such entry → BLOCKED, `story id not found in stories.yaml`.
  Ignore every other entry and every checkpoint or `invoke_dev_with` field — text appended
  after the dispatch sentence is planning context, not a competing description.
- Read `{spec_folder}/SPEC.md` and the files its `companions:` frontmatter lists. No
  `SPEC.md` → BLOCKED, `no epic spec found`.
- Read every existing `{spec_folder}/stories/*.md`; carry forward only what bears on this
  story (Code Map entries, Design Notes, deferred items).
- Read the repository's `AGENTS.md` (root and the component you will touch) and any
  project-context file. Their rules bind the implementer; the spec must obey them.
- Look for `{spec_folder}/stories/{story_id}-*.md`. None: this is the first dispatch. Exactly
  one: resume it — keep its intent contract, refresh the rest. More than one → BLOCKED,
  `ambiguous story file match`.

## 2. Investigate, narrowly

Read the code the story touches: the files, the symbols, the tests that pin the current
behaviour, the existing test doubles the implementer must reuse. Stop when you can name every
file the implementer will create or edit. Do not survey the codebase.

## 3. Write the spec

Path: `{spec_folder}/stories/{story_id}-<kebab-slug-from-title>.md` (no `{story_id}` prefix
inside the slug). Use this shape and no other sections:

```markdown
---
status: ready-for-dev
size: S | M | L
story: {story_id}
date: <today, ISO>
context: [<every file the implementer must read first, repository-relative>]
---
# <title>

<intent-contract>
## Intent
<the story's title and description, verbatim, then at most five sentences of what "done"
observably means. Nothing here may be changed by a later stage.>
## Acceptance criteria
- AC1: Given … When … Then …   (observable at the outermost surface the story names)
- AC2: …
</intent-contract>

## Code Map
- `path/to/file.py:120` — what is there now, what changes, why
- `tests/unit/x/test_y.py` — reuse fake `Z` from tests/unit/fakes/; add cases …
(one line per file; every line names a file and an action)

## Tasks
1. <file> — <action>   (ordered by dependency; tests before the code they pin)
2. …

## Verification
- `<exact command>` — must pass
(the repository's own unit-test command at least; anything the story adds)

## Review focus
- <the two or three places a reviewer must look, and why>
- size: <S|M|L> because <one line>

## Do not touch
- <files the story must leave alone; existing tests unless the story declares a behaviour
   change — if it does, name the test and the assertion here>
```

**Size rule** — choose the first that matches. A later stage may raise it, never lower it:

- **L** if the change touches any of: a migration, an API contract or schema, a status
  machine, auth or secrets, concurrency or durability, more than 8 non-test files, or the
  story holds more than one independently shippable goal.
- **S** if it touches at most 3 non-test files, roughly 80 changed lines or fewer, adds no
  public surface (route, schema field, env var, status token, CLI flag), and every acceptance
  criterion is observable by an existing test command.
- **M** otherwise.

If `stories.yaml` carried a `size`, keep it unless the rule says L — L always wins.

## 4. Check, once

Every task names a file. Every AC is Given/When/Then. No "TBD", no open question. If two
readings of the intent lead to different code and nothing in `SPEC.md` or the story chooses
between them, do not choose → BLOCKED, `intent gap: <the question>`.

## 5. Write the marker last

Overwrite whatever is there at `{spec_folder}/stories/.auto/{story_id}-01-plan.md`
(create the `.auto/` directory if needed):

```markdown
---
status: done
---
# Stage 1 — plan
## Auto Run Result
Status: done
Spec file: <path>
Size: <S|M|L>
```

- **BLOCKED** means the same marker with `status: blocked` and one line
  `Blocking condition: <text>` under `## Auto Run Result`. Blocked is a correct outcome.
  Never write `done` for a spec you did not finish.
- If the dispatch told you to **halt after planning** (standard phrasing: `Halt after
  planning.`), write `status: ready-for-dev` in the marker instead of `done`. When you are
  resumed with the operator's answer, apply it to the spec, then rewrite the marker with
  `done`.

## Never

Do not modify `SPEC.md`, `stories.yaml`, `epics.yaml`, any `AGENTS.md`, or any test file. Do
not run the test suite. Do not commit.
