from __future__ import annotations

import ast
from dataclasses import replace

import pytest

from aiverify.discovery.contracts import AttackPlan, Finding, RiskHypothesis
from aiverify.discovery.falsification_review import (
    FALSIFICATION_REVIEW_ROLE_ID,
    REVIEW_DIMENSIONS,
    FalsificationReconciliation,
    FalsificationReviewContext,
    FalsificationReviewResult,
    FalsificationReviewerIdentity,
    ImmutableArtifactRef,
    reconcile_finding,
    run_falsification_review,
)
from aiverify.discovery.models import ProjectTarget


SHA = "c" * 64


def _ref(ref: str, kind: str) -> ImmutableArtifactRef:
    return ImmutableArtifactRef(ref=ref, kind=kind, sha256=SHA)


def _context() -> FalsificationReviewContext:
    target = ProjectTarget(
        target_id="project-review",
        source_origin="https://example.invalid/review.git",
        source_commit="2" * 40,
        worktree="/tmp/m9-review",
        scope=("src",),
        discovery_budget=8,
    )
    hypothesis = RiskHypothesis(
        hypothesis_id="hypothesis-review",
        target_id=target.target_id,
        quality_property="bounded state continuity",
        assumptions=("the caller remains live",),
        trigger="caller invokes the operation",
        mechanism="state update crosses the ownership boundary",
        consequence="state remains observable",
        rationale="source-grounded causal explanation",
        required_evidence=("state bytes",),
        confidence=0.7,
        status="frozen",
        supporting_fact_ids=("fact-review",),
    )
    plan = AttackPlan(
        plan_id="plan-review",
        target_id=target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        operator_id="operator-review",
        trigger="invoke the operation",
        observations=("record state bytes",),
        evidence_expectations=("state bytes",),
        oracle="oracle-state-bytes",
        abort_boundary="abort on unsafe access",
        claim_boundary="local exact source claim",
        fixture_refs=("fixture:review",),
        status="admitted",
    )
    finding = Finding(
        finding_id="finding-review",
        target_id=target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        conclusion="supported",
        evidence_refs=("raw:1",),
        impact="one local state path",
        claim_boundary="local exact source and package only",
        rationale="immutable raw evidence supports the candidate claim",
    )
    return FalsificationReviewContext(
        context_id="context-review",
        target=target,
        source_refs=(_ref("source:1", "source"),),
        validated_fact_ids=("fact-review",),
        hypothesis=hypothesis,
        admitted_attack_plan=plan,
        oracle_contract=_ref("oracle:1", "oracle-contract"),
        candidate_finding=finding,
        execution_record=_ref("execution:1", "execution-record"),
        effective_identity=_ref("identity:1", "effective-identity"),
        raw_evidence=(_ref("raw:1", "raw-evidence"),),
        control_evidence=(_ref("control:1", "control-evidence"),),
        claim_boundary="local exact source and package only",
        production_invocation_id="production-invocation-1",
        production_provider_family="family-a",
    )


def _identity(invocation: str = "review-invocation-1") -> FalsificationReviewerIdentity:
    return FalsificationReviewerIdentity.capture(
        backend="fake-falsifier",
        requested_model="fixture-model-v1",
        effective_model="fixture-model-v1",
        invocation_id=invocation,
        provider_family="family-a",
        same_family_limitation="same provider family; this review supports path separation only",
    )


def _output(status: str = "supported", *, outcome: str | None = None) -> dict:
    dimensions = [
        {
            "schema_version": 1,
            "dimension": dimension,
            "status": status,
            "analysis": f"assessment for {dimension}",
            "evidence_refs": ["raw:1"],
            "reason_codes": [] if status == "supported" else [f"reason-{dimension}"],
        }
        for dimension in REVIEW_DIMENSIONS
    ]
    derived = "challenged" if status == "challenged" else "inconclusive" if status == "inconclusive" else "survived"
    reasons = [] if status == "supported" else [
        {
            "schema_version": 1,
            "code": "evidence_gap",
            "message": "the challenge has an explicit evidence gap",
            "evidence_refs": ["raw:1"],
        }
    ]
    return {
        "schema_version": 1,
        "review_id": "review-1",
        "outcome": outcome or derived,
        "dimensions": dimensions,
        "reasons": reasons,
    }


