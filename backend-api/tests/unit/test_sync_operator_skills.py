"""`sync_operator_skills`: the boot-time, idempotent half of operator-skill installation.

Defect (hub-Run operations, skills install fix, 2026-09-24): `install_operator_skills` runs
only during `docker build`, and it writes into `${AGENT_HOME}`, which is where the
`agent-home` named volume mounts.  Docker seeds a named volume from the image only while the
volume is empty, so an instance whose volume predates a skill never sees that skill and
never sees the `skills-manifest.json` that names it — silently, for the life of the volume.

`sync_operator_skills` is what the container runs on every boot instead: it copies a skill
the destination lacks, replaces one whose image copy differs, leaves an identical one alone,
always rewrites the manifest, and — unlike `install_operator_skills` — never refuses over a
name it finds already present, because on the second boot every operator skill is present.

Shell logic lives entirely in `scripts/harness/_common.sh` (AD-16); this module sources it
and calls the function from a minimal wrapper, so every assertion here is independent of any
harness CLI being installed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


def _run_sync(src: Path, dest: Path) -> subprocess.CompletedProcess[str]:
    """Source _common.sh and call sync_operator_skills "$src" "$dest"."""
    wrapper = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f'source "{HARNESS_DIR}/_common.sh"\n'
        f'sync_operator_skills "{src}" "{dest}"\n'
    )
    return subprocess.run(  # fixed argv, no shell
        ["bash", "-c", wrapper],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": os.environ["PATH"],
            "HOME": os.environ.get("HOME", ""),
            "HARNESS_NAME": "test",
        },
    )


def _make_skill(base: Path, name: str, body: str = "") -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(body or f"# {name}\n")


def _report(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    """The one JSON line `sync_operator_skills` prints on stdout."""
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


# ── the defect: a skill the destination never received ────────────────────────


def test_sync_installs_a_skill_the_destination_is_missing(tmp_path: Path) -> None:
    """The stale-volume case: the image ships `spec-gate`, the volume has never seen it."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate")
    _make_skill(dest, "bmad-build-auto")

    report = _report(_run_sync(src, dest))

    assert (dest / "spec-gate" / "SKILL.md").is_file()
    assert report["installed"] == ["spec-gate"]
    assert report["updated"] == []


def test_sync_writes_a_manifest_naming_every_skill_present(tmp_path: Path) -> None:
    """The manifest is what pre-flight reads; a stale volume never had one at all."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate")
    _make_skill(dest, "bmad-build-auto")

    _report(_run_sync(src, dest))

    manifest = tmp_path / "skills-manifest.json"
    assert manifest.is_file()
    assert json.loads(manifest.read_text())["skills"] == ["bmad-build-auto", "spec-gate"]


# ── idempotence: safe on every boot ───────────────────────────────────────────


def test_sync_is_idempotent_and_reports_no_change_on_a_second_run(tmp_path: Path) -> None:
    """`install_operator_skills` would exit 1 here (name already present); this must not."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate")
    _make_skill(dest, "bmad-build-auto")

    _report(_run_sync(src, dest))
    second = _report(_run_sync(src, dest))

    assert second["installed"] == []
    assert second["updated"] == []
    manifest = tmp_path / "skills-manifest.json"
    assert json.loads(manifest.read_text())["skills"] == ["bmad-build-auto", "spec-gate"]


