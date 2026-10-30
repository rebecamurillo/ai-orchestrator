# The chain, step by step

The per-step contract behind `../SKILL.md`. One section per step: the BMAD skill, what it
reads, what it writes, the checks that must hold before the step is closed, and the human
decision that closes it. Formats are `../../orchestrator/references/spec-folder.md`;
endpoints are `../../orchestrator/references/api.md`.

Each step ends by writing `INITIATIVE.md`: the new `phase`, the new `artifacts` entry, any
`decisions` and `open_questions`, committed on the initiative branch.

---

## Step 0 — context (`0-context`)

**Skill:** `bmad-project-context` — mandatory here, whatever its menu says about `anytime`.

**Reads:** the hub repository; every member submodule under `repos/*`; each repository's
`AGENTS.md`, package manifests and CI config; `git` branch state; existing initiative
folders; `GET /api/v1/version`.

**Writes:** `CONTEXT.md` — per repository: what it is, its stack, its package manager, the
**verified** install / test / quality-gate command lines, the `AGENTS.md` rules that
constrain a dispatched agent, and its submodule path in the hub. Plus: the base branch, the
state of the initiative branch, the ids already used by neighbouring initiative folders,
and the BMAD-version comparison.

**Checks:**

- Every member a later epic will touch appears with a `workdir` path that exists in the hub.
- The command lines are copied from the repository's own documentation or scripts, not
  guessed. They are *candidates* here; step 6 is what proves them.
- `installation.version` in the target's `_bmad/_config/manifest.yaml` equals
  `bmad_version` from `GET /api/v1/version` (AD-16). A mismatch or a missing manifest is
  resolved before step 6: preflight does not check it, and the BMAD skills a dispatched
  agent runs are not the ones you authored for.
  `POST /api/v1/repositories/{id}/init` bootstraps a target that has none.
- Where the harness supports subagents: one recon subagent per submodule, each returning a
  section; the lead merges them.

**Closes on:** the user confirming the member list, the workdirs and the version verdict.

---

## Step 1 — intake (`1-intake`)

**Skill:** `bmad-deep-recon` when a fact about the market, the domain, a technology or a
competitor decides the shape; `bmad-forge-idea` when the idea itself is unproven and should
be allowed to die cheaply; **neither** when the idea is already clear — say so and move on
rather than manufacturing a research step.

**Reads:** the idea as the user stated it; `CONTEXT.md`.

**Writes:** `research/` — the recon summary or the forged-idea brief, cited. Nothing else;
requirements are step 2.

**Checks:**

- The question you are researching is written down before the research runs, and it is a
  question whose answer changes a decision.
- `bmad-deep-recon` may hand the user a prompt to run in their own tool and then process
  the returned report — that is a legitimate branch, not a failure to research.
- Research fans out over subagents where supported; the synthesis stays with the lead.

**Closes on:** the user agreeing the idea is clear enough to write requirements for — or
dropping it. A dropped idea ends the initiative here; delete the branch or leave the folder
with `phase: 1-intake` and the reason in `decisions`.

---

## Step 2 — requirements (`2-requirements`)

**Skill:** `bmad-prd`.

**Reads:** the idea, `CONTEXT.md`, `research/`.

**Writes:** `PRD.md` — users, business rules, scope (and what is out of it), acceptance
criteria, non-functional constraints.

**Checks:**

- Every requirement is observable. "Fast" is not a requirement; a number is.
- Out-of-scope is stated explicitly. The spec-gate step blocks a Run on a story that
  implements something the SPEC puts out of scope, so the boundary has to exist here.
- Anything the user did not decide goes to `open_questions`, not to a default you chose.

**Closes on:** the user signing off users, business rules, scope and acceptance.

---

## Step 3 — UX (`3-ux`)

**Skill:** `bmad-ux`. **Only when UI is in scope.** No UI → `artifacts.ux: null`, a
`decisions` entry recording the skip, straight to step 4.

**Reads:** `PRD.md`.

**Writes:** `UX-SPEC.md` and `mockups/` — committed under the initiative folder, one file
per screen, named by the story id it serves (`mockups/{story_id}-*.html`).

**Checks:**

