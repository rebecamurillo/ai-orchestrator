---
title: 'Project channel storage, API and connection test'
type: 'feature'
created: '2026-11-02'
status: 'done'
route: 'dispatch'
baseline_commit: '302ef490d8e3750a8d696d66fbd1896f16813871'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A Project cannot store a chat channel, and there is no way to check one. 3-3 and 4-1 read the stored channel, and 3-5's form writes it (CAP-10).

**Approach:** A `project_channel` table with a Fernet token, where no row means `off` (AD-25). Add `GET`/`PUT /projects/{id}/channel` and `POST /projects/{id}/channel/test`, which probes the saved channel through 3-1's `ChatChannelFactory`.

## Boundaries & Constraints

**Always:** The token is encrypted through `Crypto` on write. Only `test_channel` decrypts it, to open the channel. It is never returned, logged, put in a problem body, or written to `env_vars_enc` or a gate record. The harness env path (`infrastructure/db/environment.py::read_run_environment`) never reads `project_channel` (AD-5 amendment). `token` is a `SecretStr` in the schema, and no validator message echoes it. A failed probe answers 200 `{ok: false, detail}` with the adapter's redacted text, with no retry (hard rule 7). A write to the builtin `readiness` Project is refused through `projects.py::_refuse_builtin`.

**Never:** No `chat_thread` table, no posting, no job, no `CHAT_*` settings (3-3, 4-1). No `slack` value in the API (3-2). No change to `ProjectRead`, `projects.py` (use case or schemas), the Run page, `deploy/`, or any existing test. No UI (3-5).

**Decided (lead review, 2026-11-02):**
- **Masking:** a `token_set` boolean only, never the env-var `••••` plus last four. AD-5's amendment says "never returned", and four characters of a bot token help the Operator with nothing that `replace` and Test do not.
- **Test target:** the saved channel only. That is one code path, the token never travels in a second request, and the probe exercises what 3-3 will post with.
- **Keep token:** a `PUT` without `token` keeps the stored ciphertext only when the provider is unchanged. A token from another platform is never reused.
- **At least one allowed user.** CAP-12 counts replies only from allowed people, so an empty list is a channel nobody can answer from.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error |
|---|---|---|---|
| Read, no row | `GET .../channel` | `{provider: "off"}`, with `base_url` and `channel_id` null, `allowed_users: []`, `metadata_only: false` and `token_set: false` | N/A |
| Save | `PUT` `mattermost`, every field, token | row stored, token encrypted; the response holds `token_set: true` and no token | N/A |
| Keep token | `PUT` without token, row stored, same provider | ciphertext unchanged | no row → 422 `token: no stored token to keep` |
| Turn off | `PUT {provider: "off"}` | row deleted; idempotent | N/A |
| Bad shape | base URL not http(s) or without a host; empty channel id; no allowed user; duplicate user id; handle with `@` or whitespace | nothing written | 422 naming the field |
| Builtin | any `PUT` on `readiness` | nothing written | 409 |
| Probe ok | `POST .../channel/test` | `{ok: true, detail: "connected as @<bot>"}` | N/A |
| Probe refused | `ChatError` | `{ok: false, detail}`, 200 | never 5xx |
| Test when off | no row | the factory is not called | 409 `no channel is set` |
| Unknown Project | any route | nothing written | 404 |
| Project deleted | row exists | row removed by `ON DELETE CASCADE` | N/A |

</frozen-after-approval>

## Code Map

Under `backend-api/src/orchestrator/` unless stated.

- `domain/entities/project_channel.py` (new) -- `ProjectChannel{project_id, provider: ChatProvider, base_url, channel_id, token_enc, allowed_users: tuple[ChatUser, ...], metadata_only, created_at, updated_at}`, and `view() -> ProjectChannelView`, which drops `token_enc` and sets `token_set = True`. `ChatProvider` and `ChatUser` come from `domain/ports/chat.py` (3-1).
- `domain/ports/repositories.py` -- `ProjectChannelRepository{get(project_id), put(channel), delete(project_id)}`.
- `application/use_cases/project_channel.py` (new) -- `ChannelPorts{uow, projects, channels, crypto, clock, factory}`. `get_channel`, `put_channel(draft)` and `test_channel` reuse `projects.py::_require` and `_refuse_builtin`, and `domain/errors.py`. `projects.py` is at 399 lines and stays untouched.
- `infrastructure/db/models/project_channel.py`, `infrastructure/db/repositories/project_channel.py` (new), registered in `models/__init__.py`, `repositories/__init__.py` and `db/__init__.py`. `project_id` is the PK, with an FK to `project` `ON DELETE CASCADE`. `provider` is Text with a CHECK on the two values. `allowed_users` is JSONB. Every column is `NOT NULL`.
- `backend-api/alembic/versions/{next}_project_channel.py` -- revises the head at landing time, since 2-3 and 2-5 also add revisions.
- `api/schemas/project_channel.py` (new) -- `ChannelIn{provider: off|mattermost, base_url?, channel_id?, token?: SecretStr, allowed_users[], metadata_only = false}`, `ChannelOut{provider, base_url, channel_id, token_set, allowed_users, metadata_only}`, `ChannelTestOut{ok, detail}`. Text fields use `StorableText` from `schemas/common.py`.
- `api/providers_channel.py` (new) -- `channel_ports`, shaped like `providers_trajectories.py`. Crypto comes from `app.state` as in `providers.py::project_ports`. `factory` is `infrastructure.chat.open_channel`.
- `api/routers/project_channel.py` (new) -- the three routes, with refusals declared as `routers/projects.py` declares them.
- `main.py` -- mounts the router in the first `_mount` tuple. The file is at 400 lines. If the import and the entry would pass the cap and 2-3 has not already made room, move `crypto_factory` unchanged into `infrastructure/crypto/factory.py`. `main.py` then imports it from there, so `from orchestrator.main import crypto_factory` still resolves, and the move adds `tests/unit/test_crypto_factory.py`.
- `contracts/openapi.json`, `web-client/src/api/schema.d.ts` -- through `make openapi` only.

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/fakes/project_channel.py` -- `FakeProjectChannelRepository`, the shared fake that 3-3 and 4-1 reuse.
- [x] New tests, each seen failing first: `tests/unit/application/test_project_channel.py` (every matrix row with `FakeCrypto` and 3-1's `FakeChatChannelFactory`), `test_project_channel_router.py`, `test_project_channel_schemas.py`, `test_project_channel_repository_adapter.py`, `test_run_environment_channel.py`, and `tests/e2e/test_project_channel.py` (save, read, keep, off, and Test against `http://127.0.0.1:9` answering `ok: false`).
- [x] Domain, port, migration, model, repository, use case, schemas, provider, router, mount, then `make openapi`.

