# readiness fixture

A minimal project the orchestrator uses to prove a coding-agent harness before offering it
to an Operator (SPEC CAP-8). `check.sh` is the whole quality gate: it exits 0 once
`HELLO.md` exists at the repository root and contains the word `hello`, and 1 otherwise.

This repository is never pushed anywhere real. `scripts/readiness_fixture.sh` copies these
files into a scratch working tree, installs `_bmad/` at the image's pinned `BMAD_VERSION`,
and pushes the result to a local bare origin under `$WORK_DIR/readiness/origin.git` — the
one remote a readiness Run ever clones from (`POST /harnesses/{name}/readiness`).

`specs/readiness/` holds the one Story a readiness Run plans: create `HELLO.md`. Nothing
here is edited by hand between runs; the seeding script treats this directory as read-only
and copies it, never editing it in place.
