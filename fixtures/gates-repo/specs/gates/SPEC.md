---
id: SPEC-gates-fixture
companions: []
---

# Gates fixture

Three stories, one quality-gate command, and a scripted agent. Nothing here is a real
requirement: the point of each capability is to give an Epic 6 scenario a Story frame to
stop in, so the human gate that resumes it can be proven end to end (SPEC CAP-8).

## Capabilities

- **CAP-1** `NOTIFY.md` exists at the repository root. The Story that writes it blocks on
  its first dispatch, and an Operator's Answer is what gets it written.
  **success:** `sh check.sh` exits 0 and `NOTIFY.md` is on the branch.
- **CAP-2** `PLAN.md` exists at the repository root, written by a Story that stops at its
  spec checkpoint first. **success:** `sh check.sh` exits 0 with `PLAN.md` on the branch.
- **CAP-3** `SHIP.md` exists at the repository root, written by the last Story, which the
  epic pauses after. **success:** `sh check.sh` exits 0 with `SHIP.md` on the branch.
