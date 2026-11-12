# Test Automation Summary — orchestrator-instance-guide / epic-2-mcp-api

Generated: 2026-11-12 (dispatch mode with an empty story id, so it covers the whole epic)
Spec: `initiatives/orchestrator-instance-guide/epic-2-mcp-api/SPEC.md` (path relative to the hub)
Stories: 1–7 (commits `fc3009d`..`9ecaba8`)

Framework: the project's own, pytest + httpx in `backend-api/tests/e2e` (`make e2e-api`). The
epic changed no UI (the SPEC says the web client is unchanged), so no Playwright test was added.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_agent_connection.py` (21 test functions, 29 cases). The unit
  suite proves each rule over fakes and over guides built in `tmp_path`. This module tests what
  only the running image can show: `/mcp` behind the bearer, the epic's tools published, the
  guide the image built served the same way through every MCP surface, and the new routes
  mounted behind the bearer and agreeing with their tools.
  - `/mcp` without a bearer: 401 problem+json. `tools/list` includes the 11 tools the epic adds
    (AD-34).
  - CAP-5: `read_guide()` returns exactly `/llms.txt`. For every page id in the index,
    `read_guide(id)`, `resources/read guide://{id}` and `/guide/{id}.md` give the same text.
    `resources/list` holds exactly the index's ids as `text/markdown`. `prompts/list` holds
    exactly the pages whose front matter says `kind: procedure`, named by `prompt_name`, and each
    renders one user message containing the page. `read_guide("../api/v1/projects")` is refused
    as "not a page id". An unknown page returns a 404 carrying `refusal-guide-unavailable`.
  - CAP-3: `POST /api/v1/spec-folders/validate`:
    - answers 401 without a bearer;
    - a clean folder gives `{findings: []}`;
    - two equal story ids give exactly one `spec-duplicate-entry-id` finding on
      `e1/stories.yaml`, and its `errors/…` guide page is served;
    - an absolute path, a `..` path, a `./` path and a backslash path each get 422;
    - `validate_spec_folder` over MCP answers exactly what the route answers.
  - CAP-4: `GET /api/v1/harnesses/{name}/models`:
    - `local` answers `source: configured`;
    - `claude` and `codex` answer according to how the stack is configured: `litellm`, or
      `none` with `refusal-models-unlisted` naming the harness, or 503
      `refusal-models-gateway-unreachable`. The test checks the shape of whichever answer
      arrives and never skips;
    - an unknown harness gets 404, and the route answers 401 without a bearer;
    - `list_models` answers what the route answers, and refuses a name that is not a harness
      name.
  - CAP-2:
    - `save_template`, which always sends `refuse_if_in_folder`, saves a name the folder does not
      hold (`in_folder: false`), and `list_templates` lists it;
    - a REST save with the flag on such a name answers 201;
    - every `validate_template` finding has a `code`, an integer `line` and a guide page that is
      served;
    - the names `a/b`, `a?b`, `..` and `a%2fb` are refused before any call.

No test reads page prose or pins template content (member hard rule 6). Every workflow and spec
folder is a fixture the test owns, and every name is unique per run.

Not covered here, because the stack cannot show it:
- The 409 `refusal-template-in-folder` needs `OPERATOR_TEMPLATES_DIR` pointing at a folder that
  holds the name. The e2e stack leaves the folder off, so this stays covered by
  `tests/unit/test_templates_folder_refusal.py`.
- The setup path (CAP-1) was already covered at e2e by story 1's
  `tests/e2e/test_mcp_setup_path.py`.

## Verification

- The SPEC forbids running `make e2e*` or starting a stack inside the Run, so the module was not
  run against a stack. It was run from a scratch harness in `/tmp`, outside the repository (since
  deleted). The harness served `create_app(Settings())` over uvicorn in a thread, with:
  - `GUIDE_DIR` pointed at a guide that `build_guide` built from the real `guide/` and `VERSION`;
  - the shared unit fakes behind `template_ports`;
  - `model_sources` overridden.
  Result: **29 passed** with no gateway (`source: none`). The models tests also passed with a
  fake gateway (`source: litellm`).
- `make lint`: exit 0. `make test`: exit 0 (backend 11168 passed, 1 skipped; web-client 1868
  passed).

## Coverage

- New REST operations (C5): 2 of 2 at e2e (`/spec-folders/validate`, `/harnesses/{name}/models`).
  The `refuse_if_in_folder` save is covered at e2e for the success path and at unit level for the
  409.
- MCP tools added by the epic: 11 of 11 are published. 10 of 11 are called at e2e:
  `reload_templates` is called only by unit tests, because on this stack it answers the 409
  "folder not configured", which `test_template_folder_epic.py` already covers over REST.
- MCP surfaces (CAP-5): tools, resources and prompts are all checked against the image's own
  guide.

## Next Steps

- Run the module in `ci.yml`'s `e2e-api` job on the pull request.
- Optional: an e2e stack variant with `OPERATOR_TEMPLATES_DIR` set, to exercise the 409 refusal
  end to end.
