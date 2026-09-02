# Building AI Agents — General Spec & Best Practices
## Model-agnostic guide (Claude, DeepSeek, Qwen, and others)

This is the foundation document for a software-development agent team that
takes work from spec to PR. It defines principles that hold across models,
then the contract every agent must follow. Per-agent role specs come later —
this is the shared ground they all stand on.

---

## 0. Read this first: what "model-agnostic" changes

Most published agent guidance assumes a frontier model (Claude, GPT). When
your executors are open-source (DeepSeek, Qwen, Llama, Mistral), four things
change, and every design decision below is downstream of them:

1. **Weaker instruction-following.** Small models drop constraints, especially
   ones stated once and far back in context. Rules must be short, repeated,
   and structurally enforced — not trusted to the model's diligence.
2. **Confident guessing over asking.** Frontier models can be coached to say
   "I'm unsure." Smaller models guess and move on. You cannot rely on the
   model to flag ambiguity — you must make guessing structurally fail (tests,
   schemas, gates).
3. **Shorter effective context.** Even with large advertised windows,
   attention degrades faster. Keep each agent's context minimal and its job
   narrow.
4. **No native tool-use in some models.** Tool/function-calling quality varies
   wildly. Verify each model handles structured tool calls before you route
   real work to it; fall back to constrained text output + a parser when it
   doesn't.

The through-line: **capability you can't assume must be replaced by structure
you impose.** A frontier model is coaxed with prompts; an open-source executor
is constrained with harnesses, gates, and deterministic checks.

---

## 1. Core principles (hold across all models)

### 1.1 An agent is a model in a loop with tools

The field has converged on a simple definition: an agent is an LLM
autonomously using tools in a loop until a stop condition is met. Everything
else — roles, pipelines, orchestration — is composition on top of this.

> Sources:
> - Building effective agents (Anthropic) — https://www.anthropic.com/research/building-effective-agents
> - How the agent loop works (Claude Agent SDK) — https://code.claude.com/docs/en/agent-sdk/agent-loop

### 1.2 Start simple; add structure only to fix an observed failure

The most-repeated advice in every credible source: do the simplest thing that
works. Don't reach for multi-agent orchestration when a single loop with good
verification suffices. Every constraint you add should trace to a failure you
actually saw.

> Sources:
> - Building effective agents (Anthropic) — https://www.anthropic.com/research/building-effective-agents
> - Loop engineering: Getting started with loops — https://claude.com/blog/getting-started-with-loops

### 1.3 Context is a finite attention budget, not storage

As tokens grow, recall accuracy drops — "context rot." This is architectural
and affects every transformer model, open-source ones sooner. Give each agent
the smallest set of high-signal tokens that lets it succeed. Prefer
just-in-time retrieval (file paths, queries the agent runs) over dumping
everything up front.

> Sources:
> - Effective context engineering for AI agents (Anthropic) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - Context rot research (Chroma) — https://research.trychroma.com/context-rot

### 1.4 Write at the "right altitude"

