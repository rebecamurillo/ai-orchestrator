---
title: 'Chat port and Mattermost adapter'
type: 'feature'
created: '2026-11-02'
status: 'ready-for-dev'
route: 'dispatch'
baseline_commit: '8c2a6beb6278c1e5f853467e9d60d21840595291'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Stories 3-2, 3-3, 3-4 and 4-1 need one chat port, a fake of it, and a working Mattermost adapter (CAP-10, AD-25).

**Approach:** Add `domain/ports/chat.py`, the shared fake, and `infrastructure/chat/mattermost.py` over httpx with an `open_channel` factory. Nothing calls them yet. 3-4 stores the channel, 3-5 adds the form, 3-2 adds Slack.

## Boundaries & Constraints

**Always:** Only `infrastructure/chat/` calls a chat platform. The token is a constructor argument, sent only as `Authorization: Bearer` to the configured host. It is never logged, and every `ChatError` detail goes through `infrastructure/redact.py::redact(detail, token)`. Redirects are not followed, so a 3xx is a `ChatError` and the bearer never reaches another host. A failure raises `ChatError` with the platform's own text, with no retry (hard rule 7). The adapter logs nothing.

**Never:** No table, migration, API, setting, job or UI (3-3, 3-4, 3-5, 4-1). No Slack (3-2). No edit to `main.py` or any existing test. No live Mattermost in any test.

