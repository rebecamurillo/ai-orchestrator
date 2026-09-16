"""The clone check against the running stack, over repositories this suite makes itself.

Every repository here is a bare one created under `WORK_DIR/e2e-fixtures` and registered by
its `file://` URL, so the gate proves the whole path — route, use case, adapter, real `git`,
real database — without depending on github.com being reachable from wherever this runs, and
without a credential (AD-5: the pipeline holds none).

**The fixture, in both topologies.** In CI the backend runs from source on the same machine
as this suite, so a directory this file creates is a directory the backend can clone. Under
`make up` the backend runs in a container and only the named volumes are shared, so the same
script runs through `docker compose exec -T backend-api` instead. Either way the registered
URL is the same, and neither branch needs a new setting or a new mount. Nothing skips: a run
where neither route works fails naming both, because a gate that skipped would report success
for a suite that checked nothing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROJECTS = "/api/v1/projects"
REPOSITORIES = "/api/v1/repositories"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

#: Where this suite's bare repositories live, under the work directory both topologies share.
FIXTURE_DIRECTORY = "e2e-fixtures"

BRANCH = "main"
MANIFEST_PATH = "_bmad/_config/manifest.yaml"
OTHER_VERSION = "0.0.1-not-this-instance"

FOUR = 4
ONE = 1
THREE = 3

REPO_ROOT = Path(__file__).resolve().parents[3]

#: `test_durability.py`'s own bound, for the same `docker compose exec` route.
DOCKER_TIMEOUT_SECONDS = 60.0

#: One script, run either here or inside the container: `$1` is the directory, `$2` the
#: repository name, `$3` the manifest to commit (empty for a repository that carries none).
MAKE_BARE_REPOSITORY = """
set -e
dir="$1"; name="$2"; manifest="$3"
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare "$dir/$name.git"
git init --quiet --initial-branch=main "$dir/$name.seed"
cd "$dir/$name.seed"
git config user.email e2e@example.invalid
git config user.name e2e
echo "$name" > README.md
if [ -n "$manifest" ]; then
  mkdir -p _bmad/_config
  printf '%s' "$manifest" > _bmad/_config/manifest.yaml
fi
git add --all
git commit --quiet --message seed
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""


class Fixtures:
    """Makes bare repositories where the backend can reach them, however it is running."""

    def __init__(self, work_dir: Path) -> None:
        self.directory = work_dir / FIXTURE_DIRECTORY
        self.refusals: list[str] = []

    def url(self, name: str) -> str:
        """The URL a Repository is registered with — the same string in both topologies."""
        return f"file://{self.directory}/{name}.git"

    def make(self, manifest: str = "") -> str:
        """A fresh bare repository with one commit on `main`. Returns its `file://` URL."""
        name = str(uuid4())
        arguments = [str(self.directory), name, manifest]
        for route in (self._here, self._in_the_container):
            if route(arguments):
                return self.url(name)
        pytest.fail(
            "no route to create an e2e fixture repository: writing "
            f"{self.directory} directly and `docker compose exec -T backend-api` both "
            "failed — " + " | ".join(self.refusals)
        )

    def absent(self) -> str:
        """A URL under the same directory that names nothing, and never will."""
        return self.url(str(uuid4()))

    def _here(self, arguments: list[str]) -> bool:
        """The CI topology: the backend runs on this machine, so this path is its path."""
        return self._run(["sh", "-c", MAKE_BARE_REPOSITORY, "sh", *arguments], "on this host")

    def _in_the_container(self, arguments: list[str]) -> bool:
        """The `make up` topology: only the `work` volume is shared, so run it in there."""
        return self._run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "backend-api",
                "sh",
                "-c",
                MAKE_BARE_REPOSITORY,
                "sh",
                *arguments,
            ],
            "in the backend-api container",
        )

    def _run(self, command: list[str], where: str) -> bool:
        try:
            # bounded (Operator revision, 2026-09-16): `docker compose exec` against an
            # unhealthy container blocks with no ceiling of its own
            completed = subprocess.run(  # fixed argv, no shell
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=DOCKER_TIMEOUT_SECONDS,
            )
        except OSError as error:
            self.refusals.append(f"{where}: {error}")
            return False
        except subprocess.TimeoutExpired:
            self.refusals.append(f"{where}: no answer within {DOCKER_TIMEOUT_SECONDS:.0f}s")
            return False
        if completed.returncode != 0:
            self.refusals.append(f"{where}: {(completed.stderr or completed.stdout).strip()}")
            return False
        return True