Two failure modes for any agent's instructions: too low (brittle hardcoded
if-else logic) and too high (vague guidance that assumes shared context the
model doesn't have). Aim between: specific enough to guide, flexible enough to
leave the model heuristics. The test: *if a human engineer couldn't decide
what to do from these instructions, the model can't either.*

> Source:
> - Effective context engineering for AI agents (Anthropic) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

### 1.5 Intelligence doesn't compound — you have to engineer memory

Models are stateless. Task 50 is the same as task 1 unless you build memory
outside the model: persistent files, notes, a project constitution re-injected
each run. This is model-independent and one of the highest-leverage things you
build.

> Sources:
> - Effective context engineering for AI agents (Anthropic, "structured note-taking") — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - Lamis Mukta, *Learning while you sleep: beyond memory to dreaming* (AI Native DevCon 2026) — https://youtu.be/tTcxVv8HHNw

### 1.6 Separate the maker from the checker

A reviewer agent with fresh context is less biased than the agent that wrote
the work — it isn't anchored to the author's reasoning. This is the single
most useful structural trick in a loop, and it matters *more* with weaker
models, whose self-assessment is less reliable.

> Sources:
> - Loop engineering: Getting started with loops (Anthropic) — https://claude.com/blog/getting-started-with-loops
> - How we built our multi-agent research system (Anthropic) — https://www.anthropic.com/engineering/multi-agent-research-system

### 1.7 Verification must be machine-checkable

An agent that self-reports "done" is only as trustworthy as the model. Replace
judgment with measurement wherever possible: tests pass, linter clean,
complexity under threshold, schema validates. Quantitative checks let a weak
model self-verify; qualitative ones don't. This is the mechanism that makes
open-source executors viable.

> Source:
> - Loop engineering: Getting started with loops (Anthropic) — https://claude.com/blog/getting-started-with-loops

### 1.8 Give explicit permission to express uncertainty — then don't rely on it

Frontier models: telling them to say "I'm unsure rather than guess" measurably
reduces hallucination. Do it. But for open-source executors, treat it as a
weak signal and back it with structure — the ambiguity should also make a test
or schema fail, so a guess can't pass silently.

> Sources:
> - Prompt engineering best practices for 2026 (Anthropic) — https://claude.com/blog/best-practices-for-prompt-engineering
> - Claude prompting best practices (docs) — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

---

## 2. Loop types — choose deliberately per agent

| Loop | Stops when | Use for |
|---|---|---|
| **Turn-based** | Model judges it's done or needs input | Exploration, one-off tasks; you still check |
| **Goal-based** | An evaluator confirms your criteria, or a turn cap hits | Tasks with verifiable exit criteria (most dev agents) |
| **Time-based** | You cancel, or the work completes | Recurring work; polling external systems (e.g. issue queues) |
| **Proactive** | Each task exits at its goal; routine runs until stopped | Recurring streams of well-defined work |

For a software team going spec→PR, most agents are **goal-based**: a
deterministic exit criterion (tests green, gate passed) with a hard turn cap.

> Source:
> - Loop engineering: Getting started with loops (Anthropic) — https://claude.com/blog/getting-started-with-loops

---

## 2.5 Graph engineering — wiring the loops so they can't fool each other

Loop engineering makes one agent's behaviour programmable. **Graph engineering
is the layer above:** a network of loops that watch, constrain, and correct one
another, instead of each loop quietly drifting away from reality. Once you have
more than one loop — and a spec→PR team has at least four — the failures stop
being bugs inside a loop and become problems in the *topology* connecting them.

This matters more, not less, with open-source executors: aggressive
optimization against a single metric is exactly what a cheaper model tuned to
"make the check pass" will do.

### 2.5.1 The four ways a system of single loops breaks

Each is structural — a fix inside any one loop can't address it.

- **Goodhart drift.** Push a metric hard and it detaches from the goal it stood
  for. A Coder optimizing "tests pass" can pass by writing weak tests. The
  number climbs; the meaning leaves.
- **Blindness upward.** A loop can't question its own target. The Coder can't
  ask whether the spec it's implementing is the right spec — it will faithfully
  build a misreading.
- **Inter-loop conflict.** Independent loops fight without knowing it. A "ship
  fast" pressure undermines a "thoroughness" gate; each dashboard stays green
  while the system thrashes.
- **Measurement decay.** Checks that compare reports to other reports stay green
  while the whole component floats free of reality. Every gate passes; the
  feature is still wrong.

> The core danger, stated plainly: *a graph of loops that consumes only reports
> generated by other loops inside the same graph can be perfectly
> self-consistent while drifting arbitrarily far from reality.* Your four gates
> — tests pass, CRAP ≤ 6, diff-matches-spec, review approves — are all
> **internal reports**. Nothing among them checks whether the shipped feature
> does what the human actually needed.

### 2.5.2 Anchors — the part everyone skips

An **anchor** is an external fixed reference the internal machinery is forbidden
to rewrite. It feeds values into the graph but is never subject to the graph's
dynamics. Without anchors, a graph of loops is just a more elaborate echo
chamber. For this team, the anchors are:

- **The human-approved spec** — frozen at Gate 1, the reference every downstream
  loop is measured against. Agents may not edit it.
- **The frozen rules in AGENTS.md** — safety/architecture constraints the
  optimizer can't relax to make a gate pass (complexity threshold, "never modify
  a test to make it pass", forbidden dependencies).
- **A human judgment that the merged feature meets the original need** — the
  ground-truth check that closes the gap the four internal gates can't see.

Anchors are exogenous *on purpose*. The judgment of what "better" means stays
outside the graph — it is not another optimizable node.

### 2.5.3 Metrics never travel alone

Every metric an agent optimizes gets a **counter-metric** that watches for the
cheap win, and periodically an **anchor** grounds both.

| Loop | Optimizes | Counter-metric (watches for gaming) | Anchor |
|---|---|---|---|
| Coder | tests pass, lint clean | mutation score / coverage of changed lines | approved spec |
| Quality | CRAP ≤ 6, no duplication | behaviour unchanged — same tests still green | approved spec |
| Review | diff matches spec | fresh-context reviewer, not the author | human merge judgment |
| Spec | scenarios cover the need | reviewability (≤ ~8 scenarios) + "Assumptions made" list | human need in the issue |

The pattern: the optimizing loop drives the primary metric; a watching loop
monitors the counter-metric for cheap wins; an audit pass grounds both against
the anchor. Pairing two antagonistic metrics with mutual monitoring is what
raises the cost of gaming.

### 2.5.4 References have owners; some nodes are frozen

- **Targets are owned by a slower loop.** A fast loop can't silently change its
  own threshold. The CRAP threshold lives in AGENTS.md (governed, versioned),
  not in the Quality agent's prompt where it could drift. Changing a threshold
  is itself a governed change — a PR to the constitution, reviewed by a human.
- **Some nodes are frozen deliberately** — precisely because the optimizer would
  be tempted to weaken them: the approved spec, hard safety rules, the test
  assertions (the Coder may add tests, never alter existing ones to pass).

### 2.5.5 Separate the cadences

Graph engineering pays attention to *speed*. Fast loops escalate to slow loops;
they don't override them.

| Cadence | Loop | Owns |
|---|---|---|
| Per-task | Coder / Quality / Review goal loops | code, tests, structure |
| Per-feature | Human gates (spec approval, merge) | intent, release |
| Periodic (e.g. monthly) | Retro / "dreaming" pass | amendments to AGENTS.md, prompts, thresholds |
| Rare | Constitution governance | safety rules, architecture law |

A per-task loop must never rewrite a per-feature or governance decision. It
raises a signal (a `blocked` label, a `needs-human` exit) and waits.

### 2.5.6 Two graphs, kept separate

- **Work graph** — *what* the agents do: nodes are tools, skills, artifacts,
  sub-tasks; edges are which artifact fed which step. Your label state machine
  and the spec→PR flow are this graph. (Modelling agent execution as an explicit
  state machine — permissible transitions as edges — is where production
  frameworks have converged; it's what lets you drop guard nodes, approval
  steps, and audit points at exact points in the flow.)
- **Improvement graph** — *how* the system changes itself over time: the retro
  loop, threshold changes, prompt edits. Keep this deliberate and anchored, or
  the system optimizes itself into a greener dashboard and a worse product.

### 2.5.7 The four loop layers — and the one you're missing

A graph-engineered agent system layers four kinds of loop. Map yours:

- **Operational** — per-task success, latency, cost. *You have this* (goal-loop
  exits).
- **Quality** — eval scores, error rates, safety checks. *You have this*
  (Quality agent, Review agent).
- **Governance** — who sets targets, who can move thresholds, when changes roll
  out. *Partial* — AGENTS.md exists; make threshold changes go through review.
- **Audit** — periodic checks that the metrics still correlate with real
  outcomes. **This is the gap.** Add a recurring pass that samples merged
  features and asks: did green gates actually mean the need was met? When the
  answer is no, the fix isn't the one feature — it's an amendment to the spec
  template, a prompt, or a threshold, so every future run improves.

### 2.5.8 What this changes in practice

Three concrete additions, none of them heavy:

1. **Add counter-metrics to the two most gameable loops.** Mutation score (or
   coverage-of-changed-lines) on the Coder; behaviour-unchanged verification on
   the Quality agent. These already fit your machine-checkable-exit rule.
2. **Name your anchors explicitly** in AGENTS.md — the approved spec, the frozen
   rules, the human merge judgment — and mark them as things no agent may edit.
3. **Add the audit loop.** A scheduled pass (your retro issue) that grounds the
   internal gates against the external need and feeds fixes back into the
   constitution. This is the anchor that stops the whole pipeline becoming a
   self-consistent echo chamber.

> Sources:
> - Graph Engineering for AI Agents: Beyond Single Feedback Loops (Eigent) — https://www.eigent.ai/blog/graph-engineering-ai-agents
> - Anchored graphs of improvement (José Luis Chávez Calva) — https://joseluischavezcalva.substack.com/p/anchored-graphs-of-improvement-for
> - Measuring Goodhart's law (OpenAI) — https://openai.com/index/measuring-goodharts-law/
> - Loop engineering: Getting started with loops (Anthropic) — https://claude.com/blog/getting-started-with-loops

---

## 3. The universal agent contract

Every agent you build — regardless of model — fills out this template. This is
the spec you'll instantiate per role.

```markdown
# Agent: <name>

## Role
<One sentence. What this agent is responsible for and nothing else.>

## Model & effort
- Model: <e.g. Opus / Sonnet / DeepSeek / Qwen3 — chosen by judgment load>
- Effort/reasoning: <low | medium | high — match to task, not ambition>
- Rationale: <why this model is adequate for this role>

## Inputs (explicit allow-list)
- <Exactly what this agent may read. Nothing else.>

## Forbidden inputs (explicit deny-list)
- <What it must NOT read, especially upstream artifacts that would let it
   "fill gaps" by guessing. This is what makes a weak model safe.>

## Tools (minimum viable set)
- <Only the tools this role needs. Every extra tool costs context and
   invites misuse. Scope commands where possible (e.g. only `npm test`).>

## Procedure
1. <Ordered, concrete steps. For weak models, explicit sequence beats
    "figure it out".>

## Stop condition (machine-checkable)
- Done means: <deterministic, measurable criteria — exit codes, thresholds,
   schema validation. NOT "the code looks good".>
- Turn cap: <hard limit>
- Budget cap: <hard spend limit, if your harness supports it>

## Uncertainty protocol
- If <ambiguity condition>: STOP. Do not guess. <How it signals — comment,
   label, structured error.> Then halt.

## Handoff
- On success: <what it produces, where, how the next stage is triggered>
- On failure/cap: <how it flags for a human — never silent, never auto-retry>

## Output format
- <Exact structure. For models with weak tool-use, specify a parseable text
   format and validate it.>
```

### Why the allow-list / deny-list is load-bearing

The most reliable way to stop a weak model from guessing is to **not give it
the information it would guess from.** If the Coder can only see the spec
artifact (e.g. Gherkin) and not the original human issue, an ambiguous spec
becomes a *defect it must report*, not a gap it silently fills. Structure
replaces the diligence you can't assume.

> Source:
> - Effective context engineering for AI agents (Anthropic) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents

---

## 4. Prompt structure (applies to every agent)

- **Organize into labeled sections.** Use XML tags or Markdown headers
  (`<role>`, `<inputs>`, `<procedure>`, `<stop_condition>`). Formatting
  matters *more* for weaker models — they lean on structure to parse intent.
- **One canonical example beats a laundry list of edge cases.** Start
  one-shot; add examples only where a specific failure shows up. Diverse,
  canonical examples > exhaustive rules.
- **Persistent rules go in the constitution file, not the prompt.** Anything
  that must survive the whole run belongs in a re-injected file (CLAUDE.md /
  AGENTS.md equivalent), because context compaction can drop instructions
  given once in the prompt. This bites long loops hardest.
- **Keep the system prompt minimal but complete.** Minimal ≠ short. Give
  enough to fully specify behavior, nothing that doesn't change output.

> Sources:
> - Effective context engineering for AI agents (Anthropic) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - Prompt engineering best practices for 2026 (Anthropic) — https://claude.com/blog/best-practices-for-prompt-engineering
> - Claude prompting best practices (docs) — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

---

## 5. Memory & the project constitution

- **Constitution file** (AGENTS.md / CLAUDE.md): architecture, hard rules,
  commands, conventions. Read by every agent every run. **Describe reality,
  not aspiration** — an agent copies the patterns actually in the codebase, so
  a file describing an architecture you don't have produces code matching
  neither. Keep rules checkable (`complexity ≤ 6`, `files ≤ 400 lines`), not
  vague (`follow SOLID`).
- **Structured note-taking:** for long tasks, agents write progress/decisions
  to a file that survives context resets.
- **Compaction awareness:** when a run compacts, early prompt instructions may
  vanish. Steer what's preserved (objective, acceptance criteria, file paths,
  test results) via the constitution.
