---
title: 'Detach coded rules from the BMAD method'
type: 'plan'
created: '2026-10-30'
status: 'proposed — not implemented; decisions in section 7 are open'
revised: '2026-10-30 — BMAD stays a default install of every harness; PR #8 merged'
baseline: 'origin/main fc5d800 for every file PR #8 changed; origin/main a2cccc2 for the rest, none of which changed between the two'
---

# Detach coded rules from the BMAD method

## 1. The goal and the line this plan draws

The Operator, 2026-10-30: *"detach CODED rules linked to BMAD method. The BMAD method is
installed in the container but should NOT define the code or business rules of the app
orchestrator."* The version check goes first, because workflows may use no BMAD skill at all.

The Operator, same day, on the install: *"the BMAD should still be installed in the agents
harnesses by default."* The goal is unchanged: detach the coded rules, not the install. BMAD
stays a default capability of every harness (claude, codex, opencode; `local` is served by
`opencode.sh`, `skills_install.py:49`), and no app or business rule may depend on it.

Two tests apply to every item below:

> Would this code still be correct if no template on the instance called a BMAD skill and no
> repository held a `_bmad/` folder?

> If the default install failed, would the backend still start, would a harness still be
> enabled, and would a plan that names no BMAD skill still run?

Neither test asks for BMAD to be absent from a harness; nothing in this plan removes it or
assumes an instance without it. A repository with no `_bmad/` stays an ordinary case, because
the install is global to the harness and `_bmad/` belongs to the repository (finding 6).

A template that names `skill: bmad-build-auto` is template content. Code that reads
`_bmad/_config/manifest.yaml`, or knows what a `bmad-*` skill prints, is a coded rule. Packaging
that installs and reports BMAD may name it: naming it there decides nothing about a Run.

Target state, in one paragraph: the orchestrator knows repositories, worktrees, harnesses,
skills *by name in a catalog*, templates, and the spec-folder and story-file conventions that
templates declare. BMAD is a set of skill stubs installed by default in every harness, a helper
script or two, and one family of shipped templates. An instance with no BMAD template behaves
exactly as well as one with them, a failed install costs only the Runs that name a missing
skill, and nothing about a repository is "outdated".

### Findings that change the shape of the plan

Seven facts surfaced that the requests did not list. Each is cited again in the inventory.

1. **The gate does not measure what AD-16 says it protects.** It compares the repository's
   manifest with the `BMAD_VERSION` environment variable, not with the stubs the harness
   reads. The stubs are installed at image build from the literal default in
   `scripts/harness/_common.sh:11` (the Dockerfile declares only the three CLI `ARG`s at
   `:154-156`, compose passes only those at `docker-compose.yml:60-63`, and
   `test_dockerfiles.py:240` forbids a value in the Dockerfile), and they live in the
   `agent-home` volume, which Docker seeds only while empty. The boot sync copies operator
   skills only (`_common.sh:271`). So editing `.env` moves the gate and not the stubs, and an
   image bump on an existing volume moves the gate and leaves the old stubs in place. PR #8 gave
   the CLIs a reconcile at every start; `.env.example:108` records that BMAD has none.

   **Correction to the earlier revision of this plan,** which offered PR #9's `outdated: 6.11.0`
   as an example of that skew. It is not one. Production's `BMAD_VERSION` is pinned at 6.12.4,
   and the repositories' default branches on GitHub still hold 6.11.0. The message is a correct
   comparison of those two values; stubs play no part in it.
2. **BMAD is a boot dependency.** `backend-api/docker-entrypoint.sh:44` runs
   `scripts/readiness_fixture.sh` under `set -euo pipefail`, and that script runs
   `npx --yes bmad-method@… install` (`:43`). If that command fails, the container does not
   start, on an instance that may use no BMAD template. This one install reads `.env`'s
   `BMAD_VERSION`, so it is also the only part of the stack that needs the registry at every
   boot on account of BMAD.
3. **BMAD is a harness-enablement dependency.** A harness is offered only after a readiness
   Run. The default `READINESS_TEMPLATE=epic` (`settings.py:182`, `.env.example:70`,
   `deploy/.env.example:84`) dispatches `bmad-build-auto`, `bmad-qa-generate-e2e-tests` and
   `bmad-retrospective`. The evaluation code itself is method-neutral; the default is not.
4. **A hard-coded BMAD protocol sits on the dispatch path.** `agent_render.py:59` names
   `_bmad/scripts/render_skill.py` and `:66-67` parse its output (`read and follow `, `HALT:`).
   The version check is the visible rule; this one is the deepest.
5. **Removing the stored field naively breaks rollback.** `clone_check_from_entity` reads
   `data["bmad_version"]` without a default (`infrastructure/db/repositories/repository.py:76`).
   A new image that stops writing the key produces rows a rolled-back image cannot read. See
   section 5.
6. **A stub in the harness does not make a repository ready.** The installed
   `bmad-build-auto/SKILL.md` runs `uv run {project-root}/_bmad/scripts/render_skill.py` and
   HALTs if that fails; `_common.sh:189` says the same. So with the default install in place the
   catalog check always passes for a BMAD skill name, and it can never catch a repository with
   no `_bmad/`. PR 2's guard rows and `repo-init` are still needed.
7. **`BMAD_VERSION` is in real use.** Production sets it to 6.12.4, above the shipped 6.11.0, so
   the earlier plan's literal-only pin would have ignored that value, and `install.sh upgrade`
   would have to treat the shipped value as a downgrade. See Q4.

## 2. Inventory

Classes: **(a)** a coded rule to remove; **(b)** a generic mechanism to keep, renamed or made
method-neutral; **(c)** packaging or content that may stay. Paths under `backend-api/src/orchestrator/`
are written `src/…`. The PR column refers to section 4.

### (a) Coded rules to remove

