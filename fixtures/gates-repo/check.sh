#!/bin/sh
# The gates fixture's one quality gate (SPEC CAP-1): pass while GATE_OK says so.
#
# `epic@1` runs this twice per story — once as the epic's `baseline` and once as the story's
# `verify` — so it has to be true of a repository nobody has touched yet, which is why
# GATE_OK is committed holding `1`. A scenario that writes `0` into it is how an end-to-end
# test makes a verify row fail without changing this script.
set -eu

if [ -f GATE_OK ] && [ "$(head -n 1 GATE_OK)" != "0" ]; then
  exit 0
fi
exit 1
