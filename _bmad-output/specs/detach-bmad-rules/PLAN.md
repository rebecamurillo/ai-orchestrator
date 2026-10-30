---
title: 'Detach coded rules from the BMAD method'
type: 'plan'
created: '2026-10-30'
status: 'proposed — not implemented; decisions in section 7 are open'
baseline: 'origin/main a2cccc2; every file:line below was read at that commit'
---

# Detach coded rules from the BMAD method

## 1. The goal and the line this plan draws

The Operator, 2026-10-30: *"detach CODED rules linked to BMAD method. The BMAD method is
installed in the container but should NOT define the code or business rules of the app
orchestrator."* The version check goes first, because workflows may use no BMAD skill at all.

The test applied to every item below:

> Would this code still be correct if no template on the instance called a BMAD skill and no
> repository held a `_bmad/` folder?

A template that names `skill: bmad-build-auto` is template content. Code that reads
`_bmad/_config/manifest.yaml`, or knows what a `bmad-*` skill prints, is a coded rule.

Target state, in one paragraph: the orchestrator knows repositories, worktrees, harnesses,
skills *by name in a catalog*, templates, and the spec-folder and story-file conventions that
templates declare. BMAD is a set of skill stubs in the image, a helper script or two, and one
family of shipped templates. An instance with no BMAD template behaves exactly as well as one
with them, and nothing about a repository is "outdated".

### Findings that change the shape of the plan

Five facts surfaced that the request did not list. Each is cited again in the inventory.

1. **The gate does not measure what AD-16 says it protects.** It compares the repository's
   manifest with the `BMAD_VERSION` environment variable, not with the stubs the harness
   reads. The stubs are installed at image build from the literal default in
   `scripts/harness/_common.sh:10` (the Dockerfile passes no such `ARG`, and
   `test_dockerfiles.py:232` forbids pinning it there), and they live in the `agent-home` volume, which
   Docker seeds only while empty. The boot sync copies operator skills only
   (`_common.sh:136`). So editing `.env` moves the gate and not the stubs, and an image bump
   on an existing volume moves the gate and leaves the old stubs in place. PR #9's own example
   (`outdated: 6.11.0`, while the shipped pin is also `6.11.0`) is consistent with this:
   the repository matched the shipped pin and the instance's effective variable did not. I
   did not read the production instance, so that last step is inference.
2. **BMAD is a boot dependency.** `backend-api/docker-entrypoint.sh:37` runs
   `scripts/readiness_fixture.sh` under `set -euo pipefail`, and that script runs
   `npx --yes bmad-method@… install` (`:43`). If that command fails, the container does not
   start, on an instance that may use no BMAD template.
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
| A-6 | `src/application/steps/bmad_install.py` (whole), including `:49-61` `INSTALL_COMMAND` and `:65` the three ignore lines `.claude/skills/bmad-*`, `.agents/skills/bmad-*`, `.opencode/commands/bmad-*`; `src/application/steps/__init__.py:100` kind table; `src/infrastructure/dbos/startup.py:38` import; `backend-api/AGENTS.md:30` kinds list; spine table `:384` | A step kind named after one method. Runs the pinned installer, then edits `.gitignore`. | Replaced by ordinary `shell` rows in the template (PR 5), then retired after a deprecation release (PR 10). | 5, 10 |
| A-7 | `src/application/steps/context.py:137-138` `RunEnvironment.bmad_version`; `src/infrastructure/db/environment.py:53,76`; passed at `src/api/providers.py:391`, `src/infrastructure/jobs.py:84`, `src/infrastructure/dbos/startup.py:166` | Carries the pin to exactly one reader, `bmad_install.py:85`. | Delete when the kind goes. | 10 |
| A-8 | `src/application/templates/rows.py:153-154`, `templates/plan.py:96,123`, `use_cases/plan_run.py:80,84`, `use_cases/preflight.py:59,213` | The planner's context carries `bmad_version`. Nothing reads it: `git grep` finds only the assignments. Dead since the executors took it from `RunEnvironment`. | Delete. | 3 |
| A-9 | `src/infrastructure/settings.py:225`; `.env.example:106` and `deploy/.env.example:121`, comment *"must equal `_bmad/_config/manifest.yaml` in every target repo (AD-16)"*; `src/api/providers.py:168`; `api/routers/clone_check.py:85`, `routers/projects.py:117`; `application/jobs/clone_check.py:24,28`; `infrastructure/jobs.py:64`; `infrastructure/db/seed.py:105`; `use_cases/harness_readiness_seed.py:75,85` | An instance setting whose stated meaning is a rule about other repositories. | The comment goes in PR 1, the call-site arguments in PR 3, the setting in PR 8. | 1, 3, 8 |
| A-10 | `src/api/schemas/clone_check.py:57,68` `CloneCheckResultOut.bmad_version`; `src/api/schemas/projects.py:138,181` `CloneCheckOut.bmad_version`; `contracts/openapi.json:707-736,755-795`; `web-client/src/api/schema.d.ts:993,1014` (generated) | A required, nullable API field. The `CloneCheckOut` docstring (`projects.py:131`) pins "exactly four keys". | Drop from both schemas; regenerate with `make openapi`. | 3 |
| A-11 | `web-client/src/pages/projects/index.astro:70-72,99,107`; `src/components/RepositoriesTable.astro:56-61,70,78,99,114,124`; `src/components/repository-row.ts:8` | A `method` column. The *Initialise repository* button appears only when the cell reads `missing` or `outdated`, and the done state reads `initialised · v{version}`. | Remove the column and `methodNeedsInit`; see Q5 for the button. | 3 |
| A-12 | `web-client/src/components/projects/CloneCheckReadout.astro:8,25,40-43,82-84` | A fixed `method version` line and *"run Initialise repository after save"* for a repository that needs nothing. | Remove. | 3 |
| A-13 | `scripts/harness/_common.sh:199-202` `doctor_skill_present`; called at `claude.sh:103`, `codex.sh:91`, `opencode.sh:121` | `doctor` exits non-zero when `bmad-build-auto/SKILL.md` is absent (`make platform-doctor`, `Makefile:220`). | Check that the catalog exists and parses, naming no skill. | 8 |
| A-14 | `scripts/readiness_fixture.sh:4-10,17,43-51`; `backend-api/docker-entrypoint.sh:37`; `fixtures/readiness-repo/README.md:8`; spine `:161,:396` | At every boot, runs `npx bmad-method@…` and appends the ignore lines into the fixture under `set -e`. A failure stops the container. | The fixture stops installing at boot (PR 4). | 4 |
| A-15 | `backend-api/tests/e2e/helpers/gates_fixture.py:21,53`; `helpers/hub_fixture.py:78`; `web-client/tests/e2e/uj3-fixture.ts:8-9,59-61`; `fixtures/gates-repo/README.md:34`; `fixtures/hub-repo/README.md:37`; `os.environ["BMAD_VERSION"]` readers in nine e2e modules (`test_answer_signal.py:85`, `test_budget_raise.py:75`, `test_checkpoint_signals.py:66`, `test_hub_run.py:116`, `test_retry_prompt_detail.py:98`, `test_skip_step.py:71`, `test_skip_story.py:72`, `test_spec_edit.py:55`, `test_uj3.py:129`) | E2E fixtures write a fake manifest for the sole purpose of passing the gate. | Harmless after PR 1, deleted in PR 3 with the rest of the plumbing. | 3 |

