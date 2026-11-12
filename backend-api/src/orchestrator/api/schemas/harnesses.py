"""The HTTP shape of a harness row (SPEC CAP-3, CAP-8, AD-10).

Two Operator rulings have widened this schema, and both were the same edit to the same two
exact closed-set equalities — `tests/unit/test_harnesses_router.py::
test_harness_out_of_renders_every_field` and `tests/e2e/test_harnesses.py::
test_the_response_is_the_one_list_envelope`. Neither ruling weakened them; each added names.

- **CAP-8** added `last_readiness_run_id` and `lines`, taking both equalities from five names
  to seven.
- **Story 2** (orchestrator-deploy-folder epic 1, 2026-11-11) added `setup`, taking both to
  nine; it is the last setup run's summary, `null` when no record exists.
- **Story 7.3** (the Operator ruled in session on 2026-09-10) added `models`, taking both to
  eight. `local` is the harness that needs it: an Operator picks from `LOCAL_MODELS`, the
  aliases this instance's Gateway actually routes, rather than typing a model name the host
  serves no route for. Every other harness answers `[]`, which is the statement that it takes
  a free-text model name.

`models` is composed per request from `Settings` and is not stored on the row —
`infrastructure/harness/models.py` says why a stored copy would be wrong.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.application.setup_summary import HarnessSetup
from orchestrator.application.use_cases.harness_models import ModelsAnswer
from orchestrator.domain.entities.harness import EvaluationLine, Harness


class ProbeResultOut(BaseModel):
    """The HTTP shape of a harness probe result (story 2-1).

    HTTP 200 in both the `ok=True` and `ok=False` cases — failures are reported in the body,
    not through HTTP error codes.  `failing_reason` is `null` when `ok` is `True`.
    """

    ok: bool
    failing_reason: str | None
    version: str
    models: list[str]


class ModelsOut(BaseModel):
    """The models a harness can use, and where that list comes from."""

    harness: str
    source: Literal["litellm", "configured", "none"] = Field(
        description="`litellm`: the instance's LiteLLM key's model list; `configured`: "
        "`LOCAL_MODELS`; `none`: no list is available, ask the user for a model name."
    )
    models: list[str]
    note: str | None = Field(description="What the list is, or why there is none.")
    code: str | None = Field(description="Finding code when `source` is `none`.")
    guide: str | None = Field(description="Guide page that explains `code`.")

    @classmethod
    def of(cls, answer: ModelsAnswer) -> ModelsOut:
        return cls(
            harness=answer.harness,
            source=answer.source,
            models=list(answer.models),
            note=answer.note,
            code=answer.code,
            guide=answer.guide,
        )


class EvaluationLineOut(BaseModel):
    """One line `evaluate` produced: `{check, ok, text}`, the brief's own literal shape."""

    check: str
    ok: bool
    text: str

    @classmethod
    def of(cls, line: EvaluationLine) -> EvaluationLineOut:
        return cls(check=line.check, ok=line.ok, text=line.text)


class SetupFailureOut(BaseModel):
    script: str
    reason: str


class HarnessSetupOut(BaseModel):
    """What the last setup run did, for one harness."""

    at: UtcTimestamp
    trigger: str
    ok: bool
    failures: list[SetupFailureOut]
    skills: int

    @classmethod
    def of(cls, setup: HarnessSetup) -> HarnessSetupOut:
        return cls(
            at=setup.at,
            trigger=setup.trigger,
            ok=setup.ok,
            failures=[SetupFailureOut(script=f.script, reason=f.reason) for f in setup.failures],
            skills=setup.skills,
        )


class HarnessOut(BaseModel):
    """One row of `GET /harnesses`."""

    name: str
    enabled: bool
    last_readiness_at: UtcTimestamp | None
    failing_check: str | None
    version_pin: str
    #: Defaulted, not merely nullable: the generated client type marks both optional, so
    #: `web-client/tests/unit/harness-list.test.ts`'s and `newwf-state.test.ts`'s existing
    #: fixtures — frozen, and predating this story — keep compiling unchanged. `model_dump()`
    #: still renders both keys always; only the OpenAPI `required` list changes.
    last_readiness_run_id: UUID | None = None
    lines: list[EvaluationLineOut] = Field(default_factory=list)
    #: The models this instance offers for this harness, in `LOCAL_MODELS`' own order; `[]`
    #: for a harness that takes a free-text model name. Defaulted for the same reason the two
    #: fields above are — the generated client type marks it optional, so `web-client`'s
    #: existing frozen fixtures keep compiling — and `model_dump()` still renders the key
    #: always, so both closed-set equalities see it.
    models: list[str] = Field(default_factory=list)
    #: Defaulted for the same reason; `model_dump()` still renders the key.
    setup: HarnessSetupOut | None = None

    @classmethod
    def of(
        cls, harness: Harness, models: Sequence[str] = (), setup: HarnessSetup | None = None
    ) -> HarnessOut:
        """The stored row, plus the models this instance currently offers for it.

        `models` is an argument rather than a field read off `harness`, because it is not on
        the row and should not be: it is `Settings`, and the caller is the one holding them.
        """
        return cls(
            name=harness.name,
            enabled=harness.enabled,
            last_readiness_at=harness.last_readiness_at,
            failing_check=harness.failing_check,
            version_pin=harness.version_pin,
            last_readiness_run_id=harness.last_readiness_run_id,
            lines=[EvaluationLineOut.of(line) for line in harness.lines],
            models=list(models),
            setup=HarnessSetupOut.of(setup) if setup is not None else None,
        )
