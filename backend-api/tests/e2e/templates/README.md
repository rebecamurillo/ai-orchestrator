# Test-owned workflow Templates

Every YAML here is a fixture the e2e suite posts to the running stack under a per-run unique
name (`tests/e2e/helpers/templates.py`). None of them is a shipped Template, and no test may
read, run or assert on `templates/*.yaml` at the repository root (Operator ruling, 2026-10-15):
the shipped files are exemplars the Operator edits, reorders and retires freely, and the suite
proves that the parser reads and the walker executes instructions, never a particular workflow.

Tokens: `@NAME@` is the name the fixture is saved under; `@STORY@` / `@EPIC@` name the callee a
`uses: template` row follows. Agent rows dispatch internal skills only (`ia-agents-skills/`),
never BMAD ones — `tests/unit/test_e2e_fixture_templates.py` pins both facts.
