---
title: Setup scripts and BMAD
kind: procedure
audience: host
readme: setup-and-bmad
---

Local agent on the host or the user only.

`setup/` is yours. `install`, `upgrade` and `setup` run, under the instance hold, in this order.

1. `install.sh` makes `logs/setup` mode 1777 and runs `scripts/setup/prepare.sh` in a one-shot
   `agent` container of the backend-api image. It creates every harness asset folder and
   `.orchestrator` under the agent home, and needs no running backend-api. A failure is a
   warning: setup continues.
2. The one-shot setup container runs five phases: BMAD (when `setup/bmad.choice` reads
   `installed`); each executable `setup/*.sh` directly under `setup/` in name order; the operator
   skills of the image; the fourth phase only counts each harness's skills, for the record
   (`catalog.log` and the record's `catalog` counts); and the record itself.
3. After the setup service, when backend-api is running and the command is not `upgrade`,
   `install.sh` runs each harness script's `catalog` verb inside backend-api
   (`docker compose exec`), so the catalog changes with no restart. A failure is a warning:
   pre-flight reads the previous catalog until the next start. With backend-api stopped, its
   next start writes the catalogs; an `upgrade` recreates backend-api as its own step, and that
   start rewrites them.

A script sees the harness asset folders under `HOME` and nothing else — no secret, no login, no
database; `setup/README.md` has what it gets, the clash rule and `examples/copy-folder.sh`. The
record is `.orchestrator/setup-run.json` in the agent home; the logs are `logs/setup/{timestamp}/`.
No command restarts backend-api.

- `./install.sh setup` runs it now. Exit 0: every phase passed; 2: a script failed or the
  record is not ok; 3: refused, a step is working; 1: failed.
- `./install.sh setup --reset` first empties the harness asset folders and BMAD's record,
  then runs every phase. The harness logins are not in them and are kept.
- `./install.sh bmad remove` writes `removed` to `setup/bmad.choice` and runs setup: BMAD's
  skills are deleted and stay out through every later install and upgrade.
- `./install.sh bmad install` writes `installed` and runs setup; it is also how to restore
  BMAD after a remove.
- `./install.sh install --no-bmad` writes `removed` before the first setup.

### For the host agent

`setup/*.sh` are the client's scripts; setup runs at `install` and `upgrade` and on demand, under
the instance hold. A skill that a script changes under a `bmad-` name is restored and the script
reported failed: tell the user, do not edit around it.