### (b) Generic mechanisms to keep, renamed or made neutral

| id | where | how it behaves today | what happens | PR |
| --- | --- | --- | --- | --- |
| B-1 | `src/application/preflight/lists.py:200-262` `installed_skill_lines`; `preflight/model.py:36` | Every `skill:` a plan names must be in the catalog: `fail · not installed: {name}`. Reads no method. | **Keep unchanged.** This is the generic check that survives. | — |
| B-2 | `src/application/steps/agent_skill.py:33-50` | The same check at dispatch: parks `misconfigured`. | Keep unchanged. | — |
| B-3 | `src/infrastructure/skill_catalog.py:10-13`; `scripts/harness/_common.sh:108-120` `write_skills_manifest`, `:136-162` `sync_operator_skills`, `:169-197` `install_operator_skills`; `src/infrastructure/skills_install.py` | Catalog of skill names; boot sync; build-time collision refusal. Only the comments say "BMAD". | Keep; neutral comments. | 9 |
| B-4 | `src/domain/ports/harness.py:240-246` `skills_dir`, set at each adapter (`claude/adapter.py:107`, `codex/adapter.py:147`, `opencode/adapter.py:186`) | Where a harness reads global skills. | Keep; neutral comment. | 9 |
| B-5 | `src/application/steps/agent_render.py` (whole): `:59` `RENDER_SCRIPT`, `:63` `ACCEPTED` (unused constant), `:66-67` `FOLLOW`, `HALT`, `:76` `WORKFLOW_ENTRY`, `:92-107` `render_argv`, `:121-130`, `:133-170`; `agent_workdir.py:25,31-33`; `agent.py:189,287`; `agent_prompt.py:75` `{path}` token | If the worktree has the BMAD renderer and the skill has `workflow.md`, the orchestrator runs `uv run … render_skill.py`, parses stdout, and fills the template's `rendered` clause. Otherwise it silently skips. A renderer that fails parks. | Keep the mechanism (it ended a measured failure, `agent_render.py:9-17`). Make it a template-declared pre-dispatch command; BMAD knowledge moves to a script the template names. | 6 |
| B-6 | `src/api/routers/version.py:66,80`; `contracts/openapi.json:4783-4805`; `web-client/src/api/schema.d.ts:2492`; `deploy/install.sh:514,795-798`; `src/infrastructure/mcp/tools.py:36`; `test_install_admin.py:113`; `test_version_router.py:79` | `/api/v1/version` publishes `bmad_version`, and `doctor` prints it. | Reporting what the image carries is legitimate; a field named after one method is not. See Q4. | 8 |
| B-7 | `settings.py:179` `init_template`; `src/api/routers/repository_init.py:78`; `use_cases/repositories.py:3-14`; `use_cases/project_runs.py:24,75,107`; `api/schemas/projects.py:200-202,222`; `web-client/src/actions/repositories.ts:43-67`; `web-client/src/lib/projects/runs.ts:36-37` | Already generic: a configured Template name. `min_length=1` means it cannot be switched off. `repositories.py:4-5` wrongly says the shipped plan has no `agent` step. | Keep; allow blank; see Q5. | 3 |
| B-8 | `settings.py:182` `readiness_template` default `epic`; `harness_readiness.py:58-61`; `harness_readiness_evaluate.py:202-214`; `fixtures/readiness-repo/` | Evaluation finds rows by kind and is neutral. The fixture story and spec are neutral. Only the default template and the boot install are not. | Keep the mechanism; ship a method-neutral default. | 4 |
| B-9 | `src/application/steps/agent_tail.py:69` `STORY_FILE_GLOB`, `:296-315`; `use_cases/step_detail.py:87`; `use_cases/record_trajectory.py:231`; `use_cases/run_files.py:14`; `infrastructure/harness/fake/adapter.py:82` | `{spec_folder}/stories/{id}-*.md` is the fallback when a row declares no `expect.files`. | Keep. This is the orchestrator's own convention. The staged family already overrides it with `stories/.auto/` markers (`staged-story.yaml:64`). | — |
| B-10 | `src/application/preflight/lists.py:30-32`; `preflight/model.py:31-34`; `application/templates/lists.py:55-56`; `application/rules/protected_paths.py:48-50`; `domain/ports/protected_paths.py:3` | `epics.yaml`, `stories.yaml`, `SPEC.md` as list files and AD-17 anchors. | Keep. They are the orchestrator's format, not BMAD's: *"BMAD's epics and stories are not the hub format"* (`deploy/kit/skills/initiative-spec/SKILL.md:127`). | — |
| B-11 | `application/templates/lists.py:78-79,170-193,212`; `rows.py:334-344` | FR-10: a story whose file states `status: done` is skipped. | Keep. Hard-codes one token, `done`, which is the orchestrator's own. | — |
| B-12 | `application/rules/routing.py:61` `DEFAULT`, `checkpoint=("ready-for-dev",)` | A row declaring no routing lists routes on BMAD's token. | Keep as the compatibility default for stored templates; shipped rows already declare the list. Neutral comment. | 7 |
| B-13 | `application/templates/model.py:44-45` `STATUS_TOKENS`; `templates/agent.py:213`; `templates/expressions.py:256` | `status_in` and `escalate_when` validate against BMAD's six tokens, while the newer `expect.*` lists are free-form (`agent.py:50`, `model.py:155`). | Make the legacy keys free-form too. Accepting a superset breaks no stored template. | 7 |
| B-14 | `application/story_file.py:37-43` `## Auto Run Result`, `Blocking condition:`; `steps/agent_answer.py:37,68,293`; `rules/routing.py:153-158`; `use_cases/step_detail.py:9,71,101` (the heading written a second time as a literal); `api/schemas/step_detail.py:40` | The operator's Question is read only from this BMAD HALT section. A non-BMAD template that writes `status: blocked` parks with an **empty** reason, because `section()` returned `""`. | Declarable on `expect`, with these as defaults; a sentence naming the file when nothing is found. One definition of the heading. | 7 |
| B-15 | `application/story_file.py:45-48`, `:136-141` `after_verify`; `steps/agent_prepare.py:121-134`; `use_cases/walk.py:174` | A failed `verify` rewrites the file to `status: in-progress`, because *"`bmad-build-auto` routes `in-progress` straight to implementation"* (`:46`). | Declarable on `expect`, `in-progress` the default. The `## Verify Failure` section is the orchestrator's own and stays. | 7 |
| B-16 | `steps/agent_prepare.py:57,137-155`, `agent_workdir.py:13` | Writes `{spec_folder}/project-context.md`. BMAD retired that name (`bmad-project-context/SKILL.md:90`), so it is the orchestrator's own document now. | Keep. No rename: it would churn stored prompts for nothing. | — |
| B-17 | `AGENTS.md:7` (Operator-only anchor); `README.md:3`; `backend-api/pyproject.toml:4`; `src/infrastructure/mcp/facade.py:44`; `web-client/src/components/NewWorkflowFields.tsx:64`; `deploy/kit/.claude-plugin/plugin.json:3`; `.claude-plugin/marketplace.json:10`; `deploy/kit/skills/orchestrator/SKILL.md:3,8` | Product identity: *"runs BMAD dev-loop workflows"*. The UI tooltip says *"which BMAD workflow"*. | Neutral copy. | 9 |
| B-18 | Comments: `rules/routing.py:24,59`, `story_file.py:37,46`, `claude/adapter.py:11`, `use_cases/walk.py:290`, `templates/branches.py:3,5,24,72`, `templates/plan.py:12,22`, `infrastructure/kit.py:7`, `api/routers/clone_check.py:78`, `routers/projects.py:187`, `scripts/harness/codex.sh:53`, `_common.sh:4,53-54` | Describe a rule, or use a BMAD name as the example. No behaviour. Two render into OpenAPI descriptions (`openapi.json:5525,6222`). | Reword when the code beside them changes, per the repo's comment rule. Not a sweep of its own. | each |
| B-19 | Kit text stating the rule: `deploy/kit/skills/orchestrator/SKILL.md:53,67-68,90-91`; `references/api.md:19,64`; `references/first-run.md:21-24,178`; `references/workflows.md:99`; `references/spec-folder.md:6-8`; `orchestrator-admin/SKILL.md:87,101,217`; `initiative-spec/SKILL.md:102-105`; `initiative-spec/references/chain.md:25,32-34` | Agents are told a repository with a different manifest *"is not ready to dispatch"* and that preflight fails. Becomes false at PR 1. | The false statements change with PR 1, the rest with the PR that changes the behaviour they describe. | 1, 3, 5, 8 |
| B-20 | Spine: AD-16 `:214-218` title and rule; `:161`; `:265` branch name; `:295` version table; `:354` `clone_check{…bmad_version}`; `:384` kinds; `:396,:401`; `:441` env table; `:452-453` FR-2, FR-30; `:455` FR-8; `:498-499` open risks. The PRD that defined FR-30 was removed on 2026-09-23 (`_bmad-output/README.md`); its surviving statements are the spine's. | The binding record of these rules. AGENTS.md: *"when code and spine disagree, stop"*. | Each PR amends the spine in the same commit. Draft for AD-16 in section 6. | each |
| B-21 | Operator docs: `README.md:217-220,230-231`; `templates/README.md:24,27`; `deploy/README.md:66,160` | Walkthrough says the clone check *"reports the target's BMAD state"* and to initialise *"if the target has never run the BMAD method"*. | Reword with the behaviour change. | 3, 5 |

