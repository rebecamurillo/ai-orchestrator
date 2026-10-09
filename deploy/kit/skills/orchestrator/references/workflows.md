# Customizing workflows

A workflow is a **template**: one YAML file, stored in the instance, that a Run is planned
from. The shipped templates are a starting point. Change them to fit the project — a
different verify command position, a longer timeout, another review step, a checkpoint where
the team wants a human look, a different skill or model on one step.

Templates live in the instance's database, not in the project repository and not in this
skill. Read them from the instance every time; never edit from memory.

## What a save does

- A saved version never changes. Every edit is a **new version** `max + 1` beside the old
  ones; every earlier version stays readable.
- A save applies to **Runs planned after it**. A Run already planned, queued, running or
  parked keeps the tree it was planned from. To move a parked Run onto an edited template,
  cancel it and create a new one.
- A template that calls another by `name` with no `version` follows the callee's latest
  version each time a Run is planned. Editing a callee is therefore one save; the callers
  stay untouched. A call that writes an integer `version` is pinned and does not follow.
- A save that would break a following caller (an input it binds was renamed or removed, or
  a new required input it does not bind) is refused, and the refusal names that caller.
- An upgrade that ships a changed template stores the shipped file as a new version **above
  yours**, so it becomes the latest. Nothing is overwritten, but unpinned callers and new
  Runs now pick the shipped one. After every upgrade, list the versions of each template you
  customized and, if a shipped version landed on top, re-apply your change as the next
  version.

## The edit loop

In the web UI: `/templates` → pick the template and a version → edit the YAML → **Validate**
→ **Save as v{n+1}**. The editor shows which callers follow the save and which are pinned.

Over the API (same bearer as everything else):

1. `GET /api/v1/templates` — names and version lists.
2. `GET /api/v1/templates/{name}/{version}` for the latest — `yaml`, `inputs`, `calls`,
   `called_by` (each caller with `pinned`), `pinned_by`.
3. Edit the YAML. Set the file's own `version:` to `max + 1`; `name:` must equal the name in
   the path. The stored number, not the one written in an older file, is what counts.
4. `POST /api/v1/templates/{name}/validate` with `{yaml}` — always 200. `errors[]` is
   `{line, reason}` per problem; `unvalidated[]` lists steps with no declared `gate`. Fix
   until `errors` is empty.
5. `POST /api/v1/templates/{name}/versions` with `{yaml}` → 201. A 422 carries the same
   `errors[]`.
6. `POST /api/v1/runs/preflight` with the new version and the real inputs; read `rows[]` to
   confirm the plan is the one intended before any Run spends money.

A new workflow is the same loop under a new name at `version: 1`. To offer it on
`/workflows/new`, the instance's `ROOT_TEMPLATES` must be blank or list its name (instance
`.env`, read at start-up — the `orchestrator-admin` skill owns that change).

**Ask the human before saving.** A template edit changes what every later Run does and what
it costs. Show the diff, say which callers follow it, and wait for the go-ahead. Never save a
template to get one parked Run moving.

## The file

```yaml
name: my-story            # slug; equals the name it is saved under
version: 4                # integer literal, max + 1
description: one line
inputs:
  repository: { type: repository, required: true }
  spec_folder: { type: path, required: true }
  story:      { type: item, required: true }     # bound by a caller's for_each
  harness:    { type: enum, values: [claude, codex, local], default: claude }
  model:      { type: string, required: false }
steps:
  - id: build
    uses: agent
    ...
```

Input types: `project`, `repository`, `string`, `path`, `enum` (with `values`), `number`,
`item`. `required`, `default` and `values` are the only other keys.

### Steps

Each step has an `id` (slug, unique in the file, not all digits) and either `uses: <kind>`
with an optional `with:` map, or `run: "<command>"` (a shell step). Common keys: `gate`
(`liveness | deterministic | human`), `timeout_min`, `stall_min`,
`on_fail` (`escalate | fail | continue`, or `{redispatch: <earlier agent step id>, max: n}`).
A step with no `gate` still runs, and is reported `unvalidated` — never shown green.

| Kind | `with` keys | What it does |
| --- | --- | --- |
| `run:` (shell) | — | Runs the command in the Run's worktree with the Project's env. A command that resolves empty plans the row `skipped` |
| `agent` | `harness`, `model`, `workdir`, and one dispatch form: `skill` (+ `args`, `prompt_extra`), `prompt`, or `prompt_file` | Dispatches a coding agent |
| `checkpoint` | `when` | Stops the Run for a human; a falsy `when` plans it `skipped` |
| `template` | `name`, `version` (omit to follow latest), `inputs` | Calls another template. No `timeout_min`/`on_fail` on the call itself |
| `git.worktree` | `base`, `branch`, `mode` | Opens the Run's worktree |
| `git.sync` | — | Fetch and fast-forward |
| `git.merge` | `from` | Merges `origin/{from}` into the Run's branch |
| `git.submodule` | none or `update`, **or** `workdir` + `branch` (+ `base`) | Init/update submodules, or check out a branch inside one |
| `git.commit` | `message`, `workdir` | Commits (the protected-path check runs here) |
| `git.push` | `branch`, `workdir` | Pushes; refuses the default branch |
| `pr.link` | `branch` | Records the compare URL |
| `bmad.install` | — | Installs the BMAD method into the worktree |

