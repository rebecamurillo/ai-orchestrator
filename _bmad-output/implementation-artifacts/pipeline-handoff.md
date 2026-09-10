# Running an epic through the orchestrator itself

Written 2026-09-09, after Epic 6. Corrected 2026-09-10, after Epic 7. This is the handoff for the
first epic the orchestrator builds rather than an assistant. It records what must be true before a Run
can start, where the line falls between what an agent does and what the Operator does, and what to
expect the first time.

**Correction.** This was written expecting Epic 7 to be that first epic. It was not: the Operator
chose to have Epic 7 built the established way and to test the pipeline on **Epic 8** alone. Epics 1–7
were each built by an assistant dispatching one sub-agent per story. Everything below is what changes
when the product runs its own backlog, and it now applies to Epic 8.

---

## 1. Preconditions — a Run cannot start without these

**A harness must be `enabled`.** `application/preflight/checks.py::harness_line` fails a Run that names
a harness which has no row or is disabled, and `create_run` refuses on that line. The only thing that
flips it is a readiness Run that passes all six evaluation lines. **So the readiness session comes
before the first orchestrator-run epic, not after it.**

Two code gaps that made readiness impossible were closed on 2026-09-09 and are described in
`deferred-work.md`:

- the readiness Repository is seeded with **no quality gate**, so `baseline` no longer kills the Run
  before an agent is ever dispatched (the Operator's ruling: readiness proves the harness, not the
  repository, and `enabled` means "this harness works");
- `READINESS_MODELS` binds a **per-harness** model — `claude=claude-sonnet-4-6,codex=gpt-5.4,local=local-coder`
  — because one global value cannot be right: Codex cannot run an Anthropic model and `local` is served
  from the host.

**What remains is not code.** No readiness Run has ever been observed against a live harness. Reaching
`enabled` still needs the host stack up, Langfuse reachable, `LITELLM_SPEND_KEY` able to read
`/spend/logs/v2`, the agent actually finishing the fixture story, and `git.push` to the local bare
fixture origin — a path that has never run. That is story 5-11, and it is an Operator session.

**Every environment file needs `READINESS_MODELS`.** It is a required setting and
`scripts/generate-env.sh` never rewrites an existing file. The repo's `.env` and `.env.e2e` were
updated by hand; any other checkout or deployment needs the line or backend-api will not boot. CI is
fine — it copies `.env.example`.

---

## 2. Where the line falls

**An agent writes code. It never runs a real coding agent, never reconfigures the host, and never
records an outcome nobody observed.**

Three stories are Operator-run: **5-11** (Claude readiness, still open), **7-2** (Codex readiness) and
**7-4** (OpenCode readiness plus host model serving). All three are open as of 2026-09-10; 7-2 and 7-4
each landed their code and a runbook and then halted `blocked`, exactly as described below. The two
runbooks are in their story specs under `epics/epic-07-harnesses/stories/`, and they are what the
Operator session follows. Their briefs each open with an *Operator and agent
split* section. The shape is the same in all three, and it uses the gates Epic 6 built rather than
inventing a mechanism:

1. **The agent, in one dispatch:** writes the code the fallbacks need, unit-covered over fakes; commits
   a runbook into the story spec — the exact commands, what to read in each output, and what each
   outcome forces as a decision; then **halts `blocked`**, its Blocking condition naming exactly what the
   Operator must run and the facts to report back.
2. **The Operator runs it**, with the assistant reading the output alongside them, and **Answers** the
   parked story with what was observed.
3. **The agent, resumed with that Answer**, records the dated verified block in `addendum.md` §B from the
   reported facts, lands whatever fix the outcome forces, and finishes the story.

That is the Answer gate working as designed: a blocked story, a paragraph from the Operator, and a
re-dispatch that carries it as planning context.

