"""The step-kind registry: the one enumeration of kinds there is (AD-9).

Every kind the system knows is a row of `KIND_META`, and every question about a kind is
answered by reading that row. Nothing else lists kinds: the validator derives its accepted
set from these keys, the planner reads `gate_default` and `timeout_default_min`, and the
graph reads the same table. `if kind == ...` outside this package is the smell this module
exists to remove.

Epic 4 adds one `steps/<kind>.py` per executable kind implementing `StepExecutor` and
registers it here beside its metadata. Until then the table is metadata only — no
behaviour, so nothing has to change when the executors arrive except the rows gaining a
callable.

Three of the columns carry a rule:

- **`gate_default` is not a fallback for a missing `gate`.** It is what the planner records
  as the kind's normal gate; a Template that declares no `gate` on a step is reported in
  `ValidationResult.unvalidated`, and stays reported (NFR-2). A step with no declared gate
  is never silently green.
- **`with_keys` is the accepted set, not the required set.** An unknown `with` key is
  `unknown key`; a kind with an empty set accepts no `with` key at all.
- **`planner_only` marks a kind the planner inserts and a Template may not name.**
  `plan.check` is the first row of every plan (AD-7); writing it in YAML is `unknown kind`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

#: How a step's success is decided (AD-9). A Template declares one per step.
Gate = Literal["liveness", "deterministic", "human"]

#: The gate tokens, derived from the alias so the two can never disagree.
GATES: frozenset[str] = frozenset(get_args(Gate))


@dataclass(frozen=True)
class KindMeta:
    """What the system knows about one step kind before any Template is read."""

    #: The gate the planner records for this kind; `None` where the kind is not a row.
    gate_default: Gate | None
    #: Minutes the `ProcessRunner` allows by default; `None` where nothing is timed.
    timeout_default_min: int | None
    #: The `with` keys a Template may write on a step of this kind.
    with_keys: frozenset[str]
    #: True when the planner inserts the kind and a Template may not name it.
    planner_only: bool = False


#: Every step kind there is (spine "Shipped kinds"). The only enumeration of kinds.
KIND_META: dict[str, KindMeta] = {
    "plan.check": KindMeta("deterministic", 5, frozenset(), planner_only=True),
    "git.worktree": KindMeta("deterministic", 5, frozenset({"base", "branch"})),
    "git.sync": KindMeta("deterministic", 5, frozenset()),
    "shell": KindMeta("deterministic", 30, frozenset({"command"})),
    "agent": KindMeta(
        "liveness",
        90,
        frozenset({"harness", "model", "skill", "args", "prompt_extra"}),
    ),
    "git.commit": KindMeta("deterministic", 5, frozenset({"message"})),
    "git.push": KindMeta("deterministic", 5, frozenset({"branch"})),
    "pr.link": KindMeta("liveness", 5, frozenset({"branch"})),
    "checkpoint": KindMeta("human", None, frozenset()),
    "template": KindMeta(None, None, frozenset({"name", "version", "inputs"})),
    "bmad.install": KindMeta("deterministic", 30, frozenset()),
}

#: The kinds a Template file may name — every kind the planner does not own by itself.
TEMPLATE_KINDS: frozenset[str] = frozenset(
    kind for kind, meta in KIND_META.items() if not meta.planner_only
)

#: The kind whose step calls another Template. Not a row: it is a path segment (AD-15).
TEMPLATE_CALL_KIND = "template"

#: The kind whose step dispatches a harness, and the only one carrying the agent extras.
AGENT_KIND = "agent"

#: The kind whose step is a stop for a person. Named here because `application/graph.py`
#: marks its node `human` by kind rather than by gate, and AD-9 says a kind is named here
#: or nowhere.
CHECKPOINT_KIND = "checkpoint"

#: The kind whose step runs a command. Named here because the planner skips a row of this
#: kind whose command resolved to nothing, and that test is a test about the kind.
SHELL_KIND = "shell"

#: The kind of the first row of every plan (AD-7). The planner inserts it; a Template that
#: writes it is `unknown kind`, which is what `planner_only` above says.
PLAN_KIND = "plan.check"

#: The kind whose step creates the worktree a Run works in, and so the one that names the
#: branch the Run works on. The planner reads that branch to decide which commit the whole
#: plan is read at (AD-7); `git.push` and `pr.link` name a branch too, so the question is
#: which kind names it, not which step mentions it first.
WORKTREE_KIND = "git.worktree"

#: The kind whose step commits the working tree. Named here because `signal_run` re-resolves
#: a skipped Story's commit message on this row (AD-13) and AD-9 says a kind is named in this
#: table or nowhere.
COMMIT_KIND = "git.commit"

#: The `with` key `git.commit` carries its message under — the one `skip_story` rewrites.
COMMIT_MESSAGE_KEY = "message"

#: The two kinds that end an epic on the remote. `skip_epic` marks them `skipped` when the
#: push itself is the stop (AD-13), so they are named here rather than spelled in the rule.
PUSH_KIND = "git.push"
LINK_KIND = "pr.link"
