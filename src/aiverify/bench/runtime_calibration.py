"""Strict source-of-truth verification for the OpenCalc calibration family.

This module is intentionally the small, side-effect-free front door for issue
#200.  It verifies one checked-in V1 candidate directory and writes only the
two stage receipts in a caller-owned output directory.  It does not invoke
Git, a build tool, Android CLI, adb, a model, or a runtime oracle.

The later calibration stages consume the identities emitted here.  Keeping
the input contract in one module also makes it possible to test the public
command without coupling tests to the implementation of the later stages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

SCHEMA_VERSION = 1
FAMILY_ID = "opencalc-runtime-calibration-v1"
FAMILY_VERSION = "v1"
CANDIDATE_MANIFEST_FILENAME = "candidate-manifest.json"
CANDIDATE_CLAIM_BOUNDARY = "candidate_source_of_truth_only"

UPSTREAM_ORIGIN = "https://github.com/clementwzk/OpenCalc.git"
UPSTREAM_COMMIT = "0584d61189e916a62a3b402223b35e1d7a3093db"
TARGET_SOURCE_PATH = (
    "app/src/main/java/com/darkempire78/opencalculator/activities/MainActivity.kt"
)
TARGET_SOURCE_SHA256 = "409e08157ce741bf77f7f00817a28eabee11cd1f6a5355bff7d1dd5a977eaac"
UPSTREAM_TREE_SHA256 = "8793c063c6a990ff3448fece38e62bc103952610"
UPSTREAM_ARCHIVE_SHA256 = "58d686b47f4a97f8b1127ab3de98bdf34a1c9310a221e5d5a7b4b5adcde54f3c"

PAIR_ID = "opencalc-input-save-enabled-v1"
QUALITY_CONTRACT_ID = "opencalc-unfinished-expression-config-recreation-v1"
RISK_PRIOR_ID = "opencalc-state-evolution-v1"
ATTACK_OPERATOR_ID = "orientation-activity-recreation-v1"
RISK_HYPOTHESIS_ID = "opencalc-input-preservation-v1"
ATTACK_PLAN_ID = "opencalc-orientation-preservation-v1"
EXPLORATION_POLICY_ID = "opencalc-context-nine-v1"
PREPARATION_CONTRACT_ID = "opencalc-runtime-preparation-v1"
TERMINAL_STATE_CONTRACT_ID = "opencalc-runtime-terminal-state-v1"
REDUCER_CONTRACT_ID = "opencalc-runtime-reducer-v1"
EVIDENCE_BOUNDARY_ID = "opencalc-journey-evidence-boundary-v1"
CLAIM_BOUNDARY_FAMILY_KIND = "Runtime Calibration Family"
CLAIM_BOUNDARY_ALLOWED_TERMINAL_STATES = (
    "expected_split_observed",
    "unexpected_runtime_result",
    "not_calibrated",
)
CLAIM_BOUNDARY_EXCLUSIONS = (
    "Qualification Cohort or benchmark denominator",
    "Verification Agent capability or detection rate",
    "L3, model adjudication, or Finding",
    "upstream acceptance or general Android coverage",
)
CLAIM_BOUNDARY_SCOPE = (
    "Only the frozen OpenCalc source, four opaque lane commitments, and later "
    "production-seam evidence may be interpreted."
)

LANE_IDS = tuple(f"ocrc-v1-lane-{number:02d}" for number in range(1, 5))
LANE_DIRECTORIES = tuple(f"lane-{number:02d}" for number in range(1, 5))
LANE_FILE_NAMES = ("projection.json", "driver-plan.json", "recipe.json", "run-spec.yaml")
DRIVER_PLAN_ACTIONS = (
    ("action-01", "wait_for_resource_id", "oneButton"),
    ("action-02", "tap_resource_id", "oneButton"),
    ("action-03", "tap_resource_id", "twoButton"),
    ("action-04", "tap_resource_id", "addButton"),
    ("action-05", "tap_resource_id", "threeButton"),
    ("action-06", "tap_resource_id", "fourButton"),
)
BUILD_COMMAND = (
    "./gradlew",
    "--offline",
    "--no-daemon",
    "--no-build-cache",
    "--no-configuration-cache",
    "--max-workers=1",
    "--console=plain",
    "clean",
    ":app:assembleDebug",
)


def _expected_patch_text(right_hand_side: str) -> str:
    return (
        "diff --git a/app/src/main/java/com/darkempire78/opencalculator/activities/MainActivity.kt "
        "b/app/src/main/java/com/darkempire78/opencalculator/activities/MainActivity.kt\n"
        "--- a/app/src/main/java/com/darkempire78/opencalculator/activities/MainActivity.kt\n"
        "+++ b/app/src/main/java/com/darkempire78/opencalculator/activities/MainActivity.kt\n"
        "@@ -120,6 +120,7 @@\n"
        "        fixView()\n"
        "\n"
        "        setContentView(view)\n"
        "\n"
        "        // Disable the keyboard on display EditText\n"
        "        binding.input.showSoftInputOnFocus = false\n"
        f"+        binding.input.isSaveEnabled = {right_hand_side}\n"
    )

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_LANE_RE = re.compile(r"^ocrc-v1-lane-0[1-4]$")

_SCHEMA_CONTRACTS = (
    "family_manifest",
    "source_pair",
    "discovery_commitments",
    "claim_boundary",
    "projection",
    "driver_plan",
    "run_spec",
    "recipe",
)

_SCHEMA_DOCUMENT_KINDS = {
    "family_manifest": "runtime_calibration_family_manifest",
    "source_pair": "runtime_calibration_source_pair",
    "discovery_commitments": "runtime_calibration_discovery_commitments",
    "claim_boundary": "runtime_calibration_claim_boundary",
    "projection": "blind_runtime_projection",
    "driver_plan": "deterministic_driver_plan",
    "run_spec": "runtime_calibration_run_spec",
    "recipe": "runtime_build_recipe",
}
_SCHEMA_TITLES = {
    "family_manifest": "OpenCalc Runtime Calibration family manifest",
    "source_pair": "OpenCalc Runtime Calibration matched source pair",
    "discovery_commitments": "OpenCalc Runtime Calibration discovery commitments",
    "claim_boundary": "OpenCalc Runtime Calibration claim boundary",
    "projection": "OpenCalc blind runtime projection",
    "driver_plan": "OpenCalc deterministic driver plan",
    "run_spec": "OpenCalc backend-neutral Run Spec",
    "recipe": "OpenCalc Runtime Build Recipe",
}
_SCHEMA_REQUIRED_FIELDS = {
    "family_manifest": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "status",
        "claim_boundary_ref",
        "source_pair_ref",
        "discovery_commitments_ref",
        "schema_refs",
        "backend_identity",
        "lane_root",
        "lane_ids",
        "lane_files",
        "quality_contract_id",
        "risk_prior_id",
        "attack_operator_id",
        "risk_hypothesis_id",
        "attack_plan_id",
        "exploration_policy_id",
        "preparation_contract_id",
        "terminal_state_contract_id",
        "reducer_contract_id",
        "evidence_boundary_id",
    ),
    "source_pair": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "pair_id",
        "population_classification",
        "taxonomy_id",
        "mutation_operator_id",
        "baseline",
        "upstream_source_anchor",
        "variants",
    ),
    "discovery_commitments": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "commitment_id",
        "context_acquisition",
        "neutral_contracts",
        "source_rich_package_commitments",
        "no_model_calls",
    ),
    "claim_boundary": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "claim_boundary_id",
        "family_kind",
        "local_only",
        "model_free",
        "allowed_terminal_states",
        "exclusions",
        "scope",
    ),
    "projection": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "lane_id",
        "projection_id",
        "run_spec_path",
        "driver_plan_path",
        "recipe_path",
        "claim_boundary_ref",
        "quality_contract_id",
        "risk_hypothesis_id",
        "attack_plan_id",
        "setup_plan",
        "evidence_boundary",
        "model_policy",
    ),
    "driver_plan": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "lane_id",
        "plan_id",
        "run_spec_path",
        "run_spec_sha256",
        "actions",
    ),
    "run_spec": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "lane_id",
        "run_spec_id",
        "host_project",
        "apk_glob",
        "package",
        "activity",
        "diff",
        "spec",
        "scenario",
    ),
    "recipe": (
        "schema_version",
        "document_kind",
        "family_id",
        "family_version",
        "lane_id",
        "recipe_id",
        "command",
        "timeout_seconds",
        "output_relative_path",
        "environment_policy",
        "claim_boundary_ref",
    ),
}
_SCHEMA_CANONICAL_SHA256 = {
    "claim_boundary": "4d69ecffdb556c8332bafbcc9b3e1e1e06143f9e3bf0dd26dc7c17e3e1b3069e",
    "discovery_commitments": "11fef56b419bdf5db26858ae3bb437c7dcf51932600758a001bd221c0afb7391",
    "driver_plan": "7f88e43db6906e0d94c3d77b4bc93de867adb5b4b54e268df8fd1653e40f346b",
    "family_manifest": "3d2fe94e08f88ad986d8862e29be2c3159c126edcc84731f38451d46cb92a7b8",
    "projection": "2e242d8ada565dd8e49dd15b57e5fcc01c1aa5b4853640e594b9a1fcf61a3670",
    "recipe": "862166d2cbb3aa60e503cd639df76514b398b13f18f2d728cf602800bad2590c",
    "run_spec": "e76a4f512a8908a28f3c4d1d578b5f45d17336777249716ede3b932f8e513fad",
    "source_pair": "5ae2a46f51e266ea93fbfd4c28d7847bb5aaa7c7da46caeb0a2da7d97cc45daa",
}


def _expected_artifact_kinds() -> tuple[str, ...]:
    kinds = list(_SCHEMA_CONTRACTS[:4])
    kinds.extend(f"{contract}_schema" for contract in _SCHEMA_CONTRACTS)
    for number in range(1, 5):
        kinds.extend(
            (
                f"lane_{number:02d}_projection",
                f"lane_{number:02d}_driver_plan",
                f"lane_{number:02d}_recipe",
                f"lane_{number:02d}_run_spec",
            )
        )
    return tuple(kinds)


EXPECTED_ARTIFACT_KINDS = _expected_artifact_kinds()


def _expected_artifact_paths() -> tuple[str, ...]:
    paths = [
        "family-manifest.json",
        "source-pair.json",
        "discovery-commitments.json",
        "claim-boundary.json",
    ]
    paths.extend(f"schemas/{contract}.schema.json" for contract in _SCHEMA_CONTRACTS)
    for directory in LANE_DIRECTORIES:
        paths.extend(
            f"runtime/lanes/{directory}/{file_name}" for file_name in LANE_FILE_NAMES
        )
    return tuple(paths)


EXPECTED_ARTIFACT_PATHS = _expected_artifact_paths()


class RuntimeCalibrationError(ValueError):
    """Base error for the V1 source-of-truth boundary."""


class CandidateVerificationError(RuntimeCalibrationError):
    """A stable, non-disclosing candidate rejection."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class StageReceiptError(RuntimeCalibrationError):
    """The stage could not durably establish or finalize its receipt."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ArtifactDigest:
    """The two byte identities recorded for one public input artifact."""

    kind: str
    path: str
    sha256: str
    canonical_sha256: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "canonical_sha256": self.canonical_sha256,
        }


@dataclass(frozen=True)
class CandidateInputs:
    """Validated V1 inputs and their immutable public identities."""

    root: Path
    family_id: str
    family_version: str
    candidate_identity_sha256: str
    manifest_sha256: str
    canonical_manifest_sha256: str
    claim_boundary: str
    artifacts: tuple[ArtifactDigest, ...]

    @property
    def artifact_inventory_sha256(self) -> str:
        return _sha256_bytes(
            _canonical_json_bytes([artifact.to_dict() for artifact in self.artifacts])
        )


@dataclass(frozen=True)
class CandidateVerificationReceipt:
    """Serialized result of one ``verify-candidate`` stage."""

    accepted: bool
    candidate_root: Path
    family_id: str | None
    family_version: str | None
    candidate_identity_sha256: str | None
    manifest_sha256: str | None
    canonical_manifest_sha256: str | None
    claim_boundary: str
    artifact_count: int
    artifacts: tuple[ArtifactDigest, ...]
    artifact_inventory_sha256: str | None
    reason: str | None
    output_root: Path
    start_receipt_sha256: str
    terminal_identity_sha256: str

    @property
    def status(self) -> str:
        return "accepted" if self.accepted else "rejected"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "stage": "verify-candidate",
            "status": self.status,
            "candidate_root": str(self.candidate_root),
            "family_id": self.family_id,
            "family_version": self.family_version,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "manifest_sha256": self.manifest_sha256,
            "canonical_manifest_sha256": self.canonical_manifest_sha256,
            "claim_boundary": self.claim_boundary,
            "artifact_count": self.artifact_count,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "artifact_inventory_sha256": self.artifact_inventory_sha256,
            "reason": self.reason,
            "output_root": str(self.output_root),
            "start_receipt_sha256": self.start_receipt_sha256,
            "terminal_identity_sha256": self.terminal_identity_sha256,
        }


@dataclass(frozen=True)
class _LoadedDocument:
    path: str
    raw_sha256: str
    canonical_sha256: str
    document: dict[str, Any]


_CANDIDATE_FIELDS = {
    "schema_version",
    "document_kind",
    "family_id",
    "family_version",
    "status",
    "claim_boundary_ref",
    "required_artifact_kinds",
    "artifacts",
    "identity_sha256",
}
_ARTIFACT_FIELDS = {"kind", "path", "sha256", "canonical_sha256"}
_COMMON_FIELDS = {
    "schema_version",
    "document_kind",
    "family_id",
    "family_version",
}
_FAMILY_FIELDS = {
    *_COMMON_FIELDS,
    "status",
    "claim_boundary_ref",
    "source_pair_ref",
    "discovery_commitments_ref",
    "schema_refs",
    "backend_identity",
    "lane_root",
    "lane_ids",
    "lane_files",
    "quality_contract_id",
    "risk_prior_id",
    "attack_operator_id",
    "risk_hypothesis_id",
    "attack_plan_id",
    "exploration_policy_id",
    "preparation_contract_id",
    "terminal_state_contract_id",
    "reducer_contract_id",
    "evidence_boundary_id",
}
_SOURCE_PAIR_FIELDS = {
    "schema_version",
    "document_kind",
    "family_id",
    "family_version",
    "pair_id",
    "population_classification",
    "taxonomy_id",
    "mutation_operator_id",
    "baseline",
    "upstream_source_anchor",
    "variants",
}
_DISCOVERY_FIELDS = {
    *_COMMON_FIELDS,
    "commitment_id",
    "context_acquisition",
    "neutral_contracts",
    "source_rich_package_commitments",
    "no_model_calls",
}
_CLAIM_FIELDS = {
    "schema_version",
    "document_kind",
    "family_id",
    "family_version",
    "claim_boundary_id",
    "family_kind",
    "local_only",
    "model_free",
    "allowed_terminal_states",
    "exclusions",
    "scope",
}
_PROJECTION_FIELDS = {
    *_COMMON_FIELDS,
    "document_kind",
    "lane_id",
    "projection_id",
    "run_spec_path",
    "driver_plan_path",
    "recipe_path",
    "claim_boundary_ref",
    "quality_contract_id",
    "risk_hypothesis_id",
    "attack_plan_id",
    "setup_plan",
    "evidence_boundary",
    "model_policy",
}
_PLAN_FIELDS = {
    *_COMMON_FIELDS,
    "lane_id",
    "plan_id",
    "run_spec_path",
    "run_spec_sha256",
    "actions",
}
_RECIPE_FIELDS = {
    *_COMMON_FIELDS,
    "lane_id",
    "recipe_id",
    "command",
    "timeout_seconds",
    "output_relative_path",
    "environment_policy",
    "claim_boundary_ref",
}
_RUN_SPEC_FIELDS = {
    *_COMMON_FIELDS,
    "lane_id",
    "run_spec_id",
    "host_project",
    "apk_glob",
    "package",
    "activity",
    "diff",
    "spec",
    "scenario",
}
_SCHEMA_FIELDS = {"schema_version", "document_kind", "contract_kind", "json_schema"}
_START_RECEIPT_FIELDS = {
    "schema_version",
    "stage",
    "status",
    "candidate_root",
    "output_root",
    "claim_boundary",
    "started_at",
    "start_identity_sha256",
}
_TERMINAL_RECEIPT_FIELDS = {
    "schema_version",
    "stage",
    "status",
    "candidate_root",
    "family_id",
    "family_version",
    "candidate_identity_sha256",
    "manifest_sha256",
    "canonical_manifest_sha256",
    "claim_boundary",
    "artifact_count",
    "artifacts",
    "artifact_inventory_sha256",
    "reason",
    "output_root",
    "start_receipt_sha256",
    "finished_at",
    "terminal_identity_sha256",
}


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise CandidateVerificationError("candidate_non_json_value") from error


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(value: Any) -> str:
    """Return the public canonical JSON identity for one parsed document."""

    return _sha256_bytes(_canonical_json_bytes(value))


def _required_text(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateVerificationError("candidate_input_contradictory")
    return value


def _require_sha256(value: Any) -> str:
    text = _required_text(value)
    if _SHA256.fullmatch(text) is None:
        raise CandidateVerificationError("candidate_input_contradictory")
    return text


def _require_commit(value: Any) -> str:
    text = _required_text(value)
    if _COMMIT.fullmatch(text) is None:
        raise CandidateVerificationError("candidate_input_contradictory")
    return text


def _reject_unknown(document: Mapping[str, Any], allowed: set[str]) -> None:
    if set(document) - allowed:
        raise CandidateVerificationError("candidate_unknown_field")


def _require_exact_fields(document: Mapping[str, Any], fields: set[str]) -> None:
    _reject_unknown(document, fields)
    if set(document) != fields:
        raise CandidateVerificationError("candidate_missing_field")


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CandidateVerificationError("candidate_duplicate_key")
        result[key] = value
    return result


class _UniqueYamlLoader(yaml.SafeLoader):
    pass


def _construct_unique_mapping(
    loader: _UniqueYamlLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise CandidateVerificationError("candidate_duplicate_key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueYamlLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _parse_document(raw: bytes, path: Path) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CandidateVerificationError("candidate_input_encoding_invalid") from error
    if text.startswith("\ufeff"):
        raise CandidateVerificationError("candidate_input_encoding_invalid")
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                CandidateVerificationError("candidate_non_json_value")
            ),
        )
    except CandidateVerificationError:
        raise
    except json.JSONDecodeError:
        if path.suffix.lower() not in {".yaml", ".yml"}:
            raise CandidateVerificationError("candidate_document_invalid") from None
        try:
            parsed = yaml.load(text, Loader=_UniqueYamlLoader)
        except CandidateVerificationError:
            raise
        except yaml.YAMLError:
            raise CandidateVerificationError("candidate_document_invalid") from None
    if not isinstance(parsed, dict) or any(not isinstance(key, str) for key in parsed):
        raise CandidateVerificationError("candidate_document_invalid")
    _canonical_json_bytes(parsed)
    return parsed


def canonical_json_bytes(value: Any) -> bytes:
    """Return the canonical UTF-8 JSON bytes used by V1 identities."""

    return _canonical_json_bytes(value)


def _safe_relative_path(value: Any) -> str:
    path = _required_text(value)
    if "\\" in path:
        raise CandidateVerificationError("candidate_path_invalid")
    parsed = PurePosixPath(path)
    if (
        parsed.is_absolute()
        or path != parsed.as_posix()
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise CandidateVerificationError("candidate_path_invalid")
    return path


def _contained_file(root: Path, relative_path: str) -> Path:
    relative_path = _safe_relative_path(relative_path)
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    try:
        if path.is_symlink():
            raise CandidateVerificationError("candidate_artifact_invalid")
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except CandidateVerificationError:
        raise
    except (OSError, RuntimeError, ValueError):
        raise CandidateVerificationError("candidate_artifact_missing") from None
    if not path.is_file():
        raise CandidateVerificationError("candidate_artifact_invalid")
    return path


def _load_document(root: Path, relative_path: str) -> _LoadedDocument:
    path = _contained_file(root, relative_path)
    try:
        raw = path.read_bytes()
    except OSError:
        raise CandidateVerificationError("candidate_artifact_unreadable") from None
    document = _parse_document(raw, path)
    return _LoadedDocument(
        path=relative_path,
        raw_sha256=_sha256_bytes(raw),
        canonical_sha256=canonical_sha256(document),
        document=document,
    )


def _artifact_entry(value: Any) -> ArtifactDigest:
    if not isinstance(value, Mapping):
        raise CandidateVerificationError("candidate_artifact_invalid")
    _require_exact_fields(value, _ARTIFACT_FIELDS)
    return ArtifactDigest(
        kind=_required_text(value["kind"]),
        path=_safe_relative_path(value["path"]),
        sha256=_require_sha256(value["sha256"]),
        canonical_sha256=_require_sha256(value["canonical_sha256"]),
    )


def _without_identity(document: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(document)
    value.pop("identity_sha256", None)
    return value


def _check_common(document: Mapping[str, Any], expected_kind: str) -> None:
    if not _COMMON_FIELDS.issubset(document):
        raise CandidateVerificationError("candidate_missing_field")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise CandidateVerificationError("candidate_schema_version_mismatch")
    if document.get("family_id") != FAMILY_ID:
        raise CandidateVerificationError("candidate_family_identity_mismatch")
    if document.get("family_version") != FAMILY_VERSION:
        raise CandidateVerificationError("candidate_input_version_mismatch")
    if document.get("document_kind") != expected_kind:
        raise CandidateVerificationError("candidate_document_kind_mismatch")


def _validate_family_manifest(document: Mapping[str, Any], paths: Mapping[str, ArtifactDigest]) -> None:
    _require_exact_fields(document, _FAMILY_FIELDS)
    _check_common(document, "runtime_calibration_family_manifest")
    if document["status"] != "candidate_frozen":
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["backend_identity"] != "deterministic_android_v1":
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["lane_root"] != "runtime/lanes":
        raise CandidateVerificationError("candidate_input_contradictory")
    if tuple(document["lane_ids"]) != LANE_IDS:
        raise CandidateVerificationError("candidate_input_contradictory")
    if tuple(document["schema_refs"]) != tuple(
        f"schemas/{contract}.schema.json" for contract in _SCHEMA_CONTRACTS
    ):
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["claim_boundary_ref"] != "claim-boundary.json":
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["source_pair_ref"] != "source-pair.json":
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["discovery_commitments_ref"] != "discovery-commitments.json":
        raise CandidateVerificationError("candidate_input_contradictory")
    if {
        document["quality_contract_id"],
        document["risk_prior_id"],
        document["attack_operator_id"],
        document["risk_hypothesis_id"],
        document["attack_plan_id"],
        document["exploration_policy_id"],
    } != {
        QUALITY_CONTRACT_ID,
        RISK_PRIOR_ID,
        ATTACK_OPERATOR_ID,
        RISK_HYPOTHESIS_ID,
        ATTACK_PLAN_ID,
        EXPLORATION_POLICY_ID,
    }:
        raise CandidateVerificationError("candidate_input_contradictory")
    expected_contracts = {
        "preparation_contract_id": PREPARATION_CONTRACT_ID,
        "terminal_state_contract_id": TERMINAL_STATE_CONTRACT_ID,
        "reducer_contract_id": REDUCER_CONTRACT_ID,
        "evidence_boundary_id": EVIDENCE_BOUNDARY_ID,
    }
    if any(document[field] != value for field, value in expected_contracts.items()):
        raise CandidateVerificationError("candidate_input_version_mismatch")
    lane_files = document["lane_files"]
    if not isinstance(lane_files, list) or len(lane_files) != 4:
        raise CandidateVerificationError("candidate_input_contradictory")
    for number, lane in enumerate(lane_files, start=1):
        if not isinstance(lane, Mapping):
            raise CandidateVerificationError("candidate_input_contradictory")
        _require_exact_fields(
            lane,
            {"lane_id", "relative_path", "projection", "driver_plan", "recipe", "run_spec"},
        )
        lane_id = f"ocrc-v1-lane-{number:02d}"
        directory = f"runtime/lanes/lane-{number:02d}"
        expected = {
            "lane_id": lane_id,
            "relative_path": directory,
            "projection": f"{directory}/projection.json",
            "driver_plan": f"{directory}/driver-plan.json",
            "recipe": f"{directory}/recipe.json",
            "run_spec": f"{directory}/run-spec.yaml",
        }
        if dict(lane) != expected:
            raise CandidateVerificationError("candidate_input_contradictory")
        for field in ("projection", "driver_plan", "recipe", "run_spec"):
            if lane[field] not in paths:
                raise CandidateVerificationError("candidate_artifact_missing")


def _validate_source_pair(document: Mapping[str, Any]) -> None:
    _require_exact_fields(document, _SOURCE_PAIR_FIELDS)
    _check_common(document, "runtime_calibration_source_pair")
    if document["pair_id"] != PAIR_ID:
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["population_classification"] != "curated_controlled_injection":
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["taxonomy_id"] != "config-change-01":
        raise CandidateVerificationError("candidate_input_contradictory")
    if document["mutation_operator_id"] != "toggle-input-save-enabled-v1":
        raise CandidateVerificationError("candidate_input_contradictory")
    baseline = document["baseline"]
    if not isinstance(baseline, Mapping):
        raise CandidateVerificationError("candidate_input_contradictory")
    _require_exact_fields(
        baseline,
        {"origin", "commit", "tree_sha256", "archive_sha256"},
    )
    if (
        baseline["origin"] != UPSTREAM_ORIGIN
        or baseline["commit"] != UPSTREAM_COMMIT
        or baseline["tree_sha256"] != UPSTREAM_TREE_SHA256
        or baseline["archive_sha256"] != UPSTREAM_ARCHIVE_SHA256
    ):
        raise CandidateVerificationError("candidate_source_identity_mismatch")
    anchor = document["upstream_source_anchor"]
    if not isinstance(anchor, Mapping):
        raise CandidateVerificationError("candidate_anchor_invalid")
    _require_exact_fields(
        anchor,
        {
            "origin",
            "commit",
            "path",
            "target_file_sha256",
            "context",
            "context_sha256",
            "required_occurrences",
            "insertion_after",
        },
    )
    context = (
        "        setContentView(view)\n"
        "\n"
        "        // Disable the keyboard on display EditText\n"
        "        binding.input.showSoftInputOnFocus = false"
    )
    if (
        anchor["origin"] != UPSTREAM_ORIGIN
        or anchor["commit"] != UPSTREAM_COMMIT
        or anchor["path"] != TARGET_SOURCE_PATH
        or anchor["target_file_sha256"] != TARGET_SOURCE_SHA256
        or anchor["context"] != context
        or anchor["context_sha256"] != _sha256_bytes(context.encode("utf-8"))
        or anchor["required_occurrences"] != 1
        or anchor["insertion_after"] != "binding.input.showSoftInputOnFocus = false"
    ):
        raise CandidateVerificationError("candidate_anchor_drift")
    variants = document["variants"]
    if not isinstance(variants, list) or len(variants) != 2:
        raise CandidateVerificationError("candidate_input_contradictory")
    by_id: dict[str, Mapping[str, Any]] = {}
    for variant in variants:
        if not isinstance(variant, Mapping):
            raise CandidateVerificationError("candidate_input_contradictory")
        _require_exact_fields(
            variant,
            {"variant_id", "source_id", "patch_text", "patch_sha256", "difference"},
        )
        variant_id = variant["variant_id"]
        if variant_id in by_id:
            raise CandidateVerificationError("candidate_duplicate_input")
        if variant_id not in {"control", "defect"}:
            raise CandidateVerificationError("candidate_input_contradictory")
        by_id[variant_id] = variant
        patch_text = variant["patch_text"]
        if not isinstance(patch_text, str) or variant["patch_sha256"] != _sha256_bytes(
            patch_text.encode("utf-8")
        ):
            raise CandidateVerificationError("candidate_patch_digest_mismatch")
        difference = variant["difference"]
        if not isinstance(difference, Mapping):
            raise CandidateVerificationError("candidate_input_contradictory")
        _require_exact_fields(difference, {"field", "right_hand_side"})
        if difference["field"] != "binding.input.isSaveEnabled":
            raise CandidateVerificationError("candidate_input_contradictory")
        expected_rhs = {"control": "true", "defect": "false"}[variant_id]
        if difference["right_hand_side"] != expected_rhs:
            raise CandidateVerificationError("candidate_input_contradictory")
        if patch_text != _expected_patch_text(expected_rhs):
            raise CandidateVerificationError("candidate_patch_context_mismatch")
        if variant["source_id"] != f"{PAIR_ID}-{variant_id}":
            raise CandidateVerificationError("candidate_input_contradictory")
    if set(by_id) != {"control", "defect"}:
        raise CandidateVerificationError("candidate_input_contradictory")
    control_patch = by_id["control"]["patch_text"]
    defect_patch = by_id["defect"]["patch_text"]
    if control_patch.replace("isSaveEnabled = true", "isSaveEnabled = VALUE") != defect_patch.replace(
        "isSaveEnabled = false", "isSaveEnabled = VALUE"
    ):
        raise CandidateVerificationError("candidate_pair_not_matched")


def _validate_discovery_commitments(document: Mapping[str, Any]) -> None:
    _require_exact_fields(document, _DISCOVERY_FIELDS)
    _check_common(document, "runtime_calibration_discovery_commitments")
    if document["commitment_id"] != "opencalc-discovery-commitments-v1":
        raise CandidateVerificationError("candidate_input_contradictory")
    context = document["context_acquisition"]
    if not isinstance(context, Mapping):
        raise CandidateVerificationError("candidate_input_contradictory")
    _require_exact_fields(context, {"budget", "required_paths", "adapters"})
    required_paths = (
        TARGET_SOURCE_PATH,
        "app/src/main/AndroidManifest.xml",
        "app/src/main/res/layout/activity_main.xml",
        "app/src/main/res/layout-land/activity_main.xml",
        "app/build.gradle.kts",
        "build.gradle.kts",
        "settings.gradle.kts",
        "gradle/libs.versions.toml",
        "gradle/wrapper/gradle-wrapper.properties",
    )
    adapters = (
        "source-file",
        "manifest",
        "layout",
        "build-file",
        "settings",
        "version-catalog",
    )
    if (
        context["budget"] != 9
        or tuple(context["required_paths"]) != required_paths
        or tuple(context["adapters"]) != adapters
    ):
        raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
    contracts = document["neutral_contracts"]
    if not isinstance(contracts, Mapping):
        raise CandidateVerificationError("candidate_input_contradictory")
    _require_exact_fields(
        contracts,
        {
            "quality_contract_id",
            "risk_prior_id",
            "attack_operator_id",
            "risk_hypothesis_id",
            "attack_plan_id",
            "exploration_policy_id",
        },
    )
    expected = {
        "quality_contract_id": QUALITY_CONTRACT_ID,
        "risk_prior_id": RISK_PRIOR_ID,
        "attack_operator_id": ATTACK_OPERATOR_ID,
        "risk_hypothesis_id": RISK_HYPOTHESIS_ID,
        "attack_plan_id": ATTACK_PLAN_ID,
        "exploration_policy_id": EXPLORATION_POLICY_ID,
    }
    if dict(contracts) != expected:
        raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
    packages = document["source_rich_package_commitments"]
    if not isinstance(packages, list) or len(packages) != 4:
        raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
    package_keys: set[tuple[str, str]] = set()
    for package in packages:
        if not isinstance(package, Mapping):
            raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
        _require_exact_fields(package, {"package_id", "target_kind", "variant", "identity"})
        key = (str(package["target_kind"]), str(package["variant"]))
        package_keys.add(key)
        if package["target_kind"] not in {"ChangeTarget", "ProjectTarget"}:
            raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
        if package["variant"] not in {"control", "defect"}:
            raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
        _require_sha256(package["identity"])
    if package_keys != {
        ("ChangeTarget", "control"),
        ("ChangeTarget", "defect"),
        ("ProjectTarget", "control"),
        ("ProjectTarget", "defect"),
    }:
        raise CandidateVerificationError("candidate_discovery_commitment_mismatch")
    if document["no_model_calls"] is not True:
        raise CandidateVerificationError("candidate_model_policy_mismatch")


def _validate_claim_boundary(document: Mapping[str, Any]) -> None:
    _require_exact_fields(document, _CLAIM_FIELDS)
    if document["schema_version"] != SCHEMA_VERSION:
        raise CandidateVerificationError("candidate_schema_version_mismatch")
    if document["document_kind"] != "runtime_calibration_claim_boundary":
        raise CandidateVerificationError("candidate_document_kind_mismatch")
    if document["family_id"] != FAMILY_ID or document["family_version"] != FAMILY_VERSION:
        raise CandidateVerificationError("candidate_input_version_mismatch")
    if document["claim_boundary_id"] != CANDIDATE_CLAIM_BOUNDARY:
        raise CandidateVerificationError("candidate_claim_boundary_mismatch")
    if (
        document["family_kind"] != CLAIM_BOUNDARY_FAMILY_KIND
        or document["local_only"] is not True
        or document["model_free"] is not True
        or not isinstance(document["allowed_terminal_states"], list)
        or tuple(document["allowed_terminal_states"])
        != CLAIM_BOUNDARY_ALLOWED_TERMINAL_STATES
    ):
        raise CandidateVerificationError("candidate_claim_boundary_mismatch")
    if (
        not isinstance(document["exclusions"], list)
        or tuple(document["exclusions"]) != CLAIM_BOUNDARY_EXCLUSIONS
    ):
        raise CandidateVerificationError("candidate_claim_boundary_mismatch")
    if document["scope"] != CLAIM_BOUNDARY_SCOPE:
        raise CandidateVerificationError("candidate_claim_boundary_mismatch")


def _validate_schema_document(document: Mapping[str, Any], expected_contract: str) -> None:
    _require_exact_fields(document, _SCHEMA_FIELDS)
    if document["schema_version"] != SCHEMA_VERSION:
        raise CandidateVerificationError("candidate_schema_version_mismatch")
    if document["document_kind"] != "runtime_calibration_contract_schema":
        raise CandidateVerificationError("candidate_document_kind_mismatch")
    if document["contract_kind"] != expected_contract:
        raise CandidateVerificationError("candidate_schema_contract_mismatch")
    schema = document["json_schema"]
    if not isinstance(schema, Mapping):
        raise CandidateVerificationError("candidate_schema_invalid")
    required = schema.get("required")
    properties = schema.get("properties")
    if (
        schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("title") != _SCHEMA_TITLES[expected_contract]
        or schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or required != list(_SCHEMA_REQUIRED_FIELDS[expected_contract])
        or not isinstance(properties, Mapping)
        or set(properties) != set(required or ())
    ):
        raise CandidateVerificationError("candidate_schema_contract_mismatch")
    common_properties = {
        "schema_version": {"const": SCHEMA_VERSION},
        "document_kind": {"const": _SCHEMA_DOCUMENT_KINDS[expected_contract]},
        "family_id": {"const": FAMILY_ID},
        "family_version": {"const": FAMILY_VERSION},
    }
    if any(properties.get(field) != value for field, value in common_properties.items()):
        raise CandidateVerificationError("candidate_schema_contract_mismatch")
    if canonical_sha256(schema) != _SCHEMA_CANONICAL_SHA256[expected_contract]:
        raise CandidateVerificationError("candidate_schema_contract_mismatch")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError:
        raise CandidateVerificationError("candidate_schema_invalid") from None


def _validate_against_schema(
    document: Mapping[str, Any],
    schema_document: Mapping[str, Any],
) -> None:
    schema = schema_document["json_schema"]
    try:
        errors = list(Draft202012Validator(schema).iter_errors(document))
    except (KeyError, SchemaError, TypeError, ValueError):
        raise CandidateVerificationError("candidate_schema_invalid") from None
    if errors:
        raise CandidateVerificationError("candidate_schema_document_mismatch")


def _validate_projection(
    document: Mapping[str, Any],
    lane_id: str,
    expected_paths: Mapping[str, str],
) -> None:
    _require_exact_fields(document, _PROJECTION_FIELDS)
    _check_common(document, "blind_runtime_projection")
    if document["lane_id"] != lane_id or document["projection_id"] != f"{lane_id}-projection":
        raise CandidateVerificationError("candidate_lane_identity_mismatch")
    if (
        document["run_spec_path"] != expected_paths["run_spec"]
        or document["driver_plan_path"] != expected_paths["driver_plan"]
        or document["recipe_path"] != expected_paths["recipe"]
        or document["claim_boundary_ref"] != "claim-boundary.json"
        or document["quality_contract_id"] != QUALITY_CONTRACT_ID
        or document["risk_hypothesis_id"] != RISK_HYPOTHESIS_ID
        or document["attack_plan_id"] != ATTACK_PLAN_ID
    ):
        raise CandidateVerificationError("candidate_projection_binding_mismatch")
    setup = document["setup_plan"]
    if not isinstance(setup, Mapping):
        raise CandidateVerificationError("candidate_projection_invalid")
    _require_exact_fields(setup, {"id", "operations"})
    if setup != {
        "id": "attempt-setup-plan-v1",
        "operations": ["clear_package_data", "force_portrait"],
    }:
        raise CandidateVerificationError("candidate_projection_invalid")
    boundary = document["evidence_boundary"]
    if not isinstance(boundary, Mapping):
        raise CandidateVerificationError("candidate_projection_invalid")
    _require_exact_fields(boundary, {"normalized_result", "action_lineage", "raw_backend_evidence"})
    if boundary != {
        "normalized_result": "runner_owned",
        "action_lineage": "runner_owned",
        "raw_backend_evidence": "backend_owned",
    }:
        raise CandidateVerificationError("candidate_projection_invalid")
    model_policy = document["model_policy"]
    if not isinstance(model_policy, Mapping):
        raise CandidateVerificationError("candidate_projection_invalid")
    _require_exact_fields(model_policy, {"model_calls", "l3"})
    if model_policy != {"model_calls": 0, "l3": "forbidden"}:
        raise CandidateVerificationError("candidate_model_policy_mismatch")
    _reject_projection_leakage(document)


def _validate_plan(
    document: Mapping[str, Any],
    lane_id: str,
    expected_run_spec_path: str,
    run_spec_canonical_sha256: str,
) -> None:
    _require_exact_fields(document, _PLAN_FIELDS)
    _check_common(document, "deterministic_driver_plan")
    if document["lane_id"] != lane_id or document["plan_id"] != f"{lane_id}-driver-plan":
        raise CandidateVerificationError("candidate_lane_identity_mismatch")
    if (
        document["run_spec_path"] != expected_run_spec_path
        or document["run_spec_sha256"] != run_spec_canonical_sha256
    ):
        raise CandidateVerificationError("candidate_plan_binding_mismatch")
    actions = document["actions"]
    if not isinstance(actions, list) or len(actions) != len(DRIVER_PLAN_ACTIONS):
        raise CandidateVerificationError("candidate_plan_invalid")
    for action, expected in zip(actions, DRIVER_PLAN_ACTIONS):
        if not isinstance(action, Mapping):
            raise CandidateVerificationError("candidate_plan_invalid")
        _require_exact_fields(
            action,
            {
                "action_id",
                "kind",
                "resource_id",
                "timeout_ms",
                "observation_interval_ms",
                "settle_ms",
            },
        )
        if (
            action["action_id"],
            action["kind"],
            action["resource_id"],
        ) != expected:
            raise CandidateVerificationError("candidate_plan_invalid")
        if action["kind"] == "wait_for_resource_id":
            if action["timeout_ms"] != 5000 or action["observation_interval_ms"] != 350 or action["settle_ms"] != 0:
                raise CandidateVerificationError("candidate_plan_invalid")
        elif action["timeout_ms"] != 0 or action["observation_interval_ms"] != 0 or action["settle_ms"] != 350:
            raise CandidateVerificationError("candidate_plan_invalid")
    _reject_projection_leakage(document)


def _validate_recipe(document: Mapping[str, Any], lane_id: str) -> None:
    _require_exact_fields(document, _RECIPE_FIELDS)
    _check_common(document, "runtime_build_recipe")
    if document["lane_id"] != lane_id or document["recipe_id"] != f"{lane_id}-build-recipe":
        raise CandidateVerificationError("candidate_lane_identity_mismatch")
    if tuple(document["command"]) != BUILD_COMMAND:
        raise CandidateVerificationError("candidate_recipe_invalid")
    if document["timeout_seconds"] != 900 or document["output_relative_path"] != "build/app-debug.apk":
        raise CandidateVerificationError("candidate_recipe_invalid")
    environment = document["environment_policy"]
    if not isinstance(environment, Mapping):
        raise CandidateVerificationError("candidate_recipe_invalid")
    _require_exact_fields(environment, {"mode", "dependency_resolution", "network_claim", "retry"})
    if dict(environment) != {
        "mode": "private_allowlist",
        "dependency_resolution": "offline",
        "network_claim": "none",
        "retry": False,
    }:
        raise CandidateVerificationError("candidate_recipe_invalid")
    if document["claim_boundary_ref"] != "claim-boundary.json":
        raise CandidateVerificationError("candidate_recipe_invalid")
    _reject_projection_leakage(document)


def _validate_run_spec(document: Mapping[str, Any], lane_id: str) -> None:
    _require_exact_fields(document, _RUN_SPEC_FIELDS)
    _check_common(document, "runtime_calibration_run_spec")
    if document["lane_id"] != lane_id or document["run_spec_id"] != f"{lane_id}-run-spec":
        raise CandidateVerificationError("candidate_lane_identity_mismatch")
    if (
        document["host_project"] != "."
        or document["apk_glob"] != "build/app-debug.apk"
        or document["package"] != "com.darkempire78.opencalculator.debug"
        or document["activity"] != "com.darkempire78.opencalculator.activities.MainActivity"
        or document["diff"] is not None
        or document["spec"] is not None
    ):
        raise CandidateVerificationError("candidate_run_spec_invalid")
    scenario = document["scenario"]
    if not isinstance(scenario, Mapping):
        raise CandidateVerificationError("candidate_run_spec_invalid")
    _require_exact_fields(scenario, {"id", "user_actions", "system_events", "assertions"})
    actions = (
        "wait for resource id oneButton",
        "tap resource id oneButton",
        "tap resource id twoButton",
        "tap resource id addButton",
        "tap resource id threeButton",
        "tap resource id fourButton",
    )
    if (
        scenario["id"] != "opencalc-preserve-expression"
        or tuple(scenario["user_actions"]) != actions
        or scenario["system_events"]
        != [{"step_index": 5, "event": "rotate", "args": {"orientation": "landscape"}}]
        or scenario["assertions"] != []
    ):
        raise CandidateVerificationError("candidate_run_spec_invalid")
    _reject_projection_leakage(document)


def _reject_projection_leakage(document: Mapping[str, Any]) -> None:
    serialized = json.dumps(document, ensure_ascii=False, sort_keys=True).lower()
    forbidden = (
        "control",
        "defect",
        "changetarget",
        "projecttarget",
        "change_target",
        "project_target",
        "hidden_variant",
        "expected_result",
        "expected_outcome",
        "state_loss",
        "locally_supported",
        "locally_rejected",
        "non_accountable",
        "oracle",
        "source-rich",
        "mapping-release",
    )
    if any(term in serialized for term in forbidden):
        raise CandidateVerificationError("candidate_projection_leakage")


def _walk_files(root: Path) -> set[str]:
    files: set[str] = set()
    try:
        for current, directories, names in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            retained: list[str] = []
            for name in sorted(directories):
                path = current_path / name
                if path.is_symlink():
                    raise CandidateVerificationError("candidate_artifact_invalid")
                retained.append(name)
            directories[:] = retained
            for name in sorted(names):
                path = current_path / name
                if path.is_symlink() or not path.is_file():
                    raise CandidateVerificationError("candidate_artifact_invalid")
                files.add(path.relative_to(root).as_posix())
    except CandidateVerificationError:
        raise
    except OSError:
        raise CandidateVerificationError("candidate_root_unavailable") from None
    return files


def verify_candidate_inputs(candidate_root: str | Path) -> CandidateInputs:
    """Validate the complete checked-in V1 public-input set.

    This function only reads ``candidate_root``.  It does not create a stage,
    invoke a command, mutate source, or contact a device.
    """

    try:
        root = Path(candidate_root).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        raise CandidateVerificationError("candidate_root_unavailable") from None
    if not root.is_dir():
        raise CandidateVerificationError("candidate_root_unavailable")
    manifest_path = root / CANDIDATE_MANIFEST_FILENAME
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise CandidateVerificationError("candidate_manifest_missing")
    try:
        manifest_raw = manifest_path.read_bytes()
    except OSError:
        raise CandidateVerificationError("candidate_manifest_unreadable") from None
    manifest = _parse_document(manifest_raw, manifest_path)
    _require_exact_fields(manifest, _CANDIDATE_FIELDS)
    if manifest["schema_version"] != SCHEMA_VERSION:
        raise CandidateVerificationError("candidate_schema_version_mismatch")
    if manifest["document_kind"] != "runtime_calibration_candidate_manifest":
        raise CandidateVerificationError("candidate_document_kind_mismatch")
    if manifest["family_id"] != FAMILY_ID:
        raise CandidateVerificationError("candidate_family_identity_mismatch")
    if manifest["family_version"] != FAMILY_VERSION:
        raise CandidateVerificationError("candidate_input_version_mismatch")
    if manifest["status"] != "candidate_frozen":
        raise CandidateVerificationError("candidate_input_contradictory")
    if manifest["claim_boundary_ref"] != "claim-boundary.json":
        raise CandidateVerificationError("candidate_claim_boundary_mismatch")
    if manifest["identity_sha256"] != canonical_sha256(_without_identity(manifest)):
        raise CandidateVerificationError("candidate_manifest_identity_mismatch")
    required_kinds = manifest["required_artifact_kinds"]
    if tuple(required_kinds) != EXPECTED_ARTIFACT_KINDS:
        raise CandidateVerificationError("candidate_artifact_set_mismatch")
    raw_entries = manifest["artifacts"]
    if not isinstance(raw_entries, list) or len(raw_entries) != len(EXPECTED_ARTIFACT_KINDS):
        raise CandidateVerificationError("candidate_artifact_set_mismatch")
    entries = tuple(_artifact_entry(item) for item in raw_entries)
    if (
        tuple(entry.kind for entry in entries) != EXPECTED_ARTIFACT_KINDS
        or tuple(entry.path for entry in entries) != EXPECTED_ARTIFACT_PATHS
    ):
        raise CandidateVerificationError("candidate_artifact_set_mismatch")
    if len({entry.path for entry in entries}) != len(entries):
        raise CandidateVerificationError("candidate_duplicate_input")
    expected_files = {CANDIDATE_MANIFEST_FILENAME, *(entry.path for entry in entries)}
    actual_files = _walk_files(root)
    if actual_files - expected_files:
        raise CandidateVerificationError("candidate_extra_input")
    if expected_files - actual_files:
        raise CandidateVerificationError("candidate_missing_input")

    by_path = {entry.path: entry for entry in entries}
    loaded: dict[str, _LoadedDocument] = {}
    for entry in entries:
        loaded[entry.path] = _load_document(root, entry.path)
        item = loaded[entry.path]
        if item.raw_sha256 != entry.sha256:
            raise CandidateVerificationError("candidate_artifact_digest_mismatch")
        if item.canonical_sha256 != entry.canonical_sha256:
            raise CandidateVerificationError("candidate_canonical_digest_mismatch")

    family = loaded["family-manifest.json"].document
    source_pair = loaded["source-pair.json"].document
    discovery = loaded["discovery-commitments.json"].document
    claim = loaded["claim-boundary.json"].document
    _validate_family_manifest(family, by_path)
    _validate_source_pair(source_pair)
    _validate_discovery_commitments(discovery)
    _validate_claim_boundary(claim)
    schema_documents: dict[str, Mapping[str, Any]] = {}
    for contract in _SCHEMA_CONTRACTS:
        path = f"schemas/{contract}.schema.json"
        _validate_schema_document(loaded[path].document, contract)
        schema_documents[contract] = loaded[path].document

    _validate_against_schema(family, schema_documents["family_manifest"])
    _validate_against_schema(source_pair, schema_documents["source_pair"])
    _validate_against_schema(discovery, schema_documents["discovery_commitments"])
    _validate_against_schema(claim, schema_documents["claim_boundary"])

    lane_file_map: dict[str, dict[str, str]] = {}
    for number, (lane_id, directory) in enumerate(zip(LANE_IDS, LANE_DIRECTORIES), start=1):
        lane_file_map[lane_id] = {
            "projection": f"runtime/lanes/{directory}/projection.json",
            "driver_plan": f"runtime/lanes/{directory}/driver-plan.json",
            "recipe": f"runtime/lanes/{directory}/recipe.json",
            "run_spec": f"runtime/lanes/{directory}/run-spec.yaml",
        }
        paths = lane_file_map[lane_id]
        _validate_against_schema(
            loaded[paths["run_spec"]].document,
            schema_documents["run_spec"],
        )
        _validate_against_schema(
            loaded[paths["driver_plan"]].document,
            schema_documents["driver_plan"],
        )
        _validate_against_schema(
            loaded[paths["recipe"]].document,
            schema_documents["recipe"],
        )
        _validate_against_schema(
            loaded[paths["projection"]].document,
            schema_documents["projection"],
        )
        _validate_run_spec(loaded[paths["run_spec"]].document, lane_id)
        _validate_plan(
            loaded[paths["driver_plan"]].document,
            lane_id,
            paths["run_spec"],
            loaded[paths["run_spec"]].canonical_sha256,
        )
        _validate_recipe(loaded[paths["recipe"]].document, lane_id)
        _validate_projection(loaded[paths["projection"]].document, lane_id, paths)

    for lane in family["lane_files"]:
        if lane["lane_id"] not in lane_file_map:
            raise CandidateVerificationError("candidate_lane_identity_mismatch")
    return CandidateInputs(
        root=root,
        family_id=FAMILY_ID,
        family_version=FAMILY_VERSION,
        candidate_identity_sha256=manifest["identity_sha256"],
        manifest_sha256=_sha256_bytes(manifest_raw),
        canonical_manifest_sha256=canonical_sha256(manifest),
        claim_boundary=claim["claim_boundary_id"],
        artifacts=tuple(
            ArtifactDigest(
                kind=entry.kind,
                path=entry.path,
                sha256=entry.sha256,
                canonical_sha256=entry.canonical_sha256,
            )
            for entry in entries
        ),
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _encoded_receipt(document: Mapping[str, Any]) -> bytes:
    try:
        return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        )
    except (TypeError, ValueError) as error:
        raise StageReceiptError("stage_receipt_encoding_failed") from error


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise StageReceiptError("stage_receipt_durability_failed") from error


def _write_exclusive_json(path: Path, document: Mapping[str, Any]) -> str:
    payload = _encoded_receipt(document)
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary_path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path)
        _fsync_directory(path.parent)
    except FileExistsError as error:
        raise StageReceiptError("stage_receipt_already_exists") from error
    except OSError as error:
        raise StageReceiptError("stage_receipt_write_failed") from error
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError as error:
            raise StageReceiptError("stage_receipt_cleanup_failed") from error
    return _sha256_bytes(payload)


def _stage_identity(document: Mapping[str, Any], field: str) -> str:
    value = dict(document)
    value.pop(field, None)
    return canonical_sha256(value)


def _prepare_output_root(candidate_root: str | Path, output_root: str | Path) -> Path:
    candidate = Path(candidate_root).expanduser().resolve()
    output = Path(output_root).expanduser().resolve()
    try:
        output.relative_to(candidate)
        overlaps = True
    except ValueError:
        overlaps = False
    if overlaps or output == candidate:
        raise StageReceiptError("stage_output_overlaps_candidate")
    try:
        if output.exists():
            if not output.is_dir() or any(output.iterdir()):
                raise StageReceiptError("stage_output_root_not_empty")
        else:
            output.mkdir(parents=True, exist_ok=False)
    except StageReceiptError:
        raise
    except OSError as error:
        raise StageReceiptError("stage_output_root_unavailable") from error
    return output


def _start_receipt(candidate_root: str | Path, output_root: Path) -> tuple[dict[str, Any], str]:
    document: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": "verify-candidate",
        "status": "started",
        "candidate_root": str(Path(candidate_root).expanduser().resolve()),
        "output_root": str(output_root),
        "claim_boundary": CANDIDATE_CLAIM_BOUNDARY,
        "started_at": _utc_now(),
    }
    document["start_identity_sha256"] = _stage_identity(document, "start_identity_sha256")
    digest = _write_exclusive_json(output_root / "stage-start.json", document)
    return document, digest


def _terminal_receipt(
    *,
    result: CandidateVerificationReceipt,
    start_digest: str,
) -> tuple[dict[str, Any], str]:
    document = result.to_dict()
    document["start_receipt_sha256"] = start_digest
    document["finished_at"] = _utc_now()
    document["terminal_identity_sha256"] = _stage_identity(
        document, "terminal_identity_sha256"
    )
    digest = _write_exclusive_json(result.output_root / "stage-terminal.json", document)
    return document, digest


def verify_candidate(
    candidate_root: str | Path,
    output_root: str | Path,
) -> CandidateVerificationReceipt:
    """Verify V1 inputs and durably record an accepted or rejected stage.

    The output directory must be fresh and separate from the candidate.  A
    ``KeyboardInterrupt`` or process termination after ``stage-start.json``
    intentionally leaves no terminal receipt; :func:`stage_status` then
    reports that invocation as ``abandoned`` and a later invocation cannot
    resume it.
    """

    output = _prepare_output_root(candidate_root, output_root)
    _start_document, start_digest = _start_receipt(candidate_root, output)
    try:
        inputs = verify_candidate_inputs(candidate_root)
        result = CandidateVerificationReceipt(
            accepted=True,
            candidate_root=inputs.root,
            family_id=inputs.family_id,
            family_version=inputs.family_version,
            candidate_identity_sha256=inputs.candidate_identity_sha256,
            manifest_sha256=inputs.manifest_sha256,
            canonical_manifest_sha256=inputs.canonical_manifest_sha256,
            claim_boundary=inputs.claim_boundary,
            artifact_count=len(inputs.artifacts),
            artifacts=inputs.artifacts,
            artifact_inventory_sha256=inputs.artifact_inventory_sha256,
            reason=None,
            output_root=output,
            start_receipt_sha256=start_digest,
            terminal_identity_sha256="",
        )
    except CandidateVerificationError as error:
        result = CandidateVerificationReceipt(
            accepted=False,
            candidate_root=Path(candidate_root).expanduser().resolve(),
            family_id=None,
            family_version=None,
            candidate_identity_sha256=None,
            manifest_sha256=None,
            canonical_manifest_sha256=None,
            claim_boundary=CANDIDATE_CLAIM_BOUNDARY,
            artifact_count=0,
            artifacts=(),
            artifact_inventory_sha256=None,
            reason=error.code,
            output_root=output,
            start_receipt_sha256=start_digest,
            terminal_identity_sha256="",
        )
    except Exception:  # noqa: BLE001
        # Candidate files are untrusted input; every ordinary validator failure
        # still receives a stable terminal receipt.
        result = CandidateVerificationReceipt(
            accepted=False,
            candidate_root=Path(candidate_root).expanduser().resolve(),
            family_id=None,
            family_version=None,
            candidate_identity_sha256=None,
            manifest_sha256=None,
            canonical_manifest_sha256=None,
            claim_boundary=CANDIDATE_CLAIM_BOUNDARY,
            artifact_count=0,
            artifacts=(),
            artifact_inventory_sha256=None,
            reason="candidate_verification_failed",
            output_root=output,
            start_receipt_sha256=start_digest,
            terminal_identity_sha256="",
        )
    terminal, _terminal_digest = _terminal_receipt(
        result=result,
        start_digest=start_digest,
    )
    finalized = CandidateVerificationReceipt(
        accepted=result.accepted,
        candidate_root=result.candidate_root,
        family_id=result.family_id,
        family_version=result.family_version,
        candidate_identity_sha256=result.candidate_identity_sha256,
        manifest_sha256=result.manifest_sha256,
        canonical_manifest_sha256=result.canonical_manifest_sha256,
        claim_boundary=result.claim_boundary,
        artifact_count=result.artifact_count,
        artifacts=result.artifacts,
        artifact_inventory_sha256=result.artifact_inventory_sha256,
        reason=result.reason,
        output_root=output,
        start_receipt_sha256=start_digest,
        terminal_identity_sha256=terminal["terminal_identity_sha256"],
    )
    return finalized


def _load_receipt(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError:
        raise StageReceiptError("stage_receipt_unreadable") from None
    document = _parse_document(raw, path)
    return document, _sha256_bytes(raw)


def _validate_stage_start(document: Mapping[str, Any], output_root: Path) -> None:
    _require_exact_fields(document, _START_RECEIPT_FIELDS)
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["stage"] != "verify-candidate"
        or document["status"] != "started"
        or document["claim_boundary"] != CANDIDATE_CLAIM_BOUNDARY
        or document["output_root"] != str(output_root)
    ):
        raise CandidateVerificationError("stage_receipt_invalid")
    for field in ("candidate_root", "started_at", "start_identity_sha256"):
        if not isinstance(document[field], str) or not document[field]:
            raise CandidateVerificationError("stage_receipt_invalid")
    if not Path(document["candidate_root"]).is_absolute():
        raise CandidateVerificationError("stage_receipt_invalid")
    if _SHA256.fullmatch(document["start_identity_sha256"]) is None:
        raise CandidateVerificationError("stage_receipt_invalid")
    if document["start_identity_sha256"] != _stage_identity(
        document, "start_identity_sha256"
    ):
        raise CandidateVerificationError("stage_receipt_invalid")


def _validate_stage_terminal(
    document: Mapping[str, Any],
    output_root: Path,
    start: Mapping[str, Any],
    start_digest: str,
) -> str:
    _require_exact_fields(document, _TERMINAL_RECEIPT_FIELDS)
    if (
        document["schema_version"] != SCHEMA_VERSION
        or document["stage"] != "verify-candidate"
        or document["claim_boundary"] != CANDIDATE_CLAIM_BOUNDARY
        or document["candidate_root"] != start["candidate_root"]
        or document["output_root"] != str(output_root)
        or document["start_receipt_sha256"] != start_digest
        or document["status"] not in {"accepted", "rejected"}
    ):
        raise CandidateVerificationError("stage_receipt_invalid")
    if not isinstance(document["candidate_root"], str) or not Path(
        document["candidate_root"]
    ).is_absolute():
        raise CandidateVerificationError("stage_receipt_invalid")
    if not isinstance(document["finished_at"], str) or not document["finished_at"]:
        raise CandidateVerificationError("stage_receipt_invalid")
    if _SHA256.fullmatch(document["start_receipt_sha256"]) is None:
        raise CandidateVerificationError("stage_receipt_invalid")
    if _SHA256.fullmatch(document["terminal_identity_sha256"]) is None:
        raise CandidateVerificationError("stage_receipt_invalid")
    if document["terminal_identity_sha256"] != _stage_identity(
        document, "terminal_identity_sha256"
    ):
        raise CandidateVerificationError("stage_receipt_invalid")

    if document["status"] == "accepted":
        if (
            document["family_id"] != FAMILY_ID
            or document["family_version"] != FAMILY_VERSION
            or document["claim_boundary"] != CANDIDATE_CLAIM_BOUNDARY
            or document["reason"] is not None
            or not isinstance(document["artifacts"], list)
            or document["artifact_count"] != len(EXPECTED_ARTIFACT_KINDS)
        ):
            raise CandidateVerificationError("stage_receipt_invalid")
        for field in (
            "candidate_identity_sha256",
            "manifest_sha256",
            "canonical_manifest_sha256",
            "artifact_inventory_sha256",
        ):
            if _SHA256.fullmatch(document[field]) is None:
                raise CandidateVerificationError("stage_receipt_invalid")
        if len(document["artifacts"]) != len(EXPECTED_ARTIFACT_KINDS):
            raise CandidateVerificationError("stage_receipt_invalid")
        entries = tuple(_artifact_entry(item) for item in document["artifacts"])
        if (
            tuple(entry.kind for entry in entries) != EXPECTED_ARTIFACT_KINDS
            or tuple(entry.path for entry in entries) != EXPECTED_ARTIFACT_PATHS
        ):
            raise CandidateVerificationError("stage_receipt_invalid")
        if document["artifact_inventory_sha256"] != _sha256_bytes(
            _canonical_json_bytes([entry.to_dict() for entry in entries])
        ):
            raise CandidateVerificationError("stage_receipt_invalid")
    else:
        if (
            document["family_id"] is not None
            or document["family_version"] is not None
            or document["candidate_identity_sha256"] is not None
            or document["manifest_sha256"] is not None
            or document["canonical_manifest_sha256"] is not None
            or document["artifact_count"] != 0
            or document["artifacts"] != []
            or document["artifact_inventory_sha256"] is not None
            or not isinstance(document["reason"], str)
            or not document["reason"]
        ):
            raise CandidateVerificationError("stage_receipt_invalid")
    return str(document["status"])


def stage_status(output_root: str | Path) -> str:
    """Return ``absent``, ``started``, ``abandoned``, ``accepted``, rejected, or invalid."""

    root = Path(output_root).expanduser().resolve()
    start_path = root / "stage-start.json"
    terminal_path = root / "stage-terminal.json"
    if start_path.is_symlink():
        return "invalid"
    if not start_path.is_file():
        return "absent"
    try:
        start, start_digest = _load_receipt(start_path)
        _validate_stage_start(start, root)
        if terminal_path.is_symlink():
            return "invalid"
        if not terminal_path.is_file():
            return "abandoned"
        terminal, _ = _load_receipt(terminal_path)
        return _validate_stage_terminal(terminal, root, start, start_digest)
    except (CandidateVerificationError, StageReceiptError, OSError, TypeError, ValueError):
        return "invalid"


def is_stage_abandoned(output_root: str | Path) -> bool:
    """Return whether a started stage lacks a terminal receipt."""

    return stage_status(output_root) == "abandoned"


def is_candidate_accepted(output_root: str | Path) -> bool:
    """Return true only for a structurally valid terminal accepted receipt."""

    return stage_status(output_root) == "accepted"


def _default_candidate_root() -> Path:
    return Path(__file__).resolve().parents[3] / "bench/runtime-calibration/opencalc-input-save-enabled-v1"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m aiverify.bench.runtime_calibration",
        description="Verify the frozen OpenCalc Runtime Calibration V1 inputs.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser(
        "verify-candidate",
        help="verify the complete V1 public-input set and write stage receipts",
    )
    verify.add_argument(
        "candidate_root_positional",
        nargs="?",
        help="candidate root (defaults to the bundled OpenCalc V1 candidate)",
    )
    verify.add_argument(
        "--candidate-root",
        "--input-root",
        dest="candidate_root_option",
        help="candidate root; mutually exclusive with the positional root",
    )
    verify.add_argument(
        "--output-root",
        required=True,
        help="new empty directory for stage-start.json and stage-terminal.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command != "verify-candidate":
        parser.error("unsupported command")
    if args.candidate_root_positional and args.candidate_root_option:
        parser.error("candidate root may be supplied once")
    candidate_root = (
        args.candidate_root_option
        or args.candidate_root_positional
        or str(_default_candidate_root())
    )
    try:
        receipt = verify_candidate(candidate_root, args.output_root)
    except StageReceiptError as error:
        print(error.code, file=sys.stderr)
        return 2
    print(json.dumps(receipt.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if receipt.accepted else 1


__all__ = [
    "CANDIDATE_CLAIM_BOUNDARY",
    "EXPECTED_ARTIFACT_KINDS",
    "EXPECTED_ARTIFACT_PATHS",
    "FAMILY_ID",
    "FAMILY_VERSION",
    "CandidateInputs",
    "CandidateVerificationError",
    "CandidateVerificationReceipt",
    "canonical_json_bytes",
    "canonical_sha256",
    "is_candidate_accepted",
    "is_stage_abandoned",
    "main",
    "stage_status",
    "verify_candidate",
    "verify_candidate_inputs",
]


if __name__ == "__main__":
    raise SystemExit(main())
