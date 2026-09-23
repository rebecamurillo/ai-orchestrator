---
id: SPEC-hub-beta-epic
companions: []
---

# Beta epic

One Story, one member repository — `beta-epic`'s own sibling of `alpha-epic`, proving the
hub-Run e2e journey (story H5) walks a *second* epic sequentially, inside a *different*
submodule, after the first one's `done_checkpoint` is continued.

## Capabilities

- **CAP-1** `src/beta_feature.py` exists inside `repos/beta`, written by the one Story.
  **success:** `sh check.sh` exits 0 inside `repos/beta`, and the file is on that
  submodule's own branch.
