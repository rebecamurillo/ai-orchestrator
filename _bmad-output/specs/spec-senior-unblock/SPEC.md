---
id: SPEC-senior-unblock
companions:
  - flows.md
  - brownfield.md
  - run-evidence.md
  - ../../architecture/ARCHITECTURE-SPINE.md
sources:
  - ../../forge/senior-agent-unblock/forged-idea.md
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# Senior unblock: consult, operator session, pause and team chat

## Why

A pain to solve. Stopped Runs wait on a person who is often away, and most of those waits need no real decision: the one real initiative Run spent 38h57 of 50h06 parked, and 19h43 of that was approving test edits the story already implied. When a Run does need help, the Operator cannot prompt a capable agent inside it, and cannot stop a Run that has not stopped itself. Two teams, one on Slack and one on Mattermost, need the alerts and answers where they already work. Evidence: `run-evidence.md`.

## Capabilities

### Epic 1: Senior consult

- **CAP-1**
  - **intent:** At a `blocked` stop on a row that declares a consult, a senior session on a stronger model reads the story context and the blocking condition, then either answers or sends the stop to a human.
  - **success:** The Run stays `running` with no alert during the consult. An answer resumes the original agent's session as a new attempt. A decision to escalate, a missing or unreadable decision, a crash, or no remaining budget parks `blocked` with the senior's reasoning when it gave any.
- **CAP-2**
  - **intent:** The senior decides whether the story requires a change to existing tests, by approving named files at a `blocked` stop or reviewing the diff at a `protected_path` stop on tests only.
  - **success:** Approved files enter `accepted_paths` with the senior recorded as approver and do not stop the Run again. A hit outside the approved files gets a diff review. An unjustified or unclear change, or any anchor hit, parks for a human. Preflight warns, without refusing, when the Run's repository has empty `test_globs`.
- **CAP-3**
  - **intent:** At `verify_failed`, once the template's retries are used up, the senior gives the original agent a diagnosis.
  - **success:** The diagnosis reaches the agent through one further fresh redispatch of the failing work, and the next stop parks for a human. No row resumes another row's session (AD-10).
- **CAP-4**
  - **intent:** An answer can state which stop it answers, and the Run page, kit skills and chat always do, so a late one cannot reach a later stop.
  - **success:** A stale answer naming an earlier stop, from the Run page, API or chat, is refused and changes nothing, and the refusal names the current stop. An API call naming no stop behaves as today (AD-24).
- **CAP-5**
  - **intent:** A provider failure reaches the Operator under its real cause.
  - **success:** A fixture attempt whose log holds a provider credit error parks with a reason naming that error, not `harness exit 1`, and never consults.
- **CAP-6**
  - **intent:** Staged planning searches every test lane for tests the story changes, including `test.fixme` e2e specs, and writes them into the story's declared test changes.
  - **success:** Given a fixture story that changes a label pinned by a `test.fixme` spec, the plan names that file.

### Epic 2: Operator control

- **CAP-7**
  - **intent:** At any stop, the Operator can open a senior session on the Run page, scoped to the story, epic or Run, on a chosen model, and have it investigate and fix things in conversation.
  - **success:** The session starts with the scope's context loaded, keeps its context across messages, commits its edits under its own label, and bills the Run. The Operator closes it by choosing an existing signal, and close is refused until each anchor edit is confirmed or reverted.
- **CAP-8**
  - **intent:** The Operator can pause a running Run.
  - **success:** The Run parks when the current step ends, with nothing killed, and offers the senior session, continue and cancel.
- **CAP-9**
  - **intent:** A `rejected` retrospective verdict stops the Run for a human.
  - **success:** A fixture retro with verdict `rejected` parks before the next epic and names its findings. Other verdicts do not park.

### Epic 3: Channel and alerts

- **CAP-10**
  - **intent:** Each Project chooses a chat channel, `off`, `slack` or `mattermost`, with its bot token, channel, allowed people and a metadata-only option.
  - **success:** A connection test reports success or the platform's failure. `off` leaves the Run page and API behaviour unchanged, and the token is never returned and never reaches a harness environment.