**Decided (lead review, 2026-11-02):**
- **Thread read pages explicitly.** In the server source, `perPage=0` returns the whole thread "for now", with a comment that it will become `PerPageDefault` (60) after the next ESR (`server/channels/api4/post.go::getPostThread`). The adapter therefore sends `perPage=200` (the server's `PerPageMaximum`) and `direction=down`, plus `fromCreateAt` and `fromPost` when a cursor is held. It repeats while `has_next` is true. The store applies `CreateAt > from OR (CreateAt = from AND Id > fromPost)`, ordered `CreateAt, Id ASC` (`sqlstore/post_store.go::Get`). Without `direction` the order is undefined.
- **`Reply` carries `cursor`.** It is the adapter's opaque position just after that reply: Mattermost `"{create_at}:{id}"`, Slack its `ts`. It is a position, not an id, so a deleted reply cannot strand a thread. AD-25 gains this field. The exact text is in the Spec Change Log.
- **`mentions` are `ChatUser{id, handle}`**, so each adapter renders its own syntax: Mattermost `@handle`, Slack `<@id>`.
- **Live check:** none in this story. "Done" rests on mock-transport tests. The Operator runs the live check at the 3-3 and 4-2 done checkpoints (spine open item 8, amended).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error |
|---|---|---|---|
| Probe ok | `/users/me` 200, channel member 200 | returns `username` | N/A |
| Probe refused | 401 / bot not in channel 403·404 | nothing cached | `ChatError("401 <AppError.message>")` |
| Post | text, two users | `POST /posts {channel_id, message: "@a @b\n<text>"}` → `ThreadRef(id)` | non-2xx → `ChatError` |
| Reply | thread, text | `POST /posts` with `root_id` | as above |
| Replies, first read | cursor `None`, 2 pages | every reply oldest first, without the root or the bot's own posts | N/A |
| Replies, after cursor | `"1700:abc"` | query carries `fromCreateAt=1700&fromPost=abc` | malformed cursor → `ChatError` |
| Host down | `httpx.ConnectError` | N/A | `ChatError("ConnectError: …")` |
| Not JSON / missing key | 200 with HTML | N/A | `ChatError("unexpected response from <path>")` |
| Token echoed | the error body contains the token | N/A | detail shows `***` |
| Redirect | 302 | not followed | `ChatError("302 …")` |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/`.

- `domain/ports/chat.py` (new):
  - `ChatProvider = Literal["mattermost", "slack"]`, `ChatUser{id, handle}`, `ThreadRef{id}`, `Reply{id, author_id, mentions_bot, text, cursor}`, and `ChatError(Exception)` with `.detail`.
  - `ChatChannel` Protocol: `post(text, mentions: Sequence[ChatUser]) -> ThreadRef`, `reply(thread, text) -> None`, `replies_since(thread, cursor: str | None) -> list[Reply]`, `probe() -> str` (the bot's handle, without `@`).
  - `ChatChannelFactory` Protocol: `open(provider, base_url, channel_id, token) -> ChatChannel`.
- `infrastructure/chat/mattermost.py` (new) -- `MattermostChannel(base_url, channel_id, token, client: httpx.Client | None = None)`. The base URL loses its trailing `/`. Timeout 10 s, `follow_redirects=False`, `client` injectable as in `notify/webhook.py`. `/users/me` is read once and cached for the bot's id and username. `probe` reads `GET /api/v4/users/me`, then `GET /api/v4/channels/{channel_id}/members/{me.id}`. `replies_since` reads `GET /api/v4/posts/{id}/thread` as Decided, walks `order`, and drops the root, the bot's posts and anything at or before the cursor. Non-2xx gives `"<status> <AppError.message>"`, or the body cut to 300 characters when it is not an AppError. `httpx.HTTPError` gives `"<ErrorType>: <str>"`.
- `infrastructure/chat/mentions.py` (new, pure) -- `mentions_bot(text, username)`: `@username`, case-insensitive. The next character must not be one of `[a-z0-9_-]`, and must not be a `.` followed by such a character, so `@bot.` at the end of a sentence counts and `@bot.ops` does not. 3-2 reuses the module for Slack's `<@id>` form.
- `infrastructure/chat/__init__.py` (new) -- `open_channel(provider, base_url, channel_id, token) -> ChatChannel`, matching `ChatChannelFactory`. `"slack"` raises `ChatError("slack is not available yet")` until 3-2.

## Tasks & Acceptance

**Execution:**
- [ ] `backend-api/tests/unit/fakes/chat.py` -- `FakeChatChannel`: records `posts` and `replies`, holds scripted replies per thread honouring `cursor`, a scripted `probe` result, and an optional `ChatError` raised by the next call. `FakeChatChannelFactory`: records each `open` and returns the fake. These are the shared fakes for 3-3, 3-4 and 4-1 (AD-18).
- [ ] New tests, each seen failing first: `tests/unit/test_mattermost_adapter.py` (`httpx.MockTransport` as in `test_notify_webhook.py`: every matrix row, request paths and query, bearer, bodies, two-page paging, and no token in any `ChatError`), `test_chat_mentions.py`, `test_chat_factory.py`, and `test_chat_fake.py` (the fake honours the port).
- [ ] Port, then mentions, then adapter, then factory.

**Acceptance Criteria:**
- Given a token that appears in the error body, when any call fails, then `ChatError.detail` holds `***` and not the token.
- Given a thread of 250 replies with the cursor at reply 100, when `replies_since` runs, then it makes two thread requests and returns replies 101 to 250 in order.
- Given `"thanks @Bot."`, `"@bot.ops"` and `"@botty"` with bot `bot`, when `mentions_bot` runs, then only the first is true.

## Design Notes

API facts, verified 2026-11-02:
- Bearer auth, with bot tokens used the same way: [intro](https://raw.githubusercontent.com/mattermost/mattermost/master/api/v4/source/introduction.yaml), [bot accounts](https://docs.mattermost.com/developers/integrate/reference/bot-accounts).
- `POST /api/v4/posts {channel_id, message, root_id?}` answers 201: [posts.yaml](https://raw.githubusercontent.com/mattermost/mattermost/master/api/v4/source/posts.yaml).
- The thread read answers `PostList{order, posts, has_next}` with `Post{id, create_at, user_id, root_id, message}`. Its paging is from the server source cited under Decided.
- `GET /users/me` and `GET /channels/{id}/members/{user_id}` need `read_channel`: [users.yaml](https://raw.githubusercontent.com/mattermost/mattermost/master/api/v4/source/users.yaml), [channels.yaml](https://raw.githubusercontent.com/mattermost/mattermost/master/api/v4/source/channels.yaml).
- Errors are `AppError{id, message, request_id, status_code}`. A username is 3 to 22 characters of `[a-z0-9._-]` and starts with a letter.

## Verification

**Commands:**
- `make lint` -- green: import-linter, test pairs, 400-line cap.
- `make test` -- green, with domain at 100% branch coverage.

## Spec Change Log

- 2026-11-02, lead review. The draft (port, storage, API and form) was split. The storage and API went to 3-4 and the form to 3-5. The draft's `include_router` into `projects.router` would have broken the frozen `test_projects_router.py::test_the_router_declares_four_operations_and_repeats_no_dependency`, and 3-4 now mounts in `main.py`. Defects fixed:
  - Redaction of every `ChatError`.
  - No redirects.
  - Non-JSON answers mapped to `ChatError`.
  - Explicit thread paging in place of `perPage=0`.
  - Cursors as positions.
  - `ChatUser` mentions, which Slack needs.
- Proposed AD-25 text, for the Operator to ratify: "`Reply{id, author_id, mentions_bot, text, cursor}`, where `cursor` is the adapter's opaque position just after that reply; `replies_since(thread, cursor)` returns, oldest first, the replies after it (`None` = from the start), excluding the root and the bot's own posts; `post` takes `ChatUser{id, handle}` mentions so each adapter renders its own syntax."
- KEEP: the AD-25 method set, httpx with an injectable client, and the cited API facts.
