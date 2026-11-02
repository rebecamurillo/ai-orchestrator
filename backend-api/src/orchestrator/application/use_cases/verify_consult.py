"""`verify_consult` (AD-9, AD-22, story 1-6): the senior consulted on a `verify_failed` stop,
offered where `apply_redispatch` would otherwise park.

**The consult attempt belongs to the redispatch target**, not to the `run` row that failed.
The target is the `agent` row: it holds the harness, the model, the `workdir` and the
story's tree, and `agent_consult.run` is the executor that already dispatches a senior. The
`run` row only declares the consult (`on_fail {redispatch, max, consult}`) and keeps the stop:
its `error` status and its park stay as they are, so *Retry* re-queues the gate as it always did.

**One consult per stop kind per row** is the target's entry in `step_run.consults`, written
`due` here with the block the verify row declared (the target declares none for this stop),
the stop's own reason, and the clean snapshot of both trees the senior is checked against.
Marking the target means a second `verify_failed` finds the entry and parks, whatever the
consult came to.

Nothing is offered when the verify row declares none, when the target already holds an entry,
or when the offer cannot take its snapshot: those stops park exactly as before, the last with
git's words added. The Run never leaves `running` and nothing is announced.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.rules import consult as rules
from orchestrator.application.steps import agent_consult_tree, agent_workdir
from orchestrator.application.steps.context import resolved_text
from orchestrator.application.templates.agent_row import STORY_ID_KEY
from orchestrator.application.use_cases.writers import Entry, WriterPorts, record, set_row
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.statuses import step_transition
from orchestrator.domain.values import Park

#: The stop kind the consult is offered at, and the sentence a failed offer adds to the park.
KIND = rules.VERIFY_FAILED
CONSULT_FAILED = "{reason} · consult failed: {why}"


def offer(
    ports: WriterPorts, run: Run, sender: StepRun, target: StepRun, exhausted: Park
) -> tuple[Park | None, bool]:
    """`(None, True)` when the target was queued for a consult, else `exhausted` and `False`
    (`apply_redispatch`'s own answer shape), the park carrying git's words if the sweep failed."""
    block = rules.verify_block(sender.with_resolved)
    git = ports.git
    if block is None or KIND in target.consults or git is None or run.worktree_path is None:
        return exhausted, False
    latest = ports.attempts.get_latest_agent(target.id)
    n = latest.n if latest is not None else 0
    story_id = resolved_text(target.with_resolved, STORY_ID_KEY)
    workdir = agent_workdir.declared_in(target.with_resolved)
    message = agent_consult_tree.WIP_MESSAGE.format(id=story_id, n=n)
    try:
        snapshot = agent_consult_tree.snapshot_trees(git, Path(run.worktree_path), workdir, message)
    except GitError as error:
        why = error.output.strip() or str(error)
        failed = CONSULT_FAILED.format(reason=exhausted.reason, why=why)
        return exhausted.model_copy(update={"reason": failed}), False
    entry = {
        rules.STATE_KEY: rules.DUE,
        rules.QUESTION_KEY: exhausted.reason,
        rules.SNAPSHOT_KEY: snapshot,
        rules.DECLARED_KEY: dict(block),
        rules.PARK_PATH_KEY: sender.path,
    }
    record(
        ports,
        run,
        Entry(
            event="consult",
            actor="machine",
            path=target.path,
            text=exhausted.reason,
            attempt_n=latest.n if latest is not None else None,
            payload={rules.KIND_KEY: KIND},
        ),
    )
    set_row(
        ports,
        target,
        status=step_transition(target.status, "redispatch"),
        consults={**target.consults, KIND: entry},
    )
    return None, True
