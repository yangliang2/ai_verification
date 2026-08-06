from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aiverify.discovery.attack_planning import (
    AttackPlanGenerationResult,
    AttackPlanGenerationRequest,
    AttackPlanProposal,
)
from aiverify.discovery.schema import self_validate_schema, validate_contract


ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    receipt = json.loads((ROOT / "bounded-synthesis-receipt.json").read_text())
    request = AttackPlanGenerationRequest.from_dict(receipt["request"])
    proposal = AttackPlanProposal.from_dict(receipt["proposal"])
    result = AttackPlanGenerationResult.from_dict(receipt["result"])
    assert proposal.target_id == request.target.target_id
    assert result.admission.admitted
    assert result.authoritative_output_sha256 == receipt["authoritative_output_sha256"]
    assert result.planner_identity.invocation_id == "planner-invocation-1"
    assert receipt["formal_holdout_executed"] is False
    assert receipt["side_effects"] == {
        "build": False,
        "device": False,
        "external": False,
        "runtime": False,
    }
    assert "expected_behavior" not in receipt["compiled_scenario"]
    assert receipt["compiled_scenario"]["user_actions"]
    self_validate_schema()
    validate_contract(request.to_dict(), "attack_plan_generation_request")
    validate_contract(proposal.to_dict(), "attack_plan_proposal")
    validate_contract(result.to_dict(), "attack_plan_generation_result")
    artifacts = sorted((ROOT / "artifacts").iterdir())
    packages = [path for path in artifacts if path.suffix in {".whl", ".gz"}]
    assert len(packages) == 2
    manifest = {}
    for line in (ROOT / "checksums.sha256").read_text().splitlines():
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
        "source_contract_checks": 3,
        "run_record_checks": 8,
        "package_artifact_checks": 2,
        "checksum_manifest_checks": len(manifest),
        "formal_holdout_executed": False,
        "side_effects": False,
    }, indent=2))


if __name__ == "__main__":
    main()
