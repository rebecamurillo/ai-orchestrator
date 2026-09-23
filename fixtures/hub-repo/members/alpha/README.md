# alpha member fixture

One of `fixtures/hub-repo/`'s two member submodules (story H5). `check.sh` is the whole
quality gate `alpha-epic`'s own `test`/`quality_gate` commands run: it exits 0 while
`GATE_OK` holds anything but `0`, the same rule `fixtures/gates-repo/check.sh` uses.

`tests/smoke.test.sh` is committed in this seed on purpose: it is what makes it one of
AD-17's frozen test files by the time the epic's own Story-1 `build` row first dispatches, so
`tests/e2e/helpers/hub_fixture.py`'s `poison_alpha` variant — which edits this same file
instead of leaving it alone — makes `commit-guard` park `protected_path` naming
`repos/alpha/tests/smoke.test.sh`.
