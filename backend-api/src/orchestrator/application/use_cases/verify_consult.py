"""`verify_consult` (AD-9, AD-22, story 1-6): the senior consulted on a `verify_failed` stop,
offered where `apply_redispatch` would otherwise park.

**The consult attempt belongs to the redispatch target**, not to the `run` row that failed.
The target is the `agent` row: it holds the harness, the model, the `workdir` and the
story's tree, and `agent_consult.run` is the executor that already dispatches a senior. The
`run` row only declares the consult (`on_fail {redispatch, max, consult}`) and keeps the stop:
its `error` status and its park stay as they are, so *Retry* re-queues the gate.

**One consult per stop kind per row** is the target's entry in `step_run.consults`, written
`due` here with the block the verify row declared (the target declares none for this stop)
and the verify row's path, where the stop parks. Marking the target means a second
`verify_failed` finds the entry and parks, whatever the consult came to.

**This writes rows and nothing else.** The sweep of both trees and the snapshot the senior is
checked against are git work: the target's first consult attempt takes them inside the
executor and hands them back as an offer (`agent_consult.run`), and `apply_consult` merges
them into this entry. The writer's unit of work never waits on git.

Nothing is offered when the verify row declares no consult or the target already holds an
entry; the stop parks with the reason the redispatch bound gave. The Run never leaves
`running` and nothing is announced.
"""

from __future__ import annotations

from orchestrator.application.rules import consult as rules
from orchestrator.application.use_cases.writers import WriterPorts, set_row
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import step_transition
from orchestrator.domain.values import Park

#: The stop kind the consult is offered at.
KIND = rules.VERIFY_FAILED


def offer(
    ports: WriterPorts, sender: StepRun, target: StepRun, exhausted: Park
) -> tuple[Park | None, bool]:
    """`(None, True)` when the target was queued for a consult, else `exhausted` and `False`
    (`apply_redispatch`'s own answer shape)."""
    block = rules.verify_block(sender.with_resolved)
    if block is None or KIND in target.consults:
        return exhausted, False
    entry = {
        rules.STATE_KEY: rules.DUE,
        rules.QUESTION_KEY: exhausted.reason,
        rules.DECLARED_KEY: dict(block),
        rules.PARK_PATH_KEY: sender.path,
    }
    set_row(
        ports,
        target,
        status=step_transition(target.status, "redispatch"),
        consults={**target.consults, KIND: entry},
    )
    return None, True
