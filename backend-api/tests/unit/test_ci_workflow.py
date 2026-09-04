"""The pipeline, read as a document rather than trusted as prose.

Nothing in this repository can run GitHub Actions, so the workflow is asserted here: the
five gates in AD-18's fixed order, each one a `make` target that exists, chained by `needs:`
so a red gate stops the ones after it. What local execution proves is that those targets
pass on this machine; what this module proves is that CI runs those targets and no others,
in that order, with no credential of its own.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml

from tests.unit.conftest import REPO_ROOT

WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = REPO_ROOT / "Makefile"
README = REPO_ROOT / "README.md"

#: AD-18, in order. The value is the `make` target the job must run.
GATES = ("lint", "unit", "e2e-api", "e2e-ui", "images")
GATE_TARGETS = {
    "lint": "lint",
    "unit": "test",
    "e2e-api": "e2e-api",
    "e2e-ui": "e2e-ui",
    "images": "images",
}

#: `owner/repo@<full commit sha>` — a moving tag is not a pin.
PINNED_ACTION = re.compile(r"^[\w.-]+/[\w.-]+(/[\w.-]+)*@[0-9a-f]{40}$")

#: AD-5: neither may ever reach a job's environment. The pipeline needs no credential at all.
FORBIDDEN_NAMES = ("GITHUB_TOKEN", "LITELLM_SPEND_KEY", "LITELLM_API_KEY")


@pytest.fixture(scope="module")
def workflow() -> dict[str, Any]:
    assert WORKFLOW.is_file(), f"{WORKFLOW} does not exist"
    document = yaml.safe_load(WORKFLOW.read_text())
    assert isinstance(document, dict)
    return document


@pytest.fixture(scope="module")
def jobs(workflow: dict[str, Any]) -> dict[str, Any]:
    return workflow["jobs"]


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return list(job["steps"])


def run_script(job: dict[str, Any]) -> str:
    return "\n".join(step.get("run", "") for step in steps(job))


def triggers_of(workflow: dict[str, Any]) -> dict[str, Any]:
    """`on:` is YAML 1.1's boolean true; a quoted `'on':` is the string. Accept either."""
    return workflow[True] if True in workflow else workflow["on"]


def test_the_workflow_runs_on_a_push_to_any_branch_and_on_a_pull_request(
    workflow: dict[str, Any],
) -> None:
    triggers = triggers_of(workflow)

    assert set(triggers) == {"push", "pull_request"}
    assert triggers["push"]["branches"] == ["**"]


def test_one_run_per_ref_and_the_older_one_is_cancelled(workflow: dict[str, Any]) -> None:
    """Two pushes to the same branch must not race for the same gates."""
    assert "github.ref" in workflow["concurrency"]["group"]
    assert workflow["concurrency"]["cancel-in-progress"] is True


def test_the_pipeline_reads_the_repository_and_writes_nothing(workflow: dict[str, Any]) -> None:
    assert workflow["permissions"] == {"contents": "read"}


def test_the_gates_are_the_jobs(jobs: dict[str, Any]) -> None:
    assert tuple(jobs) == GATES


def test_the_gates_are_chained_in_the_order_ad_18_fixes(jobs: dict[str, Any]) -> None:
    """lint → unit → e2e-api → e2e-ui: a failed gate stops the pipeline."""
    assert "needs" not in jobs["lint"]
    for gate, previous in zip(GATES[1:], GATES[:-1], strict=True):
        assert jobs[gate]["needs"] == previous


@pytest.mark.parametrize("gate", GATES)
def test_every_job_runs_its_gate_as_a_make_target(gate: str, jobs: dict[str, Any]) -> None:
    """No gate logic lives in the workflow: CI types what the Operator types."""
    assert f"make {GATE_TARGETS[gate]}" in run_script(jobs[gate])


def test_the_lint_job_proves_the_contract_is_current(jobs: dict[str, Any]) -> None:
    """AD-3: `gen:api --check` compares the two generated files; only re-exporting from the
    Pydantic source proves `contracts/openapi.json` itself is not stale."""
    script = run_script(jobs["lint"])

    assert "make openapi" in script
    assert "git diff --exit-code" in script
    assert "contracts" in script
    assert "web-client/src/api/schema.d.ts" in script


def test_the_unit_job_also_runs_the_changed_lines_gate(jobs: dict[str, Any]) -> None:
    script = run_script(jobs["unit"])

    assert "make coverage" in script
    assert "DIFF_COVER_BASE=" in script


def test_every_make_target_the_pipeline_runs_exists(jobs: dict[str, Any]) -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))
    declared = set(phony.split()[1:])

    script = "\n".join(run_script(job) for job in jobs.values())
    invoked = set(re.findall(r"\bmake ([a-z][a-z0-9-]*)", script))

    assert invoked
    assert invoked <= declared, invoked - declared


def test_the_unit_job_checks_out_enough_history_for_diff_cover(jobs: dict[str, Any]) -> None:
    """`--compare-branch` needs the base branch; a shallow clone reports no diff at all."""
    checkout = next(step for step in steps(jobs["unit"]) if "checkout" in step.get("uses", ""))

    assert checkout["with"]["fetch-depth"] == 0


def test_the_e2e_api_job_brings_up_postgres_and_waits_for_the_backend(jobs: dict[str, Any]) -> None:
    script = run_script(jobs["e2e-api"])

    assert re.search(r"docker compose up .*postgres", script)
    assert "orchestrator.main" in script
    assert "/healthz" in script


def test_the_e2e_ui_job_installs_the_browser_it_drives(jobs: dict[str, Any]) -> None:
    assert "playwright install" in run_script(jobs["e2e-ui"])


@pytest.mark.parametrize("gate", GATES)
def test_every_action_is_pinned_to_a_commit(gate: str, jobs: dict[str, Any]) -> None:
    """A tag can be moved under the pipeline; a commit cannot."""
    used = [step["uses"] for step in steps(jobs[gate]) if "uses" in step]

    assert used
    for reference in used:
        assert PINNED_ACTION.match(reference), reference


@pytest.mark.parametrize("name", FORBIDDEN_NAMES)
def test_the_pipeline_names_no_credential(name: str) -> None:
    """The gates run on the committed `.env.example` placeholders (AD-5)."""
    assert name not in WORKFLOW.read_text()


def test_the_pipeline_reads_no_repository_secret() -> None:
    assert "secrets." not in WORKFLOW.read_text()


def test_the_readme_names_the_gates_the_pipeline_runs(jobs: dict[str, Any]) -> None:
    """A contributor reading the README must find the same list CI enforces."""
    readme = README.read_text()
    section = readme[readme.index("## Contributing") :]

    for target in sorted(set(GATE_TARGETS.values()) | {"coverage"}):
        assert f"make {target}" in section, target
    assert ".github/workflows/ci.yml" in section
    assert "100" in section and "90" in section
