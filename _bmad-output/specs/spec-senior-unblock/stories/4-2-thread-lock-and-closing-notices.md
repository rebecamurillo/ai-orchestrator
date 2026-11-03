---
title: 'Thread lock and closing notices'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: '184e896'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4-1 closes a thread only when a chat reply wins. A stop that ends any other way leaves its thread `open`, and nobody in the channel learns who answered. A later mention gets silence. Neither Mattermost nor Slack lets a bot lock a thread (Design Notes), so "closed for good" has to be the orchestrator's own refusal, and the thread has to say so (CAP-12, AD-25).

**Approach:** Add three passes to 3-3's `chat_poll`. None writes a status or a gate record (AD-8).
- **Close:** each `open` thread whose Run has left its stop is closed and owes a closing notice.
- **Closing notice:** the notice is posted in the thread, saying how the stop ended. This pass is the only poster for every close, including 4-1's.
- **Watch:** for 24 h after it closes (`closed_at`), a closed thread whose closing notice was posted gets one notice for the first allowed reply that mentions the bot.

## Boundaries & Constraints

**Always:**
- **The stop ended** when `not (run.status == "needs_you" and run.park_seq == thread.park_seq)`. This covers a later stop, `running`, `queued` (`continue` on `dependency`), and every terminal status. A Run at the same `park_seq` has not left its stop, even when a lock flag is set or `budget_raise` rewrote its `park_kind` (Decided).
- **New `chat_thread` fields**, all nullable, owned by 4-2:
  - `closed_at`;
  - `close_notice` and `mention_notice`, each `NoticeState = Literal["due", "sending", "posted", "failed"]`. `mention_notice` never takes `due`;
  - `close_notice_at` and `mention_notice_at`, the claim times;
  - `mention_cursor`.

  `close_notice` NULL means no notice is owed. Nothing returns a `closed` thread to `open`, and only 4-1 writes `cursor`.
  - *Migration CHECKs.* Named CHECKs hold the values: `close_notice IN ('due','sending','posted','failed')` and `mention_notice IN ('sending','posted','failed')`. Two cross-column CHECKs hold the order: `close_notice IS NULL OR state = 'closed'` and `mention_notice IS NULL OR close_notice = 'posted'`.
  - *Old threads.* A thread closed before the migration keeps `closed_at` NULL. It gets no notice and no watch.
- **Close pass.** It runs once per fire, before the per-Project loop, over `threads.list_by_state("open")`. That read has its own pass-level `try`. It covers every Project's open threads, including a Project whose channel is now off and one whose channel cannot be opened.
  - *Pre-check.* For each thread, `stop_ended` is checked first with an unlocked `runs.get`. A thread whose stop has not ended is left, and takes no lock.
  - *Close.* An ended thread gets its own unit of work and its own `try`:
  1. `runs.get_for_update(thread.run_id)`, then `threads.get_for_update(thread.id)`.
  2. A re-check that the thread is still `open` and its stop has ended.
  3. A write of `state = "closed"` and `closed_at = now`. `close_notice` is `"due"` only when `channels.get(run.project_id)` returns a channel with the thread's `provider` and `channel_id`. It is NULL when there is no channel, or when the thread is on an old one.
  4. A commit.

  It calls no platform. `posting` and `failed` threads are not touched.
- **4-1's winner close** writes `closed_at = now` and `close_notice = "due"` in its existing commit. That is the one edit to 4-1's `apply_reply_batch`, and 4-1's gate already puts the thread on the current channel.
  - It is a declared behaviour change of story 4-2.
  - A 4-1 test that pins the whole closed-thread row may be revised under hard rule 1(b), citing "story 4-2, 2026-11-02", for those two fields only. No other existing test changes.
- **Closing-notice pass.** It reads `threads.list_notices_due(project_id)`: every `due` thread of the Project, oldest `closed_at` first. It posts at most `WATCH_READS_PER_FIRE` notices per Project per fire, and the rest stay `due` for the next fire. Each thread follows 3-3's post protocol:
  - *Claim.* One unit of work locks the Run, then the thread, and re-checks `due`.
    - A thread whose `provider` or `channel_id` differs from the channel this fire opened becomes `failed`. Nothing is posted, and `chat close notice abandoned` is logged.
    - Otherwise the claim reads `records.list_for_run`, composes the text, sets `close_notice = "sending"` and `close_notice_at = now`, and commits.
  - *Reply.* `channel.reply(ThreadRef(thread.ref), text)` runs with no unit of work open and no mentions.
  - *Record.* Under the thread lock, a thread still at `sending` becomes `posted`, or `failed` on any exception. Otherwise nothing is written and `chat close notice outcome dropped` is logged.
  - *First `ChatError`.* It ends the pass for that Project this fire. The remaining threads stay `due`. They were never sent, so posting them later is not a repost.

  Nothing is reposted (hard rule 7).
