import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

FORBIDDEN_PROJECTS = frozenset({"aio", "aio-host", "ai-orchestrator", "ai-orchestrator-host"})
PRODUCTION_HOME = Path("/Users/rebecam/projects/orchestrator-home")
PREFIX = "aio-deploy-"


class GuardRefusal(Exception):
    pass


def _running_projects() -> set[str]:
    try:
        done = subprocess.run(
            ["docker", "compose", "ls", "--format", "json"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise GuardRefusal(f"docker compose ls could not be run ({exc}); refusing") from exc
    if done.returncode != 0:
        raise GuardRefusal(f"docker compose ls exited {done.returncode}; refusing")
    try:
        return {entry["Name"] for entry in json.loads(done.stdout or "[]")}
    except (ValueError, KeyError, TypeError) as exc:
        raise GuardRefusal(f"docker compose ls output unreadable ({exc}); refusing") from exc


def check_project(name: str) -> None:
    if name in FORBIDDEN_PROJECTS:
        raise GuardRefusal(f"project {name!r} is a production project name")
    if not name.startswith(PREFIX):
        raise GuardRefusal(f"project {name!r} does not start with {PREFIX!r}")
    if name in _running_projects():
        raise GuardRefusal(f"project {name!r} is already running (docker compose ls)")


def check_folder(path: str | Path) -> None:
    resolved = Path(path).resolve()
    if resolved == PRODUCTION_HOME or resolved.is_relative_to(PRODUCTION_HOME):
        raise GuardRefusal(f"folder {str(path)!r} is the production home {PRODUCTION_HOME}")


def check_argv(argv: Sequence[str]) -> None:
    for i, arg in enumerate(argv):
        if Path(arg).name == "docker" and "login" in argv[i + 1 :]:
            raise GuardRefusal(f"argv {list(argv)!r} runs docker login")
