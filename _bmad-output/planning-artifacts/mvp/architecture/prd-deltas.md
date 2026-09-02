---
title: PRD deltas from the architecture spine
status: draft
created: 2026-09-02
purpose: hand-off list for `bmad-prd` (update intent) so mvp/prd.md and addendum.md stop contradicting ARCHITECTURE-SPINE.md
---

# PRD deltas — apply with `bmad-prd`

Each row names the PRD text that no longer holds and the spine decision that replaces it. Rows from `template-dsl-draft.md` §5 are included so one update pass covers both.

| PRD | Current text | Replace with | Spine |
| --- | --- | --- | --- |
| FR-2 | Project carries a GitHub token, stored encrypted, masked on read | No GitHub token on the Project; `GITHUB_TOKEN` is an instance env var. Project env vars stay Fernet-encrypted and masked. | AD-5 |
| FR-2 | `log_prompt_content` per Project | Unchanged, default from `LOG_PROMPT_CONTENT_DEFAULT` | AD-20 |
| FR-5 | Step types `git.worktree \| shell \| agent \| git.commit \| git.push` | A step is `uses: <kind>` + `with` or `run: <command>`; kinds `git.worktree, git.sync, shell, agent, git.commit, git.push, pr.link, template, bmad.install`; input type `item`; `expect`/`retry` on `agent`; `for_each` options `pause_before_item_when`, `pause_after_item_when`, reserved `parallel`; cross-template validation (cycles, depth > 3, callee inputs). | AD-9, AD-15 |
| FR-6 | Version pinned by any Run cannot change | Add: transitive — a callee version pinned by any Run is frozen; versions list shows callers. | AD-15 |
| FR-7 | Diagram rendered from parsed YAML (in the browser) | The graph is produced by backend-api (`/templates/{name}/{v}/graph`); the browser only lays out and renders; `template` calls render as collapsed nodes. | AD-15 |
| FR-8 | Pre-flight checks `render_skill.py` and the skill directory on the Working branch | Pre-flight checks `_bmad/` on the Working branch and `manifest.yaml` version == image `BMAD_VERSION`; skill directories are in the image. Add "What will run" = dry `plan_run`. | AD-7, AD-16 |
| FR-9..FR-11 | One `dev-loop` Template; push/PR at Run end | Four shipped Templates `repo-init@1`, `story@1`, `epic@1`, `initiative@1`; `git.sync` per story; push + compare link per epic. | AD-9, AD-16 |
| FR-13 | Repository lock mechanism in addendum §D | Unchanged behaviour; mechanism is the engine port's partition key. | AD-12 |
| FR-14 | Harness receives the Project's Gateway virtual key | Harness receives the instance `LITELLM_API_KEY`; attribution by tags. | AD-5, AD-11 |
| FR-16 | Routing list | Add the `expect` + `retry{max,prompt}` path before `needs-you`; retries resume the same session where the Harness allows, else new session with the prompt prepended. Add reason `protected path modified`. | AD-9, AD-17 |
| FR-17 | Spend summed from Gateway logs by Run tag | Unchanged; the key is global, tags carry `run:`. | AD-11 |
| FR-18..FR-20 | Separate endpoints answer/continue/skip/retry/cancel | One `POST /runs/{id}/signals {kind, payload}`; add *Skip epic*. | AD-13 |
| FR-22 / FR-23 | Card and header counts per story | Counts per epic and story (`n/n epics · m/m stories · k PRs`); Steps table keyed by `path`. | AD-7 |
| FR-25 | Queue read from the engine's queued workflows | Unchanged; via `engine.list_queue()`. | AD-6 |
| FR-26 | Every call carries the Project's virtual key | Every call carries the instance key plus tags `run:`, `story:`, `harness:`, `project:` and `langfuse_session_id`. | AD-11 |
| FR-27 | `claude` parented, `codex`/`local` session id | `claude` and `codex` parented via `TRACEPARENT`; `local` session id only. | AD-11 |
| FR-29 | Run diagram grouped by story-id prefix | Root = initiative when the Run is `initiative@n`; grouping from the plan's `path`, not id prefixes. | AD-7, AD-15 |
| FR-3 | Repository fields | Add `test_globs` (default `tests/**`, `**/*.test.*`, `**/*.spec.*`) used by the protected-path check. | AD-17 |
| FR-8 | Pre-flight "Harness available with a Gateway key for the Project" | "Harness enabled (readiness run passed)"; no per-Project key exists. | AD-10, AD-5 |
| FR-10 | Already-done Stories skipped unless *re-review done Stories* | Unchanged behaviour; Run input `re_review_done`; skipped rows are planned as `skipped · already done`. | AD-7 |
| FR-10 | "The DBOS step wrapper owns the timer" (addendum §G) | The `ProcessRunner` owns the timer; the engine never times steps. | AD-14, conventions |
| FR-19 | Operator may edit the Story file inline before Continue | Route `PUT /runs/{id}/files` (spec folder only, while `needs_you`). | AD-14, conventions |
| FR-19 | Done checkpoint applied by the orchestrator after commit-guard from `stories.yaml` | Planned as a `checkpoint` row (`…stories[n].after`); spec checkpoint stays on the `agent` row. | AD-7, AD-9 |
| FR-21 | `docker compose exec orchestrator …` | `docker compose exec backend-api …` | conventions |
| FR-20 | Skip: commit-guard then re-baseline | Skip marks the story frame's agent/checkpoint rows skipped; the frame's `verify` row runs as the re-baseline, then `git.commit` with message `story {id}: skipped by operator` (same tree, same result). | AD-13 |
| FR-23 | Active Operator time measured in the tab | Backend-owned: `POST /runs/{id}/activity {focused_seconds}` batched every 60 s into `run.active_seconds`. | conventions |
| FR-25 | History: every Step with duration and cost | Every execution of any row is an `attempt` (harness fields null for non-agent kinds). | seed |
| FR-16 | Run stops list | Add `internal` (unexpected exception in a step) as a `needs-you` reason with Retry. | AD-8 |
| §3 Glossary | Step statuses | Add `planned` (row exists, predecessor not done). | AD-7 |
| §3 Glossary | Gate record events | Add `protected_path`, `skip_epic`, `terminal_release`, `done`, `failed`. | AD-8 |
| §3 Glossary | — | Add Initiative, `epics.yaml`, Path, Callee Version, Signal, Protected path, Trajectory. | — |
| §6.1 Tiers | — | `story`/`epic`/`repo-init` + `template` call MUST; `initiative` SHOULD; `parallel` out of scope. | — |
| §8 Open questions | Q2 TRACEPARENT survival | Split: claude documented; codex source-verified (day-1 check). | AD-11 |
| NFR-3 | "no direct provider key" | Unchanged; add "never `GITHUB_TOKEN`". | AD-5 |
| NFR-7 | One compose file (orchestrator, Postgres, LiteLLM, Langfuse) | One compose file (web-client, backend-api, Postgres); LiteLLM and Langfuse run on the host. | seed |
| Addendum §A | Front-end Vite + React, TanStack | Astro 7 SSR on Node 24 + React islands + nanostores; openapi-typescript client. | AD-1, AD-3 |
| Addendum §A | Python 3.12 | Python 3.14. | Stack |
| Addendum §D | Gateway key per Project via `/key/generate` | Dropped. | AD-5 |
| Addendum §D | Gate record entity | Unchanged; written on every Run transition. | AD-8 |
| Addendum §G | Daily clone check needs a scheduled workflow | `engine.schedule(...)` (DBOS `create_schedule`). | AD-6 |
| Addendum §G | Harness readiness fixture | Unchanged; runs `story@1` on a fixture repository. | AD-10 |

New requirements the spine introduces (candidates for FRs):

- **FR-30 Repository initialisation** — the `repo-init@1` Template and the Repository-level action that starts it (AD-16).
- **FR-31 Protected paths** — after every agent attempt and at commit-guard, a modified `SPEC.md`, `stories.yaml`, `epics.yaml`, `AGENTS.md` or existing test file parks the Run (AD-17).
- **FR-32 Trajectory export** — `GET /projects/{id}/trajectories.jsonl` (AD-19).
- **FR-33 Harness readiness** — a Harness is offered only after its readiness run on `fixtures/readiness-repo/` (AD-10).
