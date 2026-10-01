---
name: initiative-spec
description: Take a new idea through BMAD planning to an initiative folder an ai-orchestrator Run can execute — context, research, PRD, UX, architecture, epics and stories, then the projection into epics.yaml + SPEC.md + stories.yaml and the preflight gate. Use when the user has a new idea, says "spec this", "write the initiative", "resume the initiative in <folder>", or asks "is this ready for the orchestrator".
---

# Initiative spec — idea → ready-to-dev

This skill produces one thing: an **initiative folder, committed on one initiative branch
in the hub repository, that an `initiative-hub` Run reads without improvising** — and a
PASS verdict from the instance's own preflight proving it. It plans; it never creates the
Run. Launching and supervising is `initiative-run`.

The file format is `../orchestrator/references/spec-folder.md` — authoritative, read it
before writing `epics.yaml`, `SPEC.md` or `stories.yaml`. The endpoints are
`../orchestrator/references/api.md`. The version handshake and the one-time project /
repository setup are `../orchestrator/SKILL.md`. Nothing here restates them.

Every recorded failure of this pipeline was a projection or verification defect, not a
planning defect: a story-file naming collision that halted every story, and an `install`
command that shipped without ever having been executed. Steps 6 and 7 exist because of
them and are not optional.

## What it produces

```
<initiative_folder>/           # in the hub repository, on the initiative branch
  INITIATIVE.md                # state and pointers — see references/INITIATIVE.md
  CONTEXT.md                   # step 0
  PRD.md                       # step 2
  UX-SPEC.md                   # step 3, only when UI is in scope
  ARCHITECTURE.md              # step 4
  research/                    # step 1, when research or forging ran
  mockups/                     # step 3, files named by the story id they serve
  epics.yaml                   # step 6 — hub flavour, list order is execution order
  <spec_folder>/               # one per epic; bare folder name, never a repeated path
    SPEC.md                    # step 6
    stories.yaml               # step 6
                               # stories/ is written by the dev loop — never pre-authored
```

BMAD skills write to their own configured output folder. Move the artifact into
`<initiative_folder>/` and record it under `artifacts:`; a dispatched agent sees the
repository and nothing else, so an artifact left outside the folder must at least be
recorded as a repository-relative path.

## Input

**An idea.** Establish the hub repository, choose the initiative name, the folder name and
the branch; create the folder and the branch off the base branch; write `INITIATIVE.md`
with `phase: 0-context`; commit. Then step 0.

**An existing folder.** Read `INITIATIVE.md` frontmatter and resume at `phase`. Do not
re-run a completed step; do not trust an artifact that `artifacts:` does not name. If
`gate.verdict` is `PASS` and nothing has changed since `gate.checked_at`, say so and stop
— the next skill is `initiative-run`.

**Branches.** Before continuing a resumed initiative, fast-forward its branch from the
base branch, or take a fresh branch name and record the change. A hub Run reads
`epics.yaml` off the branch it is given, so a stale initiative branch silently serves an
older `epics.yaml` than the one you just wrote — the recorded attach trap. One branch is
shared by the hub and every member submodule.

## The chain

Steps run in order. Each ends on a human decision — present the artifact, name what is
still open, and wait. Never advance two steps on one approval.

| # | phase | BMAD skill | reads | writes | ends on |
| --- | --- | --- | --- | --- | --- |
| 0 | `0-context` | `bmad-project-context` | hub + member repos, their `AGENTS.md`, branch state, `/api/v1/version` | `CONTEXT.md` | the member/workdir list and the BMAD-version verdict are confirmed |
| 1 | `1-intake` | `bmad-deep-recon` or `bmad-forge-idea`, or neither | the idea, `CONTEXT.md` | `research/` | the idea is clear enough to write requirements for, or is dropped |
| 2 | `2-requirements` | `bmad-prd` | idea, `CONTEXT.md`, `research/` | `PRD.md` | users, business rules, scope and acceptance are signed off |
| 3 | `3-ux` | `bmad-ux` | `PRD.md` | `UX-SPEC.md`, `mockups/` | the mockups are accepted, or UI is declared out of scope |
| 4 | `4-architecture` | `bmad-architecture` | `PRD.md`, `UX-SPEC.md`, `CONTEXT.md` | `ARCHITECTURE.md` | the invariants and the trade-offs are accepted |
| 5 | `5-breakdown` | `bmad-create-epics-and-stories` | `PRD.md`, `ARCHITECTURE.md` | BMAD epics + stories | the epic boundaries and the story list are accepted |
| 6 | `6-projection` | `bmad-spec` per epic, then hand projection | everything above | `epics.yaml`, `<spec_folder>/SPEC.md`, `<spec_folder>/stories.yaml`, `commands_verified` | every command has run green in its own workdir |
| 7 | `7-gate` | `bmad-review`, then preflight | the projected files | `gate` | verdict PASS, or the named defects |

