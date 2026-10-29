---
title: 'Harness CLI upgrades honour the pin and survive a redeploy'
type: 'feature'
created: '2026-10-22'
status: 'done'
review_loop_iteration: 2
baseline_commit: '0bcdfb765d4c5f493e8c63897cdd1709f3bbffd0'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Editing `CLAUDE_CODE_VERSION` (or `CODEX_VERSION`, `OPENCODE_VERSION`) in `.env` changes nothing: the image build never sees `.env`, so a rebuild reinstalls the script default and the probe refuses the harness with `cli not at pinned version`; a manual `npm install -g` lands in the container layer and is lost on recreate; a host running pulled images has no upgrade path short of a new release.

**Approach:** The pins become build arguments; the harness CLIs move to their own npm prefix `/opt/harness-cli` on the named volume `harness-bin`; each harness script gains an `ensure` verb that installs the pinned version at container start only when the installed one differs; `install.sh harness <name> --version X` edits the pin and recreates backend-api; `install.sh upgrade` rewrites the three pins to the new release's values. Operator decisions 2026-10-22 and 2026-10-29: A + B; **a pin that cannot be installed never stops the container** — that harness alone is refused (the probe already says `cli not at pinned version`) and nothing retries until the next start (hard rule 7: the restart policy must never become a retry loop); **upgrade rewrites the pins and prints each change**. The Operator amends AD-10 and the root `AGENTS.md` sentence ("Harness CLIs are installed in the backend image at the versions pinned in `.env.example`") to "installed in the image and reconciled against the `*_VERSION` pins at container start, on the `harness-bin` volume".

## Boundaries & Constraints

**Always:** `.env` is the single source of a pin (AD-20); the script default is the fallback and equals `.env.example`. `ensure` makes no network call when the installed version already matches. `ensure` reads no gateway or Langfuse variable. One `npm install -g` line serves `install` and `ensure`. A pin change is applied by **recreating** backend-api (`compose up -d`), never `compose restart`, which keeps the creation-time environment. No credential becomes an `ARG` or `ENV`. Docs state mechanisms, never congratulate (NFR-8). `sync_pins`, `seed_harnesses` and the probe verb are untouched.

**Ask First:** Any change to `sync_pins`, `seed_harnesses`, the probe verb, or a test outside the modules named in the Code Map. Any new contract variable.

**Never:** Install a CLI per Run. Retry a failed `npm install` within one start, or let a failure exit the container (which `restart: always` would turn into a loop). Edit `AGENTS.md` or the spine. Write a version literal anywhere but the scripts' defaults and the two `.env.example` files. Touch a running stack from a test or gate (hard rule 9): `install.sh` tests use the docker and curl shims.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Pin unchanged at start | installed == pin | `ensure` logs `claude 2.1.258 at pin`, runs no npm | N/A |
| Pin raised at start | installed 2.1.258, pin 2.1.260 | one `npm install -g` at the pin, logs `claude 2.1.258 → 2.1.260`, re-reads the version and logs it at pin | N/A |
| Pin cannot be installed | npm fails, or the re-read version still differs | `ensure` exits non-zero naming harness and both versions; the start stage logs `claude refused until the next start` and the container **continues** to `configure`, migrations and serving; the probe reports `cli not at pinned version` | no second npm call in that start |
| CLI missing | `command -v` fails | treated as differs: install at pin | as above |
| Pin not a plain version | `latest`, `^2.1`, empty | `ensure` refuses without calling npm, names the variable | harness refused as above |
| `--version` output noisy | CLI prints a warning line too | only the first stdout line is parsed | N/A |
| `install.sh harness claude --version 2.1.260` | `.env` present, backend-api up | writes the pin (keeps trailing comment), asks, then recreates backend-api with `--wait`, prints the harness row and the readiness command | backend-api down → pin written, says `./install.sh start` applies it, exit 0 |
| `--version` misuse | trailing with no value; value not a version; with `--subscription`/`--api-key`; with a command other than `harness`; unknown harness | `die` naming the problem (the three harness names for an unknown one), `.env` unchanged | exit 1 |
| `install.sh upgrade --tag N` | `.env` pins differ from release N's | after pulling N, reads the three pins from the new image's `/app/deploy/.env.example`, writes each differing one, prints `CLAUDE_CODE_VERSION old → new`, then starts the stack | pins unreadable from the image → `die` before writing anything, naming the image |
| `docker compose build` | raised pin in `.env` | image installs that version | `.env` without it → script default |

</frozen-after-approval>

## Code Map