| id | where | how it behaves today | what happens | PR |
| --- | --- | --- | --- | --- |
| A-1 | `src/application/preflight/checks.py:358-372` `method_version_line`; `:70` `METHOD_VERSION_FIX`; `:38-39` imports `MANIFEST_PATH`, `installed_version`; `:83` `Context.bmad_version`; `src/application/preflight/model.py:37` `CHECK_METHOD_VERSION`; `src/application/use_cases/preflight.py:110,170` | Reads `_bmad/_config/manifest.yaml` at `plan_ref`. `fail · missing` or `fail · outdated: {stated}` refuses the Run, for every plan with no `bmad.install` row, whether or not it dispatches a skill. | Delete. | 1 |
| A-2 | `checks.py:74` `BMAD_INSTALL_KIND`, `:362-363` | `skip · plan installs the method`: a special case on a kind name. | Delete with A-1. `run_finished.py:31` imports the constant, so it moves until A-5 lands. | 1 |
| A-3 | `src/application/use_cases/clone_check.py:11,16-17` (docstring), `:67-70` manifest constants, `:149-182` `installed_version`, `_scalar`, `:233` the step, `:298-315` `_version`; `src/domain/entities/repository.py:55` `LINE_METHOD_VERSION` | A fourth line, always `ok`, that parses a BMAD manifest on every check, including the 03:00 cron (`settings.py:155`), every project save, and start-up for the readiness Project. | Delete the line; the check becomes three lines answering "can this instance work in this repository". | 3 |
| A-4 | `src/domain/entities/repository.py:57-60` `MISSING_VERSION`, `OUTDATED_VERSION`, `:111` `CloneCheck.bmad_version`, `:119` `pending()`; `src/infrastructure/db/repositories/repository.py:29,59,76` | Stored in the `repository.clone_check` JSONB (migration `0003_repository.py:48`). Holds a version or one of two sentinels. | Remove from the entity; persistence keeps a compatibility write (section 5). | 3, 10 |
| A-5 | `src/application/use_cases/run_finished.py` (whole module); `src/infrastructure/db/run_finished.py:26-46`; wired at `src/infrastructure/dbos/startup.py:169-171` | After a `done` Run holding a `bmad.install` row, re-runs the clone check so the method cell refreshes. | Unwire at the composition root and delete the use case. The walker's optional `run_finished` seam stays: `_call` tolerates `None` (`walker.py:268`), and it runs inside an existing step (`walker.py:245-252`), so the walk's step sequence does not change and `DBOS_APPLICATION_VERSION` is not bumped. | 3 |
| A-6 | `src/application/steps/bmad_install.py` (whole), including `:49-61` `INSTALL_COMMAND` and `:65` the three ignore lines `.claude/skills/bmad-*`, `.agents/skills/bmad-*`, `.opencode/commands/bmad-*`; `src/application/steps/__init__.py:100` kind table; `src/infrastructure/dbos/startup.py:38` import; `backend-api/AGENTS.md:30` kinds list; spine table `:384` | A step kind named after one method. Runs the pinned installer, then edits `.gitignore`. | Replaced by ordinary `shell` rows in the template (PR 6), then retired after a deprecation release (PR 10). | 6, 10 |
| A-7 | `src/application/steps/context.py:137-138` `RunEnvironment.bmad_version`; `src/infrastructure/db/environment.py:53,76`; passed at `src/api/providers.py:391`, `src/infrastructure/jobs.py:84`, `src/infrastructure/dbos/startup.py:166` | Carries the pin to exactly one reader, `bmad_install.py:85`. | Delete when the kind goes. | 10 |
| A-8 | `src/application/templates/rows.py:153-154`, `templates/plan.py:96,123`, `use_cases/plan_run.py:80,84`, `use_cases/preflight.py:59,213` | The planner's context carries `bmad_version`. Nothing reads it: `git grep` finds only the assignments. Dead since the executors took it from `RunEnvironment`. | Delete. | 3 |
| A-9 | `src/infrastructure/settings.py:225`; `.env.example:111` and `deploy/.env.example:124`, comment *"must equal `_bmad/_config/manifest.yaml` in every target repo (AD-16)"*; `src/api/providers.py:168`; `api/routers/clone_check.py:85`, `routers/projects.py:117`; `application/jobs/clone_check.py:24,28`; `infrastructure/jobs.py:64`; `infrastructure/db/seed.py:105`; `use_cases/harness_readiness_seed.py:75,85` | An instance setting whose stated meaning is a rule about other repositories. | The rule goes, not the variable. The comment goes in PR 1, the call-site arguments in PR 3. The variable stays as a packaging pin (C-2, Q4). | 1, 3 |
| A-10 | `src/api/schemas/clone_check.py:57,68` `CloneCheckResultOut.bmad_version`; `src/api/schemas/projects.py:138,181` `CloneCheckOut.bmad_version`; `contracts/openapi.json:707-736,755-795`; `web-client/src/api/schema.d.ts:993,1014` (generated) | A required, nullable API field. The `CloneCheckOut` docstring (`projects.py:131`) pins "exactly four keys". | Drop from both schemas; regenerate with `make openapi`. | 3 |
| A-11 | `web-client/src/pages/projects/index.astro:70-72,99,107`; `src/components/RepositoriesTable.astro:56-61,70,78,99,114,124`; `src/components/repository-row.ts:8` | A `method` column. The *Initialise repository* button appears only when the cell reads `missing` or `outdated`, and the done state reads `initialised · v{version}`. | Remove the column and `methodNeedsInit`; see Q5 for the button. | 3 |
| A-12 | `web-client/src/components/projects/CloneCheckReadout.astro:8,25,40-43,82-84` | A fixed `method version` line and *"run Initialise repository after save"* for a repository that needs nothing. | Remove. | 3 |
| A-13 | Moved to C-13 in this revision. | | | |
| A-14 | `scripts/readiness_fixture.sh:4-10,17,43-51`; `backend-api/docker-entrypoint.sh:44`; `fixtures/readiness-repo/README.md:8`; spine `:161,:396` | At every boot, runs `npx bmad-method@…` and appends the ignore lines into the fixture under `set -e`. A failure stops the container. | The install leaves the boot path. The fixture copies the overlay the image already holds; with none available it is built without `_bmad/` and says so in the log (PR 4). | 4 |
| A-15 | `backend-api/tests/e2e/helpers/gates_fixture.py:21,53`; `helpers/hub_fixture.py:78`; `web-client/tests/e2e/uj3-fixture.ts:8-9,59-61`; `fixtures/gates-repo/README.md:34`; `fixtures/hub-repo/README.md:37`; `os.environ["BMAD_VERSION"]` readers in nine e2e modules (`test_answer_signal.py:85`, `test_budget_raise.py:75`, `test_checkpoint_signals.py:66`, `test_hub_run.py:116`, `test_retry_prompt_detail.py:98`, `test_skip_step.py:71`, `test_skip_story.py:72`, `test_spec_edit.py:55`, `test_uj3.py:129`) | E2E fixtures write a fake manifest for the sole purpose of passing the gate. | Harmless after PR 1, deleted in PR 3 with the rest of the plumbing. | 3 |

### (b) Generic mechanisms to keep, renamed or made neutral

