"""Atomic, auditor-side release of the OpenCalc four-lane runtime mapping.

The discovery module deliberately produces two source-rich packages and two
blind projections at a time.  This module is the only seam that can combine
those results into the frozen four-cell family.  Its release is an auditor
artifact: source meaning is available to a source authority and to the final
reducer, but there is no driver-facing serializer for the released meaning.

The implementation is intentionally conservative.  Every public constructor
rechecks the fixed lane matrix, every persisted identity is recomputable, and
the output file is created with an exclusive hard-link commit after all
validation has completed.  A changed candidate, discovery result, lane, or
existing output therefore fails closed instead of replacing a release.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn

import yaml

from aiverify.bench import opencalc_discovery as discovery
from aiverify.bench import runtime_calibration
from aiverify.runner.admission import SourceAuthority

SCHEMA_VERSION = runtime_calibration.SCHEMA_VERSION
FAMILY_ID = runtime_calibration.FAMILY_ID
FAMILY_VERSION = runtime_calibration.FAMILY_VERSION

RUNTIME_MAPPING_RELEASE_ID = "opencalc-runtime-mapping-release-v1"
RUNTIME_MAPPING_RELEASE_FILENAME = "mapping-release.json"
RUNTIME_MAPPING_CLAIM_BOUNDARY = "local_runtime_mapping_release_only"
SEALED_BLIND_STATUS = "sealed_blind"
MAPPING_RELEASED_STATUS = "mapping_released"

RUNTIME_LANE_IDS = runtime_calibration.LANE_IDS
LANE_IDS = RUNTIME_LANE_IDS
FROZEN_LANE_ORDER = RUNTIME_LANE_IDS

_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_DRIVER_VISIBLE_SHAPE = ("projection", "driver_plan", "recipe", "run_spec")
_SOURCE_REQUEST_MATERIALIZATION_KINDS = {
    "change_target_pristine_source",
    "project_target_synthetic_commit",
}


class RuntimeMappingError(runtime_calibration.RuntimeCalibrationError):
    """Base error for the fail-closed Runtime Mapping boundary."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RuntimeMappingReleaseError(RuntimeMappingError):
    """A release or release input was rejected without disclosing details."""


class RuntimeMappingVerificationError(RuntimeMappingError):
    """A previously released mapping no longer verifies."""


def _fail(code: str, *, verification: bool = False) -> NoReturn:
    error_type = RuntimeMappingVerificationError if verification else RuntimeMappingReleaseError
    raise error_type(code)


def _digest(value: Any) -> str:
    return runtime_calibration.canonical_sha256(value)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _required_text(value: Any, code: str = "mapping_schema_mismatch") -> str:
    if not isinstance(value, str) or not value.strip():
        _fail(code)
    return value


def _sha256(value: Any, code: str = "mapping_digest_invalid") -> str:
    text = _required_text(value, code)
    if _HEX_64.fullmatch(text) is None:
        _fail(code)
    return text


def _sha1(value: Any, code: str = "mapping_digest_invalid") -> str:
    text = _required_text(value, code)
    if _HEX_40.fullmatch(text) is None:
        _fail(code)
    return text


def _relative_path(value: Any, code: str = "mapping_path_invalid") -> str:
    text = _required_text(value, code)
    path = PurePosixPath(text)
    if (
        "\\" in text
        or path.is_absolute()
        or path.as_posix() != text
        or not path.parts
        or any(part in {"", ".", "..", ".git"} for part in path.parts)
    ):
        _fail(code)
    return text


def _absolute_path(value: Any, code: str = "mapping_path_invalid") -> str:
    text = _required_text(value, code)
    path = Path(text).expanduser()
    if not path.is_absolute():
        _fail(code)
    try:
        if str(path.resolve()) != text:
            _fail(code)
    except (OSError, RuntimeError):
        _fail(code)
    return text


def _strict_fields(data: Mapping[str, Any], fields: set[str], code: str) -> None:
    if set(data) != fields:
        _fail(code)