Run each BMAD skill in a **fresh context** where the harness allows it (a subagent, or a
new session). Planning skills are long; their working reasoning is not input to the next
step. The artifact on disk is the hand-off — if the next step needs something the artifact
does not say, the artifact is incomplete.

Record every decision that closes a step in `decisions:`; record every question you could
not close in `open_questions:`. `open_questions: []` is a precondition of the gate, so an
unanswered question is tracked, never absorbed.

The per-step contract — exact reads, writes, checks and failure modes — is
`references/chain.md`.

## Step 0 is mandatory

Not `anytime`, not skippable, and not satisfied by what the user tells you:

1. **The repositories.** The hub and, for a hub run, every member under `repos/*`: what
   each one is, its package manager, its real install / test / quality-gate commands, its
   `AGENTS.md` rules. This is where the step-6 command strings come from.
2. **Branch state.** The base branch, whether the initiative branch already exists, and
   whether it is behind the base.
3. **Existing initiative folders.** Their naming, their `epics.yaml` flavour, and whether
   the ids you intend to use are already taken.
4. **The method version (AD-16).** `GET /api/v1/version` gives `bmad_version`. The
   target's `_bmad/_config/manifest.yaml` must state the same `installation.version`. A
   different one is not a note: preflight fails its method-version line, and the BMAD
   skills a dispatched agent runs are not the ones you authored for. Resolve it before
   step 6 — `POST /api/v1/repositories/{id}/init` bootstraps a target that has none.

`CONTEXT.md` is the output and the thing steps 2–6 cite. Write what you verified, not what
you assumed.

## Step 3 runs only when UI is in scope

- No UI in scope → skip, set `artifacts.ux` to `null`, record the skip in `decisions:`.
- **Figma named but unreachable → stop and ask for the connector.** Do not improvise a
  spec from a screenshot or a description of a Figma file; a mockup invented at this step
  silently becomes the requirement.
- Otherwise default to HTML mockups, one file per screen.
- Mockups are committed under `<initiative_folder>/mockups/` and named by the story id
  they serve (`mockups/{story_id}-*.html`), and the story's `description` names the path.
  A dispatched agent sees the repository, never this conversation.

UX comes after requirements and before architecture. Drawing a screen before the
requirement is pinned replaces the requirement.

## Step 6 — the projection

BMAD's epics and stories are not the hub format. This step converts them and proves them.

### `epics.yaml`

A YAML list at `<initiative_folder>/epics.yaml`; list order is execution order. Per entry,
hub flavour: `id`, `title`, `branch`, `spec_folder`, `workdir`, `install`, `test`,
`quality_gate` (plus `done_checkpoint: true` where a human must see the epic land).

- `id` — quoted string, unique, and **prefix-free** against every other id in the file:
  `"1"` and `"1-a"` are refused, `"1"` and `"10"` are fine.
- `spec_folder` — a **bare folder name** relative to the initiative folder. The template
  joins `{initiative_folder}/{spec_folder}`; a repeated full path resolves to nothing.
- `branch` — the Run's one initiative branch. A hub Run works on the branch it is given,
  but the list contract still requires the field.
- `workdir` — the member submodule's repository-relative path (`repos/api`), from step 0.
- `install` / `test` / `quality_gate` — **full** commands, `cd` included. The template
  never builds `cd {workdir} && …` for you. An omitted command plans that row
  `skipped · no command` — never an error, never green.

### Per epic: `<spec_folder>/SPEC.md` and `stories.yaml`

`bmad-spec` distils the epic's slice of `PRD.md` + `ARCHITECTURE.md` (+ `UX-SPEC.md`) into
`SPEC.md`: frontmatter with `id`, `title`, `capabilities`, then `CAP-n` entries each
carrying an observable success criterion, a command wherever one exists. `stories.yaml` is
a list of `{id, title, description}` — the description is the agent's whole requirement,
since it gets that, `SPEC.md` and the project context and nothing more. The spec-gate step
blocks the Run on `TBD`/`TODO`/`???`, on an unresolved `open_questions:`, on a SPEC that
contradicts a story, and on a description that admits two incompatible implementations —
so write for that gate now.

### Never pre-author story files

`stories/` is absent when you finish. The dev loop writes `stories/{id}-*.md` as it works,
and done-detection reads frontmatter `status: done` from whatever that glob matches. A
pre-authored `{id}-{slug}.md` without that frontmatter is matched, read as the story's
file and halts the loop on every story — the recorded namespace collision. If the folder
already holds pre-authored story files, delete them in this step.