| id | where | how it behaves today | what happens | PR |
| --- | --- | --- | --- | --- |
| B-1 | `src/application/preflight/lists.py:200-262` `installed_skill_lines`; `preflight/model.py:36` | Every `skill:` a plan names must be in the catalog: `fail · not installed: {name}`. Reads no method. | **Keep unchanged.** This is the generic check that survives. | — |
| B-2 | `src/application/steps/agent_skill.py:33-50` | The same check at dispatch: parks `misconfigured`. | Keep unchanged. | — |
| B-3 | `src/infrastructure/skill_catalog.py:10-13`; `scripts/harness/_common.sh:243-256` `write_skills_manifest`, `:271-297` `sync_operator_skills`, `:304-332` `install_operator_skills`; `src/infrastructure/skills_install.py` | Catalog of skill names; boot sync; build-time collision refusal. Only the comments say "BMAD". A fault is reported, never raised (`skills_install.py:27-31`), which is the precedent PR 4 follows. | Keep; neutral comments. | 9 |
| B-4 | `src/domain/ports/harness.py:240-246` `skills_dir`, set at each adapter (`claude/adapter.py:107`, `codex/adapter.py:147`, `opencode/adapter.py:186`) | Where a harness reads global skills. | Keep; neutral comment. | 9 |
| B-5 | `src/application/steps/agent_render.py` (whole): `:59` `RENDER_SCRIPT`, `:63` `ACCEPTED` (unused constant), `:66-67` `FOLLOW`, `HALT`, `:76` `WORKFLOW_ENTRY`, `:92-107` `render_argv`, `:121-130`, `:133-170`; `agent_workdir.py:25,31-33`; `agent.py:189,287`; `agent_prompt.py:75` `{path}` token | If the worktree has the BMAD renderer and the skill has `workflow.md`, the orchestrator runs `uv run … render_skill.py`, parses stdout, and fills the template's `rendered` clause. Otherwise it silently skips. A renderer that fails parks. | Keep the mechanism (it ended a measured failure, `agent_render.py:9-17`). Make it a template-declared pre-dispatch command; BMAD knowledge moves to a script the template names. | 7 |
| B-6 | Moved to C-14 in this revision. | | | |
| B-7 | `settings.py:179` `init_template`; `src/api/routers/repository_init.py:78`; `use_cases/repositories.py:3-14`; `use_cases/project_runs.py:24,75,107`; `api/schemas/projects.py:200-202,222`; `web-client/src/actions/repositories.ts:43-67`; `web-client/src/lib/projects/runs.ts:36-37` | Already generic: a configured Template name. `min_length=1` means it cannot be switched off. `repositories.py:4-5` wrongly says the shipped plan has no `agent` step. | Keep, and correct that comment. The action stops depending on a version (Q5). Blank is not proposed (Q11). | 3 |
| B-8 | `settings.py:182` `readiness_template` default `epic`; `harness_readiness.py:58-61`; `harness_readiness_evaluate.py:202-214`; `fixtures/readiness-repo/` | Evaluation finds rows by kind and is neutral. The fixture story and spec are neutral. Only the default template is not; a BMAD fault can withdraw a harness through it. | Keep the mechanism; ship a method-neutral default. | 5 |
| B-9 | `src/application/steps/agent_tail.py:69` `STORY_FILE_GLOB`, `:296-315`; `use_cases/step_detail.py:87`; `use_cases/record_trajectory.py:231`; `use_cases/run_files.py:14`; `infrastructure/harness/fake/adapter.py:82` | `{spec_folder}/stories/{id}-*.md` is the fallback when a row declares no `expect.files`. | Keep. This is the orchestrator's own convention. The staged family already overrides it with `stories/.auto/` markers (`staged-story.yaml:64`). | — |
| B-10 | `src/application/preflight/lists.py:30-32`; `preflight/model.py:31-34`; `application/templates/lists.py:55-56`; `application/rules/protected_paths.py:48-50`; `domain/ports/protected_paths.py:3` | `epics.yaml`, `stories.yaml`, `SPEC.md` as list files and AD-17 anchors. | Keep. They are the orchestrator's format, not BMAD's: *"BMAD's epics and stories are not the hub format"* (`deploy/kit/skills/initiative-spec/SKILL.md:127`). | — |
| B-11 | `application/templates/lists.py:78-79,170-193,212`; `rows.py:334-344` | FR-10: a story whose file states `status: done` is skipped. | Keep. Hard-codes one token, `done`, which is the orchestrator's own. | — |
| B-12 | `application/rules/routing.py:61` `DEFAULT`, `checkpoint=("ready-for-dev",)` | A row declaring no routing lists routes on BMAD's token. | Keep as the compatibility default for stored templates; shipped rows already declare the list. Neutral comment. | 8 |
| B-13 | `application/templates/model.py:44-45` `STATUS_TOKENS`; `templates/agent.py:213`; `templates/expressions.py:256` | `status_in` and `escalate_when` validate against BMAD's six tokens, while the newer `expect.*` lists are free-form (`agent.py:50`, `model.py:155`). | Make the legacy keys free-form too. Accepting a superset breaks no stored template. | 8 |
| B-14 | `application/story_file.py:37-43` `## Auto Run Result`, `Blocking condition:`; `steps/agent_answer.py:37,68,293`; `rules/routing.py:153-158`; `use_cases/step_detail.py:9,71,101` (the heading written a second time as a literal); `api/schemas/step_detail.py:40` | The operator's Question is read only from this BMAD HALT section. A non-BMAD template that writes `status: blocked` parks with an **empty** reason, because `section()` returned `""`. | Declarable on `expect`, with these as defaults; a sentence naming the file when nothing is found. One definition of the heading. | 8 |
| B-15 | `application/story_file.py:45-48`, `:136-141` `after_verify`; `steps/agent_prepare.py:121-134`; `use_cases/walk.py:174` | A failed `verify` rewrites the file to `status: in-progress`, because *"`bmad-build-auto` routes `in-progress` straight to implementation"* (`:46`). | Declarable on `expect`, `in-progress` the default. The `## Verify Failure` section is the orchestrator's own and stays. | 8 |
| B-16 | `steps/agent_prepare.py:57,137-155`, `agent_workdir.py:13` | Writes `{spec_folder}/project-context.md`. BMAD retired that name (`bmad-project-context/SKILL.md:90`), so it is the orchestrator's own document now. | Keep. No rename: it would churn stored prompts for nothing. | — |
| B-17 | `AGENTS.md:7` (Operator-only anchor); `README.md:3`; `backend-api/pyproject.toml:4`; `src/infrastructure/mcp/facade.py:44`; `web-client/src/components/NewWorkflowFields.tsx:64`; `deploy/kit/.claude-plugin/plugin.json:3`; `.claude-plugin/marketplace.json:10`; `deploy/kit/skills/orchestrator/SKILL.md:3,8` | Product identity: *"runs BMAD dev-loop workflows"*. The UI tooltip says *"which BMAD workflow"*. | Neutral copy. | 9 |
| B-18 | Comments: `rules/routing.py:24,59`, `story_file.py:37,46`, `claude/adapter.py:11`, `use_cases/walk.py:290`, `templates/branches.py:3,5,24,72`, `templates/plan.py:12,22`, `infrastructure/kit.py:7`, `api/routers/clone_check.py:78`, `routers/projects.py:187`, `scripts/harness/codex.sh:61`, `_common.sh:4,188-189` | Describe a rule, or use a BMAD name as the example. No behaviour. Two render into OpenAPI descriptions (`openapi.json:5525,6222`). | Reword when the code beside them changes, per the repo's comment rule. Not a sweep of its own. | each |
| B-19 | Kit text stating the rule: `deploy/kit/skills/orchestrator/SKILL.md:53,67-68,90-91`; `references/api.md:19,64`; `references/first-run.md:21-24,178`; `references/workflows.md:99`; `references/spec-folder.md:6-8`; `orchestrator-admin/SKILL.md:87,101,234`; `initiative-spec/SKILL.md:102-105`; `initiative-spec/references/chain.md:25,32-34` | Agents are told a repository with a different manifest *"is not ready to dispatch"* and that preflight fails. Becomes false at PR 1. | The false statements change with PR 1, the rest with the PR that changes the behaviour they describe. | 1, 3, 4, 6 |
| B-20 | Spine: AD-16 `:214-218` title and rule; `:161`; `:265` branch name; `:295` version table; `:354` `clone_check{…bmad_version}`; `:384` kinds; `:396,:401`; `:441` env table; `:452-453` FR-2, FR-30; `:455` FR-8; `:498-499` open risks. The PRD that defined FR-30 was removed on 2026-09-23 (`_bmad-output/README.md`); its surviving statements are the spine's. | The binding record of these rules. AGENTS.md: *"when code and spine disagree, stop"*. | Each PR amends the spine in the same commit. Draft for AD-16 in section 6. | each |
| B-21 | Operator docs: `README.md:225-227,238-239`; `templates/README.md:24,27`; `deploy/README.md:66,160` | Walkthrough says the clone check *"reports the target's BMAD state"* and to initialise *"if the target has never run the BMAD method"*. | Reword with the behaviour change. | 3, 6 |

### (c) Packaging and content that may stay

| id | where | what it is | note |
| --- | --- | --- | --- |
| C-1 | `scripts/harness/_common.sh:190-201` `bmad_install_global_skills`; called at `claude.sh:30`, `codex.sh:20`, `opencode.sh:26`; `backend-api/Dockerfile:162-165` | Installs the stubs into the image, for every harness. Exactly what the Operator described. | Stays, by the Operator's requirement. PR 4 also keeps a copy the volume cannot hide. |
| C-2 | `scripts/harness/_common.sh:11`; `scripts/readiness_fixture.sh:17`; `.env.example:111`; `deploy/.env.example:124`; `settings.py:225`; `README.md:406-410` | The pin. Today `.env` decides the gate, the fixture and `bmad.install`, and the literal decides the stubs. Cross-checked by `test_harness_scripts.py:233-238`. | Stays, and becomes one pin that also decides the stubs, on the pattern of the CLI pins (PR 4, Q4). |
| C-3 | `agent-home` volume, `docker-compose.yml:151-153`, `deploy/docker-compose.yml:145-147` | Stubs in an existing volume never update; only operator skills sync at boot. | Content stays. This is a live defect, and the default install has to reach these volumes: PR 4 syncs the stubs at every start. |
| C-4 | `templates/repo-init.yaml` (`chore/bmad-init`, `bmad-project-context`) | A shipped template. Its only coded tie is `uses: bmad.install`. It is what puts `_bmad/` in a repository, which the harness install does not (finding 6). | Stays; rewritten in PR 6. |
| C-5 | `templates/story.yaml:22`, `initiative-hub-story.yaml:43`, `epic.yaml:75,103`, `initiative-hub-epic.yaml:118,149`, `staged-epic.yaml:100,129`, `staged-hub-epic.yaml:130,161` | Templates that choose to call a BMAD skill. The code does not special-case them. | Stays. The epic-level ones gain a guard row in PR 2; BMAD rows gain a `prerender` declaration in PR 7. |
| C-6 | `rendered` clauses naming `render_skill.py`, `templates/*.yaml` and the sibling headers (`staged-story.yaml:8`, `staged-hub-story.yaml:8`) | Template prose. The `staged-*` skills have no `workflow.md`, so that clause never fires on their rows. | Stays. PR 7 may drop the clause from the rows that can never use it. |
| C-7 | `templates/drafts/story-staged.yaml:7,75` | Never seeded. | Stays. |
| C-8 | `deploy/kit/skills/initiative-spec/` planning chain | A skill that uses BMAD to plan. Content. Only the lines in B-19 state an orchestrator rule. | Stays. |
| C-9 | `ia-agents-skills/README.md:9,19`; `spec-gate`, `staged-*` | Operator skills. `git grep` finds no BMAD reference in the skills themselves. | Stays. |
| C-10 | This repository's own tooling: `_bmad/`, `_bmad-output/`, 248 tracked files under `.agents/skills/bmad-*` (tracked despite `.gitignore:8`), `.gitignore:1-8`, `.dockerignore:22-23`, `README.md:404-418`, `test_gitignore.py:57-59`, `web-client/tests/e2e/*` screenshot paths | How *this* repository is developed, not how the product behaves. `.dockerignore` keeps it out of the image. | Stays. Renaming `_bmad-output/` would be churn; see Q10. |
| C-11 | `fixtures/gates-repo/.fake-harness/1/attempt-1.yaml:4`; test sentences such as `test_claude_adapter.py:40`, `test_install_operator_skills.py:66-115` | A name used as example data; the behaviour under test is generic. | Stays. |
| C-12 | Comments: `docker-compose.yml:80,151`, `deploy/docker-compose.yml:79,145`, `deploy/llm-platform/README.md:497`, `ci.yml:193`, `test_dockerfiles.py:181,281` | True statements about what the volume or image holds. | Stays; "skill stubs" reads fine when next touched. |
| C-13 | `scripts/harness/_common.sh:334-337` `doctor_skill_present`; called at `claude.sh:111`, `codex.sh:99`, `opencode.sh:129`; `make platform-doctor`, `Makefile:220` | Exits non-zero when `bmad-build-auto/SKILL.md` is absent. Only an operator runs it; no Run, probe or `enabled` flag reads it. Reporting a default capability is legitimate. | Stays as a report: it names the stubs and their version, and it warns rather than failing, so a missing stub does not hide the gateway check after it (PR 4). |
| C-14 | `src/api/routers/version.py:66,80`; `contracts/openapi.json:4783-4805`; `web-client/src/api/schema.d.ts:2492`; `deploy/install.sh:553,920-923`; `src/infrastructure/mcp/tools.py:36`; `test_install_admin.py:127`; `test_version_router.py:79` | `/api/v1/version` publishes `bmad_version` beside `harness_versions`, and `doctor` prints it. It reports; nothing decides on it. | Stays, under its name, and gains what is really installed (PR 4, Q4). |