def _string_tuple(value: Any, code: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        _fail(code)
    result = tuple(value)
    if not allow_empty and not result:
        _fail(code)
    if any(not isinstance(item, str) or not item.strip() for item in result):
        _fail(code)
    return result


def _meaning_for_lane(lane_id: str) -> RuntimeLaneMeaning:
    for meaning in RUNTIME_LANE_MEANINGS:
        if meaning.lane_id == lane_id:
            return meaning
    _fail("mapping_lane_identity_mismatch")


@dataclass(frozen=True)
class RuntimeLaneMeaning:
    """The one frozen semantic cell represented by an opaque lane."""

    lane_id: str
    target_kind: str
    variant: str

    def __post_init__(self) -> None:
        expected = {
            "ocrc-v1-lane-01": ("ChangeTarget", "control"),
            "ocrc-v1-lane-02": ("ChangeTarget", "defect"),
            "ocrc-v1-lane-03": ("ProjectTarget", "control"),
            "ocrc-v1-lane-04": ("ProjectTarget", "defect"),
        }.get(self.lane_id)
        if expected is None or (self.target_kind, self.variant) != expected:
            _fail("mapping_lane_meaning_mismatch")

    def to_dict(self) -> dict[str, str]:
        return {
            "lane_id": self.lane_id,
            "target_kind": self.target_kind,
            "variant": self.variant,
        }


RUNTIME_LANE_MEANINGS = (
    RuntimeLaneMeaning("ocrc-v1-lane-01", "ChangeTarget", "control"),
    RuntimeLaneMeaning("ocrc-v1-lane-02", "ChangeTarget", "defect"),
    RuntimeLaneMeaning("ocrc-v1-lane-03", "ProjectTarget", "control"),
    RuntimeLaneMeaning("ocrc-v1-lane-04", "ProjectTarget", "defect"),
)


@dataclass(frozen=True)
class RuntimeSourceRequest:
    """Source-only request that a preparation authority may consume.

    This object intentionally contains source meaning.  It is returned only
    through :class:`SourceAuthorityMapping` and never appears in a driver
    projection or deterministic-driver request.
    """

    request_id: str
    candidate_identity_sha256: str
    candidate_manifest_sha256: str
    candidate_artifact_inventory_sha256: str
    lane_id: str
    target_kind: str
    variant: str
    catalog_id: str
    package_id: str
    target_id: str
    source_id: str
    source_origin: str
    baseline_commit: str
    baseline_tree_sha256: str
    baseline_archive_sha256: str
    source_commit: str
    source_tree_sha256: str
    materialized_tree_sha256: str
    worktree_path: str
    target_path: str
    target_file_sha256: str
    anchor_identity_sha256: str
    context_acquisition_identity_sha256: str
    discovery_materialization_identity_sha256: str
    campaign_identity_sha256: str
    patch_ref: str
    patch_sha256: str
    patch_format: str
    materialization_kind: str
    materialization_receipt_identity_sha256: str | None
    result_diff_sha256: str | None
    scope: tuple[str, ...] | None
    discovery_budget: int | None
    source_package_identity_sha256: str
    discovery_result_identity_sha256: str
    leakage_audit_identity_sha256: str

    def __post_init__(self) -> None:
        meaning = _meaning_for_lane(self.lane_id)
        if (self.target_kind, self.variant) != (meaning.target_kind, meaning.variant):
            _fail("mapping_source_request_meaning_mismatch")
        for field_name in (
            "request_id",
            "catalog_id",
            "package_id",
            "target_id",
            "source_id",
            "source_origin",
            "patch_format",
            "materialization_kind",
        ):
            _required_text(getattr(self, field_name))
        for field_name in (
            "baseline_commit",
            "source_commit",
            "materialized_tree_sha256",
        ):
            _sha1(getattr(self, field_name))
        for field_name in (
            "candidate_identity_sha256",
            "candidate_manifest_sha256",
            "candidate_artifact_inventory_sha256",
            "baseline_tree_sha256",
            "baseline_archive_sha256",
            "source_tree_sha256",
            "target_file_sha256",
            "anchor_identity_sha256",
            "context_acquisition_identity_sha256",
            "discovery_materialization_identity_sha256",
            "campaign_identity_sha256",
            "patch_sha256",
            "source_package_identity_sha256",
            "discovery_result_identity_sha256",
            "leakage_audit_identity_sha256",
        ):
            _sha256(getattr(self, field_name))
        _absolute_path(self.worktree_path)
        _relative_path(self.target_path)
        _relative_path(self.patch_ref)
        if self.patch_format != "unified_diff":
            _fail("mapping_source_request_mismatch")
        if self.materialization_kind not in _SOURCE_REQUEST_MATERIALIZATION_KINDS:
            _fail("mapping_source_request_mismatch")
        if self.target_kind == "ChangeTarget":
            if self.materialization_kind != "change_target_pristine_source":
                _fail("mapping_source_request_mismatch")
            if self.source_commit != self.baseline_commit:
                _fail("mapping_source_request_mismatch")
            if self.materialization_receipt_identity_sha256 is not None:
                _fail("mapping_source_request_mismatch")
            if self.result_diff_sha256 is not None:
                _fail("mapping_source_request_mismatch")
            if self.scope is not None or self.discovery_budget is not None:
                _fail("mapping_source_request_mismatch")
        else:
            if self.materialization_kind != "project_target_synthetic_commit":
                _fail("mapping_source_request_mismatch")
            if self.source_commit == self.baseline_commit:
                _fail("mapping_source_request_mismatch")
            if self.materialization_receipt_identity_sha256 is None:
                _fail("mapping_source_request_mismatch")
            _sha256(self.materialization_receipt_identity_sha256)
            if self.result_diff_sha256 is None:
                _fail("mapping_source_request_mismatch")
            _sha256(self.result_diff_sha256)
            if self.scope != discovery.REQUIRED_CONTEXT_PATHS:
                _fail("mapping_source_request_mismatch")
            if self.discovery_budget != discovery.REQUIRED_CONTEXT_BUDGET:
                _fail("mapping_source_request_mismatch")

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "request_id": self.request_id,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "candidate_manifest_sha256": self.candidate_manifest_sha256,
            "candidate_artifact_inventory_sha256": self.candidate_artifact_inventory_sha256,
            "lane_id": self.lane_id,
            "target_kind": self.target_kind,
            "variant": self.variant,
            "catalog_id": self.catalog_id,
            "package_id": self.package_id,
            "target_id": self.target_id,
            "source_id": self.source_id,
            "source_origin": self.source_origin,
            "baseline_commit": self.baseline_commit,
            "baseline_tree_sha256": self.baseline_tree_sha256,
            "baseline_archive_sha256": self.baseline_archive_sha256,
            "source_commit": self.source_commit,
            "source_tree_sha256": self.source_tree_sha256,
            "materialized_tree_sha256": self.materialized_tree_sha256,
            "worktree_path": self.worktree_path,
            "target_path": self.target_path,
            "target_file_sha256": self.target_file_sha256,
            "anchor_identity_sha256": self.anchor_identity_sha256,
            "context_acquisition_identity_sha256": self.context_acquisition_identity_sha256,
            "discovery_materialization_identity_sha256": self.discovery_materialization_identity_sha256,
            "campaign_identity_sha256": self.campaign_identity_sha256,
            "patch_ref": self.patch_ref,
            "patch_sha256": self.patch_sha256,
            "patch_format": self.patch_format,
            "materialization_kind": self.materialization_kind,
            "materialization_receipt_identity_sha256": self.materialization_receipt_identity_sha256,
            "result_diff_sha256": self.result_diff_sha256,
            "scope": list(self.scope) if self.scope is not None else None,
            "discovery_budget": self.discovery_budget,
            "source_package_identity_sha256": self.source_package_identity_sha256,
            "discovery_result_identity_sha256": self.discovery_result_identity_sha256,
            "leakage_audit_identity_sha256": self.leakage_audit_identity_sha256,
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeSourceRequest:
        fields = {
            "schema_version",
            "request_id",
            "candidate_identity_sha256",
            "candidate_manifest_sha256",
            "candidate_artifact_inventory_sha256",
            "lane_id",
            "target_kind",
            "variant",
            "catalog_id",
            "package_id",
            "target_id",
            "source_id",
            "source_origin",
            "baseline_commit",
            "baseline_tree_sha256",
            "baseline_archive_sha256",
            "source_commit",
            "source_tree_sha256",
            "materialized_tree_sha256",
            "worktree_path",
            "target_path",
            "target_file_sha256",
            "anchor_identity_sha256",
            "context_acquisition_identity_sha256",
            "discovery_materialization_identity_sha256",
            "campaign_identity_sha256",
            "patch_ref",
            "patch_sha256",
            "patch_format",
            "materialization_kind",
            "materialization_receipt_identity_sha256",
            "result_diff_sha256",
            "scope",
            "discovery_budget",
            "source_package_identity_sha256",
            "discovery_result_identity_sha256",
            "leakage_audit_identity_sha256",
            "identity_sha256",
        }
        if not isinstance(data, Mapping):
            _fail("mapping_source_request_schema_mismatch")
        _strict_fields(data, fields, "mapping_source_request_schema_mismatch")
        if data.get("schema_version") != SCHEMA_VERSION:
            _fail("mapping_schema_version_mismatch")
        scope = data["scope"]
        parsed_scope = None if scope is None else _string_tuple(scope, "mapping_source_request_schema_mismatch")
        try:
            request = cls(
                request_id=data["request_id"],
                candidate_identity_sha256=data["candidate_identity_sha256"],
                candidate_manifest_sha256=data["candidate_manifest_sha256"],
                candidate_artifact_inventory_sha256=data["candidate_artifact_inventory_sha256"],
                lane_id=data["lane_id"],
                target_kind=data["target_kind"],
                variant=data["variant"],
                catalog_id=data["catalog_id"],
                package_id=data["package_id"],
                target_id=data["target_id"],
                source_id=data["source_id"],
                source_origin=data["source_origin"],
                baseline_commit=data["baseline_commit"],
                baseline_tree_sha256=data["baseline_tree_sha256"],
                baseline_archive_sha256=data["baseline_archive_sha256"],
                source_commit=data["source_commit"],
                source_tree_sha256=data["source_tree_sha256"],
                materialized_tree_sha256=data["materialized_tree_sha256"],
                worktree_path=data["worktree_path"],
                target_path=data["target_path"],
                target_file_sha256=data["target_file_sha256"],
                anchor_identity_sha256=data["anchor_identity_sha256"],
                context_acquisition_identity_sha256=data["context_acquisition_identity_sha256"],
                discovery_materialization_identity_sha256=data["discovery_materialization_identity_sha256"],
                campaign_identity_sha256=data["campaign_identity_sha256"],
                patch_ref=data["patch_ref"],
                patch_sha256=data["patch_sha256"],
                patch_format=data["patch_format"],
                materialization_kind=data["materialization_kind"],
                materialization_receipt_identity_sha256=data[
                    "materialization_receipt_identity_sha256"
                ],
                result_diff_sha256=data["result_diff_sha256"],
                scope=parsed_scope,
                discovery_budget=data["discovery_budget"],
                source_package_identity_sha256=data["source_package_identity_sha256"],
                discovery_result_identity_sha256=data["discovery_result_identity_sha256"],
                leakage_audit_identity_sha256=data["leakage_audit_identity_sha256"],
            )
        except KeyError:
            _fail("mapping_source_request_schema_mismatch")
        if data["identity_sha256"] != request.identity_sha256:
            _fail("mapping_source_request_identity_mismatch")
        return request


@dataclass(frozen=True)
class DiscoveryAdmissionReceipt:
    """Terminal success receipt for one of the four discovery cells."""

    lane_id: str
    target_kind: str
    variant: str
    discovery_result_kind: str
    discovery_result_identity_sha256: str
    package_id: str
    package_identity_sha256: str
    blind_projection_id: str
    blind_projection_identity_sha256: str
    leakage_audit_identity_sha256: str
    status: str = "admitted"

    def __post_init__(self) -> None:
        meaning = _meaning_for_lane(self.lane_id)
        if (self.target_kind, self.variant) != (meaning.target_kind, meaning.variant):
            _fail("mapping_admission_meaning_mismatch")
        expected_result_kind = (
            "ChangeTargetDiscoveryResult"
            if meaning.target_kind == "ChangeTarget"
            else "ProjectTargetDiscoveryResult"
        )
        if self.discovery_result_kind != expected_result_kind:
            _fail("mapping_admission_schema_mismatch")
        for field_name in (
            "discovery_result_identity_sha256",
            "package_identity_sha256",
            "blind_projection_identity_sha256",
            "leakage_audit_identity_sha256",
        ):
            _sha256(getattr(self, field_name))
        for field_name in (
            "package_id",
            "blind_projection_id",
        ):
            _required_text(getattr(self, field_name))
        if self.status != "admitted":
            _fail("mapping_admission_not_terminal")

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "lane_id": self.lane_id,
            "target_kind": self.target_kind,
            "variant": self.variant,
            "discovery_result_kind": self.discovery_result_kind,
            "discovery_result_identity_sha256": self.discovery_result_identity_sha256,
            "package_id": self.package_id,
            "package_identity_sha256": self.package_identity_sha256,
            "blind_projection_id": self.blind_projection_id,
            "blind_projection_identity_sha256": self.blind_projection_identity_sha256,
            "leakage_audit_identity_sha256": self.leakage_audit_identity_sha256,
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DiscoveryAdmissionReceipt:
        fields = {
            "schema_version",
            "status",
            "lane_id",
            "target_kind",
            "variant",
            "discovery_result_kind",
            "discovery_result_identity_sha256",
            "package_id",
            "package_identity_sha256",
            "blind_projection_id",
            "blind_projection_identity_sha256",
            "leakage_audit_identity_sha256",
            "identity_sha256",
        }
        if not isinstance(data, Mapping):
            _fail("mapping_admission_schema_mismatch")
        _strict_fields(data, fields, "mapping_admission_schema_mismatch")
        if data.get("schema_version") != SCHEMA_VERSION:
            _fail("mapping_schema_version_mismatch")
        try:
            receipt = cls(
                lane_id=data["lane_id"],
                target_kind=data["target_kind"],
                variant=data["variant"],
                discovery_result_kind=data["discovery_result_kind"],
                discovery_result_identity_sha256=data["discovery_result_identity_sha256"],
                package_id=data["package_id"],
                package_identity_sha256=data["package_identity_sha256"],
                blind_projection_id=data["blind_projection_id"],
                blind_projection_identity_sha256=data["blind_projection_identity_sha256"],
                leakage_audit_identity_sha256=data["leakage_audit_identity_sha256"],
                status=data["status"],
            )
        except KeyError:
            _fail("mapping_admission_schema_mismatch")
        if data["identity_sha256"] != receipt.identity_sha256:
            _fail("mapping_admission_identity_mismatch")
        return receipt


@dataclass(frozen=True)
class RuntimeLaneBinding:
    """One complete cross-binding between source, discovery, and lane inputs."""

    lane_id: str
    target_kind: str
    variant: str
    catalog_id: str
    package_id: str
    source_package_identity_sha256: str
    discovery_result_identity_sha256: str
    leakage_audit_identity_sha256: str
    blind_projection_id: str
    blind_projection_identity_sha256: str
    candidate_projection_id: str
    projection_path: str
    driver_plan_path: str
    recipe_path: str
    run_spec_path: str
    projection_raw_sha256: str
    driver_plan_raw_sha256: str
    recipe_raw_sha256: str
    run_spec_raw_sha256: str
    projection_canonical_sha256: str
    driver_plan_canonical_sha256: str
    recipe_canonical_sha256: str
    run_spec_canonical_sha256: str
    setup_plan_canonical_sha256: str
    projection_shape: tuple[str, ...]
    driver_plan_shape: tuple[str, ...]
    recipe_shape: tuple[str, ...]
    run_spec_shape: tuple[str, ...]
    source_request: RuntimeSourceRequest

    def __post_init__(self) -> None:
        meaning = _meaning_for_lane(self.lane_id)
        if (self.target_kind, self.variant) != (meaning.target_kind, meaning.variant):
            _fail("mapping_lane_meaning_mismatch")
        for field_name in (
            "catalog_id",
            "package_id",
            "blind_projection_id",
            "candidate_projection_id",
        ):
            _required_text(getattr(self, field_name))
        for field_name in (
            "source_package_identity_sha256",
            "discovery_result_identity_sha256",
            "leakage_audit_identity_sha256",
            "blind_projection_identity_sha256",
            "projection_raw_sha256",
            "driver_plan_raw_sha256",
            "recipe_raw_sha256",
            "run_spec_raw_sha256",
            "projection_canonical_sha256",
            "driver_plan_canonical_sha256",
            "recipe_canonical_sha256",
            "run_spec_canonical_sha256",
            "setup_plan_canonical_sha256",
        ):
            _sha256(getattr(self, field_name))
        expected_paths = _lane_paths(self.lane_id)
        if (
            self.projection_path,
            self.driver_plan_path,
            self.recipe_path,
            self.run_spec_path,
        ) != (
            expected_paths["projection"],
            expected_paths["driver_plan"],
            expected_paths["recipe"],
            expected_paths["run_spec"],
        ):
            _fail("mapping_lane_path_mismatch")
        for field_name in (
            "projection_shape",
            "driver_plan_shape",
            "recipe_shape",
            "run_spec_shape",
        ):
            value = _string_tuple(getattr(self, field_name), "mapping_driver_shape_mismatch")
            if value != getattr(self, field_name):
                _fail("mapping_driver_shape_mismatch")
        if not self.projection_shape or not self.driver_plan_shape:
            _fail("mapping_driver_shape_mismatch")
        if not isinstance(self.source_request, RuntimeSourceRequest):
            _fail("mapping_source_request_mismatch")
        if (
            self.source_request.lane_id,
            self.source_request.target_kind,
            self.source_request.variant,
            self.source_request.package_id,
            self.source_request.source_package_identity_sha256,
            self.source_request.discovery_result_identity_sha256,
            self.source_request.leakage_audit_identity_sha256,
        ) != (
            self.lane_id,
            self.target_kind,
            self.variant,
            self.package_id,
            self.source_package_identity_sha256,
            self.discovery_result_identity_sha256,
            self.leakage_audit_identity_sha256,
        ):
            _fail("mapping_source_request_mismatch")
        if self.candidate_projection_id != f"{self.lane_id}-projection":
            _fail("mapping_candidate_projection_mismatch")

    @property
    def projection_id(self) -> str:
        """The opaque projection ID in the checked-in runtime input."""

        return self.candidate_projection_id

    @property
    def blind_runtime_projection_id(self) -> str:
        return self.blind_projection_id

    @property
    def projection_commitment(self) -> str:
        return self.projection_raw_sha256

    @property
    def driver_plan_commitment(self) -> str:
        return self.driver_plan_raw_sha256

    @property
    def recipe_commitment(self) -> str:
        return self.recipe_raw_sha256

    @property
    def run_spec_commitment(self) -> str:
        return self.run_spec_raw_sha256

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "lane_id": self.lane_id,
            "target_kind": self.target_kind,
            "variant": self.variant,
            "catalog_id": self.catalog_id,
            "package_id": self.package_id,
            "source_package_identity_sha256": self.source_package_identity_sha256,
            "discovery_result_identity_sha256": self.discovery_result_identity_sha256,
            "leakage_audit_identity_sha256": self.leakage_audit_identity_sha256,
            "blind_projection": {
                "projection_id": self.blind_projection_id,
                "identity_sha256": self.blind_projection_identity_sha256,
            },
            "candidate_projection": {
                "projection_id": self.candidate_projection_id,
                "path": self.projection_path,
                "raw_sha256": self.projection_raw_sha256,
                "canonical_sha256": self.projection_canonical_sha256,
                "shape": list(self.projection_shape),
            },
            "driver_plan": {
                "path": self.driver_plan_path,
                "raw_sha256": self.driver_plan_raw_sha256,
                "canonical_sha256": self.driver_plan_canonical_sha256,
                "shape": list(self.driver_plan_shape),
            },
            "recipe": {
                "path": self.recipe_path,
                "raw_sha256": self.recipe_raw_sha256,
                "canonical_sha256": self.recipe_canonical_sha256,
                "shape": list(self.recipe_shape),
            },
            "run_spec": {
                "path": self.run_spec_path,
                "raw_sha256": self.run_spec_raw_sha256,
                "canonical_sha256": self.run_spec_canonical_sha256,
                "shape": list(self.run_spec_shape),
            },
            "setup_plan_canonical_sha256": self.setup_plan_canonical_sha256,
            "source_request": self.source_request.to_dict(),
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeLaneBinding:
        fields = {
            "schema_version",
            "lane_id",
            "target_kind",
            "variant",
            "catalog_id",
            "package_id",
            "source_package_identity_sha256",
            "discovery_result_identity_sha256",
            "leakage_audit_identity_sha256",
            "blind_projection",
            "candidate_projection",
            "driver_plan",
            "recipe",
            "run_spec",
            "setup_plan_canonical_sha256",
            "source_request",
            "identity_sha256",
        }
        if not isinstance(data, Mapping):
            _fail("mapping_lane_schema_mismatch")
        _strict_fields(data, fields, "mapping_lane_schema_mismatch")
        if data.get("schema_version") != SCHEMA_VERSION:
            _fail("mapping_schema_version_mismatch")
        projection = _mapping(data.get("candidate_projection"), "mapping_lane_schema_mismatch")
        blind = _mapping(data.get("blind_projection"), "mapping_lane_schema_mismatch")
        plan = _mapping(data.get("driver_plan"), "mapping_lane_schema_mismatch")
        recipe = _mapping(data.get("recipe"), "mapping_lane_schema_mismatch")
        run_spec = _mapping(data.get("run_spec"), "mapping_lane_schema_mismatch")
        for nested, nested_fields in (
            (blind, {"projection_id", "identity_sha256"}),
            (
                projection,
                {"projection_id", "path", "raw_sha256", "canonical_sha256", "shape"},
            ),
            (plan, {"path", "raw_sha256", "canonical_sha256", "shape"}),
            (recipe, {"path", "raw_sha256", "canonical_sha256", "shape"}),
            (run_spec, {"path", "raw_sha256", "canonical_sha256", "shape"}),
        ):
            _strict_fields(nested, nested_fields, "mapping_lane_schema_mismatch")
        try:
            lane = cls(
                lane_id=data["lane_id"],
                target_kind=data["target_kind"],
                variant=data["variant"],
                catalog_id=data["catalog_id"],
                package_id=data["package_id"],
                source_package_identity_sha256=data["source_package_identity_sha256"],
                discovery_result_identity_sha256=data["discovery_result_identity_sha256"],
                leakage_audit_identity_sha256=data["leakage_audit_identity_sha256"],
                blind_projection_id=blind["projection_id"],
                blind_projection_identity_sha256=blind["identity_sha256"],
                candidate_projection_id=projection["projection_id"],
                projection_path=projection["path"],
                driver_plan_path=plan["path"],
                recipe_path=recipe["path"],
                run_spec_path=run_spec["path"],
                projection_raw_sha256=projection["raw_sha256"],
                driver_plan_raw_sha256=plan["raw_sha256"],
                recipe_raw_sha256=recipe["raw_sha256"],
                run_spec_raw_sha256=run_spec["raw_sha256"],
                projection_canonical_sha256=projection["canonical_sha256"],
                driver_plan_canonical_sha256=plan["canonical_sha256"],
                recipe_canonical_sha256=recipe["canonical_sha256"],
                run_spec_canonical_sha256=run_spec["canonical_sha256"],
                setup_plan_canonical_sha256=data["setup_plan_canonical_sha256"],
                projection_shape=_string_tuple(projection["shape"], "mapping_lane_schema_mismatch"),
                driver_plan_shape=_string_tuple(plan["shape"], "mapping_lane_schema_mismatch"),
                recipe_shape=_string_tuple(recipe["shape"], "mapping_lane_schema_mismatch"),
                run_spec_shape=_string_tuple(run_spec["shape"], "mapping_lane_schema_mismatch"),
                source_request=RuntimeSourceRequest.from_dict(
                    _mapping(data.get("source_request"), "mapping_lane_schema_mismatch")
                ),
            )
        except KeyError:
            _fail("mapping_lane_schema_mismatch")
        if data["identity_sha256"] != lane.identity_sha256:
            _fail("mapping_lane_identity_mismatch")
        return lane


def _mapping(value: Any, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail(code)
    return value


@dataclass(frozen=True)
class SourceAuthorityVerification:
    """Small receipt returned after an authority accepts released requests."""

    release_id: str
    release_identity_sha256: str
    authority_kind: str
    request_ids: tuple[str, ...]
    status: str = "verified"

    def __post_init__(self) -> None:
        if self.release_id != RUNTIME_MAPPING_RELEASE_ID:
            _fail("mapping_release_identity_mismatch")
        _sha256(self.release_identity_sha256)
        _required_text(self.authority_kind)
        _string_tuple(self.request_ids, "mapping_source_authority_verification_mismatch")
        if self.status != "verified":
            _fail("mapping_source_authority_verification_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "release_id": self.release_id,
            "release_identity_sha256": self.release_identity_sha256,
            "authority_kind": self.authority_kind,
            "request_ids": list(self.request_ids),
        }


@dataclass(frozen=True)
class SourceAuthorityMapping:
    """The source-only view granted to an existing ``SourceAuthority``."""

    release_id: str
    release_identity_sha256: str
    source_requests: tuple[RuntimeSourceRequest, ...]
    status: str = MAPPING_RELEASED_STATUS

    def __post_init__(self) -> None:
        if self.release_id != RUNTIME_MAPPING_RELEASE_ID:
            _fail("mapping_release_identity_mismatch")
        _sha256(self.release_identity_sha256)
        if self.status != MAPPING_RELEASED_STATUS:
            _fail("mapping_release_status_mismatch")
        if not isinstance(self.source_requests, tuple) or len(self.source_requests) != 4:
            _fail("mapping_lane_cardinality_mismatch")
        if any(not isinstance(request, RuntimeSourceRequest) for request in self.source_requests):
            _fail("mapping_source_request_mismatch")
        if tuple(request.lane_id for request in self.source_requests) != RUNTIME_LANE_IDS:
            _fail("mapping_lane_order_mismatch")

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(request.lane_id for request in self.source_requests)

    def request_for_lane(self, lane_id: str) -> RuntimeSourceRequest:
        for request in self.source_requests:
            if request.lane_id == lane_id:
                return request
        _fail("mapping_lane_missing")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "release_id": self.release_id,
            "release_identity_sha256": self.release_identity_sha256,
            "lane_ids": list(self.lane_ids),
            "source_requests": [request.to_dict() for request in self.source_requests],
        }

    def verify_with(
        self,
        authority: SourceAuthority,
    ) -> SourceAuthorityVerification:
        if not isinstance(authority, SourceAuthority):
            _fail("mapping_unauthorized_consumer")
        for request in self.source_requests:
            verifier = getattr(authority, "verify_runtime_source_request", None)
            if callable(verifier):
                try:
                    verifier(request)
                except Exception as error:
                    raise RuntimeMappingVerificationError(
                        "mapping_source_authority_rejected"
                    ) from error
        return SourceAuthorityVerification(
            release_id=self.release_id,
            release_identity_sha256=self.release_identity_sha256,
            authority_kind=type(authority).__name__,
            request_ids=tuple(request.request_id for request in self.source_requests),
        )


@dataclass(frozen=True)
class ReducerLaneBinding:
    """Meaning exposed to the pure reducer after terminal execution."""

    lane_id: str
    target_kind: str
    variant: str
    package_identity_sha256: str
    discovery_result_identity_sha256: str
    blind_projection_identity_sha256: str

    def __post_init__(self) -> None:
        meaning = _meaning_for_lane(self.lane_id)
        if (self.target_kind, self.variant) != (meaning.target_kind, meaning.variant):
            _fail("mapping_reducer_meaning_mismatch")
        for field_name in (
            "package_identity_sha256",
            "discovery_result_identity_sha256",
            "blind_projection_identity_sha256",
        ):
            _sha256(getattr(self, field_name))

    def to_dict(self) -> dict[str, str]:
        return {
            "lane_id": self.lane_id,
            "target_kind": self.target_kind,
            "variant": self.variant,
            "package_identity_sha256": self.package_identity_sha256,
            "discovery_result_identity_sha256": self.discovery_result_identity_sha256,
            "blind_projection_identity_sha256": self.blind_projection_identity_sha256,
        }


@dataclass(frozen=True)
class ReducerMapping:
    """The post-terminal semantic view for a pure reducer."""

    release_id: str
    release_identity_sha256: str
    lanes: tuple[ReducerLaneBinding, ...]
    status: str = MAPPING_RELEASED_STATUS

    def __post_init__(self) -> None:
        if self.release_id != RUNTIME_MAPPING_RELEASE_ID:
            _fail("mapping_release_identity_mismatch")
        _sha256(self.release_identity_sha256)
        if self.status != MAPPING_RELEASED_STATUS:
            _fail("mapping_release_status_mismatch")
        if not isinstance(self.lanes, tuple) or len(self.lanes) != 4:
            _fail("mapping_lane_cardinality_mismatch")
        if tuple(lane.lane_id for lane in self.lanes) != RUNTIME_LANE_IDS:
            _fail("mapping_lane_order_mismatch")

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(lane.lane_id for lane in self.lanes)

    def lane_for(self, lane_id: str) -> ReducerLaneBinding:
        for lane in self.lanes:
            if lane.lane_id == lane_id:
                return lane
        _fail("mapping_lane_missing")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "release_id": self.release_id,
            "release_identity_sha256": self.release_identity_sha256,
            "lane_ids": list(self.lane_ids),
            "lanes": [lane.to_dict() for lane in self.lanes],
        }