- `_bmad-output/implementation-artifacts/spec-harness-upgrade-survives-redeploy.attempt-2.patch` -- the second implementation (reverted after review loop 2). Apply it as the starting point (`git apply`, then restore `scripts/harness/ensure-all.sh` from the patch as an executable new file), then change only what loop 2 below adds. See Spec Change Log.
- `scripts/harness/_common.sh` -- `npm_install_cli` (the single npm line; now `npm install -g --prefix "${HARNESS_PREFIX}"`, constant `HARNESS_PREFIX=/opt/harness-cli`) and `ensure_cli_at_pin`: validate pin `^[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$`; parse first stdout line only; after npm, re-read and fail if still off-pin.
- `scripts/harness/{claude,codex,opencode}.sh` -- `installed_version` uses stdout only and `head -1` (`claude --version 2>/dev/null | head -1 | awk '{print $1}'`; codex/opencode `$NF`). Leave the probe's own parsing untouched.
- `scripts/harness/ensure-all.sh` (new, executable) -- runs `ensure` for the three harnesses in its own directory; on a failure logs `[harness:<name>] refused until the next start` and continues; always exits 0. Testable by copying it beside stub `<name>.sh` scripts.
- `backend-api/docker-entrypoint.sh` -- calls `scripts/harness/ensure-all.sh` before the `configure` loop; header order updated.
- `backend-api/Dockerfile` -- valueless `ARG`s before the install step (as attempt 1). `mkdir -p /opt/harness-cli` owned by `agent`; `PATH` puts `/opt/harness-cli/bin` before `/opt/npm-global/bin`. Corepack shims stay in `/opt/npm-global` (image layer, never on the volume).
- `docker-compose.yml`, `deploy/docker-compose.yml` -- `harness-bin:/opt/harness-cli`; dev `build.args` as bare names (attempt 1).
- `deploy/install.sh` -- argument loop: `--version` only valid with `harness`, value must not start with `-`; `cmd_harness` version branch and subscription branch both apply via `compose up -d --wait --wait-timeout 600 backend-api` instead of `compose restart`; `cmd_upgrade`: `docker pull <backend image>:<tag>` (skipped with `--no-pull`), `docker run --rm --entrypoint cat <image>:<tag> /app/deploy/.env.example`, take the three pins, `die` if any is missing, then `set_var` IMAGE_TAG and each differing pin with an `old → new` line, then `stack_up`. The docker shim in `test_install_admin.py` / `test_deploy_install.py` must answer that `run`.
- `scripts/push-images.sh` -- when a pin is unset in the environment, read it from `${root}/.env` if present (that one line only, never source the file), else omit the `--build-arg`. Header usage line drops `set -a; . ./.env`.
- `.github/workflows/release.yml` -- pins step and `build-args` as attempt 1.
- Docs: `README.md`, `deploy/README.md`, `.env.example`, `deploy/.env.example`, `deploy/kit/skills/orchestrator-admin/SKILL.md`, `references/runbooks.md` -- apply = recreate (`docker compose up -d backend-api` / `./install.sh start`); a failed pin refuses only that harness; upgrade moves the pins; registry access is needed at start only when a pin changed; `docker volume rm <project>_harness-bin` re-seeds from the image. Short lines.

### Loop 2 additions (apply on top of attempt 2)

- **Image copy, outside the volume.** `backend-api/Dockerfile`: `install` writes the CLIs to `/opt/harness-image` (constant `HARNESS_IMAGE_PREFIX` in `_common.sh`; never mounted, owned by `agent`), then copies that tree into `/opt/harness-cli` so a fresh volume is still seeded. `ensure_cli_at_pin` order: (1) if `${HARNESS_IMAGE_PREFIX}/bin/<cli> --version` equals the pin, replace the volume's copy of that package and bin link from the image copy (local copy, no network) and log `<name> <pin> from image`; this runs on every start, so a changed or tampered volume copy is restored; (2) else if `${HARNESS_PREFIX}/bin/<cli> --version` equals the pin, log `at pin`; (3) else npm. Versions are read from those absolute paths, never the first `PATH` match.
- **npm, bounded and atomic.** `npm_install_cli` installs into a fresh staging prefix under `${HARNESS_PREFIX}/.staging`, with `--fetch-retries=0 --fetch-timeout=60000`, the whole call under `timeout 300`; only on success and a matching re-read is the package and its bin link moved into `${HARNESS_PREFIX}`. On failure the staging dir is removed and the previous copy is untouched. `--version` reads run under `timeout 30`. `install()` (image build) refuses a non-plain pin before npm.
- **`deploy/install.sh`.**
  - `read_release_pins` uses `docker run --rm --pull never …` when `--no-pull` is set. If the release image has no `/app/deploy/.env.example`, it warns and leaves the pins unchanged (rollback to an older release stays possible).
  - Before the confirmation prompt, `upgrade` prints the pin changes it will make, marking any downgrade, and checks that `.env` declares all three pins. A missing one → `die` before the backup or any write.
  - `--version` given twice → `die`.
  - When `recreate_backend` fails, warn with `./install.sh logs` and return non-zero after saying the pin is written.
  - After a recreate, the printed row is expected to read `disabled` until readiness is re-run, because `sync_pins` resets it. Say that, don't imply `enabled`.
