#!/bin/sh
# The gates fixture's second quality gate (SPEC CAP-8): the same rule as `check.sh`, over a
# file that lives *inside* the spec folder.
#
# `check.sh` reads `GATE_OK` at the repository root, and `PUT /runs/{id}/files` is scoped to
# the Run's own `spec_folder` (story 6-3) — so a root gate file is one an Operator can never
# repair through the product. UJ-3's scenario C has the Operator do exactly that: a scripted
# dispatch deletes `specs/gates/GATE_OK`, `verify` fails twice, and the repair is a real
# `PUT` inside the spec folder before the skip. A Repository registered with
# `quality_gate_command: sh check-spec.sh` is what selects this gate; every other suite keeps
# `sh check.sh` and is unaffected by that deletion.
set -eu

if [ -f specs/gates/GATE_OK ] && [ "$(head -n 1 specs/gates/GATE_OK)" != "0" ]; then
  exit 0
fi
exit 1