def manifest_stating(version: str) -> str:
    return f"installation:\n  version: {version}\n  installDate: 2026-09-05\nmodules: []\n"


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    """The same environment the backend reads (AD-20); `stack` first, so it is up."""
    return Settings()


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture
def project_id(authenticated: httpx.Client) -> str:
    response = authenticated.post(PROJECTS, json={"name": f"e2e clone check {uuid4()}"})
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"])


def create_repository(
    client: httpx.Client, project_id: str, url: str, **overrides: object
) -> dict[str, object]:
    payload: dict[str, object] = {"url": url, "default_branch": BRANCH}
    payload.update(overrides)
    response = client.post(f"{PROJECTS}/{project_id}/repositories", json=payload)
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, object] = response.json()
    return body


def clone_check_url(repository_id: str) -> str:
    return f"{REPOSITORIES}/{repository_id}/clone-check"


def run_check(client: httpx.Client, repository_id: str) -> dict[str, object]:
    response = client.post(clone_check_url(repository_id))
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, object] = response.json()
    return body


def line(result: dict[str, object], index: int) -> dict[str, object]:
    lines: list[dict[str, object]] = result["lines"]  # type: ignore[assignment]
    return lines[index]


# ── the ok path ──────────────────────────────────────────────────────────────


def test_a_reachable_repository_passes_every_line(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    """The whole path, against real `git`: four lines, and the version the manifest states."""
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(authenticated, project_id, url)

    result = run_check(authenticated, str(repository["id"]))

    assert result["status"] == "ok", result
    assert len(result["lines"]) == FOUR
    assert [item["status"] for item in result["lines"]] == ["ok"] * FOUR  # type: ignore[union-attr]
    assert result["bmad_version"] == settings.bmad_version
    assert result["hint"] == ""
    assert result["at"] is not None


def test_a_manifest_stating_another_version_reads_outdated(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures
) -> None:
    url = fixtures.make(manifest_stating(OTHER_VERSION))
    repository = create_repository(authenticated, project_id, url)

    result = run_check(authenticated, str(repository["id"]))

    assert result["status"] == "ok", result
    assert result["bmad_version"] == "outdated"


def test_a_repository_carrying_no_method_reads_missing_and_still_passes(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures
) -> None:
    """A repository with no `_bmad/` is one this orchestrator can still install into."""
    repository = create_repository(authenticated, project_id, fixtures.make())

    result = run_check(authenticated, str(repository["id"]))

    assert result["status"] == "ok", result
    assert result["bmad_version"] == "missing"
    assert MANIFEST_PATH in line(result, 3)["output"]  # type: ignore[operator]


def test_a_second_check_fetches_the_base_it_already_cloned(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    """The base clone is made once; every check after it is a fetch (AD-14)."""
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(authenticated, project_id, url)

    first = run_check(authenticated, str(repository["id"]))
    second = run_check(authenticated, str(repository["id"]))

    assert "cloned" in line(first, 1)["output"]  # type: ignore[operator]
    assert "fetched" in line(second, 1)["output"]  # type: ignore[operator]
    assert second["status"] == "ok", second


# ── the failing lines ────────────────────────────────────────────────────────


def test_a_url_that_exists_nowhere_fails_at_the_first_line(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures
) -> None:
    repository = create_repository(authenticated, project_id, fixtures.absent())

    result = run_check(authenticated, str(repository["id"]))

    assert result["status"] == "failed", result
    assert len(result["lines"]) == ONE
    assert line(result, 0)["status"] == "failed"
    # git's own sentence, verbatim: the Operator needs what git said, not a paraphrase
    assert "does not appear to be a git repository" in str(result["output"])
    assert result["hint"], "a failure the rules recognise carries a hint"


def test_a_default_branch_the_origin_does_not_hold_fails_the_third_line(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(authenticated, project_id, url, default_branch="develop")

    result = run_check(authenticated, str(repository["id"]))

    assert result["status"] == "failed", result
    assert len(result["lines"]) == THREE
    assert line(result, 2)["status"] == "failed"
    assert result["hint"] == "branch develop does not exist on origin"


# ── reading the stored result ────────────────────────────────────────────────


def test_a_repository_that_was_never_checked_reads_pending(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures
) -> None:
    repository = create_repository(authenticated, project_id, fixtures.absent())

    response = authenticated.get(clone_check_url(str(repository["id"])))

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "pending"
    assert response.json()["lines"] == []


def test_reading_answers_the_result_the_last_check_stored(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    """Through the database: the lines survive the `jsonb` round trip."""
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(authenticated, project_id, url)
    ran = run_check(authenticated, str(repository["id"]))

    response = authenticated.get(clone_check_url(str(repository["id"])))

    assert response.status_code == HTTP_OK
    assert response.json() == ran


def test_a_checked_repository_reads_its_lines_beside_its_check(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(authenticated, project_id, url)
    run_check(authenticated, str(repository["id"]))

    body = authenticated.get(f"{REPOSITORIES}/{repository['id']}").json()

    assert set(body["clone_check"]) == {"status", "at", "output", "bmad_version"}
    assert len(body["clone_check_lines"]) == FOUR
    assert body["clone_check_hint"] == ""


def test_an_unknown_repository_id_is_a_404(authenticated: httpx.Client) -> None:
    for method in ("get", "post"):
        response = authenticated.request(method, clone_check_url(UNKNOWN_ID))

        assert response.status_code == HTTP_NOT_FOUND, method
        assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_both_operations_need_the_bearer(client: httpx.Client) -> None:
    for method in ("get", "post"):
        response = client.request(method, clone_check_url(UNKNOWN_ID))

        assert response.status_code == HTTP_UNAUTHORIZED, method


# ── the check a save runs ────────────────────────────────────────────────────


def test_a_save_checks_every_repository_and_a_failure_never_fails_the_save(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    """The story's acceptance criterion, end to end."""
    good = fixtures.make(manifest_stating(settings.bmad_version))
    bad = fixtures.absent()
    create_repository(authenticated, project_id, good)
    create_repository(authenticated, project_id, bad)

    response = authenticated.put(f"{PROJECTS}/{project_id}", json={"name": f"saved {uuid4()}"})

    assert response.status_code == HTTP_OK, response.text
    reachable, missing = response.json()["repositories"]
    assert reachable["clone_check"]["status"] == "ok", reachable
    assert len(reachable["clone_check_lines"]) == FOUR
    assert reachable["clone_check"]["bmad_version"] == settings.bmad_version
    assert missing["clone_check"]["status"] == "failed", missing
    assert missing["clone_check_lines"][0]["status"] == "failed"
    assert "does not appear to be a git repository" in missing["clone_check"]["output"]
    assert missing["clone_check_hint"]


def test_the_results_a_save_wrote_are_the_ones_a_later_read_answers(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, settings: Settings
) -> None:
    """The save commits the checks; nothing has to be re-run to see them."""
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(authenticated, project_id, url)
    authenticated.put(f"{PROJECTS}/{project_id}", json={"name": f"saved {uuid4()}"})

    response = authenticated.get(clone_check_url(str(repository["id"])))

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "ok", response.text


# ── the credential (AD-5, hard rule 5) ───────────────────────────────────────


def test_no_response_this_suite_saw_carries_the_instance_token(
    authenticated: httpx.Client, project_id: str, fixtures: Fixtures, token: str
) -> None:
    """The bearer is the one credential this process holds that a body could echo."""
    repository = create_repository(authenticated, project_id, fixtures.absent())

    body = authenticated.post(clone_check_url(str(repository["id"]))).text

    assert token not in body
