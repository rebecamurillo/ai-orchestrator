# Senior consult and team chat for blocked agents

## Decisions

- A stop first goes to a senior session on a stronger model. The Run stays `running`; no human is alerted.
- The senior only advises and writes one decision file. The original agent makes every edit and is the one resumed.
- A missing decision, a crash or an empty budget parks for a human.
- Consult triggers, in build order: `blocked`; `protected_path` on tests only; `verify_failed` after template retries.
- Anchor hits (`SPEC.md`, `stories.yaml`, `epics.yaml`, `AGENTS.md`) skip the senior. `budget`, `checkpoint`, `misconfigured`, `plan_stale`, `dependency` never consult.
- One consult per row per stop kind; the next stop on that row goes to a human.
- Test changes: agents usually ask before editing, so at a `blocked` stop the senior may approve named test files, recorded in `accepted_paths` with the senior as approver. A hit outside those files gets a diff review at the `protected_path` park. Not justified or unclear means a human reviews it.
- One channel per Project: `off`, `slack` or `mattermost`. `off` keeps today's Run page and API path.
- One port, two adapters, polling from the host. No inbound port; Tailscale stays private.
- The Mattermost team has an existing host, so nothing goes in `deploy/`.
- One thread per question. Each message carries initiative, epic, story, row, question, senior's view, earlier answers from that story, Run link, and a mention of the allowed people.
- A reply counts only if the thread is open, the author is allowed, the bot is mentioned, and the Run is still on that same stop. Then the `answer` signal goes out and the thread closes for good.
- Reminder in the thread every 4 hours while parked; this is a declared reminder, not a retry under hard rule 7.
- Operator senior session on the Run page: open it at any stop, scoped to story, epic or Run, with a chosen model. It reuses the consult context, each message resumes the session, and it may edit code and tests while the Run is parked. The Operator closes it by choosing an existing signal; status rules are unchanged. Anchor edits are listed for the Operator to confirm.
- During a senior session the Run's actions are locked, like terminal takeover, so a thread reply cannot resume the agent mid-fix.
- A `pause` signal parks a running Run when the current step ends; nothing is killed mid-work.
- Epic order: senior consult; operator senior session and `pause`; channel port and alerts; thread replies.

## Included from the Run feedback

- Provider errors named in the stop reason and alert, instead of `harness exit 1`.
- A test-impact search in `staged-plan`, across every test lane including `test.fixme` e2e specs.
- A `rejected` retro verdict parks the Run for a human.
- `test_globs` set on hub repositories. This is Operator configuration, not a build.

## Defaults set without a ruling; object if wrong

- Must-escalate: anchor text would have to change, the story's intent is ambiguous, an irreversible or destructive action, credentials or infrastructure outside the repository.
- Spec defects: the senior rules when a test contradicts the story's own acceptance criterion and the intent is unchanged, and records the deviation. A spec contradiction needing a product or design decision goes to a human.
- Ships in the staged template family, through a template-declared `consult` key with `senior_model` and a harness. The `auto` family is unchanged.
- The bot token is a separate encrypted Project field, never a Project env var, which would reach the agent.
- Per-Project metadata-only option; the default posts the question text.
- A failed post shows on the Run page with no automatic retry.

## Rejected

- Mattermost in `deploy/`: the team already has a host, and official images are amd64 only.
- Threads per agent, story or epic: a late reply could answer the wrong question.
- Senior editing files or anchors.
- Reading replies by webhook: it needs inbound exposure.

## Build traps

- `latest_attempt_for_run` and `previous_attempt` take the newest attempt. A senior attempt must never become the session that gets resumed.
- A Run has no ID for its current stop, and `signal_run` checks none. Add one so a stale answer cannot hit the next stop; web and API get it too.
- `Actor` needs a value for senior and chat, with platform and user ID in the record.
- `agent.py` and `agent_tail.py` are at their 400-line cap.
- Bump `DBOS_APPLICATION_VERSION` only if the walker's step sequence changes.

## Needs the Operator

- Amend hard rule 1 and AD-17 (agents cannot). Proposed: "A consult senior may approve named existing test files at a `blocked` stop, or accept a `protected_path` hit on existing tests after reading the diff, when the story being executed requires the behaviour change. Anchors are never delegated." The spine also needs AD-5, AD-8, AD-10 and AD-13 updates and removal of the deferred Notifications line.

## Evidence and unverified

- Instance data, 2026-11-01: 5 Runs; every `blocked` stop came from one `staged-initiative-hub` Run: 11 stops on 10 rows, 11 answers, 4 spec edits, 0 `verify_failed` stops. One Run is a small sample.
- That Run took 50h06, 38h57 of it parked: test-edit approvals 19h43, provider credit failure 13h08, real decisions 6h03, five answers delegated to Claude 3 min. Replay estimate: about 32h with the senior alone, about 14h with chat alerts answered in 30 minutes. Assumes 10-minute consults.
- 0 `protected_path` stops is not evidence: the Run's repository has empty `test_globs`, so 105 attempts froze no test file. AD-17's test check was off for that Run.
- The credit failure (`harness exit 1`, OpenRouter 402) needs its own fix: the senior cannot help, and the park reason hid the cause.
- Not tested: login through Tailscale Serve; reaching the Mattermost host from the backend container; Mattermost and Slack thread APIs behind one port.
