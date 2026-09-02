---
title: Reconciliation review — ARCHITECTURE-SPINE vs template-dsl-draft (2026-09-02)
type: review
reviewed: ../ARCHITECTURE-SPINE.md
against: ../../template-dsl-draft.md
created: 2026-09-02
verdict: not yet reconciled — 1 blocking gap (plan-time list-file reads), 6 governance gaps, several low-severity omissions
---

# Reconciliation review — spine vs template DSL draft

Scope: only what the DSL draft says that the spine either does not govern or contradicts. Decisions already taken by the spine are taken as given and not re-opened: `uses: <kind>` + `with` / `run: <command>`; `template` is a step kind; retry without harness resume falls back to a new session with the prompt prepended; verify re-dispatch has its own counter; worktrees keyed by branch; `bmad.install` kind; the plan is materialised fully at Run start with `path` keys.

Where a decision is "taken" but not actually written anywhere in the spine text, that is reported as a gap (the spine is the build substrate; an oral decision does not bind an epic).

---

## F1 — HIGH — Full materialisation needs list files the Run has not checked out yet

**Draft (§4):** "reads each `for_each` list file exactly once (a DBOS step…) and expands the tree lazily as it descends."
**Spine (AD-7):** `plan_run` expands the whole pinned tree, "`for_each` list files read once", into `step_run` rows in one transaction *before* `engine.enqueue`.

The conflict is not the laziness itself (full materialisation is the stronger and better choice, and it is consistent with AD-17 freezing `stories.yaml` / `epics.yaml` for the life of the Run). The conflict is **where the bytes come from**:

- `initiative@1` reads `{{initiative_folder}}/epics.yaml`; `epic@1` reads `{{spec_folder}}/stories.yaml`. Both are repository files on the *working branch* (`epic.branch`), or on `base_branch` when the feature branch does not exist yet.
- The worktree for that branch is created by the `checkout` step (`git.worktree`) of `epic@1`, which is a row **inside** the plan. At `plan_run` time there is no worktree for `feat/notifications`; there is only the base clone at `/work/{project}/{repo}/base`.
- Under lazy expansion the draft never had this problem: `stories.yaml` was read after `checkout` ran. Under AD-7 the read happens before any row executes.

What the spine must say (none of it is there today):

1. **Source ref for list files.** `plan_run` reads each list file through the `Git` port from `origin/{branch}` when that branch exists on the remote, else from `origin/{base_branch}`, after one `fetch` of the base clone. No worktree is involved. The `Git` port (AD-14) needs a method for this — e.g. `read_file(ref, path) -> bytes | None` (`git show ref:path`) and `branch_exists(ref)`. Neither exists in the port list today (`clone_base, worktree_add, sync, status, commit, push, remove_worktree, delete_branch`).
2. **Record what was read.** Persist on the Run the SHA per branch from which each list file was read (`run.plan_refs: {branch: sha}`), so pre-flight, recovery and the "What will run" view agree, and so `git.worktree` / `git.sync` can detect that a protected list file changed between plan and checkout (a human push in the window — the AD-12 lock only excludes other Runs). Decide the reaction: park `needs_you` with `plan is stale: {path} changed since plan` — the same shape as AD-17.
3. **Plan-time error contract.** The validator (AD-15) cannot see list files; a missing/unparseable `epics.yaml`, an item missing a field the template references (`{{epic.branch}}`), or a `spec_folder` that does not exist on the chosen ref are **plan-time** failures. AD-7/FR-8 should say: pre-flight returns them as 422 `{path, reason}` with the *item index* (`epics[1].branch`), and `create_run` refuses to create a Run when the dry plan fails. Today the spine only lists validator-time errors.
4. **AD-16 already assumes this capability.** Pre-flight "requires `_bmad/` on the working branch with `_bmad/_config/manifest.yaml` version equal to `BMAD_VERSION`" — also a read of the working branch before checkout, with no port method. The same `read_file(ref, path)` closes both.

Stacked epics (two `epics.yaml` entries on one branch) are fine under this rule: the second epic's spec folder is human-authored and must already exist on that branch or on base at plan time — say so explicitly in the plan-time error list.

**Fix location:** AD-7 rule (source ref + `plan_refs` + plan-time error contract), AD-14 `Git` port signature, AD-16 (point at the same method), Conventions → Errors (plan-time 422 with item index).

---