- **CAP-11**
  - **intent:** A stop that needs a human posts one new thread per question in the Project's channel, with enough context to decide, and mentions the allowed people.
  - **success:** The message names initiative, epic, story, row, question, senior's view, earlier answers from that story and the Run link. A reminder posts in the thread every 4 hours while parked. A failed post shows on the Run page, is not retried automatically, and does not change the Run. Senior-approved test edits post one line with no mention.

### Epic 4: Thread replies

- **CAP-12**
  - **intent:** An allowed person can answer in the thread, and the original agent resumes with that answer.
  - **success:** A reply counts only if the thread is open, the author is allowed, the bot is mentioned, and the Run is still on that stop. The first valid reply sends `answer`, closes the thread for good and records the platform and author. Later replies and thread discussion never reach an agent. Parallel Runs in one channel never receive each other's answers. Stops whose answer is not text link to the Run page.

## Constraints

- Hard rule 1 and AD-17 are amended by the Operator before CAP-2 ships; agents cannot edit `AGENTS.md`. Proposed wording is in `brownfield.md`.
- Anchors are never delegated to a senior: `SPEC.md`, `stories.yaml`, `epics.yaml`, `AGENTS.md`.
- The automatic senior changes nothing but its decision file. A write beyond it fails the consult and parks, naming the files.
- The senior's session is never resumed by the original row (AD-10); the original agent's session is.
- Never consult on `budget`, `checkpoint`, `misconfigured`, `plan_stale`, `dependency`. One consult per row per stop kind.
- Must-escalate: anchor text would have to change, the story's intent is ambiguous, an irreversible or destructive action, credentials or infrastructure outside the repository, or a product or design decision.
- No new status tokens. Execution transitions go through `apply_step_result` and operator transitions through `signal_run` (AD-8), including chat replies and session close.
- The orchestrator reads a senior's decision from a file through a routing rule, never from model output (AD-10).
- A session may write only while the Run is parked, and the Run's actions are locked during it.
- No inbound network exposure: replies are read by polling from the host. Every service stays on loopback.
- Bot tokens are Fernet-encrypted Project fields, separate from Project env vars. `ORCHESTRATOR_TOKEN` stays the only login (AD-4, AD-5).
- No automatic retry beyond what a template declares (hard rule 7). The reminder is a declared notice, not a retry.
- Consult and session spend bills to the Run and obeys its budget.
- Tests bring fixture templates; none pins shipped template content (hard rule 6). Each new port gets one shared fake.
- Only the `staged` template family declares a consult. The `auto` family is unchanged.

## Non-goals

- Hosting Mattermost or adding anything to `deploy/`: the team already has a server.
- Telegram, email, GitHub comments, push services or PWA push.
- Conversation with a senior inside a chat thread; the session lives on the Run page.
- Consults on `merge_conflict`, `push_rejected` or `timeout`.
- Automatic retry of provider failures.
- Per-person web logins, roles, or parallel epics inside a Run.
- Fixing the application defects the past Run found, or other findings in its parks report.

## Success signal

Replaying a fixture initiative: a test that contradicts the story's own criterion finishes with no human action; a product decision reaches a Slack or Mattermost thread, an allowed reply resumes the original session, and a second reply changes nothing. On the next comparable initiative, no test-approval stop waits on a person, which removes the class that cost 19h43 in the baseline Run.

## Assumptions

- A consult takes about 10 minutes and costs $2–4; the replay estimates in `run-evidence.md` rest on this.
- The Mattermost host is reachable from the backend container.
- Slack and Mattermost thread APIs fit one port and support polling.
- The Slack app is an internal customer-built app, which keeps the higher `conversations.replies` limits.
- Login through Tailscale Serve works; the Run link depends on it.
- The Operator's instruction to continue accepted the four Run-feedback additions.
- The Operator sets `test_globs` on hub repositories; without it, CAP-2's `protected_path` review never fires.
