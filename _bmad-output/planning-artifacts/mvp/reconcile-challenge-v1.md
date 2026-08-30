---
title: Reconciliation — challenge-v1.md vs PRD (mvp)
status: draft
created: 2026-08-26
inputs:
  - ../v1-dev-loop-2026-08-26/challenge-v1.md
  - prd.md
  - addendum.md
---

# Reconciliation: challenge-v1.md → PRD (mvp) + addendum.md

Legend: **Landed** = the decision/requirement/cut/risk is traceable to a specific PRD section, FR/NFR id, non-goal, open question, or assumption (directly or via addendum.md as an explicit "how" pointer). **GAP** = not found, or found but contradicted/weakened. **N/A** = deliberately and reasonably left unstated (never proposed as PRD content).

## §1 — What the repo's design gets right (kept)

| Input item | Where it landed | Note |
|---|---|---|
| DBOS as the durable engine, Postgres only | addendum.md §A "Durable engine" row; PRD NFR-1, NFR-7, Platform | How-level; PRD states the durability contract (NFR-1), addendum states the engine choice. |
| YAML minimal internal schema, not CNCF/OWD DSL | PRD FR-5 (Template schema and validation) | Landed — schema is explicit and bounded (no loops besides `for_each`, no conditionals). |
| Workflow structure authored, instances are bound variables | PRD §3 Glossary "Template"/"Run"; FR-8 | Landed — Run = Template Version bound to Inputs. |
| Version and pin every template; runs never change mid-flight (C-1) | PRD FR-6 Immutable Versions | Landed exactly, incl. "Run started under Version n still resolves Version n". |
| Orchestrator owns session identity (pre-assigned for Claude, captured for Codex/OpenCode) | PRD §3 Glossary "Harness"; FR-14 consequences | Landed per-harness, matches challenge §5 table. |
| Gate strength labelled (liveness/deterministic/human); nothing without an oracle is ever green | PRD §3 Glossary "Gate strength"; FR-5 last consequence; NFR-2 | Landed — NFR-2 is tested explicitly ("a Template with a Step lacking `gate`"). |
| Escalate on structured status, now the story spec file's frontmatter (not JSON schema) | PRD §3 Glossary "Story file"; FR-16 | Landed, matches §3.1 decision below. |
| Instrument-dark design system, "colour is signal only" | PRD §4.7 description; NFR-6; refs to DESIGN.md/EXPERIENCE-v1.md | Landed by reference, not restated (consistent with PRD's stated approach of not duplicating UX spec). |
| Single login, per-project secret scoping, non-root container, LiteLLM virtual keys, Langfuse OTLP | PRD FR-1 (login), FR-2 (project secrets), NFR-3 (non-root/isolation), FR-26 (virtual key), FR-27 (Langfuse trace) | Landed, spread across FR-1/2/26/27 + NFR-3 as expected for a bundle of cross-cutting decisions. |

## §2 — What was cut for one week

| Input item | Where it landed | Note |
|---|---|---|
| AC→Playwright spec gen, test-id contract, G2 gate, unmatched-criterion blocking (old FR-24a/28b/12a, F9) | PRD §6.2 "Executable-spec oracle... Deferred"; §5 non-goals "does not generate or run end-to-end tests, provision test environments, or judge acceptance criteria"; addendum.md §E lineage table | Landed. Oracle correctly narrowed to `quality_gate_command` (FR-9, FR-10). |
| Serialized execution (old FR-47) → replaced by "one active run per repository, several repositories in parallel" | PRD FR-13 (repository lock, ≤1 active per Repository); addendum.md §C "Global serialization... Repository-partitioned queue instead" | **Landed with a stricter addition** — see GAP note below (PRD/addendum also cap **total** concurrent Runs at 2, which the input did not state). |
| Notifications surface / review inbox as a first-class screen | PRD §5 non-goals "no notification channel outside the UI"; addendum.md §C "Notifications inbox screen... redundant" | Landed — "Needs you" is a Board column + rail count (§3 Glossary, FR-22). |
| Epic-level re-spec on G3 rejection, session-resuming review loops, rework caps as a mechanism | Implicitly landed: no G3 exists anywhere in the PRD's FR set; PRD §5 non-goals "does not resume or replay harness sessions across containers" | N/A-by-absence — since v1 has no G3 at all, there is nothing to explicitly cut; the retry cap that does exist (FR-10, verify fails twice → needs-you) is a narrower, intentional mechanism, not the epic-level one. |
| Manual-estimate ÷ actual-minutes as infrastructure → kept as one optional field only | PRD FR-8 "optional manual estimate... stored... cannot be edited afterwards"; §6.2 "The verdict metric dashboard... deferred. The manual estimate field is captured now because it cannot be retrofitted" | Landed exactly, verbatim rationale preserved. |
| Guacamole, Mattermost, GitHub issue ingest, multi-container | Mattermost: PRD §6.2 "Deferred"; issue ingest: §6.2 "Intake and spec generation... Deferred"; multi-container: §6.2 "Second container/multi-machine execution... deferred" | Guacamole specifically is **never named** in PRD or addendum — N/A, reasonable since it was never a candidate feature to begin with (no risk of scope confusion). |

## §3 — Where the repo's design was wrong for this brief (decisions)

| Input item | Where it landed | Note |
|---|---|---|
| 3.1 Agent contract is the story spec file, not a JSON schema | PRD §3 Glossary "Story file"; FR-16; addendum.md §C row 1 | Landed. |
| 3.2 `stories.yaml` caller-only fields (`spec_checkpoint`, `done_checkpoint`, `invoke_dev_with`) + "Halt after planning." | PRD §3 Glossary "Story"; FR-14; FR-19 | Landed, all three fields present with matching semantics. |
| 3.3 Human reply goes into the file (Answer box → `## Human Answers`), resume command secondary | PRD FR-18; FR-21 ("secondary affordance"); addendum.md §D "Answer append" mechanism | Landed exactly, incl. the append format is specified in addendum §D. |
| 3.4 Board encodes status (Queued/Running/Needs you/Done/Failed), stage is a line on the card | PRD §4.7 description; FR-22; addendum.md §C | Landed. |
| 3.5 Editable YAML + diagram rendered from parsed YAML, not a visual editor | PRD FR-5, FR-7; addendum.md §C "Visual workflow editor... rejected" | Landed. |
| 3.6 Three harnesses in week one, ~80-line adapter enabled by 3.1 | PRD §4.5 description; FR-14; addendum.md §B harness matrix | Landed at PRD level (harness-agnostic dispatch contract); the "~80 lines" estimate is architecture-level, correctly not restated in PRD. |
| 3.7 Subagents are a hard requirement of `bmad-build-auto`; override escape hatch in `_bmad/custom/bmad-build-auto.toml` | PRD §8 Open question 1 ("does the Codex Harness need an overridden `implementation_handoff` / `review_layers`?") | Landed as an open question; the exact override file path is not cited in PRD (acceptable — implementation detail, not a requirement). |

## §4 — What v1 is

| Input item | Where it landed | Note |
|---|---|---|
| `dev-loop` steps: checkout → baseline → for each story {build → verify → commit} → push | PRD §4.4 description; FR-9 (checkout/baseline), FR-10 (story loop), FR-11 (push) | Landed verbatim structure. |
| Story loop detail: read story file, route on status (blocked→BLK, ready-for-dev+checkpoint→CHK, done→continue) | PRD FR-16 | Landed. |
| verify → one re-dispatch on failure, then BLK | PRD FR-10 "one re-dispatch... a second failure sets the Run to `needs-you`" | Landed. |
| commit → spec folder + code; done_checkpoint → CHK | PRD FR-10 (commit), FR-19 (done checkpoint) | Landed. |
| Five screens (Login; Board+New workflow+Run detail; Projects+New project; Runs; Templates) | Distributed: FR-1 (§4.1 Login), §4.2 (Projects), §4.3 (Templates), §4.4/§4.7 (Board, New workflow, Run detail), §4.8 (Runs) | Landed, though the PRD organizes by feature area rather than as an explicit "five screens" list — no single section enumerates them together. |
| One container, LiteLLM in front of every model | NFR-7; addendum.md §A container row; PRD Platform section | Landed. |
| One Langfuse trace per run | PRD FR-27 | Landed. |
| Not in v1: intake, spec generation | PRD §6.2 | Landed. |
| Not in v1: E2E provisioning | PRD §6.2, §5 non-goals | Landed. |
| Not in v1: PR creation by the machine (a link is enough) | PRD FR-11 "A PR link is a draft PR created with `gh` when available, else the compare URL"; addendum.md §E "FR-38..42 (PR creation is a link)" | **GAP / internal contradiction.** The input and addendum §E both state the machine does *not* create a PR ("a link is enough"), but FR-11's actual text has the system create a real draft PR via `gh`. Addendum §E's parenthetical restates the input's intent while FR-11's body contradicts it. |
| Not in v1: notifications outside the UI | PRD §5 non-goals, §6.2 | Landed. |
| Not in v1: budgets beyond per-run halt | PRD FR-17 (per-run budget halt, landed); but PRD "Constraints and guardrails" also states "per-Project monthly budget on the Gateway key," and addendum.md §D specifies `max_budget, budget_duration: "1mo"` on the LiteLLM key | **GAP.** A second budget dimension (monthly, per-Project) is introduced beyond the per-run halt the input scoped v1 to. Not necessarily wrong, but it is scope the input explicitly excluded and the PRD doesn't flag the addition as a deliberate expansion. |
| Not in v1: multi-repo runs | PRD §6.2 "Multi-repository Runs — one Run, one Repository" (with `[NOTE FOR PM]`) | Landed. |

## §5 — Harness matrix (verified 2026-08-26)

| Input item | Where it landed | Note |
|---|---|---|
| Headless invocation per harness (claude -p --bare --permission-mode dontAsk…; codex exec --json --sandbox workspace-write; opencode run --format json --auto) | PRD FR-14 consequences (per-harness bullets) | Landed at requirement level; full flag detail correctly deferred to addendum.md §B / architecture. |
| Session id: pre-assigned (claude) vs captured (codex, opencode) | PRD §3 Glossary "Harness... Session id"; FR-14 | Landed. |
| Resume-with-message commands per harness | PRD FR-21 | Landed — claude/codex show the resume command, local shows none. |
| Gateway wiring per harness (ANTHROPIC_BASE_URL, litellm responses wire_api, provider.litellm) | addendum.md §A "Gateway" row, §B | Landed as "how", appropriately not restated as FRs. |
| Trace correlation per harness (TRACEPARENT propagation vs litellm_otel/headers) | addendum.md §A "Tracing" row; PRD FR-27 consequences + `[ASSUMPTION: span parenting differs per Harness]` | Landed. |
| Skills directories differ per harness (.claude/skills vs .agents/skills vs both) | addendum.md §B | Landed as "how" pointer; not restated in PRD, appropriate. |
| Subagents support (claude yes, codex needs multi_agent flag verified day 1, opencode yes) | PRD §8 Open question 1 | Landed. |
| Permissions for unattended run (dontAsk+allowlist; workspace-write sandbox; --auto) | PRD FR-14 consequences | Landed. |
| "Why OpenCode" rationale + fallback order (Codex→LiteLLM, then Claude Code w/ gateway discovery) | addendum.md §C "Codex or Claude Code pointed at LiteLLM for local models... Kept as fallbacks" | Landed. |

## §6 — Local models on the Mac Mini

| Input item | Where it landed | Note |
|---|---|---|
| Model picks (Qwen3.8-27B coder, Qwen3.6-35B-A3B general, gpt-oss-20b runner-up), quantization, footprints | addendum.md §A "Local models" row (pointer only) | Landed as an intentional pointer — addendum explicitly states it "does not duplicate" challenge-v1/architecture detail; this is the correct level for a PRD/addendum. |
| Runtime: oMLX, memory plan, wired GPU limit sysctl | addendum.md §A | Landed as pointer. |
| Host model server / Docker-on-macOS-has-no-GPU / host.docker.internal | PRD Platform section "model server on the host (Docker on macOS has no GPU)" | Landed. |
| Prefill-is-the-bottleneck, prefix caching mandatory | Not restated anywhere in PRD/addendum | N/A — architecture-level implementation concern, correctly out of a requirements document. |
| "Expectation setting": local models 1–2 tiers below Claude/GPT-5, harness choice moves outcomes as much as model choice, local is "a cost lever... not a peer" | Not reflected in PRD §7 Success metrics | **GAP.** SM-1 (Unattended completion rate, target ≥50%) is a single blended target across all three harnesses with no caveat that the `local` harness is expected to underperform. SM-3 (cost/time per Story per Harness) captures the comparison but there's no explicit acknowledgment that a lower `local` completion rate is expected-and-fine rather than a target miss. |

## §7 — The week

| Input item | Where it landed | Note |
|---|---|---|
| Day-by-day plan (1–7) with exit criteria | addendum.md §F "The week" (condensed pointer, matches challenge-v1 §7) | Landed as pointer; full detail correctly left to architecture-v1.md per addendum's stated scope. |
| "What slips first" order (OpenCode adapter → Templates editing → Runs pagination → cancel rollback) | addendum.md §F "Slips first: OpenCode adapter, Templates editing, Runs pagination, cancel rollback" | Landed verbatim as a list. Note: PRD's actual FR-20 spec for Cancel *includes* rollback (worktree removal + branch delete) as the primary behavior — consistent, since the "slip" is a fallback contingency, not the target spec. |

## §8 — Open items to confirm on day 1

| Input item | Where it landed | Note |
|---|---|---|
| 1. Codex `multi_agent` flag / override escape hatch | PRD §8 Open question 1 | Landed verbatim. |
| 2. OpenCode session id in JSON events vs `session list` fallback | PRD §8 Open question 2 | Landed verbatim. |
| 3. TRACEPARENT survives Claude→LiteLLM→Langfuse; codex/opencode land via headers/langfuse_otel | PRD §8 Open question 3 | Landed verbatim. |
| 4. oMLX prefill/decode throughput on the actual Mac Mini | PRD §8 Open question 4 | Landed verbatim. |
| 5. `bmad-build-auto` under Claude `dontAsk`+allowlist reaches `done` on a trivial story (allowlist must cover uv, git, package manager) | PRD §8 Open question 6 | Landed (renumbered — PRD's open question 5 is a different item, "should a needs-you Run release its repository lock," sourced from the FR-13 assumption in §3/§9, not from this day-1 list). |

## Summary of gaps

1. **PR-creation contradiction** — challenge-v1 §4 and addendum §E both say v1 does *not* create a PR, only a link ("a link is enough"), but PRD FR-11 specifies the system creates a real draft PR via `gh` when available. The FR text and the decision record disagree.
2. **Budget scope creep** — challenge-v1 §4 cuts "budgets beyond per-run halt," but the PRD's Constraints/guardrails section and addendum §D add a per-Project monthly budget on the LiteLLM gateway key, which is budget scope beyond a per-run halt.
3. **Local-model expectation-setting dropped from success metrics** — challenge-v1 §6 is explicit that local models sit "one to two tiers below Claude/GPT-5" and are "a cost lever... not a peer," but PRD SM-1 sets one blended ≥50% unattended-completion target across all three harnesses with no per-harness caveat.
4. Minor: the input's "five screens" framing isn't restated as a single list anywhere in the PRD (features are organized by capability, not by screen) — functionally complete but not literally traceable as a checklist.
