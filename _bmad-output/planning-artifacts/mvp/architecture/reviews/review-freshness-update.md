# Freshness / verification review — ARCHITECTURE-SPINE.md, 2026-09-02 update

Reviewed 2026-09-02. Scope: only the technical claims **new** in the 2026-09-02 update (AD-5/AD-11 two-key split, AD-13 30-day `recv`, AD-9 prepare-commit rule, AD-14 `Git.sync` no-op and worktree reuse). The Stack table and every pinned version were already checked in `review-freshness.md` and are not re-done here. LiteLLM claims were checked against the source at the pinned tag `v1.99.0`; DBOS against the source at tag `2.31.0` (PyPI latest today is still 2.31.0, no 2.31.x follow-up); `bmad-build-auto` against the installed skill; git against `git 2.50.1` in a scratch repo.

Verdict key: **VERIFIED** · **VERIFIED (source)** (confirmed in vendor source, not in user docs) · **CONTRADICTED** · **UNVERIFIED**.

---

## 1. LiteLLM two-key split (AD-5, AD-11, env table, Open at handoff 6)

**Spine claims.** `LITELLM_API_KEY` "can only call models"; `LITELLM_SPEND_KEY` "reads `/spend/logs/v2`", "the admin-side key"; a model-call-only key "can be issued on the host LiteLLM so the harness key cannot read `/spend/logs/v2`"; `Gateway.spend_for_attempt` reads `GET /spend/logs/v2?end_user=<run_id>&session_id=<attempt_id>` with `LITELLM_SPEND_KEY`.

