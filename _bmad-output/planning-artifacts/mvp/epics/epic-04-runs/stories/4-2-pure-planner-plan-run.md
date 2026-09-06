---
title: 'Pure planner plan_run'
type: 'feature'
created: '2026-09-06'
status: 'done'
review_loop_iteration: 0
followup_review_recommended: true
context:
  - '_bmad-output/planning-artifacts/mvp/epics/epic-04-runs/briefs/4-2-pure-planner.md'
  - 'backend-api/AGENTS.md'
warnings: ['oversized']
deferred:
  - summary: >-
      A Template input's declared `default:` is dropped: neither the root scope nor a callee
      scope applies it, so any input with a default other than `harness`/`model` resolves to
      the empty string.
    evidence: |-
      `plan.root_scope` builds the scope from `RunInputs` alone and `rows.expand_call` from
      the call's own bindings; `InputDecl.default` is read nowhere in the planner. It is
      invisible on the shipped files because `RunInputs` has `harness` and `model` fields of
      its own. The brief's substitution rule enumerates the sources as "RunInputs, the loop
      item, and the entity whitelist", which is what the code implements.
    location: >-
      backend-api/src/orchestrator/application/templates/plan.py:root_scope
    severity: medium
  - summary: >-
      A command only partly resolved from a missing value is planned rather than skipped.
    evidence: |-
      `run: "{{repository.quality_gate_command}} && make test"` on a Repository that states
      no quality gate resolves to `" && make test"`, which is truthy, so the row is planned
      and a shell is handed a broken command. The brief's rule is "a shell row whose
      resolved command is empty", which this is not; skipping a compound command because one
      substitution was empty would be a new rule.
    location: >-
      backend-api/src/orchestrator/application/templates/rows.py:row_status
    severity: medium
  - summary: >-
      A list file holding an empty YAML sequence plans zero rows for that loop with no line
      the Operator can read.
    evidence: |-
      `lists._entries` returns `()` for `[]`, `check_entries` accepts it, and `expand_loop`
      emits nothing. The brief names missing and unparseable list files as refusals but not
      an empty one.
    location: >-
      backend-api/src/orchestrator/application/templates/lists.py:read_list
    severity: low
  - summary: >-
      `plan_refs` is keyed by path alone, so one list path read at two commits keeps only
      the last — and staleness is judged on that map.
    evidence: |-
      `PlanReader.record` overwrites. No shipped Template produces the collision today: each
      frame reads its own path. It becomes reachable when a Template reads one list file
      from two frames at different refs.
    location: >-
      backend-api/src/orchestrator/application/templates/reader.py:record
    severity: low
  - summary: >-
      A Story frame already marked `already done` still reads its callee's own list file, so
      a list file missing under a finished Story refuses the whole plan.
    evidence: |-
      `expand` runs unchanged inside a skipped frame; `read_list` raises `LIST_FILE_NOT_FOUND`
      before anything consults `frame.skipped`. `story@1` declares no loop, so no shipped
      Template reaches it.
    location: >-
      backend-api/src/orchestrator/application/templates/rows.py:expand_loop
    severity: low
  - summary: >-
      A root Template the store does not hold is refused as `callee not resolved`, which
      names the wrong relationship to the Operator.
    evidence: |-
      `use_cases/plan_run._unresolved` uses one reason for the root and its callees. The
      message still names the template and version, so the refusal is accurate about which
      file is missing, only not about why it was being looked for.
    location: >-
      backend-api/src/orchestrator/application/use_cases/plan_run.py:_unresolved
    severity: low
  - summary: >-
      `list_files` passes the prefix to git as a pathspec, so glob magic in a resolved
      `spec_folder` would be interpreted rather than matched literally.
    evidence: |-
      `ls-tree -r -z --name-only <ref> -- <prefix>`: a `spec_folder` holding `*`, `?` or `[`
      would select a different subtree. Spec folders come from a validated Template `path`
      input, so nothing shipped reaches it; `:(literal,top)` pathspec magic is the fix.
    location: >-
      backend-api/src/orchestrator/infrastructure/git/subprocess_git.py:list_files
    severity: low
baseline_revision: 'b91d2770ede97d32a5dee798ef4b93e58cb97512'
---

<intent-contract>

## Intent

**Problem:** A Run must be planned completely, purely, from the remote branch at one commit before it
starts (AD-7), but nothing expands a pinned Template tree into rows: 4.3's pre-flight has no *What will
run*, 4.4 has nothing to persist, and 4.6's walker has no rows to execute.

**Approach:** One pure function `plan_run(tree, inputs, *, git, base_dir, bmad_version) -> Plan` that
walks the pinned tree, reads list files and story files through the `Git` port at a recorded ref, and
returns `PlannedRow`s — `plan.check` first, `checkpoint` rows where the Template declares an item pause,
and `skipped` rows with a fixed reason. A thin use case resolves the tree through
`TemplateVersionRepository` and calls it.

## Boundaries & Constraints

**Always:**
- Pure apart from `Git.ls_remote / read_file / list_files`: no clock, no randomness, no filesystem, no
  YAML *file* I/O. Two calls with the same tree, inputs and scripted `Git` return equal `Plan`s.
