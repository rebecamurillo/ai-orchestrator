"""The step-kind registry: the one enumeration of kinds there is (AD-9).

Every kind the system knows is a row of `KIND_META`, and every question about a kind is
answered by reading that row. Nothing else lists kinds: the validator derives its accepted
set from these keys, the planner reads `gate_default` and `timeout_default_min`, and the
graph reads the same table. `if kind == ...` outside this package is the smell this module
exists to remove.

Epic 4 adds one `steps/<kind>.py` per executable kind implementing `StepExecutor` and
registers it through `registry.register` beside its metadata. The registry is the walker's
only way in: `execute(ctx)` looks the kind up here and reports a kind nothing implements as
a `misconfigured` park rather than as a skip (`steps/registry.py`). `KIND_META` stays the
answer to *what a kind is*; the registry answers *what runs it*.

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

from orchestrator.application.steps.context import StepContext, StepExecutor, StepPorts
from orchestrator.application.steps.registry import (
    EXECUTORS,
    execute,
    executor_for,
    register,
)

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
    #: Minutes of filesystem silence before the stall detector kills the process.
    #: `None` for kinds that do not use the stall detector (shell, git.*, etc.).
    stall_default_min: int | None = None


#: Every step kind there is (spine "Shipped kinds"). The only enumeration of kinds.
KIND_META: dict[str, KindMeta] = {
    "plan.check": KindMeta("deterministic", 5, frozenset(), planner_only=True),
    "git.worktree": KindMeta("deterministic", 5, frozenset({"base", "branch", "mode"})),
    "git.sync": KindMeta("deterministic", 5, frozenset()),
    "git.merge": KindMeta("deterministic", 5, frozenset({"from"})),
    # Added: the shipped-kinds table gained `git.submodule` — two forms told apart by their
    # `with` keys, bare/`{update}` for the init + update of the Run worktree's submodules and
    # `{workdir, branch, base?}` for the create-or-checkout inside one of them
    # (hub-Run initiative H1, spine AD-7/AD-9/AD-14 amendment, 2026-09-23).
    "git.submodule": KindMeta(
        "deterministic", 10, frozenset({"update", "workdir", "branch", "base"})
    ),
    "shell": KindMeta("deterministic", 30, frozenset({"command"})),
    "agent": KindMeta(
        "liveness",
        None,
        frozenset({"harness", "model", "skill", "args", "prompt_extra"}),
        stall_default_min=30,
    ),
    # Revised: `git.commit` and `git.push` gained `workdir` — the row runs inside that
    # submodule's own repository instead of the worktree root (hub-Run initiative H2, spine
    # "Template DSL v1 keys" AD-9/AD-14 amendment, 2026-09-23).
    "git.commit": KindMeta("deterministic", 5, frozenset({"message", "workdir"})),
    "git.push": KindMeta("deterministic", 5, frozenset({"branch", "workdir"})),
    "pr.link": KindMeta("liveness", 5, frozenset({"branch"})),
    # Revised: the shipped-kinds row for `checkpoint` gained `when` — a resolved falsy
    # value plans the row `skipped · no checkpoint` at plan time, the same rule the
    # empty-command shell skip already used (multi-repo initiative S5, spine AD-7
    # amendment, 2026-09-23).
    "checkpoint": KindMeta("human", None, frozenset({"when"})),
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

#: The `with` key `git.worktree` names its checkout mode in, and the one value that key
#: takes. `mode: attach` exempts the frame from branch allocation (AD-7): the declared
#: branch is worked on by its exact name, at its origin head, which is how a Run enters a
#: repository's shared integration branch — the fresh-branch guarantee is waived for those
#: frames and for those only, and AD-12's `{repository_id}:{branch}` partition is what
#: serializes the Runs that share one. A `mode` the planner does not recognise is simply not
#: attach, and the frame allocates as any other does.
WORKTREE_MODE_KEY = "mode"
ATTACH_MODE = "attach"

#: The kind that turns a hub repository's `repos/*` gitlinks into working folders, and the
#: four `with` keys its two forms are told apart by (spine "Template DSL v1 keys", ratified
#: 2026-09-23). Named here rather than in `steps/git_submodule.py` alone because the
#: validator judges the *shape* the keys make — bare or `{update}`, exclusive-or
#: `{workdir, branch, base?}` — and `application/templates/` may not import a kind's module
#: (AD-9: a kind's vocabulary is named once, in this table, or nowhere).
SUBMODULE_KIND = "git.submodule"
SUBMODULE_UPDATE_KEY = "update"
SUBMODULE_WORKDIR_KEY = "workdir"
SUBMODULE_BRANCH_KEY = "branch"
SUBMODULE_BASE_KEY = "base"

#: The checkout form's keys, derived from the kind's own row so the two forms are a
#: partition of what the kind admits rather than a second list that could drift from it.
SUBMODULE_CHECKOUT_KEYS: frozenset[str] = KIND_META[SUBMODULE_KIND].with_keys - {
    SUBMODULE_UPDATE_KEY
}

#: The `with` key `checkpoint` names its condition in (AD-7). A checkpoint that declares no
#: `when` keeps today's behaviour exactly — always a live human gate; one that declares it
#: is planned `skipped · no checkpoint` when the resolved value is falsy, by the same
#: plan-time rule `SHELL_KIND`'s empty command uses (multi-repo initiative S5, 2026-09-23).
WHEN_KEY = "when"

#: The `with` key `agent`, `git.commit` and `git.push` declare when the row runs inside a
#: submodule instead of at the worktree root (spine "Template DSL v1 keys", AD-9,
#: ratified 2026-09-23, hub-Run initiative workflow). Not `SUBMODULE_WORKDIR_KEY` above —
#: that one names *which* submodule `git.submodule`'s checkout form creates or checks out;
#: this one names *where* an unrelated kind's whole operation runs. H2 wires `git.commit` and
#: `git.push`; the `agent` kind's own `workdir` is H4's.
WORKDIR_KEY = "workdir"

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

# Every `steps/<kind>.py` module reads `KIND_META` and friends back from *this* package, so
# this module cannot import them at module level without a cycle — `checkpoint.py` and
# `shell.py` need constants from `application/templates/`, whose own modules import this
# package for `KIND_META`. Nothing here needs any kind's module to run, so nothing here
# imports one: `infrastructure/dbos/startup.py` imports `checkpoint`, `plan_check` and
# `shell` directly, once this package has fully finished, which is what actually runs each
# one's own `register(...)` call (AD-9: "each by calling `register` beside its module").

#: What this package is: the metadata table above, and the registry the walker dispatches
#: through. Re-exported so a caller writes `from orchestrator.application.steps import …`
#: whichever half it needs (AD-9: "the registry in `application/steps/__init__.py`").
__all__ = [
    "AGENT_KIND",
    "ATTACH_MODE",
    "CHECKPOINT_KIND",
    "COMMIT_KIND",
    "COMMIT_MESSAGE_KEY",
    "EXECUTORS",
    "GATES",
    "KIND_META",
    "LINK_KIND",
    "PLAN_KIND",
    "PUSH_KIND",
    "SHELL_KIND",
    "SUBMODULE_BASE_KEY",
    "SUBMODULE_BRANCH_KEY",
    "SUBMODULE_CHECKOUT_KEYS",
    "SUBMODULE_KIND",
    "SUBMODULE_UPDATE_KEY",
    "SUBMODULE_WORKDIR_KEY",
    "TEMPLATE_CALL_KIND",
    "TEMPLATE_KINDS",
    "WHEN_KEY",
    "WORKDIR_KEY",
    "WORKTREE_KIND",
    "WORKTREE_MODE_KEY",
    "Gate",
    "KindMeta",
    "StepContext",
    "StepExecutor",
    "StepPorts",
    "execute",
    "executor_for",
    "register",
]
