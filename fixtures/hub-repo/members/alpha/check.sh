#!/bin/sh
# alpha member's one quality gate (SPEC CAP-1, story H5): pass while GATE_OK says so — the
# same rule `fixtures/gates-repo/check.sh` uses. Run twice per Story by
# `initiative-hub-epic@1` (once as `baseline`, once as the Story's own `verify`), so it has
# to be true of a submodule nobody has touched yet, which is why GATE_OK is committed
# holding `1`.
set -eu

if [ -f GATE_OK ] && [ "$(head -n 1 GATE_OK)" != "0" ]; then
  exit 0
fi
exit 1