### Tests that pin these rules

Hard rule 1 applies: each revision traces to the Operator's declared change of 2026-10-30 and
asserts the new behaviour at least as thoroughly. Hard rule 6 applies: a new test owns fixture
copies and never pins `templates/*.yaml`. Of 169 test files mentioning BMAD, 101 mention
`bmad_version` or `BMAD_VERSION`, most only as a constructor argument, so PRs 3 and 10 touch
many files mechanically.

| rule | tests | PR |
| --- | --- | --- |
| Preflight line | `unit/application/preflight/test_checks.py:18,641-705`; `unit/application/test_preflight_use_case.py:13,128,194-205`; docstrings at `test_create_run_probe_gate.py:44`, `test_create_run_use_case.py:157` | 1 |
| Clone-check line and stored value | `unit/test_clone_check_use_cases.py` (20 hits, including `:266`); `unit/test_clone_check_entity.py:89`; `unit/test_clone_check_schemas.py`; `unit/test_clone_check_router.py`; `unit/test_repository_entity.py`; `unit/test_repository_schemas.py`; `unit/test_repository_repository_adapter.py`; `unit/application/test_jobs_clone_check.py`; `e2e/test_clone_check.py:221-230` (16 hits) | 3 |
| `run_finished` | `unit/application/test_run_finished.py`; `unit/test_run_finished_hook.py`. `unit/test_dbos_walker_on_finished.py` pins the seam, which stays. | 3 |
| Web client | `tests/unit/clone-check-readout.test.ts:70-140`; `tests/unit/repository-init-control.test.ts:95-96`; `tests/unit/projects-components.test.ts:107-113`; `tests/e2e/project-form.spec.ts:81`; `tests/e2e/stub-backend.mjs:222-358`; `tests/e2e/projects-fixtures.mjs` | 3 |
| Readiness boot and default template | `unit/test_readiness_fixture_script.py`; `unit/application/test_harness_readiness_seed.py`; `unit/application/test_readiness_declares_no_quality_gate.py:70,98,147` | 4, 5 |
| Kind and executor | `unit/test_bmad_install_executor.py` (11 tests); `unit/application/templates/test_step_kind_registry.py:67`; `unit/application/templates/test_shipped_templates.py:223,253-262`; `unit/application/templates/test_plan_shipped.py:36`; `unit/test_run_values.py:171`; `unit/test_process_step_log_names.py`; `unit/test_run_environment_*.py`; `e2e/test_repo_init.py`; `e2e/test_repo_init_commit_scope.py`; test-owned copies `unit/application/templates/fixtures/exemplars/repo-init.yaml:17`, `e2e/templates/repo-init.yaml:22` | 6, 10 |
| Render | `unit/application/steps/test_agent_render.py`; `unit/application/steps/test_agent_prepare.py` | 7 |
| Pin and contract | `unit/test_settings_defaults.py:88`; `unit/test_version_router.py:79`; `unit/test_install_admin.py:127`; `unit/test_harness_scripts.py:233-238`; `unit/test_dockerfiles.py:181,240,245`; `unit/test_push_images.py`; `unit/test_env_contract.py`, `test_deploy_env_contract.py` via `scripts/check_env_contract.py` | 4 |
| A template fixture naming a skill as data | `unit/application/templates/test_retro_step.py` calls `bmad-retrospective` *"an architectural anchor"* against frozen exemplars, so it pins no shipped file. | leave |

### Counts

(a) 14 · (b) 20 · (c) 14 — 48 items, each of which may span several files. Two moved to (c) in this revision, because reporting a default capability is packaging (A-13, B-6). Of the (b) items,
six (B-1, B-2, B-9, B-10, B-11, B-16) need no change at all.

## 3. Removing the gate, and what is really lost

### The simplest first step

Delete `method_version_line` and its call at `preflight.py:170`. No plan is checked against any
method version from then on. This is PR 1, a few dozen lines, no API change (a preflight `name`
is a plain string and the web client renders lines generically, so `make openapi` should show
no drift) and no migration.

Do not leave it as a `warn` or a `skip` line. Either would keep the manifest read, and the rule,
in code.

### What protection goes

| case | today | after PR 1 | how bad |
| --- | --- | --- | --- |
| Plan with no skill (`agent-smoke`) | refused on `missing` or `outdated` | runs | The defect being fixed. |
| Repository with no `_bmad/`, plan names only operator skills (`staged-*` rows) | refused | runs correctly: they have no `workflow.md` and need no renderer | The defect being fixed. |
| Repository with no `_bmad/`, plan names a BMAD skill | refused before the Run | The skill passes the catalog check, as it always will with the default install (finding 6). `agent_render.py:126-127` skips, and the harness gets a stub whose `SKILL.md` runs a script that is not there. It should HALT; the 2026-09-21 finding (`agent_render.py:9-17`) measured agents improvising instead. The Run then parks on no story file, or on what the retry bound allows, having spent budget. | **A real loss.** Spend and time, not integrity: AD-17 anchors, verify rows and the commit guard all still apply. |
| Repository with `_bmad/` at another version, BMAD skill | refused | `render_skill.py` from the repository reads the skill from the image. A hard failure parks `misconfigured` (`agent_render.py:164-169`). A soft mismatch renders something and proceeds. | **A real but narrow loss**, and only partly covered today, because of finding 1: the gate compared the variable, not the stubs. How often versions break the renderer is unmeasured. This is production's own case, with repositories at 6.11.0 and the pin at 6.12.4: PR 1 lifts the refusal, and section 5 covers what PR 4 then changes. |

### What replaces it

Nothing in code compares versions. Two generic things carry the real protection:

1. **The skill-exists check stays exactly as it is** (B-1, B-2), at preflight and at dispatch.
   It answers the question the orchestrator can answer without knowing any method.
2. **The template declares what it needs.** PR 2 adds a guard row to the shipped epic-level
   templates that lead to a BMAD skill, after the worktree row and before the first such dispatch:

   ```yaml
   - id: method-present
     run: "test -f _bmad/scripts/render_skill.py"
     timeout_min: 1
     on_fail: fail
     gate: deterministic
   ```

   No code changes and no spend: the Run stops in seconds with the path in its log. A template
   that wants version equality can write that comparison in the same row, because then the
   template owns the rule. This plan recommends it does not. PR 7 strengthens this: a row that
   declares a `prerender` and finds it missing parks, where today it skips silently.

The difference from a preflight check is that a guard row fails after the Run is created rather
than before. A template-declared `requires:` preflight list would close that gap at the cost of
a new DSL key. It is not recommended now: the gap is seconds and no money, and it can be added
later without undoing anything (Q2).

### PR #9

**Recommendation: do not merge. Close it, unmerged, when PR 1 merges.** Everything it adds
(the `plan dispatches no skill` skip, the AD-16 exception, the two helpers) would be deleted by
PR 1, and the two conflict on the same lines of `checks.py`, `test_checks.py` and AD-16.