### (c) Packaging and content that may stay

| id | where | what it is | note |
| --- | --- | --- | --- |
| C-1 | `scripts/harness/_common.sh:53-66` `bmad_install_global_skills`; called at `claude.sh:28`, `codex.sh:18`, `opencode.sh:24`; `backend-api/Dockerfile:143` | Installs the stubs into the image. Exactly what the Operator described. | Stays. |
| C-2 | `scripts/harness/_common.sh:10`; `README.md:398-402` | The pin that really decides the stubs. Cross-checked by `test_harness_scripts.py:219-222`. | Stays as the one pin; loses its env override in PR 8. |
| C-3 | `agent-home` volume, `docker-compose.yml:142-144`, `deploy/docker-compose.yml:142-144` | Stubs in an existing volume never update; only operator skills sync at boot. | Content can stay, but this is a live defect: PR 8 syncs packaged skills at boot the way operator skills already are. |
| C-4 | `templates/repo-init.yaml` (`chore/bmad-init`, `bmad-project-context`) | A shipped template. Its only coded tie is `uses: bmad.install`. | Stays; rewritten in PR 5. |
| C-5 | `templates/story.yaml:22`, `initiative-hub-story.yaml:43`, `epic.yaml:75,103`, `initiative-hub-epic.yaml:118,149`, `staged-epic.yaml:100,129`, `staged-hub-epic.yaml:130,161` | Templates that choose to call a BMAD skill. The code does not special-case them. | Stays. The epic-level ones gain a guard row in PR 2; BMAD rows gain a `prerender` declaration in PR 6. |
| C-6 | `rendered` clauses naming `render_skill.py`, `templates/*.yaml` and the sibling headers (`staged-story.yaml:8`, `staged-hub-story.yaml:8`) | Template prose. The `staged-*` skills have no `workflow.md`, so that clause never fires on their rows. | Stays. PR 6 may drop the clause from the rows that can never use it. |
| C-7 | `templates/drafts/story-staged.yaml:7,75` | Never seeded. | Stays. |
| C-8 | `deploy/kit/skills/initiative-spec/` planning chain | A skill that uses BMAD to plan. Content. Only the lines in B-19 state an orchestrator rule. | Stays. |
| C-9 | `ia-agents-skills/README.md:9,19`; `spec-gate`, `staged-*` | Operator skills. `git grep` finds no BMAD reference in the skills themselves. | Stays. |
| C-10 | This repository's own tooling: `_bmad/`, `_bmad-output/`, 248 tracked files under `.agents/skills/bmad-*` (tracked despite `.gitignore:8`), `.gitignore:1-8`, `.dockerignore:22-23`, `README.md:396-410`, `test_gitignore.py:57-59`, `web-client/tests/e2e/*` screenshot paths | How *this* repository is developed, not how the product behaves. `.dockerignore` keeps it out of the image. | Stays. Renaming `_bmad-output/` would be churn; see Q10. |
| C-11 | `fixtures/gates-repo/.fake-harness/1/attempt-1.yaml:4`; test sentences such as `test_claude_adapter.py:40`, `test_install_operator_skills.py:66-115` | A name used as example data; the behaviour under test is generic. | Stays. |
| C-12 | Comments: `docker-compose.yml:74,142`, `deploy/docker-compose.yml:79,142`, `deploy/llm-platform/README.md:497`, `ci.yml:193`, `test_dockerfiles.py:173,240` | True statements about what the volume or image holds. | Stays; "skill stubs" reads fine when next touched. |

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
| Readiness boot | `unit/test_readiness_fixture_script.py`; `unit/application/test_harness_readiness_seed.py`; `unit/application/test_readiness_declares_no_quality_gate.py:70,98,147` | 4 |
| Kind and executor | `unit/test_bmad_install_executor.py` (11 tests); `unit/application/templates/test_step_kind_registry.py:67`; `unit/application/templates/test_shipped_templates.py:223,253-262`; `unit/application/templates/test_plan_shipped.py:36`; `unit/test_run_values.py:171`; `unit/test_process_step_log_names.py`; `unit/test_run_environment_*.py`; `e2e/test_repo_init.py`; `e2e/test_repo_init_commit_scope.py`; test-owned copies `unit/application/templates/fixtures/exemplars/repo-init.yaml:17`, `e2e/templates/repo-init.yaml:22` | 5, 10 |
| Render | `unit/application/steps/test_agent_render.py`; `unit/application/steps/test_agent_prepare.py` | 6 |
| Pin and contract | `unit/test_settings_defaults.py:88`; `unit/test_version_router.py:79`; `unit/test_install_admin.py:113`; `unit/test_harness_scripts.py:219-222`; `unit/test_dockerfiles.py:232`; `unit/test_env_contract.py`, `test_deploy_env_contract.py` via `scripts/check_env_contract.py` | 8 |
| A template fixture naming a skill as data | `unit/application/templates/test_retro_step.py` calls `bmad-retrospective` *"an architectural anchor"* against frozen exemplars, so it pins no shipped file. | leave |

