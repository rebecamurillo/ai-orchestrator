---
title: 'Reply polling pass'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: '431ebf6a8a3911f3b890fba58ef20656cb85e778'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 4-1 can check replies, but nothing reads open threads, so a reply never reaches the Run (CAP-12, AD-25).

**Approach:** Add a `read` pass to 3-3's `chat_poll`. For each open thread on its Project's current channel, it reads the replies since the cursor, outside any transaction, and hands them to 4-1's `apply_reply_batch`. A read failure is stored on the thread and logged when it changes. Nothing raises out of the job.

## Boundaries & Constraints

**Always:**
- **Where it runs.** The pass runs after 3-3's passes, once per Project with a channel, over `threads.list_open_for_project(project_id)`, oldest first. A thread whose `provider` or `channel_id` differs from the channel's is skipped and not read.
- **One read per thread per fire.** `replies_since(ThreadRef(thread.ref), thread.cursor)` is called outside any unit of work. An empty list writes nothing. Otherwise the pass calls `apply_reply_batch(ports, thread.id, thread.cursor, replies)`.
- **`ChatError`** ends that thread for this fire, and the pass moves to the next thread:
  - Under the thread lock, if the thread is still `open`, `error` is set to the redacted detail, but only when it differs from the stored value.
  - Only then is `chat read failed` logged with that detail.
  - A later successful read clears `error` the same way.
  - Nothing is retried within a fire (hard rule 7).
- **Any other exception** from a thread is logged as `internal: {class}` with the thread's ids, never with its message, and the pass goes on. An SQL error's message carries its bound parameters, which here means reply text.
- **Logging.** One line per checked reply, with `run_id`, `park_seq`, `thread_id`, `reply_id` and `outcome`. A line never carries reply text, and never the `author_id` of a refused reply.
- **Resume wiring.** The job's `SignalPorts` carries `harness_is_resumable` and `latest_attempt_for_run`, wired as `api/providers.py::signal_effect_ports` wires them, so an answer resumes the recorded session. The bare `SignalPorts(writers, engine)` that `terminal_jobs` builds would default to `restart`.
- **Fresh context per fire.** `RealEngine.schedule` runs `job` inside `contextvars.Context().run`, so a fire has no workflow context. This covers `terminal_poll` too.

**Never:**
- No reply checks or normalisation (4-1).
- No posting, reminders, or close at the end of a stop (3-3, 4-2).
- No new setting, no edit to `main.py`, no live platform in any test, and no container is stopped.

**Decided (lead review, 2026-11-02):**
- **Each thread is isolated, not each Project.** A thread whose root post was deleted fails every read, and would otherwise starve every other thread of its Project. The load stays at one read per open thread per fire, which is well inside Mattermost's and Slack's limits.
- **`error` is written only when it changes.** A revoked token then gives one log line and one Run page notice per thread, not one per fire.
- **The fresh context is required.** The library replays a recovered workflow's `send` by step number, not by destination: `dbos/_sys_db.py::_send_bulk_txn` returns early for an already recorded `function_id`. Suppose a fire answers Run A and then crashes. Its recovered fire answers Run B at the same step, B's message is skipped, and B sits `running` in `recv` for 30 days. With no workflow context, each send stands alone. The database, not step replay, keeps the job idempotent: a closed thread and a `running` Run are never answered twice.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected |
|---|---|---|
| Reply | open thread, reply from an allowed person | `apply_reply_batch` called once with the thread's cursor; `answered` logged; the session resumes |
| Nothing new | empty list | nothing written, nothing logged |
| Other channel | thread on another `channel_id` or provider | not read |
| Read fails | `ChatError("429 …")` on thread 1 of 2 | thread 2 still read; `error` stored, one line; the same failure next fire: no write, no line |
| Recovers | next read succeeds | `error` cleared |
| Unexpected | `apply_reply_batch` raises `OperationalError` whose message holds the text | one line `internal: OperationalError`, no message; next thread read |
| Overlap | two fires with the same batch | one applies; 4-1's gate drops the other |
| Recovered fire | `job` called inside a workflow context | the job sees none, so `engine.signal` is delivered |
| Log hygiene | fixture text, refused author id, token | absent from every captured line |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/`.

- `application/jobs/chat_read.py` (new) -- `read_replies(ports, project, channel, chat)`, the pass. `chat_poll.py` calls it last.
- `application/jobs/chat_poll.py` (3-3's) -- `ChatPollPorts` gains `signal: SignalPorts`, from which the pass builds 4-1's `ReplyPorts`.
- `infrastructure/terminal_jobs.py` -- the chat job's ports. They come from 3-3's `open_chat_ports`, with the two callables built from `build_harnesses(settings, RealProcessRunner())`.
- `infrastructure/dbos/facade.py::RealEngine.schedule` -- `scheduled` calls `contextvars.Context().run(job)`.
- Reuse: 4-1's `apply_reply_batch`; 3-1's `FakeChatChannel` and `ChatError`; the fakes for threads (3-3) and channels (3-4); `structlog.testing.capture_logs`.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/application/test_chat_read.py`, `tests/unit/test_chat_poll_wiring.py`, `tests/unit/test_dbos_schedule_context.py` -- new. They cover every matrix row, and each is seen failing first. The context test sets the library's context variable, then asserts that `get_local_dbos_context()` is `None` inside the job.
- [x] Code Map in order.

