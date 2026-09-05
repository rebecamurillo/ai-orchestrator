---
status: blocked
---

# Shipped Templates repo-init, story, epic, initiative

## Auto Run Result

Status: blocked
Blocking condition: anchor conflict outside the operator's authorised exception. The brief
(`_bmad-output/planning-artifacts/mvp/epics/epic-03-templates/briefs/3-2-shipped-templates.md`,
"Location (Structural Seed)" and Implementation notes) requires adding `Settings.TEMPLATES_DIR`
to `backend-api/src/orchestrator/infrastructure/settings.py` and a matching
`TEMPLATES_DIR=/app/templates` line to `.env.example` (AD-20). Verified by making the change and
running the suite: this breaks `backend-api/tests/unit/test_settings.py::test_every_backend_variable_is_a_typed_field`,
which asserts `{name.upper() for name in Settings.model_fields} == BACKEND_VARIABLES`, a
hardcoded 25-name frozenset at the top of that file (lines 13-39) that does not include
`TEMPLATES_DIR`. `test_settings.py` is a pre-existing test file — a frozen anchor under
AGENTS.md hard rule 1 — and is not one of the three standing exceptions (not a pending-gate
registry, not a placeholder naming this story as its replacement, not a nondeterministic
assertion). The operator's advance authorisation for this dispatch is explicit and narrow:
"This authorisation extends to `test_env_contract.py` and to nothing else. Every other anchor
is read-only ... If you hit any other anchor conflict, STOP and report blocked with the file
and the assertion — do not work around it, do not relax or skip a test." The two
`test_env_contract.py` assertions the operator did anticipate (lines 59-60, the hardcoded `"25"`
and `"31"` substrings) are a second, separate breakage from the same setting addition and were
not reached because the story halts here first. No implementation, test, or other file was
changed by this run; the experimental edit used to verify the break was reverted before halting
and the working tree is clean.
