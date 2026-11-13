---
title: Where things are
kind: page
audience: host
---

Local agent on the host or the user only.

# Where things are

Everything a client has lives in one directory, the one `install.sh` sits in:

| Path | What |
| --- | --- |
| `install.sh` | the only command; `--help` lists every subcommand |
| `.env` | the whole configuration, mode 600, written once and never overwritten |
| `.env.example` | the contract — the reference for any variable, with its explanation inline |
| `release.env` | the release pins (`BMAD_VERSION`, `DBOS_APPLICATION_VERSION`, the harness CLIs); a line in `.env` overrides one |
| `VERSION` | the release these files came from |
| `product-files.json` | the manifest: every product and seed path with its hash |
| `docker-compose.yml` | the three containers, pulling the two images at the tag it carries |
| `setup/`, `bmad/` | the client's setup scripts and `setup/bmad.choice`; the BMAD script |
| `templates/` | the client's workflow files (`*.yaml`); `templates/shipped/` holds the release's examples |
| `kit/` | the bootstrap template, the MCP templates and `kit/install.sh`, which plugs a project repository into the instance |
| `backups/`, `diagnostics/`, `logs/`, `.upgrade/` | the `pg_dump`s of `upgrade`, `diagnose` reports, setup logs, what an upgrade staged and replaced |

Each path is product (replaced by `upgrade`), seed (written only when absent) or client (the
product never reads or writes it, `.env` apart): the table is in `README.md` § Which file is
whose. An LLM platform is not part of the folder: the product neither ships nor manages one.