Two things are worth carrying into PR 1: the `OWN_TEXT_YAML` fixture from its
`test_preflight_use_case.py` becomes the regression test for "a plan runs on a repository with
no method", and `row_skill` is a reasonable small refactor of `lists.py:225-231` only if PR 1
needs it, which it does not. This plan did not touch PR #9. If the Operator chooses to keep the
gate for skill plans (Q1), PR #9 is already that change and PR 1 is dropped.

PR #8 (harness upgrades) merged at `fc5d800`, so nothing here waits for it. It supplies the
pattern PR 4 reuses (`ensure_cli_at_pin`, `_common.sh:137`; `ensure-all.sh`). Its line
`.env.example:108`, *"BMAD_VERSION is baked into the image at build and never reconciled at
start"*, and its twin at `deploy/.env.example:123`, become false at PR 4.

## 4. The PRs, in order

Each PR ships alone, leaves `make lint` and `make test` green, and amends the spine in the same
commit. Branch prefixes follow the repository's conventional commits. Suggested release grouping
is in section 5. The numbers are the order; this revision renumbered from PR 4 on:

| now | was | change |
| --- | --- | --- |
| PR 1, 2, 3 | same | Kept. PR 2 matters more, not less (finding 6). PR 3 no longer makes `INIT_TEMPLATE` blankable. |
| PR 4 | PR 8 and half of PR 4 | One PR for the default install: build, boot sync, fixture, pin, reporting. They share one bundle, and it has to land before the new PR 6, which reads what it installed. |
| PR 5 | the other half of PR 4 | The neutral readiness default, on its own. |
| PR 6 | PR 5 | Same content; now reads the installed version. |
| PR 7 | PR 6 | Unchanged. |
| PR 8 | PR 7 | Unchanged. |
| PR 9 | PR 9 | Also states that BMAD is installed by default. |
| PR 10 | PR 10 | `Settings.bmad_version` is no longer removed anywhere. |

Dropped outright: moving the pin to a literal with no environment override, removing `BMAD_VERSION`
from the env contract, and a generic `packaged_tools` field on `/version`. Each assumed the method
was something to hide rather than a default to report.

### PR 1 — `fix(preflight): no plan is checked against a method version`

- **Scope:** A-1, A-2. Comment half of A-9. The kit sentences that become false (B-19). AD-16 and
  the FR-8 row reworded.
