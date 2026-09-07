"""The `pr.link` kind: the compare URL an Operator opens when a Run is done (FR-11, AD-14).

**A link, not a pull request.** The Run does not open one: it hands the Operator the page
GitHub already renders for `{default_branch}...{branch}`, from which they open a PR
themselves if they want one. Nothing here talks to an API, holds a credential or can fail
because a remote was unreachable — which is why the kind's gate is `liveness` (the URL was
produced) rather than `deterministic`.

**Two URL shapes, because a Repository is registered with either.** `https://github.com/o/r`
and `git@github.com:o/r`, each with or without `.git`. Anything else — a `file://` fixture, a
self-hosted forge, an unrecognised host — is `done` with `no compare link for this host` and
appends nothing: a Run that failed because its host is not GitHub would be a Run that failed
for being correctly configured, and appending a URL nobody can open would be worse than
appending none.

The append is a `RunUpdates` the writer applies (AD-8). It is an append and not a set: an
`initiative@1` Run pushes one branch per epic and ends with one link per epic. A URL the Run
already recorded is not appended twice, so a `retry` on this row leaves the list as it was.
"""

from __future__ import annotations

import re

from orchestrator.application.steps.context import StepContext, require_env
from orchestrator.application.steps.registry import register
from orchestrator.domain.values import RunUpdates, StepResult

#: The kind this module implements (AD-9: named here, beside the executor, or nowhere).
KIND = "pr.link"

#: The one `with` key `KIND_META` admits on this kind.
BRANCH_KEY = "branch"

#: The two shapes a GitHub remote is written in, `.git` optional in both. Anchored at both
#: ends: a URL that merely *contains* `github.com` — a mirror, a proxy — is not one.
GITHUB_URL = re.compile(
    r"^(?:https://github\.com/|git@github\.com:)(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?/?$"
)

#: The page the Operator opens.
COMPARE_URL = "https://github.com/{owner}/{repo}/compare/{base}...{branch}"

#: What a Repository on any other host records, and ends `done` with.
NO_LINK = "no compare link for this host"


class PrLinkExecutor:
    """Derive the compare URL from the Repository's own URL, or say there is none."""

    def execute(self, ctx: StepContext) -> StepResult:
        env = require_env(ctx)
        branch = str(ctx.with_resolved[BRANCH_KEY])
        matched = GITHUB_URL.match(env.repository_url)
        if matched is None:
            return StepResult(status="done", gate=ctx.row.gate, reason=NO_LINK)
        url = COMPARE_URL.format(
            owner=matched["owner"],
            repo=matched["repo"],
            base=env.default_branch,
            branch=branch,
        )
        recorded = env.compare_urls if url in env.compare_urls else (*env.compare_urls, url)
        return StepResult(
            status="done",
            gate=ctx.row.gate,
            output_ref=url,
            run_updates=RunUpdates(compare_urls=recorded),
        )


register(KIND, PrLinkExecutor())