def test_sync_replaces_a_customised_copy_that_differs_from_the_image(tmp_path: Path) -> None:
    """A copy the operator added to inside the volume differs from the image's, so the
    image's wins — the alternative is an instance running a skill nobody shipped."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate", "# spec-gate\nsame\n")
    _make_skill(dest, "spec-gate", "# spec-gate\nsame\n")
    marker = dest / "spec-gate" / "operator-note.md"
    marker.write_text("kept\n")

    report = _report(_run_sync(src, dest))

    assert report["installed"] == []
    # the extra file makes the trees differ, so the image's copy wins and the note goes
    assert report["updated"] == ["spec-gate"]
    assert not marker.exists()


def test_sync_reports_nothing_when_the_trees_match_exactly(tmp_path: Path) -> None:
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate", "# spec-gate\nsame\n")
    _make_skill(dest, "spec-gate", "# spec-gate\nsame\n")

    report = _report(_run_sync(src, dest))

    assert report["installed"] == []
    assert report["updated"] == []


def test_sync_replaces_a_skill_whose_image_copy_differs(tmp_path: Path) -> None:
    """The image is the source of truth: a stale volume copy is replaced, not kept."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate", "# spec-gate\nversion two\n")
    _make_skill(dest, "spec-gate", "# spec-gate\nversion one\n")

    report = _report(_run_sync(src, dest))

    assert report["updated"] == ["spec-gate"]
    assert (dest / "spec-gate" / "SKILL.md").read_text() == "# spec-gate\nversion two\n"


def test_sync_never_removes_a_skill_the_image_does_not_ship(tmp_path: Path) -> None:
    """BMAD stubs and an operator's own skills live in the same directory (AD-16)."""
    src = tmp_path / "ia-agents-skills"
    dest = tmp_path / "skills"
    _make_skill(src, "spec-gate")
    _make_skill(dest, "bmad-build-auto")
    _make_skill(dest, "operator-only")

    _report(_run_sync(src, dest))

    assert (dest / "bmad-build-auto").is_dir()
    assert (dest / "operator-only").is_dir()


# ── degraded inputs ───────────────────────────────────────────────────────────


def test_sync_still_writes_a_manifest_when_the_source_directory_is_absent(
    tmp_path: Path,
) -> None:
    """A non-image run (`make local`) has no `/app/ia-agents-skills`; the catalog must
    still become readable, or pre-flight can only say `catalog unavailable`."""
    src = tmp_path / "nowhere"
    dest = tmp_path / "skills"
    _make_skill(dest, "bmad-build-auto")

    report = _report(_run_sync(src, dest))

    assert report["installed"] == []
    manifest = tmp_path / "skills-manifest.json"
    assert json.loads(manifest.read_text())["skills"] == ["bmad-build-auto"]


def test_sync_creates_the_destination_and_an_empty_manifest_from_nothing(
    tmp_path: Path,
) -> None:
    src = tmp_path / "nowhere"
    dest = tmp_path / "skills"

    report = _report(_run_sync(src, dest))

    assert dest.is_dir()
    assert report["skills"] == 0
    assert json.loads((tmp_path / "skills-manifest.json").read_text())["skills"] == []


# ── harness wiring (AD-16) ────────────────────────────────────────────────────


@pytest.mark.parametrize("harness", ("claude", "codex", "opencode"))
def test_every_harness_script_exposes_the_skills_verb(harness: str) -> None:
    """`<harness>.sh skills` is what the backend shells at start-up; all three must have it."""
    content = (HARNESS_DIR / f"{harness}.sh").read_text()
    assert "sync_operator_skills" in content, f"{harness}.sh must call sync_operator_skills"
    assert "skills)" in content, f"{harness}.sh must dispatch the `skills` verb"


@pytest.mark.parametrize("harness", ("claude", "codex", "opencode"))
def test_the_skills_verb_runs_with_no_gateway_or_tracing_variables(
    harness: str, tmp_path: Path
) -> None:
    """Like `install`, `skills` only copies files: it must not go through
    `require_harness_env`, which refuses when LITELLM_BASE_URL or LANGFUSE_BASE_URL is
    unset.  Run against a throwaway AGENT_HOME so the machine's own `~/.claude` is
    untouched; the repository's `ia-agents-skills/` is the source, as in the image."""
    script = HARNESS_DIR / f"{harness}.sh"
    result = subprocess.run(  # fixed argv, no shell
        ["bash", str(script), "skills"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path),
            "AGENT_HOME": str(tmp_path),
        },
    )

    assert result.returncode == 0, result.stderr
    manifests = list(tmp_path.rglob("skills-manifest.json"))
    assert len(manifests) == 1, f"expected one manifest, found {manifests}"
    assert "spec-gate" in json.loads(manifests[0].read_text())["skills"]