### Counts

(a) 15 · (b) 21 · (c) 12 — 48 items, each of which may span several files. Of the (b) items,
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
| Repository with no `_bmad/`, plan names a BMAD skill | refused before the Run | The skill passes the catalog check. `agent_render.py:126-127` skips, and the harness gets a stub whose `SKILL.md` runs a script that is not there. It should HALT; the 2026-09-21 finding (`agent_render.py:9-17`) measured agents improvising instead. The Run then parks on no story file, or on what the retry bound allows, having spent budget. | **A real loss.** Spend and time, not integrity: AD-17 anchors, verify rows and the commit guard all still apply. |
| Repository with `_bmad/` at another version, BMAD skill | refused | `render_skill.py` from the repository reads the skill from the image. A hard failure parks `misconfigured` (`agent_render.py:164-169`). A soft mismatch renders something and proceeds. | **A real but narrow loss**, and only partly covered today, because of finding 1: the gate compared the variable, not the stubs. How often versions break the renderer is unmeasured. |

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
   template owns the rule. This plan recommends it does not. PR 6 strengthens this: a row that
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

PR #8 (harness upgrades, open) edits `.env.example`, `deploy/.env.example`, `_common.sh`, the
Dockerfile and the entrypoint, and adds the comment *"BMAD_VERSION is outside this rule: it must
equal every target repository's manifest (AD-16)"*. Whichever merges second rewords that
comment. PRs 4 and 8 here should be cut after PR #8 lands.

