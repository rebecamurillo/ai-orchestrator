---
title: 'Harness readiness'
type: 'feature'
created: '2026-09-08'
status: 'blocked'
review_loop_iteration: 0
followup_review_recommended: false
context: []
warnings: []
deferred: []
---

# Harness readiness

## Auto Run Result

Status: blocked

Blocking condition: anchor conflict — the brief's `GET /harnesses` requirement permanently
falsifies an existing, unnamed-successor test.

**What was investigated (no code written; tree is clean).** Read `SPEC.md` (CAP-8) and
`briefs/5-8-harness-readiness.md` only, per the dispatch instruction. Two parallel
subagents mapped the harness/project domain, migrations, `create_run`, the walker finish
hook, settings, routers/schemas, fakes and tests (agent 1), and the fixture-repo pattern,
`scripts/harness/`, the `bmad-method install` step, `stories.yaml`'s real schema
(`REQUIRED_FIELDS`), and the web-client New workflow page (agent 2). Both are already
scaffolded for this exact story: `HarnessList.tsx`'s own docstring names
`POST /harnesses/{name}/readiness` as the route that "regenerates the contract and is the
one that wires the action," and `web-client/src/lib/newwf/state.ts` already has
`harnessLineText`/`readinessHref`/the exact line format the brief specifies.

**The blocking conflict.** The brief's binding rule ("Endpoints") requires:
`GET /harnesses` → items now with `last_readiness_run_id` and `lines` of the last
evaluation. `evaluate()`'s own binding rule requires it to write `last_readiness_at` and
`last_readiness_run_id` **unconditionally** ("always... Written only here") whenever it
runs, pass or fail — i.e. after *every* readiness Run reaches a terminal status, not only a
successful one.

Two existing, already-landed test files close the `GET /harnesses` item shape to exactly
five keys, unconditionally, over every item in the response:

- `backend-api/tests/e2e/test_harnesses.py::test_the_response_is_the_one_list_envelope`
  (from story 4-3, `git log` confirms):
  ```python
  for item in body["items"]:
      assert set(item) == {"name", "enabled", "last_readiness_at", "failing_check", "version_pin"}
  ```
- `backend-api/tests/unit/test_harnesses_router.py::test_harness_out_of_renders_every_field`
  (same commit, `6cd8eca`), same closed 5-key `HarnessOut.model_dump()` assertion. This one
  alone is avoidable — a new response schema that leaves `HarnessOut` itself untouched
  would not falsify it.

The e2e one is not avoidable by schema-naming or by making the two new fields
optional/omit-when-null: the whole point of this story is that a readiness Run actually
runs and `evaluate()` writes `last_readiness_run_id`/`last_readiness_at` on that harness's
row — non-null, permanently, from that point on. Once that happens (in this story's own
`make e2e-api` coverage of `POST /harnesses/{name}/readiness`, and inevitably in any real
use thereafter), every subsequent `GET /harnesses` response for that harness carries the
two extra keys and this test fails for good, not just at diff time. Neither test names
story 5-8, or any story, as the thing that later revises its assertion, so none of hard
rule 1's three narrow exceptions (pending-gate registry, placeholder assertion, or
nondeterministic assertion) apply. Routing the two fields onto a different endpoint than
`GET /harnesses` would satisfy the test but silently deviate from the brief's explicit
"Endpoints" text — an unattended decision I'm not authorized to make (rule 5).

**A second, non-blocking finding worth carrying forward if this is unblocked.** The
brief also requires `evaluate` to run "for every Run of Project readiness (any terminal
status)" via the walker's finish hook. Today `infrastructure/dbos/walker.py::_finish` only
calls `deps.run_finished` when `status == DONE` — pinned by
`tests/unit/test_dbos_walker_on_finished.py::test_the_hook_is_not_called_when_the_run_does_not_reach_done`,
also unnamed-successor. This one *is* resolvable without touching that test or that gate:
add a second, new `WalkerDeps` callable (e.g. `on_terminal`), invoked for every terminal
status regardless of `DONE`, wired only for Project `readiness` evaluation — the existing
`run_finished` gate and its test stay exactly as they are. Flagging it here so the next
attempt doesn't have to re-derive it, and because it's the kind of "extend the finish hook"
instruction the brief actually gives (implementation notes: "extend
`use_cases/run_finished.on_finished` (4.10) with the readiness branch") that turns out to
need a second seam rather than reuse of the first, once the "any terminal status" clause is
taken literally against the DONE-only anchor.

**Third, minor, non-blocking finding.** The brief's fixture rule says
`scripts/readiness_fixture.sh` appends "the two gitignore lines," but the already-landed
`application/steps/bmad_install.py::IGNORED` tuple (the actual `_bmad` installer this
fixture must replicate, per AD-16) has **three** entries
(`.claude/skills/bmad-*`, `.agents/skills/bmad-*`, `.opencode/commands/bmad-*`). Not a test
conflict — no anchor asserts "two" — just a wording mismatch between the brief and the
landed behavior it must match, worth a line in the next dispatch's Design Notes.

**Files changed:** none (this file only).

**Verification performed:** none — investigation halted before any implementation. No
gate was run.

**Anchor check** (the literal command from the dispatch instructions), run before writing
this file:
```
for f in $(git diff --name-only origin/main..HEAD; git diff --name-only); do case "$f" in *test*|*tests/*) git cat-file -e origin/main:"$f" 2>/dev/null && echo "FLAG: $f"; esac; done
```
No output — no test file was touched (the diff for this dispatch is this one new spec
file only, not a test).

**What the next attempt needs from an operator:** a decision on the `GET /harnesses`
conflict. Options actually open (not decided here): (a) accept that
`test_the_response_is_the_one_list_envelope` and `test_harness_out_of_renders_every_field`
must be revised, and have the operator explicitly name story 5-8 in them first (satisfying
hard rule 1's placeholder exception before a dev pass, since dev passes may never do this
themselves); (b) move `last_readiness_run_id`/`lines` off `GET /harnesses` onto a different
surface (a per-harness detail endpoint, or fold `lines` into `failing_check`'s existing
free-text) and confirm that satisfies the brief's real intent even though it isn't what
"Endpoints" literally says; (c) some other reading of "items now with... lines" I have not
considered. This is a structural, brief-vs-anchor conflict outside an unattended dev pass's
authority to resolve (rule 5) — reported here rather than guessed at.
