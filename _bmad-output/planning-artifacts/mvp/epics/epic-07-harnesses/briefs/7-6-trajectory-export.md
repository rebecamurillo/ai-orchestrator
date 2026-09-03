---
story: "7-6"
epic: 7
title: Trajectory export
requirements: [FR-32 (export), SM-1, SM-3, UX-DR12, UX-DR18, AR-23]
binds: [AD-1, AD-19]
---

# Story 7.6 — Trajectory export

As the Operator,
I want to download every done story's trajectory for a Project as JSON lines,
So that unattended completion and cost per harness are computed from the record, and a fine-tuning set can be built from it later.

## Scope

**In:** `GET /api/v1/projects/{id}/trajectories.jsonl` (streamed, newest first), the *Export trajectories* action on the Project detail with its hint, a proxy passthrough for the download, tests.
**Out:** any aggregation or dashboard.

## Binding rules (inlined)

- **Endpoint (AD-19).** `GET /projects/{id}/trajectories.jsonl` → `application/x-ndjson`, `Content-Disposition: attachment; filename="trajectories-{project.slug}-{date}.jsonl"`, one JSON object per line = the trajectory row (5.9) with `story_file` included, ordered by `recorded_at desc`, streamed in pages of 100; 404 for an unknown Project; empty Project → an empty body with 200.
- **Proxy.** The Astro proxy streams the response with the headers intact; the browser download works from the page (a plain link with the session cookie).
- **Project screen (UX-DR12).** Bar action *Export trajectories* (`projects-export`) linking to `/api/projects/{id}/trajectories.jsonl`; hint under it: `one line per done story · newest first · JSON lines`; the count of trajectories shown beside (`{n} trajectories`), read from the Project read model (`trajectory_count`).
- **Fields for SM-1 and SM-3** are present per line: `harness`, `model`, `attempts[]`, `human_actions[]`, `cost_usd`, `wall_clock_seconds`, `gate_results`.

## Acceptance criteria

**Given** a Project with three trajectories
**When** the endpoint is read
**Then** three lines arrive newest first, each parses as JSON with the fields above, and the headers carry the ndjson type and the attachment filename.

**Given** a Project with none
**When** read
**Then** 200 with an empty body.

**Given** the Project detail
**When** rendered
**Then** *Export trajectories* links to the proxy path, the hint is shown, and the count reads `3 trajectories`.

**Given** the proxy
**When** the download is requested from the browser (Playwright)
**Then** the file arrives with the filename and content.

## Implementation notes

- Streaming response in FastAPI (`StreamingResponse`) over a generator paging the repository; proxy: ensure `[...path].ts` does not buffer or alter `Content-Disposition`.
- Read model: `trajectory_count` on `GET /projects/{id}`.

## Verification

```bash
make lint && make test && make openapi && make e2e-api && make e2e-ui
```

## Sources for detail only

PRD FR-32 (export), SM-1, SM-3. Spine AD-19, conventions (Routes: trajectories). `EXPERIENCE-v1.md` §3 Projects (bar actions).
