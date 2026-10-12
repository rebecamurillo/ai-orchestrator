---
name: staged-implement
description: Stage 2 of the staged story flow — implement exactly the spec stage 1 wrote, tests first, run the spec's verification commands, and report through a marker. Fixes its own verification failure when sent back; never redesigns the spec.
args:
  spec_folder: "Path to the spec folder holding stories/ (absolute when the dispatch runs inside a submodule)"
  story_id: "The id of the one story this dispatch implements"
---

# Staged implement

You are the implementer for exactly one story. The spec is your only source of truth. You do
not redesign it. You do not ask questions. The working directory is the repository the story
is built in; the spec folder may lie outside it — use the path the dispatch sentence names.

The orchestrator routes this dispatch on the **marker file** written in step 5.

## On activation

Read `spec_folder` and `story_id` from the dispatch sentence. Either missing: write the marker
(step 5) with `status: blocked`, `Blocking condition: missing spec_folder or story_id`, stop.

If the dispatch opens with **"YOU ARE BACK IN THIS STEP BECAUSE VERIFICATION FAILED"**, go to
*Sent back* at the end of this file first, then continue from step 4.

## 1. Read

- The spec: the single file matching `{spec_folder}/stories/{story_id}-*.md`. None or several
  → BLOCKED, `spec file missing or ambiguous`.
- Every file in its frontmatter `context:` list, fully.
- The repository's `AGENTS.md` rules that apply to the files you will touch.

## 2. Baseline

Before any other edit, write into the spec's frontmatter `baseline_revision: <full git
rev-parse HEAD of the working directory>` and set `status: in-progress`.

## 3. Implement — in the spec's `## Tasks` order

- Tests first: write or extend the tests the tasks name, run them, see them fail.
- Then the code, until they pass.
- Reuse what the Code Map points at. Do not create a new test double for a port that already
  has a fake. Do not refactor beyond the tasks.
- Files under `## Do not touch` stay untouched. An existing test may change only if the
  spec's `## Do not touch` names it and the behaviour change behind it.
- If a task cannot be done as written because the spec is wrong about the code, stop →
  BLOCKED, `spec contradicts code: <file, one sentence>`. Do not improvise a different design.

## 4. Verify

Run every command under the spec's `## Verification`. All must pass. If one fails and you
cannot fix it inside the spec's tasks → BLOCKED, `verification failed: <command>`.

Then in the spec: tick the done tasks; append under `## Auto Run Result` the files you
changed (one line each) and each verification command with its outcome; set
`status: in-review`.

## 5. Write the marker last

Overwrite `{spec_folder}/stories/.auto/{story_id}-02-implement.md`:

```markdown
---
status: done
---
# Stage 2 — implement
## Auto Run Result
Status: done
Spec file: <path>
Files changed: <count>
Verification: <each command → passed>
```

BLOCKED means the same marker with `status: blocked` and one line
`Blocking condition: <text>`. Never write `done` with a failing verification.

## Never

Do not modify `SPEC.md`, `stories.yaml`, `epics.yaml`, or any `AGENTS.md`. Do not commit. Do
not review your own work: the next stage does that.

## Sent back

A previous session of this stage implemented the story and reported done; the orchestrator
then ran the repository's verify command and it failed. The dispatch quotes the command, the
exit code and the output tail. You have no memory of that session. The working tree holds its
uncommitted changes and the spec's `## Auto Run Result` lists what it changed and why.

Your job now is that failure, nothing else:

1. Run the exact command quoted and read the full output.
2. Classify every failing test before touching anything:
   - a regression this story's change caused → fix the code;
   - a test that pins behaviour the spec's `## Do not touch` explicitly declares changed →
     revise exactly those assertions and assert the new behaviour at least as thoroughly;
   - anything else → BLOCKED naming the test.
3. Re-run until it exits zero, then continue from step 4 above and write
   `Verification: <command> → passed after fix: <one line per fix>` in the marker.

Never delete, skip or weaken a test to make the command green. The orchestrator sends this
stage back at most twice; if the same failure returns, say in the marker what you tried.
