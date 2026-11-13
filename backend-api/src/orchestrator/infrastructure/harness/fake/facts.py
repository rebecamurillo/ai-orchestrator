"""The `fake` harness's extractor: the result envelope its script prints, read as usage facts."""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import AttemptFacts, UsageFact
from orchestrator.domain.ports.log_facts import LogFactsCapabilities
from orchestrator.infrastructure.harness.claude.result import result_object, usage_from
from orchestrator.infrastructure.harness.jsonl import read_text

NO_ENVELOPE = "no result envelope"
MAIN = "main"


class FakeLogFacts:
    """`LogFacts` for the `fake` harness."""

    name = "fake"
    version = 1
    capabilities = LogFactsCapabilities(
        per_request_usage=False, activity=False, events=False, harness_money_per_model=False
    )

    def extract(self, attempt: Attempt, log_path: str) -> AttemptFacts:
        usage = usage_from(result_object(read_text(Path(log_path))))
        if usage is None:
            return AttemptFacts(status="partial", reason=NO_ENVELOPE)
        model = attempt.model or "fake"

        def fact(usage_class: str, **values: object) -> UsageFact:
            return UsageFact.model_validate(
                {
                    "source": "harness",
                    "model": model,
                    "conversation": MAIN,
                    "usage_class": usage_class,
                    **values,
                }
            )

        return AttemptFacts(
            usage=(
                fact("input_uncached", tokens=usage.tokens_in),
                fact("output", tokens=usage.tokens_out),
                fact("money", usd=usage.cost_usd),
            )
        )
