"""The workflow Templates the e2e suite runs — its own, never the shipped ones.

Operator ruling (2026-10-15): no test reads, runs or asserts on `templates/*.yaml` at the
repository root. The shipped files are exemplars the Operator edits, reorders and retires at
will, and a suite that followed them proved a workflow rather than the product: a shipped
edit went red here, a shipped skill nobody installs on the gate's stack refused every Run at
pre-flight. What the suite owes is that the parser reads and the walker executes
instructions — so every workflow it needs lives in `tests/e2e/templates/`, is posted through
the same `POST /templates/{name}/versions` an Operator uses, under a name no earlier run can
have taken, and dispatches internal skills only (`tests/unit/test_e2e_fixture_templates.py`
pins both facts against the files themselves, with no stack).

Tokens: `@NAME@` is the name a fixture is saved under — the API requires the text and the
path to agree — and `@STORY@` / `@EPIC@` name the callee a `uses: template` row follows.
Callees are saved first, unpinned calls resolving to the callee's latest at validate time
(Operator decision 2026-10-02).
"""

from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

TEMPLATES = "/api/v1/templates"

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404

EPIC = "epic.yaml"
STORY = "story.yaml"
HUB = "hub.yaml"
HUB_EPIC = "hub-epic.yaml"
HUB_STORY = "hub-story.yaml"
REPO_INIT = "repo-init.yaml"

TOKEN = re.compile(r"@([A-Z_]+)@")

#: The one line every fixture opens its version with; `ensure_named` bumps it in place.
VERSION_LINE = "version: 1\n"


def fixture_text(file: str, **tokens: str) -> str:
    """One fixture's text with every `@TOKEN@` filled in; a token left unfilled is a failure
    of the test that called, named, rather than YAML the stack rejects for a reason nobody
    reads back to this file."""
    text = (TEMPLATES_DIR / file).read_text()
    for key, value in tokens.items():
        text = text.replace(f"@{key}@", value)
    left = sorted(set(TOKEN.findall(text)))
    if left:
        pytest.fail(f"{file}: tokens not filled in: {', '.join(left)}")
    return text


def unique(prefix: str) -> str:
    """A Template name no earlier run of the suite can have taken: there is no `DELETE`, and
    a suite may run twice against one stack."""
    return f"{prefix}-{uuid4().hex}"


def save_fixture(api: httpx.Client, file: str, name: str, **callees: str) -> str:
    """Post `file` as `name@1`; returns the name so a caller can bind it as a callee."""
    response = api.post(
        f"{TEMPLATES}/{name}/versions",
        json={"yaml": fixture_text(file, NAME=name, **callees)},
    )
    assert response.status_code == HTTP_CREATED, response.text
    return name


def save_epic_pair(api: httpx.Client, prefix: str = "e2e-epic") -> tuple[str, str]:
    """The story callee, then the epic that follows it: `(epic_name, story_name)`."""
    story = save_fixture(api, STORY, unique(f"{prefix}-story"))
    epic = save_fixture(api, EPIC, unique(prefix), STORY=story)
    return epic, story


def save_hub_trio(api: httpx.Client, prefix: str = "e2e-hub") -> tuple[str, str, str]:
    """Hub-story, hub-epic, hub — leaf first: `(hub_name, epic_name, story_name)`."""
    story = save_fixture(api, HUB_STORY, unique(f"{prefix}-story"))
    epic = save_fixture(api, HUB_EPIC, unique(f"{prefix}-epic"), STORY=story)
    hub = save_fixture(api, HUB, unique(prefix), EPIC=epic)
    return hub, epic, story


def save_repo_init(api: httpx.Client, prefix: str = "e2e-repo-init") -> str:
    return save_fixture(api, REPO_INIT, unique(prefix))


def ensure_named(api: httpx.Client, file: str, name: str) -> int:
    """`file` stored under a *fixed* name — the one the stack's `INIT_TEMPLATE` names, which
    `POST /repositories/{id}/init` resolves by name and latest version — and the version
    number the stack will dispatch.

    Idempotent against a stack that outlives the suite: posts `1` when the name holds
    nothing, the next number when the stored latest differs from this checkout's fixture (a
    fixture edit must reach the stack, and a stored version is immutable — AD-15), and
    nothing when they agree.
    """
    listed = api.get(f"{TEMPLATES}/{name}/versions")
    if listed.status_code == HTTP_NOT_FOUND:
        save_fixture(api, file, name)
        return 1
    assert listed.status_code == HTTP_OK, listed.text
    latest = max(listed.json()["items"])
    stored = api.get(f"{TEMPLATES}/{name}/{latest}")
    assert stored.status_code == HTTP_OK, stored.text
    wanted = fixture_text(file, NAME=name).replace(VERSION_LINE, f"version: {latest}\n", 1)
    if stored.json()["yaml"] == wanted:
        return latest
    bumped = wanted.replace(f"version: {latest}\n", f"version: {latest + 1}\n", 1)
    response = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": bumped})
    assert response.status_code == HTTP_CREATED, response.text
    return latest + 1


#: The name the gate's stacks give `INIT_TEMPLATE` (`docker-compose.e2e.yml`, the `e2e-api`
#: job): `POST /repositories/{id}/init` dispatches it by name, so the suite stores
#: `repo-init.yaml` under exactly this name with `ensure_named` before the first `POST`.
E2E_INIT_TEMPLATE = "e2e-repo-init"
