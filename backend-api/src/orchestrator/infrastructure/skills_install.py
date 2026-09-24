"""Operator skills installed into every harness at container start (AD-16, AD-20).

**Why this is a start-up step and not only a build step.** `scripts/harness/<name>.sh
install` copies `ia-agents-skills/` into each harness's global skills directory during
`docker build`, and every one of those directories lives under `${AGENT_HOME}` — which is
the mount point of the `agent-home` named volume. Docker seeds a named volume from the image
*only while the volume is empty*, i.e. on its first use. An instance whose volume was created
before a skill was added therefore never receives that skill, and never receives the
`skills-manifest.json` that names it, with no error anywhere: the harness is handed a skill
name it cannot resolve, and a harness does not fail on that — it improvises. Running the copy
again on every boot is what makes the volume catch up with the image
(hub-Run operations, skills install fix, 2026-09-24).

**Only the skill copy, never the whole `install` verb.** `install` also `npm install`s the
harness CLI at its pinned version, which is minutes of work and belongs to the image. The
`skills` verb each harness script exposes is a directory copy and a manifest write, and
`_common.sh::sync_operator_skills` makes it idempotent: a skill the destination lacks is
copied, one whose image copy differs is replaced, an identical one is left alone, and nothing
is ever removed.

**Shelled, like `probe`.** `infrastructure/harness/probe.py` is the precedent: a short
synchronous one-shot call to `<harness_scripts_dir>/<name>.sh`, `subprocess.run` directly
rather than the `ProcessRunner` port, which exists for coding-agent dispatches. The
destination directory is the script's own knowledge (`SKILLS_DIR` in each), so it is stated
once, where `install` and `doctor` already read it.

**A fault here is reported, never raised.** The container must still serve: a start-up that
died over a missing harness script would take down an instance that is otherwise healthy.
What a failure costs instead is visible — the manifest stays stale or absent, and the
installed-skill pre-flight check then refuses every Run that would dispatch a skill
(`application/preflight/lists.py::installed_skill_lines`).
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import structlog

from orchestrator.infrastructure.settings import Settings

log = structlog.get_logger(__name__)

#: The scripts that own a skills directory — one per *file* in `scripts/harness/`, not one
#: per harness name: `local` is served by `opencode.sh` (`infrastructure/harness/registry.py`).
HARNESS_SCRIPTS: tuple[str, ...] = ("claude.sh", "codex.sh", "opencode.sh")

#: The verb, and how long a directory copy may take before it is called a fault.
SKILLS_VERB = "skills"
TIMEOUT_SECONDS = 120

#: The environment the verb is given: what it needs to find each harness's skills directory,
#: and nothing else. Never this process's own environment — it holds `GITHUB_TOKEN`,
#: `LITELLM_SPEND_KEY` and the instance key, and none of them has any business in a copy
#: (AD-5, hard rule 5).
SCRIPT_ENV_NAMES: tuple[str, ...] = ("PATH", "HOME", "AGENT_HOME")

#: The two lines an operator greps `docker compose logs backend-api` for.
INSTALLED_LINE = "operator skills installed"
FAILED_LINE = "operator skills install failed"


@dataclass(frozen=True)
class SkillsInstallResult:
    """What one harness script's `skills` verb reported."""

    script: str
    ok: bool
    #: Skill names the destination did not have; skill names replaced because the image's
    #: copy differed. Empty on a fault, which reports nothing rather than guessing.
    installed: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    #: How many skills the manifest now names, or `0` when the verb reported none.
    skills: int = 0
    #: The sentence a fault carries — the script's own stderr, or why it never ran.
    detail: str = ""


def install_operator_skills(settings: Settings) -> list[SkillsInstallResult]:
    """Run the `skills` verb of every harness script, in order, and log what each did."""
    results = [_one(settings, script) for script in HARNESS_SCRIPTS]
    for result in results:
        if result.ok:
            log.info(
                INSTALLED_LINE,
                script=result.script,
                installed=list(result.installed),
                updated=list(result.updated),
                skills=result.skills,
            )
        else:
            log.warning(FAILED_LINE, script=result.script, detail=result.detail)
    return results


def _one(settings: Settings, script: str) -> SkillsInstallResult:
    """One script's `skills` verb. Every failure is a result, never an exception."""
    path = Path(settings.harness_scripts_dir) / script
    if not path.is_file():
        return SkillsInstallResult(script=script, ok=False, detail=f"{path}: not found")
    try:
        completed = subprocess.run(  # fixed argv, no shell
            [str(path), SKILLS_VERB],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
            env=_script_env(settings),
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        detail = f"{type(error).__name__}: {error}"
        return SkillsInstallResult(script=script, ok=False, detail=detail)
    if completed.returncode != 0:
        return SkillsInstallResult(
            script=script, ok=False, detail=_detail(completed.returncode, completed.stderr)
        )
    return _parse(script, completed.stdout, completed.stderr)


def _script_env(settings: Settings) -> dict[str, str]:
    """`AGENT_HOME` and the two names a shell needs to run at all — see `SCRIPT_ENV_NAMES`."""
    base = {name: os.environ[name] for name in SCRIPT_ENV_NAMES if name in os.environ}
    base["AGENT_HOME"] = str(settings.agent_home)
    base["HOME"] = str(settings.agent_home)
    return base


def _parse(script: str, stdout: str, stderr: str) -> SkillsInstallResult:
    """The one JSON line `sync_operator_skills` prints, or the fault that it did not."""
    lines = [line for line in stdout.splitlines() if line.strip()]
    try:
        report = json.loads(lines[-1])
        installed = tuple(str(name) for name in report["installed"])
        updated = tuple(str(name) for name in report["updated"])
        skills = int(report["skills"])
    except IndexError, KeyError, TypeError, ValueError:
        return SkillsInstallResult(
            script=script, ok=False, detail=f"unreadable output: {stdout.strip()[:200]!r}"
        )
    return SkillsInstallResult(
        script=script,
        ok=True,
        installed=installed,
        updated=updated,
        skills=skills,
        detail=stderr.strip()[-200:],
    )


def _detail(returncode: int, stderr: str) -> str:
    """What a non-zero exit carries: the code, and the tail of what the script said."""
    return f"exit {returncode}: {stderr.strip()[-400:]}"