**Acceptance Criteria:**
- Given a Project with three open threads where the second raises `ChatError`, when one fire runs, then the first and third are read, and exactly one line names the second.
- Given the chat job's ports, when a thread's latest `agent` attempt has a `session_id` on a resuming harness, then the recorded `answer` carries `mode: session`.
- Given a fire that raises anything, when the scheduler calls the job, then the job returns normally.

## Design Notes

**Implementation decisions (2026-11-03, dev):**
- The pass is `jobs/chat_read.py::read_replies(ports, channel, chat, token) -> bool`, the shape of `post_notices`: `channel` names the Project, and `token` is what `redacted` masks. It returns `True` when any read in the fire failed (a `ChatError`, an out-of-order batch, or any exception from `replies_since`), for 4-2's watch pass. An exception from `apply_reply_batch` is not a read failure.
- **Bounding 4-1's crash row.** Any exception that is not a `ChatError`, from the read or from `apply_reply_batch`, is stored as `internal: {Class}` (`chat_notice.INTERNAL`). It goes through the same write as a `ChatError` detail: Run lock, then thread lock, only while `open`, only when it changes, and logged only when written. The thread stays `open`, and the next thread is read. A write that itself fails is logged by class, with nothing stored.
- **Clearing.** A successful read clears a stored `error` through the same write, and the pass only locks when the listed thread had one. When this fire's batch answered the stop, the clear also applies to the thread it just closed, so an answered thread does not show a stale read error.
- **Thread gone, rate limit, order (port-level).** `domain/ports/chat.py` gains two `ChatError` subclasses, `ChatThreadGone` and `ChatRateLimited`, and a pure `ChatChannel.follows(cursor, after) -> bool`. The pass catches by class and parses no detail.
  - Mattermost: a 404 on `/posts/{root}/thread` is `ChatThreadGone`. A 404 anywhere else stays a plain `ChatError`. A 429 on any call is `ChatRateLimited`.
  - Slack: `thread_not_found` from `conversations.replies` is `ChatThreadGone`. An HTTP 429, or `ratelimited` from any method, is `ChatRateLimited`.
  - A gone thread is `closed` with the redacted detail as `error`, under both locks, without touching `cursor`. A rate limit is stored like any `ChatError`, then the Project's pass stops for the fire.
  - The matrix's `ChatError("429 …")` row is a plain `ChatError`, so the next thread is still read. Only the adapter's class stops the pass.
  - `follows` compares `(create_at, id)` on Mattermost and the `ts` decimal on Slack. Each reply must follow the one before it, and the first must follow the thread's cursor. Otherwise the batch is the read failure `the replies came back out of order`, and nothing is applied.