- **Encode failures back into the system:** when an agent produces a bad
  result, don't just fix the instance — amend the constitution so every future
  run improves. (This is "dreaming," done manually and cheaply.)

> Sources:
> - Effective context engineering for AI agents (Anthropic) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - Steering Claude Code: CLAUDE.md, skills, hooks, subagents — https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
> - Lamis Mukta, dreaming (AI Native DevCon 2026) — https://youtu.be/tTcxVv8HHNw

---

## 6. Model routing — match model to judgment load

Assign the strongest/most-expensive model only where genuine judgment lives;
route mechanical, verifiable work to cheaper or open-source models.

| Judgment load | Example role type | Model class |
|---|---|---|
| High — resolves ambiguity, makes design calls | Spec writing, architecture review | Frontier (Opus / large) |
| Medium — pattern application under constraints | Implementation against a tight spec + tests | Mid (Sonnet) or strong OSS (DeepSeek, Qwen3-large) |
| Low — mechanical, fully tool-verified | Refactor to a metric, formatting, lint fixes | Small OSS (Qwen3, smaller) |

Two rules of thumb:
- The more deterministic the exit criterion, the smaller the model can be —
  the gate, not the model, guarantees quality.
- Test each open-source model's tool-calling before trusting it with tools;
  degrade to constrained text + parser if unreliable.