## 4. The PRs, in order

Each PR ships alone, leaves `make lint` and `make test` green, and amends the spine in the same
commit. Branch prefixes follow the repository's conventional commits. Suggested release grouping
is in section 5.

### PR 1 — `fix(preflight): no plan is checked against a method version`

- **Scope:** A-1, A-2. Comment half of A-9. The kit sentences that become false (B-19). AD-16 and
  the FR-8 row reworded.
- **Files:** `application/preflight/checks.py`, `preflight/model.py`, `use_cases/preflight.py:110,170`;
  `use_cases/run_finished.py:31` (the constant moves to `steps/bmad_install.py::KIND`); `.env.example:106`,
  `deploy/.env.example:121`; `deploy/kit/skills/orchestrator/SKILL.md:67-68`,
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
  none: it installs the method itself.
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
  e2e fixtures; `README.md:217-220`; spine `:354,:452-453`.
- **Tests:** the clone-check, `run_finished` and web-client rows of the test table. New:
  `clone_check_from_entity` reads a row with the key, with `null`, and without it, and with a stored
  `method version` line.
- **API:** `clone_check.bmad_version` removed from `CloneCheckOut` and `CloneCheckResultOut`.
  Breaking for an external client, which is acceptable in a beta and named in the release notes.
- **DB:** no migration. Section 5 has the read and write rule.
- **Risk:** low in behaviour. Wide in files; coverage rules (100 % on `application`, 90 % on
  changed lines) make it a thorough diff rather than a dangerous one. The `Initialise repository`
  button stops depending on a version, which changes what the Projects screen shows (Q5).
