# Freshness / Ratification Review — ARCHITECTURE-SPINE.md amendments of 2026-09-15

**Reviewer lens:** every claim the amendments commit to must be reality-checked, not asserted. The spine may describe target deltas from the approved change proposal (`sprint-change-proposal-2026-09-14.md`), but where it claims to describe existing reality it must match the repository, and every delta must be distinguishable from ratified reality (the spine's own device for this is the `*(ratified 2026-09-15, FR-n)*` marker).

**Method:** the amendment diff (`git diff HEAD`, 37 insertions / 34 deletions) was read line by line; every factual claim it touches was checked against the working tree — `web-client/src/pages/` and `src/islands/`, `backend-api/src/orchestrator/` (domain statuses, entities, ports, use cases, steps registry, routers), `contracts/openapi.json` (27 paths), `scripts/harness/*.sh`, `templates/*.yaml`, `web-client/package.json`, `.env.example`, `backend-api/pyproject.toml` + `uv.lock`, and the pinned `dbos` 2.31.0 package source installed in `backend-api/.venv`.

## Verdict

**Conditionally sound.** The load-bearing technical claims are real: DBOS 2.31.0 genuinely supports the partitioned-queue design the amendment commits to, the page/island seed was corrected *toward* reality, and every file the spine says exists was found where it says. But the marker discipline is uneven: the entire saved-Runs/dependency mechanism (F4 of the change proposal) is woven into AD-8, AD-12, AD-13 and the data-fields list **without** ratification markers, inside sections headed `[ADOPTED]`, while sibling deltas in the same sentences carry dates — a reader auditing the spine against the code cannot tell those clauses are unbuilt targets. One amended claim contradicts test-pinned reality (queue reason strings) without flagging the anchor collision.

Severity counts: **1 High · 3 Medium · 5 Low**. Verified-green results follow at the end.

---

## High

### H1 — The saved-Run / dependency machinery is presented as settled reality; none of it exists in code, and it carries no ratification marker

The following, all introduced by today's diff, have **zero** presence in `backend-api/src/orchestrator/`:

- `run.after_run_id` — no hit anywhere in the source tree (`domain/entities/run.py` has no such field);
- `ParkKind` has no `dependency` member (`domain/statuses.py:42-53` ends at `internal`);
- `SignalKind` has no `start` member (`statuses.py:57-68`; `start` exists only as a `LifecycleEvent`);
- saved Runs: `create_run.py:180` enqueues unconditionally (`engine.enqueue(run.id, partition_key=repository.id)`); `run.engine_ref` defaults to `{}`, and no *Save* path exists;
- queue reasons `waiting for run {x}` and `saved — not started` (see M2 for the others).

This is legitimate F4 target material (proposal §F4, "the deepest architecture touch in the set"). The problem is presentation: AD-12's **only** marker — `*(ratified 2026-09-15, FR-13; formerly repository_id)*` — is attached to the partition-key change, while the saved-Run semantics sit unmarked in the same rule under an `[ADOPTED]` heading; AD-8's new sentence ("A terminal transition additionally resolves the Runs whose `after_run_id` names this Run…") and AD-13's `start` row and `dependency` kind are equally unmarked; the data-fields paragraph lists `after_run_id (AD-12)` beside fields that all exist. Sibling deltas in the very same sections are dated, so the absence of a marker reads as "this is built."

**Fix:** extend the AD-12 marker to cover the whole F4 delta (or add markers to the AD-8 sentence, the AD-13 `start`/`dependency` entries, and `after_run_id` in the seed).

## Medium

### M1 — `mode: restart | session`, `reply_available` (IMP-003) — unmarked delta, no code support

AD-13's `answer` and `retry` rows now carry `{mode: restart | session}` with a 422 on missing `reply_available`; AD-10 defines `reply_available`. No `reply_available` and no signal `mode` exist anywhere in backend-api (the `Harness` port does have `run`, `resume`, `resume_command`, `capabilities` — that half is real). This is IMP-003 (`answer-reply-in-session`) target text with no date marker anywhere in the AD-13 table. Same remedy as H1.

### M2 — AD-12's queue-reason set contradicts test-pinned verbatim strings without flagging the anchor collision

Amended AD-12 gives the reason set as `{branch held by {run}, global concurrency, held by {runs}, running, waiting for your answer, waiting for run {x}, saved — not started}`. Reality (`application/use_cases/queue.py:39-43`) fixes **verbatim** — the module says so, citing SPEC CAP-11 — `running`, `waiting for your answer`, `repository lock held by {label}`, `global concurrency, held by {labels}`. So the amendment renames `repository lock held by {label}` → `branch held by {run}` (and `{label}` → `{run}`, `{labels}` → `{runs}`) with no marker and no acknowledgment that existing unit tests pin these strings. Under hard rule 1 this rename needs the operator-revision exception (dated, named in the revised test); the spine should say the reason set is part of the FR-13 delta and note the anchor consequence, or keep the existing spellings.

### M3 — The DSL table claims to be "the set `validate.py` accepts" but now includes dispatch keys it does not accept, in a shape the shipped templates contradict

The `uses: agent` row now opens with "exactly one of `skill {name, folder, id}` or `prompt` / `prompt_file`". Reality: `validate.py` has no `skill`/`prompt`/`prompt_file` step keys; today `skill` is a plain **string** inside `with:` (`KIND_META["agent"].with_keys = {harness, model, skill, args, prompt_extra}`, and shipped `templates/story.yaml` uses `with: {skill: bmad-build-auto, prompt_extra: …}`). The table's preamble is present-tense ("the set `validate.py` accepts") and the row carries no marker — AD-16's `*(ratified 2026-09-15, FR-14)*` covers the install path, not this DSL shape. Also unstated: whether the `skill {name, folder, id}` map replaces the string form (which would touch the shipped templates — allowed under the exemplar-freeze test strategy, but worth saying) and where `prompt_extra` lands in the new scheme.

## Low

### L1 — Island seed omits two islands that exist

`src/islands/` reality: Board, Diagram, NewWorkflow, ProjectForm, RunDetail, RunDiagram, RunsHistory, RunsQueue, TemplateDiagram, TemplateEditor (+ `project-form-logic.ts`). The amended seed lists nine and correctly tags `StepDetail (FR-34)` as planned — good — but omits `Diagram` (the shared stateless SVG renderer, explicitly designed for Epic 8 reuse per its own docstring) and `TemplateDiagram` (mounted on `templates/[name]/[version].astro`). A seed that ratifies the island roster should list what exists. Pages seed is otherwise accurate — today's diff actually corrected the stale `runs/[id]` to reality's `workflows/[id]`.

### L2 — Conventions Routes row lists an `auth` feature router that has never existed

`contracts/openapi.json` has no `/api/v1/auth*` path; `api/routers/` has no auth module (bearer auth is `deps.py`; login is web-client-side per AD-4). The Routes row was re-touched today and re-asserts `auth`. Also cosmetic: the row's `steps` feature is served by `routers/history.py`, and reality additionally has `GET /runs/{id}/detail` and `GET /templates/{name}/graph` the conventions don't mention.

### L3 — AD-10's `HARNESS_ENV_CONTRACT` enumeration is one variable short of the normative script

`scripts/harness/_common.sh:26` (which AD-10 itself calls normative) includes `LANGFUSE_ENVIRONMENT`; AD-10's inline list stops at `LANGFUSE_SECRET_KEY, ORCH_LOG_CONTENT`. The spine's own env-variable table *does* put `LANGFUSE_ENVIRONMENT` in the harness env, so the spine is internally inconsistent as well as script-inconsistent.

### L4 — Engine port today types `partition_key: UUID`; the new key is a string

`domain/ports/engine.py:59` — `enqueue(self, run_id: UUID, partition_key: UUID)`; `create_run.py:180` passes `repository.id`. The `"{repository_id}:{branch}"` key requires widening the port parameter to `str` (trivial: the DBOS facade already does `str(partition_key)` into `queue_partition_key: Optional[str]`). Worth one clause in AD-6/AD-12 so the delta lands as a deliberate port change rather than a silent type drift.

### L5 — `ia-agents-skills/` does not exist at the repo root yet

AD-16's amended rule reads as if the folder exists ("the operator-authored skills in the repository-root `ia-agents-skills/`"). The marker `*(ratified 2026-09-15, FR-14)*` is present, and the proposal (§"ia-agents-skills/ at the repo root") defines it as new, so this is a marked delta — but a "(to be created)" would spare the next reality-checker the `ls`.

---

## Verified green (reality-checked, no action)

- **DBOS partitioned queues — confirmed in the pinned package, not from docs.** `pyproject.toml` / `uv.lock` pin `dbos==2.31.0`; the installed package (`.venv/.../dbos/_dbos.py:939`) has `register_queue(name, *, worker_concurrency, global_concurrency, partition_concurrency, partition_worker_concurrency, partition_limiter)`, and `enqueue` takes `queue_partition_key: Optional[str]` (`_client.py`, `_core.py`) — its docstring states enqueues to a partitioned queue *must* pass one. The codebase already runs `DBOS.register_queue(name, global_concurrency=concurrency, partition_concurrency=1)` (`infrastructure/dbos/facade.py:137`) and enqueues with `partition_key=str(repository_id)`. Changing the key to `"{repository_id}:{branch}"` is expressible with the identical API (subject to L4's type widening).
- **Probe is honestly a delta.** `scripts/harness/claude.sh` dispatches `install|configure|doctor` only; no `probe` verb in any harness script; no `/harnesses/{name}/probe` path in `contracts/openapi.json` or the routers. Everywhere the spine mentions probe it carries `*(ratified 2026-09-15, FR-33)*` or sits in a row tagged FR-33.
- **Harness scripts and readiness exist as claimed.** `scripts/harness/{_common,claude,codex,opencode}.sh`, `HARNESS_ENV_CONTRACT` + per-harness `HARNESS_ENV_ALIASES` (claude: `ANTHROPIC_AUTH_TOKEN=LITELLM_API_KEY`, `ANTHROPIC_CUSTOM_HEADERS=derived`), `use_cases/harness_readiness{,_evaluate,_seed}.py`, `POST`+`GET /api/v1/harnesses/{name}/readiness`, `GET /harnesses`, the `harness` table with `enabled`/`version_pin` (touched by `db/seed.py`), `fixtures/readiness-repo/`, `scripts/readiness_fixture.sh` — all present.
- **Steps registry and shipped-kinds table match reality.** `application/steps/__init__.py` holds `KIND_META` (the one enumeration; `registry.py` holds the executor registry beside it); one module per kind exactly as the table lists (`plan_check, git_worktree, git_sync, shell, agent, git_commit, git_push, pr_link, checkpoint, bmad_install`). The agent row's timeout change (90 → stall-detector default 30) is a correctly marked FR-10 delta; code today has `KIND_META["agent"] = (…, 90, …)` and no stall detector.
- **Pages seed matches `src/pages/`** (login, index/Board, workflows/[id], workflows/new, runs with RunsQueue+RunsHistory, projects, templates, `api/[...path].ts`), with `workflows/[id]/steps/[...path]` and `StepDetail` consistently tagged FR-34 (planned).
- **`?view=diagram` retirement is a marked delta and reality agrees it exists to retire:** `workflows/[id].astro` mounts `RunDiagram` behind `?view=diagram` today; the embed-and-redirect is `*(ratified 2026-09-15, FR-29)*`.
- **`signal-criterion` is a real token:** `#6C8CD5` in `ux-ai-orchestrator-2026-08-25/DESIGN.md` frontmatter, revival recorded as an operator decision of 2026-09-15 in the ux memlog. Not yet in `web-client/src` CSS — consistent with it being part of the FR-29 delta.
- **Spot-checked stack rows are current:** dbos 2.31.0, @dagrejs/dagre 3.1.1, astro 7.2.10, react 19.2.8, nanostores 1.5.2, BMAD_VERSION 6.11.0, CLAUDE_CODE_VERSION 2.1.258.
- **`budget_usd` nullable is a marked delta:** today `run.py:65` has `budget_usd: Decimal` (required); the nullable/`tracked, no cap` change carries `*(ratified 2026-09-15, FR-17)*`. The other seed fields checked (`manual_estimate_h`, `re_review_done`, `accepted_paths`, `terminal_session`, `active_seconds`, `last_opened_at`, `worktrees[]`, `compare_urls[]`, `trace_id`) all exist on the entity.