- `application/templates/validate.py::validate` is the single parser (AD-15). `plan_run` never reads
  Template YAML itself; the list files it reads are data, not Templates.
- `application/steps/__init__.py::KIND_META` is the only enumeration of kinds (AD-9). No `if kind == ...`
  outside the constants this story names.
- `gate` is what the Template declared, or `unvalidated` when it declared none — **never**
  `meta.gate_default` (NFR-2). The two rows the *planner* inserts (`plan.check`, `checkpoint`) are the
  exception: nobody left them ungated, so they carry their kind's `gate_default`, exactly as
  `application/graph.py::_item_checkpoint` already does.
- Each list file is read once per ref (FR-10); each `stories/` listing is read once per ref.
- `domain/` and `application/` keep 100 % branch coverage (`make test` re-reports with
  `--fail-under=100`), every `src` module is imported by a unit-test module
  (`scripts/check_test_pairs.py`), a module is <= 400 lines and a function <= 50 lines / <= 5 arguments,
  `mypy --strict` passes on domain and application. No `pragma: no cover`.
- TDD (AD-18): each test module is written and watched to fail before the module it covers exists.
- `tests/unit/fakes/git.py` is **extended, never replaced** (hard rule 6: one fake per port). The
  additions are new optional keywords and one new method; no existing keyword, default or behaviour
  changes, so every assertion already in `tests/unit/test_git_port.py` still holds.

**Block If:**
- Landing the story would require editing `SPEC.md`, `stories.yaml`, any `AGENTS.md`, or an existing test
  file's existing content.

**Never:**
- No persistence (4.4), no pre-flight lines or endpoint (4.3), no executor, no engine, no router, no
  API schema, no migration. Nothing here writes a status onto a stored row: `PlannedRow` is a value.
- Do not change `domain/values.py::PlannedRow`, `domain/statuses.py`, or any Epic 3 validator module's
  behaviour. `lines.py` gains one additive loader function and nothing else.
- Do not invent a second `Gate` alias, a second kind list, or a second YAML import site.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Working branch absent | `repo-init@1`, `base_branch: main`, `origin/chore/bmad-init` not on the remote | `plan_ref` is the SHA of `origin/main` | No error expected |
| Working branch present | `epic@1` whose `branch` input names a branch the remote holds | `plan_ref` is that branch's SHA, not the base's | No error expected |
| Base branch absent | `ls_remote(url, base_branch)` answers `None` and no working branch exists | — | `PlanError` reason `base branch not found`, `item` = the branch |
| Row 1 | any Template | `seq=1, path="plan", label="plan", kind="plan.check", gate="deterministic", status="planned"` | No error expected |
| Ungated step | a custom Template step with no `gate:` | that row's `gate` is `"unvalidated"` | No error expected |
| Loop paths | `epic@1` with three stories | `stories[0].sync` … `stories[2].commit-guard`, `frame="stories[0]"`, `story_id` = the item's `id` | No error expected |
| Nested loop paths | `initiative@1`, two epics | `epics[0].stories[0].build`; label `epic 1 · story <id> · build`; `frame="epics[0].stories[0]"` | No error expected |
| Call segments | `template` call inside a `for_each` / at top level | inside: contributes no path segment; top level: contributes its `id` | No error expected |
| Item pause after | item whose `pause_after_item_when` field is truthy | one extra row `{prefix}.after`, kind `checkpoint`, gate `human`, label `… · done checkpoint`, last in the frame | No error expected |
| Item pause before | item whose `pause_before_item_when` field is truthy | one extra row `{prefix}.before`, first in the frame, label `… · before` | No error expected |
| Item pause falsy | item whose pause field is absent or falsy | no checkpoint row for that item | No error expected |
| Agent pause flag | `agent` step with `pause_when: "story.spec_checkpoint"` | `with_resolved["spec_checkpoint"] == bool(item field)`; no extra row | No error expected |
| Empty shell command | `run: "{{repository.quality_gate_command}}"`, repository has none | `status="skipped"`, `reason="no quality_gate_command"` | No error expected |
| Empty shell command, other source | a `shell` step whose resolved `command` is empty and whose expression named no quality gate | `status="skipped"`, `reason="no command"` | No error expected |
| Story already done | `{spec_folder}/stories/{id}-*.md` exists at the ref with frontmatter `status: done`, `re_review_done` false | every row of that story frame, checkpoint rows included, `status="skipped"`, `reason="already done"` | No error expected |
| Re-review | the same with `re_review_done: true` | those rows are `planned`, `reason=None` | No error expected |
| Story file not done | the story file exists with `status: in-progress` | rows are `planned` | No error expected |
| Ambiguous story file | two files match `{spec_folder}/stories/{id}-*.md` | — | `PlanError` reason `ambiguous story file`, `item` = the id |
| Prefix-free ids | ids `4-1` and `4-10` | plans normally — `4-10` is not `4-1-…` | No error expected |
| Ids not prefix-free | ids `4-1` and `4-1-a` | — | `PlanError` reason `entry ids are not prefix-free`, `item` = `4-1-a` |
| Duplicate ids | two entries with id `4-1` | — | `PlanError` reason `duplicate entry id`, `item` = `4-1` |
| List file missing | `Git.read_file` answers `None` at every candidate ref | — | `PlanError` reason `list file not found`, `item` = the path |
| List file unparseable | the text is not a YAML sequence of mappings | — | `PlanError` reason `list file is not a list`, `item` = the path |
| `stories.yaml` entry incomplete | an entry without `id`, `title` or `description` | — | `PlanError` reason `entry is missing a required field`, `item` = the id or `entry {i}` |
| `epics.yaml` entry incomplete | an entry without `id`, `title`, `branch` or `spec_folder` | — | `PlanError` reason `entry is missing a required field` |
| Initiative list-file fallback | `epics.yaml` present at base; an epic's `stories.yaml` absent at base but present at `origin/{epic.branch}` | it is read at that branch's SHA and `plan_refs[path]` is that SHA | No error expected |
| List file read once | `initiative@1`, two epics, eight stories | `Git.read_file` is called once per `(ref, path)`; each `stories/` listing once per `(ref, prefix)` | No error expected |
| Callee missing | the `ResolvedTree` holds no `ParsedTemplate` for a `(name, version)` a call names | — | `PlanError` reason `callee not resolved`, `item` = `{name}@{version}` |
| Whole-item binding | `story: "{{story}}"` in a call's `inputs` | the callee's scope holds the item mapping itself, not its text | No error expected |
| Absent value substitution | `model: "{{model}}"` with `model` unset | resolves to `""`, not `"None"` | No error expected |
| Adapter listing | `SubprocessGit.list_files` at a ref that does not exist | `()` | A timeout is still a `GitError` |

