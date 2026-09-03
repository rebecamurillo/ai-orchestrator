---
story: "6-7"
epic: 6
title: Terminal resume command, session flag, and poll
requirements: [FR-21, NFR-3, NFR-8, UX-DR5 (command block), UX-DR9, UX-DR18, AR-18]
binds: [AD-5, AD-10, AD-13, AD-14]
---

# Story 6.7 — Terminal resume command, session flag, and poll

As the Operator,
I want the exact command to pick up a story's session in a terminal, with the screen's actions held while I do, and the Run resuming by itself when I leave the story done and the tree clean,
So that the terminal is a real second path to unblock a story, visible to the record.

## Scope

**In:** `resume_command` in the Run read model, the command block with copy and `COPIED`, `terminal_start` and `terminal_release` signals and the session line, the `terminal_poll` job sending `terminal_resume`, tests.
**Out:** codex's command (Epic 7 adds the harness; the mechanism is generic).

## Binding rules (inlined)

- **Read model.** For a Run whose park row is an `agent` row on a harness with `capabilities.resume`: `terminal: {command, session_lifetime_ends_at | null, in_progress: bool}`; `command` = `docker compose exec -e ORCH_RUN_ID={…} -e ORCH_ATTEMPT_ID={…} -e ORCH_STORY_ID={…} -e ORCH_HARNESS={…} -e ORCH_PROJECT={…} -e ORCH_TAGS={…} -e ORCH_LANGFUSE_TAGS='{…}' -e TRACEPARENT={…} backend-api sh -c 'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY" ANTHROPIC_CUSTOM_HEADERS="…"; {harness.resume_command(cwd, session_id)}'` — identifiers inline, secrets referenced by name and resolved inside the container `[ASSUMPTION: no secret value ever appears on screen; the alias export list comes from the harness's HARNESS_ENV_ALIASES]`; `session_lifetime_ends_at` = attempt start + 30 days for `claude`, `null` for others; `local` → `terminal: null`.
- **Command block (UX-DR5, UX-DR9).** Section **OR CONTINUE IN THE SESSION**: the command in a `surface-inset` block, never soft-wrapped (horizontal scroll), Copy button; copy confirms `COPIED` in place for ~1.2 s and posts `terminal_start`; under it `session lifetime ends {date}` when known. Hidden when `terminal` is null.
- **Session flag (AD-13).** `terminal_start` valid when `needs_you` and not `terminal_session` → `terminal_session = true`, record; `terminal_release` valid when `terminal_session` → false, record. While `terminal_session`: the read model's `admitted_signals` drops `answer`, `continue`, `skip_story`, `skip_epic`, `retry` (keeps `cancel`, `terminal_release`); `PUT /runs/{id}/files` refuses (6.3); the line under the block reads `terminal session in progress · Answer, Continue, Skip and Retry disabled until Release — the run resumes by itself when the story file is done and the tree is clean` with a *Release* button (`wf-terminal-release`).
- **Poll (AD-13, AD-14).** Job `terminal_poll` every 30 s over Runs with `terminal_session and status == needs_you`: read `stories/{id}-*.md` status through `Workspace` and `Git.status(cwd)` plus `.git/index.lock` absence; `run.terminal_clean_polls` += 1 when the file is `done` and the tree is clean, else reset to 0; at 2 → `signal_run(terminal_resume)`: the agent row `blocked → done` (actor `terminal`), `terminal_session = false`, successor `→ queued`, Run → `running`, record `terminal_resume` (text `story file done and tree clean, resumed by terminal`); the walker runs verify. The attempt's `end_sha` is updated to HEAD for the protected-path check of the commit-guard `[ASSUMPTION]`.
- **Attribution.** Gateway calls made from the terminal carry the same identifiers (the `-e` list), so their spend lands on the attempt.

## Acceptance criteria

**Given** a Run parked `blocked` on a `claude` attempt
**When** the detail is read
**Then** `terminal.command` contains the eight identifier `-e` flags, no secret value, `sh -c` with the alias exports by name and `cd {worktree} && claude --resume {session}`, and `session_lifetime_ends_at` is start + 30 days.

**Given** the command block
**When** Copy is clicked
**Then** the clipboard holds the command, the button reads `COPIED` for about 1.2 s, and `terminal_start` is posted; the line and *Release* appear and the other buttons are disabled.

**Given** `terminal_session` true
**When** `answer` is posted
**Then** 409; `terminal_release` → 200 and the buttons return.

**Given** the poll job on the fakes with the story file `done` and a clean tree
**When** run twice
**Then** the first run sets `terminal_clean_polls = 1`, the second sends `terminal_resume`: the row is `done` with actor `terminal`, the Run is `running`, the successor queued; **and** a dirty tree between them resets the counter.

**Given** a `local` attempt
**When** the detail is read
**Then** `terminal` is null and the section is hidden.

## Implementation notes

- `application/use_cases/terminal.py` (`resume_command`, `poll`); job registered via `engine.schedule("terminal_poll", "*/30 * * * * *" or the adapter's 30 s form, job)`; migration for `terminal_clean_polls`.
- `src/components/run/CommandBlock.tsx` (React, clipboard API, no soft wrap).

## Verification

```bash
make lint && make test && make openapi && make e2e-ui
```

## Sources for detail only

PRD FR-21 (verbatim), NFR-3. Spine AD-13 (`terminal_*` rows, poll), AD-10 (`resume_command` prefixed with `env_for`), conventions "Terminal resume". `EXPERIENCE-v1.md` §2.2 (terminal session line). `DESIGN.md` command block.
