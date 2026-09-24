"""`infrastructure/skills_install.py`: operator skills installed at container start.

Why it exists (hub-Run operations, skills install fix, 2026-09-24): the skills are copied
into `${AGENT_HOME}` during `docker build`, and `${AGENT_HOME}` is where the `agent-home`
named volume mounts.  Docker seeds a named volume from the image only while the volume is
empty, so an instance whose volume predates a skill never receives it — and never receives
the `skills-manifest.json` the installed-skill pre-flight check reads.  Running the copy
again at every start-up is what makes the volume catch up with the image.

The adapter shells `<harness_scripts_dir>/<name>.sh skills`, the same way
`infrastructure/harness/probe.py` shells the `probe` verb (AD-10, AD-16).  Only the
operator-skill copy is run, never the whole `install` verb: that one `npm install`s a CLI.

The scripts here are stubs written into `tmp_path`, so nothing in this module depends on a
harness CLI, on the image, or on the machine's own `~/.claude`.
"""

from __future__ import annotations

import shutil
import stat
from pathlib import Path

import pytest

from orchestrator.infrastructure import skills_install
from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.skill_catalog import FsSkillCatalog, manifest_path
from tests.unit.conftest import REPO_ROOT

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

COMMON_SH = REPO_ROOT / "scripts" / "harness" / "_common.sh"

#: A stub that reports one installed skill and records the environment it was handed.
STUB = """#!/usr/bin/env bash
set -euo pipefail
[ "${{1:-}}" = "skills" ] || {{ echo "wrong verb: ${{1:-}}" >&2; exit 2; }}
env > "{record}"
echo '{{"dest":"{dest}","installed":["spec-gate"],"updated":[],"skills":3}}'
"""

FAILING_STUB = """#!/usr/bin/env bash
echo "operator skill name collision" >&2
exit 1
"""

NOT_JSON_STUB = """#!/usr/bin/env bash
echo not-json
"""


def _script(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _stubs(directory: Path, *, names: tuple[str, ...] | None = None) -> None:
    for name in names if names is not None else skills_install.HARNESS_SCRIPTS:
        _script(
            directory,
            name,
            STUB.format(record=directory / f"{name}.env", dest=f"/home/agent/{name}"),
        )


def _handed_env(record: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in record.read_text().splitlines() if "=" in line)


@pytest.fixture
def settings(env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Settings:
    monkeypatch.setenv("HARNESS_SCRIPTS_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_HOME", str(tmp_path / "agent-home"))
    return Settings()


# ── the happy path ────────────────────────────────────────────────────────────


def test_install_runs_the_skills_verb_of_every_harness_script(
    settings: Settings, tmp_path: Path
) -> None:
    _stubs(tmp_path)

    results = skills_install.install_operator_skills(settings)

    assert [result.script for result in results] == list(skills_install.HARNESS_SCRIPTS)
    assert all(result.ok for result in results)
    for name in skills_install.HARNESS_SCRIPTS:
        assert (tmp_path / f"{name}.env").is_file(), f"{name} was never run"


def test_install_reports_the_skills_each_script_copied(settings: Settings, tmp_path: Path) -> None:
    """ "log what it installed": the JSON line the verb prints is what carries it."""
    _stubs(tmp_path)

    results = skills_install.install_operator_skills(settings)

    assert [result.installed for result in results] == [("spec-gate",)] * len(results)
    assert all(result.updated == () for result in results)


def test_install_logs_one_line_per_script(
    settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stubs(tmp_path)
    configure_logging("info")

    skills_install.install_operator_skills(settings)

    out = capsys.readouterr().out
    assert out.count(skills_install.INSTALLED_LINE) == len(skills_install.HARNESS_SCRIPTS)
    assert "spec-gate" in out


# ── the environment the verb is handed (AD-5) ─────────────────────────────────


def test_the_script_receives_agent_home_and_no_credential(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The verb needs AGENT_HOME to find each harness's skills directory, and nothing else.
    A secret in this process's environment must never reach it (AD-5, hard rule 5)."""
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_value")
    _stubs(tmp_path)

    skills_install.install_operator_skills(settings)

    record = tmp_path / f"{skills_install.HARNESS_SCRIPTS[0]}.env"
    handed = _handed_env(record)
    assert handed["AGENT_HOME"] == str(settings.agent_home)
    assert "GITHUB_TOKEN" not in handed
    assert "ghp_secret_value" not in record.read_text()
    assert "LITELLM_API_KEY" not in handed


# ── degradation: a fault is reported, never raised ────────────────────────────


def test_a_missing_script_is_reported_and_the_others_still_run(
    settings: Settings, tmp_path: Path
) -> None:
    """A non-image run may have no harness scripts at all; start-up must not die of it."""
    _stubs(tmp_path, names=skills_install.HARNESS_SCRIPTS[1:])

    results = skills_install.install_operator_skills(settings)

    assert results[0].ok is False
    assert "not found" in results[0].detail
    assert all(result.ok for result in results[1:])


def test_a_failing_script_is_reported_and_never_raises(settings: Settings, tmp_path: Path) -> None:
    _stubs(tmp_path)
    _script(tmp_path, skills_install.HARNESS_SCRIPTS[0], FAILING_STUB)

    results = skills_install.install_operator_skills(settings)

    assert results[0].ok is False
    assert "collision" in results[0].detail


def test_unparseable_output_is_reported_without_installed_names(
    settings: Settings, tmp_path: Path
) -> None:
    """The verb's stdout is a contract; a script that breaks it is a fault, not a crash."""
    _stubs(tmp_path)
    _script(tmp_path, skills_install.HARNESS_SCRIPTS[0], NOT_JSON_STUB)

    results = skills_install.install_operator_skills(settings)

    assert results[0].ok is False
    assert results[0].installed == ()


def test_a_failure_is_logged_as_a_warning_naming_the_script(
    settings: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stubs(tmp_path)
    _script(tmp_path, skills_install.HARNESS_SCRIPTS[0], FAILING_STUB)
    configure_logging("info")

    skills_install.install_operator_skills(settings)

    out = capsys.readouterr().out
    assert skills_install.FAILED_LINE in out
    assert skills_install.HARNESS_SCRIPTS[0] in out


# ── the manifest path the catalog reads ───────────────────────────────────────


def test_manifest_path_is_the_one_the_catalog_reads(tmp_path: Path) -> None:
    """One statement of where the manifest lives, shared by `api/providers.py` and the
    walker's `StepPorts` — two readers that must never drift apart."""
    assert manifest_path(tmp_path) == tmp_path / ".claude" / "skills-manifest.json"


def test_install_makes_the_catalog_readable_end_to_end(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The whole point: after start-up the catalog answers a set, not `None`."""
    scripts, home = tmp_path / "harness", tmp_path / "agent-home"
    scripts.mkdir()
    source = tmp_path / "ia-agents-skills" / "spec-gate"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("# spec-gate\n")
    _script(
        scripts,
        "claude.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\nHARNESS_NAME=claude\n"
        f'source "{COMMON_SH}"\n'
        f'sync_operator_skills "{source.parent}" "${{AGENT_HOME}}/.claude/skills"\n',
    )
    monkeypatch.setenv("HARNESS_SCRIPTS_DIR", str(scripts))
    monkeypatch.setenv("AGENT_HOME", str(home))
    settings = Settings()

    skills_install.install_operator_skills(settings)

    catalog = FsSkillCatalog(manifest_path(settings.agent_home))
    assert catalog.installed_skills() == frozenset({"spec-gate"})