### No unexecuted command lands

**Rule: a command does not land in `epics.yaml` until it has exited 0 in its own
`workdir`, in this step.** For each epic, in the hub working tree on the initiative branch
with submodules checked out, from the hub root, run the exact string in order: `install`,
then `test`, then `quality_gate`.

- Record every run under `commands_verified` in `INITIATIVE.md`: epic id, kind, workdir,
  the exact command string, exit code, duration, timestamp.
- **The string that ran is the string that lands.** Do not tidy, shorten or re-order a
  command after verifying it; re-verify instead.
- A non-zero exit is a **blocker**, not a note: fix the command or the repository, re-run,
  and only then land it. Do not land it with a caveat, and do not drop the field to make
  the row `skipped` — a silently skipped verify is how an epic reports green having tested
  nothing.
- A command you deliberately omit is recorded as an omission with its reason in
  `decisions:`.
- Where the harness supports subagents, one subagent per workdir runs that epic's three
  commands in parallel and returns the exit codes and durations; otherwise sequential,
  same records.

## Step 7 — the gate

The verdict is the instance's answer, not a checklist.

1. **Review first.** `bmad-review` over every `SPEC.md` and `stories.yaml` — the
   adversarial, edge-case and verification-gap lenses at least, fanned out over subagents
   where supported. Resolve the findings or record them as open questions.
2. **Discover the template.** `GET /api/v1/templates`, then
   `GET /api/v1/templates/{name}/{version}` for `initiative-hub` at the version that read
   lists — `inputs` there is the authoritative input list. **Never hardcode a version**;
   the shipped templates evolve and a pinned version is how an upgraded instance breaks.
3. **Preflight with the real inputs.** `POST /api/v1/runs/preflight` with
   `template_name`, the discovered `template_version`, `project_id`, `repository_id` (the
   **hub** repository), `base_branch`, `inputs` (`branch`, `initiative_folder`, and
   whatever else `inputs` declared), `harness`, `model`, `budget_usd`. Dummy inputs prove
   nothing: every omitted field turns a check into `skip`.
4. **Resolve every `fail` line.** Each carries a `fix`. A `plan_error` names the template
   and the exact line that refused — that is a projection defect, so go back to step 6.
5. **Read `rows[]` and confirm it is the shape you intended.** One frame per epic in list
   order, one per story, and every setup / verify / gate row carrying a command. A row
   reading `skipped · no command` where you wrote a command means the field did not reach
   the planner — a defect in `epics.yaml`, not a warning.
6. **`open_questions: []`.** Zero, not "none important".

PASS requires all six: zero `fail` lines, `rows[]` as intended, `commands_verified`
covering every command in `epics.yaml` with exit 0, review findings resolved, no open
questions, and `start_allowed` true (or a `queue_note` that explains only a queue wait).
Write `gate: {verdict: PASS, checked_at: <ISO 8601 UTC>}` and stop. Anything else is
`FAIL` with the defects named and the phase moved back to the step that owns them.

## INITIATIVE.md

State and pointers, never content. The template and the field-by-field contract are
`references/INITIATIVE.md`; `phase` is what a resume reads, `autonomy` is what
`initiative-run` reads (`assisted` is the default), `artifacts` is how anything finds the
planning output. Commit it with every step that changes it, so the state on the branch is
the state.

## Subagents

Fan-out and verification only, where the harness supports them — otherwise sequential,
with the same order and the same records:

- step 0 — recon, one subagent per member submodule;
- step 1 — research fan-out;
- step 6 — command execution, one subagent per workdir;
- step 7 — one subagent per review lens.

**Never steps 1–4's conversation with the human.** Elicitation, the PRD's business rules,
the UX acceptance and the architecture trade-offs are decided with the user, in this
context. A subagent cannot hold a decision the user has not made yet.

## Rules

- Handshake before any call (`../orchestrator/SKILL.md`); a version mismatch stops you.
- One step, one human decision; never advance two steps on one approval.
- Step 0 is mandatory, and its facts come from the repositories, not from the user.
- No command lands in `epics.yaml` unexecuted; a red command is a blocker.
- No story file is pre-authored.
- Ids are quoted strings, unique and prefix-free; `spec_folder` is a bare name.
- Fast-forward a resumed initiative branch, or take a fresh name.
- Discover the template version from the API every time.
- The gate is preflight's answer. Never declare ready on a checklist alone.
- `open_questions` holds what you could not close; it is never emptied by deciding for the
  user.
- This skill creates no Run. Hand the folder and the PASS to `initiative-run`.