> Sources:
> - Choosing a Claude model and effort level in Claude Code — https://claude.com/blog/claude-model-and-effort-level-in-claude-code
> - How we built our multi-agent research system (Anthropic) — https://www.anthropic.com/engineering/multi-agent-research-system

---

## 7. Tools & safety

- **Minimum viable tool set per agent.** If a human can't say which tool fits
  a situation, the model can't either. Bloated tool sets cause wrong calls.
- **Scope tool permissions.** Allow-list the specific commands an agent may
  run; deny state-changing tools it shouldn't touch. Gate irreversible
  actions (publish, merge, delete, spend) behind a human or an explicit rule.
- **Treat everything a tool returns as data, not instructions.** Web pages,
  file contents, issue bodies — none of it can change the agent's rules. This
  guards against prompt injection, which weaker models resist less well.
- **Tools should return token-efficient output.** A verbose tool result can
  blow the context budget in one turn.

> Sources:
> - Writing tools for AI agents (Anthropic) — https://www.anthropic.com/engineering/writing-tools-for-agents
> - How the agent loop works — permissions (Claude Agent SDK) — https://code.claude.com/docs/en/agent-sdk/agent-loop

---

## 8. Cost & reliability controls

- **Always cap turns and budget.** An uncapped loop on an open-ended task runs
  long and expensive. Caps return an explicit "hit the limit" state — handle
  it, don't assume success.
