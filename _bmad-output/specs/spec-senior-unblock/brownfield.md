# Brownfield notes

Paths are under `backend-api/src/orchestrator/` unless stated. Verified 2026-11-01 on commit `4c0e985`.

## Reuse

| Need | Existing piece |
| --- | --- |
| Resume the stopped agent | `answer {mode: session}`; `signal_run._check_mode` defaults to session when the attempt can resume; `steps/agent.py::_planned` |
| Bounded re-run without a Run transition | `retry_auto` and `redispatch` in `use_cases/apply_step_result.py` |
| Read a written decision | Routing on a marker file: `steps/agent_tail.py::_route`, `rules/routing.py` |
| Accept test files | `run.accepted_paths`, `rules/protected_paths.py::check` |
| Scheduled job that sends a signal | `jobs/terminal_poll.py`: 30 seconds, state stored on the row, survives restart |
| Locked Run actions during outside work | `terminal_session`, `terminal_start`, `terminal_release` |
| Encrypted Project secrets | `Crypto` port and `EncryptedEnvVar`; the chat token needs a separate field, because Project env vars reach the harness |
| Model picker | Web inputs named with a `model` prefix or suffix get the probed-model select, so `senior_model` needs no UI work |
| Instance webhook | `domain/ports/notifier.py`, `infrastructure/notify/`; stays as it is, one-way and instance-wide |

## Traps

- **Wrong session resumed.** `latest_attempt_for_run` and `ctx.previous_attempt` take the newest attempt. A senior recorded as an attempt on the row would become the session that `answer` resumes.
- **No stop identity.** `Run` holds `park_kind`, `park_path` and `park_reason`, and `signal_run` checks no stop ID. CAP-4 adds one.
- **`Actor` is closed.** `domain/statuses.py` allows `operator`, `machine`, `terminal`. The senior and chat need values, with platform and author in the record.
- **Line caps.** `steps/agent.py` and `steps/agent_tail.py` are at 400 lines; new work goes in new modules, with a paired test module.
- **Provider failure wording.** `rules/harness_failure.py::gateway_unreachable` returns `None` when `tokens_out` is non-zero. The credit failure ran 14 minutes, so it most likely took this path and fell through to `harness exit 1`. Confirm against the attempt log.
- **Test globs.** `repository.test_globs` is exactly what the Operator lists, and empty freezes nothing. A hub Run applies the hub's list to its member paths too.
- **Rejected retro.** `retro` is an ordinary agent row in `templates/staged-hub-epic.yaml`, and nothing routes on its verdict.
- **No pause.** `SignalKind` has none, and a new park kind needs a row in AD-13's table and a UI token decision (`needs_you` renders `BLK` or `CHK`).
- **Walker sequence.** Bump `DBOS_APPLICATION_VERSION` only if the walker's step sequence changes.
- **Template prose.** The `answer` prompts in shipped templates say "Answer from the operator". A senior's answer needs its own wording, as the past Run's agents obeyed answers labelled as operator decisions and target repositories' rules may name the operator.

## Spine and anchor changes

Only the Operator changes these.

- **Hard rule 1 and AD-17, proposed wording:** "A consult senior may approve named existing test files at a `blocked` stop, or accept a `protected_path` hit on existing tests after reading the diff, when the story being executed requires the behaviour change. Anchors are never delegated."
- **AD-5:** per-Project chat tokens.
- **AD-8:** new actors, and the session and pause paths.
- **AD-9 and the template DSL:** a `consult` key naming `senior_model` and a harness, which may differ from the row's, so a cheap implementer can consult a stronger model.
- **AD-10:** the senior's session and the operator session.
- **AD-13:** `pause`, the park it writes, stop identity on signals, and session close.
- **Deferred list:** remove "Notifications (Mattermost)".

## External facts

- [Official Mattermost images are amd64 only](https://support.mattermost.com/hc/en-us/articles/53131125053204-ARM64-support-for-Mattermost-Server), which is why it is not hosted on the arm64 host.
- [Internal Slack apps keep Tier 3 limits on `conversations.replies`](https://docs.slack.dev/reference/methods/conversations.replies).
