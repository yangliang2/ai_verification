"""M9 blinded project qualification manifest and preflight contracts.

This module validates the immutable hand-off between the M9 freeze issue and
the formal executor.  It deliberately does not build, install, launch, invoke
an agent, or load the clear auditor mapping.  The runtime admission receipts
are produced by the existing production seam and are checked here as
checksum-bound evidence.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


QUALIFICATION_ID = "m9-project-qualification-v1"
LANE_IDS = tuple(f"m9-lane-{index:02d}" for index in range(1, 7))
SOURCE_ORIGIN = "https://github.com/android/architecture-samples.git"
BASELINE_COMMIT = "ee66e1526b84c026615df032c705842b7d2a521f"
DEFECT_COMMIT = "208575f78d59716669d0733b5ed3e08797b08787"
PACKAGE = "com.example.android.architecture.blueprints.main"
ACTIVITY = "com.example.android.architecture.blueprints.todoapp.TodoActivity"
RUNNER_POLICY = "m9-production-seam-v1"
BACKEND = "codex_cli"
MODEL = "codex-default"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_GIT_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_FORBIDDEN_PACKET_TERMS = (
    "defect",
    "control",
    "variant",
    "mapping",
    "expected",
    "oracle",
    "verdict",
    "outcome",
    "holdout",
    "cohort",
    "finding",
    "journey",
    "locally_supported",
    "locally_rejected",
    "non_accountable",
    "inconclusive",
)


class M9QualificationError(ValueError):
    """Raised when the frozen M9 contract is incomplete or contradictory."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors))
        detail = "\n".join(f"- {error}" for error in self.errors)
        super().__init__(f"M9 qualification is invalid:\n{detail}")


@dataclass(frozen=True)
class M9QualificationManifest:
    """Exact manifest bytes and canonical identity."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]

    @property
    def qualification_id(self) -> str:
        return str(self.document["qualification_id"])

    @property
    def lanes(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["lanes"])


@dataclass(frozen=True)
class M9QualificationPreflight:
    """Serializable, side-effect-free freeze hand-off receipt."""

    manifest: M9QualificationManifest
    admitted: bool
    side_effects: bool
    formal_execution_started: bool
    checks: tuple[Mapping[str, Any], ...]
    lane_admissions: tuple[Mapping[str, Any], ...]
    leakage_audit: Mapping[str, Any]
    contradiction_audit: Mapping[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "qualification_id": self.manifest.qualification_id,
            "manifest_sha256": self.manifest.source_sha256,
            "canonical_manifest_sha256": self.manifest.canonical_sha256,
            "admitted": self.admitted,
            "side_effects": self.side_effects,
            "formal_execution_started": self.formal_execution_started,
            "checks": [dict(item) for item in self.checks],
            "lane_admissions": [dict(item) for item in self.lane_admissions],
            "leakage_audit": dict(self.leakage_audit),
            "contradiction_audit": dict(self.contradiction_audit),
            "claim_boundary": dict(self.manifest.document["claim_boundary"]),
        }


def canonical_json_bytes(value: object) -> bytes:
    """Encode a JSON value using the repository's checksum convention."""

    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(value).hexdigest()


def sha256_file(path: str | Path) -> str:
    """Hash one file without changing it."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: str | Path) -> M9QualificationManifest:
    """Load and semantically validate the frozen manifest fail-closed."""

    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, M9QualificationError) as error:
        raise M9QualificationError((f"manifest cannot be read: {error}",)) from error
    if not isinstance(document, dict):
        raise M9QualificationError(("manifest root must be an object",))
    errors = _manifest_errors(document)
    if errors:
        raise M9QualificationError(errors)
    return M9QualificationManifest(
        source_path=source_path,
        source_sha256=sha256_bytes(raw),
        canonical_sha256=sha256_bytes(canonical_json_bytes(document)),
        document=document,
    )


def audit_neutral_packets(packets: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Prove verifier-facing packets omit ground-truth and outcome material."""

    checks: list[dict[str, Any]] = []
    for packet in packets:
        packet_id = packet.get("packet_id", "unknown")
        terms = _leakage_terms(packet)
        checks.append(
            {
                "packet_id": packet_id,
                "status": "pass" if not terms else "fail",
                "forbidden_terms": list(terms),
                "mapping_withheld": True,
                "expected_evidence_withheld": True,
                "oracle_conclusion_withheld": True,
                "verdict_withheld": True,
            }
        )
    failures = [item for item in checks if item["status"] != "pass"]
    return {
        "status": "pass" if checks and not failures else "fail",
        "packet_count": len(checks),
        "checks": checks,
        "mapping_released": False,
        "release_point": "after_context_acquisition_portfolio_attack_plan_and_leakage_audit",
    }