An `agent` step also takes, beside `with`:

- `prompts: {dispatch, rendered, answer, halt, redispatch}` — every sentence the agent is
  sent is written here; the orchestrator adds none of its own. The `skill` form requires
  `dispatch` and `rendered`; `pause_when` requires `halt`. Single-brace tokens (`{skill}`,
  `{spec_folder}`, `{story_id}`, `{path}`, `{condition}`, `{answer}`) are filled at dispatch.
- `expect: {files: [glob], success: [...], blocked: [...], checkpoint: [...],
  misconfigured_when: [...]}` — the result file the step must leave and how its status
  routes.
- `retry: {max, prompt, resume_session}` — the only automatic retry there is, bounded.
- `pause_when: "<name>.<field>"` — stop for a human after this step when the field is truthy.

### Loops and calls

`for_each: "<path to a list file>"` with `as: <name>` and nested `steps` runs those steps
once per entry. One loop per file, no nesting — a second level is a `uses: template` call
inside the loop (call depth at most 3, no cycles). `pause_before_item_when` /
`pause_after_item_when: "<name>.<field>"` plan a checkpoint around each item.

### Expressions

`{{name}}` and `{{name.field}}` only — substitution, no filters, comparisons or
concatenation inside the braces. A name is a declared input or, inside a loop, the `as`
name. `repository` exposes `url`, `default_branch`, `install_command`,
`quality_gate_command`, `unit_test_command`; `project` exposes `name`. Fields of an `item`
are whatever the list file holds and are not checked: a missing one resolves empty.

## Common customizations

- **Change what verifies a story or an epic.** Prefer data over a template edit: shell rows
  in the shipped flow run commands that come from the repository record or from `epics.yaml`
  (`install`, `test`, `quality_gate`). Edit those first. Edit the template only to add,
  remove or reorder the row itself.
- **Add a deterministic check.** A `run:` step with `gate: deterministic` and
  `on_fail: { redispatch: <agent step id>, max: 1 }` sends a failure back to the agent once,
  then parks.
- **Add a human stop.** A `checkpoint` step, or `pause_when` on an agent step.
- **Give one step its own model or harness.** Write a literal in that step's `with.model` /
  `with.harness` instead of `{{model}}` / `{{harness}}`.
- **Longer or shorter limits.** `timeout_min` on any step; `stall_min` on an agent step that
  legitimately goes quiet for long stretches (a read-only review).
- **Another agent step.** Copy an existing one, give it a new `id`, its own `skill` or
  `prompt`, and its own `expect.files`.
- **Reword what agents are told.** Edit the step's `prompts` and `retry.prompt`.

## What a template cannot change

- **Which shell commands an agent may run.** That is the harness allowlist on the instance
  (`CLAUDE_ALLOWED_TOOLS` in its `.env`), not the workflow. An agent parked because `yarn`,
  `npx` or another tool was denied is an instance fix — the `orchestrator-admin` skill.
- **The protected-path guard, the budget rule, the status tokens.** These are the
  orchestrator's, whatever the template says.
- **A Run already planned.** See *What a save does*.

## Validation reasons

`errors[].reason` is one of a fixed set; the ones an edit usually meets:

| Reason | Usual cause |
| --- | --- |
| `unknown key` | A key the level does not accept, or a `with` key the kind does not take |
| `unbound variable` / `unknown field` | `{{x}}` is not a declared input or loop name; an entity field outside its list |
| `expression syntax` | Anything in `{{ }}` beyond `name` or `name.field` |
| `callee input mismatch` / `callee not found` | A call's `inputs` do not match the callee's declared inputs by name and type; no stored template of that name |
| `duplicate step id` / `invalid slug` / `all-digit step id` | An `id` problem |
| `redispatch target not an earlier agent step` | `on_fail.redispatch` must name an `agent` step written above it |
| `dispatch prompt required` / `rendered prompt required` / `halt prompt required` / `retry prompt required` | The `prompts` or `retry` clause that form needs is missing |
| `invalid dispatch form` | More than one of `skill`, `prompt`, `prompt_file` |
| `nested for_each` / `second for_each` / `parallel is reserved` | Loop limits |
| `version must be N` / `name must be X` | The file's own header does not match the save |