- **Match effort to the task.** Reasoning depth is one of the biggest cost
  levers; don't spend `high` effort on a file listing.
- **Prefer scripts for deterministic steps.** Running a known script is
  cheaper and more reliable than having the model re-derive the logic.
- **Pilot before scaling.** If you'll fan out to many parallel agents, measure
  on a small slice first.
- **No silent auto-retry.** A failed loop flags a human; it does not silently
  re-enter the queue.

> Sources:
> - Loop engineering: Getting started with loops (Anthropic) — https://claude.com/blog/getting-started-with-loops
> - How the agent loop works — turns and budget (Claude Agent SDK) — https://code.claude.com/docs/en/agent-sdk/agent-loop

---

## 9. The spec→PR team — shape only

You'll define each role separately. This is the shared skeleton they slot into.
The pipeline is a chain of goal-based loops, each with a machine-checkable exit,
each seeing only its allowed inputs, handing off a concrete artifact.

```
Human need
   │  (structured intake — a template so the input is good enough to formalize)
   ▼
[ Intake gate ]  ── trivial? → route straight to Implementation (skip the spec)
   │  non-trivial ↓
   ▼
[ Spec agent ]  ── emits TWO artifacts:
   │                • spec  — what / why / rules, pure domain language (Coder's input)
   │                • plan  — task breakdown + routing metadata (yours, not the Coder's)
   │  (human gate — review the spec as a versioned file diff, not a comment)
   ▼
[ Implementation agent ]  ── spec → code + tests, loops until tests & lint pass
   │
   ▼
[ Quality agent ]  ── refactors to metric thresholds, behavior unchanged
   │
   ▼
[ Review agent ]  ── fresh-context review, opens PR
   │  (human gate — merge)
   ▼
  PR
```

Design invariants for every role in this team:
- **Each agent sees only its stage's input** (allow-list), never the upstream
  human artifact once a formal spec exists. Ambiguity becomes a reported
  defect, not a silent guess.
- **Each agent's exit is deterministic** (tests, lint, complexity, schema).
- **The maker is never the checker** — the review agent has fresh context.
- **Humans gate at spec approval and at merge** — the two irreversible points.
- **Constitution (AGENTS.md) is read by all**, describes the real codebase,
  holds all hard rules in checkable form.
- **Failures flag a human and stop**; nothing auto-retries or auto-merges.

### 9.1 Spec-driven development: what to adopt (and what not to)

Two large teams — GitHub (Spec Kit: Specify → Plan → Tasks → Implement) and
AWS (Kiro: Requirements → Design → Tasks) — independently converged on the same
decomposition. That convergence is signal worth respecting. Three refinements
follow from it, each tuned for a mixed-model team where the executor may be
open-source.

**A. The Spec role emits two artifacts, not one.** SDD tools split "what/why"
from "plan/tasks" because they're different concerns. Do the same:
- **spec** — objectives, behaviours, business rules, prohibitions. Pure domain
  language. This is the *only* thing the Implementation agent reads.
- **plan** — task breakdown, sizing, routing hints. Orchestration metadata for
  *you*, used to split large work and assign models.

  *Caveat that is load-bearing for a mixed-model team:* Spec Kit's `/plan`
  deliberately pulls in tech stack and data model. That is fine for a solo
  frontier agent but dangerous here — it reintroduces implementation detail
  into the Coder's field of view and recreates the two-masters problem. Adopt
  the *decomposition*, not the leakage. Keep the spec implementation-free; let
  the plan hold orchestration metadata only, and don't feed the plan to the
  Coder.