- **Rollback:** revert the image. Stored rows stay readable by the old image because the key is
  still written.

### PR 4 — `fix(readiness): no method install at boot, and a neutral default`

- **Scope:** A-14, B-8.
- **Two parts, because existing instances pin the old default in their `.env`:**
  (i) `readiness_fixture.sh` stops running `npx`. The image bakes the `_bmad/` overlay at build,
  and the script copies it into the fixture if present, so `READINESS_TEMPLATE=epic` keeps working
  with no network at boot. (ii) A new own-text shipped template, `readiness-check`, needing no
  skill: it plans the fixture's one story, asks the agent to create `HELLO.md` and write
  `specs/readiness/stories/1-hello.md` with `status: done`, then runs the verify shell row. The
  default in `settings.py:182` and both `.env.example` files moves to it.
- **Files:** `scripts/readiness_fixture.sh`, `_common.sh`, `backend-api/Dockerfile`,
  `fixtures/readiness-repo/README.md`, `templates/readiness-check.yaml`, `templates/README.md`,
  `settings.py`, `.env.example`, `deploy/.env.example`, spine `:161,:396`. Coordinate with PR #8,
  which edits the entrypoint and the Dockerfile.
- **Tests:** `test_readiness_fixture_script.py` asserts no `npx` runs. A fixture copy of the new
  template evaluates all six lines `ok` through the existing `harness_readiness_evaluate` tests.
  `e2e/test_harnesses.py` must stay green on the fake harness.
- **API / DB:** none. `enabled` flags stay as they are; nothing forces a re-proof.
- **Risk:** a readiness Run proves less about BMAD stubs (Q6). An explicit `READINESS_TEMPLATE=epic`
  survives upgrade, because `install.sh` writes `.env` once and never overwrites it (`deploy/install.sh:22`).
- **Rollback:** revert; or set `READINESS_TEMPLATE=epic`.

### PR 5 — `refactor(templates): repo-init installs through ordinary rows`

- **Scope:** A-6 (first half), C-4, B-21.
- **What changes:** `templates/repo-init.yaml` replaces `uses: bmad.install` with a `run:` row
  calling a script the image carries, for example `bmad-repo-install`, placed on `PATH` and reading
  the one pin. The script holds the installer flags and the three ignore lines. `shell` rows
  already get `PATH`, `HOME` and `env={}`, the same as the executor (`shell.py:18-23`). The Python
  kind stays registered but unused.
- **Why a script rather than a version in the YAML:** hard rule 6 forbids a test that pins template
  content, so a literal `bmad-method@6.11.0` in the template could not be cross-checked against
  `_common.sh`, and would drift. See Q4.
- **Files:** `templates/repo-init.yaml`, `scripts/methods/bmad-repo-install.sh`, `backend-api/Dockerfile`,
  `scripts/readiness_fixture.sh` (shares the ignore lines), `deploy/kit/skills/orchestrator/references/workflows.md:99`,
  spine `:218,:384` (kind marked deprecated), `README.md:219`.
- **Tests:** a shell-level test of the script with a stub `npx`, in the style of
  `test_install_operator_skills.py`; idempotent ignore lines (the behaviour `test_bmad_install_executor.py`
  pins today, ported so coverage does not fall). `e2e/test_repo_init_commit_scope.py` keeps proving that
  no skill folder reaches the commit, via its own template copy.
- **API / DB:** a new `repo-init` version seeded. Stored versions keep working while the kind stays.
- **Risk:** a failed install now parks by the row's `on_fail` rather than as `misconfigured`, so the
  reason sentence changes. `POST /init` is unaffected.
- **Rollback:** revert. The new template version stays valid under old code.

### PR 6 — `refactor(agent): a template declares its pre-dispatch render`

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

### PR 7 — `feat(templates): the result vocabulary is declared, not assumed`

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
- **Risk:** low, defaulted. **Rollback:** same hazard as PR 6 if templates carry the new keys; ship
  the code and keep the keys out of shipped templates for one release if that matters.

### PR 8 — `refactor(deploy): the method pin is packaging, not configuration`

- **Scope:** the rest of A-9, A-13, B-6, C-2, C-3.
- **What changes:** `BMAD_VERSION` leaves `Settings`, `.env.example` and `deploy/.env.example` together
  (hard rule 8). `_common.sh:10` becomes a literal with no environment override, so a leftover value
  in an instance's `.env` cannot move anything. `/version` per Q4. `doctor_skill_present` checks the
  catalog. BMAD stubs are copied at build to a packaged-skills folder and synced at boot with
  `sync_operator_skills`, so a pin bump reaches existing volumes, ending the stale-stub defect.
