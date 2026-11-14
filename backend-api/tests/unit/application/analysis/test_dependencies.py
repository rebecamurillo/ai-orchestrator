"""The dependency diff and its lookups (epic 5 story 3, AC1-AC4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from orchestrator.application.analysis.dependencies import (
    DependencyDiff,
    DependencySignals,
    diff_dependencies,
    lookup_dependencies,
    not_checked,
)
from orchestrator.application.analysis.secrets import SARIF_MEDIA_TYPE
from orchestrator.application.analysis.tier1a import Count
from orchestrator.domain.entities.analysis import AnalysisArtifact
from orchestrator.domain.ports.git_analysis import NameStatus
from orchestrator.domain.ports.package_lookup import LookupUnavailable, PackageMeta, VulnReport
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.package_lookup import FakePackageLookup

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "analysis" / "tier1b"
NOW = FakeClock(datetime(2026, 11, 13, 12, 0, tzinfo=UTC)).now()
PRIVATE = "https://npm.example.internal/secret-token-path"
ANALYSIS = UUID(int=3)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


def reader(files: dict[tuple[str, str], str]) -> Any:
    return lambda ref, path: files.get((ref, path))


def pnpm_diff() -> DependencyDiff:
    files = {
        ("b", "pnpm-lock.yaml"): fixture("pnpm-lock.base.yaml"),
        ("h", "pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
    }
    return diff_dependencies([NameStatus("M", "pnpm-lock.yaml", None)], reader(files), "b", "h")


def meta(days: float | None = 10, licence: str | None = "MIT", exists: bool = True) -> PackageMeta:
    published = None if days is None else NOW - timedelta(days=days)
    return PackageMeta(exists, published, licence)


def lookup(
    diff: DependencyDiff,
    fake: FakePackageLookup,
    *,
    lookups: bool = True,
    registries: dict[str, str] | None = None,
    written: list[str] | None = None,
) -> DependencySignals:
    ids = iter(range(100, 200))

    def write_lock(path: str) -> Path:
        if written is not None:
            written.append(path)
        return Path("/scratch") / path

    return lookup_dependencies(
        diff,
        lookup=fake,
        lookups=lookups,
        registries=registries or {},
        now=NOW,
        write_lock=write_lock,
        new_id=lambda: UUID(int=next(ids)),
        analysis_id=ANALYSIS,
    )


def figure(signals: DependencySignals, metric: str, source: str | None = None) -> int:
    (found,) = [c for c in signals.counts if (c.metric_id, c.source) == (metric, source)]
    return found.value


def artifact(signals: DependencySignals, tool: str) -> AnalysisArtifact:
    (found,) = [a for a in signals.artifacts if a.tool == tool]
    return found


# ── the diff (AC1) ───────────────────────────────────────────────────────────


def test_a_pnpm_lock_adds_left_pad_and_upgrades_zod() -> None:
    diff = pnpm_diff()
    assert [c.name for c in diff.added] == ["left-pad"]
    assert [c.name for c in diff.upgraded] == ["zod"]
    assert diff.removed == ()
    assert diff.lock_paths == ("pnpm-lock.yaml",)
    assert diff.manifest_only is False
    signals = lookup(diff, FakePackageLookup(), lookups=False)
    assert figure(signals, "code.deps_changed", "added") == 1
    assert figure(signals, "code.deps_changed", "upgraded") == 1
    assert figure(signals, "code.deps_changed", "removed") == 0


def test_a_removed_dependency_and_a_deleted_lock_file() -> None:
    files = {("b", "uv.lock"): fixture("uv.base.lock")}
    diff = diff_dependencies([NameStatus("D", "uv.lock", None)], reader(files), "b", "h")
    assert sorted(c.name for c in diff.removed) == ["old-lib", "requests"]
    assert diff.lock_paths == ()
    assert diff.manifest_only is False


def test_a_renamed_lock_file_is_read_at_base_under_its_old_path() -> None:
    files = {
        ("b", "old/poetry.lock"): fixture("poetry.base.lock"),
        ("h", "new/poetry.lock"): fixture("poetry.head.lock"),
    }
    changed = [NameStatus("R", "new/poetry.lock", "old/poetry.lock")]
    diff = diff_dependencies(changed, reader(files), "b", "h")
    assert [c.name for c in diff.added] == ["typing-extensions"]
    assert [c.name for c in diff.upgraded] == ["click"]
    assert diff.lock_paths == ("new/poetry.lock",)


def test_a_manifest_is_read_only_where_no_lock_file_exists_at_head() -> None:
    files = {
        ("b", "package.json"): fixture("package.base.json"),
        ("h", "package.json"): fixture("package.head.json"),
    }
    diff = diff_dependencies([NameStatus("M", "package.json", None)], reader(files), "b", "h")
    assert sorted(c.name for c in diff.added) == ["fsevents", "left-pad"]
    assert [c.name for c in diff.removed] == ["vitest"]
    assert [c.name for c in diff.upgraded] == ["zod"]
    assert diff.manifest_only is True
    assert diff.lock_paths == ()


def test_a_manifest_beside_a_lock_file_at_head_is_ignored() -> None:
    files = {
        ("b", "app/package.json"): fixture("package.base.json"),
        ("h", "app/package.json"): fixture("package.head.json"),
        ("h", "app/pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
    }
    diff = diff_dependencies([NameStatus("M", "app/package.json", None)], reader(files), "b", "h")
    assert diff == DependencyDiff()


def test_no_lock_file_or_manifest_changed_holds_nothing() -> None:
    diff = diff_dependencies([NameStatus("M", "src/a.py", None)], reader({}), "b", "h")
    assert diff == DependencyDiff()


# ── the lookups (AC2) ────────────────────────────────────────────────────────


def test_a_recent_added_dependency_with_a_licence_is_counted_and_detailed() -> None:
    fake = FakePackageLookup({("npm", "left-pad"): meta(days=10, licence="MIT")})
    written: list[str] = []
    signals = lookup(pnpm_diff(), fake, written=written)
    assert signals.words == {}
    assert figure(signals, "code.deps_not_in_registry") == 0
    assert figure(signals, "code.deps_recent") == 1
    assert figure(signals, "code.deps_licences", "MIT") == 1
    assert figure(signals, "code.deps_known_vulns") == 0
    assert signals.lookup_date == NOW.date()
    assert written == ["pnpm-lock.yaml"]
    detail = json.loads(artifact(signals, "dependencies").body)
    (added,) = [row for row in detail if row["change"] == "added"]
    assert added["recent"] is True
    assert added["looked_up_at"] == "2026-11-13"
    assert added["exists"] is True
    assert added["licence"] == "MIT"
    assert added["first_published"] == (NOW - timedelta(days=10)).isoformat()
    assert added["vulnerable"] is False
    (upgraded,) = [row for row in detail if row["change"] == "upgraded"]
    assert upgraded["before"] == ["3.22.4"]
    assert upgraded["after"] == ["3.23.8"]
    assert upgraded["exists"] is None
    assert upgraded["recent"] is None
    assert upgraded["vulnerable"] is None
    assert upgraded["looked_up_at"] is None


def test_a_dependency_missing_from_the_registry_and_one_without_a_licence() -> None:
    files = {
        ("b", "uv.lock"): "",
        ("h", "uv.lock"): fixture("uv.head.lock"),
    }
    diff = diff_dependencies([NameStatus("A", "uv.lock", None)], reader(files), "b", "h")
    fake = FakePackageLookup({("pypi", "new-lib"): meta(exists=False, days=None, licence=None)})
    signals = lookup(diff, fake)
    assert figure(signals, "code.deps_not_in_registry") == 1
    assert figure(signals, "code.deps_recent") == 0
    assert [c.source for c in signals.counts if c.metric_id == "code.deps_licences"] == [
        "none declared"
    ]


def test_a_dependency_with_no_first_publish_date_is_not_recent() -> None:
    signals = lookup(pnpm_diff(), FakePackageLookup({("npm", "left-pad"): meta(days=None)}))
    assert figure(signals, "code.deps_recent") == 0


def test_the_thirty_day_boundary() -> None:
    exact = lookup(pnpm_diff(), FakePackageLookup({("npm", "left-pad"): meta(days=30)}))
    inside = lookup(pnpm_diff(), FakePackageLookup({("npm", "left-pad"): meta(days=29)}))
    assert figure(exact, "code.deps_recent") == 0
    assert figure(inside, "code.deps_recent") == 1


def test_no_licence_reads_none_declared() -> None:
    signals = lookup(pnpm_diff(), FakePackageLookup({("npm", "left-pad"): meta(licence=None)}))
    assert figure(signals, "code.deps_licences", "none declared") == 1


# ── lookups off (AC3) ────────────────────────────────────────────────────────


def test_lookups_off_makes_no_call_and_holds_words_not_zeros() -> None:
    fake = FakePackageLookup()
    signals = lookup(pnpm_diff(), fake, lookups=False)
    assert fake.calls == []
    assert signals.words == {
        "code.deps_not_in_registry": "not run — lookups off",
        "code.deps_known_vulns": "not run — lookups off",
        "code.deps_recent": "not run — lookups off",
        "code.deps_licences": "not run — lookups off",
    }
    ids = {c.metric_id for c in signals.counts}
    assert ids == {"code.deps_changed"}
    assert signals.lookup_date is None
    assert signals.vulnerability_db_date is None
    assert signals.artifacts == ()


# ── registries that do not answer (AC4) ──────────────────────────────────────


def test_a_private_registry_that_does_not_answer_reads_not_checked_and_never_its_url() -> None:
    fake = FakePackageLookup(refuse_registries=[PRIVATE])
    signals = lookup(pnpm_diff(), fake, registries={"npm": PRIVATE})
    word = not_checked("npm private registry did not answer")
    assert word == "not checked — npm private registry did not answer"
    for metric in ("code.deps_not_in_registry", "code.deps_recent", "code.deps_licences"):
        assert signals.words[metric] == word
    assert PRIVATE not in json.dumps(dict(signals.words))
    assert not [
        c
        for c in signals.counts
        if c.metric_id not in ("code.deps_changed", "code.deps_known_vulns")
    ]
    assert fake.calls[0]["registry_url"] == PRIVATE


def test_a_public_registry_that_does_not_answer_reads_not_run() -> None:
    fake = FakePackageLookup({("npm", "left-pad"): LookupUnavailable("registry unreachable")})
    signals = lookup(pnpm_diff(), fake)
    for metric in ("code.deps_not_in_registry", "code.deps_recent", "code.deps_licences"):
        assert signals.words[metric] == "not run — registry unreachable"
    assert figure(signals, "code.deps_known_vulns") == 0


def test_the_private_word_wins_over_the_public_one() -> None:
    files = {
        ("b", "uv.lock"): "",
        ("h", "uv.lock"): fixture("uv.head.lock"),
        ("h", "pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
        ("b", "pnpm-lock.yaml"): fixture("pnpm-lock.base.yaml"),
    }
    changed = [NameStatus("M", "pnpm-lock.yaml", None), NameStatus("M", "uv.lock", None)]
    diff = diff_dependencies(changed, reader(files), "b", "h")
    fake = FakePackageLookup(
        {("pypi", "new-lib"): LookupUnavailable("registry unreachable")},
        refuse_registries=[PRIVATE],
    )
    signals = lookup(diff, fake, registries={"npm": PRIVATE})
    assert signals.words["code.deps_recent"] == "not checked — npm private registry did not answer"


def test_the_first_unanswered_lookup_stops_the_calls_to_that_ecosystem() -> None:
    files = {
        ("b", "package-lock.json"): "{}",
        ("h", "package-lock.json"): fixture("package-lock.head.json"),
    }
    diff = diff_dependencies([NameStatus("A", "package-lock.json", None)], reader(files), "b", "h")
    assert len(diff.added) == 3
    fake = FakePackageLookup(
        {("npm", "left-pad"): LookupUnavailable("x"), ("npm", "zod"): LookupUnavailable("x")}
    )
    lookup(diff, fake)
    assert [c["method"] for c in fake.calls].count("metadata") == 1


def test_a_dependency_added_in_two_folders_is_looked_up_once() -> None:
    text = fixture("pnpm-lock.head.yaml")
    files = {("h", "a/pnpm-lock.yaml"): text, ("h", "b/pnpm-lock.yaml"): text}
    changed = [NameStatus("A", "a/pnpm-lock.yaml", None), NameStatus("A", "b/pnpm-lock.yaml", None)]
    diff = diff_dependencies(changed, reader(files), "b", "h")
    fake = FakePackageLookup()
    signals = lookup(diff, fake)
    metadata_calls = [c for c in fake.calls if c["method"] == "metadata"]
    assert len(metadata_calls) == 4  # left-pad, zod, @scope/pkg, react: once each
    assert figure(signals, "code.deps_changed", "added") == 8


# ── vulnerabilities, the manifest fallback and nothing to look up ────────────


def test_the_osv_reports_are_merged_into_one_sarif_artifact_and_count_added_dependencies() -> None:
    sarif = json.dumps({"version": "2.1.0", "runs": [{"tool": "x"}]}).encode()
    fake = FakePackageLookup(
        vulnerabilities=VulnReport(
            frozenset({("left-pad", "1.3.0"), ("other", "9")}), sarif, "2.7.1"
        )
    )
    files = {
        ("b", "pnpm-lock.yaml"): fixture("pnpm-lock.base.yaml"),
        ("h", "pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
        ("h", "web/pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
    }
    changed = [NameStatus("M", "pnpm-lock.yaml", None), NameStatus("A", "web/pnpm-lock.yaml", None)]
    diff = diff_dependencies(changed, reader(files), "b", "h")
    written: list[str] = []
    signals = lookup(diff, fake, written=written)
    assert written == ["pnpm-lock.yaml", "web/pnpm-lock.yaml"]
    assert (
        figure(signals, "code.deps_known_vulns") == 2
    )  # left-pad, once per lock file that added it
    assert signals.osv_version == "2.7.1"
    assert signals.vulnerability_db_date == NOW.date()
    merged = artifact(signals, "osv-scanner")
    assert merged.media_type == SARIF_MEDIA_TYPE
    assert json.loads(merged.body) == {"version": "2.1.0", "runs": [{"tool": "x"}, {"tool": "x"}]}
    detail = json.loads(artifact(signals, "dependencies").body)
    assert [row["vulnerable"] for row in detail if row["name"] == "left-pad"] == [True, True]


def test_an_unreadable_scanner_report_leaves_no_sarif_artifact() -> None:
    for body in (b"", b"[]"):
        fake = FakePackageLookup(vulnerabilities=VulnReport(frozenset(), body, "2.7.1"))
        signals = lookup(pnpm_diff(), fake)
        assert [a.tool for a in signals.artifacts] == ["dependencies"]


def test_a_scanner_that_does_not_answer_reads_not_run_for_vulnerabilities_alone() -> None:
    fake = FakePackageLookup(
        {("npm", "left-pad"): meta()}, vulnerabilities=LookupUnavailable("osv-scanner: timed out")
    )
    signals = lookup(pnpm_diff(), fake)
    assert signals.words == {"code.deps_known_vulns": "not run — osv-scanner: timed out"}
    assert figure(signals, "code.deps_recent") == 1
    assert signals.osv_version is None
    assert signals.vulnerability_db_date is None
    assert signals.lookup_date == NOW.date()
    detail = json.loads(artifact(signals, "dependencies").body)
    assert [row["vulnerable"] for row in detail if row["change"] == "added"] == [None]


def test_vulnerabilities_of_manifest_dependencies_read_no_lock_file() -> None:
    files = {
        ("b", "package.json"): fixture("package.base.json"),
        ("h", "package.json"): fixture("package.head.json"),
    }
    diff = diff_dependencies([NameStatus("M", "package.json", None)], reader(files), "b", "h")
    fake = FakePackageLookup()
    signals = lookup(diff, fake)
    assert signals.words == {"code.deps_known_vulns": "not run — no lock file"}
    assert [c["method"] for c in fake.calls] == ["metadata", "metadata"]
    assert figure(signals, "code.deps_recent") == 0


def test_no_dependency_file_changed_is_zeros_and_no_lookup() -> None:
    fake = FakePackageLookup()
    signals = lookup(DependencyDiff(), fake)
    assert fake.calls == []
    assert signals.words == {}
    assert signals.artifacts == ()
    assert signals.lookup_date is None
    assert {(c.metric_id, c.source): c.value for c in signals.counts} == {
        ("code.deps_changed", "added"): 0,
        ("code.deps_changed", "removed"): 0,
        ("code.deps_changed", "upgraded"): 0,
        ("code.deps_not_in_registry", None): 0,
        ("code.deps_recent", None): 0,
        ("code.deps_licences", None): 0,
        ("code.deps_known_vulns", None): 0,
    }


def test_removed_dependencies_alone_are_detailed_but_not_looked_up() -> None:
    files = {("b", "uv.lock"): fixture("uv.base.lock")}
    diff = diff_dependencies([NameStatus("D", "uv.lock", None)], reader(files), "b", "h")
    fake = FakePackageLookup()
    signals = lookup(diff, fake)
    assert fake.calls == []
    detail = json.loads(artifact(signals, "dependencies").body)
    assert {row["change"] for row in detail} == {"removed"}


def test_an_unreadable_lock_file_makes_every_dependency_signal_a_word() -> None:
    files = {("h", "package-lock.json"): "{broken"}
    diff = diff_dependencies([NameStatus("M", "package-lock.json", None)], reader(files), "b", "h")
    fake = FakePackageLookup()
    signals = lookup(diff, fake)
    assert fake.calls == []
    assert signals.counts == ()
    assert set(signals.words) == {
        "code.deps_changed",
        "code.deps_not_in_registry",
        "code.deps_known_vulns",
        "code.deps_recent",
        "code.deps_licences",
    }
    assert set(signals.words.values()) == {"not run — package-lock.json: not parseable"}


def test_a_manifest_folder_beside_a_lock_file_folder_reads_no_lock_file_not_a_figure() -> None:
    """Epic 5 story 3 review, 2026-11-13: the manifest's added dependencies are never scanned,
    so a figure from the other folder's lock file would count them as clean."""
    files = {
        ("b", "app/pnpm-lock.yaml"): fixture("pnpm-lock.base.yaml"),
        ("h", "app/pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
        ("b", "svc/package.json"): fixture("package.base.json"),
        ("h", "svc/package.json"): fixture("package.head.json"),
    }
    changed = [
        NameStatus("M", "app/pnpm-lock.yaml", None),
        NameStatus("M", "svc/package.json", None),
    ]
    diff = diff_dependencies(changed, reader(files), "b", "h")
    assert diff.lock_paths == ("app/pnpm-lock.yaml",)
    assert diff.manifest_only is True
    fake = FakePackageLookup()
    signals = lookup(diff, fake)
    assert signals.words["code.deps_known_vulns"] == "not run — no lock file"
    assert [c for c in signals.counts if c.metric_id == "code.deps_known_vulns"] == []
    assert [c for c in fake.calls if c["method"] == "vulnerabilities"] == []
    assert figure(signals, "code.deps_changed", "added") == 3


def test_a_manifest_that_adds_nothing_beside_a_lock_file_keeps_the_scan() -> None:
    files = {
        ("b", "app/pnpm-lock.yaml"): fixture("pnpm-lock.base.yaml"),
        ("h", "app/pnpm-lock.yaml"): fixture("pnpm-lock.head.yaml"),
        ("b", "svc/package.json"): fixture("package.head.json"),
        ("h", "svc/package.json"): fixture("package.head.json").replace("\n", "\n\n", 1),
    }
    changed = [
        NameStatus("M", "app/pnpm-lock.yaml", None),
        NameStatus("M", "svc/package.json", None),
    ]
    diff = diff_dependencies(changed, reader(files), "b", "h")
    assert diff.manifest_only is False
    signals = lookup(diff, FakePackageLookup())
    assert figure(signals, "code.deps_known_vulns") == 0


def test_count_is_a_tier1a_count_rated_by_production_lines() -> None:
    signals = lookup(pnpm_diff(), FakePackageLookup(), lookups=False)
    assert signals.counts[0] == Count("code.deps_changed", "added", 1, "production")
