"""`deploy/install.sh upgrade --tag X` on the folder — product files replaced under the hold.

Epic 3 story 3 (2026-11-11): the upgrade extracts release X's folder from its image
(`kit bootstrap`), refuses while a step works or while an engine-version change would strand a
Run, takes the instance hold, backs the database up, replaces every product file (keeping what it
replaced under `.upgrade/{ts}/previous/`), runs the setup service and restarts. Docker and curl
are shims on PATH, as in `test_install_folder.py`; the "image" is a staged tree these fixtures
build with `scripts/product_manifest.py`, and nothing here touches a daemon.

A refusal is proved by hashing every file of the folder before and after; a call is proved by the
shared call log, in which `docker` and `curl` lines keep their relative order.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.unit.conftest import REPO_ROOT

DEPLOY_DIR = REPO_ROOT / "deploy"
MANIFEST_SCRIPT = REPO_ROOT / "scripts" / "product_manifest.py"
OLD = "1.0.0-test"
NEW = "2.0.0"
EXIT_WORKING, EXIT_ENGINE, EXIT_NO_MANIFEST = 3, 4, 5
SIX = (
    "LITELLM_BASE_URL",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)
#: In the repository `deploy/` and nowhere in a release: the folder's own state and the platform.
TOP_ONLY = {"llm-platform", ".env", "backups", "logs", "diagnostics", ".upgrade", "VERSION"}
SPACED = "templates/shipped/two words.yaml"
BRACKETED = "templates/shipped/a+b[1].yaml"
RUN_ID = "0192f3a0-0000-7000-8000-000000000001"
PARKED_ID = "0192f3a0-0000-7000-8000-000000000002"

PREPARE_CALL = (
    "run --rm --no-deps --user agent "
    "--entrypoint /app/scripts/setup/prepare.sh backend-api"
)

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

DOCKER_SHIM = """#!/usr/bin/env bash
printf 'docker %s\\n' "$*" >> "$SHIM_CALLS"
state() {
\tprintf 'state VERSION=%s\\n' "$(tr -d '[:space:]' < "$SHIM_FOLDER/VERSION")" >> "$SHIM_CALLS"
}
case "$*" in
\t"compose version") echo v2.99.0; exit 0 ;;
\t"compose version --short") echo 2.99.0; exit 0 ;;
\t"version --format"*) echo 28.0.0; exit 0 ;;
\t"info --format"*) echo; exit 0 ;;
\tinfo) exit 0 ;;
\t"image inspect"*) exit 0 ;;
\tlogin*) cat > /dev/null; exit 0 ;;
\t"pull "*) exit "${SHIM_PULL_RC:-0}" ;;
\t"run --rm "*" kit bootstrap")
\t\tcase "${SHIM_IMAGE:-ok}" in
\t\t\tmissing) echo "Unable to find image" >&2; exit 125 ;;
\t\t\tbroken) echo "Error response from daemon: layer does not exist" >&2; exit 1 ;;
\t\tesac
\t\ttar -C "$(dirname "$SHIM_STAGED")" -cf - "$(basename "$SHIM_STAGED")"
\t\texit 0 ;;
esac
case "$*" in
\t*" run --rm --no-deps --user agent "*"prepare.sh backend-api") exit "${SHIM_PREPARE_RC:-0}" ;;
\t*" run --rm "*" setup") state; exit "${SHIM_SETUP_RC:-0}" ;;
\t*"exec -T postgres pg_dump"*) state; echo dump; exit "${SHIM_DUMP_RC:-0}" ;;
\t*" up -d "*) exit "${SHIM_UP_RC:-0}" ;;
\t*"ps --status running --services"*) printf '%s\\n' ${SHIM_RUNNING:-}; exit 0 ;;
\t*" ps") echo "NAME STATUS"; exit 0 ;;
esac
exit 0
"""

CURL_SHIM = """#!/usr/bin/env bash
method=GET; body=""; out=""; url=""; prev=""
for arg in "$@"; do
\tcase "$prev" in -X) method="$arg" ;; -d) body="$arg" ;; -o) out="$arg" ;; esac
\tcase "$arg" in http*) url="$arg" ;; esac
\tprev="$arg"
done
printf 'curl %s %s %s\\n' "$method" "$url" "$body" >> "$SHIM_CALLS"
printf '%s\\n' "$*" >> "$SHIM_CURL_ARGV"
emit() {
\tif [ -n "$out" ] && [ "$out" != "/dev/null" ] && [ -n "$2" ]; then cp "$2" "$out"; fi
\tprintf '%s' "$1"
\texit "${3:-0}"
}
case "$url" in
\t*/api/v1/instance/activity) emit "${SHIM_ACTIVITY_CODE:-200}" "${SHIM_ACTIVITY_FILE:-}" ;;
\t*/api/v1/instance/hold)
\t\tif [ "$method" = POST ]; then emit "${SHIM_HOLD_CODE:-200}" "${SHIM_HOLD_FILE:-}"; fi
\t\temit "${SHIM_RELEASE_CODE:-200}" "" ;;
\t*/healthz)
\t\tif [ "${SHIM_HEALTHZ_CODE:-200}" = 000 ]; then emit 000 "" 7; fi
\t\tif [ "${SHIM_VERIFY_FAIL:-}" = 1 ] && grep -q ' up -d ' "$SHIM_CALLS"; then emit 000 "" 22; fi
\t\temit 200 "" ;;
\t*/api/v1/ping) emit 200 "" ;;
\t*/api/v1/version) emit 200 "${SHIM_VERSION_FILE:-}" ;;
\t*/api/v1/harnesses) emit 200 "${SHIM_HARNESS_FILE:-}" ;;
esac
emit 404 ""
"""


class Folder(NamedTuple):
    path: Path  # the client's folder, release OLD
    staged: Path  # release NEW as `kit bootstrap` hands it over
    env: dict[str, str]
    calls: Path
    served: Path


def _manifest(tree: Path) -> dict[str, object]:
    return json.loads((tree / "product-files.json").read_text())


def _skip_top(directory: str, names: list[str]) -> list[str]:
    return [n for n in names if Path(directory) == DEPLOY_DIR and n in TOP_ONLY]


def release(
    root: Path,
    version: str,
    shipped: dict[str, str],
    tweak: Callable[[Path], None] | None = None,
) -> Path:
    """A release's folder as the image carries it: `deploy/` minus the platform, the given
    example templates, `VERSION`, and the manifest `scripts/product_manifest.py` computes."""
    tree = root / "ai-orchestrator"
    shutil.copytree(DEPLOY_DIR, tree, ignore=_skip_top)
    for name in (tree / "product-files.json", tree / ".env"):
        name.unlink(missing_ok=True)
    (tree / "templates" / "shipped").mkdir(parents=True, exist_ok=True)
    for rel, text in shipped.items():
        (tree / rel).write_text(text)
    (tree / "VERSION").write_text(f"{version}\n")
    if tweak is not None:
        tweak(tree)
    manifest = subprocess.run(  # fixed argv, no shell
        [sys.executable, str(MANIFEST_SCRIPT), str(tree), str(tree / "VERSION")],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    (tree / "product-files.json").write_text(manifest)
    return tree


def _set_pin(tree: Path, name: str, value: str) -> None:
    path = tree / "release.env"
    lines = [
        f"{name}={value}" if line.startswith(f"{name}=") else line
        for line in path.read_text().splitlines()
    ]
    path.write_text("\n".join(lines) + "\n")


def _pin(tree: Path, name: str) -> str:
    return next(
        line.split("=", 1)[1]
        for line in (tree / "release.env").read_text().splitlines()
        if line.startswith(f"{name}=")
    )


def _new_tweak(pins: dict[str, str]) -> Callable[[Path], None]:
    def tweak(tree: Path) -> None:
        with (tree / "install.sh").open("a") as fh:
            fh.write(f"\n# release {NEW}\n")
        for name, value in pins.items():
            _set_pin(tree, name, value)

    return tweak


def _old_tweak(tree: Path) -> None:
    (tree / "old-only.txt").write_text("a file release 2 no longer ships\n")


def _build(tmp_path: Path, pins: dict[str, str] | None = None) -> Folder:
    old_tree = release(
        tmp_path / "rel-old",
        OLD,
        {
            "templates/shipped/x.yaml": "x: 1\n",
            SPACED: "words: 1\n",
            BRACKETED: "brackets: 1\n",
        },
        _old_tweak,
    )
    staged = release(
        tmp_path / "rel-new",
        NEW,
        {
            "templates/shipped/x.yaml": "x: 2\n",
            "templates/shipped/new.yaml": "new: 1\n",
            SPACED: "words: 2\n",
            BRACKETED: "brackets: 2\n",
        },
        _new_tweak(pins if pins is not None else {"CLAUDE_CODE_VERSION": "2.1.400"}),
    )
    path = tmp_path / "folder"
    shutil.copytree(old_tree, path)

    shims = tmp_path / "shims"
    (shims / "bin").mkdir(parents=True)
    for name, body in (("docker", DOCKER_SHIM), ("curl", CURL_SHIM)):
        (shims / "bin" / name).write_text(body)
        (shims / "bin" / name).chmod(0o755)
    served = shims / "served"
    served.mkdir()
    (served / "version.json").write_text(
        json.dumps({"app_version": OLD, "kit_version": OLD, "harness_versions": {}})
    )
    (served / "harnesses.json").write_text(json.dumps(_harnesses()))
    (served / "activity.json").write_text(json.dumps(_activity()))
    calls = shims / "calls.log"
    env = {
        "PATH": f"{shims / 'bin'}:{os.environ['PATH']}",
        "SHIM_CALLS": str(calls),
        "SHIM_CURL_ARGV": str(shims / "curl.argv"),
        "SHIM_FOLDER": str(path),
        "SHIM_STAGED": str(staged),
        "SHIM_RUNNING": "postgres backend-api web-client",
        "SHIM_VERSION_FILE": str(served / "version.json"),
        "SHIM_HARNESS_FILE": str(served / "harnesses.json"),
        "SHIM_ACTIVITY_FILE": str(served / "activity.json"),
        "GHCR_TOKEN": "ghp_upgrade_test_0123456789",
        "GITHUB_USER": "tester",
    }
    folder = Folder(path, staged, env, calls, served)

    made = _run(folder, "env", "--yes")
    assert made.returncode == 0, made.stdout + made.stderr
    (path / "templates" / "x.yaml").write_text("mine: true\n")
    (path / "templates" / "two words.yaml").write_text("mine: words\n")
    (path / "setup" / "10-mine.sh").write_text("#!/bin/sh\necho mine\n")
    (path / "compose.override.yml").write_text("services: {mine: {}}\n")
    (path / "llm-platform").mkdir()
    (path / "llm-platform" / ".env").write_text("LITELLM_MASTER_KEY=mine\n")
    (path / "llm-platform" / "docker-compose.yml").write_text("services: {litellm: {}}\n")
    return folder


@pytest.fixture
def folder(tmp_path: Path) -> Folder:
    return _build(tmp_path)


def _harnesses() -> dict[str, object]:
    setup = {
        "at": "2026-11-11T10:00:00Z",
        "trigger": "upgrade",
        "ok": True,
        "failures": [],
        "skills": 7,
    }
    row = {
        "name": "claude",
        "enabled": True,
        "last_readiness_at": None,
        "failing_check": None,
        "version_pin": "2.1.319",
        "lines": [{"check": "cli", "ok": True, "text": "ok"}],
        "models": [],
        "setup": setup,
    }
    return {"items": [row], "next_cursor": None}


def _working(run_id: str = RUN_ID, label: str = "orders-api / story 4") -> dict[str, object]:
    return {
        "run_id": run_id,
        "run_label": label,
        "path": "epic/story/implement",
        "kind": "agent",
        "started_at": "2026-11-11T10:05:00Z",
    }


def _parked(run_id: str = PARKED_ID, label: str = "billing / story 2") -> dict[str, object]:
    return {
        "run_id": run_id,
        "run_label": label,
        "status": "needs_you",
        "park_kind": "checkpoint",
        "queue_reason": None,
    }


def _activity(
    working: list[dict[str, object]] | None = None,
    in_engine: list[dict[str, object]] | None = None,
    dbos: str = "1",
) -> dict[str, object]:
    return {
        "working": working or [],
        "in_engine": in_engine or [],
        "hold": None,
        "dbos_application_version": dbos,
    }


def _serve_activity(folder: Folder, body: dict[str, object]) -> None:
    (folder.served / "activity.json").write_text(json.dumps(body, indent=2))


def _run(
    folder: Folder, *args: str, answers: str | None = None, **env: str
) -> subprocess.CompletedProcess[str]:
    dropped = {"GHCR_TOKEN", "GITHUB_TOKEN", "IMAGE_TAG", "DOCKER_CONFIG", *SIX}
    clean = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(folder.path / "install.sh"), *args],
        capture_output=True,
        text=True,
        cwd=folder.path,
        env={**clean, **folder.env, **env},
        check=False,
        input=answers,
    )


def _upgrade(folder: Folder, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    return _run(folder, "upgrade", "--tag", NEW, "--yes", *args, **env)


def _out(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def _hashes(path: Path) -> dict[str, str]:
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file()
    }


def _calls(folder: Folder, kind: str | None = None) -> list[str]:
    if not folder.calls.is_file():
        return []
    lines = folder.calls.read_text().splitlines()
    if kind is None:
        return lines
    return [line[len(kind) + 1 :] for line in lines if line.startswith(f"{kind} ")]


def _upgrade_dir(folder: Folder) -> Path:
    (only,) = sorted((folder.path / ".upgrade").iterdir())
    return only


def _assert_refused_untouched(
    folder: Folder, before: dict[str, str], result: subprocess.CompletedProcess[str]
) -> None:
    assert "refused: nothing was changed" in result.stderr
    assert _hashes(folder.path) == before
    assert not (folder.path / ".upgrade").exists()
    docker = _calls(folder, "docker")
    assert not any("pg_dump" in c for c in docker), docker
    assert not any(c.endswith(" setup") for c in docker), docker
    assert not any(" up -d " in c for c in docker), docker
    assert not any(c.startswith("POST") and "instance/hold" in c for c in _calls(folder, "curl"))


# ── AC1: a working step ──────────────────────────────────────────────────────


@needs_bash
def test_a_working_step_refuses_with_exit_3_and_changes_nothing(folder: Folder) -> None:
    _serve_activity(folder, _activity(working=[_working()]))
    before = _hashes(folder.path)

    result = _upgrade(folder)

    assert result.returncode == EXIT_WORKING, _out(result)
    assert (
        f"run {RUN_ID} (orders-api / story 4) step epic/story/implement (agent) "
        "working since 2026-11-11T10:05:00Z"
    ) in result.stderr
    _assert_refused_untouched(folder, before, result)


@needs_bash
def test_every_working_step_is_named_when_paths_carry_brackets(folder: Folder) -> None:
    first = {**_working(), "path": "epics[1].stories[3].build"}
    second = {**_working(run_id=PARKED_ID, label="billing / story 2"), "path": "epics[0].plan"}
    _serve_activity(folder, _activity(working=[first, second]))

    result = _upgrade(folder)

    assert result.returncode == EXIT_WORKING, _out(result)
    assert f"run {RUN_ID} (orders-api / story 4) step epics[1].stories[3].build (agent)" in (
        result.stderr
    )
    assert f"run {PARKED_ID} (billing / story 2) step epics[0].plan (agent)" in result.stderr


# ── AC2: the engine version ──────────────────────────────────────────────────


@needs_bash
def test_an_engine_version_change_with_a_parked_run_refuses_with_exit_4(
    tmp_path: Path,
) -> None:
    folder = _build(tmp_path, {"DBOS_APPLICATION_VERSION": "2"})
    _serve_activity(folder, _activity(in_engine=[_parked()]))
    before = _hashes(folder.path)

    result = _upgrade(folder)

    assert result.returncode == EXIT_ENGINE, _out(result)
    assert f"run {PARKED_ID} (billing / story 2) needs_you checkpoint" in result.stderr
    assert "DBOS_APPLICATION_VERSION 1 → 2" in result.stderr
    _assert_refused_untouched(folder, before, result)


@needs_bash
def test_the_same_engine_version_does_not_refuse_a_parked_run(folder: Folder) -> None:
    _serve_activity(folder, _activity(in_engine=[_parked()]))

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    after = result.stdout.split("Runs that continue:", 1)[1]
    assert f"run {PARKED_ID} (billing / story 2) needs_you checkpoint" in after


@needs_bash
def test_an_engine_version_change_with_no_run_in_the_engine_proceeds(tmp_path: Path) -> None:
    folder = _build(tmp_path, {"DBOS_APPLICATION_VERSION": "2"})

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert "DBOS_APPLICATION_VERSION 1 → 2" in result.stdout
    assert (folder.path / "release.env").read_text() == (folder.staged / "release.env").read_text()


@needs_bash
def test_an_env_override_of_the_engine_version_is_the_value_compared(tmp_path: Path) -> None:
    folder = _build(tmp_path, {"DBOS_APPLICATION_VERSION": "2"})
    with (folder.path / ".env").open("a") as fh:
        fh.write("DBOS_APPLICATION_VERSION=1\n")
    _serve_activity(folder, _activity(in_engine=[_parked()]))

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert "DBOS_APPLICATION_VERSION: .env sets 1, release 2.0.0 pins 2" in result.stdout


@needs_bash
def test_a_stopped_backend_with_an_engine_version_change_refuses_with_exit_4(
    tmp_path: Path,
) -> None:
    folder = _build(tmp_path, {"DBOS_APPLICATION_VERSION": "2"})
    before = _hashes(folder.path)

    result = _upgrade(folder, SHIM_RUNNING="postgres")

    assert result.returncode == EXIT_ENGINE, _out(result)
    assert "backend-api is stopped" in result.stderr
    _assert_refused_untouched(folder, before, result)


# ── AC3: a folder from before manifests ──────────────────────────────────────


@needs_bash
def test_a_folder_without_a_manifest_refuses_with_exit_5(folder: Folder) -> None:
    (folder.path / "product-files.json").unlink()
    before = _hashes(folder.path)

    result = _upgrade(folder)

    assert result.returncode == EXIT_NO_MANIFEST, _out(result)
    assert "Migrating an existing folder" in result.stderr
    assert _hashes(folder.path) == before
    assert not (folder.path / ".upgrade").exists()
    docker = _calls(folder, "docker")
    assert not any(c.startswith("pull ") or "kit bootstrap" in c for c in docker), docker
    assert not any(c.split()[0] in {"POST", "DELETE", "PUT"} for c in _calls(folder, "curl"))


# ── AC4: the API the upgrade reads ───────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize("silent", ["SHIM_HEALTHZ_CODE", "SHIM_ACTIVITY_CODE"])
def test_a_running_backend_whose_api_does_not_answer_refuses_with_exit_1(
    folder: Folder, silent: str
) -> None:
    before = _hashes(folder.path)

    result = _upgrade(folder, **{silent: "000"})

    assert result.returncode == 1, _out(result)
    assert "did not answer" in result.stderr
    _assert_refused_untouched(folder, before, result)


@needs_bash
def test_a_stopped_backend_is_not_asked_for_anything(folder: Folder) -> None:
    result = _upgrade(folder, SHIM_RUNNING="postgres web-client")

    assert result.returncode == 0, _out(result)
    curls = _calls(folder, "curl")
    assert not any("instance/" in c for c in curls), curls
    assert not any(c.split()[0] in {"POST", "DELETE"} for c in curls), curls


# ── AC5: what a successful upgrade writes ────────────────────────────────────

CLIENT_FILES = (
    ".env",
    "templates/x.yaml",
    "templates/two words.yaml",
    "compose.override.yml",
    "setup/10-mine.sh",
    "llm-platform/.env",
    "llm-platform/docker-compose.yml",
)


@needs_bash
def test_a_successful_upgrade_replaces_the_product_files_and_nothing_else(
    folder: Folder,
) -> None:
    before = _hashes(folder.path)
    manifest = _manifest(folder.staged)
    paths = {row["path"]: row["role"] for row in manifest["files"]}  # type: ignore[index]

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert (folder.path / "VERSION").read_text().strip() == NEW
    for rel, role in paths.items():
        if role == "product":
            assert (folder.path / rel).read_bytes() == (folder.staged / rel).read_bytes(), rel
    assert (folder.path / "product-files.json").read_bytes() == (
        folder.staged / "product-files.json"
    ).read_bytes()
    after = _hashes(folder.path)
    for rel in CLIENT_FILES:
        assert after[rel] == before[rel], rel
    named = set(paths) | {"product-files.json"}
    for rel in set(after) - set(before):
        assert rel in named or rel.split("/")[0] in {".upgrade", "backups", "logs"}, rel
    for rel in set(before) - set(after):
        assert rel in named or rel in {"old-only.txt"}, rel
    assert (folder.path / "install.sh").stat().st_mode & 0o111
    argv = "\n".join(_calls(folder)) + (folder.calls.parent / "curl.argv").read_text()
    assert "llm-platform" not in argv


@needs_bash
def test_the_replaced_files_are_kept_under_previous(folder: Folder) -> None:
    before = _hashes(folder.path)

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    previous = _upgrade_dir(folder) / "previous"
    for rel in ("install.sh", "templates/shipped/x.yaml", "release.env", "VERSION"):
        assert hashlib.sha256((previous / rel).read_bytes()).hexdigest() == before[rel], rel
    assert (previous / "product-files.json").is_file()
    assert (folder.path / "install.sh").read_text().rstrip().endswith(f"# release {NEW}")


# ── AC6: edited files, removed files, seeds ──────────────────────────────────


@needs_bash
def test_a_locally_edited_product_file_is_kept_and_listed(folder: Folder) -> None:
    edited = folder.path / "templates" / "README.md"
    edited.write_text(edited.read_text() + "\nmy own note\n")
    mine = edited.read_bytes()

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    ts = _upgrade_dir(folder).name
    kept = f".upgrade/{ts}/previous/templates/README.md"
    assert (folder.path / kept).read_bytes() == mine
    assert f"edited: templates/README.md (your copy: {kept})" in result.stdout
    assert edited.read_bytes() == (folder.staged / "templates" / "README.md").read_bytes()
    assert "edited: install.sh" not in result.stdout


@needs_bash
def test_a_product_path_the_release_dropped_is_moved_and_listed(folder: Folder) -> None:
    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    ts = _upgrade_dir(folder).name
    assert not (folder.path / "old-only.txt").exists()
    assert (_upgrade_dir(folder) / "previous" / "old-only.txt").is_file()
    assert f"removed: old-only.txt (kept at .upgrade/{ts}/previous/old-only.txt)" in result.stdout


@needs_bash
def test_an_absent_seed_is_written_and_a_present_one_is_not(folder: Folder) -> None:
    (folder.path / "setup" / "bmad.choice").unlink()
    override = (folder.path / "compose.override.yml").read_bytes()

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert (folder.path / "setup" / "bmad.choice").read_text().strip() == "installed"
    assert "wrote setup/bmad.choice" in result.stdout
    assert (folder.path / "compose.override.yml").read_bytes() == override
    assert "wrote compose.override.yml" not in result.stdout


# ── AC7: the examples beside the client's copies ─────────────────────────────


@needs_bash
def test_an_improved_and_a_new_example_are_listed_beside_the_clients_copy(
    folder: Folder,
) -> None:
    mine = (folder.path / "templates" / "x.yaml").read_bytes()

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert "improved: templates/shipped/x.yaml (your copy: templates/x.yaml)" in result.stdout
    assert "new: templates/shipped/new.yaml" in result.stdout
    assert (folder.path / "templates" / "x.yaml").read_bytes() == mine
    assert (folder.path / "templates" / "shipped" / "x.yaml").read_text() == "x: 2\n"


@needs_bash
def test_a_path_with_a_space_or_regex_characters_is_matched_whole(folder: Folder) -> None:
    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert f"improved: {SPACED} (your copy: templates/two words.yaml)" in result.stdout
    assert f"improved: {BRACKETED}" not in result.stdout
    assert (folder.path / BRACKETED).read_text() == "brackets: 2\n"
    assert (folder.path / SPACED).read_text() == "words: 2\n"
    assert (folder.path / "templates" / "two words.yaml").read_text() == "mine: words\n"


# ── AC8: the hold, and a failure before the first write ──────────────────────


@needs_bash
def test_a_refused_hold_is_exit_3_naming_the_step(folder: Folder) -> None:
    problem = {
        "type": "about:blank",
        "title": "a step is working",
        "status": 409,
        "detail": "one step is working",
        "errors": [_working()],
    }
    (folder.served / "hold.json").write_text(json.dumps(problem, indent=2))
    before = _hashes(folder.path)

    result = _upgrade(folder, SHIM_HOLD_CODE="409", SHIM_HOLD_FILE=str(folder.served / "hold.json"))

    assert result.returncode == EXIT_WORKING, _out(result)
    assert f"run {RUN_ID} (orders-api / story 4) step epic/story/implement (agent)" in result.stderr
    assert "refused: nothing was changed" in result.stderr
    assert _hashes(folder.path) == before
    assert not (folder.path / ".upgrade").exists()
    assert not any(c.startswith("DELETE") for c in _calls(folder, "curl"))
    assert not any("pg_dump" in c for c in _calls(folder, "docker"))


@needs_bash
def test_a_failed_backup_releases_the_hold_and_leaves_the_folder(folder: Folder) -> None:
    before = _hashes(folder.path)

    result = _upgrade(folder, SHIM_DUMP_RC="1")

    assert result.returncode == 1, _out(result)
    assert "refused: nothing was changed" in result.stderr
    assert "database backup failed" in result.stderr
    curls = _calls(folder, "curl")
    post = next(i for i, c in enumerate(curls) if c.startswith("POST") and "instance/hold" in c)
    delete = next(i for i, c in enumerate(curls) if c.startswith("DELETE") and "instance/hold" in c)
    assert post < delete
    assert _hashes(folder.path) == before
    assert not (folder.path / ".upgrade").exists()
    assert not any(" up -d " in c for c in _calls(folder, "docker"))


@needs_bash
@pytest.mark.parametrize("image", ["missing", "broken"])
def test_an_image_that_cannot_be_read_refuses_with_dockers_output(
    folder: Folder, image: str
) -> None:
    before = _hashes(folder.path)

    result = _upgrade(folder, SHIM_IMAGE=image)

    assert result.returncode == 1, _out(result)
    assert (
        "Unable to find image" if image == "missing" else "layer does not exist"
    ) in result.stderr
    _assert_refused_untouched(folder, before, result)


@needs_bash
def test_a_failed_pull_refuses_with_exit_1(folder: Folder) -> None:
    before = _hashes(folder.path)

    result = _upgrade(folder, SHIM_PULL_RC="1")

    assert result.returncode == 1, _out(result)
    _assert_refused_untouched(folder, before, result)
    assert not any("kit bootstrap" in c for c in _calls(folder, "docker"))


@needs_bash
def test_a_release_without_a_manifest_is_refused_naming_it(folder: Folder) -> None:
    (folder.staged / "product-files.json").unlink()
    before = _hashes(folder.path)

    result = _upgrade(folder)

    assert result.returncode == 1, _out(result)
    assert "carries no product-files.json" in result.stderr
    _assert_refused_untouched(folder, before, result)


@needs_bash
def test_a_manifest_path_outside_the_folder_is_refused(folder: Folder) -> None:
    manifest = folder.staged / "product-files.json"
    data = json.loads(manifest.read_text())
    data["files"].append({"path": "../escape.txt", "sha256": "0" * 64, "role": "product"})
    manifest.write_text(json.dumps(data, indent=2))
    before = _hashes(folder.path)

    result = _upgrade(folder)

    assert result.returncode == 1, _out(result)
    assert "outside this folder" in result.stderr
    _assert_refused_untouched(folder, before, result)


@needs_bash
def test_the_tag_is_required_and_must_look_like_one(folder: Folder) -> None:
    before = _hashes(folder.path)

    missing = _run(folder, "upgrade", "--yes")
    odd = _run(folder, "upgrade", "--tag", 'x"; rm -rf /', "--yes")

    assert missing.returncode == 1 and "needs --tag" in missing.stderr
    assert odd.returncode == 1 and "not a release tag" in odd.stderr
    assert _hashes(folder.path) == before


@needs_bash
def test_declining_the_prompt_refuses_after_showing_the_plan(folder: Folder) -> None:
    before = _hashes(folder.path)

    result = _run(folder, "upgrade", "--tag", NEW, answers="n\n")

    assert result.returncode != 0, _out(result)
    assert "upgrade cancelled" in result.stderr
    assert "CLAUDE_CODE_VERSION" in result.stdout
    assert "improved: templates/shipped/x.yaml" in result.stdout
    _assert_refused_untouched(folder, before, result)


# ── AC9: a failure after the first write ─────────────────────────────────────


@needs_bash
@pytest.mark.parametrize("failing", [{"SHIM_UP_RC": "1"}, {"SHIM_VERIFY_FAIL": "1"}])
def test_a_failed_start_names_the_step_the_previous_files_and_the_rollback(
    folder: Folder, failing: dict[str, str]
) -> None:
    result = _upgrade(folder, **failing)

    assert result.returncode == 1, _out(result)
    ts = _upgrade_dir(folder).name
    assert "upgrade stopped at start" in result.stderr
    assert f".upgrade/{ts}/previous/" in result.stderr
    assert f"upgrade --tag {OLD}" in result.stderr
    assert (folder.path / "VERSION").read_text().strip() == NEW


@needs_bash
def test_a_failed_setup_run_is_reported_and_the_stack_still_starts(folder: Folder) -> None:
    result = _upgrade(folder, SHIM_SETUP_RC="2")

    assert result.returncode == 0, _out(result)
    assert "setup exited 2" in _out(result)
    assert any(" up -d " in c for c in _calls(folder, "docker"))


# ── AC10: the order, and the report ──────────────────────────────────────────


def _index(calls: list[str], needle: str) -> int:
    return next(i for i, c in enumerate(calls) if needle in c)


@needs_bash
def test_prepare_runs_between_the_dump_and_the_setup_service_without_exec(folder: Folder) -> None:
    """epic 5 story 1, 2026-11-11 AD-28 amendment."""
    result = _upgrade(folder, SHIM_RUNNING="postgres")

    assert result.returncode == 0, _out(result)
    calls = _calls(folder)
    order = [
        _index(calls, "pg_dump"),
        _index(calls, PREPARE_CALL),
        _index(calls, "-e ORCH_SETUP_TRIGGER=upgrade"),
    ]
    assert order == sorted(order), calls
    assert not [c for c in calls if "exec -T backend-api" in c]


@needs_bash
def test_the_calls_come_in_the_documented_order(folder: Folder) -> None:
    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    calls = _calls(folder)
    order = [
        _index(calls, f"docker pull ghcr.io/rebecamurillo/ai-orchestrator/backend-api:{NEW}"),
        _index(calls, "kit bootstrap"),
        _index(calls, "curl GET http://127.0.0.1:8000/api/v1/instance/activity"),
        _index(calls, "curl POST http://127.0.0.1:8000/api/v1/instance/hold"),
        _index(calls, "pg_dump"),
        _index(calls, f"-e ORCH_SETUP_TRIGGER=upgrade -e ORCH_RELEASE={NEW}"),
        _index(calls, " up -d --wait"),
    ]
    assert order == sorted(order), calls
    post = next(c for c in calls if c.startswith("curl POST") and "instance/hold" in c)
    assert json.loads(post.split(" ", 3)[3]) == {
        "ttl_seconds": 1800,
        "reason": f"upgrade to {NEW}",
    }
    # the dump is taken from the old files, setup runs on the new ones
    states = [c for c in calls if c.startswith("state ")]
    assert states == [f"state VERSION={OLD}", f"state VERSION={NEW}"]
    # nothing deletes the hold: the new backend clears it at start
    assert not any(c.startswith("curl DELETE") for c in calls)


@needs_bash
def test_no_pull_reads_the_local_image(folder: Folder) -> None:
    result = _upgrade(folder, "--no-pull")

    assert result.returncode == 0, _out(result)
    docker = _calls(folder, "docker")
    assert not any(c.startswith("pull ") for c in docker), docker
    assert any(
        c.startswith("run --rm --pull never ") and c.endswith(f"backend-api:{NEW} kit bootstrap")
        for c in docker
    ), docker


@needs_bash
def test_the_report_lists_pins_overrides_and_leaves_env_alone(folder: Folder) -> None:
    with (folder.path / ".env").open("a") as fh:
        fh.write("CODEX_VERSION=0.1.0 # kept by hand\n")
    env_before = (folder.path / ".env").read_bytes()
    old_pin = _pin(folder.path, "CLAUDE_CODE_VERSION")
    codex = _pin(folder.staged, "CODEX_VERSION")

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert f"{OLD} → {NEW}" in result.stdout
    claude = next(ln for ln in result.stdout.splitlines() if "CLAUDE_CODE_VERSION" in ln)
    assert f"CLAUDE_CODE_VERSION {old_pin} → 2.1.400" in claude
    assert "downgrade" not in claude
    assert not any("CODEX_VERSION" in ln and "→" in ln for ln in result.stdout.splitlines())
    assert f"CODEX_VERSION: .env sets 0.1.0, release {NEW} pins {codex}" in result.stdout
    assert "setup claude: ok" in result.stdout
    assert (folder.path / ".env").read_bytes() == env_before


@needs_bash
@pytest.mark.parametrize(
    ("new", "downgrade"), [("0.0.1", True), ("99.0.0", False), ("2.1.319-beta.1", True)]
)
def test_only_a_downgrade_is_marked(tmp_path: Path, new: str, *, downgrade: bool) -> None:
    folder = _build(tmp_path, {"CLAUDE_CODE_VERSION": new})

    result = _upgrade(folder)

    line = next(ln for ln in result.stdout.splitlines() if "CLAUDE_CODE_VERSION" in ln)
    assert f"→ {new}" in line
    assert ("(downgrade)" in line) is downgrade


@needs_bash
def test_a_release_whose_pins_are_unchanged_prints_none(tmp_path: Path) -> None:
    folder = _build(tmp_path, {})

    result = _upgrade(folder)

    assert result.returncode == 0, _out(result)
    assert "release pins: unchanged" in result.stdout
    assert "no pin of release.env is overridden in .env" in result.stdout


# ── AC11: what the script no longer is ───────────────────────────────────────


def test_the_script_has_no_pin_writing_left_and_keeps_its_pin_shape() -> None:
    text = (DEPLOY_DIR / "install.sh").read_text()
    for gone in ("require_pin_declarations", "write_release_pins", "HARNESS_PIN_VARIABLES"):
        assert gone not in text, gone
    shape = next(
        line
        for line in (REPO_ROOT / "scripts/harness/_common.sh").read_text().splitlines()
        if line.startswith("PLAIN_VERSION=")
    )
    assert shape in text.splitlines()
    for forbidden in ("declare -A", "local -A", "mapfile", "readarray", "sed -i"):
        assert forbidden not in text, forbidden
