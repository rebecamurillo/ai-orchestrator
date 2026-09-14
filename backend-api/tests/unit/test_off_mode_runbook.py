"""Runbook-source consistency checks for off-mode section of DEPLOY.md (story 9-6).

The backend test locates the section by finding the heading string in DEPLOY.md and slicing
from there to the next same-level heading or end of file.  It asserts specific names and log
strings, not prose, so rewording the section does not break it, but renaming a field or log
event does (story 9-6 Design Notes).

No credential value is read or asserted (hard rule 5, AD-5).
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
RUNBOOK_HEADING = "Running without the host services"

_SETTINGS_PY = (
    PROJECT_ROOT / "backend-api" / "src" / "orchestrator" / "infrastructure" / "settings.py"
)
_MAIN_PY = PROJECT_ROOT / "backend-api" / "src" / "orchestrator" / "main.py"


def _section_text() -> str:
    """Return the text of the runbook section, from the heading to the next ## or end."""
    deploy_md = (PROJECT_ROOT / "DEPLOY.md").read_text(encoding="utf-8")
    heading_marker = f"## {RUNBOOK_HEADING}"
    start = deploy_md.index(heading_marker)
    # find the next ## heading after the section starts (skip the heading itself)
    next_heading = deploy_md.find("\n## ", start + len(heading_marker))
    if next_heading == -1:
        return deploy_md[start:]
    return deploy_md[start:next_heading]


# --- LITELLM_BASE_URL appears in both the runbook section and settings.py ---


def test_runbook_names_litellm_base_url() -> None:
    """The runbook section names LITELLM_BASE_URL and settings.py defines litellm_base_url."""
    section = _section_text()
    assert "LITELLM_BASE_URL" in section, "DEPLOY.md runbook section must name LITELLM_BASE_URL"

    settings_src = _SETTINGS_PY.read_text(encoding="utf-8")
    assert "litellm_base_url" in settings_src, (
        "settings.py must define litellm_base_url (env var LITELLM_BASE_URL)"
    )


# --- LANGFUSE_BASE_URL appears in both the runbook section and settings.py ---


def test_runbook_names_langfuse_base_url() -> None:
    """The runbook section names LANGFUSE_BASE_URL and settings.py defines langfuse_base_url."""
    section = _section_text()
    assert "LANGFUSE_BASE_URL" in section, "DEPLOY.md runbook section must name LANGFUSE_BASE_URL"

    settings_src = _SETTINGS_PY.read_text(encoding="utf-8")
    assert "langfuse_base_url" in settings_src, (
        "settings.py must define langfuse_base_url (env var LANGFUSE_BASE_URL)"
    )


# --- "gateway disabled" appears in both the runbook section and main.py ---


def test_runbook_log_gateway_disabled() -> None:
    """The runbook section documents 'gateway disabled' and main.py logs it."""
    section = _section_text()
    assert "gateway disabled" in section, (
        "DEPLOY.md runbook section must document the 'gateway disabled' log event"
    )

    main_src = _MAIN_PY.read_text(encoding="utf-8")
    assert '"gateway disabled"' in main_src, (
        'main.py must emit log.warning("gateway disabled", ...)'
    )


# --- "tracing disabled" appears in both the runbook section and main.py ---


def test_runbook_log_tracing_disabled() -> None:
    """The runbook section documents 'tracing disabled' and main.py logs it."""
    section = _section_text()
    assert "tracing disabled" in section, (
        "DEPLOY.md runbook section must document the 'tracing disabled' log event"
    )

    main_src = _MAIN_PY.read_text(encoding="utf-8")
    assert '"tracing disabled"' in main_src, (
        'main.py must emit log.warning("tracing disabled", ...)'
    )
