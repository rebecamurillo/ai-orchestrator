---
id: SPEC-hub-alpha-epic
companions: []
---

# Alpha epic

One Story, one member repository. Nothing here is a real requirement: the point is to give
the hub-Run e2e journey (story H5) a Story frame inside `repos/alpha` to build, verify and
commit, entirely separately from the hub's own spec artifacts.

## Capabilities

- **CAP-1** `src/alpha_feature.py` exists inside `repos/alpha`, written by the one Story.
  **success:** `sh check.sh` exits 0 inside `repos/alpha`, and the file is on that
  submodule's own branch.