- **`scripts/push-images.sh` / `release.yml`.** Strip any `#` comment (any whitespace before it) and surrounding quotes, take the first matching line, and validate against the plain-version pattern before passing `--build-arg`. Release fails on a non-plain pin.
- **Docs.**
  - `README.md` volume reset: stop the stack first, and only with the Operator's go-ahead (hard rule 9). Match `deploy/README.md` and the runbook.
  - `.env.example` / `deploy/.env.example`: `BMAD_VERSION` is baked in, not reconciled.
  - Say `harness-bin` is not backed up and `uninstall` removes it.
  - Rollback runbook: a rollback rewrites the pins to the older release's values.
- **Tests (add, red first).**
  - `ensure` copies from the image when the image copy is at the pin, with no npm.
  - A tampered volume copy is restored from the image.
  - An npm failure leaves the previous copy in place and removes staging.
  - The npm argv carries `--fetch-retries=0`.
  - `upgrade --no-pull` uses `--pull never`.
  - An image without `.env.example` leaves the pins with a warning.
  - A missing pin declaration dies before any write.
  - The planned pin changes print before the prompt.
  - `--version` twice is refused.
  - A declined recreate prompt runs no `up` and says `Not recreated`, on both the version and subscription paths.
  - `--version=9.8.7` writes the pin.
  - `push-images.sh` with a one-space comment and with a quoted value.
  - The plain-version pattern is the same in `deploy/install.sh` and `_common.sh` (text comparison).

## Tasks & Acceptance

**Execution:**
- [x] `backend-api/tests/unit/test_harness_scripts.py` -- attempt-1 tests plus: noisy `--version`; bad pin format runs no npm; post-install re-read mismatch fails; `ensure-all.sh` with one failing stub exits 0, runs the other two, logs the refusal -- red first
- [x] `backend-api/tests/unit/test_dockerfiles.py` -- attempt-1 tests, with the ordering test asserting `ensure-all.sh` precedes the first `configure` in code (not substring); harness prefix on PATH before `/opt/npm-global/bin` -- red first
- [x] `backend-api/tests/unit/test_deploy_compose.py` -- `harness-bin` at `/opt/harness-cli` in both compose files -- red first
- [x] `backend-api/tests/unit/test_install_admin.py` -- matrix rows for `--version` (trailing `--version` as last argv; `start --version`), `up -d` not `restart`, subscription disabled-row hint; revise the subscription test's `restart` assertion citing this spec and 2026-10-29 -- red first
- [x] `backend-api/tests/unit/test_deploy_install.py` (or `test_install_admin.py`) -- upgrade rewrites differing pins with `old → new`, leaves equal ones, dies before writing when the image yields none -- red first
- [x] `backend-api/tests/unit/test_push_images.py` -- pins from env and from `.env` reach `--build-arg`; no other `.env` value appears in the docker log -- red first
- [x] `backend-api/tests/unit/test_deploy_env_contract.py` -- the three pins have equal values in root and deploy `.env.example` -- red first
- [x] implementation files per Code Map, including Loop 2 additions
- [x] Loop 2 tests listed in the Code Map -- red first
- [x] comments: none narrating the change (AGENTS.md "Comments earn their place")

**Acceptance Criteria:**
- Given a raised pin in `.env`, when backend-api is recreated, then `claude --version` prints the pin and the probe no longer reports `cli not at pinned version`; recreating again keeps it.
- Given an uninstallable pin, when backend-api starts, then `/healthz` answers, the other harnesses work, that harness's probe reports `cli not at pinned version`, and the log shows exactly one npm attempt.
- Given `make lint` and `make test`, then both are green with no threshold touched.

## Spec Change Log

- **Review loop 1 (2026-10-29).** Findings: fail-closed `ensure` plus `restart: always` made an unbounded npm retry loop; `install.sh upgrade` left old pins while the volume hid the new image's CLIs (and could downgrade a fresh volume); `compose restart` never re-reads `.env`; the volume at `/opt/npm-global` froze the corepack shims; `--version` parsing merged stderr and took every line; no post-install re-check; no pin-format check; global `--version` flag; weak ordering test; untested push-images build args and entrypoint stop. Amended: intent (fail-soft, upgrade rewrites pins, Operator 2026-10-29), Code Map, matrix, tasks. Avoids: crash loop, silent downgrade, a pin edit that never applies. **KEEP from attempt 1:** valueless ARGs placed just before the install step; bare-name compose `build.args` (an `${VAR:-}` form breaks `test_compose_fails_closed.py`); `npm_install_cli` shared line; `print_harness_row` helper; release.yml pins step; confirmation before recreate with `--yes`; the shim-based test style; `STARTUP_ORDER` revision with its dated citation.