- **The ending record** (`rules/chat_close.py::ending_record`, pure):
  - *The stop's park record.* This is the `(run.park_seq - thread.park_seq + 1)`-th record from the end whose `event` is in `PARK_KINDS`. The invariant behind it: every `park_seq` increment writes exactly one such record (`writers.park_run`, `budget_second_record`, `_write_dependency_park`), and no other writer uses a park-kind event.
  - *The window.* The records after the park record and before the next park record.
  - *The choice.* In the window, the first record that is either a signal whose event is `answer`, `continue`, `retry`, `skip_step`, `skip_story`, `skip_epic`, `terminal_resume` or `cancel`, or the expiry record (event `failed`, actor `machine`, text `writers.RUN_EXPIRED`). Failing that, the first `budget_raise`. Failing that, the first `done`, `failed` or `cancelled`. Failing that, the next park record when its event is `paused`. Otherwise `None`.
  - *Known limitation.* A resuming `budget_raise` followed by a `cancel` while the Run runs reads `Run cancelled`.
  - `session` is true when a `session_end` record lies between the park record and the chosen record.
- **Closing text** (`close_line`): `Closed · stop {park_seq} · {how}`, then `Replies in this thread are no longer read.`, then `Run: {PUBLIC_BASE_URL}/workflows/{run_id}`. The link line is left out when the base URL is blank.
  - **`how`, for a signal**, is `{verb} {by}`:
    - *verb:* `answered`, `continued`, `retried`, `step skipped`, `story skipped`, `epic skipped`, `resumed`, `Run cancelled`, or `budget raised`. An `answer` at a stop whose park record is `checkpoint` reads `rejected`.
    - *by*, from the record's `actor`:
      - `operator`: `by the Operator (Run page or API)`;
      - `chat`: `by {author} via {platform}`, read from the payload;
      - `terminal`: `from a terminal session`;
      - `senior`: `by the senior`;
      - `machine`: `by the orchestrator`.
    - `session` appends ` after a senior session`.
  - **`how`, for the expiry record:** `Run expired`, with no `by` part.
  - **`how`, for any other lifecycle record:** `the Run finished`, `the Run failed`, or `the Run was cancelled`.
  - **`how`, for a `paused` park record:** `the Run was paused`.
  - **`how`, with no record:** `the stop ended`.
  - **Defensive wordings.** `by the senior` and `the Run was paused` keep the table total, and today's code cannot reach either. `pause` is refused at `needs_you`, so an ender always comes first. A consult runs while the Run is `running`, and an Operator session ends with an `operator` signal.
    - No matrix row covers them.
    - `test_chat_close_rules.py` covers both, and `the stop ended`, directly on `ending_record` and `close_line` with fabricated records. There is no `pragma: no cover`.
  - **`author`** goes through 3-3's `neutralise`. Every newline is then collapsed to one space, and the result is cut to 200 code points. When it is missing, the `by` part reads `by a chat reply via {platform}`.
  - **Never in the text:** answer text, the question, a reason, or a mention. The text is therefore the same under `metadata_only`.
