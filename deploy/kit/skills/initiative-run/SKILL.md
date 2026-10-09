---
name: initiative-run
description: Dispatch a ready initiative folder to an ai-orchestrator instance and supervise the Run it creates — readiness gate, a human-confirmed harness, model and budget, creation, then watching for parks and answering the ones the declared autonomy allows. Use when the user says to run the initiative, dispatch a folder, launch the workflow, asks what the run is doing, or says it parked or is blocked.
---

# Dispatch and supervise an initiative

This skill takes an initiative folder that `initiative-spec` declared ready and turns it
into one Run, then stays with that Run until it finishes or needs its human. It assumes the
`orchestrator` skill beside it: the version handshake, the connection values, the endpoint
reference (`../orchestrator/references/api.md`) and the poll cadence are all there, and
nothing here replaces them. Do the handshake before the first call.

`INITIATIVE.md` at the folder root is the state: `initiative`, `phase`, `branch`, `flavor`,
`autonomy`, `artifacts`, `open_questions`, `decisions`, `gate`, `runs`. You read it at the
start and write back only `gate`, `runs` and a `decisions` entry.

## 1. Readiness

Re-run the gate, do not trust a recorded verdict: the folder, the branch and the instance
have all moved since it was written.

- `POST /api/v1/runs/preflight` with the inputs you are actually about to send — template,
  version, project, repository, base branch, `inputs`, harness, model, budget. The gate and
  what each check means is `../initiative-spec/SKILL.md` step 7; follow it there rather than
  re-deriving it here.
- Any `fail` line stops the dispatch. Report the line and its `fix`; a fix that belongs in
  the folder goes back through `initiative-spec`, not into a hand-edit here.
- `open_questions` must be empty. One open question is one park waiting to happen.
- Confirm `rows[]` is the plan you expect — the right epic count, the right story frames.
  A surprise here is a projection defect, which is cheap now and expensive at story 40.
- An attached initiative branch is fast-forwarded before dispatch, or a fresh branch name is
  taken. A Run started on a stale branch reads the old `epics.yaml` for its whole life.

Record the verdict in `INITIATIVE.md`'s `gate` with the timestamp of this check.

## 2. Recap and confirm

Before anything is created, state in a few lines what this Run will build: the epics, the
story count, the repositories or submodule working folders touched, the branch, and what the
Run will leave behind (branch, commits, PRs). Keep it to what the plan says.

Then get three things from the human, in one exchange:

- **harness** — `claude`, `codex` or `local`; null takes the instance default.
- **model** — what the template's own routing does not already fix.
- **budget** — `budget_usd`. One budget decision per Run. Never invent a number, never
  raise it silently, and never carry one over from a previous Run because it looked similar.

Nothing in steps 3 and 4 may change any of the three. A budget that turns out too small is
a `budget` park, which goes to the human (§4).

## 3. Dispatch

1. Preflight once more if anything changed between step 1 and the confirmation.
2. `POST /api/v1/runs` with exactly what was preflighted and confirmed. Fields and the
   `save` / `after_run_ids` options: `../orchestrator/references/api.md`.
3. Append the run id to `INITIATIVE.md`'s `runs`, with the date and the budget confirmed for
   it. That list is how the next session knows what already ran.
4. Hand the human the deep link — `<web base>/workflows/{run_id}` — and the queue answer
   (`starts_now`, `waiting`) from the 201 body.

## 4. Supervise

Supervision is a watcher, not an always-on agent: there is no push channel, and an agent
idling against a poll loop burns context to learn nothing. `orchestrator-watch` is installed
at `.orchestrator/bin/orchestrator-watch` (the installer prints the `PATH` line):

```bash
orchestrator-watch <run_id>            # prints each status change; exits on what needs a human
orchestrator-watch <run_id> --once     # one poll, for a harness that cannot hold a process
orchestrator-watch <run_id> --notify   # also a desktop notification per change
```

It polls at the documented cadence and refuses tighter. Its exit code is the branch:

| exit | meaning | what you do |
| --- | --- | --- |
| 0 | `done` | report the result, close out the folder's `runs` entry |
| 2 | `needs_you` | read `.orchestrator/runs/<run_id>.json` and go to the autonomy table |
| 3 | `failed` / `cancelled` | report it with the alert; a failed Run is not retried blind |
| 1 | HTTP or usage error | report the URL and the code it names |

**Where the harness can run a background process, run the watcher there** and read the
payload file when it exits 2 — that keeps the polling noise out of this conversation
entirely. Where it cannot, call `--once` at the cadence the Run's own status sets: 5 s while
`queued`/`running`, 30 s otherwise. Never tighter, in either mode.

On a park, `references/autonomy.md` decides who answers: the table is indexed by
`INITIATIVE.md`'s `autonomy` (`supervised`, `assisted`, `auto`; `assisted` is the default)
and by the alert's `park_kind`. Read it before sending any signal. Two rules hold at every
level:

- The signal kind comes from the Run's own `admitted_signals`, never from assumption.
- `budget` and `checkpoint` never resolve without the human.

A park that will recur on every story is not answered one story at a time. Name the cause
and where it is fixed: a tool the agent was denied is the instance's harness allowlist
(`orchestrator-admin`); a step the project needs added, moved, re-timed or re-worded is a
template edit, proposed to the human with `../orchestrator/references/workflows.md` — and
it reaches only Runs planned after the save, never this one.

When a park goes to the human, give them the deep link and the alert's `reason` verbatim —
not a paraphrase of a question an agent asked about their code.

## 5. When the Run ends

Report what landed: branch, commits, PRs, the final spend against the budget, and every
story that is `skipped` or `unvalidated` — those are words, not successes. Write the outcome
into `INITIATIVE.md`'s `runs` entry and add a `decisions` line for anything the supervision
decided on the human's behalf.
