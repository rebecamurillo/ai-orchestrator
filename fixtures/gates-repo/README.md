# gates fixture

The repository Epic 6's end-to-end scenarios drive a Run against (SPEC CAP-1, CAP-8). It is
the readiness fixture's sibling and has the same shape — a spec folder, a `stories.yaml`, a
one-line quality gate — with one addition: `.fake-harness/`, which scripts what the `fake`
harness does on each dispatch, so a whole dev loop (`blocked` → *Answer* → `done`) can be
walked deterministically, in seconds, with no model and no spend.

`check.sh` is the whole quality gate: it exits 0 while `GATE_OK` holds anything but `0`.
`GATE_OK` is committed holding `1`, because `epic@1`'s `baseline` row runs the gate *before*
the first story and fails the Run if it does not pass. A scenario that writes `0` into it is
how a test makes `verify` fail.

`check-spec.sh` is the same rule over `specs/gates/GATE_OK` — the same file, inside the spec
folder. It exists because `PUT /runs/{id}/files` is scoped to the Run's own `spec_folder`
(story 6-3), so a gate file at the repository root is one an Operator can never repair
through the product. UJ-3's scenario C (story 6-8) needs exactly that repair, so it registers
its Repository with `quality_gate_command: sh check-spec.sh`. Which gate a Run uses is a
Repository setting, so the two coexist and no existing suite changes.

`specs/gates/stories.yaml` holds three stories, one per gate this epic is about: `1` is the
plain one an Answer resumes, `2` carries `spec_checkpoint: true`, and `3` carries
`done_checkpoint: true`.

`.fake-harness/{story_id}/attempt-{k}.yaml` is read on the k-th dispatch of that story in a
worktree, falling back to `.fake-harness/{story_id}/default.yaml`. The schema is
`backend-api/src/orchestrator/infrastructure/harness/fake/scenario.py`, which is also the
only thing that reads these files. Beside `story_file:`, `files:`, `commit:`, `exit_code:`,
`sleep_seconds:`, `echo_prompt:` and `usage:` it carries `delete: [paths]` — worktree-relative
files the dispatch removes before it writes anything, which is how a scenario makes a quality
gate fail rather than merely disagree.

Nothing here is edited by hand between runs: `backend-api/tests/e2e/helpers/gates_fixture.py`
copies this directory into a scratch tree, writes a `_bmad/_config/manifest.yaml` stating the
instance's own `BMAD_VERSION`, and pushes the result to a bare origin the backend clones
from. This directory is never edited in place.
