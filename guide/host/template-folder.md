---
title: Editing the workflow templates
kind: procedure
audience: host
readme: template-folder
---

Local agent on the host or the user only.

The shipped templates are a starting point, not a fixed part of the product. Five single
files ship — `staged-initiative-hub` and `staged-initiative-repo` (three agent sessions per
story: plan, implement, review, each on its own model), `repo-init`, `agent-smoke` and the
off-menu `harness-readiness` — and none calls another template. The format, with three
working examples, is in `templates/README.md`.

Your own templates live in the folder `./templates` next to `docker-compose.yml`, mounted
read-only into the backend at `/app/operator-templates` (`OPERATOR_TEMPLATES_DIR`). The
folder is read at start-up and on `POST /api/v1/templates/reload`; the answer lists what was
`stored`, `unchanged`, `refused` and `not_in_folder`. Editing at `/templates` in the web UI
still works: open a template and a version, edit the YAML, **Validate**, and **Save as
v{n+1}**. A saved version never changes.

When the folder holds a file named after a template, edit the file: a version saved on the instance is superseded by the file's content as the next version at the next reload or start-up, and stays listed.

A save or a reload applies to Runs planned after it: a Run that is already planned, queued or
running keeps the tree it was planned from.

An upgrade that ships a changed template adds a new version of it on first boot and never
overwrites or removes the versions you saved. A changed shipped file lands as a new version,
and a folder file of that name then wins again at the next reload or start-up.


Upgrading from 1.0.0-beta.3: the staged pieces `staged-hub-epic`, `staged-hub-story`,
`staged-epic` and `staged-story` are no longer shipped or called — `staged-initiative-hub` and
`staged-initiative-repo` are single files. A version you saved of one of those pieces stays
listed but no Run reaches it any more; re-apply its change inside the single file, as a folder
file or a web save. A folder from before this release has no `product-files.json` and is
migrated (§ Migrating an existing folder), which brings the `./templates` mount and its `.env`
values with the new `docker-compose.yml` and `.env.example`.

What you can change — step kinds, inputs, loops, checkpoints, a model or a timeout per step,
the prompts agents are sent — and the same edit loop over the API are in
the guide page `workflows/customize`, which a project's coding agent reads through the
instance (`read_guide`), so it can propose and validate a template change for
you; it saves only on your go-ahead.

A template does not decide which shell commands an agent may run. That is
`CLAUDE_ALLOWED_TOOLS` in `.env`. The shipped value allows `Bash` whole — the container is
the sandbox, and `git push` stays denied by the harness adapter — so an agent is never
parked on a denied package manager or test runner. An install that narrows it to command
families (`Bash(yarn *)`, `Bash(npx *)`, …) must list every tool its repositories use, and
a change needs `./install.sh start`.
