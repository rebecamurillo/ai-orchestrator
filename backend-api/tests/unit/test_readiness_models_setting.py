"""`READINESS_MODELS`: the model each harness's readiness Run binds (SPEC CAP-8, AD-20).

A readiness Run that binds no model leaves `{{model}}` empty in `templates/story.yaml`, and
the harness falls back to its own built-in default — for Claude Code that is a model the
operator's Gateway does not serve, so the Run fails on the first agent step for a reason
that has nothing to do with readiness. This contract is what stops that, so it is checked
here in three directions:

- it parses, one model per harness, and refuses the shapes that would silently bind nothing;
- it covers exactly `HARNESS_NAMES`, refused at start-up rather than at dispatch — a
  harness with no entry must never reach `start` (`test_harness_readiness_start_model.py`
  covers what `start` does if one ever does);
- every model it names is a `model_name` the committed `deploy/llm-platform/litellm.config.yaml`
  serves,
  which is the actual failure being fixed: a model no `model_list` route answers.

One value per harness rather than one global model, because a single value cannot be right:
`codex` cannot run an Anthropic model and `local` is pointed at the host's own model server.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from orchestrator.application.use_cases.harness_readiness import DEFAULT_READINESS_MODELS
from orchestrator.domain.entities.harness import HARNESS_NAMES
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

#: What the committed contract binds, harness by harness. Written out rather than derived
#: from the file under test: this is the operator's own decision — the cheapest model that
#: can finish the fixture's one story on each harness — and a derived expectation would
#: agree with any later edit instead of holding it to the decision.
COMMITTED = {"claude": "claude-sonnet-4-6", "codex": "gpt-5.4", "local": "local-coder"}

GATEWAY_CONFIG = REPO_ROOT / "deploy" / "llm-platform" / "litellm.config.yaml"


def _served_model_names(path: Path) -> set[str]:
    """Every `model_name` the host Gateway's `model_list` answers on."""
    config = yaml.safe_load(path.read_text())
    return {entry["model_name"] for entry in config["model_list"]}


# ── the contract parses ──────────────────────────────────────────────────────


def test_the_committed_contract_binds_one_model_per_harness(env: dict[str, str]) -> None:
    assert Settings().readiness_models == COMMITTED


def test_the_contract_covers_every_harness_the_image_installs(env: dict[str, str]) -> None:
    assert set(Settings().readiness_models) == set(HARNESS_NAMES)


def test_pairs_are_split_and_stripped(env: dict[str, str]) -> None:
    value = " claude = a , codex = b , local = c "

    assert Settings(readiness_models=value).readiness_models == {
        "claude": "a",
        "codex": "b",
        "local": "c",
    }


def test_a_mapping_passed_directly_is_left_alone(env: dict[str, str]) -> None:
    """The composition root reads the environment, but `Settings(...)` also takes the parsed
    shape — the `local_models` precedent's own leave-a-list-alone behaviour."""
    assert Settings(readiness_models=dict(COMMITTED)).readiness_models == COMMITTED


# ── the shapes that would bind nothing ───────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "claude,codex=b,local=c",  # no `=` at all
        "=a,codex=b,local=c",  # no harness name
        "claude=,codex=b,local=c",  # no model name
        "claude= ,codex=b,local=c",  # whitespace is not a model name
        "  ",  # nothing whatsoever
    ],
)
def test_an_entry_that_names_no_model_is_rejected(env: dict[str, str], value: str) -> None:
    with pytest.raises(ValidationError, match="readiness_models"):
        Settings(readiness_models=value)


@pytest.mark.parametrize("missing", HARNESS_NAMES)
def test_a_harness_with_no_entry_is_refused_at_start_up_and_named(
    env: dict[str, str], missing: str
) -> None:
    """Loud and early: the process refuses to start rather than dispatching a readiness Run
    that binds no model for one harness while the other two look configured."""
    partial = ",".join(f"{name}={model}" for name, model in COMMITTED.items() if name != missing)

    with pytest.raises(ValidationError, match=missing):
        Settings(readiness_models=partial)


def test_a_name_that_is_not_a_harness_is_refused_and_named(env: dict[str, str]) -> None:
    """`opencode=local-coder` is the typo that matters: `local` is the harness that runs
    OpenCode, so the entry looks right, covers nothing, and would leave `local` unbound if
    the extra name were quietly ignored."""
    value = ",".join([*(f"{n}={m}" for n, m in COMMITTED.items()), "opencode=local-coder"])

    with pytest.raises(ValidationError, match="opencode"):
        Settings(readiness_models=value)


# ── the models are ones the Gateway actually serves ──────────────────────────


def test_every_committed_model_is_served_by_the_host_gateway_config() -> None:
    """The defect this setting fixes, asserted directly: a bound model no `model_list` route
    answers is a failed agent step, whatever the rest of readiness proves."""
    served = _served_model_names(GATEWAY_CONFIG)

    assert set(COMMITTED.values()) <= served, sorted(served)


def test_the_gateway_config_is_read_as_a_list_of_named_models() -> None:
    """Proves the check above reads something: an empty set would satisfy `<=` vacuously
    only if the left side were empty too, and this pins the right side to real content."""
    assert "claude-sonnet-4-6" in _served_model_names(GATEWAY_CONFIG)


# ── the contract file and the use case's fallback say the same thing ─────────


def test_the_env_example_line_is_the_committed_mapping() -> None:
    """AD-20's other direction: the committed contract file, parsed by the same reader
    `make lint` uses, holds exactly what `Settings` is asserted to produce above."""
    raw = parse_env_example(ENV_EXAMPLE)["READINESS_MODELS"]

    assert dict(pair.split("=", 1) for pair in raw.split(",")) == COMMITTED


def test_the_use_cases_fallback_mapping_is_the_committed_one() -> None:
    """`HarnessReadinessPorts.models` defaults to this, and the composition root overrides it
    with `settings.readiness_models`; the two drifting apart would make a unit test prove a
    binding production never makes."""
    assert dict(DEFAULT_READINESS_MODELS) == COMMITTED
