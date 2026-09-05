#!/bin/sh
# git asks for a credential through this program (GIT_ASKPASS); the answer is the token the
# adapter put in one private variable, and nothing else. It is never on a command line,
# never in a URL and never in a git config, so no other process on this host can read it.
printf '%s\n' "${ORCHESTRATOR_GIT_TOKEN}"