## F2 — HIGH — Item-level checkpoints and `for_each` options are absent from the spine

**Draft (§2, §4):** `for_each: <list file>` + `as: <name>` + `steps:`; options `pause_before_item_when` / `pause_after_item_when` (item expressions only); `epics.yaml` may carry `done_checkpoint` per epic "evaluated by the initiative's `for_each` after the epic's `pr` step"; story `spec_checkpoint` / `done_checkpoint`.
**Spine:** neither option, nor `as`, nor the `item` input type is mentioned anywhere. The step state machine has `running --> checkpoint: pause_when true` only.

Three consequences:

1. **No row to carry the pause.** Under AD-7 the plan holds one `step_run` per *step*; `epics[0]` and `epics[0].epic.stories[3]` are path segments, not rows. `pause_after_item_when` fires after the item's last step is `done` — which row goes to `checkpoint`? The Run parks (`needs_you`, `park_kind = checkpoint`) via `gate_record`, but the Steps table and the run diagram (FR-23/FR-29) have nothing to render. Choose and write one of: (a) synthetic item rows (`epics[0]`, kind `item`, status derived / `checkpoint` / `skipped`) — also solves F3's aggregate-status question and gives Skip epic a target; or (b) item pauses are `gate_record` + `run.park_path` only, and the UI renders the parked path. (a) is recommended; it keeps AD-8's "the UI renders the stored token, never derives one".
2. **Timing of `pause_when` is ambiguous.** The draft's `spec_checkpoint` on `build` reads as "review the spec *before* the agent builds"; the spine's `running --> checkpoint` reads as "after the attempt". State it: `pause_when` parks *before* the first attempt of the step (`queued --> checkpoint`), `pause_after_item_when` parks after the item's last step is `done`, `pause_before_item_when` before its first step is `queued`. Add the corresponding edges to the step machine; `checkpoint --> queued: continue` already exists.
3. **Expression language is undefined.** `pause_*_item_when`, `pause_when`, `escalate_when` are strings (`"story.spec_checkpoint"`, `"output.status == blocked"`). The spine neither names the grammar (bare item field → truthy; `a == b`; nothing else?) nor lists it among validator rules. Since these strings are evaluated inside `application/`, they must be parsed by `validate.py` (AD-15) and rejected when they reference anything but `{{as}}.<field>` (item pauses) or `output.status` (`escalate_when`).

**Fix location:** AD-7 (item rows or park_path), AD-8 step state machine (edges for pre-attempt and item-level checkpoint), AD-15 (expression grammar + `for_each` option validation), Conventions → Status tokens (kind `item` if adopted).

---

## F3 — MEDIUM — `template` rows, aggregate status, and `timeout_min` / `on_fail` on a `template` step

**Draft (§6.1):** the reason for making `template` a Step was "so it can carry `timeout_min`/`on_fail`".
**Spine:** AD-9 lists `template` as a kind; AD-7's path example (`epics[0].epic.stories[3].story.build`) shows `epic` and `story` as path segments; nothing says whether a `template` step is itself a `step_run` row, what its status is, or what `timeout_min`/`on_fail` on it mean.

- If `template` rows exist they need an aggregate status (done when every descendant row is done/skipped; error when a descendant is error and its `on_fail` escalated) — AD-8's machine has no aggregate transitions, and AD-9's `StepExecutor.execute` returns a `StepResult` for one execution, which a `template` row never has. Say either "a `template` step produces no row; its callee's rows are inlined under its path" (then `timeout_min`/`on_fail` on it are **rejected by the validator**), or define the derived-status rule.
- `timeout_min` on a `template` step cannot be honoured under the Conventions row "enforced by the `ProcessRunner`, never by the engine" — a callee spans many processes. Reject it in AD-15 or move enforcement; do not leave it silently ignored.
- AD-19 triggers on "a Story step reaches `done` and its verify step is `done` or `skipped`" — with no `template` row, "Story step" must be redefined as "the last row under `…story.` reaches done" (or the synthetic row from F2 option (a)).

**Fix location:** AD-7 (rows vs segments), AD-9 (what `template` returns), AD-15 (reject `timeout_min`/`on_fail` on `template`, or define them), AD-19 trigger.

---

## F4 — MEDIUM — `on_fail` vocabulary, re-dispatch counter and missing state-machine edges

