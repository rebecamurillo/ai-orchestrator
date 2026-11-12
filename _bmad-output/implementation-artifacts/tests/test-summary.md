# Test Automation Summary — orchestrator-instance-guide / epic-1-guide

Generated: 2026-11-12 (dispatch, empty story id, covering the whole epic)
Spec: `initiatives/orchestrator-instance-guide/epic-1-guide/SPEC.md` (hub-relative)
Stories: 1–6 (committed `7edcbb8`..`6612f9b`)

Framework: the project's own — pytest + httpx in `backend-api/tests/e2e` (`make e2e-api`),
with `jsonschema` and `pyyaml` from `uv.lock`. No UI changed in this epic (SPEC § Non-goals), so
no Playwright test was added.

## Generated Tests

### API (e2e) tests — `make e2e-api` gate

- [x] `backend-api/tests/e2e/test_guide.py` (10 tests). The unit suite tests the routes against
  guides built in `tmp_path`. This module tests what only the running image can show: the
  Dockerfile's `build_guide` step wrote the guide where the routes read it, the open routes answer
  with no bearer while `/api/v1/*` still refuses requests without one, and a finding from the real
  validator names a page the real build wrote.
  - `/llms.txt` without a bearer: 200, `text/plain; charset=utf-8`, the llmstxt layout (title, blank
    line, release blockquote), sections in the order Guide → Host → Errors, and `errors/` pages only
    under Errors (CAP-3).
  - Every page the index lists is served open as `text/markdown; charset=utf-8`. Its front matter
    `release` equals `GET /api/v1/version`'s `app_version` (AC-8). `title`, `kind` and `audience`
    follow C2, `audience: host` matches the Host section, and every host page holds the local-only
    line (CAP-6).
  - No open response sets a cookie or an `access-control-*` header, even with an `Origin` header
    present (AD-1 amended).
  - `/api/v1/projects` and `/api/v1/templates` without a bearer still answer 401.
  - These requests answer 404 `application/problem+json` with `code: refusal-guide-unavailable` and
    `guide: errors/refusal-guide-unavailable`: an unknown page, an unknown schema, and a schema
    name with an upper-case letter. `/guide/%2e%2e/VERSION.md` answers 404.
  - The refusal's own guide page is served, so the code resolves on the instance (CAP-1 + CAP-2).
  - `/schemas/workflow.json` and `/schemas/spec-folder.json`: 200, `application/schema+json`, the
    right `$schema`/`$id`, and both pass as draft 2020-12 schemas (CAP-4).
  - AC-12, HTTP half. One workflow fixture owned by the test is accepted by the served schema and by
    `POST /api/v1/templates/{name}/validate`. The same fixture with an unknown top-level key is
    refused by both. The validator's finding carries `code: template-unknown-key`,
    `guide: errors/template-unknown-key` and an integer `line`, and that guide page is served.
  - The spec-folder schema's `epics` and `stories` definitions refuse an entry that lacks its
    required fields and accept one that has them.

No test reads page prose or pins which pages ship (member hard rule 6). Every assertion checks
structure: the layout, media types, front matter, the host line, codes and ids.

## Verification

- The SPEC forbids running `make e2e*` or starting a stack inside the Run, so the module was not run
  against a stack. It was run in-process from a scratch harness outside the repository (since
  deleted). That harness used `create_app(Settings())` with `guide_dir` overridden to a guide built by
  `build_guide` from the real `guide/` and `VERSION`, and with the shared unit fakes behind
  `template_ports`. Result: **10 passed**.
- `make lint`: exit 0. `make test`: exit 0 (backend 11005 passed, 1 skipped; web-client 1868 passed).

## Coverage

- Open routes (CAP-3): 3/3 routes (`/llms.txt`, `/guide/{id}.md`, `/schemas/{name}.json`), happy
  path and refusal.
- Finding codes leaving the API (CAP-1): template validate is covered. Pre-flight lines with codes
  are not covered at e2e: they would need a real cloned repository with a bad `epics.yaml`, and the
  unit suite already covers them over the fake `Git`.
- Format descriptions (CAP-4): 2/2 schemas.
- Host pages (CAP-6): host-line rule on every served host page. The README blocks are checked by
  `make lint` (`scripts/check_guide.py`), not over HTTP.

## Next Steps

- Run `make e2e` (the disposable `aio-e2e` stack) outside the Run so the module runs against the
  built image.
- Schemathesis (`test_schemathesis.py`) now also reaches the three open routes through
  `/openapi.json`. Watch its first run for a generated `page_id` the 404 path does not handle.