def test_survived_review_captures_clean_context_and_all_dimensions():
    context = _context()
    calls = []

    def backend(value):
        calls.append(value)
        assert set(value.to_dict()) == {
            "schema_version", "context_id", "target", "source_refs", "validated_fact_ids",
            "hypothesis", "admitted_attack_plan", "oracle_contract", "candidate_finding",
            "execution_record", "effective_identity", "raw_evidence", "control_evidence",
            "claim_boundary", "production_invocation_id", "production_provider_family",
        }
        assert value.context_sha256 == context.context_sha256
        return _output()

    result = run_falsification_review(context, backend, _identity())
    assert len(calls) == 1
    assert result.status == "complete"
    assert result.review is not None
    assert result.review.outcome == "survived"
    assert tuple(item.dimension for item in result.review.dimensions) == REVIEW_DIMENSIONS
    assert result.review.reviewer_identity.role == FALSIFICATION_REVIEW_ROLE_ID
    assert FalsificationReviewResult.from_dict(result.to_dict()) == result
    reconciliation = reconcile_finding(context.candidate_finding, result.review, context)
    assert FalsificationReconciliation.from_dict(reconciliation.to_dict()) == reconciliation


@pytest.mark.parametrize(
    ("dimension_status", "expected_outcome"),
    [("challenged", "challenged"), ("inconclusive", "inconclusive")],
)
def test_challenged_and_inconclusive_reviews_block_aggregate(
    dimension_status: str, expected_outcome: str
):
    context = _context()
    raw = _output()
    raw["dimensions"][2]["status"] = dimension_status
    raw["dimensions"][2]["reason_codes"] = ["evidence_gap"]
    raw["outcome"] = expected_outcome
    raw["reasons"] = [
        {
            "schema_version": 1,
            "code": "evidence_gap",
            "message": "one challenge dimension is not resolved",
            "evidence_refs": ["raw:1"],
        }
    ]
    result = run_falsification_review(context, lambda _context: raw, _identity("review-" + dimension_status))
    assert result.status == "complete"
    assert result.review is not None
    reconciliation = reconcile_finding(context.candidate_finding, result.review, context)
    assert reconciliation.finding == context.candidate_finding
    assert reconciliation.aggregate_supported is False
    assert reconciliation.raw_evidence_refs == context.raw_evidence


def test_incomplete_or_contradictory_output_is_rejected_and_identity_is_separate():
    context = _context()
    result = run_falsification_review(
        context,
        lambda _context: {"schema_version": 1, "dimensions": []},
        _identity(),
    )
    assert result.status == "rejected"
    assert result.rejection_reasons

    same_identity = _identity(context.production_invocation_id)
    rejected = run_falsification_review(context, lambda _context: _output(), same_identity)
    assert rejected.status == "rejected"
    assert "separate" in " ".join(rejected.rejection_reasons)


def test_tampering_finding_or_raw_evidence_is_rejected():
    context = _context()
    identity = _identity()
    raw = _output()
    result = run_falsification_review(context, lambda _context: raw, identity)
    assert result.status == "complete"
    assert result.review is not None
    tampered_dimension = replace(result.review.dimensions[0], evidence_refs=("not-in-context",))
    tampered = replace(
        result.review,
        dimensions=(tampered_dimension, *result.review.dimensions[1:]),
    )
    with pytest.raises(ValueError, match="cannot reconcile"):
        reconcile_finding(context.candidate_finding, tampered, context)


def test_forbidden_material_in_any_allowlisted_context_field_is_rejected():
    context = _context()
    tainted_hypothesis = replace(
        context.hypothesis,
        rationale="source rationale accidentally includes a hidden mapping",
    )
    with pytest.raises(ValueError, match="forbidden material"):
        replace(context, hypothesis=tainted_hypothesis)


def test_module_has_no_import_path_to_production_oracle():
    from pathlib import Path

    source = Path("src/aiverify/discovery/falsification_review.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            forbidden.extend(alias.name for alias in node.names if "oracle" in alias.name or "adjud" in alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if "oracle" in node.module or "adjud" in node.module:
                forbidden.append(node.module)
    assert forbidden == []
