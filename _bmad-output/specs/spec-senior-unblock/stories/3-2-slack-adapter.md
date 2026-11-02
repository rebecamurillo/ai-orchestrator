---
title: 'Slack adapter'
type: 'feature'
created: '2026-11-02'
status: 'in-progress'
route: 'dispatch'
baseline_commit: '94f0f44f04d7243b4d7241b81e83eadca4afdf8b'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Project can store only a `mattermost` channel. CAP-10 also offers `slack`, and `open_channel("slack", …)` still refuses with `slack is not available yet`.

**Approach:** Add `infrastructure/chat/slack.py`, a `SlackChannel` that fits 3-1's `ChatChannel` port with no port change, open it through `ChatChannels` for `slack`, and let 3-4's schema accept `slack`. Backend only. The form's `slack` option is a later step.

## Boundaries & Constraints

**Always:**
- Only `infrastructure/chat/` calls Slack, over httpx on the client that `ChatChannels` shares. The bot token (`xoxb-…`) is sent only as `Authorization: Bearer`, never as a `token` parameter, and only to the stored `base_url`. Redirects are not followed.
- Every `ChatError` detail is redacted against the token in its raw and escaped forms, as 3-1 does. A token httpx could not send is refused at construction without being echoed. The adapter logs nothing.
- A failure raises `ChatError` with Slack's own error code. Nothing is retried, and a 429 is reported, not waited out (hard rule 7).
- `replies_since` excludes what AD-25's 4-1 amendment excludes: the root, the bot's own posts, and every system, webhook, bot or app post. On Slack that means any message carrying `subtype`, `bot_id`, `bot_profile` or `app_id`, or a `type` other than `message`. It fails closed: a message without a string `user` is not a reply.
- `Reply.body` is `text` with every bot mention removed by the match that sets `mentions_bot`, as the port defines it.

**Never:** No port change, no migration (the `provider` CHECK already holds `slack`), no new setting, no job. No web-client change except what `make openapi` regenerates. No live Slack in any test. No edit to an existing test beyond the three that pin "slack refused" (rule 1(b), below).