**Draft (§2, §3.1):** `on_fail: escalate (default) | fail | continue`, plus the object form `on_fail: { redispatch: build, max: 1 }` used by `verify` (draft is itself inconsistent; the object form is the one the skeleton needs). §6.3 asked for a separate counter.
**Spine:** the Run machine mentions `on_fail fail`; AD-9's `StepResult.next: Redispatch | None` implies the object form; **the "own counter" decision is not written anywhere**, no `on_fail` enumeration exists, and the step machine lacks the edges these values need:

| Draft behaviour | Edge missing in AD-8 step machine |
| --- | --- |
| auto-retry on `expect` miss with `retry.max` remaining | `error --> queued: auto-retry (retry_count < max)` — today only the operator signal `retry` re-queues |
| `on_fail: {redispatch: build}` | the target row is already `done`; needs `done --> queued: redispatch (redispatch_count < on_fail.max)` and the `verify` row returning to `planned`/`queued` |
| `on_fail: continue` | Run proceeds past a row in `error`; today `error` is terminal for the walker unless a signal arrives |
| `on_fail: fail` | present on the Run machine, absent on the step machine (`running --> error` then Run `failed`) |
| Skip story / Skip epic on rows not yet started | `planned --> skipped`, `queued --> skipped` — today `skipped` is reachable only from `running` |

Also unstated: the two counters as columns (`step_run.retry_count`, `step_run.redispatch_count`, both reset to 0 on operator `retry`?), the exhaustion reasons (`expect failed after {max+1} attempts`, `verify failed after {max+1} re-dispatches`), and the draft's "configuration failures (FR-16 list) are never retried".

**Fix location:** AD-8 (both machines; add the five edges), AD-9 (enumerate `on_fail ∈ {escalate, fail, continue, {redispatch, max}}`; `Redispatch` carries the target path), entity notes (counters), AD-15 (validator: `redispatch` target must be an earlier `agent` step in the same template file; `retry` requires `expect`; both only on `agent`).

---

## F5 — MEDIUM — Item scoping ("variables do not inherit"), `item` type, entity fields, and standalone start

**Draft (§4):** "A callee sees only what its caller passes in `inputs`; item bindings are explicit inputs of type `item`." "`epic` and `story` remain startable directly from *New workflow*."
**Spine:** AD-15 lists "unbound variable" and "callee input mismatch", which *implies* strict scoping but never states it; the `item` input type is absent; nothing says which entity fields `{{repository.*}}` / `{{project.*}}` expose (`install_command`, `quality_gate_command`, `default_branch`?); and a Template with a required `item` input (`story@1`) cannot be started from a form — there is no list to bind it from — which contradicts "startable directly" unless the spine says how (e.g. the form takes `stories.yaml` path + story id and binds one item).

**Fix location:** AD-15 rule (add: "a callee's scope is exactly its declared inputs; `for_each … as` binds one variable of type `item` visible only in that block; no ambient variables"), AD-7 (`plan_run` builds one scope per call frame), Conventions (a row "Template variables": input types `project | repository | string | path | enum | item`, the entity fields exposed, `path` = repo-relative POSIX, `..` rejected), FR-8/UJ mapping (which shipped templates are startable: those whose required inputs are form-bindable; `item` bindable only from a list file + id, or not at all).

---

## F6 — MEDIUM — No port for reading repository files; four rules depend on one

`expect.files` globbing and frontmatter parsing (draft §2), reading `stories.yaml` / `epics.yaml` (F1), writing `project-context.md` (spine FR-15 row says "via `Git`/fs port"), and the commit-guard's protected-path check all read or write the worktree from `application/`. The declared port list (`ports/{engine,harness,git,process,gateway,tracer,clock,repositories}.py`) has no filesystem port, and AD-18 requires unit tests to run on in-memory fakes only. Add `Workspace` (or fold into `Git`): `glob(cwd, pattern)`, `read_text(cwd, path)`, `write_text(cwd, path, text)`, plus `read_file(ref, path)` from F1. One fake in `tests/unit/fakes/`.

**Fix location:** AD-14 (port list), Structural Seed `domain/ports/…`, AD-18 fakes.

---

## F7 — LOW — Validator rules the draft states that AD-15 does not

