from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aiverify.discovery.contracts import AttackPlan, Finding, RiskHypothesis
from aiverify.discovery.falsification_review import (
    FalsificationReviewContext,
    FalsificationReviewResult,
    FalsificationReviewerIdentity,
    ImmutableArtifactRef,
    reconcile_finding,
    run_falsification_review,
)
from aiverify.discovery.models import ProjectTarget
from aiverify.discovery.schema import self_validate_schema, validate_contract


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _context(data: dict) -> FalsificationReviewContext:
    return FalsificationReviewContext(
        context_id=data["context_id"],
        target=ProjectTarget.from_dict(data["target"]),
        source_refs=tuple(ImmutableArtifactRef.from_dict(item) for item in data["source_refs"]),
        validated_fact_ids=tuple(data["validated_fact_ids"]),
        hypothesis=RiskHypothesis.from_dict(data["hypothesis"]),
        admitted_attack_plan=AttackPlan.from_dict(data["admitted_attack_plan"]),
        oracle_contract=ImmutableArtifactRef.from_dict(data["oracle_contract"]),
        candidate_finding=Finding.from_dict(data["candidate_finding"]),
        execution_record=ImmutableArtifactRef.from_dict(data["execution_record"]),
        effective_identity=ImmutableArtifactRef.from_dict(data["effective_identity"]),
        raw_evidence=tuple(ImmutableArtifactRef.from_dict(item) for item in data["raw_evidence"]),
        control_evidence=tuple(
            ImmutableArtifactRef.from_dict(item) for item in data["control_evidence"]
        ),
        claim_boundary=data["claim_boundary"],
        production_invocation_id=data["production_invocation_id"],
        production_provider_family=data["production_provider_family"],
        schema_version=data.get("schema_version", 1),
    )


def main() -> None:
    receipt = json.loads((ROOT / "bounded-review-receipt.json").read_text(encoding="utf-8"))
    assert receipt["scope"] == "non-holdout-local-fixture"
    assert receipt["formal_holdout"] is False
    assert receipt["side_effects"] == {
        "agent": False,
        "build": False,
        "device": False,
        "production": False,
        "runtime": False,
    }

    context = _context(receipt["context"])
    identity = FalsificationReviewerIdentity.from_dict(receipt["identity"])
    assert context.context_sha256 == receipt["context_sha256"]
    assert identity.invocation_id == "review-invocation-1"
    assert identity.invocation_id != context.production_invocation_id
    assert identity.same_family_limitation

    raw_output = receipt["raw_output"]
    result = run_falsification_review(context, lambda _context: raw_output, identity)
    recorded_result = FalsificationReviewResult.from_dict(receipt["result"])
    assert result == recorded_result
    assert result.status == "complete"
    assert result.review is not None
    reconciliation = reconcile_finding(context.candidate_finding, result.review, context)
    assert reconciliation.to_dict() == receipt["reconciliation"]
    assert reconciliation.aggregate_supported is True
    assert reconciliation.finding == context.candidate_finding
    assert reconciliation.raw_evidence_refs == context.raw_evidence

    self_validate_schema()
    validate_contract(context.to_dict(), "falsification_review_context")
    validate_contract(result.to_dict(), "falsification_review_result")
    validate_contract(result.review.to_dict(), "falsification_review")
    validate_contract(reconciliation.to_dict(), "falsification_reconciliation")

    artifacts = sorted((ROOT / "artifacts").iterdir())
    packages = [path for path in artifacts if path.suffix in {".whl", ".gz"}]
    assert len(packages) == 2
    manifest = {}
    for line in (ROOT / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            digest, relative = line.split("  ", 1)
            manifest[relative] = digest
    assert manifest
    for relative, digest in manifest.items():
        candidate = ROOT / relative
        if not candidate.is_file():
            candidate = ROOT.parents[2] / relative
        assert sha256(candidate) == digest, relative
    print(json.dumps({
        "status": "passed",
        "source_contract_checks": 4,
        "run_record_checks": 12,
        "package_artifact_checks": 2,
        "checksum_manifest_checks": len(manifest),
        "formal_holdout_executed": False,
        "side_effects": False,
    }, indent=2))


if __name__ == "__main__":
    main()
