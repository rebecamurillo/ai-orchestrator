"""The per-harness setup scripts, held to the contract they exist to hold (AD-10, AD-5).

`scripts/harness/<name>.sh` is the only place a harness's environment and static config are
defined. Nothing in Epic 1 executes `install` — that happens at image build — so without
this module the four scripts could ship broken, non-executable, or carrying a credential,
and every gate would stay green until an Epic 5 adapter tried to use them.

Four properties are worth asserting mechanically:

- **They run.** `bash -n` parses each file, and each harness script answers an unknown verb
  with usage and exit 2. A script that cannot be sourced is caught here, not at build time.
- **`install` needs no gateway credential.** It runs as `agent` during `docker build`, where
  `LITELLM_API_KEY` and the Langfuse keys do not exist and must never be baked in. The guard
  therefore belongs to `configure` and `doctor`, and this module proves it is still there for
  those two: a scrubbed environment must refuse, naming the variable.
- **Config files carry names, not values (AD-10).** A harness config that interpolated
  `LITELLM_API_KEY` would write the key into `AGENT_HOME`; the per-attempt values arrive
  through the environment instead.
- **AD-5 holds by absence.** `GITHUB_TOKEN` and `LITELLM_SPEND_KEY` appear in no script.

The pinned versions are read back out of the scripts and compared with `.env.example`, so
the contract and the defaults cannot drift apart silently.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT, parse_env_example

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"

COMMON = "_common.sh"
HARNESSES = ("claude", "codex", "opencode")
VERBS = ("install", "configure", "doctor")

#: The `: "${NAME:=default}"` line in each script, against the contract line that pins it.
PINNED_VERSIONS = {
    "claude": "CLAUDE_CODE_VERSION",
    "codex": "CODEX_VERSION",
    "opencode": "OPENCODE_VERSION",
}

#: Never in a harness process, so never in a harness script (AD-5).
FORBIDDEN_NAMES = ("GITHUB_TOKEN", "LITELLM_SPEND_KEY")

#: The exit code a shell convention reserves for "wrong usage".
USAGE_EXIT_CODE = 2

#: What `configure` and `doctor` require before they will write or probe anything.
REQUIRED_AT_CONFIGURE = (
    "LITELLM_BASE_URL",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


def script(name: str) -> Path:
    return HARNESS_DIR / f"{name}.sh"


def text(name: str) -> str:
    path = script(name)
    assert path.is_file(), f"{path} is missing"
    return path.read_text()


def code(name: str) -> str:
    """The script with its whole-line comments dropped.

    AD-5 is about what a script *does*, and `_common.sh` documents the two names it must
    never carry. Reading through the comments would make that documentation a violation.
    """
    kept = [line for line in text(name).splitlines() if not line.strip().startswith("#")]
    return "\n".join(kept) + "\n"


def _run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # fixed argv, no shell
        list(argv),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# ── the scripts exist and run ────────────────────────────────────────────────


@pytest.mark.parametrize("name", (COMMON.removesuffix(".sh"), *HARNESSES))
def test_the_script_is_committed(name: str) -> None:
    assert script(name).is_file()


@pytest.mark.parametrize("name", HARNESSES)
def test_a_harness_script_is_executable(name: str) -> None:
    """`docker compose exec backend-api scripts/harness/claude.sh doctor` runs it directly."""
    mode = script(name).stat().st_mode

    assert mode & stat.S_IXUSR, f"{name}.sh: owner cannot execute it"
    assert mode & stat.S_IXOTH, f"{name}.sh: the container's user cannot execute it"


@pytest.mark.parametrize("name", (COMMON.removesuffix(".sh"), *HARNESSES))
def test_the_script_parses(name: str) -> None:
    result = _run("bash", "-n", str(script(name)))

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("name", HARNESSES)
def test_an_unknown_verb_prints_usage_and_exits_two(name: str) -> None:
    """Sourcing `_common.sh` must not itself need configuration — this is what proves it."""
    result = _run("bash", str(script(name)), "nonsense", env={"PATH": os.environ["PATH"]})

    assert result.returncode == USAGE_EXIT_CODE, result.stdout + result.stderr
    assert "usage" in result.stderr


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize("verb", VERBS)
def test_the_script_implements_every_verb(name: str, verb: str) -> None:
    assert re.search(rf"^{verb}\(\) \{{", text(name), re.MULTILINE), f"{name}.sh: no {verb}()"


# ── install needs no credential; configure and doctor refuse without one ─────


@pytest.mark.parametrize("name", HARNESSES)
@pytest.mark.parametrize("verb", ("configure", "doctor"))
def test_configure_and_doctor_check_the_environment_first(name: str, verb: str) -> None:
    lines = code(name).splitlines()
    dispatch = next(line for line in lines if f"{verb})" in line or "|doctor)" in line)

    assert "require_harness_env" in dispatch, f"{name}.sh: {verb} must call require_harness_env"


@pytest.mark.parametrize("name", HARNESSES)
def test_install_does_not_check_the_gateway_environment(name: str) -> None:
    """It runs during `docker build`, where those values do not exist and must not be baked in."""
    dispatch = next(line for line in code(name).splitlines() if "install)" in line)

    assert "require_harness_env" not in dispatch, dispatch


@pytest.mark.parametrize("name", HARNESSES)
def test_configure_refuses_with_nothing_configured(name: str) -> None:
    """A container that configured a harness from an empty environment would serve broken."""
    result = _run(
        "bash",
        str(script(name)),
        "configure",
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", "")},
    )

    assert result.returncode != 0
    assert any(variable in result.stderr for variable in REQUIRED_AT_CONFIGURE), result.stderr


def test_the_guard_names_every_variable_configure_needs() -> None:
    body = text(COMMON.removesuffix(".sh"))
    guard = body[body.index("require_harness_env()") :]

    for variable in REQUIRED_AT_CONFIGURE:
        assert f"${{{variable}:?" in guard, variable


# ── AD-10: names, not values; AD-5: two names never appear ──────────────────


@pytest.mark.parametrize("name", (COMMON.removesuffix(".sh"), *HARNESSES))
@pytest.mark.parametrize("forbidden", FORBIDDEN_NAMES)
def test_no_script_names_a_credential_a_harness_never_receives(name: str, forbidden: str) -> None:
    assert forbidden not in code(name), f"{name}.sh: {forbidden} (AD-5)"


@pytest.mark.parametrize("name", HARNESSES)
def test_a_config_file_is_written_with_variable_names_not_values(name: str) -> None:
    """`env_key`, `{env:...}` and the adapter's environment carry the key; the file never does."""
    assert "${LITELLM_API_KEY" not in code(name), f"{name}.sh: expands the key into its config"


