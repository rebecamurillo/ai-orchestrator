# Project and repository fields — what to confirm before the first save

A Project and its Repositories are the settings every Run reads. Most of them decide what an
unattended story is allowed to do and what stops it. Fill them with the user, field by field,
and read back what each choice means before `POST /api/v1/projects` or
`POST /api/v1/projects/{project_id}/repositories`. The same walk applies to a `PUT` that
changes one of them: a change reaches Runs planned after the save, never a Run in flight.

## Project

| field | what it does | confirm with the user |
| --- | --- | --- |
| `name` | the label on the Board and in every Run's identity line | spelled the way the team says it |
| `context_text` | prose handed to every dispatched agent as project context | nothing in it that is a secret; nothing that contradicts the repository's own `AGENTS.md` |
| `context_paths` | repository paths read into the agent's context on every attempt (one per line) | each exists on the default branch; small files, not whole folders — every attempt pays for them |
| `env_vars` | encrypted at rest, decrypted into the harness process only | these reach the agent's shell; no `GITHUB_TOKEN`, no orchestrator credential, nothing the agent should not be able to print |

## Repository

| field | what it does | confirm with the user |
| --- | --- | --- |
| `url` | what the orchestrator clones with its own instance-wide `GITHUB_TOKEN` | reachable by that token; the clone check proves it |
| `default_branch` | the branch Runs are cut from when no `base_branch` says otherwise; `git.push` refuses to push to it | the real integration branch, since agents' branches are compared against it |
| `install_command` | the `setup` row of every epic, run in the worktree before anything else | the exact string that works from the repository root; empty plans `skipped · no command` |
| `unit_test_command` | the `baseline` row before the first story **and** the `verify` row after each story | it must exit 0 on the base branch today, or the Run fails at `baseline` before any agent runs |
| `quality_gate_command` | the `e2e` row at the end of an epic, after test generation | same: green today, or the epic ends red |
| `test_globs` | the files frozen for the agent during a story (AD-17); a change to one parks the Run `protected_path` | see below — this field decides how often an unattended Run stops |
| `package_manager` | informational: shown on the Repository row | matches the repository |

In a hub repository the three commands are read from `epics.yaml` per epic instead (see
`./spec-folder.md`), and `test_globs` is matched inside each member submodule.

## `test_globs`: the decision that shapes auto mode

The field is exactly what is listed, one glob per line, matched against repository-relative
paths. Nothing is added behind it (Operator decision 2026-10-06: the three former defaults
`tests/**`, `**/*.test.*`, `**/*.spec.*` are now placeholder text in the form and nothing
more).

- **Empty.** No file is frozen. The agent may edit or delete existing tests as part of a
  story, and the only guard on that is the verify commands and the human reading the branch.
  Fewer stops; a test quietly weakened to go green is not caught by the machine.
- **The three former defaults.** Every pre-existing test is frozen. A bug-fix or refactor
  story that legitimately changes a test parks the Run on every such story, and the human
  must `continue` with the hit files each time. Many stops; nothing slips.
- **A narrow list** (`tests/billing/**`, `migrations/**`, one critical file). Only those paths
  stop the Run. This is the usual right answer: name what must survive an agent untouched,
  leave the rest to verify and review.

Whatever is chosen, `SPEC.md`, `stories.yaml`, `epics.yaml` and every `AGENTS.md` stay
frozen for every Run; they are not configurable.

Say this back to the user in one sentence before saving, for example: "With these globs an
unattended Run stops whenever a story changes a file under `tests/billing/`; it does not stop
for any other test change."

## What an unattended story Run does with these settings

State this before the first real Run, so nobody is surprised by what happens while they are
not watching:

1. The orchestrator clones with its token, cuts the Run's branch from `base_branch`, runs
   `install_command`, then `unit_test_command` as the baseline. A red baseline fails the Run
   there, before any agent spends anything.
2. For each story, an agent is dispatched into the worktree with the project context and the
   `env_vars`. It commits its own work. It never pushes and never holds a git credential.
3. After each attempt the orchestrator diffs exactly what the agent changed against the
   frozen set from `test_globs` plus the four anchors, then runs `unit_test_command` again.
4. The Run **stops for a human** (`needs_you`) on: a frozen file touched (`protected_path`),
   verify red after the template's bounded retries (`verify_failed`), the agent asking a
   question or being denied a tool (`blocked`), the budget reached (`budget`), a stall or a
   wall-clock timeout, or a checkpoint the story or epic declared. Nothing proceeds past a
   stop on its own, and nothing is retried silently.
5. At the end of the epic the orchestrator generates end-to-end tests, runs
   `quality_gate_command`, writes a retrospective into the spec folder, pushes the branch and
   records a compare link. No pull request is opened; a human does that from the link.
6. Spend is tracked per attempt against `budget_usd`; the budget is a human's decision at
   Run creation and is never raised by the machine.

If the user wants fewer unattended stops, the levers are, in order: a narrower `test_globs`,
verify commands that are green today, stories whose descriptions leave one implementation,
and a template edit for the rest (`./workflows.md`). If they want more control, add
`spec_checkpoint` or `done_checkpoint` to the stories that deserve a look.
