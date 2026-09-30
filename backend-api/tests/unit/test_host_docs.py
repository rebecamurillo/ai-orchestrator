"""The half of the stack that is not in compose, documented where AD-20 says it lives.

LiteLLM, Langfuse and the model server run on the Mac mini itself — Docker on macOS has no
GPU, and the Gateway holds keys the containers never see. They are therefore documented
rather than orchestrated, and `deploy/llm-platform/` is that documentation. Prose is not
usually testable,
but each item below is a decision some later story depends on being written down:

- the Gateway's two keys (PRD §8 item 5) and which one a harness may receive (AD-5),
- the `langfuse_otel` callback and `LITELLM_OTEL_V2=true`, without which the Gateway's own
  spans never reach the tracing server (AD-11),
- local models as `openai/<alias>` with `use_chat_completions_api: true`, which is what
  lets Codex's `/v1/responses` calls bridge to the model server (addendum §A),
- the egress allowlist, which NFR-4 makes a host firewall rule rather than a container one,
- the nightly `pg_dump` into `deploy/llm-platform/backups/`, 14 days kept (spine Operations).

A missing line here is a decision that has to be rediscovered. The file also has to stay
free of key material, which is the other half of what is asserted.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

HOST = REPO_ROOT / "deploy" / "llm-platform"
README = HOST / "README.md"
LITELLM_CONFIG = HOST / "litellm.config.yaml"
BACKUPS_KEEP = HOST / "backups" / ".gitkeep"

#: Every decision the brief requires `deploy/llm-platform/README.md` to carry, as it must
#: appear in it.
DOCUMENTED = (
    "1.99.0",  # LiteLLM, pinned
    "model_list",
    "LITELLM_OTEL_V2=true",
    "langfuse_otel",
    "use_chat_completions_api: true",
    "key_type: llm_api",  # LITELLM_API_KEY, the only Gateway key a harness receives
    "proxy_admin_viewer",  # LITELLM_SPEND_KEY, backend-api only
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "4.27.0",  # Langfuse, pinned
    "oMLX",
    "pg_dump",
    "deploy/llm-platform/backups/",
    "14 days",
)

#: Values that must never appear in a committed file (hard rule 5).
SECRET_VARIABLES = (
    "ORCHESTRATOR_TOKEN",
    "GITHUB_TOKEN",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_SECRET_KEY",
    "POSTGRES_PASSWORD",
)


@pytest.fixture(scope="module")
def readme() -> str:
    assert README.is_file(), f"{README} is missing"
    return README.read_text()


@pytest.fixture(scope="module")
def litellm_config() -> str:
    assert LITELLM_CONFIG.is_file(), f"{LITELLM_CONFIG} is missing"
    return LITELLM_CONFIG.read_text()


# ── what the README has to say ───────────────────────────────────────────────


@pytest.mark.parametrize("item", DOCUMENTED)
def test_the_readme_documents_the_decision(readme: str, item: str) -> None:
    assert item in readme, item


def test_the_readme_names_the_egress_rule_as_a_host_rule(readme: str) -> None:
    """NFR-4: the containers do not enforce it, so the document is the whole of it."""
    lowered = readme.lower()

    assert "egress" in lowered
    assert "firewall" in lowered


def test_the_readme_says_where_the_gateway_is_reached_from(readme: str) -> None:
    """`host.docker.internal` is why `extra_hosts` exists in the compose file."""
    assert "host.docker.internal" in readme


# ── the starting configuration ───────────────────────────────────────────────


def test_the_config_declares_the_model_list(litellm_config: str) -> None:
    assert "model_list:" in litellm_config


def test_the_config_turns_on_the_tracing_callback(litellm_config: str) -> None:
    """Without the callback the Gateway's own spans never reach Langfuse (AD-11)."""
    assert "langfuse_otel" in litellm_config


def test_the_config_bridges_the_local_models_to_chat_completions(litellm_config: str) -> None:
    """Codex speaks `/v1/responses`; the model server speaks chat completions."""
    assert "use_chat_completions_api: true" in litellm_config


def test_every_local_alias_in_the_contract_has_a_model(litellm_config: str) -> None:
    """`LOCAL_MODELS` is what the `local` harness offers; a missing entry is a 404 at run time."""
    aliases = parse_env_example(ENV_EXAMPLE)["LOCAL_MODELS"].split(",")

    assert aliases
    for alias in aliases:
        assert f"model_name: {alias.strip()}" in litellm_config, alias


def test_the_config_reads_its_keys_from_the_host_environment(litellm_config: str) -> None:
    """`os.environ/NAME` is LiteLLM's own indirection; a literal here would be a key."""
    assert "os.environ/" in litellm_config


# ── nothing here carries key material ────────────────────────────────────────


@pytest.mark.parametrize("variable", SECRET_VARIABLES)
def test_no_contract_placeholder_reaches_the_host_documents(
    readme: str, litellm_config: str, variable: str
) -> None:
    placeholder = parse_env_example(ENV_EXAMPLE)[variable]

    assert placeholder not in readme, variable
    assert placeholder not in litellm_config, variable


# ── the backups directory is tracked, its contents are not ───────────────────


def test_the_backups_directory_is_tracked() -> None:
    assert BACKUPS_KEEP.is_file()


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_a_dump_is_ignored_but_the_directory_is_not() -> None:
    """A nightly `pg_dump` of the whole database must never be committable."""

    def ignored(path: str) -> bool:
        result = subprocess.run(  # fixed argv, no shell
            ["git", "check-ignore", "-q", "--no-index", path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0

    assert ignored("deploy/llm-platform/backups/orchestrator-2026-09-04.sql")
    assert not ignored("deploy/llm-platform/backups/.gitkeep")