class RuntimeReducerAuthority:
    """Marker type for the final no-I/O reducer consumer."""


@dataclass(frozen=True)
class TerminalExecutionEvidence:
    """Typed proof that the reducer is being called after terminal execution."""

    lane_ids: tuple[str, ...]
    terminal_identity_sha256: str
    status: str = "terminal"

    def __post_init__(self) -> None:
        if self.lane_ids != RUNTIME_LANE_IDS:
            _fail("mapping_terminal_lane_order_mismatch")
        _sha256(self.terminal_identity_sha256)
        if self.status != "terminal":
            _fail("mapping_terminal_evidence_required")


RuntimeTerminalExecutionEvidence = TerminalExecutionEvidence


@dataclass(frozen=True)
class RuntimeMappingRelease:
    """The one immutable transition from ``sealed_blind`` to released."""

    release_id: str
    candidate_identity_sha256: str
    candidate_manifest_sha256: str
    candidate_artifact_inventory_sha256: str
    discovery_admissions: tuple[DiscoveryAdmissionReceipt, ...]
    lanes: tuple[RuntimeLaneBinding, ...]
    driver_visible_serialization_sha256: str
    driver_projection_ids: tuple[str, ...]
    driver_visible_shape: tuple[str, ...]
    previous_status: str = SEALED_BLIND_STATUS
    status: str = MAPPING_RELEASED_STATUS
    claim_boundary: str = RUNTIME_MAPPING_CLAIM_BOUNDARY
    family_id: str = FAMILY_ID
    family_version: str = FAMILY_VERSION
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.release_id != RUNTIME_MAPPING_RELEASE_ID:
            _fail("mapping_release_identity_mismatch")
        for field_name in (
            "candidate_identity_sha256",
            "candidate_manifest_sha256",
            "candidate_artifact_inventory_sha256",
            "driver_visible_serialization_sha256",
        ):
            _sha256(getattr(self, field_name))
        if self.family_id != FAMILY_ID or self.family_version != FAMILY_VERSION:
            _fail("mapping_family_mismatch")
        if self.claim_boundary != RUNTIME_MAPPING_CLAIM_BOUNDARY:
            _fail("mapping_claim_boundary_mismatch")
        if self.previous_status != SEALED_BLIND_STATUS or self.status != MAPPING_RELEASED_STATUS:
            _fail("mapping_status_transition_mismatch")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("mapping_schema_version_mismatch")
        if not isinstance(self.discovery_admissions, tuple) or len(self.discovery_admissions) != 4:
            _fail("mapping_admission_cardinality_mismatch")
        if any(
            not isinstance(admission, DiscoveryAdmissionReceipt)
            for admission in self.discovery_admissions
        ):
            _fail("mapping_admission_schema_mismatch")
        if not isinstance(self.lanes, tuple) or len(self.lanes) != 4:
            _fail("mapping_lane_cardinality_mismatch")
        if any(not isinstance(lane, RuntimeLaneBinding) for lane in self.lanes):
            _fail("mapping_lane_schema_mismatch")
        if tuple(item.lane_id for item in self.discovery_admissions) != RUNTIME_LANE_IDS:
            _fail("mapping_admission_order_mismatch")
        if tuple(item.lane_id for item in self.lanes) != RUNTIME_LANE_IDS:
            _fail("mapping_lane_order_mismatch")
        if tuple(item.lane_id for item in self.lanes) != tuple(
            item.lane_id for item in self.discovery_admissions
        ):
            _fail("mapping_admission_order_mismatch")
        if len({item.package_id for item in self.lanes}) != 4:
            _fail("mapping_duplicate_package")
        if len({item.blind_projection_id for item in self.lanes}) != 4:
            _fail("mapping_duplicate_projection")
        if len({item.candidate_projection_id for item in self.lanes}) != 4:
            _fail("mapping_duplicate_projection")
        if self.driver_projection_ids != tuple(
            item.candidate_projection_id for item in self.lanes
        ):
            _fail("mapping_driver_projection_mismatch")
        if self.driver_visible_shape != _DRIVER_VISIBLE_SHAPE:
            _fail("mapping_driver_shape_mismatch")
        if any(
            lane.projection_shape != self.lanes[0].projection_shape
            or lane.driver_plan_shape != self.lanes[0].driver_plan_shape
            or lane.recipe_shape != self.lanes[0].recipe_shape
            or lane.run_spec_shape != self.lanes[0].run_spec_shape
            for lane in self.lanes[1:]
        ):
            _fail("mapping_driver_shape_mismatch")
        for admission, lane in zip(self.discovery_admissions, self.lanes):
            if (
                admission.lane_id,
                admission.target_kind,
                admission.variant,
                admission.package_id,
                admission.package_identity_sha256,
                admission.discovery_result_identity_sha256,
                admission.blind_projection_id,
                admission.blind_projection_identity_sha256,
                admission.leakage_audit_identity_sha256,
            ) != (
                lane.lane_id,
                lane.target_kind,
                lane.variant,
                lane.package_id,
                lane.source_package_identity_sha256,
                lane.discovery_result_identity_sha256,
                lane.blind_projection_id,
                lane.blind_projection_identity_sha256,
                lane.leakage_audit_identity_sha256,
            ):
                _fail("mapping_admission_binding_mismatch")
            request = lane.source_request
            if (
                request.candidate_identity_sha256,
                request.candidate_manifest_sha256,
                request.candidate_artifact_inventory_sha256,
            ) != (
                self.candidate_identity_sha256,
                self.candidate_manifest_sha256,
                self.candidate_artifact_inventory_sha256,
            ):
                _fail("mapping_candidate_identity_mismatch")

    @property
    def lane_ids(self) -> tuple[str, ...]:
        return tuple(lane.lane_id for lane in self.lanes)

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    @property
    def canonical_bytes(self) -> bytes:
        return runtime_calibration.canonical_json_bytes(self.to_dict())

    @property
    def driver_visible(self) -> dict[str, Any]:
        """Return only the opaque, uniform input manifest for a driver."""

        return {
            "projection_ids": list(self.driver_projection_ids),
            "shape": list(self.driver_visible_shape),
            "serialization_sha256": self.driver_visible_serialization_sha256,
        }

    def to_driver_visible(self) -> dict[str, Any]:
        """Expose no source meaning when a caller asks for driver input."""

        return self.driver_visible

    def _identity_dict(self) -> dict[str, Any]:
        return self.to_dict(include_identity=False)

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "document_kind": "runtime_mapping_release",
            "family_id": self.family_id,
            "family_version": self.family_version,
            "release_id": self.release_id,
            "claim_boundary": self.claim_boundary,
            "previous_status": self.previous_status,
            "status": self.status,
            "candidate": {
                "identity_sha256": self.candidate_identity_sha256,
                "manifest_sha256": self.candidate_manifest_sha256,
                "artifact_inventory_sha256": self.candidate_artifact_inventory_sha256,
            },
            "lane_ids": list(self.lane_ids),
            "discovery_admissions": [
                admission.to_dict() for admission in self.discovery_admissions
            ],
            "lanes": [lane.to_dict() for lane in self.lanes],
            "driver_visible": {
                "projection_ids": list(self.driver_projection_ids),
                "shape": list(self.driver_visible_shape),
                "serialization_sha256": self.driver_visible_serialization_sha256,
            },
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RuntimeMappingRelease:
        fields = {
            "schema_version",
            "document_kind",
            "family_id",
            "family_version",
            "release_id",
            "claim_boundary",
            "previous_status",
            "status",
            "candidate",
            "lane_ids",
            "discovery_admissions",
            "lanes",
            "driver_visible",
            "identity_sha256",
        }
        if not isinstance(data, Mapping):
            _fail("mapping_release_schema_mismatch")
        _strict_fields(data, fields, "mapping_release_schema_mismatch")
        if data.get("document_kind") != "runtime_mapping_release":
            _fail("mapping_document_kind_mismatch")
        if data.get("schema_version") != SCHEMA_VERSION:
            _fail("mapping_schema_version_mismatch")
        candidate = _mapping(data.get("candidate"), "mapping_release_schema_mismatch")
        _strict_fields(
            candidate,
            {"identity_sha256", "manifest_sha256", "artifact_inventory_sha256"},
            "mapping_release_schema_mismatch",
        )
        driver = _mapping(data.get("driver_visible"), "mapping_release_schema_mismatch")
        _strict_fields(
            driver,
            {"projection_ids", "shape", "serialization_sha256"},
            "mapping_release_schema_mismatch",
        )
        raw_admissions = data.get("discovery_admissions")
        raw_lanes = data.get("lanes")
        if not isinstance(raw_admissions, list) or not isinstance(raw_lanes, list):
            _fail("mapping_release_schema_mismatch")
        lane_ids = _string_tuple(data.get("lane_ids"), "mapping_release_schema_mismatch")
        if lane_ids != RUNTIME_LANE_IDS:
            _fail("mapping_lane_order_mismatch")
        if not isinstance(driver.get("projection_ids"), list):
            _fail("mapping_release_schema_mismatch")
        try:
            release = cls(
                release_id=data["release_id"],
                candidate_identity_sha256=candidate["identity_sha256"],
                candidate_manifest_sha256=candidate["manifest_sha256"],
                candidate_artifact_inventory_sha256=candidate["artifact_inventory_sha256"],
                discovery_admissions=tuple(
                    DiscoveryAdmissionReceipt.from_dict(_mapping(item, "mapping_release_schema_mismatch"))
                    for item in raw_admissions
                ),
                lanes=tuple(
                    RuntimeLaneBinding.from_dict(_mapping(item, "mapping_release_schema_mismatch"))
                    for item in raw_lanes
                ),
                driver_visible_serialization_sha256=driver["serialization_sha256"],
                driver_projection_ids=_string_tuple(
                    driver["projection_ids"], "mapping_release_schema_mismatch"
                ),
                driver_visible_shape=_string_tuple(driver["shape"], "mapping_release_schema_mismatch"),
                previous_status=data["previous_status"],
                status=data["status"],
                claim_boundary=data["claim_boundary"],
                family_id=data["family_id"],
                family_version=data["family_version"],
                schema_version=data["schema_version"],
            )
        except KeyError:
            _fail("mapping_release_schema_mismatch")
        if data["identity_sha256"] != release.identity_sha256:
            _fail("mapping_release_identity_mismatch")
        return release

    def verify_integrity(self) -> None:
        """Reparse the canonical public form to detect tampering or drift."""

        try:
            restored = RuntimeMappingRelease.from_dict(self.to_dict())
        except RuntimeMappingError as error:
            raise RuntimeMappingVerificationError(error.code) from error
        if restored != self:
            _fail("mapping_release_identity_mismatch", verification=True)

    @classmethod
    def load(cls, path: str | Path) -> RuntimeMappingRelease:
        return load_runtime_mapping_release(path)

    @classmethod
    def from_file(cls, path: str | Path) -> RuntimeMappingRelease:
        return load_runtime_mapping_release(path)

    def consume(
        self,
        consumer: object,
        *,
        terminal_evidence: TerminalExecutionEvidence | None = None,
    ) -> SourceAuthorityMapping | ReducerMapping:
        """Grant meaning only to Source Authority or the terminal reducer."""

        self.verify_integrity()
        if isinstance(consumer, SourceAuthority):
            if terminal_evidence is not None:
                _fail("mapping_consumer_phase_mismatch")
            return SourceAuthorityMapping(
                release_id=self.release_id,
                release_identity_sha256=self.identity_sha256,
                source_requests=tuple(
                    lane.source_request for lane in self.lanes
                ),
            )
        if isinstance(consumer, RuntimeReducerAuthority):
            if not isinstance(terminal_evidence, TerminalExecutionEvidence):
                _fail("mapping_terminal_evidence_required")
            return ReducerMapping(
                release_id=self.release_id,
                release_identity_sha256=self.identity_sha256,
                lanes=tuple(
                    ReducerLaneBinding(
                        lane_id=lane.lane_id,
                        target_kind=lane.target_kind,
                        variant=lane.variant,
                        package_identity_sha256=lane.source_package_identity_sha256,
                        discovery_result_identity_sha256=lane.discovery_result_identity_sha256,
                        blind_projection_identity_sha256=lane.blind_projection_identity_sha256,
                    )
                    for lane in self.lanes
                ),
            )
        _fail("mapping_unauthorized_consumer")

    def for_source_authority(self, authority: SourceAuthority) -> SourceAuthorityMapping:
        result = self.consume(authority)
        if not isinstance(result, SourceAuthorityMapping):
            _fail("mapping_consumer_phase_mismatch")
        return result

    def for_reducer(
        self,
        reducer: RuntimeReducerAuthority,
        *,
        terminal_evidence: TerminalExecutionEvidence,
    ) -> ReducerMapping:
        result = self.consume(reducer, terminal_evidence=terminal_evidence)
        if not isinstance(result, ReducerMapping):
            _fail("mapping_consumer_phase_mismatch")
        return result


