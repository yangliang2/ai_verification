"""M0.2 contract tests for catalogued non-formal Injection Lab admission."""

from __future__ import annotations

from dataclasses import replace
import difflib
from hashlib import sha256
import json
from pathlib import Path
import subprocess

import pytest

from aiverify.injection import (
    CuratedCatalogError,
    CuratedSourceCatalog,
    CuratedSourceEntry,
    FaultOperator,
    FixtureAnchor,
    InjectionAdmission,
    InjectionCandidate,
    InjectionMaterializer,
    SourceDelta,
    TaxonomyRelationship,
    admit_catalogued_candidate,
    capture_baseline_provenance,
    load_curated_source_catalog,
)


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _repository(tmp_path: Path) -> Path:
    repository = tmp_path / "caller"
    repository.mkdir()
    _git(repository, "init", "-b", "main")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Injection Lab Test")
    _git(repository, "remote", "add", "origin", "https://example.invalid/catalog.git")
    (repository / "source.txt").write_text("baseline\n", encoding="utf-8")
    _git(repository, "add", "source.txt")
    _git(repository, "commit", "-m", "baseline")
    return repository


def _catalog(repository: Path) -> CuratedSourceCatalog:
    baseline = capture_baseline_provenance(repository, _git(repository, "rev-parse", "HEAD"))
    patch_text = "".join(
        difflib.unified_diff(
            ["baseline\n"],
            ["candidate\n"],
            fromfile="a/source.txt",
            tofile="b/source.txt",
        )
    )
    candidate = InjectionCandidate(
        candidate_id="catalogued-candidate",
        baseline=baseline,
        source_delta=SourceDelta.from_patch(
            delta_id="catalogued-delta",
            patch_text=patch_text,
            source_ref="patches/catalogued.patch",
        ),
        operator=FaultOperator(
            operator_id="curated-unified-diff",
            version="v1",
            applicability="declared fixture source only",
            safety_boundary="one detached disposable worktree",
        ),
    )
    return CuratedSourceCatalog(
        entries=(
            CuratedSourceEntry(
                source_id="catalogued-source",
                candidate=candidate,
                patch_path="patches/catalogued.patch",
                fixture_anchor=FixtureAnchor(
                    path="source.txt",
                    sha256=sha256((repository / "source.txt").read_bytes()).hexdigest(),
                ),
                population_classification="curated_controlled_injection",
                taxonomy_relationship=TaxonomyRelationship.known("concurrency"),
            ),
        )
    )


