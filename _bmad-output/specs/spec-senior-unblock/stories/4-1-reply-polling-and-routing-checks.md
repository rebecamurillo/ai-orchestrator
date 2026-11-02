---
title: 'Reply routing checks'
type: 'feature'
created: '2026-11-02'
status: 'ready-for-dev'
route: 'dispatch'
baseline_commit: '08d281ef1334e590787518bfd9ae560b4cfddb67'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A thread reply becomes an instruction to a full-access agent. Only an allowed person's reply to the Run's current `blocked` stop may reach it, and only once (CAP-12, AD-24, AD-25).

**Approach:** `apply_reply_batch` takes one thread's new replies, read by 4-3 outside any transaction, and checks them in order under the Run and thread row locks. The first reply that passes sends `answer` (actor `chat`, `stop = thread.park_seq`) and closes the thread in the same unit of work. Nothing calls it until 4-3.

## Boundaries & Constraints

**Always:**
- One unit of work holds `runs.get_for_update(thread.run_id)`, then `threads.get_for_update(thread_id)`. Every writer that locks both takes the Run first.
- **Gate**, checked once per batch. The thread must be `open`, its `cursor` must equal the batch's `read_cursor`, and the Project's channel, read now, must have the thread's `provider` and `channel_id`. Otherwise nothing is written, and the outcome is `superseded` or `channel_changed`.
- **Checks per reply**, in order. The first failure is the outcome:
  1. `not_allowed`: `author_id` is not in `allowed_users`.
  2. `no_mention`: `mentions_bot` is false.
  3. `stale`: the Run is not `needs_you` at `park_seq == thread.park_seq`.
  4. `locked`: `senior_session` or `terminal_session` is set.
  5. `not_answerable`: `thread.park_kind` or `run.park_kind` is not `blocked`, or `validate` refuses the `answer`.
  6. `bad_text`: the normalised `body` is empty, longer than `MAX_ANSWER_CHARS` (8,000), or not UTF-8 encodable.
- **Normalising `Reply.body`** (3-1): CRLF and lone CR become LF, then NFC. Every `Cc` character but `\n` and `\t` is dropped, as are the bidi controls U+202A–U+202E and U+2066–U+2069. The ends are trimmed, and nothing else changes. An oversized body is refused, never truncated.
- **Pass:** `apply_signal` writes `answer` with actor `chat` and payload exactly `{text, platform: thread.provider, author_id, author}`. `author` is the handle from `allowed_users`. Only `text` comes from the reply, and `_check_mode` defaults `mode`. The thread is `closed` at the winner's `cursor`. After the commit, the engine is told as `signal_run` tells it.
- **Fail:** the pending cursor moves to that reply's `cursor`, and checking goes on. A batch with no winner commits the last reply's cursor.
- **Refused apply:** a `DomainError` from `apply_signal` rolls back. A second unit of work, under the same locks and gate, moves the cursor past that reply and ends the batch (`refused`).
- **Result:** returns `[(reply_id, outcome)]`, with `answered` for the winner. It logs nothing.

**Never:**
- No reading, job, setting or log line (4-3).
- No posting, and no close at the end of a stop (4-2). No thread creation (3-3).
- No platform syntax in `application/` (AD-25), and no status write outside `apply_signal` (AD-8).
- Nothing moves a `closed` thread back to `open`.
- No container is stopped.