**Acceptance Criteria:**
- Given a channel saved with token `tok-<uuid>`, when `GET /projects`, `GET /projects/{id}`, `GET .../channel` and a refused `.../test` are read in e2e, then no body contains it.
- Given a Project with a channel and one env var, when `read_run_environment` builds its `ProjectContext`, then `env_vars` holds exactly that one variable.
- Given an existing database, when migrations run, then every Project reads `off`.

## Verification

**Commands:**
- `make lint` -- green: import-linter, test pairs, 400-line cap.
- `make test` -- green, with domain and application at 100% branch coverage.
- `make openapi` -- no drift.
- `make e2e` -- green on the disposable stack only. Schemathesis covers the new routes.

## Spec Change Log

- 2026-11-02, lead review: split out of the 3-1 draft. Added the builtin, cascade, `SecretStr` and allowed-user rules, and the `main.py` mount. The draft's mount inside `projects.router` would break a frozen test.
- 2026-11-02, implementation. The Code Map names `infrastructure.chat.open_channel` as the factory. A bare function cannot satisfy `ChatChannelFactory.open`, so `main()` wires one shared `ChatChannels()` (3-1's done state), stores it as `app.state.chat`, and closes it in a `finally` after uvicorn returns or raises. `main.py` made room by moving `crypto_factory` unchanged into `infrastructure/crypto/factory.py`, which `main` re-imports.
- 2026-11-02, story 3-4 review. Six fixes:
  - A token the current key cannot open makes Test answer 200 `{ok: false}`. The `Crypto` port gains `DecryptionError`, which the Fernet adapter raises as a subclass of `InvalidToken`, so env-var callers behave as before.
  - `is_valid_base_url` answers `False` for a malformed host and refuses userinfo, a query and a fragment.
  - `put` is one `INSERT … ON CONFLICT (project_id) DO UPDATE`.
  - Lead decision: a kept token never follows a host change. Such a request gets 422 `token: enter the token again when the host changes`, comparing base URLs without a trailing `/`.
  - The dead behavioural half of `test_run_environment_channel.py` is replaced by a static check over `db/environment.py` and `harness/env.py`.
  - Three tests in this story's `test_project_channel_repository_adapter.py` pinned the old add-then-update `put`. They were revised under hard rule 1(b), with dated notes.

## Implementation Notes

- **Built:** `domain/entities/project_channel.py` (entity, `ProjectChannelView` with `token_set`, the pure shape rules), the `ProjectChannelRepository` port, `application/use_cases/project_channel.py` (`get_channel`, `put_channel`, `test_channel`, reusing `projects.py::_require` and `_refuse_builtin`), the model, adapter and migration `0028_project_channel`, `api/schemas/project_channel.py`, `api/providers_channel.py`, `api/routers/project_channel.py`, `infrastructure/crypto/factory.py`, and the mount and wiring in `main.py` (397 lines). The contract was regenerated with `make openapi`.
- **Tests:** the shared fake `tests/unit/fakes/project_channel.py`, plus nine new test modules: the six the spec names, `test_project_channel_entity.py`, `test_crypto_factory.py` and `test_main_chat_channels.py` (close at shutdown, and also when serving raises). All of them failed at collection before the code existed. No existing test was revised.
- **Token proofs:** the token is encrypted on write and kept by copying the ciphertext, with no decrypt. `ChannelDraft.token` and `ProjectChannel.token_enc` are `repr=False`, and the schema token is a `SecretStr`. Validator messages are fixed text, so a 422 never echoes the token. `structlog` capture shows no log line during save, read and a refused test. Project reads, channel reads and a refused probe carry no token, in the router tests and in e2e. `test_channel` also replaces the token with `***` in a `ChatError` detail, in case a factory does not redact. `environment.py` names no channel storage, and its `ProjectContext` holds only the Project's own variables.
- **Shape rules:** these sit at the schema, at their field path. A `mattermost` body needs `base_url`, `channel_id` and at least one allowed user (`validate_default` field validators). A token is non-empty printable ASCII with no whitespace, which matches the adapter's own refusal. The use case repeats the presence checks as `Invalid("<field>: …")` for callers outside the API. A keep is refused when the stored token belongs to another provider (`token: the stored token belongs to another provider`).
- **Gates:** `make lint` green (test pairs 304 modules). `make test` green: backend 9,468 passed and 1 skipped, domain and application at 100% branch coverage; web-client 1,771 passed. `make openapi` regenerated `contracts/openapi.json` and `schema.d.ts` with no drift. `make e2e` was not run, by instruction. `tests/e2e/test_project_channel.py` and schemathesis on the new routes are still unverified.

