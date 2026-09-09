"""`env_for`: the exact environment a harness process receives, and nothing else (AD-5, AD-10).

`scripts/harness/_common.sh` is normative — it declares `HARNESS_ENV_CONTRACT`, and the
tuple below mirrors it name for name. Two statements of one list is a liability unless
something compares them, so `tests/unit/test_harness_env_contract.py` parses the bash array
and asserts the equality in both directions: a name added to the script and not here fails
that test rather than a harness that cannot find its own configuration.

The result is built from four sources, merged in this order, each winning over the one
before it:

1. the Project's decrypted variables, minus every name AD-5 forbids;
2. the four names every process needs (`HOME`, `PATH`, `LANG`, `TERM`) — so a Project
   variable cannot re-point the harness at a different `PATH` binary or a different
   `~/.claude` by naming `HOME`;
3. the contract, so a Project cannot re-point its own attempts at another Run's
   identifiers either;
4. the harness's own aliases, derived from the contract by a callable the adapter supplies.

Step 4 is what keeps this module harness-agnostic. `ANTHROPIC_CUSTOM_HEADERS` is *derived*
from contract values and is a Claude name, so it is built in `claude/adapter.py` and passed
in here; Epic 7's `codex` and `local` adapters pass their own and change nothing else.

**AD-5 by absence.** `GITHUB_TOKEN`, `LITELLM_SPEND_KEY`, `DATABASE_URL` and every
`ORCHESTRATOR_*` name are not in the contract and are stripped out of the Project's
variables on the way through. 2.1 already refuses those names when a Project is saved; this
is the second refusal, because AD-5 is a property of the harness environment and not of one
form's validation.

**Nothing here reads the orchestrator's own environment except `PATH` and `LANG`**, the two
values a child needs to run at all and that the runner would supply anyway.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.infrastructure.settings import Settings

#: The normative list, mirrored from `scripts/harness/_common.sh` in its own order.
HARNESS_ENV_CONTRACT: tuple[str, ...] = (
    "ORCH_RUN_ID",
    "ORCH_ATTEMPT_ID",
    "ORCH_STORY_ID",
    "ORCH_HARNESS",
    "ORCH_PROJECT",
    "ORCH_TAGS",
    "ORCH_LANGFUSE_TAGS",
    "TRACEPARENT",
    "LITELLM_BASE_URL",
    "LITELLM_API_KEY",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_ENVIRONMENT",
    "ORCH_LOG_CONTENT",
)

#: The four names outside the contract that every process needs.
#:
#: `infrastructure/process/runner.py::_child_env` overwrites all four on top of whatever
#: mapping it is handed, and adds a fifth of its own (`GIT_TERMINAL_PROMPT=0`) — and it
#: takes `HOME`, `PATH` and `LANG` from *this process's* environment rather than from the
#: mapping, so the values below are not what a child ends up with; they are what this
#: contract says the contract contains. The two agree on `HOME` because
#: `backend-api/Dockerfile` sets `HOME=${AGENT_HOME}` for the process that starts children,
#: and on `TERM` because both fix it at `dumb`.
BASE_NAMES: tuple[str, ...] = ("HOME", "PATH", "LANG", "TERM")

#: Never in a harness environment, whatever asks for them (AD-5).
FORBIDDEN_NAMES = frozenset({"GITHUB_TOKEN", "LITELLM_SPEND_KEY", "DATABASE_URL"})
#: Two families of name a Project may not set, for two reasons. `ORCHESTRATOR_*` is every
#: credential this process holds for itself (AD-5). `OTEL_LOG_*` is the content-logging
#: switch, which AD-5 makes the *instance's* to set from `project.log_prompt_content` and
#: the harness's alias builder adds after this filter has run — without the prefix here, a
#: Project variable named `OTEL_LOG_USER_PROMPTS` would turn prompt logging on while
#: `ORCH_LOG_CONTENT` still said `0`, which is the one state that must not be reachable.
FORBIDDEN_PREFIXES: tuple[str, ...] = ("ORCHESTRATOR_", "OTEL_LOG_")

#: What a harness with no drawable terminal should see.
TERM = "dumb"
#: What this process falls back to when its own environment carries neither name — the same
#: values `infrastructure/process/runner.py` falls back to, for the same reason.
DEFAULT_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
DEFAULT_LANG = "C.UTF-8"

#: The five tag positions, in the order AD-11 pins them.
TAG_POSITIONS = ("run", "attempt", "story", "harness", "project")

#: The contract names whose values are *identifiers of this attempt* rather than
#: configuration or credentials: the Run, the Attempt, the Story, the harness, the Project,
#: the two tag renderings and the traceparent. They are the leading eight of the contract,
#: and this slice is what says so — a name inserted into `HARNESS_ENV_CONTRACT` before
#: `LITELLM_BASE_URL` would join them, which is the right answer for an identifier and the
#: wrong one for anything else, so `tests/unit/test_terminal_command.py` pins the membership
#: as a set rather than trusting the arithmetic.
#:
#: **This is the AD-5 boundary for FR-21's resume command.** Everything in this tuple may be
#: printed on a screen; nothing outside it ever may.
IDENTIFIER_COUNT = 8
IDENTIFIER_NAMES: tuple[str, ...] = HARNESS_ENV_CONTRACT[:IDENTIFIER_COUNT]

#: What an adapter supplies to turn the contract into its own native names: the contract
#: environment in, the harness-native additions out.
AliasBuilder = Callable[[Mapping[str, str]], Mapping[str, str]]


def is_forbidden(name: str) -> bool:
    """Whether AD-5 keeps this name out of every harness environment."""
    return name in FORBIDDEN_NAMES or name.startswith(FORBIDDEN_PREFIXES)


def tag_list(values: Mapping[str, str]) -> list[str]:
    """The five tags, one string per position, in the order AD-11 pins them.

    Every position is always rendered, empty value included: `StepRun.story_id` is `None` on
    an `agent` row outside a story frame, and dropping the position there would give
    LiteLLM's tag list two shapes to parse instead of one.
    """
    return [f"{position}:{values[position]}" for position in TAG_POSITIONS]


def env_for(  # noqa: PLR0913 — one argument per fact; the brief fixes the first four
    attempt: Attempt,
    *,
    run: Run,
    project_slug: str,
    project_env: Mapping[str, str],
    log_content: bool,
    settings: Settings,
    story_id: str | None = None,
    traceparent: str = "",
    aliases: AliasBuilder | None = None,
) -> dict[str, str]:
    """The environment for one attempt: contract, aliases, Project variables, base names.

    `story_id` and `project_slug` are arguments rather than reads, because neither is on
    `Attempt` or `Run`: the story id is `StepRun.story_id` and the slug is
    `RunEnvironment.project_slug`, both of which the walker already holds. `traceparent` is
    `""` until 5.2 supplies one — the key exists from this story on, because the contract
    list is exact.
    """
    contract = _contract(
        attempt,
        run=run,
        project_slug=project_slug,
        log_content=log_content,
        settings=settings,
        story_id=story_id,
        traceparent=traceparent,
    )
    result = {
        **{name: value for name, value in project_env.items() if not is_forbidden(name)},
        **_base_names(settings),
        **contract,
    }
    if aliases is not None:
        result.update(aliases(contract))
    return result


def _base_names(settings: Settings) -> dict[str, str]:
    """`HOME`, `PATH`, `LANG`, `TERM` — what the `ProcessRunner` would add anyway (AD-14)."""
    return {
        "HOME": str(settings.agent_home),
        "PATH": os.environ.get("PATH") or DEFAULT_PATH,
        "LANG": os.environ.get("LANG") or DEFAULT_LANG,
        "TERM": TERM,
    }


def identifiers(
    attempt: Attempt,
    *,
    run: Run,
    project_slug: str,
    story_id: str | None,
    traceparent: str,
) -> dict[str, str]:
    """The eight `IDENTIFIER_NAMES`, in the contract's own order, with AD-10/AD-11's values.

    Its own function because two callers need exactly these eight and no more: `_contract`
    below, which then adds the configuration and the credentials for a harness process, and
    `terminal_contract`, which adds *references* to those instead for a command an Operator
    reads. One statement of the eight, so the two orders and the two tag renderings cannot
    come apart.

    **It takes no `Settings`, and that is a property, not an accident** (AD-5): nothing here
    can reach a credential, so nothing built from it can carry one.
    """
    tags = tag_list(
        {
            "run": str(run.id),
            "attempt": str(attempt.id),
            "story": story_id or "",
            "harness": attempt.harness or "",
            "project": project_slug,
        }
    )
    return {
        "ORCH_RUN_ID": str(run.id),
        "ORCH_ATTEMPT_ID": str(attempt.id),
        "ORCH_STORY_ID": story_id or "",
        "ORCH_HARNESS": attempt.harness or "",
        "ORCH_PROJECT": project_slug,
        # both names carry the same five tags; the JSON array is built from the list
        # rather than by splitting the joined string, so a value holding a comma cannot
        # silently become two items in one of the two renderings and one in the other
        "ORCH_TAGS": ",".join(tags),
        "ORCH_LANGFUSE_TAGS": json.dumps(tags),
        "TRACEPARENT": traceparent,
    }


def shell_reference(name: str) -> str:
    """`$NAME` — how a credential travels in a command an Operator reads (AD-5, FR-21)."""
    return f"${name}"


def terminal_contract(
    attempt: Attempt,
    *,
    run: Run,
    project_slug: str,
    story_id: str | None,
    traceparent: str,
) -> dict[str, str]:
    """The contract as a *command string* may state it: identifiers by value, the rest by name.

    Handed to the same `AliasBuilder` the real environment uses, so the alias list a terminal
    command exports is the harness's own `HARNESS_ENV_ALIASES` and never a second copy of it
    — and `ANTHROPIC_AUTH_TOKEN` comes back as the literal `$LITELLM_API_KEY` because that is
    what this mapping says `LITELLM_API_KEY` is.

    **`ORCH_LOG_CONTENT` arrives as a reference too, so it is never the string `"1"`, so a
    terminal session exports no content-logging switch.** That is the right default and not a
    gap: the switch is per Project and per attempt, the container's own environment holds no
    such variable, and turning prompt logging on for a session the orchestrator is not
    recording would be a decision this command has no standing to make.

    Like `identifiers`, it takes no `Settings` — the whole AD-5 argument for FR-21's command
    is that a value it was never given cannot appear in it.
    """
    known = identifiers(
        attempt, run=run, project_slug=project_slug, story_id=story_id, traceparent=traceparent
    )
    referenced = {name: shell_reference(name) for name in HARNESS_ENV_CONTRACT if name not in known}
    return {**known, **referenced}


def _contract(  # noqa: PLR0913 — the contract is one value per name, by construction
    attempt: Attempt,
    *,
    run: Run,
    project_slug: str,
    log_content: bool,
    settings: Settings,
    story_id: str | None,
    traceparent: str,
) -> dict[str, str]:
    """Exactly `HARNESS_ENV_CONTRACT`, in its order, with the values AD-10 and AD-11 pin."""
    return {
        **identifiers(
            attempt,
            run=run,
            project_slug=project_slug,
            story_id=story_id,
            traceparent=traceparent,
        ),
        "LITELLM_BASE_URL": settings.litellm_base_url,
        "LITELLM_API_KEY": settings.litellm_api_key.get_secret_value(),
        "LANGFUSE_BASE_URL": settings.langfuse_base_url,
        "LANGFUSE_PUBLIC_KEY": settings.langfuse_public_key,
        "LANGFUSE_SECRET_KEY": settings.langfuse_secret_key.get_secret_value(),
        "LANGFUSE_ENVIRONMENT": settings.langfuse_environment,
        "ORCH_LOG_CONTENT": "1" if log_content else "0",
    }