- **Files:** `settings.py`, both `.env.example`, `scripts/harness/{_common,claude,codex,opencode}.sh`,
  `api/routers/version.py`, `infrastructure/mcp/tools.py`, `deploy/install.sh:514,795-798`, kit
  `SKILL.md:53`, `references/api.md:19`, `orchestrator-admin/SKILL.md:101,217`, spine `:295,:441`,
  `README.md:402`.
- **Tests:** contract row of the test table. `test_harness_scripts.py:219-222` loses its cross-check
  against the removed variable and pins the literal against the `/version` source instead. New: boot
  sync replaces a stale stub and leaves an unknown skill alone.
- **API:** `/version` shape per Q4. **DB:** none.
- **Risk:** boot sync must not delete operator-added stubs; `sync_operator_skills` already never
  removes. Cut after PR #8.
- **Rollback:** revert; a leftover `.env` line works again.

### PR 9 — `docs: the product no longer describes itself as a BMAD runner`

- **Scope:** B-3, B-4, B-17, remaining B-18.
- **Files:** `README.md:3`, `backend-api/pyproject.toml:4`, `mcp/facade.py:44`,
  `NewWorkflowFields.tsx:64`, `plugin.json:3`, `marketplace.json:10`, `orchestrator/SKILL.md:3,8`,
  comments. **`AGENTS.md:7` and `backend-api/AGENTS.md:30` are anchors only the Operator changes**
  (hard rule 1), so they are proposed text in the PR description, unless the Operator approves the
  edit (Q9).
- **Tests:** copy assertions only, if any. **API / DB:** the MCP instruction string; none. **Risk:** none.
- Can ship any time after PR 1.

### PR 10 — `refactor!: retire bmad.install and the compatibility paths`

- **Scope:** the rest of A-4, A-6, A-7, the PR 6 default. Ships at least one release after PRs 5
  and 6, so nothing parked or planned still needs them.
- **What changes:** delete the kind, the executor and `RunEnvironment.bmad_version`. Stop writing
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
| `BMAD_VERSION` left in an instance `.env` | Ignored: `extra="ignore"` (`settings.py:118`). Still reaches the process through `env_file`, which is why PR 8 removes the env override in `_common.sh`. | Read. |
| `.env` regenerated on upgrade | No: written once, never overwritten (`deploy/install.sh:22`). So `READINESS_TEMPLATE=epic` and `ROOT_TEMPLATES` persist; PR 4 keeps `epic` working for that reason. | Read. |
| Stored `clone_check` rows | Carry `bmad_version` and possibly a `method version` line. Read tolerantly: `.get`, stale line ignored. Next check overwrites (03:00 daily cron, any project save, start-up for the readiness Project). The web client looks lines up by name, so a stale line never renders. | Read; not run. |
| Rollback to beta.2 | The old reader needs the key: `data[BMAD_VERSION_KEY]` raises `KeyError` if absent. **So PR 3 keeps writing `"bmad_version": null`.** The old type allows `None` (`repository.py:111`). The old UI shows `—`, and its gate returns. | Read; not run. |
| Stored template versions | Immutable and kept. `seed_shipped` inserts only when a file's hash is new across every version (`templates.py:_seed_file`). | Read. |
| **Rollback seeding hazard** | Because of that hash rule, an old image does not re-seed its older file: the hash already exists, and the newest stored version stays the one from the newer release. Old code then plans it. Harmless for PRs 2, 4 and 5 (valid under old code); **a template with a new `with` or `expect` key (PRs 6, 7) does not validate on old code.** Those rollbacks need the pre-upgrade backup or a re-saved template. | Read; not run. |
| Runs in flight at upgrade | Rows are frozen at plan time (AD-7). A planned `bmad.install` row works until PR 10. A row with a `rendered` clause renders through PR 6's default. Walker step sequence is unchanged, so no `DBOS_APPLICATION_VERSION` bump in any PR. | Read `walker.py:245-252`; not run. |
| Repositories already initialised | Their committed `_bmad/` keeps working and is never read by the orchestrator's rules. No action. Their `.gitignore` lines stay. | Read. |
| Repositories not initialised | Run anything; BMAD-skill templates stop at their guard. | By design. |
| Existing `agent-home` volumes | Hold stubs from when they were created. Unchanged until PR 8, which starts syncing. | Read. |
| Older kit installed in a project | May tell an agent to compare `bmad_version` (`orchestrator/SKILL.md:67`). Until refreshed, an agent might refuse a repository the instance would accept. The kit's handshake already says to stop on a kit/instance mismatch. | Read. |
| `deploy/install.sh` reading a missing `bmad_version` | `json_string` yields blank; `doctor` prints an empty value. The bundle ships with the image, so PR 8 changes both together. | Read. |

### Suggested release grouping

