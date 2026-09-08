# Epic 5 handoff — the unattended dev loop, and the one thing it has not proved

Written 2026-09-08, after story 5-11. For whoever builds Epic 6 and after.

`epic-1-handoff.md` … `epic-4-handoff.md` all still hold; nothing in them was undone here. Read this
once before your first Epic 6 story; you should not need it again.

Eleven stories were dispatched. **Ten landed with every gate green. Story 5-11 halted `blocked`, and
that is the honest state of the epic** — the loop is built and unit-proved end to end, but it has
never once run a real coding agent against a real Gateway. §6 is the runbook that closes it.

---

## 1. What you can rely on

The agent step exists and is wired from the walker down to the process group.

```
domain/ports/harness.py         start(...) -> HarnessHandle · wait(handle) -> HarnessResult
                                run == wait(start(...)) · resume · resume_command · capabilities
domain/ports/tracer.py          create_run_trace · step_span · attempt_span · attempt_observed · trace_url
domain/ports/gateway.py         spend_for_attempt -> AttemptSpend (never raises)
domain/ports/trajectories.py    add · list_for_project — no update, no delete
infrastructure/harness/         env.py (env_for) · registry.py (build_harnesses) · claude/{adapter,result}.py
infrastructure/tracing/         langfuse_tracer.py
infrastructure/gateway/         litellm_spend.py
application/steps/agent.py      prepare → dispatch (396 lines)
application/steps/agent_tail.py protected paths → route → spend → budget (400 lines)
application/rules/              routing.py · protected_paths.py · budget.py — all 100 % branch
application/story_file.py       the story-file contract: find it, keep it unambiguous, read it
application/use_cases/          spend.py · record_trajectory.py · harness_readiness*.py
```

**The executor's order is load-bearing and pinned.** `agent_tail.tail` runs the protected-path check,
then `route(...)`, then spend and the budget rule. A frozen assertion reads `inspect.getsource(tail)`
and requires the marker order `"5.6" < "route(" < "5.7"`. FR-31 needs the anchor check to win over
every route, so do not reorder those.

**All eleven FR-16 routing rows have a named unit test each.** No story file → `misconfigured · no
story file`; two files → `ambiguous story file: a.md, b.md`; unparseable frontmatter, seven
configuration conditions, `blocked` (the whole `## Auto Run Result` becomes the Question),
`done` + exit 0 (the only way forward), `ready-for-dev` at a spec checkpoint, unexpected status with
and without retries left, non-zero exit with and without retries left.

**Two migrations:** `0008_harness_readiness`, `0009_trajectory`. Both survive `make durability`.

**Two settings:** `LANGFUSE_PROJECT_ID`, `READINESS_BUDGET_USD`. One dependency: `langfuse==4.15.1`.

---

## 2. Decisions that are load-bearing — do not undo these by accident

**`Harness.run` is exactly `wait(start(...))`.** Story 5-1 built `run` as one call; AD-14 requires
`attempt.pgid` recorded *before* the process is awaited, which that shape cannot serve. 5-4 split the
port into `start`/`wait` and kept `run` as their composition, so 5-1's frozen tests still pass. The
executor commits `pgid` and `session_id` between the two, and kills the group if that commit raises.
**Cancel does not work without this.**

**`_frame_start_sha` answers the lowest-`n` attempt that has a `start_sha`.** It used to answer the
frame's first row-with-attempts, which for a story frame is `git.sync`'s `None` — so `frame_start_sha`
was `None` on every attempt and AD-17's read side was dead. That is AD-17's own wording, and it is the
attempt `agent._start` writes `frozen_test_files` on.

**`frozen_test_files` is computed with pathspec `"."`, never `""`.** `""` is not a valid git pathspec;
`SubprocessGit.list_files` reports a refusal as `()`, which would have silently produced an empty
frozen set on every Run with no gate failing. The constant is `WHOLE_TREE`.

**`git status` runs with `--untracked-files=all` and `-c core.quotePath=false`.** Porcelain otherwise
collapses a new anchor inside a new directory to `?? dir/`, and quotes non-ASCII paths — both let an
agent's anchor edit escape the check.

**Project variables cannot override `HOME`/`PATH`/`LANG`/`TERM`, nor switch on `OTEL_LOG_*`.** The
merge order is project_env → base → contract → aliases, with `FORBIDDEN_PREFIXES = ("ORCHESTRATOR_",
"OTEL_LOG_")`. Content logging is the Project's switch, not a variable's.

**`Project.builtin` is derived from `slug`, not a column.** A frozen assertion pins the `project`
table to an exact nine-column set; deriving the field avoided an anchor edit entirely.

**`evaluate` fires from `WalkerDeps.on_terminal`, a second hook**, not from `run_finished` — whose
`DONE`-only gate is frozen. `on_terminal` fires on `done`/`failed`/`cancelled`.

