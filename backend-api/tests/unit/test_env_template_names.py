"""The template names both `.env.example` copies carry agree with each other and the code.

Story 7, 2026-11-06: a dev stack reads the root copy and `install.sh` the deploy one, so a
`READINESS_TEMPLATE` or `ROOT_TEMPLATES` that differs between them points two instances at
different templates; `READINESS_TEMPLATE` must also be the name `Settings` defaults to.
"""

from __future__ import annotations

import pytest

from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

DEPLOY_ENV_EXAMPLE = REPO_ROOT / "deploy" / ".env.example"


@pytest.mark.parametrize("variable", ["READINESS_TEMPLATE", "ROOT_TEMPLATES"])
def test_both_copies_name_the_same_value(variable: str) -> None:
    root = parse_env_example(ENV_EXAMPLE)
    deploy = parse_env_example(DEPLOY_ENV_EXAMPLE)

    assert root[variable]
    assert deploy[variable] == root[variable]


def test_the_readiness_template_is_the_settings_default() -> None:
    root = parse_env_example(ENV_EXAMPLE)

    assert (
        root["READINESS_TEMPLATE"]
        == Settings.model_fields["readiness_template"].default
        == "harness-readiness"
    )


def test_the_root_templates_are_the_four_shipped_roots_that_belong_on_the_menu() -> None:
    root = parse_env_example(ENV_EXAMPLE)

    assert (
        root["ROOT_TEMPLATES"]
        == "staged-initiative-hub,staged-initiative-repo,repo-init,agent-smoke"
    )