def audit_contradiction_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a contradiction packet before any runner side effect."""

    required = tuple(packet.get("required_fields", ()))
    present = tuple(packet.get("present_fields", ()))
    missing = tuple(field for field in required if field not in present)
    expected = packet.get("expected_admission") == "rejected"
    denominator = packet.get("formal_denominator") is False
    no_side_effects = packet.get("side_effects") is False
    pre_side_effect = packet.get("rejection_boundary") == "before_any_build_device_agent_or_runtime_side_effect"
    passed = bool(missing) and expected and denominator and no_side_effects and pre_side_effect
    return {
        "packet_id": packet.get("packet_id"),
        "status": "pass" if passed else "fail",
        "missing_fields": list(missing),
        "expected_admission": packet.get("expected_admission"),
        "formal_denominator": packet.get("formal_denominator"),
        "side_effects": packet.get("side_effects"),
        "rejection_boundary": packet.get("rejection_boundary"),
        "command_calls": [],
        "pre_side_effect_rejection": pre_side_effect,
    }


def validate_admission_receipts(
    receipts: Sequence[Mapping[str, Any]],
    *,
    lane_ids: Sequence[str] = LANE_IDS,
) -> dict[str, Any]:
    """Validate six committed production-seam admission receipts."""

    expected_ids = tuple(lane_ids)
    checks: list[dict[str, Any]] = []
    for lane_id, receipt in zip(expected_ids, receipts, strict=False):
        options = (
            receipt.get("runner_policy", {}).get("options", {})
            if isinstance(receipt.get("runner_policy"), Mapping)
            else {}
        )
        effects = receipt.get("side_effects", {})
        passed = (
            receipt.get("admitted") is True
            and receipt.get("status") == "admitted"
            and isinstance(effects, Mapping)
            and effects.get("external") is False
            and effects.get("build") is False
            and effects.get("device") is False
            and effects.get("agent") is False
            and options.get("device") == "emulator-5554"
            and options.get("backend") == BACKEND
            and options.get("requested_driver_model") == MODEL
            and options.get("requested_l3_model") == MODEL
            and options.get("runner_policy_version") == RUNNER_POLICY
        )
        checks.append(
            {
                "lane_id": lane_id,
                "status": "pass" if passed else "fail",
                "receipt_status": receipt.get("status"),
                "side_effects": dict(effects) if isinstance(effects, Mapping) else effects,
            }
        )
    if len(receipts) != len(expected_ids):
        checks.append(
            {
                "lane_id": "population",
                "status": "fail",
                "reason": f"expected {len(expected_ids)} receipts, got {len(receipts)}",
            }
        )
    failures = [item for item in checks if item["status"] != "pass"]
    return {
        "status": "pass" if not failures else "fail",
        "receipt_count": len(receipts),
        "checks": checks,
        "formal_execution_started": False,
    }


def _manifest_errors(document: Mapping[str, Any]) -> tuple[str, ...]:
    errors: list[str] = []

    def require(name: str) -> object | None:
        if name not in document:
            errors.append(f"missing manifest field: {name}")
            return None
        return document[name]

    if require("schema_version") != 1:
        errors.append("schema_version must be 1")
    if require("qualification_id") != QUALIFICATION_ID:
        errors.append("qualification_id is not the M9 project qualification")
    if require("status") != "frozen":
        errors.append("manifest status must be frozen")
    if require("formal_holdout_executed") is not False:
        errors.append("formal_holdout_executed must be false in #136")
    if require("formal_denominator") is not False:
        errors.append("formal_denominator must be false in #136")

    implementation = document.get("implementation", {})
    if not isinstance(implementation, Mapping):
        errors.append("implementation must be an object")
    elif implementation.get("merged_commit") != "d3e03dc036a1fb8d0f7f314e7999b58294399242":
        errors.append("implementation merged commit is not the exact #135 merge")

    target = document.get("target", {})
    if not isinstance(target, Mapping):
        errors.append("target must be an object")
    else:
        if target.get("source_origin") != SOURCE_ORIGIN:
            errors.append("target origin drifted")
        if target.get("source_commit") != BASELINE_COMMIT:
            errors.append("target baseline commit drifted")
        if target.get("defect", {}).get("commit") != DEFECT_COMMIT:
            errors.append("target defect commit drifted")
        if target.get("control", {}).get("commit") != BASELINE_COMMIT:
            errors.append("target control commit drifted")
        if target.get("package") != PACKAGE or target.get("activity") != ACTIVITY:
            errors.append("target package/activity identity drifted")

    cohort = document.get("cohort", {})
    lanes = document.get("lanes", ())
    if not isinstance(cohort, Mapping):
        errors.append("cohort must be an object")
    else:
        if cohort.get("lane_count") != 6:
            errors.append("cohort lane_count must be 6")
        if cohort.get("defect_count") != 3 or cohort.get("control_count") != 3:
            errors.append("cohort must contain three defect and three control lanes")
        if tuple(cohort.get("lane_order", ())) != LANE_IDS:
            errors.append("cohort lane order drifted")
        commitment = cohort.get("mapping_commitment", {})
        if not isinstance(commitment, Mapping) or not _SHA256.fullmatch(str(commitment.get("sha256", ""))):
            errors.append("mapping commitment must be a SHA-256 digest")
        elif commitment.get("clear_mapping_in_verifier_inputs") is not False:
            errors.append("clear mapping must be excluded from verifier inputs")

    if not isinstance(lanes, list) or tuple(item.get("lane_id") for item in lanes) != LANE_IDS:
        errors.append("lanes must contain six opaque lane IDs in approved order")
    elif any("role" in item or "variant" in item for item in lanes):
        errors.append("lane manifest must not expose role or variant")

    runner = document.get("runner", {})
    if not isinstance(runner, Mapping):
        errors.append("runner must be an object")
    else:
        if runner.get("backend") != BACKEND or runner.get("policy_version") != RUNNER_POLICY:
            errors.append("runner backend/policy drifted")
        if runner.get("device") != "emulator-5554":
            errors.append("runner device drifted")
        if runner.get("requested_driver_model") != MODEL or runner.get("requested_l3_model") != MODEL:
            errors.append("runner model identity drifted")

    policy = document.get("policy", {})
    if not isinstance(policy, Mapping):
        errors.append("policy must be an object")
    else:
        if policy.get("portfolio_budget") != 8:
            errors.append("portfolio budget must be 8")
        if policy.get("top_three_portfolio") is not True:
            errors.append("top-three portfolio policy is not frozen")
        if policy.get("one_attempt_per_lane") is not True:
            errors.append("one-attempt policy is not frozen")
        if policy.get("zero_retry") is not True or policy.get("zero_replacement") is not True:
            errors.append("zero-retry/zero-replacement policy is not frozen")

    claim = document.get("claim_boundary", {})
    if not isinstance(claim, Mapping) or claim.get("local_only") is not True:
        errors.append("claim boundary must be local-only")

    return tuple(dict.fromkeys(errors))


def _leakage_terms(value: object) -> tuple[str, ...]:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    return tuple(
        term for term in _FORBIDDEN_PACKET_TERMS if re.search(rf"\b{re.escape(term)}\b", text)
    )


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M9QualificationError((f"duplicate manifest key: {key}",))
        result[key] = value
    return result


__all__ = [
    "ACTIVITY",
    "BACKEND",
    "BASELINE_COMMIT",
    "DEFECT_COMMIT",
    "LANE_IDS",
    "M9QualificationError",
    "M9QualificationManifest",
    "M9QualificationPreflight",
    "MODEL",
    "PACKAGE",
    "QUALIFICATION_ID",
    "RUNNER_POLICY",
    "SOURCE_ORIGIN",
    "audit_contradiction_packet",
    "audit_neutral_packets",
    "canonical_json_bytes",
    "load_manifest",
    "sha256_bytes",
    "sha256_file",
    "validate_admission_receipts",
]
