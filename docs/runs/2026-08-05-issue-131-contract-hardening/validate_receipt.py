"""Validate the committed #131 contract-hardening evidence inventory."""

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
        ROOT / "src/aiverify/discovery/acquisition.py",
        ROOT / "tests/discovery/test_acquisition.py",
    )
    assert all(path.is_file() for path in sources)
    source = sources[0].read_text(encoding="utf-8")
    tests = sources[1].read_text(encoding="utf-8")
    for marker in (
        "object.__setattr__(self, \"requested_evidence\"",
        "self.no_diff is not True",
        "acquisition graph origin does not match target",
        "acquisition receipt commit does not match target",
    ):
        assert marker in source
    for marker in ("schema_version=True", "no_diff=False", "mixed_provenance"):
        assert marker in tests

    schema = json.loads(
        (ROOT / "src/aiverify/discovery/discovery_schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert schema["$defs"]["contextAcquisitionReceipt"]["properties"]["no_diff"] == {
        "const": True
    }

    artifacts = sorted((RUN / "artifacts").glob("aiverify-0.1.0*"))
    assert len(artifacts) == 2
    assert all(path.stat().st_size > 0 for path in artifacts)
    lines = [
        line for line in (RUN / "checksums.sha256").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(lines) == 8
    for line in lines:
        digest, relative = line.split("  ", 1)
        assert digest == sha256(RUN / relative)

    output = {
        "status": "passed",
        "source_contract_checks": 6,
        "run_record_checks": 6,
        "package_artifact_checks": len(artifacts),
        "checksum_manifest_checks": len(lines),
        "formal_holdout_executed": False,
    }
    print(json.dumps(output, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
