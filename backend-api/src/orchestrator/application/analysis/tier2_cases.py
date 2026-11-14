"""Tier 2 test-case signals: what the JUnit reports of base, head and the fail-to-pass run say."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence

from orchestrator.application.analysis.tier1a import Count
from orchestrator.application.analysis.tier2_reports import Case, is_import_error

EXECUTED = "code.tests_executed"
FAIL_TO_PASS = "code.fail_to_pass"
OUTCOMES = ("fail", "pass", "import_error", "skipped", "not_run")
ABSENT = "absent from the report"
Identity = tuple[str | None, str, str]


def mapped(file: str | None, renames: Mapping[str, str]) -> str | None:
    return None if file is None else renames.get(file, file)


def identity(case: Case, renames: Mapping[str, str]) -> Identity:
    return (mapped(case.file, renames), case.classname, case.name)


def executed_counts(
    base: Sequence[Case],
    head: Sequence[Case],
    renames: Mapping[str, str],
    of: Callable[[str | None], str],
) -> tuple[Count, ...]:
    before = {identity(c, renames) for c in base}
    after = {identity(c, {}) for c in head}
    added = Counter(of(c.file) for c in head if identity(c, {}) not in before)
    removed = Counter(
        of(mapped(c.file, renames)) for c in base if identity(c, renames) not in after
    )
    total = Counter(of(c.file) for c in head)
    counts = [
        Count(EXECUTED, f"{cls}:{label}", figures[cls], None)
        for cls in sorted({*added, *removed, *total})
        for label, figures in (("added", added), ("removed", removed), ("total", total))
    ]
    return tuple(counts)


def absent(case: Case, produced: Sequence[Case]) -> tuple[str, str]:
    """A new case the report does not list: an import error shows as a missing case."""
    if case.file is not None:
        stem = case.file.rsplit(".", 1)[0].replace("/", ".")
        if any(
            is_import_error(c) and (c.file == case.file or stem in c.classname or stem in c.name)
            for c in produced
        ):
            return "import_error", "import error"
    return "not_run", ABSENT


def verdict(case: Case, produced: Sequence[Case]) -> tuple[str, str]:
    found = next((c for c in produced if identity(c, {}) == identity(case, {})), None)
    if found is None:
        return absent(case, produced)
    if found.outcome == "passed":
        return "pass", ""
    if found.outcome == "skipped":
        return "skipped", found.message
    if is_import_error(found):
        return "import_error", "import error"
    return "fail", found.message


def fail_to_pass(new: Sequence[Case], produced: Sequence[Case]) -> tuple[tuple[Count, ...], bytes]:
    """The counts per outcome and the JSON body listing each new case with its reason."""
    rows = [(case, *verdict(case, produced)) for case in new]
    body = json.dumps(
        [
            {"file": c.file, "classname": c.classname, "name": c.name, "outcome": o, "reason": r}
            for c, o, r in rows
        ]
    ).encode()
    tally = Counter(outcome for _, outcome, _ in rows)
    return tuple(Count(FAIL_TO_PASS, o, tally[o], None) for o in OUTCOMES), body
