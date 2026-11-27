---
title: Initiative packages
kind: page
audience: any
---
# Initiative packages

A Project's initiative procedure is one installed package: a folder of its hub repository that holds
`package.yaml` and the workflow templates it names. An initiative walks the package's sequence, one Run per workflow.

## package.yaml

The file has exactly four keys; an unknown or a missing key refuses the install.

- `name` — matches `^[a-z][a-z0-9-]*$`.
- `sequence` — a non-empty list, in order, of `{workflow, template}`. `workflow` matches the same pattern and appears once.
  `template` is either a path inside the package ending in `.yaml`, or the name of a shipped template.
- `gate` — `{pass, fail, owners_key}`. `pass` and `fail` are non-empty lists of words that share no word;
  `owners_key` matches `^[a-z_][a-z0-9_]*$`.
- `status_map` — a non-empty mapping from a step-file word to one of `done`, `running`, `waiting for her`, `failed`.

The folder of an initiative comes from the repository's `initiative_folder` (default `initiatives`), never from the package.
A package template is stored as `{package.name}.{template}`, where `template` is the file name without `.yaml`, tagged with the
installed commit sha; two package templates may not share a stem. The package holds exactly one `spec-gate` row, and its
`expect.success` lists every `pass` and `fail` word. The sequence is frozen when an initiative is created: a later install does not
change an initiative that exists.

## Template type

A template declares `type: interactive` or `type: auto`; the default is `auto`. An `interactive` template whose plan holds a
conversation row runs in the interactive lane, whose concurrency is `MAX_INTERACTIVE_RUNS`. A Run parked on a conversation holds an
interactive slot, never a `MAX_ACTIVE_RUNS` one. Every other Run runs in the walk lane.

## The conversation kind

A step with `uses: conversation` needs `type: interactive` and `role: plan`. Its keys:

- `with` — `skill` and `persona` (text) and `step` (a slug, the step's name in the initiative).
- `expect.files` — one literal path, no glob character. `expect.success` — one or more words. `expect.blocked` — optional words.
- `writes` — optional list of paths. A conversation may write these anchors inside `{initiative_folder}/{slug}/` without a
  `protected_path` stop; any other anchor, test file or path outside the folder still stops.
- `prompts.open` and `prompts.close` — both required. `prompts.close` names `{attempt_id}`.

Two Run inputs shape a round. `round_steps` is a comma-separated list of step names: when it is non-empty, a conversation row
outside it is `skipped · not in this round`, and a list that names no conversation row of the plan stops the Run as misconfigured.
`first_turn` is the text of the first turn: it replaces `prompts.open` for the first conversation row of the plan, or for each row
named by `round_steps`.

## The step file and its words

The step file is the row's `expect.files` path. Its YAML frontmatter holds `status`, the word. A step closes on two facts together:
the operator's word, which the agent attests by writing `.orchestrator/session/close` naming the turn's attempt id, and the file
holding one of the `expect.success` words. The operator's word without the done word, or the done word without the operator's word,
does not close it. A word the row does not list as done reopens the conversation with the sentence
`step not closed · {file} has status {word}, the done content is status {done} · the step stays open`; a file with no status or no
file gives the matching sentence.

## The gate

The `spec-gate` row is an agent row whose step file carries a gate word. `pass` and `fail` both route the row `done`; the Run's
verdict holds the word, the frontmatter fields and the body text.

- A `pass` word starts the next entry of the sequence. Before a build workflow it runs preflight: a defect in the spec files starts a
  new round at the step that writes `epics.yaml`; any other failing check stops the initiative as waiting for her.
- A `fail` word reads the owners list under `owners_key` in the step file's frontmatter, and starts a new round of the same spec
  workflow with `round_steps` set to those steps in sequence order and `first_turn` set to the file's body. No owners, or an owner
  that is not a step of the workflow, stops it as waiting for her.
- A word in neither list stops it as waiting for her: `gate word {word} is not declared`.

## The status map

`status_map` turns the step-file word into the initiative's status. A running Run whose step-file word is not a key of the map reads
`failed` with the reason `unmapped word {word}`.

## Install without a screen

All routes sit under `/api/v1` and take the bearer token.

- `PUT /projects/{id}/package` with `{repository_id, path, ref}` reads `package.yaml` and its templates at `ref` of the hub and
  stores them all or none. It answers 422 with `errors[]` naming each file and reason, 404, or 409 when `ref` is not a branch of the
  remote or another project holds a package of that name from another repository or path.
- `GET /projects/{id}/package` reads the installed record and its declaration.
- `DELETE /projects/{id}/package` answers 204 and keeps every stored template version. It answers 409 while initiatives created from
  the package are open.
- `PUT /projects/{id}/run-defaults` replaces the five defaults together: `default_budget_usd`, `default_harness`, `default_model`,
  `default_autonomy`, `default_senior_model`. `null` clears one; an omitted key is refused.
- `PUT /repositories/{id}/initiative-folder` with `{initiative_folder}` sets where the repository's initiatives live.

Each has an MCP tool: `install_package`, `read_package`, `remove_package`, `set_run_defaults` and
`set_initiative_folder`.

## Reopen

`POST /api/v1/initiatives/{id}/reopen` with `{step, reason}` opens a conversation step again as the next round. It cancels every live
Run of the initiative, attaches the branch `spec/{slug}` or creates it from the hub's default branch, and starts the spec workflow's
Run with `round` plus one, `first_turn` set to `reason`, and `round_steps` set to the step and every later conversation step of that
workflow not yet done. It answers 201 `{run_id, round}`; 404 for an unknown initiative; 409 for a cancelled or done initiative, a Run
that is still live, or a hub whose default branch is missing from its remote; 422 for an empty reason or a `step` that is not a
conversation step of the frozen sequence. It has no MCP tool.

## Upgrades

An upgrade keeps every parked conversation: the order is in `host/upgrade`, § Initiative conversations.
