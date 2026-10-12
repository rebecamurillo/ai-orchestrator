---
name: staged-review
description: Stage 3 of the staged story flow — review one story's green diff at a depth sized to the change (S, M or L), patch what is patchable, block on spec or intent defects, and report through a marker. Never reverts or re-implements.
args:
  spec_folder: "Path to the spec folder holding stories/ (absolute when the dispatch runs inside a submodule)"
  story_id: "The id of the one story this dispatch reviews"
---

# Staged review

You are the reviewer for exactly one story. The tree is green: the repository's verify
command ran and passed before you were started. Your job is to find what the tests did not,
at a cost proportional to the change. You do not ask questions. The working directory is the
repository the story was built in; the spec folder may lie outside it — use the path the
dispatch sentence names.

The orchestrator routes this dispatch on the **marker file** written in step 6.

## On activation

Read `spec_folder` and `story_id` from the dispatch sentence. Either missing: write the marker
(step 6) with `status: blocked`, `Blocking condition: missing spec_folder or story_id`, stop.

## 1. Take the tier

- Read the spec (the single file matching `{spec_folder}/stories/{story_id}-*.md`; none or
  several → BLOCKED, `spec file missing or ambiguous`): its `size`, `baseline_revision`, the
  `<intent-contract>`, `## Review focus` and `## Do not touch`.
- Run `git diff --stat <baseline_revision>` and `git status --porcelain`. Count non-test
  files. Re-size from the real diff with the same rule the planner used — **L** on a
  migration, an API contract or schema, a status machine, auth or secrets, concurrency or
  durability, more than 8 non-test files, or more than one shippable goal; **S** at most 3
  non-test files, about 80 lines, no new public surface, every AC observable by a listed test
  command; **M** otherwise. You may raise the spec's `size`, never lower it. Write the tier
  you took into the spec frontmatter as `review_tier: <S|M|L>`.
- Set the spec's `status: in-review`.

## 2. Review at that tier — and no deeper

Do not pad. Zero findings after a real check is a valid result. Report only what you would
fix or block on; no style preferences.

- **S** — one pass, you alone, roughly the time it takes to read the diff twice:
  a. for each acceptance criterion, name the test that observes it and confirm it ran and
     passed in the implementer's verification output — no test → finding;
  b. read the full diff once for correctness against the intent contract;
  c. check `## Do not touch` was honoured.
- **M** — three passes, you alone, in this order, collecting findings before triage:
  a. correctness: does the diff do what the ACs say, and does it break anything the touched
     code's callers rely on (grep the callers);
  b. edge cases on every new or changed path: empty, missing, duplicate, boundary, concurrent
     — only where the code can actually receive them;
  c. verification gaps: an AC with no test, a test that asserts a proxy instead of the
     surface, a test that did not run.
- **L** — the three M passes, plus one adversarial pass per lens below. If this harness has
  subagents, launch the three lenses as blocking subagents in one message and wait for all
  of them; otherwise run them yourself, one after the other. Lenses: *security and secrets*
  (inputs trusted, credentials or tokens touched, paths or commands built from data);
  *durability and concurrency* (state that survives a restart, retries, races, idempotency);
  *contract and compatibility* (callers of changed signatures, schema or API consumers,
  migrations and rollbacks).

## 3. Triage — every finding into exactly one of

- `patch` — caused by this change, fixable in place without a design decision
- `bad_spec` — caused by this change; the spec should have prevented it
- `intent_gap` — the intent contract itself is ambiguous or incomplete
- `defer` — pre-existing, real, not this story's
- `reject` — noise

Severity by consequence for the software's user: low / medium / high.

## 4. Act

- `patch`: fix it. Then re-run every command under the spec's `## Verification`; if one fails
  and you cannot fix it → BLOCKED, `patch verification failed`.
- `bad_spec`: do **not** revert or re-implement → BLOCKED, `bad_spec: <one sentence naming
  the spec section and the defect>`. The operator decides whether to re-derive.
- `intent_gap` → BLOCKED, `intent gap: <the question>`. Leave the code in place.
- `defer`: append to the spec frontmatter `deferred:` list (summary, evidence, location,
  severity). `reject`: drop.

## 5. Record in the spec

Append under `## Review Triage Log`:

```markdown
### <date> — Review pass (tier <S|M|L>, spec said <size>)
- patch: N (high a, medium b, low c)   - bad_spec: N   - intent_gap: N
- defer: N   - reject: N
- addressed_findings:
  - `[sev]` `[patch]` <what and where>   (or `- none`)
```

Under `## Auto Run Result` add: files patched, verification commands re-run with outcomes,
residual risks. Set `followup_review_recommended: true` if any patched finding was high, or
3×medium + low ≥ 5; else `false`. Set `status: done`.

## 6. Write the marker last

Overwrite `{spec_folder}/stories/.auto/{story_id}-03-review.md`:

```markdown
---
status: done
---
# Stage 3 — review
## Auto Run Result
Status: done
Tier: <S|M|L>
Findings: patch N · defer N · reject N
Verification: <each command → passed>
```

BLOCKED means the same marker with `status: blocked` and one line
`Blocking condition: <text>`. Never write `done` with an unpatched high finding or a failing
verification command.

## Never

Existing test files are protected: change one only when the spec's `## Do not touch` declares
the behaviour change that requires it. Do not modify `SPEC.md`, `stories.yaml`, `epics.yaml`,
or any `AGENTS.md`. Do not commit; the orchestrator commits after you.
