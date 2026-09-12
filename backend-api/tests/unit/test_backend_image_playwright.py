"""The backend image carries Chromium's system libraries, asserted textually.

A harness runs a target repository's UI gate (`make e2e-ui`) inside this container as the
non-root `agent` (NFR-3) — who cannot `apt-get` anything, so the shared libraries the
browser links against must come from the image. An image without them turns every
Playwright story into `blocked` with "Host system is missing dependencies to run
browsers", which no agent can act on.

The browser build itself is deliberately *not* baked: `playwright install chromium` needs
no root, lands under `HOME` on the persistent `agent-home` volume, and belongs to the
target repository's own setup step (`make install-e2e` here), at whatever Playwright
version that repository pins.

What is checked, textually like `test_dockerfiles.py`:

- **The libraries are installed at build time, as root.** The e2e gate's stack re-hardens
  and has no sudo (`docker-compose.e2e.yml`), and even where sudo works, re-installing
  system libraries every Run is time an agent should not spend.
- **The version that selects the package list is the version web-client pins.** The ARG
  default and `web-client/package.json` are two copies of one pin; this is the gate that
  keeps them one value.
"""

from __future__ import annotations

import json
import re

from tests.unit.conftest import REPO_ROOT

BACKEND_DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"
WEB_PACKAGE_JSON = REPO_ROOT / "web-client" / "package.json"


def dockerfile() -> str:
    assert BACKEND_DOCKERFILE.is_file(), f"{BACKEND_DOCKERFILE} is missing"
    return BACKEND_DOCKERFILE.read_text()


def test_the_image_installs_chromiums_system_libraries() -> None:
    """`playwright install-deps chromium` is the one supported source of the apt list."""
    joined = re.sub(r"\\\n", " ", dockerfile())

    assert re.search(r"playwright@\S*\s+install-deps\s+chromium", joined)


def test_the_libraries_are_installed_as_root() -> None:
    """Everything before the first `USER` runs as root; the install must be there."""
    text = dockerfile()
    at_install = text.index("install-deps")
    users_before = re.findall(r"^USER\s+(\S+)", text[:at_install], re.MULTILINE)

    assert users_before == [], "install-deps runs after a USER switch — no longer root"


def test_the_playwright_pin_is_the_one_web_client_pins() -> None:
    """Two copies of one pin: the ARG default and `@playwright/test` in package.json."""
    match = re.search(r"^ARG\s+PLAYWRIGHT_VERSION=(\S+)$", dockerfile(), re.MULTILINE)
    assert match is not None, "no `ARG PLAYWRIGHT_VERSION=<pin>` in the backend Dockerfile"

    package = json.loads(WEB_PACKAGE_JSON.read_text())
    pinned = package["devDependencies"]["@playwright/test"]

    assert match.group(1) == pinned, f"Dockerfile pins {match.group(1)}, web-client {pinned}"
