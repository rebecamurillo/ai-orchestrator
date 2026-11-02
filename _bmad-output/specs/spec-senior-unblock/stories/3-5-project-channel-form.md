---
title: 'Project channel form'
type: 'feature'
created: '2026-11-02'
status: 'in-review'
route: 'dispatch'
baseline_commit: '2460a484df02e3db8e88834fef9153551b3d3515'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Operator cannot set or test a Project's chat channel from the web client. The API exists since 3-4 (CAP-10).

**Approach:** Add a `ChannelForm` island below `ProjectForm` on the Project edit page. It reads, saves and tests through `GET`/`PUT /projects/{id}/channel` and `POST .../channel/test`, and shows the probe's `detail` verbatim.

## Boundaries & Constraints

**Always:** The island calls only `src/api/client.ts`, through the same-origin proxy (AD-1). Payload types come from `src/api/schema.d.ts` (AD-3). The token is sent only when the Operator typed a replacement, never kept in a store or `localStorage`, and cleared from state after a save. Test is disabled until a channel is saved and while the form has unsaved changes, because 3-4 probes the saved channel only. Copy states facts (NFR-8). The channel section says: "the bot token is stored encrypted, never shown, and never given to an agent".

**Never:** No change to `ProjectForm.tsx`, `src/actions/projects.ts`, `stub-backend.mjs`, `projects-fixtures.mjs`, the new-Project page, or any existing test. `project-form.spec.ts` pins zero `*token*` test ids on `/projects/new`. No `slack` option (3-2). No Run page change.

**Decided (lead review, 2026-11-02):**
- The token field follows the env-var pattern without the mask. When `token_set` is true it shows `set` and a `replace` control, which reveals an empty password input.
- The Operator's live check is not this story's gate. It is the connection test this form offers, run with a real bot token at the 3-3 done checkpoint.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected | Error |
|---|---|---|---|
| Load, off | `GET` → `off` | the provider select reads `off`; other fields hidden; Test disabled | a failed `GET` → its problem `detail` with a retry control |
| Load, set | `mattermost`, `token_set` | fields filled; token shows `set · replace` | N/A |
| Save new | `mattermost`, fields, token | `PUT` body holds the token; afterwards the token field reads `set` | 422 → each `errors[].path` shown at its field |
| Save, keep | the token was not replaced | `PUT` body has no `token` key | N/A |
| Turn off | select `off`, save | `PUT {provider: "off"}`; Test disabled | N/A |
| Allowed users | `"u1 alice\nu2 bob"` | `[{id: "u1", handle: "alice"}, …]` | a line without exactly two fields → inline error, no request |
| Test | saved, clean | `POST .../test`; `ok`/`failed` and `detail` shown beside the button | a non-200 → its problem `detail` |
| Dirty | a field edited after the save | Test disabled, with the line "save before testing" | N/A |
| Builtin | `readiness` | `PUT` 409 | its `detail` shown |

</frozen-after-approval>

## Code Map

Under `web-client/`.

- `src/lib/projects/channel.ts` (new, pure) -- `formFromChannel(ChannelOut)`, `bodyFromForm(form)` (sends `token` only when replaced), `parseAllowedUsers(text)` and `formatAllowedUsers(users)`, one `id handle` per line, and `errorsByField(problem)`.
- `src/islands/ChannelForm.tsx` (new, one prop `projectId`, at most 300 lines) -- the provider select (`off`, `mattermost`), base URL, channel id, token, allowed users textarea, a metadata-only switch, Save, Test and the result line. Every test id starts with `channel-`. CSS variables only, with no inline styles.
- `src/pages/projects/[id]/edit.astro` -- mounts `<ChannelForm client:load projectId={projectId} />` below `ProjectForm`, only when the Project was found.

## Tasks & Acceptance

**Execution:**
- [ ] New tests, each seen failing first: `tests/unit/channel-form-lib.test.ts` (every helper, every matrix row it owns), `tests/unit/channel-form-island.test.ts` (React Testing Library, as in `project-form-island.test.ts`: load, save, keep, off, test, dirty, errors), and `tests/e2e/channel-form.spec.ts`. The e2e spec opens `/projects/<CLEAN_ID>/edit` and answers the browser's `/api/projects/*/channel*` calls with `page.route()`.
- [ ] The lib, then the island, then the page.

**Acceptance Criteria:**
- Given a saved channel, when the Operator presses Test and the stub answers `{ok: false, detail: "401 Invalid or expired session"}`, then `failed` and that text appear beside the button.
- Given a stored token, when the Operator saves without pressing `replace`, then the request body has no `token` key.
- Given `/projects/new`, when it renders, then no `channel-*` test id exists.

## Verification

**Commands:**
- `make lint` -- green: eslint, prettier, tsc, astro check, `gen:api --check`, test pairs.
- `make test` -- green, with `src/lib/**` at 90% lines or more.
- `make e2e-ui` -- green. It binds 4321; if that port is held, ask the Operator before stopping anything (hard rule 9).

## Spec Change Log

- 2026-11-02, lead review: split out of the 3-1 draft. Added Test disabled while the form is dirty, the token cleared after a save, the builtin refusal, and the check that `/projects/new` has no `channel-*` ids.
