---
title: Trust
kind: page
audience: any
---

# Trust

The backend container runs harness CLIs as the user `agent` with passwordless sudo, and
without `cap_drop` — deliberately, so an agent can `apt-get install` what a target
repository's install script needs. A Run executes code from the repositories you
register. Register only repositories you trust as much as this machine.

`VERIFY_DOCKER=true` widens that. The `docker` sidecar is privileged, and anything that can
reach its daemon — every Run's commands and every coding agent, by design — can start a
privileged container or mount the host filesystem of the machine the daemon runs on: root
in Docker Desktop's VM, root on a Linux host running Docker Engine. What it does not give is
this stack's own daemon: the sidecar is a separate dockerd with its own containers, images
and networks, so a Run cannot see, stop or read the orchestrator's containers, its database
or its `.env` through it, and nothing it publishes leaves backend-api's network namespace.
Containers it starts can still reach the network, and the rest of the compose network
(`postgres`, `web-client`) can reach the ports they publish on backend-api. Turn it on only
for repositories you would let run `docker` on that machine, and turn it off when none
needs it.