**Trajectory is append-only three ways:** the repository exposes only `add`/`list_for_project`, `add`
reads back by `(run_id, frame)` before inserting, and the table carries `unique(run_id, frame)`. It is
written when a Story frame's commit-guard row reaches `done` — `end_sha` is only a fact once the
commit-guard has run, and by construction it never runs until build is `done` and verify is
`done|skipped`.

---

## 3. The rules that will bite you

**Five modules sit at exactly 400/400 against a hard cap `test_source_limits` enforces**:
`steps/agent_tail.py`, `steps/context.py`, `use_cases/walk.py`, `use_cases/run_views.py`, and
`use_cases/run_graph.py`. `main.py` is 399, `api/schemas/run_views.py` 399, `apply_step_result.py` 394.
**Every story in the back half of this epic had to displace something to add anything, and what got
displaced was usually explanatory prose.** That is a slow erosion of the codebase's own rationale and
it should be fixed with a deliberate split before Epic 6 adds to these modules, not with more trimming.

**`tests/unit/fakes/` is the one part of `tests/` that may be extended.** Additively only: new members,
new defaulted parameters, extended docstrings — never a changed or removed member, default or
assertion. `fakes/{clock,git,workspace}.py` grew this epic under that rule. Everything else under
`tests/` is frozen, including every `web-client/tests/**` spec.

**Adding a new test to an existing test file is an anchor violation.** Story 5-2 did it, was caught
before committing, and the coverage moved to a new module with the frozen file restored byte-identical.
New coverage goes in a new file. Always.

**`web-client/src/api/schema.d.ts` is generated (AD-3).** It comes only from `make openapi` /
`pnpm gen:api`. Hand-editing it is forbidden.

**`make e2e-ui` and the dev stack both bind 4321.** Run `make down` first. Story 5-11 lost a gate run
to this.

---

## 4. Known gaps, honestly

**The budget park was inert until the last commit of this epic.** Story 5-7 guessed
`CAP_EXIT_FIELD = "stop_reason"` / `CAP_EXIT_VALUE = "max_budget"` for the `--max-budget-usd` cap stop.
5-11 read the shipped Claude Code 2.1.258 bundle and **disproved** it: `"max_budget"` occurs zero times
anywhere in the bundle, and `stop_reason` carries `stop_sequence`/null. The bundle's own error-result
schema declares `subtype: "error_max_budget_usd"`, emitted on `terminal_reason === "budget_exhausted"`.
Corrected under operator authorisation, with a negative test asserting the old pair is *not* read as a
cap stop. **The lesson is bigger than the constant: a value that only a live run can confirm should not
ship as a plausible guess behind a passing test.**

**A resumed dispatch records no `pgid`, and `Harness.resume` takes neither `model` nor
`budget_usd_remaining`.** So orphan control cannot reap a retry that a dead backend interrupted, and
CAP-7's "never exceeds its budget by more than one attempt" does not hold across a resume. Closing it
changes `Harness.resume`'s signature, which 5-1's tests freeze. **This is the largest known correctness
gap in the epic** and it needs an operator decision, not a quiet fix.

**`--max-budget-usd 0.00` is refused by the CLI** (`must be a positive number greater than 0`, exit 1,
no JSON), so an exhausted-budget dispatch fails as a harness exit rather than the budget park FR-17
intends. `0.01` and `0.001` are accepted. `test_claude_adapter.py:459` asserts `"0.00"`.

**Five defects 5-11 found on the way, none fixed, all recorded in its story spec:**

1. `readiness_fixture.sh` runs `git init --bare` without `-b main` → unborn HEAD → `git ls-remote`
   returns zero lines → clone check fails → `POST /readiness` 422. A patch exists, tested green, held
   back — see below.
2. **`lists.py::read_list` records the not-yet-existing working branch**, so `plan.check` parks
   `plan_stale` on the first `epic@1` Run of any new branch. `PlanReader.record`'s own docstring states
   the opposite contract. **Epic 4 defect.**
3. **`continue` on a `plan_stale` park sets the row `running`, nothing enqueues it, `close_run` parks
   `internal` → the Run is unrecoverable.** **Epic 4/6 defect.**
4. `POST /harnesses/not-a-harness/readiness` returns **201** and creates a real Run for a nonexistent
   harness (the GET correctly 404s). This is why schemathesis created 74 Runs once the fixture worked.
5. The readiness Run binds no model, so Claude Code asks for `claude-opus-5`, which no local
   `model_list` serves. A `READINESS_MODEL` setting threaded like `READINESS_BUDGET_USD` is the obvious
   shape but needs a default nobody has chosen.

**Why the fixture patch was not landed.** Measured both ways on the same commit: `make e2e` is exit 0 /
145 passed without it, exit 2 / 5 failed with it. The failures are defects 2–4 becoming *reachable*,
not a flaw in the patch. Hard rule 6 makes a landed gate's green a precondition, so landing it alone
would block every later story. **Land it together with defect 2's fix, or not at all.**

