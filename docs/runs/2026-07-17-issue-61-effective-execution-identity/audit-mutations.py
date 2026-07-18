"""Recompute outer checksums after provenance mutations and require rejection."""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path


RUN_RECORD = Path(__file__).resolve().parent
REPO_ROOT = RUN_RECORD.parents[2]
SOURCE_ATTEMPT = RUN_RECORD / "success-attempt-2"
sys.path.insert(0, str(REPO_ROOT / "src"))

from aiverify.runner.execution_identity import (  # noqa: E402
    ExecutionIdentityError,
    verify_execution_provenance,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def reject(name: str, mutate, expected: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix=f"issue61-{name}-") as temp:
        attempt = Path(temp) / "attempt"
        shutil.copytree(SOURCE_ATTEMPT, attempt)
        provenance_path = attempt / "execution-provenance.json"
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        mutate(provenance, attempt)
        provenance_path.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        try:
            verify_execution_provenance(
                {
                    "path": "execution-provenance.json",
                    "sha256": sha256(provenance_path),
                },
                attempt_id=provenance["attempt_id"],
                scenario=provenance["scenario"],
                base_dir=attempt,
            )
        except ExecutionIdentityError as error:
            if expected not in str(error):
                raise AssertionError(f"{name}: unexpected rejection: {error}") from error
            return {
                "mutation": name,
                "outer_checksum_recomputed": True,
                "audit": "rejected",
                "reason": str(error),
            }
        raise AssertionError(f"{name}: tampered provenance was accepted")


def role_cwd(provenance: dict, attempt: Path) -> None:
    ref = provenance["roles"]["journey_driver"]["invocations"][0]
    receipt_path = attempt / ref["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["source_observation"]["session_meta"]["cwd"] = "/wrong/host"
    receipt["effective_model_source"]["observation_sha256"] = canonical_sha256(
        receipt["source_observation"]
    )
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    ref["sha256"] = sha256(receipt_path)


results = [
    reject(
        "host.origin",
        lambda manifest, _: manifest["host"].update(
            {"origin": "https://evil.invalid/replaced.git"}
        ),
        "host identity checksum mismatch",
    ),
    reject(
        "run_spec.package",
        lambda manifest, _: manifest["run_spec"].update(
            {"package": "org.example.replaced"}
        ),
        "Run Spec snapshot contradicts captured identity",
    ),
    reject(
        "deployment.process.args",
        lambda manifest, _: manifest["deployment"]["process"]["args"].__setitem__(
            2, "--device=wrong-device"
        ),
        "deployment process checksum mismatch",
    ),
    reject("journey_driver.session_cwd", role_cwd, "role session cwd contradicts"),
]

print(json.dumps({"mutations": results, "passed": len(results)}, indent=2))