- **Wiring.** `ChatPollPorts.signal` holds `SignalPorts` on the fire's own writers. `terminal_jobs._chat_poll_job` builds `harness_is_resumable` from `build_harnesses(settings, RealProcessRunner())`, once per job build, and `latest_attempt_for_run` from `writers.attempts`, as `signal_effect_ports` does. The job body is wrapped, so a failure to open the session is logged as `chat poll failed` by class, and the scheduler always sees a normal return.
- **Fresh context.** `RealEngine.schedule`'s wrapper calls `contextvars.Context().run(job)`. This covers every scheduled job.
- **Shared fakes extended.** `FakeChatChannel` gains `follows`, `read_errors` (per-thread persistent failures) and `misordered`. `World.ports()` gains `signal`, with the settable `resumable` and `latest_attempt`.
- **Existing tests revised (rule 1(b), story 4-3, 2026-11-03):**
  - `test_chat_poll_registration.py`: the fake `open_chat_ports` yields a stand-in with `writers` instead of a string, since the job now builds `SignalPorts` on it. The assertion is now `is`, and it also pins `signal.writers`.
  - `test_chat_slack_budget.py`: the mock transport also answers the read pass's `auth.test` and `conversations.replies`, because the read now runs in the same fire. Every assertion is unchanged.
- **Review fixes (2026-11-03, 4-3 review):**
  - **An exception that cannot be stored is still logged.** An error write now reports `written`, `same` or `moot`. When `apply_reply_batch` raises and the thread can no longer take the error (closed, or gone), one `chat read failed` line `internal: {Class}` is logged with the thread's ids anyway. The main case: the batch committed the answer and the close, then `finish_signal`'s `engine.signal` raised. That case is an instance of the pre-existing deferred item in `implementation-artifacts/deferred-work.md` ("A backend killed after `signal_run` commits but before `engine.signal` delivers leaves the Run marked running with a walker still waiting on its recv"). 4-3 leaves a trace and does not fix it: the startup re-send sweep is still that item's fix. A value already stored was logged when it was stored, so a repeat failure on an open thread stays silent.
  - **One close point.** The gone thread is closed through 4-1's `close_thread`, now `close_thread(ports, thread, cursor=None, *, error=None)`. A cursor or error left out is kept. 4-1's call and tests are unchanged, and 4-2 has one function to extend.
  - **A stable rate-limit text.** `ChatRateLimited` carries `stable`, its detail without the platform's wait, defaulting to the detail. Slack's 429 sets it to `{method}: 429 rate limited` and keeps `Retry-After {n}` in the detail, which 3-2's adapter test pins. The pass stores and logs `stable`. The choice is the port, not the pass: only the adapter knows which part of its text varies, and no application code trims a string.
  - **No private exception escapes Mattermost.** `_call` maps a 404 to the class its caller names: plain `ChatError` by default, and `ChatThreadGone` only from the thread read.
  - **`closed_ok`** clears an error only on a thread whose state is `closed`.
- **Proposed AD-25 line** (for the Operator to ratify): "`ChatError` has two port-level subclasses: `ChatThreadGone` (the thread's root no longer exists: Mattermost 404 on the thread read, Slack `thread_not_found`) and `ChatRateLimited` (HTTP 429, Slack `ratelimited`). `ChatChannel.follows(cursor, after)` orders an adapter's own opaque cursors. The read pass closes a gone thread with its detail, ends a Project's reads for the fire on a rate limit, refuses an out-of-order batch as a failed read, and stores every other failure, `internal: {Class}` included, on its thread only when it changes."
- **Only a live check confirms:** Mattermost's actual status for a deleted root, Slack's code for a deleted parent, the Slack Tier 3 behaviour under one read per open thread per fire, and the fresh context under a real recovered DBOS scheduled workflow.

## Verification

**Commands:**
- `make lint`, `make test` -- green, with application at 100% branch coverage and every new module paired with a test.
- `make e2e` -- green, on the disposable stack only.

**Manual checks:**
- At 4-2's done checkpoint, the Operator answers a live Mattermost thread once and replies again. The second reply changes nothing.