**Decided (lead review, 2026-11-02):**
- **Replies only at `blocked` stops.** At a checkpoint, `answer` means *Reject with a reason*, so "@bot looks good" would reject the spec. Refusing there fails closed, and CAP-12 sends stops whose answer is not text to the Run page. AD-25 is amended.
- **The adapter strips the mention.** `Reply.body` is `text` with every bot mention removed by the match that sets `mentions_bot`. That keeps one matcher and adds no port method. 3-1's spec is amended.
- **3-3 lands the contract below.** If any part is missing, 4-1 reports `blocked`. One story owns each table.
- Replies after the winner stay past the cursor, for 4-2.
- `test_run_statuses.py::ACTORS` gains `chat`, appended, under rule 1(b). AD-8's 2026-11-01 amendment declares it, and the revision cites 4-1 and the date. No other existing test changes.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected |
|---|---|---|
| Valid | allowed, `@bot fix X`, Run `blocked` at the thread's stop | one `answer "fix X"`, actor `chat`; thread closed; one `engine.signal`, after the commit |
| Two valid in one batch | r1 and r2 pass | r1 applies; r2 stays past the cursor |
| Two pollers | the same batch twice | the second is `superseded` and writes nothing |
| Run page first | its answer commits between the read and the check | `stale`; cursor advances; no second message |
| Later stop | Run parked again (`park_seq + 1`) | `stale` |
| Not a reply stop | `checkpoint`; or a thread posted at `budget` whose Run is `blocked` after a raise | `not_answerable` |
| Outsider, no mention | author not listed; allowed author without `@bot` | `not_allowed`, `no_mention`; cursor advances |
| Locked | either flag, including one set after the read | `locked` |
| Bad text | `@bot` alone, blank, 8,001 characters, lone surrogate | `bad_text` |
| Hostile text | `<script>`, `{{answer}}`, `"mode": "restart"`, U+202E, NUL | normalised text stored; payload keys and `mode` unchanged |
| Channel switched | the Project is now on another provider or channel | nothing written |
| Apply refuses | `apply_signal` raises `Conflict` | rolled back; the cursor moves past it in a second unit of work |
| Crash before commit | — | nothing written; a re-read decides the same way |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/`.

- `application/use_cases/signal_run.py` (366 lines):
  - Extract `apply_signal(ports, run, signal, *, actor=None) -> Applied{run, rule, effect}`. It covers the stale stop, `validate`, `_check_mode`, `record` (where `actor` overrides `rule.actor`), the effect, `_apply` and `park_dependents`, with no unit of work and no engine call.
  - `finish_signal(ports, run_id, signal, applied)` is the after-commit half.
  - `signal_run` becomes: lock, `apply_signal`, commit, `finish_signal`, with unchanged behaviour.
- `domain/statuses.py` -- `Actor` gains `chat`. The column is `Text`, so no migration.
- `application/rules/chat_reply.py` (new, pure) -- `normalise`, `MAX_ANSWER_CHARS`, `Outcome`, and `check(channel, thread, reply, run, park_row, rows)`.
- `application/use_cases/chat_reply.py` (new) -- `ReplyPorts{signal: SignalPorts, threads, channels}` and `apply_reply_batch`.
- Reuse: `validate`, `refuse_stale_stop`, 2-3's `get_for_update`, and the fakes for threads (3-3), channels (3-4) and the engine.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- through `make openapi` only.

## Contract 3-3 provides (3-3's implementer: read this)

4-1 and 4-3 use these exact names.

- **Entity.** `domain/entities/chat_thread.py`:
  - `ChatThreadState = Literal["posting", "open", "closed", "failed"]`.
  - `ChatThread{id, run_id, park_seq, park_kind: ParkKind, provider: ChatProvider, channel_id, ref, cursor, state, error, last_reminded_at, created_at, updated_at}`.
  - `park_kind`, `provider` and `channel_id` are the values at posting.
- **Table** `chat_thread`:
  - `id` is a UUIDv7 primary key. `run_id` is a foreign key to `run`, `ON DELETE CASCADE`.
  - Unique on `(run_id, park_seq)` and on `ref`, with CHECKs on `state` and `provider`.
  - Only `ref` (null while `posting`), `cursor`, `error` and `last_reminded_at` are nullable.
- **Repository.** `ChatThreadRepository` in `domain/ports/repositories.py` has at least `add`, `get`, `get_for_update` (`SELECT … FOR UPDATE`), `list_open_for_project(project_id)` (oldest first) and `update`. The shared fake is `tests/unit/fakes/chat_thread.py::FakeChatThreadRepository`, and its `get_for_update` returns `get`.
- **Writes.** Every thread write reads the row through `get_for_update` in its unit of work, taking the Run lock first when both are locked. Only 4-1 writes `cursor`, and only forward. Nothing returns a `closed` or `failed` thread to `open`.
- **One session.** `open_chat_ports(session_factory, notifier) -> ChatPorts{writers, threads, channels}` builds all three on one session, so an answer and its close commit together.
- **The job.** `application/jobs/chat_poll.py::run_chat_poll(ports: ChatPollPorts)`:
  - For each Project with a channel, it decrypts the token, opens the channel once per fire through `ChatChannelFactory`, and runs the passes: post and remind (3-3), then read (4-3).
  - An exception in one Project is logged by class name only, and never reaches another Project or the scheduler.
  - Fires can overlap, so every pass must be safe when two run at once.
- **Registration and setting.** `infrastructure/terminal_jobs.py::engine_jobs` registers the job as `chat_poll`, cron `*/{CHAT_POLL_SECONDS} * * * * *`. `CHAT_POLL_SECONDS` goes in `Settings` and `.env.example`, defaults to 30, and must be 10, 12, 15, 20 or 30, or start-up refuses.
- **Copy and display.** A post invites a reply only when `park_kind` is `blocked`. Every other stop links to the Run page. The Run page shows the stop's thread `error` whatever its `state`.

## Tasks & Acceptance

**Execution:**
- [ ] `backend-api/tests/unit/application/test_chat_reply_rules.py`, `test_chat_reply_apply.py`, `test_signal_apply.py` -- new. They cover every matrix row through the shared fakes, including `mode: session` when the latest attempt can resume. Each is seen failing first.
- [ ] `backend-api/tests/e2e/test_concurrent_answers.py` -- new. Two concurrent Run page `answer`s naming one stop give one 200, one 409 and one `answer` record. This settles 1-1's deferred race.
- [ ] `backend-api/tests/unit/test_run_statuses.py` -- the `ACTORS` revision.
- [ ] Code Map in order, then `make openapi`.

**Acceptance Criteria:**
- Given a Run `blocked` at stop 3 with an open thread holding two allowed replies, when a Run page answer commits between the read and the check, then the gate record holds exactly one `answer`, and the engine one message.
- Given a passing reply, when the batch commits, then the record, the close and the cursor land in one commit, and `engine.signal` is called only after it.
- Given the existing `signal_run` tests, when they run after the extraction, then every one passes unchanged.

## Design Notes

- **The row lock closes the race.** `park_seq` does not change after an answer, so a stale reply naming that stop passes AD-24 and has to fail on status. Whichever answer commits first moves the Run to `running`, and the rest then fail `stale` under the lock.
- **The terminal flag is re-read under the lock.** `handle_signal::_refuse_early` reads `terminal_session` outside the unit of work, so check 4 reads it again. The Run page path keeps that gap. It is reported, and 4-1 does not fix it.
- **Resume, not restart.** `terminal_jobs` builds `SignalPorts(writers, engine)` without the two callables, so `_check_mode` would choose `restart`. `ReplyPorts.signal` must carry both callables, and 4-3 wires them.

## Spec Change Log

- 2026-11-02, lead review. The reading pass, job wiring, errors and logging were split to 4-3.
- Defects fixed:
  - A `budget`-stop thread could answer after a raise. `thread.park_kind` is now required.
  - The channel match is re-checked under the lock.
  - `locked` now runs before `validate`.
  - NUL is dropped rather than refused, and C1 and bidi controls are dropped too.
  - The payload takes only `text` from the reply.
  - A refused apply ends the batch.
- Proposed AD-25 text: "`Reply` gains `body`. `replies_since` excludes system, webhook, bot and plugin posts. `chat_thread` gains `park_kind`, `provider` and `channel_id` at posting, and a thread off the Project's current channel is not read. Only a `blocked` stop takes thread replies; a `checkpoint` stop, where `answer` means *Reject with a reason*, links to the Run page. A reply's checks and its `answer` share one unit of work that locks the Run, then the thread."
- KEEP: the lock order, the cursor compare-and-set, and flows.md's rule that the first failure stops.

## Verification

**Commands:**
- `make lint`, `make test` -- green, with domain and application at 100% branch coverage and every new module paired with a test.
- `make openapi` -- no drift.
- `make e2e` -- green, on the disposable stack only.