- **Review loop 2 (2026-10-29).** Findings: the `harness-bin` volume hid each new image's baked CLIs, so every release that raised a pin needed the npm registry at start (air-gap, `--no-pull`, rollback) and a tampered volume copy survived recreates; npm's own fetch retries contradicted hard rule 7; an unbounded npm or `--version` could outlast the healthcheck; an interrupted npm could leave a broken CLI; `upgrade --no-pull` could pull implicitly, could half-write `.env`, and downgraded hand-raised pins without warning before the prompt; push-images/release pin parsing accepted comments and quotes; untested decline, `--version=X`, and duplicate flag. Amended: Code Map (Loop 2 additions), tasks. Avoids: registry-dependent upgrades, persistent tampering, hidden retries, half-written `.env`. **KEEP from attempt 2:** everything in attempt 1's KEEP list; `ensure-all.sh` and its stub-script tests; `/opt/harness-cli` prefix ahead of `/opt/npm-global/bin` on PATH; recreate via `compose up -d --wait --wait-timeout 600 backend-api` on both harness paths; `read_release_pins` from the image's `/app/deploy/.env.example`; `push-images.sh` reading only the pin lines; root/deploy pin agreement test; the revised subscription test citing this spec.

## Design Notes

Fail-soft is safe because the gate already exists: the probe compares `--version` with the pin and refuses the harness, and `create_run` reads the probe. `ensure-all.sh` exists so the "continue on failure" behaviour is executable in a unit test rather than a regex over the entrypoint.

A dedicated prefix keeps the volume's scope to exactly the three CLIs. `NPM_CONFIG_PREFIX` stays `/opt/npm-global` for anything an agent installs during a Run.

## Verification

**Commands:**
- `make lint` -- green
- `make test` -- green, new tests included
- `make e2e` -- green (disposable `aio-e2e` stack)

**Manual checks (Operator's own stack, hard rule 9):**
- Raise `CLAUDE_CODE_VERSION`, `docker compose up -d backend-api`, then `docker compose exec backend-api claude --version` prints the pin; set an impossible pin and confirm the UI stays up with claude refused.

## Suggested Review Order

**Start-up reconcile: image copy, volume, npm**

- Entry point: image copy first, volume second, one bounded npm last.
  [`_common.sh:137`](../../scripts/harness/_common.sh#L137)

- Aside-then-swap so an interrupted copy never leaves the volume empty.
  [`_common.sh:108`](../../scripts/harness/_common.sh#L108)

- One npm line: staged prefix, no fetch retries, two-minute bound.
  [`_common.sh:71`](../../scripts/harness/_common.sh#L71)

- A failing harness is refused; the container keeps starting (no restart loop).
  [`ensure-all.sh:9`](../../scripts/harness/ensure-all.sh#L9)

- Runs before configure, migrations and serving.
  [`docker-entrypoint.sh:38`](../../backend-api/docker-entrypoint.sh#L38)

**Image and volume layout**

- Pins as valueless build args; script default stays the fallback.
  [`Dockerfile:154`](../../backend-api/Dockerfile#L154)

- Harness prefix ahead of npm-global; image copy on no PATH.
  [`Dockerfile:48`](../../backend-api/Dockerfile#L48)

- harness-bin mount and the longer start allowance.
  [`deploy/docker-compose.yml:82`](../../deploy/docker-compose.yml#L82)

**Operator commands**

- Pin, recreate, then print that harness's own start-up lines.
  [`install.sh:978`](../../deploy/install.sh#L978)

- Upgrade reads the release's pins from its image before asking.
  [`install.sh:810`](../../deploy/install.sh#L810)

- Planned pin changes, with downgrades marked.
  [`install.sh:848`](../../deploy/install.sh#L848)

**Publishing**

- Published images carry only the contract's pins.
  [`push-images.sh:38`](../../scripts/push-images.sh#L38)

- Release reads and validates the same pins.
  [`release.yml:142`](../../.github/workflows/release.yml#L142)

**Peripherals**

- ensure behaviour against scratch prefixes and shims.
  [`test_harness_scripts.py:397`](../../backend-api/tests/unit/test_harness_scripts.py#L397)

- install.sh harness and upgrade cases through the docker shim.
  [`test_install_admin.py:648`](../../backend-api/tests/unit/test_install_admin.py#L648)

- Operator runbook for a harness upgrade.
  [`runbooks.md:145`](../../deploy/kit/skills/orchestrator-admin/references/runbooks.md#L145)
