# Test Automation Summary — orchestrator-instance-guide / epic-3-bootstrap

Generated: 2026-11-13 (dispatch mode with an empty story id, so it covers the whole epic)
Spec: `initiatives/orchestrator-instance-guide/epic-3-bootstrap/SPEC.md` (path relative to the hub)
Stories: 1–4 (commits `ffcc010`..`ba4a325`)
Previous summary (epic 2): in git history at `acff0e3`.

Framework: the project's own, pytest + httpx in `backend-api/tests/e2e` (`make e2e-api`). The
epic changed no UI, so no Playwright test was added.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_bootstrap.py` (11 tests). The unit suite proves the version
  answer through a test client and the installer against a `curl` stub. This module tests what
  only the running image can show:
  - **CAP-1 / C1:** `GET /api/v1/version` without a bearer gets 401. With one, the answer
    holds a non-empty `app_version`, `bootstrap_contract == 1`, exactly the three `guide`
    addresses, and `kit_version` as a key whose value is `null`. The MCP `version` tool returns
    the same answer as the route. Its description names `refusal-bootstrap-contract`, says to
    continue, and never says to stop on a mismatch. `read_guide` takes one optional `id`. The
    three guide addresses from the answer resolve on this instance (index → a listed page →
    the same text through `guide://{id}`). The page `errors/refusal-bootstrap-contract` is
    served.
  - **CAP-3:** both kit routes require the bearer. The served archive has nothing under
    `skills/` or `bin/` and holds `bootstrap/SKILL.md.tmpl`, `install.sh` and the three `mcp/`
    templates (AC-4). The installer served by `/kit/install.sh` is byte-identical to the
    `install.sh` inside the archive.
  - **CAP-2 (AC-1/AC-3 over the wire):** the served installer is piped into `bash -s --
    --harness all --base-url <stack>/`, as the connect page documents. It runs in `tmp_path`,
    with `HOME`, `CODEX_HOME` and `XDG_CONFIG_HOME` there too. Checked:
    - it fetches the kit from this instance's `/kit/archive` and its probe reports
      `bootstrap_contract 1`;
    - all three MCP configurations parse (`json`, `tomllib`), point at `<stack>/mcp` (trailing
      `/` stripped) and refer to the token variable by name;
    - `bootstrap.json` holds contract 1, and each skill folder holds exactly `SKILL.md`;
    - no written file and no output contains the token value, no written file contains the
      instance's `app_version`, and no placeholder is left unsubstituted.

    The release check uses the release the instance actually serves, not the AD-33 regex,
    because the stack address (`127.0.0.1:<port>`) matches that regex (SPEC § Constraints).
    The regex check stays in the unit suite, which renders with host names.

No assertion reads page prose or pins which pages or template steps ship (member hard rule 6).
No existing test file was changed (member hard rule 1).

## Verification

- `ruff format`, `ruff check`, `mypy` on the new module: clean. `make lint`: green.
- `pytest --collect-only tests/e2e/test_bootstrap.py`: 11 tests collected.
- **Not run.** The SPEC forbids the Run from running `make e2e*` or starting a stack, so these
  tests have not been run against a stack. The Operator runs them with `make e2e`, the
  disposable `aio-e2e` stack.
- The piped-installer test needs `bash`, `curl`, `tar` and `python3` on the e2e runner (the
  host, through `uv run`). If any is missing, the test fails and names it; it never skips.

## Coverage

- C1 elements (`/mcp`, `version` keys, `read_guide(id?)`, `/llms.txt`): 4/4 against the image.
- Epic routes touched (`/version`, `/kit/install.sh`, `/kit/archive`): 3/3, happy path + 401.
- AC-1, AC-3, AC-4 (the parts a running stack can show): covered. AC-2 (two builds) and the
  live session per CLI are left to the owner by hand (SPEC § Non-goals).
- UI: none changed, so 0/0.

## Next Steps

- Operator: run `make e2e` to execute the module in the disposable stack.