- "One `for_each` per Template" (draft §2) — AD-15 rejects *nested* `for_each` only; two sibling loops are not rejected.
- "Unbound variables are reported with the calling Template's line" — Conventions → Errors carries `{path, line?, reason}` with no template/version; cross-template errors need `{template, version, path, line, reason}`.
- `template.with.version` must be an integer literal (no `latest`) — implied by AD-15's "a Run resolving a changed callee" but not stated.
- `gate` enum (`liveness | deterministic | human`, missing → `unvalidated`) — `unvalidated` is not in Conventions → Status tokens; what a `gate: human` step does at runtime (always `checkpoint` after done?) is undefined.
- `expect.files` "each glob must match exactly one file" — fine as an `agent.py` rule, but say it in AD-10/AD-9 so it is not re-invented per harness.
- The draft's `retry.resume_session` key: with the harness-capability fallback decided, say whether the key is dropped (recommended) or kept as an override.

**Fix location:** AD-15 list, Conventions → Errors and Status tokens, AD-9 agent step.

---

## F8 — LOW — Per-epic push/PR, cost roll-up by path, worktree switching details

- **PR links:** draft records "the compare URL on the Run"; with n epics there are n URLs and the card reads `n/n epics · m/m stories · k PRs`. Say that `pr.link` writes the URL to its row's `output_ref` and the Run's links/counts are derived from `pr.link` rows by path (no `run.pr_url` column).
- **Cost roll-up:** draft "spans nest by path; cost per epic / initiative are sums". AD-11 makes every attempt a child span of the Run trace (flat). Either nest spans per path segment (one span per `template` call / item) or state that Langfuse is flat and roll-ups are SQL sums of `attempt.cost` grouped by `step_run.path` prefix. Add the roll-up rule to Conventions (no stored totals).
- **Worktree switching (draft §4, §6.4):** worktrees keyed by branch is decided, but the spine does not say (i) `git.worktree` is idempotent — existing worktree → `sync`, dirty tree → `error`; (ii) which worktree is `StepContext.cwd` for a row — the worktree of the nearest preceding `git.worktree` in path order (`run.current_worktree`), and rows before any `git.worktree` have no cwd (validator: `shell`/`agent`/`git.*` other than `git.worktree` require a preceding checkout in the same or an ancestor template); (iii) when `remove_worktree` / `delete_branch` are ever called (never in MVP?).
- **"Frozen" (AD-15) vs immutable:** every version is already immutable (save = n+1); say what "frozen" additionally prevents (deleting the version / the template) or drop the word.
- **Skip epic (AD-13 `skip_epic`):** the signal exists; its effect on rows is not stated — "all remaining rows under the enclosing `epics[i]` path, including `push` and `pr`, become `skipped`; the walker continues at `epics[i+1]`" (draft: "skip remaining stories, no push").

**Fix location:** AD-11, AD-13, AD-14, Conventions (new rows: PR links, cost roll-up, step cwd).

---

## Coverage check (draft item → spine status)

| Draft item | Spine | Note |
| --- | --- | --- |
| Step vocabulary / kinds | AD-9 | governed (`uses:` rename) |
| `gate` values, `unvalidated` | — | F7 |
| `timeout_min` defaults | Conventions | governed; `template` case F3 |
| `on_fail` values | partial | F4 |
| `expect` / `retry` semantics | AD-10, decided fallback | machine edges F4; `resume_session` key F7 |
| `for_each` options, `as`, `item` type | — | F2, F5 |
| "Variables do not inherit" | implied | F5 |
| `pause_*_item_when`, item checkpoints | — | F2 |
| Transitive pinning | AD-15, `template_version.calls[]` | governed; "frozen" wording F8 |
| Validator: cycles, depth>3, `parallel`, unbound, mismatch | AD-15 | governed; gaps F7 |
| Skip epic | AD-13 | signal exists; row effect F8, edges F4 |
| Per-epic push/PR | AD-14 `git.push` | link storage F8 |
| Cost roll-up by path | — | F8 |
| Standalone `epic` / `story` | seed lists the files | `item` binding F5 |
| `epics.yaml` shape | AD-17 (protected only) | plan-time errors F1 |
| §6.1 template as step | AD-9 | rows / aggregate F3 |
| §6.2 retry without resume | decided | not written in spine text — add to AD-10 or AD-9 agent |
| §6.3 verify counter | decided | not written in spine text — F4 |
| §6.4 worktree per branch | AD-14 | idempotency / cwd F8 |
| Lazy expansion vs full plan | AD-7 | F1 (source of list files) |