**Decided (2026-11-02):**
- **`base_url` is required for `slack`, as for `mattermost`.** The form will pre-fill `https://slack.com/api`. A server-side default would be a per-platform branch in the use case, which AD-25 prevents, and it would make 3-4's host-change rule compare a typed URL with an implied one. Required keeps that rule unchanged, and a GovSlack workspace types `https://slack-gov.com/api`. The adapter appends the method name (`{base_url}/chat.postMessage`), so `base_url` is the Web API root, ending in `/api`.
- **Cursor = the reply's `ts`.** 3-1 already decided this. `replies_since` sends `oldest=<cursor>` and also keeps only messages whose `ts` is greater than the cursor, so a server that ignores `oldest` cannot return a reply twice. A cursor that is not `digits.digits` is a `ChatError`.
- **Paging:** `limit=200`, which is under Slack's recommended page size, then `cursor=<response_metadata.next_cursor>` until it is empty. A repeated `next_cursor` is an unexpected response, and the read stops after 50 pages. The result is sorted by `ts`.
- **Outgoing text is escaped.** `&`, `<` and `>` become `&amp;`, `&lt;` and `&gt;`, Slack's three control characters. Without this, an agent's question containing `<!channel>` or `<@U…>` would ping people. Mentions are added after escaping, as `<@{ChatUser.id}>` separated by spaces and followed by a newline, as Mattermost does.
- **Mentions** are `<@BOTID>`, and also `<@BOTID|label>`, matched exactly, case-sensitively. Fenced code, inline code and quote lines (`>` or `&gt;`) are masked first, as for Mattermost, so a quoted mention never counts.
- **`thread_broadcast` is excluded**, because it carries a `subtype`. A reply posted with *Also send to channel* does not count, which fails closed.
- **Probe:** `auth.test` gives the bot's `user_id` and `user`, cached once both checks pass. `conversations.info` must answer `is_member: true` and not `is_archived`. `probe()` returns `user`.
- **Rate limits (verified 2026-11-02):** the change Slack announced on 2025-05-29 cut `conversations.replies` and `conversations.history` to 1 request a minute and 15 messages a page for commercially distributed non-Marketplace apps. Internal customer-built apps keep Tier 3 (50+ a minute, `limit` up to 1,000). **The bot must therefore be an internal app, created in and installed to the team's own workspace**, with bot scopes `chat:write`, `channels:history` and `channels:read`, plus `groups:history` and `groups:read` for a private channel. The bot must also be invited to the channel.
- **`body` keeps Slack's entities.** `&lt;`, `&gt;`, `&amp;` and other people's `<@U…>` stay as Slack wrote them, because the port defines `body` as `text` minus the bot's mentions and nothing else. Whether 4-1 needs them decoded is for the lead to decide.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error |
|---|---|---|---|
| Probe ok | `auth.test` ok, `conversations.info` `is_member: true` | returns `user`; bot id cached | N/A |
| Probe, bot not in channel | `is_member: false` | nothing cached | `ChatError("conversations.info: the bot is not a member of <id>")` |
| Probe, bad channel | `ok:false, error:"channel_not_found"` | nothing cached | `ChatError("conversations.info: channel_not_found")` |
| Probe, archived | `is_archived: true` | nothing cached | `ChatError("conversations.info: <id> is archived")` |
| Post | text with `<!channel>`, two users | `chat.postMessage {channel, text: "<@U1> <@U2>\n&lt;!channel&gt;"}` → `ThreadRef(ts)` | N/A |
| Reply | thread, text | `chat.postMessage` with `thread_ts` | N/A |
| Replies, first read | cursor `None`, two pages | every reply oldest first, without the root or the bot's posts; the second request carries `cursor` | N/A |
| Replies, after cursor | `"1700000000.000100"` | `oldest` sent; only later `ts` returned, even if the server ignores `oldest` | malformed → `ChatError` |
| Not a person | `subtype` (bot_message, channel_join, thread_broadcast), `bot_id`, `bot_profile`, `app_id`, no `user` | dropped | N/A |
| Mention | `<@BOT> fix it`, `<@BOT\|bot>`, `` `<@BOT>` ``, `&gt; <@BOT>`, `<@BOTX>` | true, true, false, false, false; `body` drops the counted ones | N/A |
| `ok:false` | `{"ok":false,"error":"missing_scope","needed":"chat:write"}` | N/A | `ChatError("chat.postMessage: missing_scope (needed: chat:write)")` |
| 429 | `Retry-After: 30` | one request, not retried | `ChatError("conversations.replies: 429 rate limited, Retry-After 30 s")` |
| Token echoed | an error body contains the token | N/A | detail shows `***` |
| Host down, not JSON, redirect | as 3-1 | N/A | `ChatError` as 3-1 |
| Settings | `PUT` with `provider: slack` and every field | stored; Test opens `SlackChannel` | missing `base_url` → 422 at the field |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `infrastructure/chat/http.py` (new) -- the transport rules both adapters share, moved unchanged out of `mattermost.py`: `new_client`, `TIMEOUT_SECONDS`, `MAX_RESPONSE_BYTES`, `TOKEN_REFUSED`, `sendable`, `redact_token`, and `exchange(client, method, url, token, label, …) -> (status, headers, content)`, which streams, caps and maps transport errors. `mattermost.py` imports them and keeps its public names.
- `infrastructure/chat/slack.py` (new) -- `SlackChannel(base_url, channel_id, token, client=None)`, as Decided.
- `infrastructure/chat/mentions.py` -- `slack_mentions_bot(text, user_id)` and `slack_strip_mentions(text, user_id)`, which reuse the masking.
- `infrastructure/chat/__init__.py` -- `slack` opens `SlackChannel`.
- `api/schemas/project_channel.py` -- `ProviderIn` gains `slack`. `base_url`, `channel_id` and at least one allowed user are required for every provider but `off`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- through `make openapi` only.

## Tasks & Acceptance

**Execution:**
- [x] New tests, each seen failing first: `tests/unit/test_slack_adapter.py` (every matrix row, using `httpx.MockTransport`), `test_slack_adapter_hardening.py` (tokens, caps, redirects, transport errors), `test_slack_mentions.py`, `test_chat_http.py`, and `test_project_channel_slack.py` (schema, use case with the shared fakes, factory).
- [x] Rule 1(b) revisions, citing "story 3-2, 2026-11-02": `test_chat_factory.py::test_slack_is_refused_until_its_adapter_lands`, the `{"provider": "slack"}` refusal cases in `test_project_channel_schemas.py` and `test_project_channel_router.py`, and the contract assertion `"slack" not in …` in `test_project_channel_router.py`.
- [x] Shared transport, then mentions, adapter, factory, schema, then `make openapi`.