def _lane_paths(lane_id: str) -> dict[str, str]:
    if lane_id not in RUNTIME_LANE_IDS:
        _fail("mapping_lane_identity_mismatch")
    number = lane_id[-2:]
    prefix = f"runtime/lanes/lane-{number}"
    return {
        "projection": f"{prefix}/projection.json",
        "driver_plan": f"{prefix}/driver-plan.json",
        "recipe": f"{prefix}/recipe.json",
        "run_spec": f"{prefix}/run-spec.yaml",
    }


def _read_document(candidate: runtime_calibration.CandidateInputs, relative_path: str) -> tuple[dict[str, Any], str, str]:
    path = candidate.root.joinpath(*PurePosixPath(relative_path).parts)
    if path.is_symlink() or not path.is_file():
        _fail("mapping_candidate_input_mismatch")
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8")
        try:
            document = json.loads(text)
        except json.JSONDecodeError:
            document = yaml.safe_load(text)
    except (OSError, UnicodeDecodeError, ValueError, yaml.YAMLError):
        _fail("mapping_candidate_input_mismatch")
    if not isinstance(document, dict):
        _fail("mapping_candidate_input_mismatch")
    raw_sha256 = _sha256_bytes(raw)
    canonical = _digest(document)
    expected = {item.path: item for item in candidate.artifacts}.get(relative_path)
    if expected is None or expected.sha256 != raw_sha256 or expected.canonical_sha256 != canonical:
        _fail("mapping_candidate_input_mismatch")
    return document, raw_sha256, canonical


