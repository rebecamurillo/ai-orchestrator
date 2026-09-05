#!/usr/bin/env bash
# scripts/check_e2e_target.sh — refuse to run the e2e gate against a database that is not
# the gate's own.
#
# `tests/e2e` writes and never cleans up: `test_projects.py` says so in its own docstring,
# `test_schemathesis.py` fuzzes every published operation while authenticated, and
# `test_clone_check.py` leaves bare fixture repositories and base clones behind. That is
# correct for a suite that must pass twice against the same stack — and ruinous when the
# stack is the one you develop against.
#
# So the gate names the only database it may write to. `make e2e` builds a stack whose
# database is `orchestrator_e2e` and passes it here; CI does the same. Anything else refuses,
# before pytest opens a connection.
#
# `E2E_ALLOW_SHARED_STACK=1` is the deliberate override — for the case where you *want* the
# suite pointed at a stack you already have and accept what it leaves there. It warns; it
# does not go quiet.
set -euo pipefail

url="${DATABASE_URL:-}"

if [[ -z "$url" ]]; then
	cat >&2 <<'MSG'
DATABASE_URL is not set: the e2e gate constructs Settings in the test process, so the whole
contract must be exported, and this check has nothing to read. Run `make e2e`, which builds
the gate's own stack and exports it.
MSG
	exit 1
fi

# the database is the last path segment, without a query string; the password never appears
database="${url##*/}"
database="${database%%\?*}"

if [[ "$database" == *_e2e ]]; then
	exit 0
fi

if [[ "${E2E_ALLOW_SHARED_STACK:-}" == "1" ]]; then
	echo "warning: running the e2e suite against database '${database}' — it writes Projects," >&2
	echo "         fixture repositories and base clones there, and deletes none of them" >&2
	exit 0
fi

cat >&2 <<MSG
refusing to run the e2e suite against database '${database}'.

The suite creates Projects, Repositories and clones and never removes them, so it may only
run against a database built for it — one whose name ends in '_e2e'.

  make e2e                       build the aio-e2e stack, run this gate in it, destroy it
  E2E_ALLOW_SHARED_STACK=1 ...   run it here anyway, and keep what it leaves behind
MSG
exit 1
