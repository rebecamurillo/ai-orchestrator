"""Opengrep SARIF: results as findings, matched between base and head, and the stored baseline.

A finding is identified by its tool, rule, path after rename detection and the whitespace-collapsed
hash of the source text it matched, so code that only moved inside a file is the same finding
(ARCHITECTURE §7.3).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from orchestrator.application.analysis.duplication import FILE_SCHEME, relative_sarif

Severity = Literal["high", "medium", "low"]
Kind = Literal["security", "bug"]

SCANNED_FILES = "files"
SECURITY_TAG = "security"
CWE_PATTERN = r"CWE-\d+"
HIGH_SCORE = 7.0
MEDIUM_SCORE = 4.0
DEFAULT_LEVEL = "warning"
LEVEL_SEVERITY: Mapping[str, Severity] = {
    "error": "high",
    "warning": "medium",
    "note": "low",
    "none": "low",
}


class SarifUnreadable(Exception):
    """The report is not SARIF this module can read."""


@dataclass(frozen=True)
class Finding:
    tool: str
    rule_id: str
    path: str
    line: int
    text_hash: str
    severity: Severity
    kind: Kind
    cwe: tuple[str, ...]
    run_index: int
    result_index: int

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.tool, self.rule_id, self.path, self.text_hash)


@dataclass(frozen=True)
class Matched:
    new: tuple[Finding, ...]
    unchanged: tuple[Finding, ...]
    absent: tuple[Finding, ...]


def _scanned_path(uri: str, root: str) -> str:
    path = uri.removeprefix(FILE_SCHEME).removeprefix(f"{root.rstrip('/')}/")
    return path.removeprefix(f"{SCANNED_FILES}/")


def _matched_text(region: Mapping[str, Any], source: str | None) -> str:
    if source is None:
        snippet = region.get("snippet")
        return str(snippet["text"]) if isinstance(snippet, dict) else ""
    start = int(region["startLine"])
    end = int(region.get("endLine", start))
    lines = source.splitlines()[start - 1 : end]
    if not lines:
        return ""
    first = int(region["startColumn"]) - 1 if "startColumn" in region else 0
    last = int(region["endColumn"]) - 1 if "endColumn" in region else None
    if len(lines) == 1:
        return lines[0][first:last]
    lines[0] = lines[0][first:]
    lines[-1] = lines[-1][:last]
    return "\n".join(lines)


def _rule(rules: Sequence[Mapping[str, Any]], rule_id: str, index: object) -> Mapping[str, Any]:
    if isinstance(index, int) and 0 <= index < len(rules):
        return rules[index]
    return next((r for r in rules if r.get("id") == rule_id), {})


def _severity(rule: Mapping[str, Any], level: object) -> Severity:
    score = (rule.get("properties") or {}).get("security-severity")
    try:
        value = float(score) if score is not None else None
    except ValueError, TypeError:
        value = None
    if value is not None:
        return "high" if value >= HIGH_SCORE else "medium" if value >= MEDIUM_SCORE else "low"
    named = level or (rule.get("defaultConfiguration") or {}).get("level") or DEFAULT_LEVEL
    return LEVEL_SEVERITY.get(str(named), "medium")


def _tags(rule: Mapping[str, Any]) -> list[str]:
    return [str(t) for t in (rule.get("properties") or {}).get("tags") or ()]


def parse_findings(
    text: str,
    *,
    root: str,
    read_source: Callable[[str], str | None],
    renames: Mapping[str, str],
) -> list[Finding]:
    """Every result of every run; `renames` maps a base path to its head path."""
    found: list[Finding] = []
    try:
        for run_index, run in enumerate(json.loads(text)["runs"]):
            driver = run["tool"]["driver"]
            rules = driver.get("rules") or []
            for result_index, result in enumerate(run.get("results") or []):
                physical = result["locations"][0]["physicalLocation"]
                region = physical["region"]
                path = _scanned_path(physical["artifactLocation"]["uri"], root)
                rule = _rule(rules, result["ruleId"], result.get("ruleIndex"))
                tags = _tags(rule)
                body = " ".join(_matched_text(region, read_source(path)).split())
                found.append(
                    Finding(
                        tool=driver["name"],
                        rule_id=result["ruleId"],
                        path=renames.get(path, path),
                        line=int(region["startLine"]),
                        text_hash=hashlib.sha256(body.encode()).hexdigest(),
                        severity=_severity(rule, result.get("level")),
                        kind="security" if any(t.lower() == SECURITY_TAG for t in tags) else "bug",
                        cwe=tuple(dict.fromkeys(re.findall(CWE_PATTERN, " ".join(tags)))),
                        run_index=run_index,
                        result_index=result_index,
                    )
                )
    except ValueError, KeyError, TypeError, AttributeError, IndexError:
        raise SarifUnreadable from None
    return found


def match(base: Sequence[Finding], head: Sequence[Finding]) -> Matched:
    """Per key the first `min(base, head)` head findings are unchanged, the rest new."""
    by_key: dict[tuple[str, str, str, str], list[Finding]] = defaultdict(list)
    for finding in base:
        by_key[finding.key].append(finding)
    new: list[Finding] = []
    unchanged: list[Finding] = []
    remaining = {key: len(items) for key, items in by_key.items()}
    for finding in head:
        if remaining.get(finding.key, 0) > 0:
            remaining[finding.key] -= 1
            unchanged.append(finding)
        else:
            new.append(finding)
    absent = [f for key, items in by_key.items() for f in items[len(items) - remaining[key] :]]
    absent.sort(key=lambda f: (f.run_index, f.result_index))
    return Matched(tuple(new), tuple(unchanged), tuple(absent))


def _stamp(document: dict[str, Any], states: Mapping[tuple[int, int], str]) -> None:
    for run_index, run in enumerate(document["runs"]):
        for result_index, result in enumerate(run.get("results") or []):
            result["baselineState"] = states[(run_index, result_index)]


def _strip_scanned(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _strip_scanned(item)
    elif isinstance(value, dict):
        if isinstance(value.get("uri"), str):
            value["uri"] = value["uri"].removeprefix(f"{SCANNED_FILES}/")
            value.pop("uriBaseId", None)
        for item in value.values():
            _strip_scanned(item)


def with_baseline(
    head_text: str | None, base_text: str | None, matched: Matched, *, root: str
) -> str:
    """The head SARIF with each result's `baselineState`, the fixed base results appended.

    Without a head report (nothing to scan at head) the base report's tools carry the absent
    results alone; without a base report nothing is absent. `root` is the head side's scratch
    folder; no scratch path is kept.
    """
    base = json.loads(base_text) if base_text is not None else {"runs": []}
    document = json.loads(head_text if head_text is not None else base_text or '{"runs": []}')
    if head_text is None:
        for run in document["runs"]:
            run["results"] = []
    states = {(f.run_index, f.result_index): "new" for f in matched.new}
    states.update({(f.run_index, f.result_index): "unchanged" for f in matched.unchanged})
    _stamp(document, states)
    runs = {run["tool"]["driver"]["name"]: run for run in document["runs"]}
    for finding in matched.absent:
        base_run = base["runs"][finding.run_index]
        original = base_run["results"][finding.result_index]
        run = runs.get(finding.tool)
        if run is None:
            run = {"tool": {"driver": {"name": finding.tool, "rules": []}}, "results": []}
            document["runs"].append(run)
            runs[finding.tool] = run
        driver = run["tool"]["driver"]
        listed = driver.setdefault("rules", [])
        descriptor = _rule(
            base_run["tool"]["driver"].get("rules") or [],
            finding.rule_id,
            original.get("ruleIndex"),
        )
        if descriptor and all(r.get("id") != finding.rule_id for r in listed):
            listed.append(descriptor)
        original.pop("ruleIndex", None)
        original["baselineState"] = "absent"
        run["results"].append(original)
    stored = relative_sarif(json.dumps(document), root)
    cleaned = json.loads(stored)
    _strip_scanned(cleaned)
    return json.dumps(cleaned, ensure_ascii=False)
