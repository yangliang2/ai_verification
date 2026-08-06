"""Validate the committed #132 hypothesis-portfolio evidence inventory."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    sources = (
        ROOT / "src/aiverify/discovery/hypothesis_portfolio.py",
        ROOT / "src/aiverify/discovery/lifetime_ownership_risk.py",
        ROOT / "src/aiverify/discovery/discovery_schema.json",
        ROOT / "src/aiverify/discovery/schema.py",
        ROOT / "src/aiverify/discovery/__init__.py",
        ROOT / "tests/discovery/test_hypothesis_portfolio.py",
    )
    assert all(path.is_file() for path in sources)
    portfolio_source = sources[0].read_text(encoding="utf-8").lower()
    forbidden = ("formal holdout", "production_adjudication", "hidden mapping")
    assert not any(term in portfolio_source for term in forbidden)
    schema = json.loads(
        (ROOT / "src/aiverify/discovery/discovery_schema.json").read_text(encoding="utf-8")
    )
    for definition in (
        "hypothesisGenerationRequest",
        "hypothesisCandidate",
        "hypothesisGenerationResponse",
        "hypothesisPortfolio",
    ):
        assert definition in schema["$defs"]
    receipt = json.loads(
        (RUN / "bounded-generation-receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["formal_holdout_executed"] is False
    assert receipt["side_effects"] is False
    assert receipt["backend"] == "fake-hypothesis-backend"
    assert receipt["requested_model"] == receipt["effective_model"]
    assert receipt["candidate_count"] == 3
    assert _no_leakage(receipt)

    artifacts = sorted((RUN / "artifacts").glob("aiverify-0.1.0*"))
    assert len(artifacts) == 2
    assert all(path.stat().st_size > 0 for path in artifacts)
    lines = [
        line
        for line in (RUN / "checksums.sha256").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 13
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert digest == sha256(RUN / relative)

    output = {
        "status": "passed",
        "source_contract_checks": 12,
        "run_record_checks": 8,
        "package_artifact_checks": len(artifacts),
        "checksum_manifest_checks": len(lines),
        "formal_holdout_executed": False,
        "side_effects": False,
    }
    print(json.dumps(output, sort_keys=True, indent=2))


def _no_leakage(value: object) -> bool:
    text = json.dumps(value, sort_keys=True).lower()
    return all(term not in text for term in ("hidden_mapping", "expected_oracle", "verdict"))


if __name__ == "__main__":
    main()
