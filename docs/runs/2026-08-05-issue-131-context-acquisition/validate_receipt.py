"""Validate the committed #131 evidence inventory without external state."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


RUN = Path(__file__).resolve().parent
ROOT = RUN.parents[2]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    required_sources = (
        ROOT / "src/aiverify/discovery/acquisition.py",
        ROOT / "src/aiverify/discovery/models.py",
        ROOT / "src/aiverify/discovery/schema.py",
        ROOT / "src/aiverify/discovery/discovery_schema.json",
        ROOT / "tests/discovery/test_acquisition.py",
    )
    assert all(path.is_file() for path in required_sources)
    source_text = (ROOT / "src/aiverify/discovery/acquisition.py").read_text(encoding="utf-8").lower()
    forbidden = ("expected_verdict", "hidden_mapping", "production_adjudication", "formal_holdout")
    assert not any(term in source_text for term in forbidden)
    schema = json.loads((ROOT / "src/aiverify/discovery/discovery_schema.json").read_text(encoding="utf-8"))
    assert "contextAcquisitionResult" in schema["$defs"]
    assert "contextAcquisitionReceipt" in schema["$defs"]
    assert "inferred" in schema["$defs"]["contextFact"]["properties"]["status"]["enum"]
    assert "source_tree_sha256" in schema["$defs"]["contextGraph"]["properties"]

    readme = (RUN / "README.md").read_text(encoding="utf-8")
    for term in ("ProjectTarget", "budget", "unresolved", "checksums", "Local-only claim boundary"):
        assert term in readme
    artifacts = sorted((RUN / "artifacts").glob("aiverify-0.1.0*"))
    assert len(artifacts) == 2
    for artifact in artifacts:
        assert artifact.stat().st_size > 0
    checksums = RUN / "checksums.sha256"
    lines = [line for line in checksums.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 10
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert digest == sha256(RUN / relative)

    output = {
        "status": "passed",
        "source_contract_checks": len(required_sources) + 5,
        "run_record_checks": 8,
        "package_artifact_checks": len(artifacts),
        "checksum_manifest_checks": len(lines),
        "formal_holdout_executed": False,
    }
    print(json.dumps(output, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
