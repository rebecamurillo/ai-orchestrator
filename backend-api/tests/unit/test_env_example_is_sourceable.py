"""`.env.example` is executed by a shell, so it has to parse as one.

The README tells every contributor to `cp .env.example .env` and then `set -a; . ./.env;
set +a`; the CI e2e-api job does exactly that, and so does `scripts/harness/_common.sh` by
way of the container entrypoint. A value that is legal to a dotenv parser but not to `bash`
therefore breaks the pipeline and the documented setup while every other gate stays green.

This is not hypothetical. `CLAUDE_ALLOWED_TOOLS` shipped as

    CLAUDE_ALLOWED_TOOLS=Task,Bash(uv run *),Bash(git *),...

whose unquoted parentheses are a syntax error to `bash`. Nothing caught it locally, because a
`.env` created before that variable existed still sourced cleanly — the environment-contract
check compares variable *names*, so a stale file passes it. The first fresh `cp` was on a CI
runner, four stories later.

`docker compose` and pydantic-settings both strip surrounding quotes, so quoting a value costs
nothing and is what makes the three readers agree.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT

BASH = shutil.which("bash")

#: Contract lines whose blank value is the documented off switch (story O-8, 2026-10-12).
BLANK_BY_DESIGN = {"NOTIFY_WEBHOOK_URL", "NOTIFY_WEBHOOK_SECRET", "PUBLIC_BASE_URL"}

pytestmark = pytest.mark.skipif(BASH is None, reason="bash not on PATH")


def _source(path: str) -> subprocess.CompletedProcess[str]:
    """Source `path` the way the README and the CI job do, under `bash -e`."""
    assert BASH is not None
    return subprocess.run(  # fixed argv, no shell
        [BASH, "-e", "-c", f'set -a; . "{path}"; set +a'],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_a_fresh_copy_sources_cleanly() -> None:
    """`cp .env.example .env` then `. ./.env` — the first thing every new machine does."""
    result = _source(str(ENV_EXAMPLE))

    assert result.returncode == 0, result.stderr


def test_every_variable_survives_the_round_trip() -> None:
    """Sourcing must not silently drop or truncate a value at the first special character."""
    assert BASH is not None
    declared = [
        line.split("=", 1)[0]
        for line in ENV_EXAMPLE.read_text().splitlines()
        if line and not line.lstrip().startswith("#") and "=" in line
    ]

    assert declared
    script = f'set -a; . "{ENV_EXAMPLE}"; set +a; ' + "; ".join(
        f'test -n "${name}" || echo "empty: {name}"'
        for name in declared
        if name not in BLANK_BY_DESIGN
    )
    result = subprocess.run(  # fixed argv, no shell
        [BASH, "-e", "-c", script],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "", result.stdout


def test_a_value_with_shell_syntax_in_it_is_quoted() -> None:
    """The specific shape that broke: parentheses, unquoted.

    Asserted over the file rather than by sourcing, because `bash` accepts some of these in
    isolation and fails on others — the rule is "quote it", not "hope it parses".
    """
    offenders = []
    for number, line in enumerate(ENV_EXAMPLE.read_text().splitlines(), start=1):
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        value = line.split("=", 1)[1].split("#")[0].strip()
        if value[:1] in {"'", '"'}:
            continue
        if any(character in value for character in "()|&;<>`$"):
            offenders.append(f"{number}: {line}")

    assert not offenders, "quote these values:\n" + "\n".join(offenders)
