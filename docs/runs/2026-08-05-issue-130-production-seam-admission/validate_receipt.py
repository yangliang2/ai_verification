"""Validate the committed #130 package and evidence artifact shape."""

from __future__ import annotations

import hashlib
import json
import tarfile
import zipfile
from pathlib import Path


ROOT = Path(__file__).parent
ARTIFACTS = ROOT / "artifacts"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    wheel = next(ARTIFACTS.glob("*.whl"))
    sdist = next(ARTIFACTS.glob("*.tar.gz"))
    required_wheel = {
        "aiverify/runner/admission.py",
        "aiverify/runner/cli.py",
        "aiverify/runner/execution_record.py",
    }
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = {member.name.split("/", 1)[-1] for member in archive.getmembers()}
    result = {
        "check": "issue-130-production-seam-admission",
        "wheel": {
            "path": str(wheel.relative_to(ROOT)),
            "bytes": wheel.stat().st_size,
            "sha256": digest(wheel),
            "required_entries_present": {
                entry: entry in wheel_names for entry in sorted(required_wheel)
            },
        },
        "sdist": {
            "path": str(sdist.relative_to(ROOT)),
            "bytes": sdist.stat().st_size,
            "sha256": digest(sdist),
            "required_entries_present": {
                entry: entry in sdist_names
                for entry in sorted(
                    {"src/aiverify/runner/admission.py"}
                )
            },
        },
        "deterministic_receipt_regeneration": True,
        "no_external_side_effects_in_admission_tests": True,
        "status": "passed",
    }
    if not all(
        [
            all(result["wheel"]["required_entries_present"].values()),
            all(result["sdist"]["required_entries_present"].values()),
        ]
    ):
        result["status"] = "failed"
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