def _read_lane_documents(
    candidate: runtime_calibration.CandidateInputs,
    lane_id: str,
) -> dict[str, tuple[dict[str, Any], str, str]]:
    return {
        name: _read_document(candidate, path)
        for name, path in _lane_paths(lane_id).items()
    }


def _driver_document(
    documents: Mapping[str, tuple[dict[str, Any], str, str]],
) -> dict[str, Any]:
    result = {
        name: documents[name][0]
        for name in _DRIVER_VISIBLE_SHAPE
    }
    serialized = json.dumps(result, ensure_ascii=False, sort_keys=True).lower()
    if any(term in serialized for term in discovery.PROJECTION_LEAKAGE_TERMS):
        _fail("mapping_driver_leakage")
    return result


def _source_request_for_package(
    package: discovery.SourceRichDiscoveryPackage,
    *,
    lane_id: str,
    result: discovery.ChangeTargetDiscoveryResult | discovery.ProjectTargetDiscoveryResult,
) -> RuntimeSourceRequest:
    target = package.target
    pair = package.pair
    context = package.context_acquisition
    if isinstance(target, discovery.ChangeTarget):
        materialization_kind = "change_target_pristine_source"
        source_commit = target.source_commit
        source_tree = context.source_tree_sha256
        materialized_tree = pair.baseline.tree_sha256
        materialization_receipt = None
        result_diff = None
        scope = None
        budget = None
        patch_ref = target.diff_ref
    elif isinstance(target, discovery.ProjectTarget):
        receipt = package.synthetic_commit
        if receipt is None:
            _fail("mapping_source_materialization_missing")
        assert package.synthetic_commit is not None
        materialization_kind = "project_target_synthetic_commit"
        source_commit = receipt.synthetic_commit
        source_tree = receipt.synthetic_source_tree_sha256
        materialized_tree = receipt.synthetic_tree_sha256
        materialization_receipt = receipt.identity_sha256
        result_diff = receipt.result_diff_sha256
        scope = target.scope
        budget = target.discovery_budget
        patch_ref = f"{discovery.PATCH_ARTIFACT_DIRECTORY}/{package.variant.variant_id}.patch"
    else:
        _fail("mapping_source_target_invalid")
    return RuntimeSourceRequest(
        request_id=f"{RUNTIME_MAPPING_RELEASE_ID}:{lane_id}:source-request",
        candidate_identity_sha256=result.candidate_identity_sha256,
        candidate_manifest_sha256=result.candidate_manifest_sha256,
        candidate_artifact_inventory_sha256=result.candidate_artifact_inventory_sha256,
        lane_id=lane_id,
        target_kind="ChangeTarget" if isinstance(target, discovery.ChangeTarget) else "ProjectTarget",
        variant=package.variant.variant_id,
        catalog_id=package.catalog_id,
        package_id=package.package_id,
        target_id=target.target_id,
        source_id=package.source_id,
        source_origin=pair.baseline.origin,
        baseline_commit=pair.baseline.commit,
        baseline_tree_sha256=(
            context.source_tree_sha256
            if isinstance(target, discovery.ChangeTarget)
            else package.synthetic_commit.parent_source_tree_sha256  # type: ignore[union-attr]
        ),
        baseline_archive_sha256=pair.baseline.archive_sha256,
        source_commit=source_commit,
        source_tree_sha256=source_tree,
        materialized_tree_sha256=materialized_tree,
        worktree_path=context.source_root,
        target_path=pair.anchor.path,
        target_file_sha256=(
            pair.anchor.target_file_sha256
            if isinstance(target, discovery.ChangeTarget)
            else package.synthetic_commit.target_file_sha256  # type: ignore[union-attr]
        ),
        anchor_identity_sha256=pair.anchor.identity_sha256,
        context_acquisition_identity_sha256=context.identity_sha256,
        discovery_materialization_identity_sha256=(
            context.identity_sha256
            if isinstance(target, discovery.ChangeTarget)
            else package.synthetic_commit.identity_sha256  # type: ignore[union-attr]
        ),
        campaign_identity_sha256=_digest(package.campaign.to_dict()),
        patch_ref=patch_ref,
        patch_sha256=package.variant.patch_sha256,
        patch_format="unified_diff",
        materialization_kind=materialization_kind,
        materialization_receipt_identity_sha256=materialization_receipt,
        result_diff_sha256=result_diff,
        scope=scope,
        discovery_budget=budget,
        source_package_identity_sha256=package.identity_sha256,
        discovery_result_identity_sha256=result.identity_sha256,
        leakage_audit_identity_sha256=result.leakage_audit.identity_sha256,
    )


