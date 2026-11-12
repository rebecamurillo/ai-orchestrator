---
title: Upgrading
kind: procedure
audience: host
readme: upgrade
---

Local agent on the host or the user only.

```bash
./install.sh upgrade --tag <newer>
```

Run it from this folder, with nothing extracted over it first: `upgrade` takes the release's
files from the target image itself, and a `kit bootstrap | tar x` over this folder would
replace product files outside the hold, with no copy in `previous/`.

`upgrade` prints `running <version> → target <tag>` and refuses a target equal to what is
running. The order is fixed: it extracts the target release's folder from its own image into
`.upgrade/{ts}/staged/`; checks, with nothing written, that no working step runs and, when the
release changes `DBOS_APPLICATION_VERSION`, that no Run is in the engine; asks to continue;
takes the instance hold; takes a `pg_dump` into `backups/`; replaces each product file, the
previous copy moving to `.upgrade/{ts}/previous/`; writes each seed file that is absent; runs
setup; restarts and proves the API. It prints what it will do before it asks, and a report at
the end: `replaced`, `added`, `removed` and `edited` lines, `seed written`, the release pins
it changes, the `.env` overrides of `release.env` (which keep their value) and the Runs that
continue. An example workflow of `templates/shipped/` whose content changed, and whose name
you hold in `templates/`, is listed as `improved:`; a new one as `new:`. Your own files are
never touched.

- `.upgrade/{ts}/staged/` is the release's folder as extracted; `.upgrade/{ts}/previous/`
  holds every product file the upgrade replaced or removed. A product file whose content you
  had edited is listed as `edited` and its copy is in `previous/`.
- **Refusals** print `refused: nothing was changed` and leave the folder as it was. Exit 3:
  a working step runs (or the hold answered 409). Exit 4: the release changes
  `DBOS_APPLICATION_VERSION` and Runs are in the engine — finish or cancel them. Exit 5: the
  folder has no `product-files.json` — follow § Migrating an existing folder. Exit 1: anything
  else failed (the line says what). Exit 0: upgraded.
- **Rollback** is `./install.sh upgrade --tag <older>`, plus restoring the `pg_dump` of
  `backups/` when the newer release migrated the schema: migrations run forward only, so
  running an older release on a migrated database is expected to fail closed. By hand the
  backup is
  `docker compose exec postgres pg_dump -U orchestrator -Fc orchestrator > backup.dump`.
- **`DBOS_APPLICATION_VERSION`** is a release pin in `release.env` and versions the engine's
  durable step sequence. A release that changes it makes every in-flight Run unrecoverable
  under the old value, so `upgrade` refuses with exit 4 while any Run is parked, queued or
  blocked in the engine (a parked `needs_you` Run holds its slot for up to
  `HUMAN_WAIT_SECONDS`, 30 days by default). Never set it in `.env` as routine.
- **Harness CLI versions are release pins** (`CLAUDE_CODE_VERSION`, `CODEX_VERSION`,
  `OPENCODE_VERSION`, `LANGFUSE_OPENCODE_PLUGIN_VERSION`, with `BMAD_VERSION`) in
  `release.env`, read before `.env`: a line in `.env` overrides one, and `doctor` and `upgrade`
  report each override. The upgrade no longer writes pins into `.env`. At every start
  `backend-api` copies the image's CLI onto the `harness-bin` volume (`/opt/harness-cli`) when
  the image's is at the pin, and otherwise runs one `npm install` of the pin there, kept
  across a recreate.
- `./install.sh harness <claude|codex|opencode> --version X` edits `.env` and recreates
  `backend-api`. `docker compose restart` does not apply a pin: it keeps the old environment.
- The registry is needed at start only when a pin differs from the image's. A pin that
  cannot be installed refuses that harness alone (`cli not at pinned version`); the API
  still starts. The logs name the harness and both versions. Nothing retries until the next
  start.
- `harness-bin` is not backed up, and `./install.sh uninstall` removes it. To re-seed it
  from the image, stop the stack and `docker volume rm <project>_harness-bin`; both take
  the instance down, so ask the Operator first.
- `POSTGRES_DB` is fixed after first boot, and the stack supports exactly one
  `backend-api` replica.
- **Two settings an upgrade from a release before 2026-10-12 keeps as they were.** A
  Repository's `test_globs` is now exactly what you list, and an empty list freezes no test
  file; rows saved earlier still hold the former three globs (`tests/**`, `**/*.test.*`,
  `**/*.spec.*`) until you clear them in the Repository form, and every story that edits an
  existing test parks `protected_path` until then. And `CLAUDE_ALLOWED_TOOLS` in your `.env`
  still lists command families where the new default is `Bash` whole — replace the families
  with `Bash` unless you want the narrower list.
- **`VERIFY_DOCKER` is absent from an `.env` written before Docker for Runs**, which means
  off. If you added a `docker` sidecar to `docker-compose.yml` by hand, set
  `VERIFY_DOCKER=true` before the upgrade (`./install.sh start --with-docker` appends it):
  otherwise the first start after it removes that container. A volume named `docker-data`
  is reused as the image cache. A hand-added service the new file no longer declares is left
  as an orphan container — `docker compose up -d --remove-orphans` from this directory
  removes it — and `docker volume rm` removes any volume only it used.

### For the host agent

A refusal prints `refused: nothing was changed`. Report the line, do not work around it. Two
decisions are the user's:

1. **Runs in the engine on a `DBOS_APPLICATION_VERSION` change (exit 4).** They would become
   unrecoverable under the new value. A parked Run cannot be waited out: it holds its slot
   for `HUMAN_WAIT_SECONDS` (30 days). The two honest options are to answer or cancel every
   parked Run, or not to upgrade yet. `DEPLOY.md` §5.1 is the full statement; put the choice
   to the user, do not make it.
2. **Rollback.** `./install.sh upgrade --tag <older>`, plus restoring the `backups/` dump when
   the newer release migrated the schema: migrations run forward only, and an older release on
   a migrated database is expected to fail closed.

Afterwards, the kit in every plugged project is stale — the skills came out of the old image.
From inside each project repository:

```bash
curl -fsSL -H "Authorization: Bearer $ORCHESTRATOR_TOKEN" \
  "$ORCHESTRATOR_BASE_URL/api/v1/kit/install.sh" | bash -s -- --harness claude
```

`--harness` is whatever that project's `.orchestrator/kit.json` records. Then
`./install.sh doctor`, and check the templates — `host/runbooks`, *Template refresh*.