- **Files:** `application/preflight/checks.py`, `preflight/model.py`, `use_cases/preflight.py:110,170`;
  `use_cases/run_finished.py:31` (the constant moves to `steps/bmad_install.py::KIND`); `.env.example:111`,
  `deploy/.env.example:124` (the comment becomes *"the BMAD stubs installed in every harness; no
  relation to any repository"*); `deploy/kit/skills/orchestrator/SKILL.md:67-68`,
  `references/first-run.md:21-24,178`, `initiative-spec/SKILL.md:102-105`, `references/chain.md:32-34`;
  spine `:218,:441,:455`.
- **Tests:** remove the line-9 block in `test_checks.py`; revise `test_preflight_use_case.py:128,194-205`.
  New: a plan with a skill row on a repository with no manifest has no `method version` line and
  `read_file` is never asked for that path; `create_run` accepts it; the catalog check still fails
  an unknown skill. Each revision names the 2026-10-30 ruling.
- **API / DB:** none. `PreflightPorts.bmad_version` stays until PR 3, for `plan_run`.
- **Risk:** the loss in section 3. **Rollback:** revert; no data involved.

### PR 2 — `feat(templates): BMAD templates state their own prerequisite`

- **Scope:** the guard row in `epic` and `initiative-hub-epic`, before the story loop, since their
  story templates call `bmad-build-auto`; and in `staged-epic` and `staged-hub-epic`, before the
  epic-tail BMAD rows, so a repository with no method still gets its stories built and stops at
  the tail (Q3). Epic level on purpose: once per epic rather than per story, and outside the Story
  frame, whose rows `record_trajectory` and readiness evaluation read by kind. `repo-init` needs
  none: it installs the method itself. The guard checks the repository, not the harness: with the
  default install the stubs are always there, so this row is the only fast stop (finding 6).
- **Files:** those four templates; `templates/README.md`.
- **Tests:** none pinning shipped content (hard rule 6). `test_shipped_smoke.py` must stay green.
  One new test on a fixture copy: a failing `run` row with `on_fail: fail` stops before the next
  agent row. If that is already covered, no new test.
- **API / DB:** seeds new template versions by hash at start-up. A Run already planned keeps its rows.
- **Risk:** a repository without `_bmad/` running `epic` now stops at the guard, which is the intent.
- **Rollback:** revert. Note the seeding hazard in section 5: the guard version stays newest in the
  database unless restored, and it stays valid under the old code.

### PR 3 — `refactor!: the clone check stops reading a method`

- **Scope:** A-3, A-4 (entity and API; compatibility write stays), A-5, A-8, A-10, A-11, A-12,
  A-15, the call-site half of A-9, B-7, B-21. One PR because the API field and its only UI ship in
  the same image tag.
- **Files:** `use_cases/clone_check.py`, `domain/entities/repository.py`,
  `infrastructure/db/repositories/repository.py`, `api/schemas/{clone_check,projects}.py`,
  `api/routers/{clone_check,projects}.py`, `application/jobs/clone_check.py`,
  `infrastructure/{jobs,dbos/startup}.py`, `infrastructure/db/{seed,run_finished}.py`,
  `use_cases/{run_finished,harness_readiness_seed,plan_run,preflight}.py`,
  `templates/{plan,rows}.py`; `contracts/openapi.json`, `web-client/src/api/schema.d.ts` (generated);
  `web-client/src/{pages/projects/index.astro,components/RepositoriesTable.astro,components/repository-row.ts,components/projects/CloneCheckReadout.astro}`;
  e2e fixtures; `README.md:225-227`; spine `:354,:452-453`.
- **The action:** *Initialise repository* is offered whenever no init Run is in progress, including
  after a finished one, whose compare link stays beside it. Today `initControl`
  (`RepositoriesTable.astro:70-85`) hides the button after a `DON` Run, and with no version cell
  that would be permanent, leaving no way to move a repository's `_bmad/` to a newer pin (Q5).
- **Tests:** the clone-check, `run_finished` and web-client rows of the test table. New:
  `clone_check_from_entity` reads a row with the key, with `null`, and without it, and with a stored
  `method version` line.
- **API:** `clone_check.bmad_version` removed from `CloneCheckOut` and `CloneCheckResultOut`.
  Breaking for an external client, which is acceptable in a beta and named in the release notes.
- **DB:** no migration. Section 5 has the read and write rule.
- **Risk:** low in behaviour. Wide in files; coverage rules (100 % on `application`, 90 % on
  changed lines) make it a thorough diff rather than a dangerous one. A second init on a repository
  reuses `chore/bmad-init` when the origin still holds it (`git_worktree.py:190`), so an unmerged old
  branch is continued rather than rebased onto the new base, and it dispatches the context agent
  again, which spends. `git.commit` ends `no changes` rather than failing (`git_commit.py:83`).
- **Rollback:** revert the image. Stored rows stay readable by the old image because the key is
  still written.

### PR 4 — `feat(deploy): the default BMAD install is packaging, and it never stops a start`

- **Scope:** A-14, C-1, C-2, C-3, C-13, C-14. Replaces the old PR 8 and the first half of the old PR 4.
- **Where the install happens: at build always, at boot as a copy, from the registry at boot only
  when the Operator set a pin the image does not carry.**

  | when | what | registry | if it fails |
  | --- | --- | --- | --- |
  | Image build, `<harness>.sh install` | Installs `bmad-method@$BMAD_VERSION` once into a bundle at `/opt/harness-image/bmad/<version>/`, holding `_bmad/` and each harness's stubs, then seeds the harness homes from it as today. `/opt/harness-image` is PR #8's prefix and is never mounted, so no volume can hide it. | yes | **The build fails.** That is the right stop: a release must not ship without its default capability, and no running instance is affected. |
  | Every start, pin is the image's | Copies the bundle's stubs over each harness's skills directory. | no | Logged. That harness keeps what it holds. The start continues. |
  | Every start, pin is not the image's | The bundle on the `harness-bin` volume at that pin if present, else exactly one `timeout 120 npx bmad-method@<pin>` into staging there, moved in only when its manifest reports the pin. Hard rule 7: no retry until the next start. | once, and not again while the volume holds that pin | Logged. That harness keeps what it holds. The start continues. |
  | Every start, the fixture | `readiness_fixture.sh` stops running `npx` and copies `_bmad/` from the bundle at the pin, else the image's own. | no | Built without `_bmad/`, with a log line. Only its `git` commands stay under `set -e`; they are not about BMAD. |

- **How it reaches existing `agent-home` volumes.** `ensure_bmad_at_pin`, beside `ensure_cli_at_pin`
  and in the same order of preference, driven by a second loop in `ensure-all.sh`, which already
  exits 0 whatever happens (`ensure-all.sh:13`). It runs from the entrypoint rather than from the
  `skills` verb for two reasons: the verb's environment is only `PATH`, `HOME` and `AGENT_HOME`
  (`skills_install.py:60`), so it cannot see the pin; and it runs after the fixture
  (`main.py:194`). The sync copies a stub the volume lacks, replaces one that differs (the image is
  the source of truth, as `_common.sh:267` already rules), removes only a name the previous bundle
  installed and this one does not, and never touches a name in `ia-agents-skills/`: the operator
  skill wins, with a log line, because the build-time collision refusal cannot cover a pin chosen
  later. The `skills` verb then rewrites the catalog, so it names what is really there.
- **How a failure is surfaced.** Nothing else in the app reads any of this:
  1. A start log line per harness: `bmad-method 6.12.4 not installed: keeps 6.11.0`, with the cause.
  2. `${AGENT_HOME}/.bmad-stubs.json`: the pin, and each harness's installed version and skill names.
  3. `/api/v1/version` keeps `bmad_version` (the pin) and gains `bmad_installed`, per harness.
     `./install.sh doctor` reports `warn` when they differ, and `<harness>.sh doctor` warns (C-13).
  4. At a Run, the existing catalog check: a plan naming a skill that is not there is refused with
     `not installed: {name}` (B-1, B-2). A plan naming none is untouched.

  The state file is not read by preflight, by the harness probe, or by `enabled`. A harness with no
  stubs is still offered, and still runs own-text and operator-skill plans.
- **How the installed version is upgraded.**
  1. *With a release.* `BMAD_VERSION` joins `HARNESS_PIN_VARIABLES` (`install.sh:796`), so
     `./install.sh upgrade --tag X` shows and writes the release's value, marking a downgrade. The
     image carries that bundle, so the recreate lays the stubs down with no registry.
  2. *Between releases.* `./install.sh harness bmad --version X` through the `cmd_harness` version
     path (`install.sh:1020-1033`), or edit `.env` and `docker compose up -d backend-api`; `restart`
     does not re-read `.env`. The next start makes the one registry attempt in the table.
  3. *Repositories.* Never touched. A repository's `_bmad/` moves only through `repo-init`, as a PR,
     when someone chooses (Q5). The pin is not compared with it.
- **The pin:** a fourth valueless build `ARG` (`Dockerfile:154-156`, `docker-compose.yml:60-63`,
  `release.yml:148-166`, `push-images.sh:50`). The shipped value moves to 6.12.4 in this PR (Q4), so
  `upgrade` does not offer production a downgrade. `Settings.bmad_version` stays beside
  `claude_code_version`, and its only reader after PR 10 is `/version`.
- **Files:** `scripts/harness/{_common,ensure-all,claude,codex,opencode}.sh`,
  `scripts/readiness_fixture.sh`, `backend-api/docker-entrypoint.sh` (comment), `backend-api/Dockerfile`,
  both compose files (build args, volume and `start_period` comments), `.github/workflows/release.yml`,
  `scripts/push-images.sh`, both `.env.example` (`:108`/`:123` reworded), `api/routers/version.py`,
  `deploy/install.sh:553,796,920-923,1020-1033`, `fixtures/readiness-repo/README.md:8`, kit
  `SKILL.md:53`, `references/api.md:19`, `orchestrator-admin/SKILL.md:101,234`, spine `:161,:295,:396,:441`,
  `README.md:406-410`, `contracts/openapi.json` and `schema.d.ts` (generated).
- **Tests:** contract row of the test table, and `test_readiness_fixture_script.py` asserts no `npx`
  runs. New, in the style of the PR #8 tests in `test_harness_scripts.py`, with a stub `npx`: a failing
  install exits 0, keeps the old stubs and logs both versions; a stale stub on a scratch volume is
  replaced; an unknown skill and an operator-named skill are left alone; a stub the old bundle had
  and the new one lacks is removed; a volume with no state file loses nothing; a second start makes
  no registry call. Fixture script with no bundle: a valid origin with no `_bmad/`. Router: the new
  field, and `null` with no state file. `install.sh doctor` warns on a difference.
- **API / DB:** `/version` gains a field, so `make openapi`; the old `install.sh` ignores it. No DB.
- **Risk:** the first start moves stubs on real volumes, see section 5 for production. A Run recovered
  across a restart reads the new stubs, because rows are frozen but skills are not; operator skills
  already behave this way. A start can take up to 120 s longer, inside the 600 s `start_period`.
- **Rollback:** revert. The stubs stay in the volume at the version they reached, and an old image's
  fixture goes back to `npx` at boot. The `.env` value stays valid.

### PR 5 — `fix(readiness): a method-neutral default template`

- **Scope:** B-8.
- **What changes:** a new own-text shipped template, `readiness-check`, needing no skill: it plans
  the fixture's one story, asks the agent to create `HELLO.md` and write
  `specs/readiness/stories/1-hello.md` with `status: done`, then runs the verify shell row. The
  default in `settings.py:182` and both `.env.example` files moves to it. The fixture keeps its
  `_bmad/` overlay (PR 4), so `READINESS_TEMPLATE=epic` keeps working.
- **Files:** `templates/readiness-check.yaml`, `templates/README.md`, `settings.py`, `.env.example`,
  `deploy/.env.example`.
- **Tests:** a fixture copy of the new template evaluates all six lines `ok` through the existing
  `harness_readiness_evaluate` tests. `e2e/test_harnesses.py` must stay green on the fake harness.
- **API / DB:** none. `enabled` flags stay as they are; nothing forces a re-proof.
- **Risk:** a readiness Run proves less about BMAD stubs (Q6). An explicit `READINESS_TEMPLATE=epic`
  survives upgrade, because `install.sh` writes `.env` once and never overwrites it (`deploy/install.sh:23`),
  so such an instance keeps the dependency until that line changes. The release notes must say so.
- **Rollback:** revert; or set `READINESS_TEMPLATE=epic`.

### PR 6 — `refactor(templates): repo-init installs through ordinary rows`

- **Scope:** A-6 (first half), C-4, B-21. Needs PR 4.
- **What changes:** `templates/repo-init.yaml` replaces `uses: bmad.install` with a `run:` row
  calling a script the image carries, for example `bmad-repo-install`, placed on `PATH`. The script
  holds the installer flags and the three ignore lines. It reads the version from
  `.bmad-stubs.json`, because a `shell` row gets `env={}` (`shell.py:18-23`) and so no `BMAD_VERSION`;
  this also means a repository gets the version its harness really holds. The Python kind stays
  registered but unused.
- **Why a script rather than a version in the YAML:** hard rule 6 forbids a test that pins template
  content, so a literal `bmad-method@6.12.4` in the template could not be cross-checked against the
  pin, and would drift. See Q4.
- **Files:** `templates/repo-init.yaml`, `scripts/methods/bmad-repo-install.sh`, `backend-api/Dockerfile`,
  `scripts/readiness_fixture.sh` (shares the ignore lines), `deploy/kit/skills/orchestrator/references/workflows.md:99`,
  spine `:218,:384` (kind marked deprecated), `README.md:227`.
- **Tests:** a shell-level test of the script with a stub `npx`, in the style of
  `test_install_operator_skills.py`; idempotent ignore lines (the behaviour `test_bmad_install_executor.py`
  pins today, ported so coverage does not fall). `e2e/test_repo_init_commit_scope.py` keeps proving that
  no skill folder reaches the commit, via its own template copy.
- **API / DB:** a new `repo-init` version seeded. Stored versions keep working while the kind stays.
- **Risk:** a failed install now parks by the row's `on_fail` rather than as `misconfigured`, so the
  reason sentence changes. `POST /init` is unaffected.
- **Rollback:** revert. The new template version stays valid under old code.

### PR 7 — `refactor(agent): a template declares its pre-dispatch render`

- **Scope:** B-5. The highest-risk PR; it touches the dispatch path.
- **What changes:** an `agent` row may declare `with: { prerender: "<command>" }`, with the tokens
  `{worktree}` and `{skill_dir}`. The contract, method-neutral: exit non-zero parks `misconfigured`
  with the last output line; the last non-empty stdout line fills `{path}` in the `rendered` clause;
  empty stdout renders nothing. A declared command that cannot start parks, which is the generic
  replacement for today's silent skip. All BMAD knowledge (`_bmad/scripts/render_skill.py`,
  `uv run --no-cache`, `read and follow`, `HALT:`, the `workflow.md` skip) moves into
  `scripts/methods/bmad-render.sh`. The BMAD rows in shipped templates declare it. `staged-*` rows
  have no `workflow.md` and declare nothing.