def _expected_result_items(
    result: discovery.ChangeTargetDiscoveryResult | discovery.ProjectTargetDiscoveryResult,
    target_kind: str,
) -> tuple[tuple[str, discovery.SourceRichDiscoveryPackage, discovery.BlindRuntimeProjection], ...]:
    expected = tuple(
        meaning for meaning in RUNTIME_LANE_MEANINGS if meaning.target_kind == target_kind
    )
    if len(result.packages) != 2 or len(result.projections) != 2:
        _fail("mapping_discovery_admission_incomplete")
    if not result.admitted or result.leakage_audit.status != "passed":
        _fail("mapping_discovery_admission_incomplete")
    if any(
        getattr(result, field_name) != 0
        for field_name in ("build_calls", "device_calls", "model_calls")
    ):
        _fail("mapping_discovery_side_effect")
    if isinstance(result, discovery.ProjectTargetDiscoveryResult) and result.source_patches_applied != 2:
        _fail("mapping_discovery_materialization_mismatch")
    return tuple(
        (meaning.lane_id, result.packages[index], result.projections[index])
        for index, meaning in enumerate(expected)
    )


def _candidate_lane_binding(
    candidate: runtime_calibration.CandidateInputs,
    package: discovery.SourceRichDiscoveryPackage,
    projection: discovery.BlindRuntimeProjection,
    lane_id: str,
    result: discovery.ChangeTargetDiscoveryResult | discovery.ProjectTargetDiscoveryResult,
) -> RuntimeLaneBinding:
    documents = _read_lane_documents(candidate, lane_id)
    projection_document, projection_raw, projection_canonical = documents["projection"]
    plan_document, plan_raw, plan_canonical = documents["driver_plan"]
    recipe_document, recipe_raw, recipe_canonical = documents["recipe"]
    run_spec_document, run_spec_raw, run_spec_canonical = documents["run_spec"]
    paths = _lane_paths(lane_id)
    if (
        projection_document.get("lane_id") != lane_id
        or projection_document.get("projection_id") != f"{lane_id}-projection"
        or projection_document.get("run_spec_path") != paths["run_spec"]
        or projection_document.get("driver_plan_path") != paths["driver_plan"]
        or projection_document.get("recipe_path") != paths["recipe"]
        or projection_document.get("quality_contract_id") != projection.quality_contract_id
        or projection_document.get("risk_hypothesis_id") != projection.risk_hypothesis_id
        or projection_document.get("attack_plan_id") != projection.attack_plan_id
        or projection_document.get("model_policy") != {"model_calls": 0, "l3": "forbidden"}
        or projection_document.get("diff") is not None
    ):
        _fail("mapping_projection_binding_mismatch")
    if (
        plan_document.get("run_spec_path") != paths["run_spec"]
        or plan_document.get("run_spec_sha256") != run_spec_canonical
        or plan_document.get("lane_id") != lane_id
    ):
        _fail("mapping_driver_plan_binding_mismatch")
    if (
        recipe_document.get("lane_id") != lane_id
        or run_spec_document.get("lane_id") != lane_id
    ):
        _fail("mapping_runtime_artifact_binding_mismatch")
    internal_commitments = (
        projection.projection_commitment,
        projection.driver_plan_commitment,
        projection.recipe_commitment,
        projection.run_spec_commitment,
    )
    raw_commitments = (projection_raw, plan_raw, recipe_raw, run_spec_raw)
    if internal_commitments != raw_commitments:
        _fail("mapping_input_digest_mismatch")
    source_request = _source_request_for_package(package, lane_id=lane_id, result=result)
    return RuntimeLaneBinding(
        lane_id=lane_id,
        target_kind="ChangeTarget"
        if isinstance(package.target, discovery.ChangeTarget)
        else "ProjectTarget",
        variant=package.variant.variant_id,
        catalog_id=package.catalog_id,
        package_id=package.package_id,
        source_package_identity_sha256=package.identity_sha256,
        discovery_result_identity_sha256=result.identity_sha256,
        leakage_audit_identity_sha256=result.leakage_audit.identity_sha256,
        blind_projection_id=projection.projection_id,
        blind_projection_identity_sha256=projection.identity_sha256,
        candidate_projection_id=projection_document["projection_id"],
        projection_path=paths["projection"],
        driver_plan_path=paths["driver_plan"],
        recipe_path=paths["recipe"],
        run_spec_path=paths["run_spec"],
        projection_raw_sha256=projection_raw,
        driver_plan_raw_sha256=plan_raw,
        recipe_raw_sha256=recipe_raw,
        run_spec_raw_sha256=run_spec_raw,
        projection_canonical_sha256=projection_canonical,
        driver_plan_canonical_sha256=plan_canonical,
        recipe_canonical_sha256=recipe_canonical,
        run_spec_canonical_sha256=run_spec_canonical,
        setup_plan_canonical_sha256=_digest(projection_document["setup_plan"]),
        projection_shape=tuple(projection_document.keys()),
        driver_plan_shape=tuple(plan_document.keys()),
        recipe_shape=tuple(recipe_document.keys()),
        run_spec_shape=tuple(run_spec_document.keys()),
        source_request=source_request,
    )


def _validate_discovery_result(
    candidate: runtime_calibration.CandidateInputs,
    result: discovery.ChangeTargetDiscoveryResult | discovery.ProjectTargetDiscoveryResult,
    target_kind: str,
) -> tuple[RuntimeLaneBinding, ...]:
    expected_class = (
        discovery.ChangeTargetDiscoveryResult
        if target_kind == "ChangeTarget"
        else discovery.ProjectTargetDiscoveryResult
    )
    if not isinstance(result, expected_class):
        _fail("mapping_discovery_result_kind_mismatch")
    if (
        result.candidate_identity_sha256 != candidate.candidate_identity_sha256
        or result.candidate_manifest_sha256 != candidate.manifest_sha256
        or result.candidate_artifact_inventory_sha256 != candidate.artifact_inventory_sha256
    ):
        _fail("mapping_candidate_identity_mismatch")
    items = _expected_result_items(result, target_kind)
    expected_projection_ids = tuple(projection.projection_id for _, _, projection in items)
    if result.leakage_audit.checked_projection_ids != expected_projection_ids:
        _fail("mapping_leakage_audit_mismatch")
    try:
        audited = discovery.audit_projection_leakage(
            tuple(projection for _, _, projection in items)
        )
    except Exception as error:
        raise RuntimeMappingReleaseError("mapping_leakage_audit_mismatch") from error
    if audited != result.leakage_audit:
        _fail("mapping_leakage_audit_mismatch")
    bindings: list[RuntimeLaneBinding] = []
    for lane_id, package, projection in items:
        try:
            expected_projection = discovery._build_projection(candidate, package, lane_id)
        except Exception as error:
            raise RuntimeMappingReleaseError("mapping_projection_mismatch") from error
        if projection != expected_projection:
            _fail("mapping_projection_mismatch")
        bindings.append(_candidate_lane_binding(candidate, package, projection, lane_id, result))
    return tuple(bindings)


def _validate_shared_discovery_contracts(
    packages: Sequence[discovery.SourceRichDiscoveryPackage],
) -> None:
    if len(packages) != 4:
        _fail("mapping_discovery_admission_incomplete")

    def neutral_document(
        package: discovery.SourceRichDiscoveryPackage,
        field_name: str,
        excluded: frozenset[str] = frozenset(),
    ) -> dict[str, Any]:
        document = getattr(package, field_name).to_dict()
        return {key: value for key, value in document.items() if key not in excluded}

    neutral_fields: tuple[tuple[str, frozenset[str]], ...] = (
        ("quality_contract", frozenset()),
        ("risk_prior", frozenset()),
        ("attack_operator", frozenset()),
        (
            "risk_hypothesis",
            frozenset({"target_id", "behavior_delta_id", "contract_drift_id"}),
        ),
        ("attack_plan", frozenset({"target_id"})),
        ("risk_priority", frozenset()),
    )
    for field_name, excluded in neutral_fields:
        expected = neutral_document(packages[0], field_name, excluded)
        if any(
            neutral_document(package, field_name, excluded) != expected
            for package in packages[1:]
        ):
            _fail("mapping_discovery_contract_mismatch")
    if any(
        package.exploration_policy_id != packages[0].exploration_policy_id
        for package in packages[1:]
    ):
        _fail("mapping_discovery_contract_mismatch")
    if any(
        package.context_acquisition.required_paths != discovery.REQUIRED_CONTEXT_PATHS
        or package.context_acquisition.adapters != discovery.REQUIRED_CONTEXT_ADAPTERS
        or package.context_acquisition.engine_adapters != discovery.ENGINE_CONTEXT_ADAPTERS
        or package.context_acquisition.result.receipt.discovery_budget
        != discovery.REQUIRED_CONTEXT_BUDGET
        or package.context_acquisition.result.receipt.budget_used
        != discovery.REQUIRED_CONTEXT_BUDGET
        for package in packages
    ):
        _fail("mapping_discovery_context_mismatch")


