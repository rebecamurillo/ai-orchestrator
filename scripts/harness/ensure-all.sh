#!/usr/bin/env bash
# Container start: reconcile each harness CLI with its pin. A harness whose pin cannot be
# installed is refused until the next start (its probe reports `cli not at pinned version`);
# the start itself always continues, because an exit here would let `restart: always` turn
# one failed npm install into a retry loop (hard rule 7).
set -uo pipefail
dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for name in claude codex opencode; do
  if ! "${dir}/${name}.sh" ensure; then
    printf '[harness:%s] refused until the next start\n' "$name" >&2
  fi
done
exit 0
