---
id: SPEC-mvp-epic-02-projects
companions: []
sources:
  - ../../prd.md
  - ../../architecture/ARCHITECTURE-SPINE.md
  - ../../../ux-designs/ux-v1-dev-loop-2026-08-26/EXPERIENCE-v1.md
---

> **Canonical contract for Epic 2.** Each story's full requirements live in `briefs/<id>-<slug>.md`, named from `stories.yaml` `invoke_dev_with`. Read the brief for the story you are dispatched on; do not read the other briefs. The repository's `AGENTS.md` files are the constitution; the architecture spine (`AD-n`) binds when a brief and the code disagree.

# Epic 2 — Projects and Repositories with the Clone check

## Why

A pain to prevent: a wrong URL or a token without access must fail at configuration time, not hours into a Run. This epic gives the Operator the Project (context text, encrypted agent environment variables, the content-logging switch) and its Repositories (default branch, commands, protected test globs), and runs the Clone check on every save so the Repository row states `ok`, `failed` with the verbatim git output, and the method version it carries. It realises user journey UJ-1 except repository initialisation, which needs Runs (Epic 4).

## Capabilities

- **CAP-1** Project with encrypted environment variables
  - **intent:** The Operator creates and edits a Project with name, context text, context file paths, agent environment variables, and the `log_prompt_content` switch; variables are encrypted at rest and returned masked.
  - **success:** `POST`/`PUT`/`GET /api/v1/projects` round-trip every field; the database holds only ciphertext; reads show `••••` plus the last four characters; the default of `log_prompt_content` equals `LOG_PROMPT_CONTENT_DEFAULT`.
- **CAP-2** Repository registration with commands and test globs
  - **intent:** The Operator registers Repositories under a Project with URL, default branch, package manager, `test_globs`, and the optional install, quality-gate, and unit-test commands.
  - **success:** a Repository without `quality_gate_command` saves with `verify_skipped: true`; `test_globs` defaults to the three globs; URL and default branch are required; ids are UUIDv7.
- **CAP-3** Clone check on save and on demand
  - **intent:** Saving a Project runs the Clone check per Repository (`git ls-remote`, base clone, default branch, method version) with the instance token supplied per command, stores the result on the Repository, and the Operator can re-run it from the row.
  - **success:** each line reports `ok` with duration or the verbatim command output; a failure stores `status: failed` without blocking the save; `bmad_version` reads the version, `missing`, or `outdated`; the token is never written to disk.
- **CAP-4** Projects list and detail screens
  - **intent:** The Operator sees every Project, and for one Project its context, repositories table with method and clone-check cells, settings, and (empty for now) runs.
  - **success:** the screens match the experience spec's Projects surface; a failed check reads `failed · new runs blocked` with *re-run check*; a missing quality command reads `— none declared` and `verify step will be skipped`.
- **CAP-5** New project and edit form with the live Clone check readout
  - **intent:** The Operator fills one form for the Project and its Repositories, saves, and reads the Clone check result per Repository beside the form with the one-line fix.
  - **success:** validation errors re-render the form with every value kept and the error beside the field; after save the readout shows each check line; the form states that credentials are instance settings and shows no token field.

## Constraints

- Credentials are instance settings (AD-5): no GitHub token or Gateway key is ever a Project field; `GITHUB_TOKEN` reaches git only through `GIT_ASKPASS`, per command; it is never stored, logged, or written under `/work`.
- Project environment variables are Fernet-encrypted with `ORCHESTRATOR_SECRET_KEY` (AD-5) and masked on every read.
- All git and filesystem side effects go through the `Git` port (AD-14); use cases never import `subprocess`, `os`, or `shutil` (AD-2).
- `repository.clone_check{status, at, output, bmad_version}` is written only by `use_cases/projects.run_clone_check` (AD-14).
- API shapes follow Epic 1's conventions: bearer auth, problem+json, `{items, next_cursor}` lists, generated TypeScript types (AD-3).
- UI follows the instrument-dark tokens and the signal rule; copy states mechanisms (NFR-6, NFR-8).
- Tests first; unit tests on fakes (`tests/unit/fakes/git.py` is created here); every new module has a test module (AD-18).

## Non-goals

- No Runs, no repository initialisation action, no daily re-check job (Epic 4).
- No per-Project spend figure, no trajectories export (Epics 7, 8).
- No deletion of Projects or Repositories in the MVP UI (API `DELETE` is out of scope).

## Success signal

The Operator creates the project *Website* with two repositories, one of which the instance token cannot reach; on save the second row reads `failed` with `fatal: Authentication failed` verbatim and the fix line; after granting access and clicking *re-run check* both rows read `ok` with their method version.
