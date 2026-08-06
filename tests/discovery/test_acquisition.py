from __future__ import annotations

import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.discovery import (
    ContextAcquisitionRequest,
    ContextAcquisitionResult,
    DiscoveryContractError,
    ProjectTarget,
    acquire_project_context,
    acquire_context,
    validate_contract,
)


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def _held_out_project(tmp_path: Path) -> ProjectTarget:
    repo = tmp_path / "held-out-project"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture Author")
    _git(repo, "remote", "add", "origin", "https://example.invalid/held-out-project.git")
    (repo / "app/src/main").mkdir(parents=True)
    (repo / "docs").mkdir()
    (repo / "app/src/main/AndroidManifest.xml").write_text(
        """<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="com.example.heldout">
  <application android:name=".App">
    <activity android:name=".MainActivity" android:exported="true" />
  </application>
</manifest>
""",
        encoding="utf-8",
    )
    (repo / "app/src/main/MainActivity.kt").write_text(
        """class MainActivity {
  fun refresh() { viewModelScope.launch { repository.load() } }
  fun onDestroy() { repository.close() }
}
""",
        encoding="utf-8",
    )
    (repo / "app/src/main/Repository.kt").write_text(
        """class Repository {
  fun load() = dao.query()
  fun save() = dao.insert()
  fun migrate() = Migration(1, 2)
  fun restore() = fallback()
}
""",
        encoding="utf-8",
    )
    (repo / "app/build.gradle.kts").write_text(
        """plugins { id("com.android.application") }
android { namespace = "com.example.heldout"; compileSdk = 35
  defaultConfig { applicationId = "com.example.heldout"; versionName = "1.2" }
}
""",
        encoding="utf-8",
    )
    (repo / "docs/quality.md").write_text(
        "# Quality contract\nThe lifecycle path has a bounded latency budget.\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("held-out source fixture\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fixture")
    head = _git(repo, "rev-parse", "HEAD")
    return ProjectTarget(
        target_id="project-held-out",
        source_origin="https://example.invalid/held-out-project",
        source_commit=head,
        worktree=str(repo),
        scope=("app", "docs", "README.md"),
        discovery_budget=32,
    )


def test_acquisition_builds_graph_from_raw_source_without_context_manifest(tmp_path: Path) -> None:
    target = _held_out_project(tmp_path)

    first = acquire_project_context(target, suggestions=("inspect ownership manually",))
    second = acquire_project_context(target, suggestions=("inspect ownership manually",))

    assert isinstance(first, ContextAcquisitionResult)
    assert first == second
    assert first.graph.target_id == target.target_id
    assert first.graph.source_commit == target.source_commit
    assert first.graph.source_tree_sha256
    assert first.receipt.no_diff is True
    assert first.receipt.budget_used <= target.discovery_budget
    assert "inspect ownership manually" in first.suggested_probes
    assert any(fact.predicate == "manifest_package" and fact.status == "known" for fact in first.graph.facts)
    assert any(fact.predicate == "call_site" and fact.status == "known" for fact in first.graph.facts)
    assert any(fact.predicate == "persistence_writer" and fact.status == "known" for fact in first.graph.facts)
    assert any(fact.predicate == "lifecycle_boundary" and fact.status == "known" for fact in first.graph.facts)
    assert first.graph.nodes
    assert first.graph.edges
    assert {adapter.adapter_id for adapter in first.receipt.adapters} == {
        "manifest",
        "build",
        "symbols_calls",
        "persistence_state",
        "lifecycle_ownership",
        "quality_version",
    }
    for fact in first.graph.facts:
        if fact.status == "known":
            assert fact.provenance
            assert fact.provenance[0].source_sha256
    validate_contract(first.graph.to_dict(), "context_graph")
    validate_contract(first.to_dict(), "context_acquisition_result")
    assert ContextAcquisitionResult.from_dict(first.to_dict()) == first


def test_request_contract_round_trips_and_drives_alias(tmp_path: Path) -> None:
    target = _held_out_project(tmp_path)
    request = ContextAcquisitionRequest(
        target=target,
        requested_evidence=("manifest", "build"),
        suggestions=("inspect the source boundary",),
    )

    restored = ContextAcquisitionRequest.from_dict(request.to_dict())
    result = acquire_context(restored)

    assert restored == request
    assert [adapter.adapter_id for adapter in result.receipt.adapters] == ["manifest", "build"]
    validate_contract(request.to_dict(), "context_acquisition_request")


def test_raw_fixture_does_not_carry_outcome_oracle_or_hidden_mapping(tmp_path: Path) -> None:
    target = _held_out_project(tmp_path)
    result = acquire_project_context(target)
    serialized = str(result.to_dict()).lower()

    assert "expected_verdict" not in serialized
    assert "hidden_mapping" not in serialized
    assert "defect" not in serialized
    assert "control" not in serialized
    assert all(
        fact.status != "known" or fact.provenance
        for fact in result.graph.facts
    )


def test_budget_exhaustion_is_explicit_and_deterministic(tmp_path: Path) -> None:
    target = replace(_held_out_project(tmp_path), discovery_budget=1)

    result = acquire_project_context(target)

    assert result.receipt.budget_used == 1
    assert result.receipt.skipped_scope
    assert any("budget exhausted" in item for item in result.unresolved)
    assert any(item.status == "budget-exhausted" for item in result.receipt.adapters)


def test_identity_and_dirty_worktree_fail_before_source_acquisition(tmp_path: Path) -> None:
    target = _held_out_project(tmp_path)
    with pytest.raises(DiscoveryContractError, match="source commit mismatch"):
        acquire_project_context(replace(target, source_commit="0" * 40))

    Path(target.worktree, "app/src/main/extra.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(DiscoveryContractError, match="worktree is not clean"):
        acquire_project_context(target)


def test_contradictory_and_stale_source_evidence_remains_non_known(tmp_path: Path) -> None:
    target = _held_out_project(tmp_path)
    repo = Path(target.worktree)
    (repo / "app/build.gradle").write_text(
        'android { defaultConfig { applicationId "com.example.other" } }\n',
        encoding="utf-8",
    )
    (repo / "docs/revision.md").write_text(
        f"source_commit: {'a' * 40}\n",
        encoding="utf-8",
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "contradictory source fixture")
    target = replace(target, source_commit=_git(repo, "rev-parse", "HEAD"))

    result = acquire_project_context(target)

    application_ids = [
        fact for fact in result.graph.facts if fact.predicate == "application_id"
    ]
    assert application_ids
    assert all(fact.status == "contradictory" for fact in application_ids)
    assert any(fact.status == "stale" for fact in result.graph.facts)
    assert any("contradictory evidence" in item for item in result.unresolved)
    assert any("stale source revision" in item for item in result.unresolved)
