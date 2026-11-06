# templates/ — the shipped workflow templates

Every `*.yaml` directly in this directory is seeded into the instance at start-up as the next
version of its name (`seed_shipped`, by content hash). Five single files ship; none calls
another template. `drafts/` is never seeded. The operator's own templates live in a separate
folder (§ The operator's folder). `tests/unit/application/templates/test_shipped_families.py`
checks that this table names every shipped file and that every staged file carries the fixed
header block under its `description:` (`# family … # called by … # sibling …`) — names and
headers only, never steps, ordering or counts (hard rule 6).

| file | family | role | calls | on the menu | sibling in the other family |
| --- | --- | --- | --- | --- | --- |
| `staged-initiative-hub.yaml` | staged | root, hub scope | — | yes | `drafts/initiative-hub.yaml` |
| `staged-initiative-repo.yaml` | staged | root, single repository | — | yes | — (the auto family has no single-repository initiative root) |
| `harness-readiness.yaml` | — | root, harness readiness fixture flow | — | no | `drafts/epic.yaml` |
| `repo-init.yaml` | — | root, bootstrap the BMAD method into a repository | — | yes | — |
| `agent-smoke.yaml` | — | root, one-dispatch check of an install | — | yes | — |

`drafts/` keeps the retired auto family as a reference, never seeded:

- `drafts/initiative-hub.yaml`, `drafts/initiative-hub-epic.yaml`, `drafts/initiative-hub-story.yaml` — the multi-repository hub flow, three linked files
- `drafts/initiative.yaml`, `drafts/epic.yaml`, `drafts/story.yaml` — the single-repository flow, three linked files
- `drafts/story-run.yaml`, `drafts/story-staged.yaml` — the story pieces

**auto** — one `bmad-build-auto` session per story (plan, implement, review in one context).
Maintained, not evolved. **staged** — three sessions per story, `plan` → `implement` →
deterministic `verify` → `review`, each on its own model (`plan_model`, the Run's `model`,
`review_model`) and its own limit, each routed on a marker under `{spec_folder}/stories/.auto/`.
New workflow behaviour lands in the staged family. The menu is `ROOT_TEMPLATES` in the instance
`.env`.

The staged epic tail routes its `retro` row on `{spec_folder}/stories/.auto/retro.md`, not on
`RETROSPECTIVE.md`: `status: rejected` parks the Run `blocked` on that row with the marker's
`## Auto Run Result` section as the reason, `accepted` and `accepted-with-open-items` carry on.
The stop admits `answer`, `skip_step`, `skip_epic` and `cancel`, not `continue`.

## The single-file format

A template is one YAML file: `name`, `version`, optional `inputs` and `description`, and
`steps`. A step is a call to a built-in (`uses: agent`, `git.sync`, `git.worktree`, …) or a
loop (`for_each`). A loop reads a list file (`stories.yaml`, `epics.yaml`) from the repository
at plan time and plans its `steps` once per entry; loops nest to a depth of two. Three working
examples, each valid as written and the only `yaml` blocks in this file. Each opens with a
top-level `git.worktree` checkout — an agent step runs in the Run's worktree:

Depth 0 — no loop, one agent step after the checkout:

```yaml
name: example-depth-0
version: 1
inputs:
  project: { type: project, required: true }
  repository: { type: repository, required: true }
  base_branch: { type: string, required: true }
  branch: { type: string, required: true }
  spec_folder: { type: path, required: true, description: The folder holding SPEC.md and stories/ }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
  - id: build
    uses: agent
    with:
      harness: claude
      skill: bmad-build-auto
    prompts:
      dispatch: "Run the skill {skill}: spec folder {spec_folder}, story id {story_id}."
      rendered: "The workflow for skill {skill} is rendered at {path}; read and follow it."
    gate: liveness
```

Depth 1 — a `stories` loop over `{{spec_folder}}/stories.yaml`:

```yaml
name: example-depth-1
version: 1
inputs:
  project: { type: project, required: true }
  repository: { type: repository, required: true }
  base_branch: { type: string, required: true }
  branch: { type: string, required: true }
  spec_folder: { type: path, required: true, description: The folder holding stories.yaml }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
  - id: stories
    for_each: "{{spec_folder}}/stories.yaml"
    as: story
    steps:
      - id: build
        uses: agent
        with:
          harness: claude
          skill: bmad-build-auto
        prompts:
          dispatch: "Run the skill {skill}: spec folder {spec_folder}, story id {story_id}."
          rendered: "The workflow for skill {skill} is rendered at {path}; read and follow it."
        gate: liveness
```

Depth 2 — an `epics` loop holding a `stories` loop:

```yaml
name: example-depth-2
version: 1
inputs:
  project: { type: project, required: true }
  repository: { type: repository, required: true }
  base_branch: { type: string, required: true }
  branch: { type: string, required: true }
  initiative_folder: { type: path, required: true, description: The folder holding epics.yaml }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
  - id: epics
    for_each: "{{initiative_folder}}/epics.yaml"
    as: epic
    # agent steps read spec_folder from scope, so the epics loop binds it
    bind: { spec_folder: "{{initiative_folder}}/{{epic.spec_folder}}" }
    steps:
      - id: stories
        for_each: "{{spec_folder}}/stories.yaml"
        as: story
        steps:
          - id: build
            uses: agent
            with:
              harness: claude
              skill: bmad-build-auto
            prompts:
              dispatch: "Run the skill {skill}: spec folder {spec_folder}, story id {story_id}."
              rendered: "The workflow for skill {skill} is rendered at {path}; read and follow it."
            gate: liveness
```

### Scope and names

- A name in `{{…}}` resolves from the innermost scope outward: the loop's `as` name (`story`,
  `epic`, read as `{{story.title}}`), then names a loop `bind`s, then the Run's inputs. An inner
  loop sees everything its outer loops declare.
