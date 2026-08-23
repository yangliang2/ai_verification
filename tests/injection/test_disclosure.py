"""M0.3 tests for audit-side blind-packet disclosure eligibility."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from aiverify.injection import (
    CataloguedDisclosureReview,
    DisclosurePolicy,
    DisclosureReview,
    InjectionReceipt,
    MaterializedWorktree,
    STALE_RESULT_DISCLOSURE_POLICY,
    admit_catalogued_candidate,
    load_curated_source_catalog,
    review_catalogued_admission,
    review_visible_packet_material,
)
from aiverify.injection.models import result_identity_sha256


def test_disclosure_policy_rejects_declared_tokens_in_every_visible_surface() -> None:
    policy = DisclosurePolicy(
        policy_id="stale-result-v1",
        forbidden_tokens=("APPLY_STALE", "injected_defect", "expected_oracle"),
    )
    visible_material = {
        "source": 'event("APPLY_STALE")',
        "metadata": {
            "metric_context": {
                "seed_kind": "injected_defect",
                "expected_oracle_level": "L2",
            }
        },
        "paths": {
            "patch": "patches/apply-stale-result.patch",
        },
        "derived_identifiers": {
            "source_id": "curated-apply-stale-result-v1",
        },
        "error": "expected-oracle material cannot be verifier-visible",
    }

    review = review_visible_packet_material(policy, visible_material)
    repeated = review_visible_packet_material(policy, visible_material)

    assert review.status == "rejected"
    assert review.rejection_code == "declared_disclosure_detected"
    assert review.claim_boundary == "m0_structural_blind_packet_eligibility_only"
    assert {finding.forbidden_token for finding in review.findings} == {
        "APPLY_STALE",
        "injected_defect",
        "expected_oracle",
    }
    assert any(finding.visible_path == "/source" for finding in review.findings)
    assert any("expected_oracle_level" in finding.visible_path for finding in review.findings)
    assert any(finding.visible_path == "/paths/patch" for finding in review.findings)
    assert any(
        finding.visible_path == "/derived_identifiers/source_id"
        for finding in review.findings
    )
    assert any(finding.visible_path == "/error" for finding in review.findings)
    assert repeated == review


def test_disclosure_policy_marks_clean_nested_material_eligible() -> None:
    policy = DisclosurePolicy(
        policy_id="high-entropy-v1",
        forbidden_tokens=("HIDDEN_RESULT_4f7e2a", "AUDIT_ONLY_09bcde"),
    )
    review = review_visible_packet_material(
        policy,
        {
            "source": {"path": "src/feature.java", "content": "return result;"},
            "metadata": {"scope": ["feature"]},
            "derived_identifiers": {"packet": "packet-a1b2c3"},
        },
    )

    assert review.status == "eligible"
    assert review.rejection_code is None
    assert review.findings == ()
    assert DisclosurePolicy.from_dict(policy.to_dict()) == policy
    assert DisclosureReview.from_dict(review.to_dict()) == review


class _ReceiptMaterializer:
    """Deterministic M0.1 receipt seam; materialization itself is covered in #185."""

    def __init__(self, candidate, worktree_root: Path) -> None:
        result_source_tree_sha256 = sha256(b"stale-result-review-tree").hexdigest()
        result_diff_sha256 = sha256(b"stale-result-review-diff").hexdigest()
        result_identity = result_identity_sha256(
            baseline_identity_sha256=candidate.baseline.identity_sha256,
            patch_identity_sha256=candidate.source_delta.identity_sha256,
            result_source_tree_sha256=result_source_tree_sha256,
            result_diff_sha256=result_diff_sha256,
        )
        self._candidate = candidate
        self._receipt = InjectionReceipt(
            outcome="materialized",
            candidate_identity_sha256=candidate.identity_sha256,
            baseline_identity_sha256=candidate.baseline.identity_sha256,
            patch_identity_sha256=candidate.source_delta.identity_sha256,
            result_source_tree_sha256=result_source_tree_sha256,
            result_diff_sha256=result_diff_sha256,
            result_identity_sha256=result_identity,
            worktree=MaterializedWorktree(
                path=str((worktree_root / "owned-worktree").resolve()),
                ownership_token="1" * 32,
                candidate_identity_sha256=candidate.identity_sha256,
                baseline_commit=candidate.baseline.commit,
                result_identity_sha256=result_identity,
            ),
        )

    def materialize(self, candidate):
        assert candidate == self._candidate
        return self._receipt


def test_stale_result_is_retained_as_audit_evidence_but_rejected_for_blind_packet(
    tmp_path: Path,
) -> None:
    catalog_path = Path("bench/curated-source-catalog-v1.json")
    source_id = "curated-deterministic-concurrency-apply-stale-result-v1"
    catalog = load_curated_source_catalog(catalog_path)
    entry = catalog.select(source_id)
    patch_path = Path(
        "bench/capability-slices/deterministic-concurrency/patches/apply-stale-result.patch"
    )
    run_spec_path = Path(
        "bench/capability-slices/deterministic-concurrency/run-specs/stale-candidate.yaml"
    )
    before = {path: path.read_bytes() for path in (patch_path, run_spec_path)}
    admission = admit_catalogued_candidate(
        catalog_path,
        source_id,
        _ReceiptMaterializer(entry.candidate, tmp_path),
    )
    review = review_catalogued_admission(
        catalog_path,
        source_id,
        admission,
        STALE_RESULT_DISCLOSURE_POLICY,
    )

    assert admission.status == "sealed"
    assert admission.package is not None
    assert review.status == "rejected"
    assert review.rejection_code == "declared_disclosure_detected"
    assert review.claim_boundary == "m0_structural_blind_packet_eligibility_only"
    assert review.catalog_identity_sha256 == catalog.identity_sha256
    assert review.catalog_source_sha256 == catalog.catalog_source_sha256
    assert review.catalog_entry_identity_sha256 == entry.identity_sha256
    assert review.admission_identity_sha256 == admission.identity_sha256
    assert review.audit_package_identity_sha256 == admission.package.identity_sha256
    assert review.review.policy_identity_sha256 == STALE_RESULT_DISCLOSURE_POLICY.identity_sha256
    assert {finding.forbidden_token for finding in review.findings} == {
        "APPLY_STALE",
        "injected_defect",
        "expected_oracle",
    }
    assert any(
        finding.visible_path == "/source/patch_text" for finding in review.findings
    )
    assert any(
        finding.forbidden_token == "expected_oracle"
        and finding.visible_path == "/audit_artifacts/0/text"
        for finding in review.findings
    )
    assert any(
        finding.visible_path == "/paths/patch_path" for finding in review.findings
    )
    assert any(
        finding.visible_path == "/derived_identifiers/source_id"
        for finding in review.findings
    )
    assert CataloguedDisclosureReview.from_dict(review.to_dict()) == review
    assert {path: path.read_bytes() for path in before} == before