- **Watch pass.** It reads `threads.list_watched(project_id, provider, channel_id, closed_since=now - WATCH_HOURS, limit=WATCH_READS_PER_FIRE)`, with the opened channel's provider and id.
  - *What the list holds.* Threads that are `closed`, have `close_notice == "posted"` and `mention_notice` NULL, are on that channel, and have `closed_at >= closed_since`. Every filter is in the query, and the newest `closed_at` comes first. `WATCH_HOURS = 24` and `WATCH_READS_PER_FIRE = 5`.
  - *Skipped.* The watch is skipped for a Project whose read pass hit a `ChatError` in the same fire.
  - *Starvation, accepted.* With more than `WATCH_READS_PER_FIRE` watched threads, the older ones may go unread until their window ends, because the notice is a courtesy and the reply is refused either way.
  - **Read.** For each thread, `replies_since(ref, mention_cursor or cursor)` runs outside any unit of work. An empty list writes nothing.
  - **The first counted reply.** A reply counts when its `author_id` is in `allowed_users` and its `mentions_bot` is true. Outsiders never count (Decided). For the first such reply, a claim takes the thread lock and checks that `mention_notice` is NULL and `mention_cursor` is unchanged since the read. It then sets `mention_notice = "sending"`, `mention_notice_at = now`, and `mention_cursor` to that reply's cursor, and commits. Then it calls `reply(ref, "This thread is closed. Act on the Run page: {link}")` with no mentions, and records `posted` or `failed` as above. Without a base URL the text is `This thread is closed. Act on the Run page.`
  - **No counted reply.** `mention_cursor` moves to the last reply's cursor under the same check.
  - **One notice per thread.** A thread gets one notice, never one per mention.
  - **A `ChatError` on a read** sets `mention_notice = "failed"` and `mention_notice_at = now` under the thread lock, only while `mention_notice` is still NULL. That ends the thread's watch, and one line is logged. The watch pass then stops for that Project this fire.
- **Sweep.** It runs at the start of every fire, beside 3-3's `posting` sweep. Nothing is reposted.
  - *Interrupted.* It reads `threads.list_notices_in("sending")`: every thread with either notice field at `sending`. Under `get_for_update`, each notice field is re-checked against its own state and its own claim time (`close_notice` with `close_notice_at`, `mention_notice` with `mention_notice_at`). A field still `sending` whose claim time is before `ports.started_at`, or more than `POSTING_STALE_MINUTES` old, becomes `failed`, and `chat notice interrupted` is logged.
  - *Stranded.* It reads `threads.list_notices_in("due")`. A `due` thread whose Run's Project has no channel row becomes `failed` under the thread lock, and `chat close notice abandoned` is logged.
- **Pass order.**
  - *Per fire:* the sweeps, then **close** over every open thread.
  - *Then per Project with a channel:* post, remind, accept notice (3-3), read (4-3), **closing notice**, **watch**. 4-3's `read_replies` now reports whether any read raised `ChatError`, so the watch can be skipped.
- **Isolation and logging** follow 3-3. There is one `try` for each thread and pass. Log lines carry ids, `park_seq`, the notice state and `error_class`, and never text, a handle, an author id or error detail. A notice failure is not stored in `chat_thread.error`, which keeps 3-3's D3 meaning: a post or read failure.

**Never:**
- No status write, gate record or engine call (AD-8). No reopening.
- No change to `cursor`, to 4-1's checks, or to 4-3's read of open threads.
- No API, read-model, web-client or setting change. No `DBOS_APPLICATION_VERSION` bump.
- No platform syntax in `application/` (AD-25). No live platform in any test. No container is stopped (hard rule 9).