### 1.1 A model-call-only virtual key exists — VERIFIED (source + PR)
- `POST /key/generate` accepts `key_type` (`llm_api | management | read_only | default`, default `default`) — `GenerateKeyRequest.key_type`, `litellm/proxy/_types.py` (v1.99.0) around the `LiteLLMKeyType` enum: `LLM_API = "llm_api"  # Can call LLM API routes (chat/completions, embeddings, etc.)`.
- `handle_key_type` maps `llm_api → allowed_routes=["llm_api_routes"]`, `management → ["management_routes"]`, `read_only → ["info_routes"]` — `litellm/proxy/management_endpoints/key_management_endpoints.py` (`def handle_key_type`). Docstring of `/key/generate` in the same file: "`key_type: Optional[str]` - Type of key that determines default allowed routes. Options: "llm_api" (can call LLM API routes), "management" …, "read_only" …, "default" …".
- Raw `allowed_routes` in the body requires PROXY_ADMIN (`_check_allowed_routes_caller_permission`: "Only proxy admins can set `allowed_routes` on a key. Use `key_type` to pick a preset route bucket instead."); the `key_type` presets are the non-admin-safe path. Since the host operator creates both keys with the master key this does not matter, but it fixes the recipe: use `key_type`, not hand-written `allowed_routes`.
- Enforcement: `RouteChecks.should_call_route` → `is_virtual_key_allowed_to_call_route` "Applies to all Roles" — `litellm/proxy/auth/route_checks.py`; called from `user_api_key_auth.py` on every request. A key with `allowed_routes=["llm_api_routes"]` calling `/spend/logs/v2` gets 403 `"Virtual key is not allowed to call this route. Only allowed to call routes: [...]"`.
- Feature origin: PR #12909 "Proxy - specify `key_type` - allows specifying if key can call LLM API vs Management routes", merged 2025-07-24 — https://github.com/BerriAI/litellm/pull/12909. **Not documented** on https://docs.litellm.ai/docs/proxy/virtual_keys (that page mentions only `allowed_routes`, "enforced for every role, including admin-owned keys"); it is in the endpoint docstring/OpenAPI only.
- `models: [...]` on the key additionally restricts which models it may call (https://docs.litellm.ai/docs/proxy/virtual_keys — "Restrict which models a key can call"). Orthogonal to routes.

### 1.2 Does `/spend/logs/v2` require an admin/master key? — CONTRADICTED as stated; the real rule is stricter for the *spend* key
- The route is **not** admin-only and **not** premium: `ui_view_spend_logs` is registered for `"/spend/logs/v2"` and `"/spend/logs/ui"` with `dependencies=[Depends(user_api_key_auth)]` and no `premium_user` check — `litellm/proxy/spend_tracking/spend_management_endpoints.py`. Query params include `api_key, user_id, request_id, session_id, team_id, min_spend, max_spend, start_date, end_date, page, page_size, status_filter, model, model_id, model_group, key_alias, end_user, error_code, error_message, sort_by, sort_order` — so `end_user=` and `session_id=` (the spine's filters) exist. Note `session_id` is documented as "partial string match".
- Role gate: a plain virtual key defaults to `user_role = INTERNAL_USER` (`user_api_key_auth.py`: `LitellmUserRoles(user_object.user_role) if user_object … else LitellmUserRoles.INTERNAL_USER`; `_return_user_api_key_auth_obj`: `user_role or _get_user_role(user_obj) or LitellmUserRoles.INTERNAL_USER`). `non_proxy_admin_allowed_routes_check` lets INTERNAL_USER through for `internal_user_routes`, which includes `spend_tracking_routes` = `/spend/logs`, `/spend/logs/v2`, `/spend/logs/ui`, `/spend/tags`, `/key|user|team|organization/spend/report` … (`_types.py`). So **a default virtual key can call `/spend/logs/v2`** — the "cannot read spend logs" property comes only from `key_type=llm_api` (§1.1), not from the endpoint.
- **Row scoping (the part the spine misses):** for a non-admin caller the handler forces `where user = <caller's user_id>` (`user_scope_applies = not is_request_id_lookup and not is_admin_view and team_id is None and _can_user_view_spend_log(...)`; then `where_conditions["user"] = user_api_key_dict.user_id` or an `AND [{"user": …}]`). `_is_admin_view_safe` is true only for `PROXY_ADMIN` / `PROXY_ADMIN_VIEW_ONLY`. `_can_user_view_spend_log` is true only when the role is INTERNAL_USER/INTERNAL_USER_VIEW_ONLY **and** `user_id is not None`. Consequence: a non-admin `LITELLM_SPEND_KEY` sees only rows whose `user` column equals its own `user_id`; the harness key's rows carry the harness key's `user` (or NULL if it has no user) and would be invisible → `Gateway.spend_for_attempt` returns empty and the readiness check "non-empty spend" fails. `global_spend_tracking_routes` (`/global/spend/tags` etc.) are a separate group that a non-admin key reaches only with `permissions: ["get_spend_routes"]` on the key.
- Therefore the spend key must be one of: (a) the **master key** (`user_role=PROXY_ADMIN`, `user_id=litellm_proxy_admin_name`) — works, but it is the key that can also mint keys; (b) a virtual key whose **owner user has `user_role: proxy_admin`** (`/user/new` with `user_role`, then `/key/generate` with that `user_id`; docs: keys inherit "The owner's role in full. If the owner is `proxy_admin`, every non-admin route restriction is skipped" — https://docs.litellm.ai/docs/proxy/virtual_keys) — optionally narrowed with `key_type=read_only` … **no**: `read_only` maps to `info_routes`, which does not contain `/spend/logs/v2`; use the admin-owned key with explicit `allowed_routes: ["/spend/logs/v2"]` (allowed for a master-key caller) to make it spend-only; or (c) a `proxy_admin_viewer`-owned key (read-parity with admin, all GETs allowed, LLM routes 403 — `_check_proxy_admin_viewer_access`), which is the least-privilege fit: it can read every spend row and cannot call models or create keys. Roles are enforced on the API, not UI-only (https://docs.litellm.ai/docs/proxy/access_control).

### 1.3 Spine fix
- AD-5 / env table: keep the two-key split; replace "the admin-side key" with the concrete recipe in `host/README.md`: `LITELLM_API_KEY` = `/key/generate {"key_type":"llm_api","models":[…]}`; `LITELLM_SPEND_KEY` = a key owned by a user with `user_role: proxy_admin_viewer` (or `proxy_admin`, or the master key as the day-1 fallback) — never a plain default key, because a default key is row-scoped to its own `user_id` and returns nothing for the harness key's calls.
- AD-11: state that `/spend/logs/v2` is non-premium but **row-scoped for non-admin callers**, and that `session_id` is a partial (substring) match — attempt ids are UUIDs so this is harmless, but say it.
- Open at handoff 6: the fallback "one key for both" is not a smaller exposure than the split — a default key already reaches `/spend/logs/v2` for its own rows; the split's value is that the harness key gets `key_type=llm_api` (403 on every non-LLM route). Reword.
- Readiness check (AD-10): add "spend key is admin-view" as an explicit check line (`GET /spend/logs/v2?api_key=<harness key hash>` returns rows).

---

## 2. DBOS `recv` with a 30-day timeout (AD-13, state diagram)

**Spine claims.** "the engine adapter waits with a single `recv` on `human:{run_id}` (30 days; expiry is applied by the walker as Run `failed`, reason `parked 30 days`)"; diagram `needs_you --> failed: parked 30 days (recv expiry)`.

- Signature — VERIFIED: `DBOS.recv(topic: Optional[str] = None, timeout_seconds: float = 60) -> Any` — https://docs.dbos.dev/python/reference/contexts and `dbos/_dbos.py` at tag 2.31.0.
- Returns `None` on expiry, does not raise — VERIFIED (docs + source): "Calls to `recv` wait for the next message in the queue, returning `None` if the wait times out." (https://docs.dbos.dev/python/reference/contexts; same sentence at https://docs.dbos.dev/python/tutorials/workflow-communication). Source `dbos/_sys_db.py` 2.31.0: `SystemDatabase.recv` loops `while not event.is_set(): … if remaining <= 0: break` then `recv_consume`, which does `message: Any = None … if len(rows) > 0: message = …` and records the (possibly `None`) output in `operation_outputs` before `return message`. So a 30-day expiry yields a recorded `None`; the walker's `failed: parked 30 days` branch is reachable and idempotent on replay.
- Timeout is durable across restarts — VERIFIED (source): `recv_setup` calls `record_sleep(workflow_uuid, timeout_function_id, timeout_seconds)`, which checkpoints `end_time = time.time() + seconds` as a `DBOS.sleep` row (`function_id = recv step id + 1`; `_dbos.py`: `timeout_function_id = ctx.curr_step_function_id + 1`) and on replay returns `max(0, end_time - now)`. The 30-day deadline therefore survives process restarts rather than restarting from zero. `DBOS.step_id` bookkeeping: a `recv` consumes **two** step ids (recv + its sleep) — relevant to Open at handoff 2 (`step_id == function_id`).
- Maximum timeout — VERIFIED none: no clamp on `timeout_seconds` in `_dbos.py` or `_sys_db.py` (`record_sleep` only floors at 0; `sleep` returns early for `<= 0`); docs specify no maximum. The wait loop wakes every `_event_recheck_interval()` and re-checks the DB, so a 2 592 000 s timeout is just a long loop. Only caveat: a workflow-level `SetWorkflowTimeout` (not used by the spine) would cancel earlier.
- One correctness note — CONTRADICTED only if the walker is `async def`: `DBOS.recv` calls `check_async("recv")` and raises when invoked from a coroutine; an async workflow must use `DBOS.recv_async`. The spine does not say whether `infrastructure/dbos/walker.py` is sync or async (AD-6/AD-13 silent; research/dbos.md notes async workflows exist). State it.

**Spine fix.** AD-13: add "(`recv` returns `None` on expiry; the timeout is a durable sleep step, so it survives restarts; no upper bound in DBOS 2.31)" and name `recv` vs `recv_async` according to the walker's sync/async choice. Open at handoff 2: note the extra sleep step id per `recv`.

---

## 3. `bmad-build-auto` step-01 "clean working tree" (AD-9)

**Spine claims.** "the harness always starts on a clean tree (`bmad-build-auto` step-01 halts otherwise)"; the `agent` executor commits `project-context.md`, Answer archive, `## Verify Failure` as `orchestrator: prepare story {id} attempt {n}` before dispatch.

- Installed skill text — VERIFIED at `/Users/rebecamurillo/Documents/projects/optimai/ai-orchestrator/.agents/skills/bmad-build-auto/step-01-clarify-and-route.md:73`: "Version control sanity check. If version control is unavailable, skip this check. Otherwise require a clean working tree, a branch that fits the intent, and writable repository metadata. For Git, run `git add --refresh -- .`, then confirm the tree is still clean; on failure or change, HALT with status `blocked` and blocking condition `version-control metadata not writable`. … HALT on a dirty tree or obvious branch mismatch."
- What "clean" means — the skill **does not define it**; the LLM judges from `git status`. Reality check (`git 2.50.1`): an untracked file makes `git status --porcelain` non-empty (`?? untracked.txt`) — i.e. the ordinary reading of "clean working tree" (`test -z "$(git status --porcelain)"`) is **dirty** with an untracked file; only `git status --porcelain -uno` / `git diff-index --quiet HEAD` ignore untracked files. A staged-but-uncommitted file shows `A  file` — dirty under every reading. Only a **committed** file is clean under all readings. So: an untracked file *may* count (undefined → assume yes); merely tracking (`git add`) is definitely not enough; `project-context.md` must be **committed** (or git-ignored, see below).
- Where the file lives — the skill loads `persistent_facts = ["file:{project-root}/**/project-context.md"]` (`.agents/skills/bmad-build-auto/customize.toml:28`), any path; PRD FR-15 puts it at `{Spec folder}/project-context.md` (`mvp/prd.md:244`). Nothing in the skill requires it to be tracked; a git-ignored `project-context.md` would also satisfy "clean" and be loaded. The spine's choice to commit it is valid and keeps FR-15 auditable, but it is a choice, not a requirement — say which.
- Edge found: `git add --refresh -- .` fails (`fatal: pathspec '.' did not match any files`, exit 128) in a repository with **no tracked files**, and step-01 then halts `version-control metadata not writable`. `fixtures/readiness-repo/` (AD-10) must contain at least one committed file — trivially true for a repo with `_bmad/`, but worth one line.

**Spine fix.** AD-9: keep the prepare commit; change "the harness always starts on a clean tree (`bmad-build-auto` step-01 halts otherwise)" to "…on a tree where `git status --porcelain` is empty — step-01 requires a clean tree without defining it, and untracked files show in `git status`, so everything the orchestrator writes is committed, never left untracked or merely staged". Add the readiness-repo "at least one tracked file" line to AD-10 or the fixture's README.

---

## 4. git: `pull --ff-only` without upstream; `worktree add` of an existing branch (AD-14, `git.sync` row)

**Spine claims.** `git.sync` = "fetch + `pull --ff-only`; recorded no-op when the branch has no upstream; non-fast-forward → park `push_rejected`"; `git.worktree` "adds or reuses `wt/{branch}` (reuse when clean, refuse when dirty)"; pre-flight "refuses when any branch the plan checks out is held by a worktree of a non-terminal Run".

Reality-checked with `git 2.50.1` (scratch repo under the session scratchpad):

| Command | Result |
| --- | --- |
| `git pull --ff-only` on a branch with no upstream | fails, exit **1**: "There is no tracking information for the current branch." → VERIFIED: the no-op needs an explicit check. |
| `git rev-parse --abbrev-ref @{upstream}` on that branch | exit **128** "fatal: no upstream configured for branch …" → usable as the check (non-zero ⇒ no-op). |
| Upstream configured but remote branch deleted (`git fetch --prune`) | `rev-parse @{upstream}` exit 128 ("unknown revision"); `pull --ff-only` exit 1 ("no such ref was fetched"). So the `rev-parse` guard also covers the deleted-remote case (recorded no-op), which is the right outcome for a branch the operator removed upstream. |
| `git pull --ff-only` with upstream, up to date | exit 0 "Already up to date." |
| `git worktree add ../wt X` where `X` exists and is checked out nowhere | exit 0, "Preparing worktree (checking out 'X')" → VERIFIED. |
| Same branch while another worktree holds it | exit **128** "fatal: 'X' is already used by worktree at …" → git itself enforces one checkout per branch; the pre-flight "held branch" rule is consistent with git. |
| Branch checked out in the **base clone** (`main`) | exit 128, same error. |
| After `git worktree remove`, add again | exit 0. |

- **Gap:** `/work/{project}/{repo}/base` is described as a base clone, not `--bare` or detached; whatever branch it has checked out (the default branch after `clone`) can never be the target of `worktree add`. A Run whose plan checks out `repository.default_branch` (allowed — only `git.push` refuses it) would fail at `git.worktree`. Either make the base clone bare / detached-HEAD (`git clone --bare`, or `git checkout --detach` after clone) or add "the base clone's checked-out branch" to the held-branch pre-flight rule.

**Spine fix.** `git.sync` row / AD-14: "`Git.sync` runs `git fetch --prune`, then `git rev-parse --abbrev-ref @{upstream}`; non-zero ⇒ recorded no-op (no upstream, or upstream deleted); otherwise `git pull --ff-only`, non-zero ⇒ park `push_rejected` (`sync: branch diverged`)". AD-14 base clone: declare it bare or detached so the default branch is never held by the base; or extend the pre-flight held-branch rule.

---

## 5. Summary table

| # | Claim | Verdict | Fix |
| --- | --- | --- | --- |
| 1a | A virtual key can be restricted to model calls only | VERIFIED (source, v1.99.0; `key_type=llm_api`; undocumented on the docs site) | Name `key_type` in `host/README.md` |
| 1b | `/spend/logs/v2` requires an admin/master key | CONTRADICTED — any default key may call it, but non-admin callers are **row-scoped to their own `user_id`**, so the spend key must be admin/admin-viewer-owned (or master) to see the harness key's rows | AD-5, AD-11, Open 6, AD-10 check line |
| 2 | `recv` 30 days → `None` on expiry; no max | VERIFIED (docs + source 2.31.0); timeout is a durable sleep step; `recv_async` required in an async workflow | AD-13 wording; Open 2 (two step ids per recv) |
| 3 | step-01 halts on a dirty tree ⇒ prepare commit | VERIFIED (skill file line 73); "clean" undefined → untracked counts in practice, staged is dirty, so **committed** is the safe rule | AD-9 wording; readiness repo needs ≥1 tracked file |
| 4a | `pull --ff-only` fails without upstream ⇒ explicit `@{upstream}` check | VERIFIED (exit 1; `rev-parse @{upstream}` exit 128, also when the remote branch was deleted) | `git.sync` row wording |
| 4b | `worktree add` of an existing branch works when checked out nowhere else | VERIFIED (exit 0; exit 128 "already used by worktree" otherwise, including the base clone's branch) | Base clone bare/detached or held-branch rule |
