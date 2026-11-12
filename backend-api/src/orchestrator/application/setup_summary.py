"""What a setup record says, reduced to what the harness list and the version read show."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from orchestrator.domain.entities.setup_run import ScriptRun, SetupRun

#: `timeout $SETUP_SCRIPT_TIMEOUT` exits 124; the record has no separate timeout field.
TIMEOUT_EXIT = 124
#: Which catalog count a harness shows; `local` runs on opencode.
CATALOG_OF = {"claude": "claude", "codex": "codex", "opencode": "opencode", "local": "opencode"}


@dataclass(frozen=True)
class SetupFailure:
    script: str
    reason: str


@dataclass(frozen=True)
class HarnessSetup:
    at: datetime
    trigger: str
    ok: bool
    failures: tuple[SetupFailure, ...]
    skills: int


def script_reason(script: ScriptRun) -> str:
    parts: list[str] = []
    if script.exit == TIMEOUT_EXIT:
        parts.append("timeout")
    elif script.exit != 0:
        parts.append(f"exit {script.exit}")
    if script.clashes:
        parts.append(f"clashes: {', '.join(script.clashes)}")
    return "; ".join(parts) or "failed"


def failures(record: SetupRun) -> list[SetupFailure]:
    found = []
    if not record.bmad.ok:
        found.append(SetupFailure("bmad", record.bmad.reason or "failed"))
    found += [SetupFailure(s.name, script_reason(s)) for s in record.scripts if not s.ok]
    return found


def harness_setup(record: SetupRun | None, harness: str) -> HarnessSetup | None:
    if record is None:
        return None
    found = failures(record)
    catalog = CATALOG_OF.get(harness)
    return HarnessSetup(
        at=record.at,
        trigger=record.trigger,
        ok=not found,
        failures=tuple(found),
        skills=getattr(record.catalog, catalog) if catalog else 0,
    )


def bmad_installed(record: SetupRun | None) -> str | None:
    if record is None or record.bmad.choice != "installed" or not record.bmad.ok:
        return None
    return record.bmad.version


def bmad_choice(record: SetupRun | None) -> str | None:
    return record.bmad.choice if record is not None else None