**Decided (lead decisions, 2026-11-02):**
- **The stop's identity is `park_seq`** (3-3, AD-24). A `park_kind` rewrite at the same `park_seq` does not end the stop. A `budget` thread rewritten to `blocked` stays open and reminded.
- **4-1 is edited** as stated above. The edit is declared here, and the rule 1(b) revision is allowed for the two new fields.
- **The count-back stays.** A guard test pins its invariant (Tasks). The `budget_raise`-then-`cancel` misattribution is a stated limitation. Expiry is not one, because its record ranks with the signals.
- **The watch counts allowed authors only.**
- **`WATCH_HOURS` and `WATCH_READS_PER_FIRE` are constants.** A 429 that ends a watch for good is accepted.
- **Every open thread is closed, whatever its channel.** A Project whose channel is now off is included.
- **The known gap is accepted** (Design Notes).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected |
|---|---|---|
| Run page answer | open thread at stop 3; record `answer` by `operator`; Run `running` | closed, `close_notice` `due`; one `reply`: `Closed · stop 3 · answered by the Operator (Run page or API)`, no mentions; `posted` |
| Chat answer | 4-1's winner by `alice` on `slack` | 4-1's commit holds `closed`, `closed_at` and `due`; one reply `… answered by alice via slack`; the close pass writes nothing |
| Other endings | `cancel`; `terminal_resume`; `continue` on `dependency` (Run `queued`); expiry (`RUN_EXPIRED`); `failed` from `on_fail`; `skip_story`; `answer` at a `checkpoint` stop | `Run cancelled by the Operator (Run page or API)`; `resumed from a terminal session`; `continued …`; `Run expired`; `the Run failed`; `story skipped …`; `rejected by the Operator (Run page or API)` |
| Later stop | answered, then parked again at stop 4 before the pass | stop 3's thread closed with the answer's text; stop 4 untouched |
| Senior session | `session_start`, `session_end`, `answer` | `answered by the Operator (Run page or API) after a senior session` |
| Not ended | same `park_seq` with `senior_session`, with `terminal_session`, or `budget` rewritten to `blocked` | stays `open` |
| Raise | held `budget_raise`, then `answer`; or a resuming `budget_raise` | `answered …`; or `budget raised by the Operator (Run page or API)` |
| Park counting | Run with 5 earlier park records, thread at stop 0 from before `park_seq` existed | the right park record and ender are chosen |
| No ender | no ender record in the window | `Closed · stop 3 · the stop ended` |
| Hostile or metadata-only | author handle with a newline and `@channel`; a 300-character handle; `metadata_only: true` | the handle neutralised, its newline now one space, cut to 200; the text identical in both modes; no answer or question text |
| Overlap | the fake's `on_send` runs a second fire during `reply` | one close write; one `reply` |
| Notice fails | `ChatError` on `reply` | `close_notice` `failed`; `error` unchanged; one line naming `error_class`; no repost next fire |
| Backlog | 7 `due` threads in one Project | 5 posted this fire, oldest `closed_at` first; 2 stay `due` and are posted next fire |
| Notice 429 | `ChatError("429 …")` on the 2nd of 4 `due` | the 2nd `failed`; the 3rd and 4th not sent and still `due`; one line |
| Switched after due | `due` thread; the Project's channel now another `channel_id` or provider | `failed` at the claim; no `reply`; one `chat close notice abandoned` line |
| Off after due | `due` thread; the Project's channel row deleted | the sweep sets `failed`; no `reply`; one `chat close notice abandoned` line |
| Restart | `sending` claimed before `started_at`, on either notice field | that field `failed`, the other field unchanged; no `reply` |
| In flight | `sending` claimed 2 min ago, same process | untouched |
| Channel switched | open thread on the old channel; Run left its stop | closed, `close_notice` NULL; no `reply` |
| Channel off | the Project's channel was deleted; open thread; Run left its stop | closed by the per-fire close pass, `close_notice` NULL; no channel opened; no `reply` |
| Unopened channel | decryption fails | the close pass still closes; `due` notices wait; no `reply` |
| Not open | `posting` or `failed` thread whose Run left its stop | not touched |
| Not ended, cheap | open thread whose Run is still at its stop | unlocked `runs.get` only; no `get_for_update`, no write |
| List fails | `list_by_state("open")` raises | one line; the per-Project passes still run |
| Late mention | closed and noticed; allowed `@bot do X` after the cursor | one `reply` `This thread is closed. Act on the Run page: …`; `posted` |
| One per thread | two counted mentions in one read; another on the next fire | one notice in all |
| Not counted | an outsider's mention; an allowed reply without a mention | no notice; `mention_cursor` advances |
| Window and cap | closed 25 h ago; `closed_at` NULL (closed before the migration); 7 watched threads | not read; not read; the 5 newest read |
| Watch read fails | `ChatError` on the first watched thread of 3 | that thread `mention_notice` `failed` with `mention_notice_at`; the other two not read this fire; one line |
| Read pass failed | 4-3's read hit `ChatError` this fire | no watch read for that Project this fire |
| Stays closed | a 4-1 batch arrives for a closed thread | `superseded`; still `closed` |
| No transaction | `on_send` checks the fake unit of work | none open during any `reply` |
| Log hygiene | handle, author id, token, error detail in fixtures | absent from every captured line |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/entities/chat_thread.py` (3-3's) -- `NoticeState` and the six fields, each defaulting to `None`.
- `domain/ports/repositories.py` -- `ChatThreadRepository` gains:
  - `list_notices_due(project_id)`: every `due` thread of the Project, oldest `closed_at` first;
  - `list_notices_in(state)`: every thread with either notice field at `state`, across Projects, for the sweep;
  - `list_watched(project_id, provider, channel_id, closed_since, limit)`, with every filter in the query, newest `closed_at` first.
- `infrastructure/db/models/chat.py`, `infrastructure/db/repositories/chat.py`, `alembic/versions/{head+1}_chat_thread_close.py`:
  - six nullable columns with the four named CHECKs of Boundaries. The migration writes no data;
  - the adapter's `update` persists all six columns.
- `application/jobs/chat_read.py` (4-3's) -- `read_replies` returns `True` when any thread read raised `ChatError` in this fire. The change is additive.
- `application/rules/chat_close.py` (new, pure) -- `stop_ended`, `ending_record`, `close_line`, `closed_mention_line`, `WATCH_HOURS` and `WATCH_READS_PER_FIRE`.
- `application/jobs/chat_close.py` (new) -- the close pass, the closing-notice pass and the `sending` sweep.
- `application/jobs/chat_watch.py` (new) -- the watch pass.
- `application/jobs/chat_poll.py` -- the pass order above. The close pass runs once per fire, outside the per-Project `try`, inside its own per-thread `try`.
- `application/use_cases/chat_reply.py` (4-1's) -- the winner's close also writes `closed_at` and `due`, from `signal.writers.clock`.
- Reuse:
  - 3-3's `neutralise`, `POSTING_STALE_MINUTES`, `ChatPollPorts.public_base_url` and `started_at`;
  - `domain/statuses.py::PARK_KINDS`;
  - the shared fakes `FakeChatThreadRepository` (extended, not copied), `FakeChatChannel` with `on_send`, `FakeClock`, and the run, record and channel fakes.

## Tasks & Acceptance

**Execution:**
- [x] Extend `tests/unit/fakes/chat_thread.py` with the three list methods. Each reads a thread's Project through `runs`, as `list_open_for_project` does, and applies every filter the adapter's query applies.
- [x] New tests, each seen failing first, covering every matrix row through the shared fakes, with `structlog.testing.capture_logs` for logs:
  - `tests/unit/application/test_chat_close_rules.py`, including the defensive wordings on fabricated records
  - `tests/unit/application/test_chat_close.py`
  - `tests/unit/application/test_chat_watch.py`
  - `tests/unit/application/test_chat_poll_order.py`
  - `tests/unit/test_chat_repository_close.py`, which covers:
    - the compiled list queries, with every filter;
    - the four CHECKs;
    - an `update` round trip of each of the six new columns.
  - `tests/unit/application/test_park_record_invariant.py`, the count-back's guard, which pins three things:
    1. **The writers.** Each park writer, driven through the shared fakes, raises `park_seq` by exactly 1 and appends exactly one record whose event is in `PARK_KINDS`. The writers are `writers.park_run`, `apply_step_result.budget_second_record` and `writers._write_dependency_park`, every `park_seq` increment in `application/` at `afb565a`.
    2. **The scan.** An `ast` scan of `application/` raises a flag in two cases. Flags are allowed only inside those three functions, so a new park writer fails the test until it is added to (1).
       - A `park_seq` keyword argument or dict key whose value is not a plain attribute read `<expr>.park_seq`. Read-model and log sites such as `run_events.py`'s `RunEvent(park_seq=run.park_seq)`, and 3-3's `ChatThread`, `StopFacts` and `reminder_text` calls, pass.
       - An `Entry(event=…)` whose value is a `PARK_KINDS` string literal or `park.kind`.
    3. **The alphabets.** `PARK_KINDS` shares no token with `SIGNAL_KINDS`, `LIFECYCLE_EVENTS`, `MACHINE_EVENTS` or `WRITE_EVENTS`.
- [x] 4-1's winner-close edit. A 4-1 test that pins the whole closed-thread row is revised under rule 1(b), citing "story 4-2, 2026-11-02", for the two new fields only (Decided).
- [x] Code Map in order.

**Acceptance Criteria:**
- Given a Run `blocked` at stop 3 with an open thread, when the Operator answers on the Run page and a fire runs, then the thread is `closed` and the fake channel holds exactly one reply in that thread, naming the Operator, with no mentions.
- Given an allowed reply that 4-1 applied, when the same fire's closing-notice pass runs, then one reply names `{author} via {platform}`, and no fire after it posts another.
- Given a closed thread with a posted notice, when two allowed users mention the bot over two fires, then exactly one closed-thread notice is posted, and none after a restart.
- Given any fire, when it raises anywhere in these passes, then `run_chat_poll` returns normally and no Run, Step or gate record has changed.

## Design Notes

- **No platform lock exists, verified 2026-11-02.**
  - Mattermost's v4 posts API has no operation that locks a thread or refuses replies ([posts.yaml](https://raw.githubusercontent.com/mattermost/mattermost/master/api/v4/source/posts.yaml)). Its only control is channel-wide posting permissions ([forum](https://forum.mattermost.com/t/disable-replies-on-a-specific-channel-in-mattermost/22860)).
  - Slack's *Pause replies and reactions* is Enterprise-only, done in the UI by Org Owners or Content Admins, and has no API ([help](https://slack.com/help/articles/42527000860179)).
  - "Locked" therefore means three things: 4-1 refuses every non-`open` thread, the closing notice says replies are no longer read, and the watch gives one pointer to the Run page.
- **Why this order.**
  - *Close first.* Then a reply sent after the stop ended reaches the watch, rather than 4-1's `stale`, which would move the cursor past it with no notice.
  - *Closing notices after read.* Then 4-1's closes get their notice in the same fire.
  - *Watch last.* It needs a posted closing notice.
  - *Known gap, accepted (lead decisions).* A Run page answer that commits between this fire's close pass and its read pass still meets `stale`, and that reply gets no notice.
  - *Possible fix, not built.* The read pass could re-check the stop under 4-1's locks and send the replies of a thread whose stop has ended to the watch instead of `stale`.
- **One poster.** 4-1 writes only the marker, and this story's pass posts every closing notice. That fits 4-1's "No posting" and its "replies after the winner stay past the cursor, for 4-2".
- **Attribution without a stop on the gate record.** `gate_record` carries no `park_seq`, so the stop's park record is counted from the end, anchored on `run.park_seq`. That also holds for Runs parked before AD-24 existed. The Run lock in the claim makes the Run and its records one consistent read, because the walker's park takes the same row lock by its `UPDATE`.
  - The `budget_raise` priority covers the held raise (AD-13).
  - The remaining misattribution is a resuming raise followed by a `cancel` while the Run runs, which reads `Run cancelled`. It is a stated limitation (lead decisions).
  - The count-back rests on one park-kind record per `park_seq` increment. `test_park_record_invariant.py` pins that, and fails when a new park writer appears. A `stop` column on `gate_record` was considered and not taken.
- **Run page: unchanged.** `Alert.chat_thread` is the current stop's thread, and a closed thread's stop is never current. 3-3's `chatThreadText` already renders `closed`. A failed closing notice is logged only, because the stop it reports on is over.
- **Load.** The watch and the closing notices each add at most `WATCH_READS_PER_FIRE` calls per fire per Project, which at 30 s is 10 a minute each. In each pass the first `ChatError` ends that pass for the Project in that fire, and a read-pass `ChatError` skips the watch. A 429 is therefore never repeated in the same fire. The Slack Tier 3 deferral on open-thread reads stays deferred (below).
- **Proposed AD-25 amendment**, for the Operator to ratify:
  > A thread's stop has ended when its Run is no longer `needs_you` at its `park_seq`; a `park_kind` rewrite at the same `park_seq` does not end it. `chat_poll` closes such a thread first in each fire, for every Project whatever its channel, and every close, by a reply or at the end of the stop, owes one closing notice in the thread, claimed in the database, posted once with no mention, never reposted, naming how the stop ended from the gate record and carrying no answer text. For 24 h after it closes, a closed thread whose closing notice was posted is read for its first allowed reply mentioning the bot, which gets one notice pointing to the Run page. No platform lets a bot lock a thread; "closed" is the orchestrator's refusal. `chat_thread` gains `closed_at`, `close_notice`, `close_notice_at`, `mention_notice`, `mention_notice_at` and `mention_cursor`.
- **Why the budget thread stays open.** A `budget` stop rewritten to `blocked` at the same `park_seq` keeps its open, reminded thread (3-3). There is one thread per `park_seq` for good, so closing it would leave a chat-only team with no thread for the blocked question.
- **Why allowed authors only.** It matches 4-1's silent refusal of outsiders, and an outsider cannot make the bot speak.
- **Deferred, not 4-2's:**
  - **Edited replies.** If the done checkpoint shows that an admin edit or a slash-command post reads as an allowed person's reply, dropping edited replies (`edit_at`, `edited`) in the adapters is a follow-up story.
  - **Slack Tier 3** on open-thread reads. 4-3 isolated threads but does not stop on a 429. The `deferred-work.md` entry stays open.

## Verification

**Commands:**
- `make lint`, `make test` -- green, with domain and application at 100% branch coverage and every new module paired with a test.
- `make e2e` -- green, on the disposable stack only.

**Manual checks (done checkpoint).** The Operator runs these with real bot tokens on Mattermost and on Slack, using a fixture Run at a `blocked` stop. First, confirm the Slack bot is an internal app that is not distributed (3-2).

*Setup, once per platform:*
- The stack runs on this commit: `select * from alembic_version` reads `0030_chat_thread_close` (the `psql` line in `DEPLOY.md`).
- `PUBLIC_BASE_URL` is set, so every notice ends with the Run link. `CHAT_POLL_SECONDS` is the period "one poll" means below (30 s by default).
- The Project's channel is stored and its connection test passes (3-4). Two people are in `allowed_users`, and a third person who is in the channel is not.
- The fixture Run is at a `blocked` stop with an agent attempt that can be resumed, and its root post is in the channel (3-3).
- To read a thread's state, run through the same `psql` line:
  `select park_seq, state, closed_at, close_notice, mention_notice, mention_cursor from chat_thread where run_id = '<run id>' order by park_seq;`
- To read the answer record: `select actor, payload from gate_record where run_id = '<run id>' and event = 'answer' order by at;`

*Pass criteria:*
1. Reply once as an allowed person, mentioning the bot. Within one poll the session resumes, the `answer` gate record's payload has `mode: session`, and one reply in the thread reads `Closed · stop {n} · answered by {handle} via {platform}`, then `Replies in this thread are no longer read.`, then the Run link. It mentions nobody. The row reads `closed`, `close_notice = posted`.
2. Reply again as an allowed person, mentioning the bot. The Run, its records and its status do not change. Within one poll one reply appears: `This thread is closed. Act on the Run page: {link}`. The row reads `mention_notice = posted`.
3. Restart the backend (`docker compose restart backend-api`, with the Operator's go-ahead, hard rule 9), then mention the bot a third time. After two polls no further reply appears.
4. As the person not in `allowed_users`, mention the bot in the closed thread. After two polls no reply appears.
5. Bring the Run to a second `blocked` stop and answer it on the Run page. Within one poll its thread closes with `Closed · stop {n+1} · answered by the Operator (Run page or API)`. The first thread gets nothing new.

A step fails when its reply is missing, appears twice, carries answer text or a mention, or the row does not read as stated.

*Trust edges.* Observe each one and record the outcome in `deferred-work.md`. They are not pass criteria. A bad outcome opens an "Edited replies" follow-up and does not fail 4-2.
- **Mattermost slash command.** Make a custom slash command whose endpoint returns `{"response_type":"in_channel","text":"@bot …"}`, and run it in an open thread as an allowed user. Record whether it is read as that user's reply.
- **Mattermost admin edit.** A system admin edits an allowed user's non-answering post in an open thread to `@bot …` before the next poll. Record whether it is applied.
- **Slack Connect.** A Slack Connect external user mentions the bot in an open thread. Record whether the log line shows `not_allowed` and whether the user's id differs from every allowed id.

## Spec Change Log

- 2026-11-02, written from `stories.yaml` 4-2, CAP-11, CAP-12, flows.md, brownfield.md, AD-8, AD-13, AD-24 and AD-25 with every amendment, the 3-1, 3-2, 3-3, 4-1 and 4-3 story files, and the code at `afb565a`. That code covers `signal_run`, `writers.park_run` and its siblings, `signals_table`, `run_views_alert`, the chat port and adapters, and 3-3's in-progress fakes.
- KEEP: the end-of-stop rule on `park_seq` alone, one poster for every notice, the claim-commit-post-record protocol, and no reopening.
- 2026-11-02, lead decisions on Q1 to Q9:
  - **Q1.** The end of a stop is keyed on `park_seq` alone, following 3-3 and AD-24. "With that `park_kind`" is dropped.
  - **Q2.** The `apply_reply_batch` edit is a declared behaviour change of 4-2. The rule 1(b) revision is named in Boundaries.
  - **Q3.** `by the senior` and `the Run was paused` (newly added) are kept as defensive wordings. They are noted as unreachable, and no matrix row covers them.
  - **Q4.** The count-back is kept, with the new guard test `test_park_record_invariant.py`. The `budget_raise`-then-`cancel` misattribution is a stated limitation.
  - **Q5.** Allowed authors only.
  - **Q6.** Constants, and a 429 ends a watch for good.
  - **Q7.** The close pass now runs once per fire over every open thread, whatever its channel, so a Project whose channel is off is included. `close_notice` is NULL with no channel or an old one. A matrix row was added.
  - **Q8, Q9.** Deferred, in Design Notes.
  - **Known gap.** Accepted. The cheap fix is proposed in one sentence and not built.
- 2026-11-02, lead review. Approved with changes, all applied:
  - **The guard scan (high).** It now flags only non-attribute `park_seq` values, and `Entry(event=…)` with a park-kind literal or `park.kind`, outside the three writers. `WRITE_EVENTS` joins the disjointness check.
  - **Stranded `due`.**
    - `list_notices_due(project_id)` returns every `due` thread.
    - A channel mismatch at the claim fails the notice as `chat close notice abandoned`.
    - The sweep fails the `due` notices of Projects with no channel row.
    - Rows "Switched after due" and "Off after due" were added.
  - **Burst and 429.** At most `WATCH_READS_PER_FIRE` closing notices per Project per fire, and the first `ChatError` ends the pass. Rows "Backlog" and "Notice 429" were added.
  - **Repository.**
    - `list_watched` takes `provider` and `channel_id`, with every filter in the query.
    - The fake filters through `runs`.
    - The adapter persists the six columns, with a round-trip test for each.
    - `list_notices_sending()` became `list_notices_in(state)`.
  - **Manual checks.**
    - The pass criteria mention the bot, check `mode: session`, restart before the third mention, and add an outsider check.
    - The Slack bot must be an internal, undistributed app.
    - The trust edges are observed and recorded with recipes, and are not pass criteria.
  - **Watch read failure.** It writes `failed` and `mention_notice_at` only while `mention_notice` is NULL. The sweep re-checks each notice field against its own state and claim time.
  - **Defensive wordings.** They are tested directly in `test_chat_close_rules.py`, with no pragma.
  - **Expiry.** The `RUN_EXPIRED` record ranks with the signals and reads `Run expired`.
  - **Closing text.** Newlines in `author` collapse to one space before the 200 cut. An `answer` at a `checkpoint` stop reads `rejected`.
  - **The close pass.** An unlocked pre-check comes first, and the open-thread list has its own `try`. Rows "Not ended, cheap" and "List fails" were added.
  - **The watch.**
    - The Intent wording is aligned to `closed_at`.
    - The starvation of older threads is stated and accepted.
    - The watch is skipped after a read-pass `ChatError`, through an additive `bool` return from 4-3's `read_replies`.
  - **Migration.** The named and cross-column CHECKs were added. Threads closed before the migration get no notice and no watch.
  - Item 13 skipped as instructed.
- 2026-11-03, built at `184e896` (dispatch facts from the lead):
  - **One close point.** 4-1's `close_thread` is now the only close write, used by 4-1's winner, 4-3's gone-thread close and this story's close pass. It writes `closed_at` and `close_notice` itself, so the "edit `apply_reply_batch`" task is done there. It is the same declared behaviour change. It now returns the closed thread.
  - **A gone root owes no notice.** A close with `error` (4-3's deleted root) writes `close_notice` NULL. A reply to a deleted root always fails, and its `ChatError` would end the closing-notice pass for the Project in that fire.
  - **The backlog cap** counts each notice that reached `reply`, posted or failed. A notice abandoned at the claim does not count.
  - **A `ChatError` on a watch notice's reply** ends the watch pass for the Project in that fire, as on a read (Design Notes, Load).
  - **Fakes.** `tests/unit/fakes/chat_thread.py` gained the three lists. No other fake changed.
  - **Existing tests revised under rule 1(b), citing "story 4-2, 2026-11-03".** No 4-1 test pinned the whole closed-thread row. These five tests pinned what 4-2 declares changed:
    - `test_chat_repository_adapter.py`: the thread table's column and nullable sets, its CHECK set, and the 0029 migration's columns compared to the model's. Each now adds 4-2's six columns or four CHECKs. `test_chat_repository_close.py` pins them.
    - `test_chat_read.py::test_a_reply_from_an_allowed_person_answers_the_stop_and_is_logged`: the same fire now also has the watch's read from `c1`.
    - `test_chat_remind.py::test_a_run_that_moved_to_another_stop_is_not_reminded` and `::test_a_locked_or_moving_run_is_not_reminded[status running]`: the ended stop's thread now gets its closing notice, and still no reminder.
