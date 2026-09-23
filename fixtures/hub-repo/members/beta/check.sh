#!/bin/sh
# beta member's one quality gate (SPEC CAP-1, story H5) — the same rule
# `fixtures/hub-repo/members/alpha/check.sh` and `fixtures/gates-repo/check.sh` use.
set -eu

if [ -f GATE_OK ] && [ "$(head -n 1 GATE_OK)" != "0" ]; then
  exit 0
fi
exit 1