def _check_driver_shape_and_hash(
    candidate: runtime_calibration.CandidateInputs,
    lanes: tuple[RuntimeLaneBinding, ...],
) -> str:
    documents = _driver_documents(candidate, lanes)
    return _digest(documents)


def _driver_documents(
    candidate: runtime_calibration.CandidateInputs,
    lanes: Sequence[RuntimeLaneBinding],
) -> tuple[dict[str, Any], ...]:
    documents: list[dict[str, Any]] = []
    for lane in lanes:
        raw_documents = _read_lane_documents(candidate, lane.lane_id)
        document = _driver_document(raw_documents)
        if tuple(document) != _DRIVER_VISIBLE_SHAPE:
            _fail("mapping_driver_shape_mismatch")
        documents.append(document)
    if not documents:
        _fail("mapping_driver_shape_mismatch")
    if any(tuple(document) != tuple(documents[0]) for document in documents[1:]):
        _fail("mapping_driver_shape_mismatch")
    return tuple(documents)


def _precheck_output_path(output_path: str | Path) -> Path:
    path = Path(output_path).expanduser()
    if path.name != RUNTIME_MAPPING_RELEASE_FILENAME:
        _fail("mapping_output_filename_mismatch")
    if path.exists() or path.is_symlink():
        _fail("mapping_release_already_exists")
    if not path.parent.is_dir() or path.parent.is_symlink():
        _fail("mapping_output_unavailable")
    return path


