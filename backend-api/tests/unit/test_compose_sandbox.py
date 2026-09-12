"""The sandbox split: agents may install anything, except on the gate's stack.

Operator decision, 2026-09-11: a target repository's own install script may need apt
packages, and the harness runs as the non-root `agent` (NFR-3) — so the image carries
`sudo` with a NOPASSWD entry, and the base stack leaves `backend-api` unhardened so
setuid actually works (`test_compose_services.py` holds that half). The one stack that
never runs a real agent — `make e2e`'s, on the scripted `fake` harness — re-hardens in
its own overlay, which is the half this module holds.

What is checked, textually like `test_dockerfiles.py`:

- **The image carries sudo and the agent's NOPASSWD entry, written as root.** After
  `USER agent` nobody can write `/etc/sudoers.d`.
- **The e2e overlay re-hardens the backend.** `cap_drop: ALL` and `no-new-privileges`
  moved here from the base file rather than vanishing; without them the gate's stack
  would inherit the sandbox for a harness that has no use for it.
"""

from __future__ import annotations

import re

from tests.unit.conftest import REPO_ROOT

BACKEND_DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"
E2E_OVERLAY = REPO_ROOT / "docker-compose.e2e.yml"


def dockerfile() -> str:
    assert BACKEND_DOCKERFILE.is_file(), f"{BACKEND_DOCKERFILE} is missing"
    return BACKEND_DOCKERFILE.read_text()


def overlay_code() -> str:
    """The overlay with its whole-line comments dropped, like `test_dockerfiles.code`."""
    assert E2E_OVERLAY.is_file(), f"{E2E_OVERLAY} is missing"
    kept = [
        line for line in E2E_OVERLAY.read_text().splitlines() if not line.strip().startswith("#")
    ]
    return "\n".join(kept) + "\n"


# ── the image carries sudo for the agent ─────────────────────────────────────


def test_the_image_installs_sudo() -> None:
    joined = re.sub(r"\\\n", " ", dockerfile())
    match = re.search(r"apt-get install[^&]*", joined)

    assert match is not None, "no `apt-get install` block found in the backend Dockerfile"
    assert re.search(r"\bsudo\b", match.group(0))


def test_the_agent_has_a_nopasswd_entry_written_as_root() -> None:
    text = dockerfile()
    at_entry = text.index("/etc/sudoers.d/agent")
    users_before = re.findall(r"^USER\s+(\S+)", text[:at_entry], re.MULTILINE)

    assert users_before == [], "the sudoers entry is written after a USER switch"
    assert "agent ALL=(ALL) NOPASSWD:ALL" in text
    assert re.search(r"chmod 0440 /etc/sudoers\.d/agent", text)


# ── the gate's stack takes the hardening back ────────────────────────────────


def test_the_e2e_overlay_drops_every_capability() -> None:
    assert re.search(r"cap_drop:\s*\n\s*- ALL", overlay_code())


def test_the_e2e_overlay_refuses_privilege_escalation() -> None:
    assert "no-new-privileges:true" in overlay_code()


def test_the_hardening_sits_under_the_backend_service() -> None:
    """The overlay names two services; the hardening must land on `backend-api`, not on
    `postgres`, whose block precedes it."""
    text = overlay_code()
    at_backend = text.index("backend-api:")

    assert text.index("cap_drop:") > at_backend
    assert text.index("no-new-privileges:true") > at_backend