**B. Not every task needs a spec.** Spec overhead is real cost, and it taxes
exactly the work that least needs it. Add an intake gate before the Spec agent.
The practitioner trigger: *if you'd be annoyed to have the agent interpret the
requirement differently than you meant, write the spec; if you could fix the
output in a quick follow-up, skip it.* Route trivial fixes and bugfixes
straight to Implementation with a `trivial` label or a size check.

**C. Version the spec like code.** Once a spec steers everything downstream, it
needs the same machinery code already has: version control, review as diffs,
history. Don't approve a spec in a comment thread — commit it to
`.specs/{id}_{kind}_{slug}/spec.md` (the canonical artifact directory, resolved
by `create-artifact` from the branch name), review it as a PR diff, and reference
it by path from the agent definition rather than pasting it into a prompt box.
The human gate becomes a reviewable diff with blame and rollback, not an ephemeral
approval.

**What to reject:** the common "You are an AI software engineer, draft a spec
for [X]" starter pattern has the *model* originate requirements from a vague
prompt. That's where hallucinated scope enters. Your design puts the human need
first through a structured template so the Spec agent *formalizes* rather than
*invents*. Keep it that way.

> Sources:
> - Loop engineering: Getting started with loops (Anthropic) — https://claude.com/blog/getting-started-with-loops
> - Building effective agents (Anthropic) — https://www.anthropic.com/research/building-effective-agents
> - Effective context engineering for AI agents (Anthropic) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - Spec-driven development with AI: a new open-source toolkit (GitHub / Spec Kit) — https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
> - Spec-Driven Development for AI Agents: Governing Specs (TrueFoundry) — https://www.truefoundry.com/blog/spec-driven-development-ai-agents
> - What Is Spec-Driven Development? (Augment Code — the skip-the-spec trigger) — https://www.augmentcode.com/guides/what-is-spec-driven-development
> - Spec-Driven Development with AI Agents (OTTO Tech Blog — Story/Plan/Implement/Review in practice) — https://www.otto.de/jobs/en/blogs/techblog/spec-driven-development-agent-workflows/

---

## 10. Data collection for future fine-tuning

**Position first, so no one over-invests:** fine-tuning is not how this system
gets good. Reliability comes from structure — linters, hooks, gates, ordered
plans — which is mandatory, inspectable, and updatable with a commit.
Fine-tuning gives behaviour that is probabilistic, opaque, and updatable only
by retraining. Treat it as a *narrow, later* optimization for output-format and
house-style adherence on a small open model — never as the mechanism for
teaching TDD, architecture, or planning. Those must stay structural.

That said, the *right* time to set up data collection is **now**, because the
training set is a by-product of simply operating the pipeline. If you don't
capture runs from day one, you'll wish you had. Collecting is cheap; it commits
you to nothing.

### 10.1 What to collect — capture the successful trajectory, not just the diff

For every unit that reaches a **fully green terminal state** (all gates passed,
human-merged), record the whole trajectory as a structured record. A merged PR
is the anchor of quality — only merged, gate-passing runs are training-eligible.

```jsonc
// one record per completed task (the checklist item, not the whole feature)
{
  "schema_version": "1.0",
  "task_id": "142.3",
  "repo": "acme/billing",
  "commit_sha": "…",            // the merge commit — provenance anchor
  "layer": "application",        // which layer this task touched
  "test_type": "unit-mocked-ports",
  "model": "qwen3-coder-30b",    // which model produced it (for later comparison)
  "inputs": {
    "scenario": "…",             // the single Gherkin/use-case for this task
    "layer_contract": "…",       // the relevant AGENTS.md layer rows
    "task_line": "Application: ApplyDiscount use case, repo port mocked (S4)"
  },
  "trajectory": [
    { "step": "red",      "artifact_path": "…test file…", "test_run": "FAIL: …" },
    { "step": "green",    "artifact_path": "…impl file…", "test_run": "PASS" },
    { "step": "refactor", "diff": "…",                    "test_run": "PASS" }
  ],
  "gates": {
    "unit": "pass", "arch_lint": "pass", "lint": "pass",
    "mutation_score": 0.86, "coverage_changed_lines": 0.94
  },
  "human_signal": "merged",      // merged | merged-with-edits | reverted-later
  "human_edits": "…diff if the reviewer changed it before merge…"
}
```

Why this shape:

- **The trajectory, not just the final diff, is the lesson.** The value is the
  red→green→refactor *sequence* — that's the behaviour you'd eventually want a
  model to internalize. A bare before/after diff throws away the TDD structure.