**The rule an agent must not break, and the reason it exists.** Never ship a value only a live run can
confirm. Epic 5's story 5-7 shipped `stop_reason: "max_budget"` as a plausible constant behind a
passing test; story 5-11 later read the shipped Claude bundle and found the string occurs nowhere in
it. A halt is cheap. A plausible wrong constant behind a green gate is not.

Stories **7-1** and **7-3** (the Codex and OpenCode adapters) are fully implementable, but their argv
shape, session-capture event and exit-code semantics can only be *confirmed* against the real CLI.
Where a value is unknown, leave it unset and halt rather than guessing.

**Epic 8 needs no split at all.** All six stories are read-model and UI work; none touches a live
service.

---

## 3. What to expect the first time

**The Run will park often, and that is the feature.** AD-17 parks a Run whenever an agent's attempt
touches a protected path — every `AGENTS.md`, every existing test file. Epic 6 needed **five** anchor
rulings from the Operator across eight stories. Under the orchestrator each becomes a `protected_path`
park to Accept, or a `blocked` park to Answer, from the Run detail.

The Operator chose to keep it that way: **park and ask every time.** No pre-authorised class, no
batching. It means more stops, but every frozen assertion is seen before it changes — and the first
epic is as much a test of the gates as a way to get Epic 7 built.

**What each stop will look like**, from Epic 6's own experience:

| Park | Why it happened in Epic 6 | The Operator's reply |
| --- | --- | --- |
| `blocked` | A frozen test contradicted the story's own brief | Answer with the ruling |
| `protected_path` | The story needed to edit a frozen test to land its gate | Accept the files, or Retry after reverting |
| `checkpoint` | A `spec_checkpoint` story finished planning | Continue, or Reject with a reason |
| `verify_failed` | The quality gate failed twice | Retry, Skip story, or fix the tree by inline edit |

**Four things Epic 6 learned that an unattended run will re-learn expensively if nobody says them.**
They are not in `AGENTS.md` — the Operator chose not to edit the constitution — so they belong in a
story's brief when it is relevant:

1. **New coverage goes in a new test file.** Adding a test to an existing one is itself an anchor
   violation, and it will park the Run.
2. **Split a capped module, never trim it.** Several modules sit at exactly 400 lines against
   `test_source_limits`. Epic 5 bought space by deleting its own explanatory prose.
3. **A new endpoint goes in a new sibling router**, never into `api/routers/runs.py`, whose route count
   is pinned.
4. **Do not pin behaviour a later story's brief owns.** Epic 6's story 6-1 wrote a test guessing at
   6-2's behaviour, guessed wrong, and cost the epic a halt and a ruling.

---

## 4. The order of work

Superseded 2026-09-10. Steps 1, 2 and 4 happened differently: PR #6 merged, the readiness fixes went
to their own PR, and Epic 7 was built the established way rather than by the orchestrator. What
remains:

```
1. ✅ Merge PR #6                     Epic 6, green
2. ✅ Epic 7 built                    7-1, 7-3, 7-5, 7-6 landed; 7-2, 7-4 halted blocked
3. Host change · Langfuse             leave events_only mode      ← blocks everything below
4. Operator session · 5-11, 7-2, 7-4  claude, codex, local readiness — one sitting
5. Orchestrator runs Epic 8           the first epic the product builds itself
```

**Step 3 is the real gate, and it is new.** Story 7-4 found the host Langfuse in v4 `events_only`
mode: every public read API answers 404, so `attempt_observed` can only ever return `False` and the
`trace observed` evaluation line cannot pass for *any* harness. Until that changes, no readiness Run
can reach `enabled` — and until a harness is `enabled`, `preflight/checks.py::harness_line` refuses
every Run, so the orchestrator cannot start one at all. See `epic-7-handoff.md` §2.

Step 4 is one sitting for all three harnesses, which is what the Operator chose: batch the
real-harness runs rather than interrupt the pipeline three times. `oMLX` must be running for `local`;
`host/litellm.config.yaml` already carries both `LOCAL_MODELS` aliases and needs no change.