def test_catalogued_source_admits_to_a_structurally_sealed_non_formal_package(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    admission = admit_catalogued_candidate(
        _catalog(repository),
        "catalogued-source",
        materializer,
    )

    assert admission.status == "sealed"
    assert admission.rejection_code is None
    assert admission.ledger.states == (
        "draft",
        "materialized",
        "source-identity-verified",
        "policy-accepted",
        "evidence-bound",
        "sealed",
    )
    assert admission.package is not None
    assert admission.package.formal_status == "non_formal"
    assert admission.package.cohort_membership == "not_a_cohort_member"
    assert admission.package.claim_boundary == "m0_structural_audit_only"
    assert admission.package.not_claimed_evidence == {
        "build": "not_claimed",
        "installation": "not_claimed",
        "runtime": "not_claimed",
        "oracle": "not_claimed",
        "flakiness": "not_claimed",
        "equivalence": "not_claimed",
    }
    assert admission.receipt is not None

    materializer.cleanup(admission.receipt)


def test_checked_in_catalog_binds_declared_patch_and_fixture_bytes(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    catalog = _catalog(repository)
    catalog_path = _write_checked_in_catalog(repository, catalog)

    loaded = load_curated_source_catalog(catalog_path)

    assert loaded.to_dict() == catalog.to_dict()
    assert loaded.identity_sha256 == catalog.identity_sha256


def _write_checked_in_catalog(repository: Path, catalog: CuratedSourceCatalog) -> Path:
    entry = catalog.select("catalogued-source")
    patch = repository / entry.patch_path
    patch.parent.mkdir()
    patch.write_text(entry.candidate.source_delta.patch_text, encoding="utf-8")
    catalog_path = repository / "curated-source-catalog.json"
    catalog_path.write_text(
        json.dumps(catalog.to_dict(), sort_keys=True),
        encoding="utf-8",
    )
    return catalog_path


def test_catalog_patch_drift_is_a_stable_fail_closed_rejection(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    catalog = _catalog(repository)
    catalog_path = _write_checked_in_catalog(repository, catalog)
    (repository / "patches/catalogued.patch").write_text("drift\n", encoding="utf-8")

    with pytest.raises(CuratedCatalogError) as raised:
        load_curated_source_catalog(catalog_path)

    assert raised.value.code == "catalog_patch_drift"


def test_catalog_fixture_anchor_drift_is_a_stable_fail_closed_rejection(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    catalog_path = _write_checked_in_catalog(repository, _catalog(repository))
    (repository / "source.txt").write_text("fixture drift\n", encoding="utf-8")

    with pytest.raises(CuratedCatalogError) as raised:
        load_curated_source_catalog(catalog_path)

    assert raised.value.code == "catalog_fixture_anchor_drift"


def test_catalog_rejects_duplicate_sources_and_invalid_provenance(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    catalog = _catalog(repository)
    catalog_path = _write_checked_in_catalog(repository, catalog)
    document = catalog.to_dict()
    document["entries"].append(document["entries"][0])
    catalog_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CuratedCatalogError) as duplicate:
        load_curated_source_catalog(catalog_path)

    assert duplicate.value.code == "catalog_duplicate_source_id"

    document = catalog.to_dict()
    document["entries"][0]["candidate"]["baseline"]["source_origin"] = ""
    catalog_path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(CuratedCatalogError) as invalid_provenance:
        load_curated_source_catalog(catalog_path)

    assert invalid_provenance.value.code == "catalog_invalid_provenance"


def test_checked_in_stale_result_source_has_a_byte_bound_catalog_entry() -> None:
    catalog = load_curated_source_catalog("bench/curated-source-catalog-v1.json")

    entry = catalog.select("curated-deterministic-concurrency-apply-stale-result-v1")

    assert entry.population_classification == "curated_controlled_injection"
    assert entry.taxonomy_relationship == TaxonomyRelationship.known(
        "coroutine-concurrency-05"
    )
    assert entry.candidate.source_delta.patch_sha256 == (
        "1076db34c0aa8e445fce21ce833d3d44db7734afe558784ec7022049b7cb5975"
    )


def test_missing_catalog_selection_has_a_terminal_inspectable_rejection(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    admission = admit_catalogued_candidate(
        _catalog(repository),
        "not-declared",
        materializer,
    )

    assert admission.status == "rejected"
    assert admission.rejection_code == "catalog_source_missing"
    assert admission.ledger.states == ("draft", "rejected")
    assert admission.receipt is None


def test_catalog_admission_preserves_a_dirty_caller_checkout(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    (repository / "source.txt").write_text("staged caller\n", encoding="utf-8")
    _git(repository, "add", "source.txt")
    (repository / "source.txt").write_text("unstaged caller\n", encoding="utf-8")
    (repository / "caller-untracked.txt").write_text("keep\n", encoding="utf-8")
    before = {
        "head": _git(repository, "rev-parse", "HEAD"),
        "status": _git(repository, "status", "--porcelain=v1"),
        "source": (repository / "source.txt").read_bytes(),
        "untracked": (repository / "caller-untracked.txt").read_bytes(),
    }
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    admission = admit_catalogued_candidate(
        _catalog(repository),
        "catalogued-source",
        materializer,
    )

    assert admission.status == "sealed"
    assert {
        "head": _git(repository, "rev-parse", "HEAD"),
        "status": _git(repository, "status", "--porcelain=v1"),
        "source": (repository / "source.txt").read_bytes(),
        "untracked": (repository / "caller-untracked.txt").read_bytes(),
    } == before
    assert admission.receipt is not None
    materializer.cleanup(admission.receipt)
    assert {
        "head": _git(repository, "rev-parse", "HEAD"),
        "status": _git(repository, "status", "--porcelain=v1"),
        "source": (repository / "source.txt").read_bytes(),
        "untracked": (repository / "caller-untracked.txt").read_bytes(),
    } == before


def test_sealed_admission_has_a_hash_chained_immutable_ledger(tmp_path: Path) -> None:
    repository = _repository(tmp_path)
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")
    admission = admit_catalogued_candidate(
        _catalog(repository),
        "catalogued-source",
        materializer,
    )

    assert admission.ledger.identity_sha256
    assert admission.ledger.entries[0].previous_entry_sha256 is None
    assert admission.ledger.entries[-1].state == "sealed"
    assert (
        admission.ledger.entries[-1].previous_entry_sha256
        == admission.ledger.entries[-2].identity_sha256
    )
    assert InjectionAdmission.from_dict(admission.to_dict()) == admission

    assert admission.receipt is not None
    materializer.cleanup(admission.receipt)


def test_admission_rejects_a_materialized_receipt_for_another_candidate(
    tmp_path: Path,
) -> None:
    repository = _repository(tmp_path)
    catalog = _catalog(repository)
    entry = catalog.select("catalogued-source")
    contradictory_patch = "".join(
        difflib.unified_diff(
            ["baseline\n"],
            ["different candidate\n"],
            fromfile="a/source.txt",
            tofile="b/source.txt",
        )
    )
    contradictory_candidate = replace(
        entry.candidate,
        candidate_id="contradictory-candidate",
        source_delta=SourceDelta.from_patch(
            delta_id="contradictory-delta",
            patch_text=contradictory_patch,
            source_ref="patches/contradictory.patch",
        ),
    )
    materializer = InjectionMaterializer(repository, tmp_path / "owned-worktrees")

    class ContradictoryReceiptMaterializer:
        def materialize(self, candidate: InjectionCandidate):
            return materializer.materialize(contradictory_candidate)

    admission = admit_catalogued_candidate(
        catalog,
        "catalogued-source",
        ContradictoryReceiptMaterializer(),
    )

    assert admission.status == "rejected"
    assert admission.rejection_code == "receipt_identity_mismatch"
    assert admission.ledger.states == ("draft", "materialized", "rejected")
    assert admission.package is None
    assert admission.receipt is not None
    materializer.cleanup(admission.receipt)