- **`human_edits` is gold and rare.** When a reviewer fixes the agent's output
  before merge, the *edit* is the highest-signal correction you will ever get —
  it's a human labelling exactly what "correct" looked like. Capture it
  separately.
- **`reverted-later` is a negative label.** A PR that merged green then got
  reverted is a Goodhart example — gates passed, reality disagreed. Keep these;
  they're the counter-examples that stop you fine-tuning toward gate-gaming.
- **`model` field** lets you later ask "did fine-tuning actually beat the base
  model" on a held-out slice.

### 10.2 Where it comes from — instrument the loop, don't add work

Every field above is already produced by the pipeline. Collection is a passive
tap, not a new agent:

- A **post-merge hook** (GitHub Action on merge to main) assembles the record
  from the PR, the linked plan.md task, and the CI gate results.
- Store as **JSONL, one file per repo, versioned or in object storage** — append
  only, never edited. This is itself an *anchor* (§2.5.2): training data the
  optimizing machinery may read but never rewrite.
- **Redact before storage** if any repo carries secrets or PII in diffs — a
  filter step in the collection hook, not an afterthought.

### 10.3 The eval set matters more than the training set

The failure mode of every local fine-tuning effort is skipping evaluation and
tuning toward a vibe. Before you ever train:

- **Freeze a held-out benchmark** of real tasks with objective pass/fail —
  never used in training, only for before/after comparison. This is your
  fine-tuning **anchor**. Without it you cannot tell "better" from "different".
- **Measure the metric that matters:** iterations-to-green and gate-pass-rate on
  the held-out set, base model vs fine-tuned. Not loss curves, not vibes.
- **A fine-tune that doesn't beat the base model on the frozen set is
  discarded.** Version adapters; keep a rollback.

### 10.4 When (and whether) to actually train

Gate the decision behind evidence, not enthusiasm:

- **Only after** you have hundreds of clean trajectories *and* a specific,
  recurring, structure-resistant failure (typically output-format or
  convention adherence — not correctness, which structure already handles).
- **Scope:** QLoRA/LoRA adapter on a 7–14B model (feasible on a 48GB Apple
  Silicon box via MLX-LM / Unsloth). Full-parameter tuning of a 30B+ model needs
  rented multi-GPU cloud and is almost never worth it for a team this size.
- **Never fine-tune on gate-passing examples alone** without the `reverted-later`
  and counter-metric signals — you'll bake in the cheap win. (§2.5.1, Goodhart.)

> The one thing worth doing early is the *collection*, precisely because it's
> cheap and keeps the option open without betting on it. Everything else waits
> for evidence.

> Sources:
> - Effective context engineering for AI agents (Anthropic — why knowledge belongs in context, not weights) — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
> - Graph Engineering for AI Agents (Eigent — anchors, Goodhart in training data) — https://www.eigent.ai/blog/graph-engineering-ai-agents
> - Measuring Goodhart's law (OpenAI) — https://openai.com/index/measuring-goodharts-law/

---

## 11. Checklist before you ship any agent