def _encoded_release(release: RuntimeMappingRelease) -> bytes:
    try:
        return (
            json.dumps(
                release.to_dict(),
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise RuntimeMappingReleaseError("mapping_release_encoding_failed") from error


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as error:
        raise RuntimeMappingReleaseError("mapping_release_durability_failed") from error


def write_runtime_mapping_release(
    release: RuntimeMappingRelease,
    output_path: str | Path,
) -> str:
    """Atomically create exactly one append-only ``mapping-release.json``."""

    if not isinstance(release, RuntimeMappingRelease):
        _fail("mapping_release_type_invalid")
    release.verify_integrity()
    path = _precheck_output_path(output_path)
    payload = _encoded_release(release)
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        _fsync_directory(path.parent)
    except FileExistsError as error:
        raise RuntimeMappingReleaseError("mapping_release_already_exists") from error
    except OSError as error:
        raise RuntimeMappingReleaseError("mapping_release_write_failed") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as error:
            raise RuntimeMappingReleaseError("mapping_release_cleanup_failed") from error
    return _sha256_bytes(payload)


def _unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("mapping_duplicate_key")
        result[key] = value
    return result


def load_runtime_mapping_release(path: str | Path) -> RuntimeMappingRelease:
    """Load one strict persisted release and verify its embedded identity."""

    release_path = Path(path).expanduser()
    if release_path.is_symlink() or not release_path.is_file():
        _fail("mapping_release_unavailable", verification=True)
    try:
        document = json.loads(
            release_path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_pairs,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeMappingVerificationError("mapping_release_unavailable") from error
    try:
        return RuntimeMappingRelease.from_dict(document)
    except RuntimeMappingError as error:
        raise RuntimeMappingVerificationError(error.code) from error


read_runtime_mapping_release = load_runtime_mapping_release


def release_runtime_mapping(
    change_discovery: discovery.ChangeTargetDiscoveryResult,
    project_discovery: discovery.ProjectTargetDiscoveryResult,
    *,
    candidate_root: str | Path = discovery.DEFAULT_CANDIDATE_ROOT,
    output_path: str | Path | None = None,
) -> RuntimeMappingRelease:
    """Validate all four admitted lanes and create one complete release.

    No output is written until both discovery results, all candidate artifacts,
    all cross-bindings, and the uniform driver-visible shape have passed.
    """

    if output_path is not None:
        _precheck_output_path(output_path)
    try:
        candidate = runtime_calibration.verify_candidate_inputs(candidate_root)
    except runtime_calibration.RuntimeCalibrationError as error:
        raise RuntimeMappingReleaseError("mapping_candidate_input_mismatch") from error
    if not isinstance(change_discovery, discovery.ChangeTargetDiscoveryResult):
        _fail("mapping_change_discovery_required")
    if not isinstance(project_discovery, discovery.ProjectTargetDiscoveryResult):
        _fail("mapping_project_discovery_required")
    if change_discovery.pair != project_discovery.pair:
        _fail("mapping_source_pair_mismatch")
    change_lanes = _validate_discovery_result(candidate, change_discovery, "ChangeTarget")
    project_lanes = _validate_discovery_result(candidate, project_discovery, "ProjectTarget")
    _validate_shared_discovery_contracts(
        (*change_discovery.packages, *project_discovery.packages)
    )
    lanes = (*change_lanes, *project_lanes)
    if tuple(lane.lane_id for lane in lanes) != RUNTIME_LANE_IDS:
        _fail("mapping_lane_order_mismatch")
    all_driver_documents = _driver_documents(candidate, lanes)
    driver_shape = _DRIVER_VISIBLE_SHAPE
    driver_digest = _digest(all_driver_documents)
    admissions = tuple(
        DiscoveryAdmissionReceipt(
            lane_id=lane.lane_id,
            target_kind=lane.target_kind,
            variant=lane.variant,
            discovery_result_kind=(
                "ChangeTargetDiscoveryResult"
                if lane.lane_id in (RUNTIME_LANE_IDS[0], RUNTIME_LANE_IDS[1])
                else "ProjectTargetDiscoveryResult"
            ),
            discovery_result_identity_sha256=lane.discovery_result_identity_sha256,
            package_id=lane.package_id,
            package_identity_sha256=lane.source_package_identity_sha256,
            blind_projection_id=lane.blind_projection_id,
            blind_projection_identity_sha256=lane.blind_projection_identity_sha256,
            leakage_audit_identity_sha256=lane.leakage_audit_identity_sha256,
        )
        for lane in lanes
    )
    release = RuntimeMappingRelease(
        release_id=RUNTIME_MAPPING_RELEASE_ID,
        candidate_identity_sha256=candidate.candidate_identity_sha256,
        candidate_manifest_sha256=candidate.manifest_sha256,
        candidate_artifact_inventory_sha256=candidate.artifact_inventory_sha256,
        discovery_admissions=admissions,
        lanes=lanes,
        driver_visible_serialization_sha256=driver_digest,
        driver_projection_ids=tuple(lane.candidate_projection_id for lane in lanes),
        driver_visible_shape=driver_shape,
    )
    if output_path is not None:
        write_runtime_mapping_release(release, output_path)
    return release


build_runtime_mapping_release = release_runtime_mapping
admit_runtime_mapping = release_runtime_mapping
release_opencalc_runtime_mapping = release_runtime_mapping


def verify_runtime_mapping_release(
    release: RuntimeMappingRelease | Mapping[str, Any],
    *,
    candidate_root: str | Path | None = None,
    change_discovery: discovery.ChangeTargetDiscoveryResult | None = None,
    project_discovery: discovery.ProjectTargetDiscoveryResult | None = None,
) -> bool:
    """Reverify a release and optionally its current candidate/discoveries."""

    try:
        value = (
            release
            if isinstance(release, RuntimeMappingRelease)
            else RuntimeMappingRelease.from_dict(release)
        )
        value.verify_integrity()
    except RuntimeMappingError:
        raise
    except (TypeError, ValueError) as error:
        raise RuntimeMappingVerificationError("mapping_release_invalid") from error
    if candidate_root is not None:
        try:
            candidate = runtime_calibration.verify_candidate_inputs(candidate_root)
        except runtime_calibration.RuntimeCalibrationError as error:
            raise RuntimeMappingVerificationError(
                "mapping_candidate_input_mismatch"
            ) from error
        if (
            candidate.candidate_identity_sha256 != value.candidate_identity_sha256
            or candidate.manifest_sha256 != value.candidate_manifest_sha256
            or candidate.artifact_inventory_sha256 != value.candidate_artifact_inventory_sha256
        ):
            _fail("mapping_candidate_identity_mismatch", verification=True)
        expected_digest = _check_driver_shape_and_hash(candidate, value.lanes)
        if expected_digest != value.driver_visible_serialization_sha256:
            _fail("mapping_input_digest_mismatch", verification=True)
        for lane in value.lanes:
            _candidate_lane_binding_from_release(candidate, lane)
    if (change_discovery is None) != (project_discovery is None):
        _fail("mapping_discovery_pair_incomplete", verification=True)
    if change_discovery is not None and project_discovery is not None:
        expected = release_runtime_mapping(
            change_discovery,
            project_discovery,
            candidate_root=candidate_root or runtime_calibration._default_candidate_root(),
        )
        if expected.to_dict() != value.to_dict():
            _fail("mapping_post_release_mutation", verification=True)
    return True


def _candidate_lane_binding_from_release(
    candidate: runtime_calibration.CandidateInputs,
    lane: RuntimeLaneBinding,
) -> None:
    documents = _read_lane_documents(candidate, lane.lane_id)
    for name, raw_sha, canonical_sha in (
        ("projection", lane.projection_raw_sha256, lane.projection_canonical_sha256),
        ("driver_plan", lane.driver_plan_raw_sha256, lane.driver_plan_canonical_sha256),
        ("recipe", lane.recipe_raw_sha256, lane.recipe_canonical_sha256),
        ("run_spec", lane.run_spec_raw_sha256, lane.run_spec_canonical_sha256),
    ):
        if documents[name][1:] != (raw_sha, canonical_sha):
            _fail("mapping_input_digest_mismatch", verification=True)
    if _digest(documents["projection"][0]["setup_plan"]) != lane.setup_plan_canonical_sha256:
        _fail("mapping_input_digest_mismatch", verification=True)


def verify_released_source_requests(
    release_or_mapping: RuntimeMappingRelease | SourceAuthorityMapping,
    authority: SourceAuthority,
) -> bool:
    """Verify the source-only release view with an existing authority type."""

    if isinstance(release_or_mapping, RuntimeMappingRelease):
        mapping = release_or_mapping.consume(authority)
        if not isinstance(mapping, SourceAuthorityMapping):
            _fail("mapping_consumer_phase_mismatch")
    elif isinstance(release_or_mapping, SourceAuthorityMapping):
        mapping = release_or_mapping
    else:
        _fail("mapping_unauthorized_consumer")
    mapping.verify_with(authority)
    return True


def verify_source_requests(
    release_or_mapping: RuntimeMappingRelease | SourceAuthorityMapping,
    authority: SourceAuthority,
) -> bool:
    return verify_released_source_requests(release_or_mapping, authority)


def _prepare_stage_root(output_root: str | Path) -> Path:
    raw_root = Path(output_root).expanduser()
    if raw_root.is_symlink():
        _fail("mapping_stage_output_root_symlink")
    root = raw_root.resolve()
    if root.exists():
        if not root.is_dir() or any(root.iterdir()):
            _fail("mapping_stage_output_root_not_empty")
    else:
        try:
            root.mkdir(parents=True, exist_ok=False)
        except OSError as error:
            raise RuntimeMappingReleaseError("mapping_stage_output_unavailable") from error
    return root


def _write_stage_json(path: Path, document: Mapping[str, Any]) -> str:
    if path.exists() or path.is_symlink():
        _fail("mapping_stage_receipt_already_exists")
    payload = (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        _fsync_directory(path.parent)
    except FileExistsError as error:
        raise RuntimeMappingReleaseError("mapping_stage_receipt_already_exists") from error
    except OSError as error:
        raise RuntimeMappingReleaseError("mapping_stage_receipt_write_failed") from error
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError as error:
            raise RuntimeMappingReleaseError("mapping_stage_receipt_cleanup_failed") from error
    return _sha256_bytes(payload)


def _stage_identity(document: Mapping[str, Any], field_name: str) -> str:
    value = dict(document)
    value.pop(field_name, None)
    return _digest(value)


def _accepted_predecessor(
    predecessor_root: str | Path,
    candidate_root: str | Path,
) -> tuple[dict[str, Any], str]:
    root = Path(predecessor_root).expanduser().resolve()
    terminal_path = root / "stage-terminal.json"
    if not terminal_path.is_file() or terminal_path.is_symlink():
        _fail("mapping_predecessor_not_accepted")
    try:
        raw = terminal_path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("mapping_predecessor_not_accepted")
    if not isinstance(document, dict):
        _fail("mapping_predecessor_not_accepted")
    if (
        document.get("stage") != "verify-candidate"
        or document.get("status") != "accepted"
        or document.get("candidate_root")
        != str(Path(candidate_root).expanduser().resolve())
        or not runtime_calibration.is_candidate_accepted(root)
    ):
        _fail("mapping_predecessor_not_accepted")
    terminal_identity = document.get("terminal_identity_sha256")
    if not isinstance(terminal_identity, str) or _HEX_64.fullmatch(terminal_identity) is None:
        _fail("mapping_predecessor_not_accepted")
    return document, _sha256_bytes(raw)


def stage_status(output_root: str | Path) -> str:
    """Return the structural status of an ``admit-family`` staging root."""

    root = Path(output_root).expanduser().resolve()
    start_path = root / "stage-start.json"
    terminal_path = root / "stage-terminal.json"
    if start_path.is_symlink() or terminal_path.is_symlink():
        return "invalid"
    if not start_path.is_file():
        return "absent"
    try:
        start_raw = start_path.read_bytes()
        start = json.loads(start_raw.decode("utf-8"))
        if not isinstance(start, dict) or start.get("stage") != "admit-family":
            return "invalid"
        if start.get("start_identity_sha256") != _stage_identity(
            start, "start_identity_sha256"
        ):
            return "invalid"
        if not terminal_path.is_file():
            return "abandoned"
        terminal_raw = terminal_path.read_bytes()
        terminal = json.loads(terminal_raw.decode("utf-8"))
        if not isinstance(terminal, dict):
            return "invalid"
        if terminal.get("start_receipt_sha256") != _sha256_bytes(start_raw):
            return "invalid"
        if terminal.get("terminal_identity_sha256") != _stage_identity(
            terminal, "terminal_identity_sha256"
        ):
            return "invalid"
        status = terminal.get("status")
        release_path = root / RUNTIME_MAPPING_RELEASE_FILENAME
        if status == "accepted":
            if not release_path.is_file() or release_path.is_symlink():
                return "invalid"
            release = load_runtime_mapping_release(release_path)
            if (
                release.identity_sha256 != terminal.get("mapping_release_identity_sha256")
                or _sha256_bytes(release_path.read_bytes())
                != terminal.get("mapping_release_sha256")
            ):
                return "invalid"
        elif status == "rejected" and (
            release_path.exists() or release_path.is_symlink()
        ):
            return "invalid"
        if status not in {"accepted", "rejected"}:
            return "invalid"
        return str(status)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RuntimeMappingError):
        return "invalid"


def admit_family(
    *,
    candidate_root: str | Path = discovery.DEFAULT_CANDIDATE_ROOT,
    source_root: str | Path = discovery.DEFAULT_SOURCE_ROOT,
    output_root: str | Path,
    predecessor_root: str | Path,
    materialization_root: str | Path | None = None,
) -> RuntimeMappingRelease:
    """Run the model-free, Git-only family-admission stage."""

    output = _prepare_stage_root(output_root)
    try:
        candidate = runtime_calibration.verify_candidate_inputs(candidate_root)
    except runtime_calibration.RuntimeCalibrationError as error:
        raise RuntimeMappingReleaseError("mapping_candidate_input_mismatch") from error
    predecessor_terminal, predecessor_digest = _accepted_predecessor(
        predecessor_root, candidate_root
    )
    if (
        predecessor_terminal.get("candidate_identity_sha256")
        != candidate.candidate_identity_sha256
        or predecessor_terminal.get("manifest_sha256") != candidate.manifest_sha256
        or predecessor_terminal.get("artifact_inventory_sha256")
        != candidate.artifact_inventory_sha256
    ):
        _fail("mapping_predecessor_input_mismatch")
    start: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": "admit-family",
        "status": "started",
        "candidate_root": str(Path(candidate_root).expanduser().resolve()),
        "source_root": str(Path(source_root).expanduser().resolve()),
        "output_root": str(output),
        "predecessor_root": str(Path(predecessor_root).expanduser().resolve()),
        "predecessor_terminal_sha256": predecessor_digest,
        "claim_boundary": RUNTIME_MAPPING_CLAIM_BOUNDARY,
    }
    start["start_identity_sha256"] = _stage_identity(start, "start_identity_sha256")
    start_digest = _write_stage_json(output / "stage-start.json", start)
    release: RuntimeMappingRelease | None = None
    error_code: str | None = None
    try:
        change = discovery.admit_change_target_pair(candidate_root, source_root)
        project = discovery.admit_project_target_pair(
            candidate_root,
            source_root,
            materialization_root,
        )
        release = release_runtime_mapping(
            change,
            project,
            candidate_root=candidate_root,
            output_path=output / RUNTIME_MAPPING_RELEASE_FILENAME,
        )
    except RuntimeMappingError as error:
        error_code = error.code
    except (discovery.OpenCalcDiscoveryError, runtime_calibration.RuntimeCalibrationError) as error:
        error_code = getattr(error, "code", "mapping_family_admission_failed")
    except Exception:  # noqa: BLE001 - terminalize every ordinary admission failure
        error_code = "mapping_family_admission_failed"
    status = "accepted" if release is not None else "rejected"
    terminal: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "stage": "admit-family",
        "status": status,
        "candidate_root": str(Path(candidate_root).expanduser().resolve()),
        "source_root": str(Path(source_root).expanduser().resolve()),
        "output_root": str(output),
        "claim_boundary": RUNTIME_MAPPING_CLAIM_BOUNDARY,
        "candidate_identity_sha256": candidate.candidate_identity_sha256,
        "manifest_sha256": candidate.manifest_sha256,
        "artifact_inventory_sha256": candidate.artifact_inventory_sha256,
        "mapping_release_identity_sha256": release.identity_sha256 if release else None,
        "mapping_release_sha256": (
            _sha256_bytes((output / RUNTIME_MAPPING_RELEASE_FILENAME).read_bytes())
            if release is not None
            else None
        ),
        "reason": error_code,
        "predecessor_terminal_sha256": predecessor_digest,
        "start_receipt_sha256": start_digest,
    }
    terminal["terminal_identity_sha256"] = _stage_identity(
        terminal, "terminal_identity_sha256"
    )
    _write_stage_json(output / "stage-terminal.json", terminal)
    if release is None:
        raise RuntimeMappingReleaseError(error_code or "mapping_family_admission_failed")
    return release


admit_runtime_mapping_family = admit_family


__all__ = [
    "FAMILY_ID",
    "FAMILY_VERSION",
    "FROZEN_LANE_ORDER",
    "LANE_IDS",
    "MAPPING_RELEASED_STATUS",
    "RUNTIME_LANE_IDS",
    "RUNTIME_LANE_MEANINGS",
    "RUNTIME_MAPPING_CLAIM_BOUNDARY",
    "RUNTIME_MAPPING_RELEASE_FILENAME",
    "RUNTIME_MAPPING_RELEASE_ID",
    "SEALED_BLIND_STATUS",
    "DiscoveryAdmissionReceipt",
    "ReducerLaneBinding",
    "ReducerMapping",
    "RuntimeLaneBinding",
    "RuntimeLaneMeaning",
    "RuntimeMappingError",
    "RuntimeMappingRelease",
    "RuntimeMappingReleaseError",
    "RuntimeMappingVerificationError",
    "RuntimeReducerAuthority",
    "RuntimeSourceRequest",
    "RuntimeTerminalExecutionEvidence",
    "SourceAuthority",
    "SourceAuthorityMapping",
    "SourceAuthorityVerification",
    "TerminalExecutionEvidence",
    "admit_family",
    "admit_runtime_mapping",
    "admit_runtime_mapping_family",
    "build_runtime_mapping_release",
    "load_runtime_mapping_release",
    "read_runtime_mapping_release",
    "release_opencalc_runtime_mapping",
    "release_runtime_mapping",
    "stage_status",
    "verify_released_source_requests",
    "verify_runtime_mapping_release",
    "verify_source_requests",
    "write_runtime_mapping_release",
]
