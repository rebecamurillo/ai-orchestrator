# Forged idea — AI agent workflow OS (ai-orchestrator)

Outcome: **HARDENED**. Attack mode. Survives, with scope cut and two gates relocated.

## What it is (after forging)
An asynchronous specification-and-verification cockpit. A human defines and challenges the need
(AI-assisted), the pipeline runs unattended, the human time-slices to other work and returns at
**epic** completion to validate and test. Not "an OS that replaces engineering" — a system that
moves a senior engineer from writing code to specifying and verifying it, across parallel pipelines.

## Locked
- Human gates are **asynchronous**; parallelism across projects is what amortizes the human ceiling.
- Unit of human return is the **epic**, not the story or the PR.
- Human-approved acceptance criteria **precede** code generation. This is what makes the oracle independent.
- Oracle = Playwright E2E in a prod-like dockerized env with a real DB. Then human QA of the running feature before merge.
- Fixes go to a new chat session against the epic.

## Rejected, and why
- **Generic "issue -> PR" as first scenario** — half of all tickets are faster to write than to specify. PoC targets one repo, one ticket class: slow-to-write, fast-to-specify, fast-to-verify.
- **CNCF Serverless Workflow DSL interpreter (for PoC)** — DBOS is already a durable code-first workflow engine. A declarative layer on top is an interpreter you must write and maintain, and it buys nothing until workflow authors exist outside the core team. Keep YAML with a minimal internal schema; adopt the CNCF DSL when a second consumer justifies it.
- **Kestra-style visual workflow editor (for PoC)** — a product in its own right. Edit workflow YAML in git.
- **File-existence as "validation"** — that is a liveness check. It never proved correctness and must not be labelled as if it did.

## Hardening required before build
1. **Human signs the executable spec, not the prose.** If an agent translates AC -> Playwright and nobody reads the spec file, drift re-enters through the translation. Name which artifact carries the signature.
2. **Invert the escalation trigger.** Print-mode agents cannot ask, so they assume and proceed — escalating on "agent reports blocked" catches the honest agents and misses the confidently-wrong ones. Require every agent to emit `open_questions` **and** `assumptions` in its output file; escalate on either.
3. **Label gate strength in the orchestrator.** Every step declares liveness / deterministic-oracle / adversarial / human. Any stage with no oracle is explicitly marked unvalidated rather than shown green.
4. **Isolate the E2E environment per run** (ephemeral DB or schema-per-run, dynamic ports), or serialize runs per repo. Flake that reads as failure destroys trust in the red signal faster than any bug.
5. **Cap the rework loop** (e.g. 2 fix cycles) then hand to a human. Otherwise a wrong premise burns budget indefinitely.
6. **Front-end PoC scope is the review inbox**, not the workflow designer: what needs my gate, on which project, with enough context to reload cold. This is the feature the async model actually depends on.
7. **Do not rely on harness session-id resume.** That state is container-local (`~/.claude/projects`); container death or the stated v2 multi-container plan destroys it. Persist the transcript and the inputs needed to *reconstruct* a session.

## Success metric for the PoC
**Human-minutes per merged PR, versus the same person writing it by hand.** Instrumented in Langfuse
from day one, same trace id. "It produced a PR" is not the metric. If the ratio is ~1.1x on the
easy ticket class, the idea does not survive contact with the hard class.

## Surviving weak point (unresolved)
The central bet is untested: that an epic-sized batch of agent work can be validated by a human in
materially less time than writing it, **once cold context-reload cost is counted**. Time-slicing
away and back is exactly where careful review degrades into rubber-stamping. Nothing in the design
detects a gate that has quietly become a formality.

Second-order, unargued: **cross-repo ownership.** Whoever owns repo #2 owns the PRs this opens.
If they must run their own AC gate, "multiple projects" is multiple humans doing gates — a tool each
team installs, not a portfolio system. Different product, different justification for an engine.
