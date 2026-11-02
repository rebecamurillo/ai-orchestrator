---
title: 'Escalation thread and reminders'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: 'd016040'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Run that stops for a human tells no one in the team's channel. The Operator learns of it only from the Run page or the instance webhook (CAP-11, AD-25).

**Approach:** Add the `chat_thread` table and `chat_poll`, the job 4-1 and 4-3 build on. Each fire runs three passes for each Project with a channel, through the `ChatChannel` port alone:
- **Post:** one thread per stop, with composed context and mentions.
- **Remind:** a mentioning reply in the thread every `CHAT_REMINDER_HOURS` while the Run stays at that stop.
- **Notice:** one line with no mention when the senior accepts test edits.

The Run page shows the stop's thread state and error.

## Boundaries & Constraints

**Always:**
- **Base.** 3-3 builds on 3-2's landed commits: `infrastructure/chat/http.py`, `SlackChannel`, and 3-2's review fixes. Those fixes are 3-2's and are not repeated here:
  - one redact-then-cut helper in `http.py` for both adapters;
  - Slack refuses a non-https `base_url`;
  - user ids and handles are validated when mentions are rendered (Slack `^[A-Z0-9]+$`, Mattermost `^[a-z0-9._-]+$`);
  - `unfurl_links` and `unfurl_media` are false;
  - `auth.test` requires `bot_id`.
- **One backend process.** This is an invariant. `created_at`, `started_at` and "now" all come from the `Clock` port, never from the database's `now()`.
- **Post protocol.** A post has three steps, and the platform call happens outside any transaction:
  1. *Claim.* One unit of work:
     - runs `runs.get_for_update(run_id)` and re-checks that the stop is due;
     - reads the stop's facts (`chat_facts.py`);
     - calls `threads.add(ChatThread(state="posting", ref=None, …))`;
     - and commits.

     `add` is `INSERT … ON CONFLICT DO NOTHING` with no conflict target, and returns `rowcount == 1`. `False`, or a thread that `get_by_stop` already finds, means another fire owns the post, so this fire does nothing.
  2. *Compose and post.* `compose_stop` runs after the commit. `channel.post(text, mentions)` then runs with no unit of work open.
  3. *Record.* One unit of work calls `threads.get_for_update(id)`. If the row is still `posting`, it becomes `open` with `ref` set. Otherwise nothing is written and `chat post outcome dropped` is logged.

  A `ChatError` makes the row `failed`, with `error` set to its detail. Any other exception, in composing or posting, gives `error = "internal: {Class}"`. The token is also masked in the application: `detail.replace(token, "***") if token else detail`, with no infrastructure import. Nothing is reposted (hard rule 7). A failed post changes neither the Run nor any status (AD-8).
