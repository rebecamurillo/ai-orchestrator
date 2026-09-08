---
id: SPEC-readiness-fixture
companions: []
---

# Readiness fixture

The smallest possible kernel: one capability, one story, one quality-gate command. A
readiness Run (SPEC CAP-8) proves a harness can read this file, write the file it names,
and leave the repository at a commit `check.sh` accepts.

## Capabilities

- **CAP-1** A file `HELLO.md` exists at the repository root and contains the word `hello`.
  **success:** `sh check.sh` exits 0.