- `bind` (on a loop) maps scope names to values rendered once per item, so an inner step or
  loop can read them as plain names. The depth-2 example binds `spec_folder` per epic.
- An input may carry an optional `description`; the Run form shows it under the field.
- `spec_folder`, stated plainly: it is the one name agent steps read implicitly from scope. With
  one loop it comes from the `spec_folder` input; with an epics loop it must be bound on that
  loop as in the example; without it agent rows plan with no story contract and no error.
- Loop ids `epics` and `stories` are what the `skip_epic` and `skip_story` signals act on. A loop named neither `epics` nor `stories` gets no skip signal of its own; an outer loop must be called `epics` for *Skip epic* to stop at its boundary.
- A `git.worktree` inside a loop gets no per-item fresh branch.
- A redispatch must name an earlier agent step of the same `steps` list; a cross-list target
  validates but is refused at plan time.
- Put `only` on the outermost loop; an inner `only` refuses the plan for any outer item whose
  list lacks the id.
- Preflight's `SPEC.md` check assumes `spec_folder` = `{{initiative_folder}}/{{epic.spec_folder}}`.

### The `version:` line

`version:` is required by the parser; for a folder file its value is ignored. The instance assigns the next number and the reload answer reports it in `stored[].version`. Leave the line as it is (`version: 1` is fine). Changing only the `version:` line changes the file's hash and stores a new version. A web UI save still has to say the next number.

## The operator's folder

`OPERATOR_TEMPLATES_DIR` (in `.env`) names a folder of the operator's own templates; the
deployment mounts `./templates` there read-only:

```text
OPERATOR_TEMPLATES_DIR=/app/operator-templates
volumes:  - ./templates:/app/operator-templates:ro
```

Only lower-case `*.yaml` files directly under the folder are read; names starting with `.` are
ignored; files over 1 MiB are refused. The folder is read at start-up and on reload:

```text
curl -X POST -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" http://localhost:8000/api/v1/templates/reload
```

```text
{
  "folder": "/app/operator-templates",
  "stored": [{"name": "my-flow", "version": 3, "file": "my-flow.yaml", "overrides_shipped": false}],
  "unchanged": [{"name": "example-depth-0", "version": 1, "file": "example-depth-0.yaml", "overrides_shipped": false}],
  "refused": [{"file": "broken.yaml", "errors": [{"reason": "unknown step kind", "template": "broken", "line": 7}]}],
  "not_in_folder": [{"name": "agent-smoke", "overrides_shipped": true}]
}
```

A Run in flight keeps the version it was planned on; a reload only affects Runs planned later.

When the folder holds a file named after a template, edit the file: a version saved on the instance is superseded by the file's content as the next version at the next reload or start-up, and stays listed.

A name is listed in `not_in_folder` only when the folder once stored a version of it; a file that never stored one (its content always equalled the latest version, or it was always refused) is not listed after removal.

A shipped name listed in `not_in_folder` with `overrides_shipped: true` keeps running your last folder version. To go back to the shipped text, copy the image's `/app/templates/agent-smoke.yaml` (for that name) into the folder, or save it in the web UI.

### Linked templates

Stored templates may call another template unpinned. A folder change to such a callee is
refused when it would strand any stored version of a caller; the caller-check errors are in the
reload answer's `refused[].errors`. The way out is a single file (no call) or a new name.

## Checking a release

Run after an upgrade. Each step names its inputs and the result to expect.

Preconditions:

- The folder is mounted and `OPERATOR_TEMPLATES_DIR` is set (`deploy/README.md` § Editing the workflow templates, upgrade note).
- The fixtures are git remotes the instance can clone, made the way `backend-api/tests/e2e/helpers/hub_fixture.py` (`make_hub`) makes them, but pushed to private GitHub repositories the instance clones over HTTPS with its token. For each repository: copy the fixture tree, `git init` the copy, write `_bmad/_config/manifest.yaml` stating the instance's `BMAD_VERSION`, commit, push `main`.
  - one repository from `fixtures/readiness-repo`;
  - one per member from `fixtures/hub-repo/members/alpha` and `fixtures/hub-repo/members/beta`;
  - the hub, from a copy of `fixtures/hub-repo` without `members/`: run `git submodule add <alpha HTTPS URL> repos/alpha` and the same for beta, so `.gitmodules` and the gitlinks exist before the commit.
- Each repository is registered under a Project the owner creates. Never use the built-in `readiness` project: every finished Run on it is scored as harness readiness and can disable a harness.

Steps:

1. Copy the three examples above into the folder, then `POST /api/v1/templates/reload`.
   Expected: `example-depth-0`, `example-depth-1`, `example-depth-2` in `stored` (in `unchanged` on a repeat).
2. `POST /api/v1/runs/preflight` for each example.
   Inputs: depth 0 and depth 1 on the Project and Repository registered from `fixtures/readiness-repo`, `base_branch: main`, `branch` a fresh name, `spec_folder: specs/readiness`; depth 2 on the Project and the hub Repository, `base_branch: main`, `branch` a fresh name, `initiative_folder: initiatives/demo`.
   Expected: zero `fail` lines and one frame per loop item.
3. Start a Run on each example with the inputs of step 2.
   Expected: status `done`.
4. While the depth-1 Run is `running`, edit its file in the folder and call reload.
   Expected: the backend container id unchanged (`docker compose ps`), the running row's attempt count unchanged, the Run still on its earlier version, then status `done`.
5. Before upgrading, plan a Run on a linked template (for example the stored `initiative-hub`), upgrade, then let it finish.
   Expected: status `done`.
