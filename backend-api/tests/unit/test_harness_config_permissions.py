"""The config a harness writes into `AGENT_HOME` is readable by its owner only.

`test_harness_scripts.py` already proves no config file interpolates a credential *by value*
— per-attempt secrets arrive through the environment, named not spelled. One credential
escapes that rule by construction: Langfuse's OTLP endpoint authenticates with HTTP Basic,
so `claude.sh` has nowhere to put `LANGFUSE_PUBLIC_KEY:LANGFUSE_SECRET_KEY` except inside
`settings.json`, base64-encoded and trivially reversible.

`cat >` creates a file at `0666 & ~umask`, which is `0644` under the image's default umask.
That file lives in the `agent-home` volume, which outlives `make down` — so a real Langfuse
secret would sit world-readable in a persistent volume until the volume is removed.

The three `chmod 600` calls are what this module pins. It asserts on the scripts rather than
on a running container because nothing in Epic 1 executes `configure`; the mode is checked
where it is written, next to the write itself. `codex.sh` and `opencode.sh` carry no key
material today and are held to the same mode anyway: the asymmetry, not the permission, is
what would rot.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"

# script -> the config file its `configure` writes
WRITTEN_CONFIGS = {
    "claude.sh": "settings.json",
    "codex.sh": "config.toml",
    "opencode.sh": "opencode.json",
}


def _script(name: str) -> str:
    path = HARNESS_DIR / name
    assert path.is_file(), f"{path} is missing"
    return path.read_text()


@pytest.mark.parametrize(("script", "config"), sorted(WRITTEN_CONFIGS.items()))
def test_the_written_config_is_restricted_to_its_owner(script: str, config: str) -> None:
    """A `cat >` with no `chmod` leaves the file at 0644 under the image's umask."""
    text = _script(script)

    assert config in text, f"{script} no longer writes {config}"
    assert re.search(rf"chmod 600 .*{re.escape(config)}", text), (
        f"{script} writes {config} without restricting it to its owner"
    )


@pytest.mark.parametrize(("script", "config"), sorted(WRITTEN_CONFIGS.items()))
def test_the_mode_is_set_after_the_file_exists(script: str, config: str) -> None:
    """`chmod` before `cat >` would pass the check above and change nothing."""
    text = _script(script)
    redirect = text.index('> "${')  # the heredoc's `cat > "${DIR}/<config>"`

    chmod = next(
        (m.start() for m in re.finditer(rf"chmod 600 .*{re.escape(config)}", text)),
        None,
    )

    assert chmod is not None
    assert chmod > redirect, f"{script} chmods {config} before writing it"


def test_the_langfuse_basic_header_is_the_reason_this_module_exists() -> None:
    """If the Basic header ever leaves `settings.json`, this constraint can be revisited.

    Asserting it keeps the docstring above honest: a future change that moves the credential
    out to an environment variable should see this test fail and delete it deliberately.
    """
    common = _script("_common.sh")
    claude = _script("claude.sh")

    assert "langfuse_basic_auth()" in common
    assert "LANGFUSE_SECRET_KEY" in common
    assert "$(langfuse_basic_auth)" in claude


def test_no_other_harness_script_writes_a_config_this_module_does_not_cover() -> None:
    """A fourth config file added later must arrive with its mode, or fail here."""
    written = {
        path.name
        for path in HARNESS_DIR.glob("*.sh")
        if re.search(r"cat > \"\$\{", path.read_text())
    }

    assert written == set(WRITTEN_CONFIGS), sorted(written ^ set(WRITTEN_CONFIGS))


def test_the_scripts_are_still_the_only_place_this_is_decided() -> None:
    """A `chmod` in the Dockerfile would be undone by `configure` at every container start."""
    dockerfile = (REPO_ROOT / "backend-api" / "Dockerfile").read_text()

    for config in WRITTEN_CONFIGS.values():
        assert f"chmod 600 {config}" not in dockerfile