- Figma named but the connector unreachable → **stop and ask for it.** Never reconstruct a
  Figma design from a screenshot or a description: an invented mockup becomes the
  requirement without anyone deciding it did.
- No connector and no Figma file → HTML mockups, the default.
- Every mockup is referenced from the story that implements it, by path, in the story's
  `description`. A dispatched agent sees the repository and the project context only.
- The mockups are committed. An attachment in a chat does not reach the agent.

**Closes on:** the user accepting the mockups, or declaring UI out of scope.

---

## Step 4 — architecture (`4-architecture`)

**Skill:** `bmad-architecture`.

**Reads:** `PRD.md`, `UX-SPEC.md`, `CONTEXT.md` (brownfield: the architecture ratifies what
the repositories already do).

**Writes:** `ARCHITECTURE.md` — the spine: the invariants every epic must hold, the
decisions with their trade-offs, and what is deliberately left open.

**Checks:**

- The spine is what keeps independently built epics consistent; anything no epic can
  violate does not belong in it.
- A decision that contradicts a repository's `AGENTS.md` is a conflict to raise with the
  user, not to resolve silently.
- Validate it (the skill's own validation mode) before closing.

**Closes on:** the user accepting the invariants and the trade-offs.

---

## Step 5 — breakdown (`5-breakdown`)

**Skill:** `bmad-create-epics-and-stories`.

**Reads:** `PRD.md`, `ARCHITECTURE.md`, `UX-SPEC.md`.

**Writes:** BMAD's epics and stories, in BMAD's own shape. **This is not `epics.yaml`** —
the conversion is step 6, and conflating them is how a planning artifact ends up dispatched
as a contract.

**Checks:**

- One epic maps to one member repository (one `workdir`). An epic that spans two members
  cannot carry one `install`/`test` pair and must be split.
- Epic order is execution order: an epic that depends on another comes after it.
- Every story is independently verifiable by a command that exists.
- Story ids are planned to be unique and prefix-free across the epic.

**Closes on:** the user accepting the epic boundaries and the story list.

---

## Step 6 — projection (`6-projection`)

**Skills:** `bmad-spec` once per epic for the `SPEC.md` distillation; the `epics.yaml` and
`stories.yaml` projection is a mechanical conversion you do by hand against the format
reference.

**Reads:** everything above.

**Writes:** `epics.yaml`; per epic `<spec_folder>/SPEC.md` and `<spec_folder>/stories.yaml`;
`commands_verified` in `INITIATIVE.md`.

### Order of work

1. Choose the `spec_folder` name per epic — a bare folder name, no repeated path.
2. Write `epics.yaml` with the core fields and the hub fields, list order = execution order.
3. Per epic: `bmad-spec` over that epic's slice of `PRD.md` + `ARCHITECTURE.md`
   (+ `UX-SPEC.md`) → `SPEC.md`; then `stories.yaml` from step 5's stories.
4. Execute every command. Record every run. Only then is the file final.
5. Delete any pre-authored file under `<spec_folder>/stories/`.

### Checks on `epics.yaml`

- Top level is a YAML **list**.
- `id`, `title`, `branch`, `spec_folder` on every entry; `workdir` on every entry (hub).
- Ids are quoted strings, unique, prefix-free (`"1"` + `"1-a"` is refused; `"1"` + `"10"`
  is fine).
- `branch` is the Run's initiative branch on every entry.
- `install`, `test`, `quality_gate` are **full** command strings, `cd` included, relative to
  the hub root. An omitted one plans `skipped · no command` — never an error, never green.
- `done_checkpoint: true` on every epic whose landing a human must see.

### Checks on `SPEC.md`

- Frontmatter `id`, `title`, `capabilities`; a title heading; a `## Capabilities` section of
  `CAP-n` entries, each with an observable **success** criterion — a command wherever one
  exists.
- No `TBD`, `TODO`, `FIXME`, `???`, no placeholder left from a template, no unresolved
  `open_questions:` or `assumptions:`. The spec-gate step blocks the Run on each of these.
- No capability contradicted by a story's scope.

### Checks on `stories.yaml`

- Top level is a YAML list; `id`, `title`, `description` on every entry.
- The `description` is the complete requirement: the dispatched agent gets it, `SPEC.md`
  and the project context, nothing else. It admits exactly one implementation.
- Ids quoted, unique, prefix-free — the story's file is found by the glob `{id}-*.md`.
- `spec_checkpoint: true` where a human reviews the planned story before implementation;
  `done_checkpoint: true` where one reviews the result; `invoke_dev_with` for a per-story
  instruction that does not belong in the requirement.
- **No `stories/` directory.** The dev loop writes `stories/{id}-*.md` itself and treats a
  file with frontmatter `status: done` as finished. A pre-authored `{id}-{slug}.md` without
  that frontmatter is matched by the glob and halts the loop on every story.

### Command verification

The rule: **no command lands in `epics.yaml` that has not exited 0 in its own `workdir`
during this step.**

1. Check out the hub on the initiative branch with submodules initialised.
2. Per epic, from the hub root, run the exact string: `install`, then `test`, then
   `quality_gate`. Order matters — `test` without `install` proves nothing about a fresh
   clone, which is what the Run gets.
3. Append one `commands_verified` entry per run: `{epic, kind, workdir, command, exit,
   seconds, at}`.
4. Exit non-zero → **blocker.** Fix the command or the repository, re-run, land only the
   green string. Do not land it with a caveat; do not drop the field so the row plans
   `skipped`.
5. The string that ran is the string that lands. Tidying a command after verifying it
   un-verifies it.
6. A deliberate omission is a `decisions` entry with its reason, not a silent gap.
7. Where subagents are supported: one per workdir, in parallel, each returning exit codes
   and durations; otherwise sequential.

**Closes on:** every command green and recorded, and the user seeing the epic/story list in
its final shape.

---

## Step 7 — the gate (`7-gate`)

**Skills:** `bmad-review`, then the instance's preflight.

**Reads:** the projected files; `INITIATIVE.md`.

**Writes:** `gate: {verdict, checked_at}`; `phase: ready` on PASS.

### 1. Review

`bmad-review` over every `SPEC.md` and `stories.yaml`. At least the adversarial, edge-case
and verification-gap lenses; one subagent per lens where supported. Every finding is fixed
or recorded as an open question — and an open question blocks the gate.

### 2. Discover the template

`GET /api/v1/templates`, then `GET /api/v1/templates/{name}/{version}` for `initiative-hub`.
`inputs` on the version read is the authoritative input list. **Never hardcode a version.**

### 3. Preflight with the real inputs

`POST /api/v1/runs/preflight` with `template_name`, the discovered `template_version`,
`project_id`, `repository_id` (the hub), `base_branch`, `inputs` (`branch`,
`initiative_folder`, plus whatever `inputs` declared), `harness`, `model`, `budget_usd`.
Every field is optional there and a missing one makes its checks `skip` — so a preflight run
with placeholder inputs is not a gate.

### 4. Read the answer

- `lines[]` — resolve **every** `fail`; each carries a `fix`.
- `plan_error` — names the template and the line that refused. A projection defect: back to
  step 6.
- `rows[]` — one frame per epic in list order, one per story; every setup / verify / gate row
  carrying its command. A row reading `skipped · no command` where you wrote a command means
  the field never reached the planner.
- `start_allowed`, `queue_note` — true, or a note that explains only a queue wait.
- `conflict_consent_required` — if true, record it; `initiative-run` needs the consent and a
  human has to give it.

### 5. Cross-check the records

Every `install`/`test`/`quality_gate` string in `epics.yaml` has a `commands_verified` entry
with `exit: 0`. A command without one fails the gate even if preflight is clean — preflight
proves the file plans, not that the commands work.

### 6. Verdict

PASS requires all of: zero `fail` lines; `rows[]` the intended shape; every command
verified green; review findings resolved; `open_questions: []`; `start_allowed` true.

Write `gate: {verdict: PASS, checked_at: <ISO 8601 UTC>}`, set `phase: ready`, commit, and
hand over to `initiative-run`. Anything less is `FAIL` with the defects named and `phase`
moved back to the step that owns each one. A PASS older than the last edit to the projected
files is stale: re-run this step.