**Acceptance Criteria:**
- Given 250 replies with no cursor, when `replies_since` runs, then it makes two `conversations.replies` requests and returns all 250 in `ts` order.
- Given a thread holding a `bot_message`, a `thread_broadcast`, an `app_id` post and a `bot_id` post by an allowed user, when `replies_since` runs, then none is returned.
- Given a token that appears in an error body, a transport error or a 5xx, when any call fails, then `ChatError` shows `***`.

## Design Notes

Slack Web API facts, verified 2026-11-02:
- [`auth.test`](https://docs.slack.dev/reference/methods/auth.test) answers `{ok, url, team, user, team_id, user_id, bot_id}`.
- [`conversations.info`](https://docs.slack.dev/reference/methods/conversations.info) answers `{ok, channel}`. The [conversation object](https://docs.slack.dev/reference/objects/conversation-object)'s `is_member` is whether the token's own identity is a member. It needs `channels:read` or `groups:read`.
- [`chat.postMessage`](https://docs.slack.dev/reference/methods/chat.postMessage) takes JSON `{channel, text, thread_ts?}` and answers `{ok, channel, ts, message}`. Reply to the parent's `ts`. It needs `chat:write`.
- [`conversations.replies`](https://docs.slack.dev/reference/methods/conversations.replies) takes `channel`, `ts`, `cursor`, `limit` (no more than 200 recommended) and `oldest`. It answers `{ok, messages, has_more, response_metadata.next_cursor}`, earliest first, with the parent first. It needs `channels:history` or `groups:history`, and is Tier 3.
- [Rate limits](https://docs.slack.dev/apis/web-api/rate-limits): HTTP 429 with `Retry-After` in seconds. [The 2025-05-29 change](https://docs.slack.dev/changelog/2025/05/29/rate-limit-changes-for-non-marketplace-apps) says "Internal customer-built applications are not impacted by these changes."
- [Formatting](https://docs.slack.dev/messaging/formatting-message-text): a mention is `<@U012AB3CD>`. `&`, `<` and `>` are control characters to escape as entities.
- Every method answers HTTP 200 with `ok: false` and an `error` code on failure, and `missing_scope` adds `needed`.

## Verification

**Commands:**
- `make lint` -- green: import-linter, test pairs, 400-line cap.
- `make test` -- green, with domain and application at 100% branch coverage.
- `make openapi` -- regenerates the contract for `slack`, with no drift afterwards.

**Manual checks (only a live workspace can confirm):** whether `conversations.replies` repeats the parent on every page; whether `oldest` filters thread replies as documented; what `auth.test`'s `user` returns for a bot token; whether a 429 ever arrives as HTTP 200 `ratelimited` instead.

## Spec Change Log

- 2026-11-02, written by the implementer from `stories.yaml` 3-2, AD-25 and its 3-1 and 4-1 amendments, and the 3-1 and 3-4 story files.

## Implementation Notes

- **Built:** `infrastructure/chat/http.py` and `slack.py` (new), the Slack matchers in `mentions.py`, which now shares one `_without` helper with `strip_mentions`, `slack` in `open_channel`, and `slack` in `ProviderIn`. `REQUIRED_REASON` now names the provider. `mattermost.py` sends through `http.exchange` with no behaviour change (its two suites pass unchanged), and it lists the moved names in `__all__`, so `from …mattermost import TIMEOUT_SECONDS, MAX_RESPONSE_BYTES, new_client` still resolves. The port, the use case, the entity, the fakes and the migration are unchanged. `make openapi` added `slack` to the `provider` enum of `ChannelIn` and `ChannelOut`.
- **Tests:** five new modules. All of them failed at collection before the code existed. The four rule-1(b) revisions listed under Tasks were the only existing tests that failed once `slack` was allowed, and each now names this story and its date. The two refusal cases now use the unknown provider `teams`, so "an unknown provider is refused at its field" keeps its coverage.
- **Gates:** `make lint` green (test pairs 306 modules). `make test` green: backend 9,625 passed and 1 skipped, with domain and application at 100% branch coverage and the chat modules fully covered; web-client 1,846 passed. A second `make openapi` changed nothing.
- **Pre-existing, not touched:** `mypy` on `infrastructure/chat` (outside the gate) reports `no-any-return` at `mattermost.py::_message`, from 3-1.