**The Gate Record panel overflows its container** on the Run detail — long reasons run past the right
edge instead of wrapping. Visible in both epic-5 screens. Cosmetic; e2e asserts content, not layout.

**Deferred, still true:** the New workflow *re-run readiness* link is an inert `<a href>`; wiring it to
the live POST needs anchor edits in `harness-list.test.ts` and `new-workflow.spec.ts`. A Project
variable named `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` can still re-point the harness off the Gateway.
Nothing asserts the image's `HOME == AGENT_HOME`.

---

## 5. What Epic 6 inherits

Epic 6 adds the operator's replies to the parks this epic created. Four things are already decided:

- **The parks exist; the resumes do not.** `blocked`, `misconfigured`, `checkpoint`, `budget`,
  `protected_path` and `timeout` all park with exact reason texts and admitted signals. What is missing
  is Answer, Continue-on-agent-row, Skip story, Skip epic, Raise budget, Accept, and terminal signals.
- **The Run detail already renders what the read model admits.** `QuestionBlock.tsx` renders the story
  file's own Markdown through a safe allowlist parser — no `dangerouslySetInnerHTML` anywhere, so
  injected script/link/image prints as literal text. Add buttons by widening `admitted_signals`, not by
  hardcoding them. There is no `<textarea>` in the codebase; the Answer box is yours to add.
- **`run.accepted_paths[]` exempts a path from the protected-path rule by exact match**, checked before
  any protection test. The Accept branch is code without a caller until Epic 6 wires the signal.
- **`StepResult.payload["hits"]` carries the protected-path hits** and reaches the gate record, but
  `GateRecordOut` drops `payload` — nothing reads it yet.

Defects 2 and 3 in §4 will strand a Run in Epic 6's own territory. Fix them before building on top.

---

## 6. Runbook — closing story 5-11

5-11 is not an implementation story. Its whole scope is running the readiness Run for real and
recording what it shows. It halted because **the host cannot serve a model call**, not because of
anything in this repository.

**Two host changes are needed, each blocking on its own:**

1. **A real upstream provider credential on the Gateway.** `host/.env` carries
   `ANTHROPIC_API_KEY=not-set`, `OPENAI_API_KEY=not-set`, `OMLX_API_KEY=not-set`. Every model fails at
   the first completion — `claude-sonnet-4-6` → `401 invalid x-api-key`. `host/.env`'s own comment
   says the proxy answers `/health` and `/v1/models` without them, which is all the harness `doctor`
   check requires, which is why this stayed invisible. Set one real key and restart the LiteLLM
   container.
2. **Langfuse out of v4 `events_only` mode.** `/api/public/observations` and `/api/public/traces` both
   answer `404 — not available on deployments running in Langfuse v4 events_only mode` on this 4.27.0
   instance. `attempt_observed` *is* `observations.get_many(...)` and answers `False` on any failure,
   so readiness line 3 `trace observed` can never be `ok` here. Ingestion is unaffected; only reads.

**The orchestrator's own five credentials are already provisioned and verified** in the root `.env`:
the Langfuse pair (200 on `/api/public/projects`), `LANGFUSE_PROJECT_ID=ai-orchestrator`,
`LITELLM_SPEND_KEY` = the host master key, and `LITELLM_API_KEY` = a minted `key_type: llm_api` virtual
key aliased `ai-orchestrator-harness-epic5`. **Values copied out of `host/.env` carry inline `#`
comments that must be stripped** — unstripped they read as 73 characters and fail auth silently.

**Then:**

```bash
make down && make up
curl -s -X POST -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  localhost:8000/api/v1/harnesses/claude/readiness
# poll GET /runs/{id} until terminal, then:
curl -s -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" localhost:8000/api/v1/harnesses
```

Expect `claude · enabled`, `last_readiness_at` set, every evaluation line `ok`. Apply defect 1's
fixture patch first (recorded verbatim in 5-11's story spec) or the Run will 422 — and land it with
defect 2's fix, per §4.

**PRD §8, as it stands:**

| # | Item | State |
| --- | --- | --- |
| 1 | allowlist under `--permission-mode dontAsk` | open — no agent row ever ran |
| 2 | trace continuity via `attempt_observed` | open — and not closable while Langfuse is `events_only` |
| 3 | skill discovery from the worktree | **closed, positively** — 49 stubs in the image, `bmad-build-auto` resolved from a fixture clone; the `SKILL_STUBS_INTO_WORKTREE` fallback was not needed and was not built |
| 4 | spend and session headers coexist | open — no spend row |
| 5 | two keys | **closed** — harness key `403` on `/spend/logs/v2` (`Only allowed to call routes: ['llm_api_routes']`), spend key `200` with real rows |

All FR-14 flags were confirmed against **2.1.258 in the image**, closing the gap 5-1 disclosed when
only 2.1.236 was reachable on the host. Spend for the whole attempt: **$0.00** — nothing was billable.