- **Compatibility:** rows already persisted, and stored template versions, carry a `rendered` clause
  and no `prerender`. For one release, such a row uses the old command as an internal default, so a
  Run planned before the upgrade renders as it was planned to (AD-7). PR 10 removes the default.
- **Files:** `steps/agent_render.py`, `steps/agent.py`, `application/steps/__init__.py` (allowed `with`
  keys), `templates/*.yaml`, the script, `steps/agent_workdir.py:25,31-33`, spine AD-9 and the DSL table.
- **Tests:** `test_agent_render.py` rewritten against the contract with fake processes, and a fixture
  template for each outcome; a test of the script against the repository's own vendored
  `_bmad/scripts/render_skill.py`. `make e2e` is not enough, because it uses the fake harness
  (`skills_dir = None`): run one real-harness `story` Run on a scratch repository before merging.
- **Risk:** a real regression here silently degrades every BMAD story. **Rollback:** see the seeding
  hazard in section 5. Old code rejects a template with an unknown `with` key and would plan the
  newest stored version, so rolling back this PR needs the pre-upgrade database backup, or a
  re-saved template, for the affected names.

### PR 8 — `feat(templates): the result vocabulary is declared, not assumed`

- **Scope:** B-12, B-13, B-14, B-15.
- **What changes:** `expect` gains `question_section`, `condition_prefix` and `sent_back_status`,
  defaulting to today's values, so stored templates change nothing. `_blocked` falls back to a
  sentence naming the file when the section is absent, ending the empty-question park. `status_in`
  and `escalate_when` accept any token. `step_detail.py:101` uses the one definition. Shipped
  templates declare the values explicitly.
- **Files:** `story_file.py`, `rules/routing.py`, `steps/agent_answer.py`, `steps/agent_prepare.py`,
  `steps/agent_tail.py`, `use_cases/step_detail.py`, `templates/{model,agent,agent_row,expressions}.py`,
  shipped templates, spine FR-16 notes.
- **Tests:** a fixture template with a wholly non-BMAD vocabulary goes through blocked, answered and
  sent-back; defaults unchanged.
- **API:** `result` in step detail reads the declared section. No shape change. **DB:** none.
- **Risk:** low, defaulted. **Rollback:** same hazard as PR 7 if templates carry the new keys; ship
  the code and keep the keys out of shipped templates for one release if that matters.

### PR 9 — `docs: the product no longer describes itself as a BMAD runner`

- **Scope:** B-3, B-4, B-17, remaining B-18. The new copy says what is true: the orchestrator runs
  agent workflows, and BMAD is installed by default in every harness. It stops describing itself as
  a BMAD runner, not as a product that carries BMAD.
- **Files:** `README.md:3`, `backend-api/pyproject.toml:4`, `mcp/facade.py:44`,
  `NewWorkflowFields.tsx:64`, `plugin.json:3`, `marketplace.json:10`, `orchestrator/SKILL.md:3,8`,
  comments. **`AGENTS.md:7` and `backend-api/AGENTS.md:30` are anchors only the Operator changes**
  (hard rule 1), so they are proposed text in the PR description, unless the Operator approves the
  edit (Q9).
- **Tests:** copy assertions only, if any. **API / DB:** the MCP instruction string; none. **Risk:** none.
- Can ship any time after PR 1.

### PR 10 — `refactor!: retire bmad.install and the compatibility paths`

- **Scope:** the rest of A-4, A-6, A-7, the PR 7 default. Ships at least one release after PRs 6
  and 7, so nothing parked or planned still needs them.
- **What changes:** delete the kind, the executor and `RunEnvironment.bmad_version`
  (`Settings.bmad_version` stays, C-2). Stop writing
  the `bmad_version` key. Optional Alembic data migration to scrub the key and stale lines (Q7).
- **Files:** `steps/bmad_install.py`, `steps/__init__.py:100`, `dbos/startup.py:38`,
  `steps/context.py:137-138`, `db/environment.py`, `api/providers.py`, `infrastructure/jobs.py`,
  `db/repositories/repository.py`, `backend-api/AGENTS.md:30` (Operator), spine AD-16 and `:384`.
- **Tests:** kind row of the test table; test-owned template copies move to `run:` rows.
- **Risk:** a stored *operator-edited* template with `uses: bmad.install` stops validating, and a Run
  still parked on such a row gets `misconfigured · no executor for kind` (`registry.py:11,76`).
  Mitigation: the release notes give the SQL to find such templates, and the prior release's
  `doctor` can warn. **Rollback:** the prior image reads rows with no key only if PR 3's reader is
  in it, which is why this ships a release later.

## 5. Compatibility

### Existing instances and upgrades from 1.0.0-beta.2

| concern | what happens | verified how |
| --- | --- | --- |
| `BMAD_VERSION` in an instance `.env` | It remains the pin, and from PR 4 it also decides the stubs. A value above the shipped one is honoured, not ignored. `install.sh upgrade` refuses an `.env` that lacks the line, as it does for the CLI pins (`require_pin_declarations`), naming the line to add. | Read. |
| `.env` regenerated on upgrade | No: written once, never overwritten (`deploy/install.sh:23`). So `READINESS_TEMPLATE=epic` and `ROOT_TEMPLATES` persist; PR 4 keeps the fixture's overlay for that reason. | Read. |
| Stored `clone_check` rows | Carry `bmad_version` and possibly a `method version` line. Read tolerantly: `.get`, stale line ignored. Next check overwrites (03:00 daily cron, any project save, start-up for the readiness Project). The web client looks lines up by name, so a stale line never renders. | Read; not run. |
| Rollback to beta.2 | The old reader needs the key: `data[BMAD_VERSION_KEY]` raises `KeyError` if absent. **So PR 3 keeps writing `"bmad_version": null`.** The old type allows `None` (`repository.py:111`). The old UI shows `—`, and its gate returns. | Read; not run. |
| Stored template versions | Immutable and kept. `seed_shipped` inserts only when a file's hash is new across every version (`templates.py:_seed_file`). | Read. |
| **Rollback seeding hazard** | Because of that hash rule, an old image does not re-seed its older file: the hash already exists, and the newest stored version stays the one from the newer release. Old code then plans it. Harmless for PRs 2, 5 and 6 (valid under old code); **a template with a new `with` or `expect` key (PRs 7, 8) does not validate on old code.** Those rollbacks need the pre-upgrade backup or a re-saved template. | Read; not run. |
| Runs in flight at upgrade | Rows are frozen at plan time (AD-7). A planned `bmad.install` row works until PR 10. A row with a `rendered` clause renders through PR 7's default. Walker step sequence is unchanged, so no `DBOS_APPLICATION_VERSION` bump in any PR. | Read `walker.py:245-252`; not run. |
| Repositories already initialised | Their committed `_bmad/` keeps working and is never read by the orchestrator's rules. No action. Their `.gitignore` lines stay. | Read. |
| Repositories not initialised | Run anything; BMAD-skill templates stop at their guard. | By design. |
| Existing `agent-home` volumes | Hold stubs from when they were created, until PR 4, whose first start syncs them to the pin. No volume needs recreating. Names the previous bundle installed cannot be known on that first start, so a stub dropped upstream stays until the next pin change. | Read; not run. |
| **Production at the 6.12.4 pin, repositories at 6.11.0** | PR 1 lifts the refusal. PR 4's first start then lays the stubs down at 6.12.4, whatever they hold now (section 8), and no check stands between them and a repository's 6.11.0 `render_skill.py`. So the mismatch the gate reported could become real and silent at that start. Before beta.4 reaches production: run one real-harness `story` Run with 6.12.4 stubs on a scratch repository at 6.11.0, then either accept the result or merge `repo-init` PRs into the repositories first. | Read; not run, and the outcome is unmeasured. |
| Older kit installed in a project | May tell an agent to compare `bmad_version` (`orchestrator/SKILL.md:67`). Until refreshed, an agent might refuse a repository the instance would accept. The kit's handshake already says to stop on a kit/instance mismatch. | Read. |
| `deploy/install.sh` and `bmad_installed` | The field is new at PR 4. An older instance omits it, `json_object` yields blank, and `doctor` then reports the pin alone, without a warning. | Read. |