</intent-contract>

## Code Map

Read these before writing; they are the shape every new file copies.

- `backend-api/src/orchestrator/application/templates/model.py` -- the parsed tree: `ParsedTemplate`,
  `Step{id, uses, meta, params, gate, timeout_min, agent, call}`, `ForEach{id, source, as_name, steps,
  pause_before_item_when, pause_after_item_when}`, `AgentExtras`, `TemplateCall{name, version, inputs}`.
  `Step.params` is the `with` map as ordered pairs; `run:` sugar is already `("command", <text>)`.
  `Step.gate` is `None` when the file declared none -- that is the `unvalidated` case.
- `backend-api/src/orchestrator/application/steps/__init__.py` -- `KIND_META` (`gate_default`,
  `timeout_default_min`, `with_keys`, `planner_only`), `AGENT_KIND`, `CHECKPOINT_KIND`,
  `TEMPLATE_CALL_KIND`. `plan.check` is `planner_only` with `gate_default="deterministic"`,
  `timeout_default_min=5`; `checkpoint` is `("human", None)`; `shell` is `("deterministic", 30)`.
  There is no `SHELL_KIND` constant yet -- add one here beside the three that exist, the way AD-9 says
  a kind is named here or nowhere. Do not change any existing row.
- `backend-api/src/orchestrator/application/graph.py` -- the walker voice to copy: a frozen `_Frame`
  dataclass, small helpers, one rule per function, and `_item_checkpoint` proving that a planner-inserted
  checkpoint takes `KIND_META[CHECKPOINT_KIND].gate_default` rather than `unvalidated`.
- `backend-api/src/orchestrator/application/templates/expressions.py` -- `ENTITY_FIELDS` (the whitelist:
  `project.name`; `repository.url | default_branch | install_command | quality_gate_command |
  unit_test_command`), `EXPRESSION`, `VARIABLE`, `WHOLE_VARIABLE`, `BARE_FIELD`, `ITEM_TYPE`. **Reuse
  these regexes and the whitelist**; a second copy is how substitution and validation come to disagree.
- `backend-api/src/orchestrator/application/templates/lines.py` -- `load_with_lines`, `LinedMap`,
  `LinedSeq`, `LineLoader`, `as_map`, `as_seq`. The one module that imports `yaml`; the new
  `load_sequence` goes here for that reason.
- `backend-api/src/orchestrator/domain/values.py` -- `PlannedRow{seq, path, label, kind, gate, status,
  reason, with_resolved, frame, story_id}`, already final. `gate` is the **domain** `Gate` (four tokens);
  `kind` is a plain `str`.
- `backend-api/src/orchestrator/domain/entities/run.py` -- `plan_ref: str | None`, `plan_refs: dict[str,
  str]` "the commit each list file was read at, so a plan can be called stale". That docstring fixes what
  `Plan.plan_refs` holds: one entry per list file, not per file read.
- `backend-api/src/orchestrator/domain/ports/git.py` -- the port's three conventions (`GitError` on
  failure, `None`/`False` for "not there", a `Path` the caller composed). `read_file(dest, ref, path)`
  takes the base clone's path, which is why `plan_run` needs `base_dir`.