- **No transaction across a platform call.** Every database read sits inside a `with uow:` block that closes before any `post` or `reply`.
- **Stale `posting` rows.** At the start of every fire, a sweep over `threads.list_by_state("posting")` fails the stale rows under `get_for_update`.
  - A row is stale when it was created before `ports.started_at` (this process's start) or more than `POSTING_STALE_MINUTES` (10) ago.
  - Its error is `post interrupted; not reposted; a thread may exist and is not read`.
  - Newer rows belong to a post still in flight and are left alone.
- **Post pass.** It covers every Run of the Project with `status == needs_you`.
  - **Due.** `park_kind` is not `paused`, neither `senior_session` nor `terminal_session` is set, and `get_by_stop(run.id, run.park_seq)` is `None`. The claim re-checks all of this under the Run lock, and stores `park_seq`, `park_kind`, `provider` and `channel_id` as they are at posting.
  - **Mentions.** `mentions` is `allowed_users`, in stored order, and each adapter renders its own syntax.
  - **Unopened channel.** When the Project's channel cannot be opened, the pass still claims each due stop, as `failed`. Decryption and `factory.open` each fail this way, and the error is `channel could not be opened: {Class}`, or the redacted `ChatError` detail when `open` raised one. The remind and notice passes are skipped for that Project.
- **Message.** `rules/chat_message.py::compose_stop(facts, metadata_only)` is pure. It writes one fact per line, in this order, and leaves out a line whose fact is missing:
  1. Headline: `Run needs you · {project} / {repository} · {park_kind} · stop {park_seq}`.
  2. `Initiative: {folder}`, where folder is `inputs.spec_folder` or else `initiative_folder`, as `Header.folder` reads it.
  3. `Epic: {n}`: the epic's position, the index of `epic_frame(park_path)` plus 1.
  4. `Story: {park_row.story_id}`.
  5. `Row: {park_row.label}`.
  6. `Question: …`.
  7. `Senior's view: …`.
  8. `Earlier answers in this story:`, then one `- {who}: {text}` line per answer.
  9. The action line.
  10. `Run: {PUBLIC_BASE_URL}/workflows/{run_id}`, left out when `PUBLIC_BASE_URL` is blank.
- **Question and senior's view.** A consult entry belongs to the stop when it sits on `park_row`, or on the row whose entry's `park_path` equals `run.park_path`, under `consults[run.park_kind]`, with `state` set to `escalate` or `failed`. When such an entry exists and `park_reason` starts with `"{question} · "`, the question is the entry's `question` and the senior's view is the rest of the reason. Otherwise the question is `park_reason` and no senior's view line is written.
- **Earlier answers.** These are the gate records with event `answer` or `senior_answer` whose `path` is inside `story_frame(park_path)`, oldest first, showing at most the last 3.
  - `who` is `Operator` for actor `operator` or `terminal`, and `Senior` for `senior`. 4-1 adds `chat`, and with it the `{author} via {platform}` branch.
  - `text` is `payload.text` for `answer` and `record.text` for `senior_answer`.
- **Untrusted text.** The question, the senior's view, each answer, and the notice's files and reason are untrusted. Before they are placed, every `Cc` character except `\n` is dropped, as are the bidi controls U+202A–U+202E and U+2066–U+2069. Every continuation line of such a field is then prefixed with `  › `, so untrusted text never starts a line, fence, heading or quote.
- **Action line.** Both posts and reminders choose it from `thread.park_kind`. At a `blocked` stop it reads `Reply in this thread and mention the bot to answer. The first allowed reply resumes the agent.` At every other stop it reads `Act on the Run page.`
- **Length.**
  - **Field caps.** Folder, story id, label, project and repository are cut to 200 code points each, the question to 1,500, the senior's view to 600, and each answer to 200.
  - **Total.** If the text still exceeds `MAX_POST_CHARS` (3,000 code points), it is cut in this order until it fits:
    1. whole answer lines, oldest first;
    2. the senior's view, from its end;
    3. the question, from its end.
  - **Marker.** The marker `… (cut; the Run page has the rest)` appears once, on its own line, before the action line. The action line and the Run link always stay.
- **`metadata_only`** keeps lines 1 to 5, 9 and 10. It leaves out the question, the senior's view and the earlier answers.
- **Remind pass.** It covers `threads.list_open_for_project(project_id)`.
  - **Skipped.** A thread whose `provider` or `channel_id` differs from the channel this fire opened.
  - **Due.** Its Run is `needs_you` at `park_seq == thread.park_seq` with neither lock flag set, and `now - (last_reminded_at or created_at) >= CHAT_REMINDER_HOURS`.
  - **Claim.** It locks the Run, then the thread (4-1's order), re-checks that the thread is due, sets `last_reminded_at = now` and commits.
  - **Reply.** It then runs outside any transaction, as `reply(ref, text, mentions=allowed_users)`. The text is `Still waiting · {thread.park_kind} · stop {park_seq} · parked {h} h`, then the action line and the Run link.
  - **Failure.** A failure logs `chat reminder failed` with the ids and `error_class`. It is not stored, `last_reminded_at` stays set, and nothing is retried.
- **Notice pass.**
  - **Selection.** `notices.unposted_accepts(project_id, since=channel.created_at)` is an anti-join: every `senior_accept` gate record on the Project's Runs with `at >= since` and no `chat_notice` row. It has no Run status filter.
  - **Claim and post.** The claim is `notices.add(ChatNotice(gate_record_id, run_id, created_at))`, returning `False` on conflict, and it is committed before `post(line, mentions=())`. The post is a channel post, not a thread. On failure, the notice's `error` is written. There is no state machine and no sweep.
  - **Line.** `{project} / {repository} · story {story_id} · the senior accepted test edits: {files} · {reason} · {link}`.
    - `files` lists at most 10 names, then `and {n} more`.
    - `reason` is cut to 600 code points.
    - The untrusted-text rules apply, and the line is at most `MAX_POST_CHARS`.
    - Under `metadata_only` the line reads `… · the senior accepted test edits to {n} files · {link}`.
- **Isolation.**
  - Each fire is skipped when the job finds no chat factory in its slot, because `serving` has exited at shutdown.
  - Per fire, `crypto()` and `channels.list_all()` run inside one `try`.
  - Per Project, token decryption, `factory.open` (once per fire) and the three passes run inside one `try`.
  - Per Run, thread or notice, each claim, post or reply runs inside its own `try`.
  - An exception at any level is logged with ids and `error_class` only, and the job moves on. Nothing raises out of `run_chat_poll`.
- **Logging in 3-3's passes.** Ids, `park_seq`, `state` and `error_class` only, never a token, message text or error detail. The detail lives only in `chat_thread.error` and `chat_notice.error`. 4-3's read pass keeps its own rule.
- **Adapters and port** (D1, D2).
  - **Port.**
    - `ChatChannel.reply` becomes `reply(thread, text, mentions: Sequence[ChatUser] = ())`, and each adapter renders the mentions as it does for `post`.
    - The port doc gains: "An adapter delivers text as one message or raises `ChatError`; it never splits."
    - `SlackChannel.post` and `reply` raise `ChatError("text too long after escaping: {n}")` when the escaped text plus mentions exceeds 4,000 characters.
  - **Mattermost neutralisation** (D1). `MattermostChannel` inserts U+2060 after every `@` in `text` that is not preceded by a word character, and backslash-escapes `[` and `]`. The adapter's own mention prefix is built separately, and a mention handle of `channel`, `here` or `all` raises `ChatError`.
  - **Slack.** It needs tests only: `<!channel>`, `<!here>`, `<!everyone>`, `<!subteam^S1>` and `<https://x|y>` arrive escaped, and neither `link_names` nor `parse` is sent.
  - **Fake.** `FakeChatChannel.replies` keeps its shape and gains a parallel `reply_mentions` list. An optional `on_send` hook runs at the start of `post` and `reply`.
- **Run page.** `Alert.chat_thread` is `{provider, state, error}` for `get_by_stop(run.id, run.park_seq)`, or `None` when there is no thread. It is set whatever the thread's state.

**Never:**
- No reading of replies, no `cursor` write, no answer (4-1, 4-3).
- No close at the end of a stop and no closing notice (4-2). A thread whose Run has left its stop is left `open` and unreminded, for 4-2 to close.
- No platform syntax in `application/` (AD-25). Edits to `infrastructure/chat/` are limited to D1's neutralisation and D2's reply mentions. D1 includes L9's handle refusal, and the edits also cover M6's Slack length refusal, which the review requires.
- No status write and no gate record (AD-8). No change to `Notifier`. No automatic repost.
- No live platform in any test. No container is stopped (hard rule 9).

**Decided (lead review, 2026-11-02):**
- **The Run lock serialises the claim.** The unique insert is the backstop, so two fires never both post. The 10-minute staleness rule keeps an overlapping fire from failing a post that is still in flight.
- **`paused` and locked stops do not post.** The Operator caused the pause, or is already at the Run, and 4-1 would refuse a reply there as `locked`. A stop that becomes due again later, because a lock cleared at the same `park_seq`, posts then.
- **One thread per `park_seq`, for good.**
  - A channel switched after posting does not repost the stop, and a thread on the old channel is not reminded.
  - A `budget` stop that becomes `blocked` at the same `park_seq` keeps its thread and its `budget` copy.
  - A stop claimed `failed` stays failed after the channel is fixed.
- **The senior's test-edit line is a channel post, not a thread.** No human stop exists, since the Run stays `running` and no `park_seq` is spent. A thread would invite replies that nothing reads.
- **Reuse `PUBLIC_BASE_URL`** (AD-20, already in `Settings` and `.env.example`), with `notify/format.py::run_url`'s path `/workflows/{id}`.
- **D1.** `props.disable_group_highlight` does not suppress notifications, so Mattermost neutralises mentions in the text instead.
- **D2.** Reminders mention `allowed_users`.
- **D3.** Reminder failures are logged, not stored, because 4-3 owns `error` on an open thread.
- **D4.** `chat_notice` is trimmed to a claim row.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected |
|---|---|---|
| Blocked stop | Run `needs_you`, `blocked`, stop 3, two allowed users | one `post` with both users; thread `open` with `ref`; lines in the pinned order; reply invitation |
| Other stop | `checkpoint`, `budget`, `dependency` (no row) | posted; `Act on the Run page.`; a `dependency` stop has no Row line |
| Senior escalated | entry `escalate`, reason `"Q · senior: needs a product call"` | `Question: Q`, then `Senior's view: senior: needs a product call` |
| Earlier answers | 5 answers in the story frame (operator, terminal, senior), 1 outside it | the last 3 from the frame, oldest first, labelled `Operator` or `Senior` |
| Hostile text | a question holding `\n# h`, a code fence, `> q`, `@channel`, U+202E, NUL, `\t` | controls dropped; every continuation line starts `  › `; no line starts with `#`, a fence or `>` |
| Metadata only | `metadata_only: true` | no Question, Senior's view or answers line; the fixture question text appears nowhere |
| Long text | a fixture exactly `MAX_POST_CHARS + 1` long; a 10,000-character question | ≤ 3,000 code points; cut in the pinned order; one marker line before the action line; action line and link present |
| No base URL | `PUBLIC_BASE_URL=` | no `Run:` line |
| Overlap | the fake's `post` runs a second fire before it returns | one `post`; one row |
| Post fails | `ChatError("403 … tok-x …")` | row `failed`; `error` has `***` and not the token; the next fire does not post |
| Unexpected | `post` raises `ValueError` | row `failed`, `internal: ValueError` |
| Restart | `posting` row created before `started_at` | `failed` with the interrupted copy; no `post` |
| In flight | `posting` row 2 min old, same process | untouched |
| Paused or locked | `paused`, or `senior_session` | no post |
| Reminder due | open thread created 4 h ago, Run at its stop | one `reply` mentioning `allowed_users`; `last_reminded_at = now` |
| Reminder overlap | two fires both see it due | one `reply` |
| Not due | 3 h 59 min; Run moved to stop 4; thread `failed` | no reply |
| Channel switched | thread on another `channel_id` or provider | no reply |
| Reminder copy | thread posted at `budget`; Run now `blocked` at the same stop | headline `budget`; `Act on the Run page.` |
| Reminder fails | `ChatError` on `reply` | one `chat reminder failed` line; nothing stored; `last_reminded_at` stays set |
| Senior accept | `senior_accept` record; the Run has already ended | one channel `post` with no mentions; a second fire posts nothing |
| Long accept | 14 files, 900-character reason | 10 names and `and 4 more`; reason cut to 600 |
| Old accept | record from before `channel.created_at` | not posted |
| Project isolation | A's token cannot be decrypted, A has one due stop; B is fine | A's stop `failed`, `channel could not be opened: DecryptionError`; B posts; one line names A |
| No transaction | the fake's `on_send` hook checks the fake unit of work | no unit of work is open during any `post` or `reply` |
| Shutdown | the chat slot is empty | the fire does nothing |
| Log hygiene | token, question text and error detail in the fixtures | absent from every captured line of 3-3's passes |
| Run page | thread `failed` with an error; `open`; none | `alert.chat_thread` has the state and error; `null` when there is none |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/entities/chat_thread.py` (new) -- `ChatThreadState` and `ChatThread`, as in 4-1's contract, and `ChatNotice{gate_record_id, run_id, created_at, error}`.
- `domain/ports/chat.py` -- `reply` gains `mentions`, plus the "never splits" doc line (D2, M6).
- `domain/ports/repositories.py`:
  - `ChatThreadRepository{add -> bool, get, get_for_update, get_by_stop(run_id, park_seq), list_open_for_project(project_id), list_by_state(state), update}`. The two lists return the oldest first.
  - `ChatNoticeRepository{add -> bool, unposted_accepts(project_id, since) -> list[GateRecord], set_error(gate_record_id, error)}`.
  - `ProjectChannelRepository` gains `list_all()`, ordered by `project_id`.
- `infrastructure/db/models/chat.py`, `infrastructure/db/repositories/chat.py` (new), plus `alembic/versions/{head+1}_chat_thread.py`. `chat_thread` follows 4-1's contract. `chat_notice` has `gate_record_id` as its PK, an FK to `gate_record`, and `run_id` as an FK to `run`, both `ON DELETE CASCADE`, with only `error` nullable. Also add the `list_all` adapter for project channels.
- `infrastructure/db/chat.py` (new) -- `open_chat_ports(session_factory, notifier) -> ChatPorts{writers, threads, channels, notices, projects, repositories}`, all on one session.
- `infrastructure/chat/mattermost.py`, `slack.py` -- D1's neutralisation, the handle refusal, D2's reply mentions, and M6's Slack length refusal. Nothing else.
- `application/rules/chat_message.py` (new, pure) -- `StopFacts`, `neutralise`, `compose_stop`, `reminder_text`, `accept_line`, `MAX_POST_CHARS`, and the caps.
- `application/jobs/chat_facts.py` (new) -- `stop_facts(chat, run)`, called inside the claim.
- `application/jobs/chat_post.py`, `chat_remind.py`, `chat_notice.py` (new) -- one module per pass, plus the stale sweep in `chat_post.py`.
- `application/jobs/chat_poll.py` (new) -- `ChatPollPorts{chat, factory, crypto: Callable[[], Crypto], clock, public_base_url, reminder_hours, started_at}` and `run_chat_poll`. The passes run in the order sweep, post, remind, notice. 4-3 appends the read pass and adds `signal`.
- `infrastructure/settings.py`:
  - `chat_poll_seconds: int = 30`, with a validator that refuses start-up outside `{10, 12, 15, 20, 30}`.
  - `chat_reminder_hours: int`, `ge=1`, default 4.
- `.env.example` and `deploy/.env.example` -- uncommented `CHAT_POLL_SECONDS=30` and `CHAT_REMINDER_HOURS=4`, each with a trailing comment. `scripts/check_env_contract.py` skips `#` lines.
- `infrastructure/terminal_jobs.py` -- `engine_jobs(…, chat: ChatChannelFactory | None = None)` adds `("chat_poll", f"*/{s} * * * * *", job)` only when `chat` is given. `started_at` is taken from the `Clock` when the job is built. The job reads the slot on every fire.
- `infrastructure/dbos/startup.py` -- `serving(…, chat=None)` keeps `chat` in a module slot that is cleared on exit. `_SERVING`'s three-tuple and its loops are unchanged.
- `main.py` -- passes the `ChatChannels()` it already builds and closes, as `serving(engine, session_factory, git, chat=chat)`.
- `application/use_cases/run_view_types.py`, `run_views.py`, `run_views_alert.py`:
  - `Alert.chat_thread: ChatThreadNote | None = None`.
  - `RunViewPorts.chat_threads: ChatThreadRepository | None = None`.
  - `build_alert(…, thread=None)`.
- `api/schemas/run_alert.py` -- `ChatThreadOut{provider, state, error}`, plus `AlertOut.chat_thread` with `_drop_default`.
- `api/providers.py` -- wires `chat_threads`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- through `make openapi` only.
- `web-client/src/lib/run/chat.ts` (new) -- `chatThreadText(thread)`:
  - `posting` reads `posting the thread to {provider}`.
  - `open` reads `thread posted to {provider}`.
  - `failed` reads `thread post failed; not retried`.
  - `closed` reads `thread closed`.
- `web-client/src/components/run/ChatThreadLine.tsx` (new) -- a neutral line, `data-testid="wf-chat-thread"` with `data-state`, plus `data-testid="wf-chat-thread-error"` holding `error` verbatim. `Banner.tsx` renders it as the next sibling of the `wf-alert` aside, in a fragment, on the alert branch only, when `detail.alert?.chat_thread` is set.

## Tasks & Acceptance

**Execution:**
- [x] Shared fakes:
  - `tests/unit/fakes/chat_thread.py` holds `FakeChatThreadRepository` (`get_for_update` returns `get`, and `add` honours both unique keys) and `FakeChatNoticeRepository`.
  - `list_all` is added to 3-4's `FakeProjectChannelRepository`.
  - `reply_mentions` and `on_send` are added to `FakeChatChannel`, so `test_chat_fake.py` needs no revision.
- [x] New tests, each seen failing first, covering every matrix row through the shared fakes, `FakeCrypto` and `FakeClock`:
  - `tests/unit/application/test_chat_message.py` (including the exact-length cut)
  - `test_chat_post.py`, `test_chat_remind.py`, `test_chat_notice.py` and `test_chat_poll.py` (isolation, order, `on_send` transaction check, log hygiene with `structlog.testing.capture_logs`)
  - `tests/unit/test_chat_repository_adapter.py`: the compiled SQL is `ON CONFLICT DO NOTHING` with no target, `add` returns `rowcount == 1`, and the anti-join is covered
  - `test_chat_poll_registration.py`, `test_settings_chat.py` (11 refused, blank gives 30) and `test_run_alert_chat_thread.py`
  - `test_mattermost_neutralise.py` and `test_slack_neutralise.py`, plus reply-mention and length-refusal cases in each
  - `web-client/tests/unit/run-chat-thread.test.ts`
  - `web-client/tests/e2e/run-detail-chat-thread.spec.ts`, against a stubbed backend: a `failed` thread shows `wf-chat-thread-error` right after `wf-alert`
- [x] Code Map in order, then `make openapi`. No existing test changes. `test_terminal_poll_wiring.py` still sees only `terminal_poll`, because its calls pass no `chat`.

**Acceptance Criteria:**
- Given one parked stop and a fake `post` that runs a second fire before it returns, when both finish, then `FakeChatChannel.posts` holds exactly one post and the table holds one row.
- Given a `posting` row and a backend restart, when the next fire runs, then the row is `failed` and nothing is posted.
- Given a stop thread that failed with `403 bot not in channel`, when `GET /runs/{id}` is read, then `alert.chat_thread` is `{state: "failed", error: "403 bot not in channel"}`, and the Run page shows that error.
- Given an open thread and a Run still parked at its stop, when the fake clock passes 4 h, then one mentioning reminder is posted, and none more until 8 h.

## Design Notes

- **Limits, verified 2026-11-02.**
  - Mattermost refuses a post longer than the server's `maxPostSize` with `model.post.is_valid.message_length.app_error`. That size is 16,383 runes on current schemas and 4,000 on old ones ([post.go](https://raw.githubusercontent.com/mattermost/mattermost/master/server/public/model/post.go)).
  - Slack's [`chat.postMessage`](https://docs.slack.dev/reference/methods/chat.postMessage) recommends at most 4,000 characters for `text`, and may split longer `text` into several messages. A split root would break the thread, so `SlackChannel` refuses past 4,000 after escaping, rather than relying on the application's cap.
- **Questions for the lead:**
  1. **`ChatPorts` gains three fields:** `notices`, `projects` and `repositories`, beside 4-1's `{writers, threads, channels}`. The change is additive, and 4-1 and 4-3 use only the original three.
  2. **`ChatThreadRepository.add -> bool`** is additive to 4-1's "at least" list.
- **Proposed AD-25 amendment**, for the Operator to ratify:
  > `reply(thread, text, mentions=())` renders mentions as `post` does; an adapter delivers text as one message or raises `ChatError`, never splits. `chat_notice(gate_record_id, run_id, created_at, error)` holds the one-line channel post for a `senior_accept`, claimed by its primary key, posted once, never reposted. Reminders mention the allowed people. One backend process; thread times come from the `Clock` port.
- **Proposed addendum from implementation**, for the Operator to ratify with the amendment above:
  > `ChatPorts` and `ChatPollPorts` live in `application/jobs/chat_ports.py` (`chat_poll.py` re-exports `ChatPollPorts`), with `notices`, `projects` and `repositories` required beside 4-1's three. The chat factory `serving` holds sits in `infrastructure/terminal_jobs.py::CHAT_SLOT`, which `chat_poll` reads on every fire. Mattermost refuses a mention whose handle is `channel`, `here` or `all`; Slack refuses a message longer than 4,000 characters after escaping.
- **Implementation decisions (2026-11-02, dev):**
  - The cut marker is written when anything was cut, a field cap included, so a 10,000-character question shows it even when the capped text fits.
  - A senior-accept line with no row `story_id` leaves out `· story {id}`; with no Run link it leaves out `· {link}`.
  - `parked {h} h` counts whole hours since the thread's `created_at`, the post, which is within one poll of the park.
  - When `factory.open` raises `ChatError`, the claimed row's `error` is the redacted detail alone; any other exception gives `channel could not be opened: {Class}`.
  - Due stops are posted oldest Run first. The pass pre-checks `get_by_stop` without a lock, so a stop that has its thread takes no Run lock each fire; the claim re-checks under the lock.
  - The remind pass pre-checks the period from the thread alone before locking, for the same reason.
  - `FakeUnitOfWork` gains a read-only `is_open`, which the `on_send` checks use.
- **No `DBOS_APPLICATION_VERSION` bump.** A new schedule is not a change to the walker's sequence. Before 4-3, a recovered scheduled fire re-runs the job, and the database claims keep posting at most once.
- **Shutdown window.** A fire already running when `ChatChannels.close()` is called can fail its posts as `internal: {Class}`. Only fires that start after `serving` exits are skipped.

## Verification

**Commands:**
- `make lint`, `make test` -- green. Domain and application are at 100% branch coverage, every new module is paired with a test, and both env contracts match `Settings`.
- `make openapi` -- no drift afterwards.
- `make e2e` -- green, on the disposable stack only.
- `make e2e-ui` -- green with the new spec. Bind another port if 4321 is held (hard rule 9).

**Manual checks (done checkpoint):** the Operator runs the Projects page connection test with a real bot token, on Mattermost and on Slack, to check bot-token auth and host reachability (spine open item 8). Optional: park a fixture Run, see one thread with the expected mentions, and see a reminder after setting `CHAT_REMINDER_HOURS=1`.

## Spec Change Log

- 2026-11-02, written from `stories.yaml` 3-3, CAP-11, AD-8, AD-24 and AD-25 with its amendments, and the 3-1, 3-2, 3-4, 4-1 and 4-3 story files. The 4-1 and 4-3 contract is delivered unchanged.
- 2026-11-02, lead review. Approved with changes, all applied:
  - **High:** remind skips threads off the current channel (H1); untrusted text is neutralised (H2); the env lines go in both contracts (H3).
  - **Medium:**
    - facts are read inside the claim (M1);
    - an unopened channel claims due stops `failed` (M2);
    - the notice anti-join has no status filter (M3);
    - notice caps (M4);
    - no `chat` actor before 4-1 (M5);
    - "never splits" and Slack's 4,000 refusal (M6);
    - one process with `Clock` times (M7);
    - reminder copy from `thread.park_kind` (M8);
    - `reply_mentions` (M9);
    - the baseline is 3-2's last commit (M10).
  - **Low:** field caps and cut order (L1), transaction hook (L2), interleaved overlap and `ON CONFLICT` test (L3), guarded token replace (L4), shutdown skip (L5), log scope (L6), interrupted copy (L7), line placement (L8), refused handles (L9), epic position (L10).
  - **Decided:** D1 to D4 resolved the earlier questions 1 to 4. The AD-25 amendment text was revised.
