#!/bin/sh
# The readiness fixture's one quality gate (SPEC CAP-8): pass once HELLO.md exists at the
# repository root and contains the word "hello".
set -eu

if [ -f HELLO.md ] && grep -q "hello" HELLO.md; then
  exit 0
fi
exit 1
