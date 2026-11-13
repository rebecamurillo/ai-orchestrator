"""The one role an attempt is counted under (ARCHITECTURE §4, RM-8)."""

from __future__ import annotations

import re

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun

SENIOR = "senior"
CHAT = "chat"
AS_DECLARED = "as declared: {}"

_INDEX = re.compile(r"\[\d+\]$")


def role_of(attempt: Attempt, row: StepRun) -> str:
    if attempt.role == "consult":
        return SENIOR
    if attempt.role == "session":
        return CHAT
    if row.role:
        return row.role
    return AS_DECLARED.format(_INDEX.sub("", row.path.rsplit(".", 1)[-1]))