def test_the_environment_contract_carries_the_model_key_and_not_the_spend_key() -> None:
    body = code(COMMON.removesuffix(".sh"))
    contract = body[body.index("HARNESS_ENV_CONTRACT=(") :].split(")", 1)[0]

    assert "LITELLM_API_KEY" in contract
    for forbidden in FORBIDDEN_NAMES:
        assert forbidden not in contract


# ── the pinned versions agree with the contract ──────────────────────────────


@pytest.mark.parametrize(("name", "variable"), sorted(PINNED_VERSIONS.items()))
def test_the_pinned_version_matches_the_contract(name: str, variable: str) -> None:
    """A script default drifting from `.env.example` would install a version nobody chose."""
    contract = parse_env_example(ENV_EXAMPLE)
    match = re.search(rf"\$\{{{variable}:=([^}}]+)\}}", text(name))

    assert match, f"{name}.sh: no default for {variable}"
    assert match.group(1) == contract[variable]


def test_the_method_version_matches_the_contract() -> None:
    contract = parse_env_example(ENV_EXAMPLE)
    match = re.search(r"\$\{BMAD_VERSION:=([^}]+)\}", text(COMMON.removesuffix(".sh")))

    assert match
    assert match.group(1) == contract["BMAD_VERSION"]


def test_the_agent_home_default_matches_the_contract() -> None:
    contract = parse_env_example(ENV_EXAMPLE)
    match = re.search(r"\$\{AGENT_HOME:=([^}]+)\}", text(COMMON.removesuffix(".sh")))

    assert match
    assert match.group(1) == contract["AGENT_HOME"]