- `backend-api/src/orchestrator/infrastructure/git/subprocess_git.py` -- `_run`, `_attempt`, `_remote`,
  and `read_file`'s two-candidate loop (`origin/{ref}` then `ref`). `list_files` copies that loop.
- `backend-api/tests/unit/fakes/git.py` -- the shared fake: scripted lists, `calls`, an optional
  `FakeClock`. Extend it; do not write a second `Git` double.
- `backend-api/src/orchestrator/domain/errors.py` + `api/errors.py::DOMAIN_STATUS` -- `Invalid` maps to
  422 and `ProblemError` already carries `{template, version, line, path, reason}`, so `PlanError(Invalid)`
  reaches the Operator as a problem document in 4.3/4.4 with no new mapping.
- `backend-api/src/orchestrator/application/use_cases/clone_check.py` -- how a use case takes ports plus
  `work_dir`/`bmad_version` as arguments because `application/` may not read the environment (AD-20), and
  how `{work_dir}/{project.slug}/{repository.slug}/base` is composed (`BASE_DIRECTORY`).
- `templates/{repo-init,epic,story,initiative}.yaml` -- the four shipped files, read verbatim by
  `tests/unit/application/templates/test_shipped_templates.py` (`REPO_ROOT`/`TEMPLATES_DIR` pattern to
  copy). **`story@1`'s fourth step id is `commit-guard`, with a hyphen.**