### Suggested release grouping

- **beta.3:** PRs 1, 2, 3, 9. The Operator's request is met here.
- **beta.4:** PRs 4, 5, 6. BMAD is installed by default on every volume, and is no longer a boot,
  a harness-enablement or a kind dependency.
- **beta.5:** PRs 7, 8. BMAD is no longer on the dispatch path.
- **The next release after both 6 and 7 have shipped:** PR 10.

Jumping straight from beta.2 to the last of these is safe for data. Its one cost is a Run parked on
an unexecuted `bmad.install` row, which then needs cancelling.

## 6. Draft of AD-16 after this plan

The final form, for the record. PR 1 applies the rule's "Pre-flight requires…" sentence; later PRs
reach the rest.

> ### AD-16 — Skills live in the image; a method is what a template calls
>
> - **Prevents:** per-run installs; skill folders in target repositories; a skill-name collision
>   resolved by copy order; a method's conventions becoming the orchestrator's rules.
> - **Rule:** The image carries a set of skills: operator-authored ones from `ia-agents-skills/` and
>   the BMAD stubs, installed by default in every harness at the `BMAD_VERSION` pin, and laid over the
>   `agent-home` volume at every start. A failed install fails an image build; at a start it is logged,
>   reported by `/version` and `doctor`, and stops nothing. The build fails on a name collision and
>   writes `skills-manifest.json`, the union, per harness home; the `SkillCatalog` port exposes it, and
>   pre-flight and dispatch check a named skill against it. That is the only skill rule the orchestrator
>   enforces. No code reads a method's manifest in a repository, compares a repository with the pin, or
>   decides anything on a method's paths or skills. A template that needs something in the repository
>   states it, in its own rows. A method installed into a repository is a template's doing (`repo-init`,
>   one shipped example) *(Operator decisions 2026-10-30: the version gate, the clone check's method line
>   and the `bmad.install` kind are removed; BMAD stays installed in every harness by default)*.

## 7. Open questions for the Operator

Each has a recommendation; PR 1 can start on Q1 alone, and PR 4 needs Q4.

| # | question | recommendation |
| --- | --- | --- |
| Q1 | Remove the gate for every plan, including BMAD-skill plans, accepting the loss in section 3? PR #9 stands only if the answer is no. | **Yes, remove for all, and close PR #9 unmerged after PR 1.** This is what was asked; the check was also weaker than documented. |
| Q2 | Is a guard row enough, or should templates get a declarative `requires:` preflight list, so the refusal comes before the Run exists? | **Guard rows now.** The gap is seconds and no spend, and it adds no DSL. Add `requires:` later if a real need shows up. |
| Q3 | In `staged-epic` and `staged-hub-epic`, a repository with no `_bmad/` can build its stories but not run the epic tail. Stop at the tail, or skip the tail? | **Stop at the tail.** Stories and their commits are kept and a skipped retrospective would be silent. An Operator can use a template without those rows. |
| Q4 | `BMAD_VERSION`: where does the pin live, and how does the installed version move? | **`.env`, as a fourth pin beside the three CLIs, on PR #8's mechanism: the image's bundle when it is at the pin, else one bounded registry attempt, moved by `install.sh upgrade` and `install.sh harness bmad --version X`. The shipped value moves to 6.12.4. `/version` keeps `bmad_version` and adds `bmad_installed`.** Production already sets this variable and the stubs simply do not follow it; this makes it true. *Cheaper:* image only, with a differing pin merely logged: no registry at boot, but an `.env` edit then does nothing until a new image. *Rejected:* a literal with no override (the previous recommendation), which ignores production's 6.12.4, and a generic `packaged_tools` field, which renames a report for no behaviour. |
| Q5 | *Initialise repository* can no longer react to a version. Keep it always available, or remove it, since `repo-init` is on the menu? | **Keep it, offered whenever no init Run is in progress, including after a finished one.** The endpoint and `is_init` are already generic, it is the one action that needs no form, and with the method cell gone it is how a repository's `_bmad/` reaches a newer pin. Production's repositories at 6.11.0 are that case today. |
| Q6 | Should the default readiness Run prove the BMAD stubs? A neutral default proves the harness, not the stubs. | **Neutral by default, even with BMAD installed by default.** Default is not dependency: with `epic` as the default, a stub fault could withdraw or refuse a harness, which is the app rule this plan removes. PR 4 reports the stubs' state instead, and readiness is about the harness (`harness_readiness_evaluate.py:27-31`). What is lost is proof that a real session discovers a stub; `READINESS_TEMPLATE=epic` stays available for an instance that wants it. |
| Q7 | Scrub the stored `bmad_version` key and stale lines with a migration? | **No.** A tolerant reader and the daily overwrite are enough; a migration adds rollback risk for tidiness. Reconsider at PR 10 only if the key's presence confuses someone. |
| Q8 | Do PR 7 and PR 8 at all? Without them the rendering and the Question format still assume BMAD, though only softly, and a non-BMAD template still works if it writes those conventions. | **Yes, but they can wait for a non-BMAD template to exist.** PR 7 is the riskiest here. If the near goal is only "no BMAD rule blocks me", beta.3 and beta.4 achieve it. PR 8's empty-question park is worth fixing on its own earlier, since it hits the first non-BMAD template that blocks. |
| Q9 | `AGENTS.md:7` and `backend-api/AGENTS.md:30` are anchors. Approve an edit? | **Yes.** Proposed line 7: *"An orchestrator that runs agent workflows against other repositories: a Run plans every step up front, …"*. Everything else in that sentence stays. |
| Q10 | Rename `_bmad-output/`, or stop using BMAD to develop this repository? | **Leave both.** It is this repository's own tooling, the spine's path is referenced from many places, and it is not product behaviour. |
| Q11 | Should an instance be able to opt out of the default install, with a setting such as `BMAD_INSTALL=false` or a blank `INIT_TEMPLATE`? New; nothing in this plan assumes one. | **No, not now.** Once PRs 1 to 6 land nothing depends on BMAD, so an opt-out would protect no rule, while adding a setting and a branch to the install. The one cost of the default is 49 more skills visible to each harness (`README.md:412`), unmeasured. Reconsider if that proves to cost something, or if an instance has a reason to keep the stubs out. |
| Q12 | Does "installed by default" extend to `_bmad/` in target repositories? New. | **No.** The default covers the harness; a repository receives `_bmad/` only through `repo-init`, as a PR. A worktree overlay at dispatch would make the skills work everywhere, but it writes unreviewed files into a repository and needs exactly the coded method knowledge this plan removes. The consequence is finding 6: a BMAD skill on a repository with no `_bmad/` stops at its guard row. |

## 8. What this plan did not verify

- No gate was run for the plan itself; it is a document. No proposed change was prototyped, PR 4's
  install, sync and state file included.
- Behaviour was read from code and docstrings. In particular I did not run: a skill-dispatching Run
  on a repository with no `_bmad/`; `render_skill.py` across two BMAD versions, including 6.11.0 in a
  repository against 6.12.4 stubs; a rollback to beta.2; a start with the registry unreachable.
- The production instance was not read, by instruction. Its 6.12.4 pin and the 6.11.0 on the
  repositories' default branches are as stated by the Operator. Not known: which version the stubs on
  production's `agent-home` volume hold. From the code a `.env` value cannot reach them, so they would
  be whatever the image's literal was, but that was not checked and an image could be built otherwise.
  Also not known: whether its `.env` sets `READINESS_TEMPLATE=epic`.
- Assumed, to confirm when PR 4 is cut: that one `bmad-method` install with all three `--tools`
  yields the same stubs as today's three per-tool installs, including a working `.agents/skills` for
  both codex and opencode. And when PR 6 is cut: that a `shell` row's `HOME` is the agent home
  (`process/runner.py:197` takes it from the backend's own environment).
- Whether 6.12.4 works with the shipped templates is unmeasured. This repository's own `_bmad/` is at
  6.11.0 and `test_harness_scripts.py:233-238` pins the contract to the script.
- Stored operator-edited templates on real instances were not inspected, so how many use `bmad.install`
  is unknown.
- The main checkout holds uncommitted work in `.env.example`, `settings.py`, `test_harness_scripts.py`
  and `test_install_admin.py`, which PR 4 also touches. It was not read; line numbers there may move.