- [ ] Role is one sentence; the agent does one thing
- [ ] Inputs are an explicit allow-list; forbidden inputs are named
- [ ] Tools are the minimum set; commands are scoped
- [ ] Stop condition is machine-checkable, not a judgment call
- [ ] Turn cap and budget cap are set
- [ ] Uncertainty protocol makes guessing halt, not proceed
- [ ] Hard rules live in the constitution file, not the prompt
- [ ] Handoff artifact is concrete; failure flags a human
- [ ] Model and effort match the judgment load, not the ambition
- [ ] If open-source: tool-calling reliability verified, or text+parser fallback
- [ ] A separate agent (or human) checks the work — maker ≠ checker
- [ ] Spec artifact is implementation-free; plan/routing metadata kept separate
- [ ] Trivial work can skip the spec (intake gate exists)
- [ ] Spec is a versioned, diff-reviewable file — not a comment-thread approval
- [ ] Every gameable metric has a counter-metric (maker can't cheat the number)
- [ ] Anchors are named and frozen — approved spec, safety rules, human judgment
- [ ] Thresholds live in the versioned constitution, not in agent prompts
- [ ] An audit loop grounds the internal gates against the real need
- [ ] Successful trajectories are captured (JSONL) for optional future tuning
- [ ] Repo-not-initialized halts the Coder immediately (no looping on unstable env)
- [ ] Each skill (onboarding, TDD-per-layer, specifier) has a hard stop condition

---

## Source index

**Anthropic — primary engineering**
- Building effective agents — https://www.anthropic.com/research/building-effective-agents
- Effective context engineering for AI agents — https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- Writing tools for AI agents — https://www.anthropic.com/engineering/writing-tools-for-agents
- How we built our multi-agent research system — https://www.anthropic.com/engineering/multi-agent-research-system

**Anthropic — loops, steering, prompting**
- Loop engineering: Getting started with loops — https://claude.com/blog/getting-started-with-loops
- How the agent loop works (Agent SDK) — https://code.claude.com/docs/en/agent-sdk/agent-loop
- Steering Claude Code: CLAUDE.md, skills, hooks, subagents — https://claude.com/blog/steering-claude-code-skills-hooks-rules-subagents-and-more
- Choosing a Claude model and effort level — https://claude.com/blog/claude-model-and-effort-level-in-claude-code
- Prompt engineering best practices for 2026 — https://claude.com/blog/best-practices-for-prompt-engineering
- Claude prompting best practices (docs) — https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

**Spec-driven development**
- Spec-driven development with AI: a new open-source toolkit (GitHub / Spec Kit) — https://github.blog/ai-and-ml/generative-ai/spec-driven-development-with-ai-get-started-with-a-new-open-source-toolkit/
- Spec-Driven Development for AI Agents: Governing Specs (TrueFoundry) — https://www.truefoundry.com/blog/spec-driven-development-ai-agents
- What Is Spec-Driven Development? A Complete Guide (Augment Code) — https://www.augmentcode.com/guides/what-is-spec-driven-development
- Spec-Driven Development with Agent Workflows (OTTO Tech Blog) — https://www.otto.de/jobs/en/blogs/techblog/spec-driven-development-agent-workflows/
- How to Write a Good Spec for AI Agents (O'Reilly / Addy Osmani) — https://www.oreilly.com/radar/how-to-write-a-good-spec-for-ai-agents/

**Graph engineering**
- Graph Engineering for AI Agents: Beyond Single Feedback Loops (Eigent) — https://www.eigent.ai/blog/graph-engineering-ai-agents
- Anchored graphs of improvement (José Luis Chávez Calva) — https://joseluischavezcalva.substack.com/p/anchored-graphs-of-improvement-for
- Measuring Goodhart's law (OpenAI) — https://openai.com/index/measuring-goodharts-law/

**Talks / external**
- Lamis Mukta, *Learning while you sleep: beyond memory to dreaming* (AI Native DevCon 2026) — https://youtu.be/tTcxVv8HHNw
- Sean Grove, *The New Code* (AI Engineer World's Fair 2025) — founding SDD talk
- Context rot research (Chroma) — https://research.trychroma.com/context-rot

---

## 12. Companion skills (separate files)

Three skills operationalize this guide. Each is a standalone file the building
agent installs into the repo. They share the guide's invariants — machine-checkable
exits, hard stop conditions, structure over instruction — and each has an
explicit halt so a weak model can't loop on an unstable environment.

| Skill | Owner | Purpose | Hard stop |
|---|---|---|---|
| **onboarding-agents-md** | Human + building agent | Bootstrap a new repo: detect stack, install linters/quality gates/hooks, write the AGENTS.md layer contract, extract per-layer test samples from existing code, emit TDD scripts. Produces a step-by-step plan for **human validation** before anything is written. | Stops for human review at each phase gate; never installs without approval |
| **tdd-by-layer** | Coder | Execute one plan task as a red→green→refactor cycle using the layer's test type. | **Halts immediately if the repo is not initialized** (no AGENTS.md layer contract, gates not installed) — prevents error-looping on an unstable env |
| **specify-issue** | Tech-lead | Turn an issue into a pure-intent spec (scenarios, assumptions, open questions). Handles both features (domain extraction) and bug fixes (code investigation). | Halts and asks (`blocked`) on any ambiguity rather than guessing |
| **plan-pipeline** | Planner | Turn the approved spec into an ordered, checkable plan.md the Coder consumes one task at a time. Each task = one layer, one TDD cycle. | Halts and asks (`blocked`) on any ambiguity rather than guessing |

Design notes that bind all three:

- **The onboarding skill is the prerequisite for the other two.** Its output —
  the layer contract, installed gates, hooks, and TDD scripts — is the stable
  environment `tdd-by-layer` checks for before it will run. This dependency is
  deliberate: it's what stops the Coder from looping on a half-built repo.
- **`tdd-by-layer`'s init check is a frozen precondition (§2.5.4).** The Coder
  may not "work around" a missing environment; it stops and escalates.
- **`plan-pipeline`'s plan.md is the ordered checklist** that makes a
  weak Coder reliable — each task is one small, independently verifiable
  red→green→refactor cycle (§Part 1–2 of the TDD-per-layer approach).

The three skill files accompany this guide as separate documents.