- Read-only anchors: `tests/unit/test_source_limits.py` (<= 400 lines, no `print`, no wall clock in
  `application/`), `test_coverage_gates.py` (no `pragma: no cover` in the rule packages),
  `test_layering.py`, `test_check_test_pairs.py`, `test_git_port.py` (asserts `FakeGit` satisfies `Git`
  and pins the fake's defaults -- keep every one of them true).

## Tasks & Acceptance

**Execution:**

- `backend-api/src/orchestrator/domain/ports/git.py` -- append `list_files(self, dest: Path, ref: str,
  prefix: str) -> tuple[str, ...]` to the `Git` protocol: every repository-relative path under `prefix`
  at `ref`, `()` when the ref or the prefix is not there. Docstring states that "not there" is `()`, per
  the module's second convention.
- `backend-api/src/orchestrator/infrastructure/git/subprocess_git.py` -- implement `list_files` with
  `ls-tree -r --name-only` over the same `(origin/{ref}, ref)` candidate loop `read_file` uses, ending
  option parsing with `END_OF_OPTIONS` before the prefix; split the output on newlines, drop blanks.
- `backend-api/src/orchestrator/application/steps/__init__.py` -- add `SHELL_KIND = "shell"` and
  `PLAN_KIND = "plan.check"` beside `AGENT_KIND`/`CHECKPOINT_KIND`/`TEMPLATE_CALL_KIND`, with the same
  one-line rationale voice. Nothing else in the module changes.
- `backend-api/src/orchestrator/application/templates/lines.py` -- add `load_sequence(text: str) ->
  LinedSeq | None`: one YAML document whose root is a sequence, `None` for anything else, never raising.
  Keeps `yaml` a single import site.
- `backend-api/src/orchestrator/application/dto.py` -- new: frozen `ProjectSnapshot{id, name, slug}`,
  `RepositorySnapshot{id, slug, url, default_branch, install_command=None, quality_gate_command=None,
  unit_test_command=None, test_globs=()}`, `RunInputs{project, repository, base_branch, values: dict[str,
  Any] = {}, harness: str = "claude", model: str | None = None, re_review_done: bool = False}`. `values`
  holds the Template's own declared inputs (`branch`, `spec_folder`, `initiative_folder`, …).
- `backend-api/src/orchestrator/application/templates/plan_model.py` -- new: `PlanError(Invalid)` with
  keyword-only `reason, template, version, line, item`; the reason constants (`LIST_FILE_NOT_FOUND`,
  `LIST_FILE_NOT_A_LIST`, `ENTRY_MISSING_FIELDS`, `DUPLICATE_ENTRY_ID`, `ID_NOT_PREFIX_FREE`,
  `AMBIGUOUS_STORY_FILE`, `CALLEE_NOT_RESOLVED`, `BASE_BRANCH_NOT_FOUND`); the skipped reasons
  (`REASON_ALREADY_DONE`, `REASON_NO_QUALITY_GATE`, `REASON_NO_COMMAND`); the path/label constants
  (`PLAN_PATH`, `PATH_SEPARATOR`, `LABEL_SEPARATOR = " · "`, `BEFORE_ITEM`, `AFTER_ITEM`,
  `AFTER_LABEL = "done checkpoint"`); frozen `ResolvedTree{root, callees: tuple[ParsedTemplate, ...]}`
  with `callee(name, version) -> ParsedTemplate | None` and `pinned_versions() -> tuple[TemplateRef, ...]`
  (root first, then callees in walk order -- what 4.4 writes to `Run.pinned_versions`); frozen
  `Plan{plan_ref: str, plan_refs: dict[str, str], rows: tuple[PlannedRow, ...]}`.
- `backend-api/src/orchestrator/application/templates/reader.py` -- new: `PlanReader`, the only thing
  that touches `Git` here. Holds `git`, `base: Path`, `url`, a `plan_refs` dict, and memo dicts.
  `sha(branch) -> str | None` (memoised `ls_remote`), `read(ref, path) -> str | None` (memoised
  `read_file`), `listing(ref, prefix) -> tuple[str, ...]` (memoised `list_files`), `record(path, sha)`.
  Memoisation is what makes "each list file is read once" checkable on `FakeGit.calls`.
- `backend-api/src/orchestrator/application/templates/substitute.py` -- new: `resolve(value, scope)` and
  `lookup(name, field, scope)`. A string that is exactly `{{name}}` returns the scope value **whole**
  (any type, `None` included); every other string interpolates each `{{name}}` / `{{name.field}}` with
  `""` for `None` and `str(...)` otherwise; mappings and sequences recurse; anything else is returned as
  is. A field on an entity snapshot is read only when `expressions.ENTITY_FIELDS` allows it; a field on a
  mapping item is `item.get(field)`; anything else is `None`. Reuse `expressions.WHOLE_VARIABLE`,
  `EXPRESSION` and `VARIABLE`.
- `backend-api/src/orchestrator/application/templates/lists.py` -- new: `read_list(reader, frame, path)`
  returning `(items, ref_used)`; `list_kind(path)` (`stories.yaml` / `epics.yaml` / neither, by basename);
  `REQUIRED_FIELDS` per kind (`stories`: `id, title, description`; `epics`: `id, title, branch,
  spec_folder`); `check_entries(...)` raising `PlanError` for a missing field, a duplicate id, or ids that
  are not prefix-free (`b.startswith(a + "-")`, so `4-1`/`4-10` is fine and `4-1`/`4-1-a` is not);
  `story_done(reader, ref, stories_dir, story_id)` -> `bool`, raising `AMBIGUOUS_STORY_FILE` on two
  matches and reading the matched file's YAML frontmatter for `status: done`. The fallback ref rule lives
  in `read_list`: absent at `frame.ref` and the frame declares a branch the remote holds -> read at that
  branch's SHA and return it as `ref_used`.
- `backend-api/src/orchestrator/application/templates/rows.py` -- new: the walker. Frozen `Frame{prefix,
  labels, ref, scope, story_id, skipped, template, branch, in_loop}` and `Context{tree, inputs, reader,
  bmad_version}`; `expand(steps, frame, ctx)`, `expand_loop`, `expand_call`, `step_row`,
  `checkpoint_row`, `agent_extras`, `row_status`, `working_branch(template, scope)`. Keep every function
  <= 50 lines.
- `backend-api/src/orchestrator/application/templates/plan.py` -- new: the public
  `plan_run(tree, inputs, *, git, base_dir, bmad_version) -> Plan`. Builds the reader and the root scope,
  resolves `plan_ref`, emits the `plan` row, calls `expand`, numbers `seq` densely from 1, and returns the
  `Plan` with `plan_refs` copied out of the reader.
- `backend-api/src/orchestrator/application/use_cases/plan_run.py` -- new: frozen `PlanPorts{templates,
  git}`; `resolve_tree(templates, ref) -> ResolvedTree` walking `TemplateCall`s transitively through
  `TemplateVersionRepository.get` + `validate()` (a version that is missing, or that no longer validates,
  is a `PlanError`); `plan_for(ports, ref, inputs, *, base_dir, bmad_version) -> Plan`.
- `backend-api/tests/unit/fakes/git.py` -- extend additively: new optional keywords `refs: dict[str, str]`
  (branch -> sha for `ls_remote(url, branch)`), `files: dict[tuple[str, str], str]` (`(ref, path)` ->
  text) and `listings: dict[tuple[str, str], list[str]]` (`(ref, prefix)` -> paths), plus the new
  `list_files` port method. When a mapping keyword is `None` the existing sequential script answers, so
  every current caller and every assertion in `tests/unit/test_git_port.py` is unaffected.
- `backend-api/tests/unit/application/templates/plan_fixtures.py` -- new: the scripted repositories the
  plan tests share -- `stories.yaml` / `epics.yaml` texts, story-file texts, and builders for
  `ProjectSnapshot` / `RepositorySnapshot` / `RunInputs` / `ResolvedTree` over the four shipped Templates.
- New test modules, each written before the module it covers:
  `tests/unit/application/test_dto.py`;
  `tests/unit/application/templates/test_plan_model.py`;
  `tests/unit/application/templates/test_plan_substitute.py`;
  `tests/unit/application/templates/test_plan_reader.py`;
  `tests/unit/application/templates/test_plan_lists.py` (also imports `lines.load_sequence`);
  `tests/unit/application/templates/test_plan_rows.py` (synthetic Templates: ungated step, top-level
  call, `before` pause, empty command with and without the quality-gate expression);
  `tests/unit/application/templates/test_plan_shipped.py` (the six acceptance criteria below, on the four
  shipped files);
  `tests/unit/application/test_plan_run_use_case.py`;
  `tests/unit/test_git_list_files.py` (port, fake and `SubprocessGit.list_files` against a real temporary
  repository, the way `tests/unit/test_subprocess_git.py` builds one).

**Acceptance Criteria:**
- Given `repo-init@1`, `base_branch: main`, and a `Git` where `chore/bmad-init` is not on the remote, when
  planned, then `plan_ref` is `origin/main`'s SHA and the rows are `plan, checkout, install, commit, push,
  link` with `seq` 1-6, gates `deterministic ×5` then `liveness`, `checkout.with_resolved` substituting to
  `{base: "main", branch: "chore/bmad-init"}`, and `push.with_resolved["branch"] == "chore/bmad-init"`.
- Given `epic@1` with three stories where story `2` declares `done_checkpoint: true` and story `3` has a
  `done` story file, and `re_review_done` false, when planned, then the rows are `plan, checkout,
  baseline, stories[0].{sync,build,verify,commit-guard}, stories[1].{sync,build,verify,commit-guard},
  stories[1].after, stories[2].{sync,build,verify,commit-guard} (all `skipped · already done`), push,
  link`; labels read `story 1 · build` and `story 2 · done checkpoint`; every story row carries `frame`
  and `story_id`.
- Given the same with `re_review_done: true`, when planned, then story `3`'s rows are `planned` with no
  reason.
- Given a repository with no `quality_gate_command`, when `epic@1` is planned, then `baseline` and every
  `verify` row are `skipped` with reason `no quality_gate_command`.
- Given `initiative@1` with two epics on the same branch and eight stories, when planned, then paths read
  `epics[i].stories[j].<step>`, labels read `epic 1 · story <id> · build`, each epic frame ends with
  `epics[i].push`, `epics[i].link` and -- only where the epic declares `done_checkpoint` --
  `epics[i].after`, and each `stories.yaml` is read exactly once.
- Given a `stories.yaml` holding ids `4-1` and `4-1-a`, or an entry missing a required field, when
  planned, then a `PlanError` carrying `template`, `version`, `line`, `item` and `reason` is raised naming
  the offending entry.
- Given a custom Template step that declares no `gate`, when planned, then its row's `gate` is
  `unvalidated`.
- Given `make lint`, when it runs, then ruff, `mypy --strict`, `lint-imports`, the env contract and the
  test-pair gate all pass.
- Given `make test`, when it runs, then the unit suite is green and the 100 % branch re-report over
  `domain/` + `application/` still passes.

## Spec Change Log

### 2026-09-06 — `on_fail` and `escalate_when` reach the row

**Triggering finding.** The `deferred` item this story recorded — a step's `on_fail`,
`redispatch`/`redispatch_max` and an agent's `escalate_when` are parsed but reach no row — was not
open after all. The coordinator relayed the binding half of brief 4-7 (the executor story), which is
an anchor this story may not read: the `shell` executor switches on `with_resolved.on_fail` and must
build `Redispatch{target_seq, max}` from the row **and no other input**, because AD-7 forbids
re-reading the Template at execution time and an executor sees one row and never the plan.

**What was amended.** The requirement was implemented rather than deferred:

- `with_resolved["on_fail"]` is the word the file wrote (`fail` / `continue` / `escalate`), or
  `{"target_seq": int, "max": int}` for the redispatch form. A row that declared nothing carries no
  key, which the executor reads as the DSL's own default, `escalate`.
- The target is resolved **inside the row's own frame**, so `stories[3].verify` goes back to
  `stories[3].build` and never to another Story's, and to a `seq` rather than to an id.
- `with_resolved["escalate_when"]` is carried verbatim on every agent row (`None` when undeclared).
  Nothing in this epic reads it; Epic 5 has no other source.
- A target the frame does not hold is `PlanError{reason: "redispatch target is not a row of this
  frame", item: <the path looked for>}`.

**Known-bad state avoided.** Two. Resolving the target to a **step id** would have left 4-7 unable to
build a `Redispatch` without the plan. Resolving it **globally** rather than per frame would have sent
one Story's failed verify back to a different Story's build — silently, and only under retry.

**KEEP.** The two-shape pipeline is deliberate and must survive re-derivation: the walker records a
`Redispatched` value object holding the target **path** plus its declaring Template, because `seq` is a
property of the finished list and does not exist mid-walk; `plan.numbered` is the single place where
both facts exist at once, and it assigns `seq` and resolves the route in one pass. Keep the refusal
named from the route's own Template — the frame that declared it is gone by numbering time, so a root-
named error would point at the wrong file for a step written in a callee. Keep `working_branch` in
`plan_model.py`: it moved there to hold `rows.py` under the 400-line limit.

## Review Triage Log

### 2026-09-06 — Review pass
- intent_gap: 0
- bad_spec: 0
- patch: 12: (high 1, medium 4, low 7)
- defer: 8: (high 0, medium 3, low 5)
- reject: 7: (high 0, medium 1, low 6)
- addressed_findings:
  - `[high]` `[patch]` `SubprocessGit.list_files` used `--name-only` without `-z`, so git
    quoted and octal-escaped any path holding a non-ASCII byte; `story_done`'s `{id}-*.md`
    match then decided a finished Story had written no file and the whole frame would be
    dispatched again. Now `-z`, split on NUL. The new adapter test was checked to fail
    against the old flag set (3 failures) and pass against the new one.
  - `[medium]` `[patch]` `AMBIGUOUS_STORY_FILE` was unreachable on a re-review, because
    `_already_done` returned before the lookup. Two files matching one Story is a fact about
    the repository, so the lookup now always runs and only its answer is dropped.
  - `[medium]` `[patch]` No guard against two rows sharing a path. `step_run` is stored
    unique on `(run_id, path)` (4.1), so a top-level step called `plan` would have been a 500
    at 4.4's insert; it is now `DUPLICATE_ROW_PATH`, a 422 at plan time.
  - `[medium]` `[patch]` The Run's `harness` and `model` reached the agent row with nothing
    asserting it — deleting both from the scope left the suite green. Asserted now, including
    that an unchosen model is `""` and not `None`.
  - `[medium]` `[patch]` `working_branch`'s kind rule had no test distinguishing it from
    "the first step that mentions a branch". Covered with a Template whose only top-level
    branch is a `git.push`, and with a remote that holds that branch.
  - `[low]` `[patch]` A command resolving to whitespace was planned; `" "` runs nothing and
    exits 0, which is a green row nobody ran. Now stripped before the emptiness test.
  - `[low]` `[patch]` `names_field` matched the field without the entity, so
    `{{project.quality_gate_command}}` would have read `no quality_gate_command`. Both halves
    are matched now.
  - `[low]` `[patch]` `inputs.values` was spread before the named fields, so a Template input
    called `repository` could replace the snapshot the Run was created from. Reordered.
  - `[low]` `[patch]` The negative memo on `PlanReader.listing`/`read` was unverified — one
    `ls-tree` per Story instead of per Run passed silently. Both negative cases asserted.
  - `[low]` `[patch]` A required list-file field present but empty was refused by an
    unasserted rule; `title: ""` and `title:` are now both covered.
  - `[low]` `[patch]` The recursive listing let `stories/3-notes/scratch.md` count as Story
    3's file, and made a real file plus a nested one ambiguous. A story file is now a file in
    the folder, not one under a folder in it.
  - `[low]` `[patch]` Test-quality: two `# type: ignore[arg-type]`/`Any` parameters that
    weakened the `mypy` gate, and a hardcoded base-clone path, replaced with the real types
    and `fixtures.BASE`.

## Design Notes

**Why `plan_run` takes `base_dir`.** The brief's signature is `plan_run(tree, inputs, *, git,
bmad_version)`, but `Git.read_file` / `list_files` take the base clone's `Path` (AD-14:
`{work_dir}/{project.slug}/{repository.slug}/base`), and `application/` may not read the environment
(AD-20), so the path has to arrive as an argument. It is keyword-only beside `git`, which keeps the
call site five arguments and the function pure.

**How the working branch is found.** `plan_ref` is "the SHA of `origin/{branch}` when the working branch
exists, else of `origin/{base_branch}`" -- and the branch a Run works on is the one its first top-level
`git.worktree` step names, resolved in scope. That one rule gives all three brief cases with no per-template
special case: `repo-init@1` names `chore/bmad-init` (absent -> base), `epic@1` names `{{branch}}`,
`initiative@1` has no top-level worktree at all (its worktree is inside the epic frame) -> base. Inside a
callee frame the same rule supplies the fallback branch the brief's `initiative@1` assumption needs: a list
file absent at the frame's ref is re-read at that branch's head when the remote holds it, and that SHA
becomes the frame's ref for the story files read under it, so a frame never mixes two commits.

**`plan_refs` holds list files.** `Run.plan_refs` is documented as "the commit each list file was read at,
so a plan can be called stale", so `read_list` is what records an entry. Story-file reads use their frame's
ref and add no entry: a story file is not what makes a plan stale.

**`with_resolved` carries the resolved `timeout_min`.** The brief's Defaults rule resolves `timeout_min`
from the step or the kind for every row, and `PlannedRow` -- frozen in 4.1 -- has no field for it, so
`with_resolved` is the only carrier a complete plan has (AD-7: no later edit may change what runs). It is
written for every row whose resolved timeout is not `None`, which is every kind but `checkpoint`. The
brief's `repo-init` AC pins `checkout.with_resolved` to the two substituted `with` keys; the test asserts
exactly those two as the substituted set, and the timeout separately.

**`commit-guard`, with a hyphen.** The brief's prose writes `stories[n].commit_guard`, which is
`template-dsl-draft.md` §3's spelling; the shipped `templates/story.yaml` declares `id: commit-guard`. The
binding rule is "top-level step -> its id", the template file is not this story's to edit, and the label
rule only maps `_` to a space -- so the path is `stories[0].commit-guard` and the label is
`story 1 · commit-guard`. Flagged rather than silently chosen.

**A story frame is a `stories.yaml` loop.** Which list a `for_each` reads is decided by the resolved
source's basename, not by the loop's id: that is also what selects the required-field set and the
`epic {i+1}` / `story {item.id}` label form. A loop over any other file gets no required fields, labels
`{as_name} {i+1}`, and no already-done rule.

**Golden expansion** (`initiative@1`, first epic, fourth story):

```text
seq  path                            label                             kind      gate
 1   plan                            plan                              plan.check deterministic
 2   epics[0].checkout               epic 1 · checkout                 git.worktree deterministic
 3   epics[0].baseline               epic 1 · baseline                 shell      deterministic
 …   epics[0].stories[3].build       epic 1 · story 4-1 · build        agent      liveness
 …   epics[0].push                   epic 1 · push                     git.push   deterministic
 …   epics[0].after                  epic 1 · done checkpoint          checkpoint human
```

## Verification

**Commands:**
- `make lint` -- expected: exit 0.
- `make test` -- expected: exit 0, including the 100 % branch re-report over `domain/` and `application/`.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` -- expected: exit 0. Docker is installed but off the default
  PATH on this machine. If no daemon is available, report that verbatim rather than skipping it silently.

## Auto Run Result

Status: done

**What landed.** `plan_run(tree, inputs, *, git, base_dir, bmad_version) -> Plan` — the pure planner
(AD-7). It resolves one commit for the whole Run, walks the pinned tree, and returns `PlannedRow`s:
`plan.check` first, one row per executable step, a `checkpoint` row wherever an item's
`pause_*_item_when` field is truthy, and `skipped` rows carrying `already done`,
`no quality_gate_command` or `no command`. Nothing is persisted and no status is written.

**Files.**
- `application/dto.py` — `ProjectSnapshot`, `RepositorySnapshot`, `RunInputs`.
- `application/templates/plan.py` — the public `plan_run`, the root scope, `plan_ref`, the plan-check
  row, and the one-path-per-row guard.
- `application/templates/rows.py` — the walker: paths, labels, frames, `story_id`, the skipped rules.
- `application/templates/agent_row.py` — what an `agent` row carries beside its `with`.
- `application/templates/lists.py` — list files, their refusals, and the already-done rule.
- `application/templates/reader.py` — `PlanReader`: the one door to `Git`, memoised (FR-10).
- `application/templates/substitute.py` — `{{name}}` / `{{name.field}}` filled in from the scope.
- `application/templates/plan_model.py` — `PlanError`, the reasons, `ResolvedTree`, `Plan`.
- `application/use_cases/plan_run.py` — resolves the tree through `TemplateVersionRepository`.
- Additive edits: `Git.list_files` (port, `SubprocessGit`, shared fake), `SHELL_KIND`/`PLAN_KIND`/
  `WORKTREE_KIND` in the kind registry, `lines.load_sequence`.
- Ten new unit-test modules and one shared fixture module.

**Review.** Four layers (blind hunter, edge-case hunter, verification-gap, intent alignment).
12 patched (1 high, 4 medium, 7 low), 8 deferred, 7 rejected. No `intent_gap` and no `bad_spec`, so
no loopback. Follow-up review recommended: `true` — a high-severity finding was patched (score 19).

**Verification, as run on this machine.**
- `make lint` — exit 0 (ruff, `mypy --strict`, `lint-imports` 3/3 kept, env contract, test pairs
  79/79, `gen:api --check`, web-client).
- `make test` — exit 0; backend 2878 passed / 23 skipped, `domain/` + `application/` **100 % branch,
  0 missing**; web-client 722 passed.
- `PATH="$HOME/.docker/bin:$PATH" make e2e` — exit 0; 107 passed, 21 subtests, against a fresh
  `aio-e2e` stack torn down cleanly. Docker is installed at `~/.docker/bin/docker` and is not on the
  default PATH on this machine.
- `make e2e-ui` — not run; it changes no web-client file and 4.1 recorded that port 4321 is held by
  the operator's own dev stack.

**Follow-up commit (relayed 4-7 requirement).** `with_resolved.on_fail` and `with_resolved.
escalate_when` now carry a row's routing, with the redispatch target resolved to a `seq` inside the
row's own frame; an unresolvable target is a `PlanError`. See the Spec Change Log entry above. The
`deferred` item covering this is closed; the other two stand.

**Residual risks.**
- Three readings had to be chosen where the brief's prose and its anchors disagree, each flagged in
  **Design Notes**: `base_dir` added to the signature the brief fixes; `timeout_min` written into
  `with_resolved` because `PlannedRow` has no field for it; and `commit-guard` with a hyphen, since
  `templates/story.yaml` declares that id and the brief's row lists spell it `commit_guard`.
- The seven remaining `deferred` entries are the honest list of what a later story must decide. The
  two that matter are the dropped Template input `default:` values and the partly-resolved command,
  both of which the brief's own wording currently licenses.
- The validator's earlier-agent set is flat over a whole file, so it accepts a redispatch from inside
  a loop to a step outside it. The planner refuses that at plan time rather than guessing; if a
  Template ever legitimately needs it, the rule to change is `rows._routing`, not the validator.
- `Context.bmad_version` is carried and read by no rule yet. It is the brief's own signature; the
  first consumer is an executor.