- **beta.3:** PRs 1, 2, 3, 9. The Operator's request is met here.
- **beta.4:** PRs 4, 5, 8, after PR #8. BMAD is no longer a boot or a kind dependency.
- **beta.5:** PRs 6, 7. BMAD is no longer on the dispatch path.
- **The next release after both 5 and 6 have shipped:** PR 10.

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
>   any packaged set (today, the `bmad-method` stubs at one pin in `scripts/harness/_common.sh`). The
>   build fails on a name collision and writes `skills-manifest.json`, the union, per harness home;
>   the `SkillCatalog` port exposes it, and pre-flight and dispatch check a named skill against it.
>   That is the only skill rule the orchestrator enforces. No code reads a method's manifest, compares
>   a method's version, or names a method's paths or skills. A template that needs something in the
>   repository states it, in its own rows. A method installed into a repository is a template's doing
>   (`repo-init`, one shipped example) *(Operator decision 2026-10-30: the version gate, the clone
>   check's method line and the `bmad.install` kind are removed)*.

## 7. Open questions for the Operator

Each has a recommendation; PR 1 can start on Q1 alone.

| # | question | recommendation |
| --- | --- | --- |
| Q1 | Remove the gate for every plan, including BMAD-skill plans, accepting the loss in section 3? PR #9 stands only if the answer is no. | **Yes, remove for all, and close PR #9 unmerged after PR 1.** This is what was asked; the check was also weaker than documented. |
| Q2 | Is a guard row enough, or should templates get a declarative `requires:` preflight list, so the refusal comes before the Run exists? | **Guard rows now.** The gap is seconds and no spend, and it adds no DSL. Add `requires:` later if a real need shows up. |
| Q3 | In `staged-epic` and `staged-hub-epic`, a repository with no `_bmad/` can build its stories but not run the epic tail. Stop at the tail, or skip the tail? | **Stop at the tail.** Stories and their commits are kept and a skipped retrospective would be silent. An Operator can use a template without those rows. |
| Q4 | `BMAD_VERSION`: where does the pin live, and what does `/version` say? | **One literal in `_common.sh`, off the env contract. `/version` drops `bmad_version` and gains a generic `packaged_tools: {"bmad-method": "6.11.0"}` read from a file the image build writes, `null` on a source-tree run, the way `kit_version` already behaves.** Alternative that is cheaper: leave the setting as an informational pin beside the CLI pins, comment corrected. It would still invite editing a value that moves nothing. |
| Q5 | *Initialise repository* can no longer react to a version. Keep it always visible, or remove it, since `repo-init` is on the menu? | **Keep it, always available, and allow `INIT_TEMPLATE` to be blank to hide it.** The endpoint and `is_init` are already generic, and it is the one action that needs no form. |
| Q6 | Should a readiness Run still prove the BMAD stubs? A neutral default proves the harness, not the stubs. | **Neutral by default.** `READINESS_TEMPLATE=epic` stays available for an instance that wants the stricter proof. Readiness is about the harness (`harness_readiness_evaluate.py:27-31`), and a first-time install then needs no BMAD to enable one. |
| Q7 | Scrub the stored `bmad_version` key and stale lines with a migration? | **No.** A tolerant reader and the daily overwrite are enough; a migration adds rollback risk for tidiness. Reconsider at PR 10 only if the key's presence confuses someone. |
| Q8 | Do PR 6 and PR 7 at all? Without them the rendering and the Question format still assume BMAD, though only softly, and a non-BMAD template still works if it writes those conventions. | **Yes, but they can wait for a non-BMAD template to exist.** PR 6 is the riskiest here. If the near goal is only "no BMAD rule blocks me", beta.3 and beta.4 achieve it. PR 7's empty-question park is worth fixing on its own earlier, since it hits the first non-BMAD template that blocks. |
| Q9 | `AGENTS.md:7` and `backend-api/AGENTS.md:30` are anchors. Approve an edit? | **Yes.** Proposed line 7: *"An orchestrator that runs agent workflows against other repositories: a Run plans every step up front, …"*. Everything else in that sentence stays. |
| Q10 | Rename `_bmad-output/`, or stop using BMAD to develop this repository? | **Leave both.** It is this repository's own tooling, the spine's path is referenced from many places, and it is not product behaviour. |

## 8. What this plan did not verify

- No gate was run for the plan itself; it is a document. No proposed change was prototyped.
- Behaviour was read from code and docstrings. In particular I did not run: a skill-dispatching Run
  on a repository with no `_bmad/`; `render_skill.py` across two BMAD versions; a rollback to beta.2;
  the fixture boot with no network (an `npx` cache in the volume may let a boot pass offline).
- The production instance was not read, by instruction, so the effective `BMAD_VERSION` behind PR #9's
  report is inference.
- I did not review open PR #8 in full, only its overlap with these files. Line numbers will move once it
  merges.
- Stored operator-edited templates on real instances were not inspected, so how many use `bmad.install`
  is unknown.
