"""Admission of the OpenCalc ChangeTarget and ProjectTarget matched pair.

This module owns the side-effect-free discovery boundary for the OpenCalc
runtime-calibration family.  It binds the checked-in candidate to a pristine
upstream checkout, validates the two controlled injections, acquires bounded
context from each admitted source, and emits auditor-only packages plus blind
runtime projections for both target modes.

The source tree passed to :func:`admit_change_target_pair` is never patched;
the patch remains a value in the auditor package and resulting
``ChangeTarget``.  ``admit_project_target_pair`` instead creates separate
fresh clones, applies the anchored injection, and records deterministic
synthetic commits.  Neither path invokes Gradle, Android CLI, adb, a model, or
a runtime oracle.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from aiverify.bench import runtime_calibration
from aiverify.discovery.acquisition import (
    ContextAcquisitionResult,
    acquire_project_context,
)
from aiverify.discovery.campaign import (
    ContextExpansionRequest,
    ContextExpansionResult,
    DiscoveryCampaignPackage,
    admit_campaign_plan,
    seed_change_campaign,
    seed_project_campaign,
)
from aiverify.discovery.contracts import (
    AttackOperator,
    AttackPlan,
    ContractDrift,
    FailureChain,
    QualityContract,
    RiskHypothesis,
    RiskPrior,
)
from aiverify.discovery.models import (
    ChangeTarget,
    ContextFact,
    DiscoveryContractError,
    ProjectTarget,
    ProvenanceRef,
)
from aiverify.discovery.risk import (
    BehaviorDelta,
    RiskDerivationResult,
    RiskPriority,
    make_risk_derivation_strategy,
)

SCHEMA_VERSION = 1

FAMILY_ID = runtime_calibration.FAMILY_ID
FAMILY_VERSION = runtime_calibration.FAMILY_VERSION
PAIR_ID = runtime_calibration.PAIR_ID
UPSTREAM_ORIGIN = runtime_calibration.UPSTREAM_ORIGIN
UPSTREAM_COMMIT = runtime_calibration.UPSTREAM_COMMIT
UPSTREAM_TREE_SHA256 = runtime_calibration.UPSTREAM_TREE_SHA256
UPSTREAM_ARCHIVE_SHA256 = runtime_calibration.UPSTREAM_ARCHIVE_SHA256
TARGET_SOURCE_PATH = runtime_calibration.TARGET_SOURCE_PATH
TARGET_SOURCE_SHA256 = runtime_calibration.TARGET_SOURCE_SHA256
QUALITY_CONTRACT_ID = runtime_calibration.QUALITY_CONTRACT_ID
RISK_PRIOR_ID = runtime_calibration.RISK_PRIOR_ID
ATTACK_OPERATOR_ID = runtime_calibration.ATTACK_OPERATOR_ID
RISK_HYPOTHESIS_ID = runtime_calibration.RISK_HYPOTHESIS_ID
ATTACK_PLAN_ID = runtime_calibration.ATTACK_PLAN_ID
EXPLORATION_POLICY_ID = runtime_calibration.EXPLORATION_POLICY_ID

REQUIRED_CONTEXT_BUDGET = 9
REQUIRED_CONTEXT_PATHS = (
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
REQUIRED_CONTEXT_ADAPTERS = (
    "source-file",
    "manifest",
    "layout",
    "build-file",
    "settings",
    "version-catalog",
)
ENGINE_CONTEXT_ADAPTERS = (
    "manifest",
    "build",
    "symbols_calls",
    "persistence_state",
    "lifecycle_ownership",
    "quality_version",
)
PATCH_ARTIFACT_DIRECTORY = (
    "bench/runtime-calibration/opencalc-input-save-enabled-v1-diffs"
)

CONTROL_VARIANT = "control"
DEFECT_VARIANT = "defect"
VARIANT_IDS = (CONTROL_VARIANT, DEFECT_VARIANT)
CONTROL_LANE_ID = "ocrc-v1-lane-01"
DEFECT_LANE_ID = "ocrc-v1-lane-02"
PROJECT_CONTROL_LANE_ID = "ocrc-v1-lane-03"
PROJECT_DEFECT_LANE_ID = "ocrc-v1-lane-04"
PROJECT_LANE_IDS = (PROJECT_CONTROL_LANE_ID, PROJECT_DEFECT_LANE_ID)

SYNTHETIC_COMMIT_MESSAGE = "OpenCalc calibration synthetic project target"
SYNTHETIC_AUTHOR_NAME = "OpenCalc Calibration"
SYNTHETIC_AUTHOR_EMAIL = "opencalc-calibration@localhost"
SYNTHETIC_COMMIT_TIMESTAMP = "2000-01-01T00:00:00Z"

DEFAULT_CANDIDATE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "bench/runtime-calibration/opencalc-input-save-enabled-v1"
)
DEFAULT_SOURCE_ROOT = Path("/Users/peter/hosts/opencalc-calibration")

_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_HEX_40 = re.compile(r"^[0-9a-f]{40}$")
_COMMIT = _HEX_40

# These terms are deliberately narrower than a general semantic leak
# detector.  They cover the material the driver is explicitly forbidden to
# receive at this boundary while allowing neutral contract identifiers.
PROJECTION_LEAKAGE_TERMS = (
    "control",
    "defect",
    "variant",
    "changetarget",
    "projecttarget",
    "source-rich",
    "source_rich",
    "expected symptom",
    "expected_result",
    "expected_behavior",
    "state_loss",
    "oracle",
)


class ChangeTargetAdmissionError(runtime_calibration.RuntimeCalibrationError):
    """A stable, non-disclosing rejection at the ChangeTarget seam."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


# Keep the historical public alias exact; ProjectTarget errors subclass this
# type so existing broad handlers still cover both discovery target modes.
OpenCalcDiscoveryError = ChangeTargetAdmissionError


class ProjectTargetAdmissionError(ChangeTargetAdmissionError):
    """A stable, non-disclosing rejection at the ProjectTarget seam."""


ProjectTargetDiscoveryError = ProjectTargetAdmissionError


def _fail(code: str) -> None:
    raise ChangeTargetAdmissionError(code)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ChangeTargetAdmissionError(f"invalid_{field}")
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ChangeTargetAdmissionError(f"invalid_{field}")
    if not allow_empty and not value:
        raise ChangeTargetAdmissionError(f"invalid_{field}")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ChangeTargetAdmissionError(f"invalid_{field}")
    return value


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], code: str) -> None:
    if sorted(set(data) - allowed):
        _fail(code)


def _as_mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(code)
    return value


def _as_list(value: object, code: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(code)
    return value


def _canonical_origin(value: str) -> str:
    return value.strip().rstrip("/")


def _safe_relative_path(value: object, field: str) -> str:
    value = _required_text(value, field)
    if "\\" in value:
        _fail(f"invalid_{field}")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or parsed.as_posix() != value
        or any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        _fail(f"invalid_{field}")
    return value


def _canonical_patch_text(right_hand_side: str) -> str:
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


@dataclass(frozen=True)
class SourceBaseline:
    """The complete immutable baseline identity declared by the candidate."""

    origin: str
    commit: str
    tree_sha256: str
    archive_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.origin, "baseline_origin")
        _required_text(self.commit, "baseline_commit")
        _required_text(self.tree_sha256, "baseline_tree")
        _required_text(self.archive_sha256, "baseline_archive")
        if not _COMMIT.fullmatch(self.commit):
            _fail("invalid_baseline_commit")
        if not _HEX_40.fullmatch(self.tree_sha256):
            _fail("invalid_baseline_tree")
        if not _HEX_64.fullmatch(self.archive_sha256):
            _fail("invalid_baseline_archive")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "origin": self.origin,
            "commit": self.commit,
            "tree_sha256": self.tree_sha256,
            "archive_sha256": self.archive_sha256,
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceBaseline:
        _reject_unknown(
            data,
            {
                "schema_version",
                "origin",
                "commit",
                "tree_sha256",
                "archive_sha256",
                "identity_sha256",
            },
            "source_pair_schema_mismatch",
        )
        try:
            baseline = cls(
                origin=data["origin"],
                commit=data["commit"],
                tree_sha256=data["tree_sha256"],
                archive_sha256=data["archive_sha256"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except KeyError:
            _fail("source_pair_schema_mismatch")
        identity = data.get("identity_sha256")
        if identity is not None and identity != baseline.identity_sha256:
            _fail("source_identity_digest_mismatch")
        return baseline


@dataclass(frozen=True)
class UpstreamSourceAnchor:
    """A unique, exact context binding for one upstream source file."""

    origin: str
    commit: str
    path: str
    target_file_sha256: str
    context: str
    context_sha256: str
    required_occurrences: int
    insertion_after: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.origin, "anchor_origin")
        _required_text(self.commit, "anchor_commit")
        _required_text(self.target_file_sha256, "anchor_target_digest")
        _required_text(self.context_sha256, "anchor_context_digest")
        if not _COMMIT.fullmatch(self.commit):
            _fail("invalid_anchor_commit")
        _safe_relative_path(self.path, "anchor_path")
        if not _HEX_64.fullmatch(self.target_file_sha256):
            _fail("invalid_anchor_target_digest")
        _required_text(self.context, "anchor_context")
        if _bytes_digest(self.context.encode("utf-8")) != self.context_sha256:
            _fail("anchor_context_digest_mismatch")
        if (
            isinstance(self.required_occurrences, bool)
            or not isinstance(self.required_occurrences, int)
            or self.required_occurrences != 1
        ):
            _fail("anchor_occurrence_contract_mismatch")
        _required_text(self.insertion_after, "anchor_insertion_after")
        if not self.context.endswith(self.insertion_after):
            _fail("anchor_insertion_mismatch")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "origin": self.origin,
            "commit": self.commit,
            "path": self.path,
            "target_file_sha256": self.target_file_sha256,
            "context": self.context,
            "context_sha256": self.context_sha256,
            "required_occurrences": self.required_occurrences,
            "insertion_after": self.insertion_after,
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> UpstreamSourceAnchor:
        _reject_unknown(
            data,
            {
                "schema_version",
                "origin",
                "commit",
                "path",
                "target_file_sha256",
                "context",
                "context_sha256",
                "required_occurrences",
                "insertion_after",
                "identity_sha256",
            },
            "source_pair_schema_mismatch",
        )
        try:
            anchor = cls(
                origin=data["origin"],
                commit=data["commit"],
                path=data["path"],
                target_file_sha256=data["target_file_sha256"],
                context=data["context"],
                context_sha256=data["context_sha256"],
                required_occurrences=data["required_occurrences"],
                insertion_after=data["insertion_after"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except (KeyError, TypeError):
            _fail("source_pair_schema_mismatch")
        identity = data.get("identity_sha256")
        if identity is not None and identity != anchor.identity_sha256:
            _fail("source_anchor_digest_mismatch")
        return anchor


@dataclass(frozen=True)
class MatchedSourceVariant:
    """One declared member of the matched control/defect source pair."""

    variant_id: str
    source_id: str
    population_classification: str
    taxonomy_id: str
    mutation_operator_id: str
    patch_text: str
    patch_sha256: str
    difference_field: str
    right_hand_side: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.variant_id not in VARIANT_IDS:
            _fail("pair_variant_mismatch")
        _required_text(self.source_id, "variant_source_id")
        _required_text(self.population_classification, "variant_classification")
        _required_text(self.taxonomy_id, "variant_taxonomy")
        _required_text(self.mutation_operator_id, "variant_operator")
        _required_text(self.patch_text, "variant_patch")
        if _bytes_digest(self.patch_text.encode("utf-8")) != self.patch_sha256:
            _fail("variant_patch_digest_mismatch")
        _required_text(self.difference_field, "variant_difference_field")
        if not isinstance(self.right_hand_side, str) or self.right_hand_side not in {
            "true",
            "false",
        }:
            _fail("pair_difference_mismatch")
        expected_source_id = f"{PAIR_ID}-{self.variant_id}"
        if self.source_id != expected_source_id:
            _fail("pair_source_id_mismatch")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "variant_id": self.variant_id,
            "source_id": self.source_id,
            "population_classification": self.population_classification,
            "taxonomy_id": self.taxonomy_id,
            "mutation_operator_id": self.mutation_operator_id,
            "patch_text": self.patch_text,
            "patch_sha256": self.patch_sha256,
            "difference": {
                "field": self.difference_field,
                "right_hand_side": self.right_hand_side,
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        classification: str,
        taxonomy_id: str,
        mutation_operator_id: str,
    ) -> MatchedSourceVariant:
        _reject_unknown(
            data,
            {
                "schema_version",
                "variant_id",
                "source_id",
                "population_classification",
                "taxonomy_id",
                "mutation_operator_id",
                "patch_text",
                "patch_sha256",
                "difference",
            },
            "source_pair_schema_mismatch",
        )
        difference = _as_mapping(data.get("difference"), "pair_difference_mismatch")
        _reject_unknown(
            difference,
            {"field", "right_hand_side"},
            "pair_difference_mismatch",
        )
        try:
            return cls(
                variant_id=data["variant_id"],
                source_id=data["source_id"],
                population_classification=data.get(
                    "population_classification", classification
                ),
                taxonomy_id=data.get("taxonomy_id", taxonomy_id),
                mutation_operator_id=data.get(
                    "mutation_operator_id", mutation_operator_id
                ),
                patch_text=data["patch_text"],
                patch_sha256=data["patch_sha256"],
                difference_field=difference["field"],
                right_hand_side=difference["right_hand_side"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except (KeyError, TypeError):
            _fail("source_pair_schema_mismatch")


@dataclass(frozen=True)
class MatchedRuntimeSourcePair:
    """The shared baseline/anchor and exactly two controlled injections."""

    pair_id: str
    population_classification: str
    taxonomy_id: str
    mutation_operator_id: str
    baseline: SourceBaseline
    anchor: UpstreamSourceAnchor
    variants: tuple[MatchedSourceVariant, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.pair_id != PAIR_ID:
            _fail("pair_identity_mismatch")
        if self.population_classification != "curated_controlled_injection":
            _fail("pair_classification_mismatch")
        if self.taxonomy_id != "config-change-01":
            _fail("pair_taxonomy_mismatch")
        if self.mutation_operator_id != "toggle-input-save-enabled-v1":
            _fail("pair_operator_mismatch")
        if self.baseline.origin != self.anchor.origin:
            _fail("source_anchor_baseline_mismatch")
        if self.baseline.commit != self.anchor.commit:
            _fail("source_anchor_baseline_mismatch")
        if len(self.variants) != 2 or {item.variant_id for item in self.variants} != set(VARIANT_IDS):
            _fail("pair_variant_mismatch")
        ordered = tuple(sorted(self.variants, key=lambda item: item.variant_id))
        if ordered != self.variants:
            _fail("pair_variant_order_mismatch")
        for variant in self.variants:
            if (
                variant.population_classification != self.population_classification
                or variant.taxonomy_id != self.taxonomy_id
                or variant.mutation_operator_id != self.mutation_operator_id
                or variant.difference_field != "binding.input.isSaveEnabled"
            ):
                _fail("matched_pair_contract_mismatch")
        control = self.variant(CONTROL_VARIANT)
        defect = self.variant(DEFECT_VARIANT)
        if control.right_hand_side != "true" or defect.right_hand_side != "false":
            _fail("pair_difference_mismatch")
        normalized_control = control.patch_text.replace(
            "isSaveEnabled = true", "isSaveEnabled = VALUE"
        )
        normalized_defect = defect.patch_text.replace(
            "isSaveEnabled = false", "isSaveEnabled = VALUE"
        )
        if normalized_control != normalized_defect:
            _fail("matched_pair_patch_mismatch")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    def variant(self, variant_id: str) -> MatchedSourceVariant:
        for variant in self.variants:
            if variant.variant_id == variant_id:
                return variant
        raise KeyError(variant_id)

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "pair_id": self.pair_id,
            "population_classification": self.population_classification,
            "taxonomy_id": self.taxonomy_id,
            "mutation_operator_id": self.mutation_operator_id,
            "baseline": self.baseline.to_dict(),
            "upstream_source_anchor": self.anchor.to_dict(),
            "variants": [item.to_dict() for item in self.variants],
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MatchedRuntimeSourcePair:
        _reject_unknown(
            data,
            {
                "schema_version",
                "pair_id",
                "population_classification",
                "taxonomy_id",
                "mutation_operator_id",
                "baseline",
                "upstream_source_anchor",
                "variants",
                "identity_sha256",
            },
            "source_pair_schema_mismatch",
        )
        baseline = SourceBaseline.from_dict(
            _as_mapping(data.get("baseline"), "source_pair_schema_mismatch")
        )
        anchor = UpstreamSourceAnchor.from_dict(
            _as_mapping(data.get("upstream_source_anchor"), "source_pair_schema_mismatch")
        )
        variants = _as_list(data.get("variants"), "source_pair_schema_mismatch")
        try:
            pair = cls(
                pair_id=data["pair_id"],
                population_classification=data["population_classification"],
                taxonomy_id=data["taxonomy_id"],
                mutation_operator_id=data["mutation_operator_id"],
                baseline=baseline,
                anchor=anchor,
                variants=tuple(
                    MatchedSourceVariant.from_dict(
                        _as_mapping(item, "source_pair_schema_mismatch"),
                        classification=data["population_classification"],
                        taxonomy_id=data["taxonomy_id"],
                        mutation_operator_id=data["mutation_operator_id"],
                    )
                    for item in variants
                ),
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except KeyError:
            _fail("source_pair_schema_mismatch")
        identity = data.get("identity_sha256")
        if identity is not None and identity != pair.identity_sha256:
            _fail("source_pair_digest_mismatch")
        return pair


@dataclass(frozen=True)
class OpenCalcContextAcquisition:
    """The bounded pristine-source Context Acquisition receipt."""

    result: ContextAcquisitionResult
    required_paths: tuple[str, ...] = REQUIRED_CONTEXT_PATHS
    adapters: tuple[str, ...] = REQUIRED_CONTEXT_ADAPTERS
    engine_adapters: tuple[str, ...] = ENGINE_CONTEXT_ADAPTERS
    materialized_patch_applied: bool = False
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.result, ContextAcquisitionResult):
            _fail("context_acquisition_invalid")
        if self.required_paths != REQUIRED_CONTEXT_PATHS:
            _fail("context_commitment_mismatch")
        if self.adapters != REQUIRED_CONTEXT_ADAPTERS:
            _fail("context_adapter_mismatch")
        if self.engine_adapters != ENGINE_CONTEXT_ADAPTERS:
            _fail("context_engine_adapter_mismatch")
        if self.materialized_patch_applied is not False:
            _fail("discovery_source_materialization_mutated")
        if self.target.scope != REQUIRED_CONTEXT_PATHS:
            _fail("context_commitment_mismatch")
        if self.target.discovery_budget != REQUIRED_CONTEXT_BUDGET:
            _fail("context_budget_mismatch")
        receipt = self.result.receipt
        if receipt.requested_evidence != ENGINE_CONTEXT_ADAPTERS:
            _fail("context_engine_adapter_mismatch")
        if tuple(item.adapter_id for item in receipt.adapters) != ENGINE_CONTEXT_ADAPTERS:
            _fail("context_engine_adapter_mismatch")
        if receipt.no_diff is not True:
            _fail("context_diff_present")
        if receipt.discovery_budget != REQUIRED_CONTEXT_BUDGET:
            _fail("context_budget_mismatch")
        if receipt.budget_used != REQUIRED_CONTEXT_BUDGET:
            _fail("context_budget_exhausted")
        if tuple(receipt.inspected_scope) != tuple(sorted(REQUIRED_CONTEXT_PATHS)):
            _fail("context_required_path_not_inspected")
        if receipt.skipped_scope:
            _fail("context_required_path_skipped")
        if any(item.status == "budget-exhausted" for item in receipt.adapters):
            _fail("context_budget_exhausted")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def target(self) -> ProjectTarget:
        return self.result.target

    @property
    def source_root(self) -> str:
        return self.result.target.worktree

    @property
    def source_tree_sha256(self) -> str:
        return self.result.graph.source_tree_sha256 or ""

    @property
    def unknown_fact_ids(self) -> tuple[str, ...]:
        return tuple(
            fact.fact_id for fact in self.result.graph.facts if fact.status == "unknown"
        )

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "target_kind": "ProjectTarget",
            "target": self.target.to_dict(),
            "required_paths": list(self.required_paths),
            "adapters": list(self.adapters),
            "engine_adapters": list(self.engine_adapters),
            "discovery_budget": self.result.receipt.discovery_budget,
            "budget_used": self.result.receipt.budget_used,
            "inspected_paths": list(self.result.receipt.inspected_scope),
            "skipped_paths": list(self.result.receipt.skipped_scope),
            "unknown_fact_ids": list(self.unknown_fact_ids),
            "source_root": self.source_root,
            "source_tree_sha256": self.source_tree_sha256,
            "patch_applied": self.materialized_patch_applied,
            "result": self.result.to_dict(),
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OpenCalcContextAcquisition:
        _reject_unknown(
            data,
            {
                "schema_version",
                "target_kind",
                "target",
                "required_paths",
                "adapters",
                "engine_adapters",
                "discovery_budget",
                "budget_used",
                "inspected_paths",
                "skipped_paths",
                "unknown_fact_ids",
                "source_root",
                "source_tree_sha256",
                "patch_applied",
                "result",
                "identity_sha256",
            },
            "context_schema_mismatch",
        )
        try:
            raw_paths = _as_list(data["required_paths"], "context_schema_mismatch")
            raw_adapters = _as_list(data["adapters"], "context_schema_mismatch")
            raw_engine = _as_list(data["engine_adapters"], "context_schema_mismatch")
            raw_unknown = _as_list(data["unknown_fact_ids"], "context_schema_mismatch")
            acquisition = cls(
                result=ContextAcquisitionResult.from_dict(
                    _as_mapping(data["result"], "context_schema_mismatch")
                ),
                required_paths=tuple(raw_paths),
                adapters=tuple(raw_adapters),
                engine_adapters=tuple(raw_engine),
                materialized_patch_applied=data["patch_applied"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except (KeyError, DiscoveryContractError, ChangeTargetAdmissionError):
            _fail("context_schema_mismatch")
        if tuple(raw_unknown) != acquisition.unknown_fact_ids:
            _fail("context_unknown_fact_mismatch")
        expected = acquisition.to_dict(include_identity=False)
        for field in (
            "target_kind",
            "target",
            "required_paths",
            "adapters",
            "engine_adapters",
            "discovery_budget",
            "budget_used",
            "inspected_paths",
            "skipped_paths",
            "unknown_fact_ids",
            "source_root",
            "source_tree_sha256",
            "patch_applied",
            "result",
        ):
            if data.get(field) != expected[field]:
                _fail("context_identity_mismatch")
        identity = data.get("identity_sha256")
        if identity is not None and identity != acquisition.identity_sha256:
            _fail("context_identity_mismatch")
        return acquisition


def _normalized_identity(value: Any) -> Any:
    """Remove delivery paths while retaining all source bytes and identities."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in {"worktree", "source_root", "worktree_path"}:
                result[key] = "<pristine-source-root>"
            else:
                result[key] = _normalized_identity(item)
        return result
    if isinstance(value, list):
        return [_normalized_identity(item) for item in value]
    return value


def _project_normalized_identity(
    value: Any,
    *,
    path: tuple[str, ...] = (),
) -> Any:
    """Normalize delivery paths and nested receipts for ProjectTarget identity."""

    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key == "identity_sha256" and path[-1:] == ("context_acquisition",):
                continue
            if key in {"worktree", "source_root", "worktree_path"}:
                result[key] = "<project-materialization-path>"
            else:
                result[key] = _project_normalized_identity(item, path=(*path, key))
        return result
    if isinstance(value, list):
        return [
            _project_normalized_identity(item, path=path) for item in value
        ]
    return value


@dataclass(frozen=True)
class SyntheticProjectCommit:
    """Receipt for one deterministic, source-materialized ProjectTarget."""

    variant_id: str
    source_id: str
    parent_commit: str
    parent_tree_sha256: str
    parent_source_tree_sha256: str
    synthetic_commit: str
    synthetic_tree_sha256: str
    synthetic_source_tree_sha256: str
    target_file_sha256: str
    patch_sha256: str
    result_diff_sha256: str
    author_name: str
    author_email: str
    author_timestamp: str
    committer_name: str
    committer_email: str
    committer_timestamp: str
    message: str
    worktree_path: str
    patch_applied: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.variant_id not in VARIANT_IDS:
            _fail("synthetic_variant_mismatch")
        if self.source_id != f"{PAIR_ID}-{self.variant_id}":
            _fail("synthetic_source_id_mismatch")
        for field in (
            "parent_commit",
            "synthetic_commit",
            "parent_tree_sha256",
            "synthetic_tree_sha256",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not _HEX_40.fullmatch(value):
                _fail("synthetic_git_identity_invalid")
        for field in (
            "parent_source_tree_sha256",
            "synthetic_source_tree_sha256",
            "target_file_sha256",
            "patch_sha256",
            "result_diff_sha256",
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not _HEX_64.fullmatch(value):
                _fail("synthetic_digest_invalid")
        if self.parent_commit != UPSTREAM_COMMIT:
            _fail("synthetic_parent_commit_mismatch")
        if self.parent_tree_sha256 != UPSTREAM_TREE_SHA256:
            _fail("synthetic_parent_tree_mismatch")
        if self.synthetic_commit == self.parent_commit:
            _fail("synthetic_commit_unchanged")
        if self.synthetic_tree_sha256 == self.parent_tree_sha256:
            _fail("synthetic_tree_unchanged")
        for field in (
            "author_name",
            "author_email",
            "author_timestamp",
            "committer_name",
            "committer_email",
            "committer_timestamp",
            "message",
            "worktree_path",
        ):
            _required_text(getattr(self, field), f"synthetic_{field}")
        if (
            self.author_name != SYNTHETIC_AUTHOR_NAME
            or self.author_email != SYNTHETIC_AUTHOR_EMAIL
            or self.author_timestamp != SYNTHETIC_COMMIT_TIMESTAMP
            or self.committer_name != SYNTHETIC_AUTHOR_NAME
            or self.committer_email != SYNTHETIC_AUTHOR_EMAIL
            or self.committer_timestamp != SYNTHETIC_COMMIT_TIMESTAMP
            or self.message != SYNTHETIC_COMMIT_MESSAGE
        ):
            _fail("synthetic_commit_metadata_mismatch")
        if not Path(self.worktree_path).is_absolute():
            _fail("synthetic_worktree_path_invalid")
        if self.patch_applied is not True:
            _fail("synthetic_patch_not_applied")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def commit(self) -> str:
        return self.synthetic_commit

    @property
    def source_commit(self) -> str:
        return self.synthetic_commit

    @property
    def tree(self) -> str:
        return self.synthetic_tree_sha256

    @property
    def result_tree_sha256(self) -> str:
        return self.synthetic_tree_sha256

    @property
    def parent(self) -> str:
        return self.parent_commit

    @property
    def source_tree_sha256(self) -> str:
        return self.synthetic_source_tree_sha256

    @property
    def result_source_tree_sha256(self) -> str:
        return self.synthetic_source_tree_sha256

    @property
    def receipt_identity_sha256(self) -> str:
        return self.identity_sha256

    @property
    def result_identity_sha256(self) -> str:
        return self.identity_sha256

    @property
    def patch_identity_sha256(self) -> str:
        return self.patch_sha256

    @property
    def identity_sha256(self) -> str:
        return _digest(
            {
                key: value
                for key, value in self.to_dict(include_identity=False).items()
                if key not in {"worktree_path", "result_identity_sha256"}
            }
        )

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "document_kind": "synthetic_project_target_commit_receipt",
            "variant_id": self.variant_id,
            "source_id": self.source_id,
            "parent_commit": self.parent_commit,
            "parent_tree_sha256": self.parent_tree_sha256,
            "parent_source_tree_sha256": self.parent_source_tree_sha256,
            "synthetic_commit": self.synthetic_commit,
            "synthetic_tree_sha256": self.synthetic_tree_sha256,
            "synthetic_source_tree_sha256": self.synthetic_source_tree_sha256,
            "target_file_sha256": self.target_file_sha256,
            "patch_sha256": self.patch_sha256,
            "result_diff_sha256": self.result_diff_sha256,
            "author_name": self.author_name,
            "author_email": self.author_email,
            "author_timestamp": self.author_timestamp,
            "committer_name": self.committer_name,
            "committer_email": self.committer_email,
            "committer_timestamp": self.committer_timestamp,
            "message": self.message,
            "patch_applied": self.patch_applied,
        }
        result["worktree_path"] = self.worktree_path
        if include_identity:
            result["result_identity_sha256"] = self.identity_sha256
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SyntheticProjectCommit:
        _reject_unknown(
            data,
            {
                "schema_version",
                "document_kind",
                "variant_id",
                "source_id",
                "parent_commit",
                "parent_tree_sha256",
                "parent_source_tree_sha256",
                "synthetic_commit",
                "synthetic_tree_sha256",
                "synthetic_source_tree_sha256",
                "target_file_sha256",
                "patch_sha256",
                "result_diff_sha256",
                "author_name",
                "author_email",
                "author_timestamp",
                "committer_name",
                "committer_email",
                "committer_timestamp",
                "message",
                "worktree_path",
                "patch_applied",
                "result_identity_sha256",
                "identity_sha256",
            },
            "synthetic_commit_schema_mismatch",
        )
        if data.get("document_kind") != "synthetic_project_target_commit_receipt":
            _fail("synthetic_commit_document_kind_mismatch")
        try:
            receipt = cls(
                variant_id=data["variant_id"],
                source_id=data["source_id"],
                parent_commit=data["parent_commit"],
                parent_tree_sha256=data["parent_tree_sha256"],
                parent_source_tree_sha256=data["parent_source_tree_sha256"],
                synthetic_commit=data["synthetic_commit"],
                synthetic_tree_sha256=data["synthetic_tree_sha256"],
                synthetic_source_tree_sha256=data["synthetic_source_tree_sha256"],
                target_file_sha256=data["target_file_sha256"],
                patch_sha256=data["patch_sha256"],
                result_diff_sha256=data["result_diff_sha256"],
                author_name=data["author_name"],
                author_email=data["author_email"],
                author_timestamp=data["author_timestamp"],
                committer_name=data["committer_name"],
                committer_email=data["committer_email"],
                committer_timestamp=data["committer_timestamp"],
                message=data["message"],
                worktree_path=data["worktree_path"],
                patch_applied=data["patch_applied"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except KeyError:
            _fail("synthetic_commit_schema_mismatch")
        identity = data.get("identity_sha256")
        if identity is not None and identity != receipt.identity_sha256:
            _fail("synthetic_commit_identity_mismatch")
        result_identity = data.get("result_identity_sha256")
        if result_identity is not None and result_identity != receipt.identity_sha256:
            _fail("synthetic_commit_identity_mismatch")
        return receipt


SyntheticCommitReceipt = SyntheticProjectCommit
ProjectTargetMaterializationReceipt = SyntheticProjectCommit


@dataclass(frozen=True)
class SourceRichDiscoveryPackage:
    """An auditor-only admitted source-rich ChangeTarget or ProjectTarget package."""

    package_id: str
    catalog_id: str
    target: ChangeTarget | ProjectTarget
    pair: MatchedRuntimeSourcePair
    variant: MatchedSourceVariant
    context_acquisition: OpenCalcContextAcquisition
    campaign: DiscoveryCampaignPackage
    behavior_delta: BehaviorDelta | None
    contract_drift: ContractDrift | None
    quality_contract: QualityContract
    risk_prior: RiskPrior
    attack_operator: AttackOperator
    risk_hypothesis: RiskHypothesis
    attack_plan: AttackPlan
    risk_priority: RiskPriority
    exploration_policy_id: str
    schema_version: int = SCHEMA_VERSION
    synthetic_commit: SyntheticProjectCommit | None = None

    def __post_init__(self) -> None:
        _required_text(self.package_id, "package_id")
        _required_text(self.catalog_id, "catalog_id")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool):
            _fail("schema_version_mismatch")
        if self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")
        if not isinstance(self.target, (ChangeTarget, ProjectTarget)):
            _fail("package_target_invalid")
        if self.variant != self.pair.variant(self.variant.variant_id):
            _fail("package_variant_mismatch")
        if self.target.source_origin != self.pair.baseline.origin:
            _fail("package_source_origin_mismatch")
        if self.target.worktree != self.context_acquisition.source_root:
            _fail("package_context_source_mismatch")
        if self.context_acquisition.target.target_id != self.target.target_id:
            _fail("package_context_target_mismatch")
        if self.context_acquisition.materialized_patch_applied:
            _fail("discovery_source_materialization_mutated")
        if isinstance(self.target, ChangeTarget):
            if self.target.source_commit != self.pair.baseline.commit:
                _fail("package_source_commit_mismatch")
            if self.target.diff_sha256 != self.variant.patch_sha256:
                _fail("package_patch_mismatch")
            if self.behavior_delta is None or self.contract_drift is None:
                _fail("package_change_contract_missing")
            if self.synthetic_commit is not None:
                _fail("package_synthetic_commit_unexpected")
        else:
            if self.target.source_commit == self.pair.baseline.commit:
                _fail("package_project_source_commit_mismatch")
            if self.target.scope != REQUIRED_CONTEXT_PATHS:
                _fail("package_scope_mismatch")
            if self.target.discovery_budget != REQUIRED_CONTEXT_BUDGET:
                _fail("package_budget_mismatch")
            if self.behavior_delta is not None or self.contract_drift is not None:
                _fail("package_project_diff_present")
            receipt = self.synthetic_commit
            if not isinstance(receipt, SyntheticProjectCommit):
                _fail("package_synthetic_commit_missing")
            if receipt.variant_id != self.variant.variant_id or receipt.source_id != self.source_id:
                _fail("package_synthetic_commit_mismatch")
            if receipt.synthetic_commit != self.target.source_commit:
                _fail("package_source_commit_mismatch")
            if receipt.worktree_path != self.target.worktree:
                _fail("package_synthetic_worktree_mismatch")
            if self.context_acquisition.target != self.target:
                _fail("package_context_target_mismatch")
            if receipt.patch_sha256 != self.variant.patch_sha256:
                _fail("package_patch_mismatch")
            if receipt.synthetic_source_tree_sha256 != self.context_acquisition.source_tree_sha256:
                _fail("package_source_tree_mismatch")
            if receipt.parent_commit != self.pair.baseline.commit:
                _fail("package_parent_commit_mismatch")
            if receipt.parent_tree_sha256 != self.pair.baseline.tree_sha256:
                _fail("package_parent_tree_mismatch")
        if self.campaign.campaign.status != "plan-admitted":
            _fail("campaign_not_admitted")
        if self.campaign.campaign.target != self.target:
            _fail("package_campaign_target_mismatch")
        if (
            self.behavior_delta is not None
            and self.behavior_delta.target_id != self.target.target_id
        ):
            _fail("package_behavior_delta_mismatch")
        if (
            self.contract_drift is not None
            and self.contract_drift.contract_id != QUALITY_CONTRACT_ID
        ):
            _fail("package_contract_drift_mismatch")
        if self.exploration_policy_id != EXPLORATION_POLICY_ID:
            _fail("package_exploration_policy_mismatch")
        campaign = self.campaign.campaign
        if campaign.quality_contracts != (self.quality_contract,):
            _fail("package_quality_contract_mismatch")
        if campaign.risk_priors != (self.risk_prior,):
            _fail("package_risk_prior_mismatch")
        if campaign.attack_operators != (self.attack_operator,):
            _fail("package_attack_operator_mismatch")
        if campaign.hypotheses != (self.risk_hypothesis,):
            _fail("package_risk_hypothesis_mismatch")
        if campaign.attack_plans != (self.attack_plan,):
            _fail("package_attack_plan_mismatch")
        if self.campaign.risk_priority != self.risk_priority:
            _fail("package_risk_priority_mismatch")
        if self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def source_id(self) -> str:
        return self.variant.source_id

    @property
    def identity_sha256(self) -> str:
        if isinstance(self.target, ProjectTarget):
            return _digest(_project_normalized_identity(self.to_dict(include_identity=False)))
        return _digest(_normalized_identity(self.to_dict(include_identity=False)))

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        is_change = isinstance(self.target, ChangeTarget)
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "package_kind": "source_rich_discovery_package",
            "package_id": self.package_id,
            "catalog_id": self.catalog_id,
            "target_kind": "ChangeTarget" if is_change else "ProjectTarget",
            "variant": self.variant.variant_id,
            "source_id": self.source_id,
            "target": self.target.to_dict(),
            "matched_source_pair": self.pair.to_dict(),
            "source_provenance": {},
            "context_acquisition": self.context_acquisition.to_dict(),
            "campaign": self.campaign.to_dict(),
            "neutral_contracts": {
                "quality_contract": self.quality_contract.to_dict(),
                "risk_prior": self.risk_prior.to_dict(),
                "attack_operator": self.attack_operator.to_dict(),
                "risk_hypothesis": self.risk_hypothesis.to_dict(),
                "attack_plan": self.attack_plan.to_dict(),
                "risk_priority": self.risk_priority.to_dict(),
            },
            "exploration_policy_id": self.exploration_policy_id,
        }
        if is_change:
            assert isinstance(self.target, ChangeTarget)
            assert self.behavior_delta is not None
            assert self.contract_drift is not None
            result["source_provenance"] = {
                "origin": self.pair.baseline.origin,
                "commit": self.pair.baseline.commit,
                "tree_sha256": self.pair.baseline.tree_sha256,
                "archive_sha256": self.pair.baseline.archive_sha256,
                "anchor_identity_sha256": self.pair.anchor.identity_sha256,
                "target_path": self.pair.anchor.path,
                "target_file_sha256": self.pair.anchor.target_file_sha256,
                "context_sha256": self.pair.anchor.context_sha256,
                "required_occurrences": self.pair.anchor.required_occurrences,
            }
            result["patch"] = {
                "ref": self.target.diff_ref,
                "path": self.pair.anchor.path,
                "text": self.variant.patch_text,
                "sha256": self.variant.patch_sha256,
                "field": self.variant.difference_field,
                "right_hand_side": self.variant.right_hand_side,
            }
            result["discovery_source_materialization"] = {
                "source_root": self.context_acquisition.source_root,
                "pristine_tree_sha256": self.pair.baseline.tree_sha256,
                "patch_applied": self.context_acquisition.materialized_patch_applied,
                "runtime_build_worktree": False,
            }
            result["behavior_delta"] = self.behavior_delta.to_dict()
            result["contract_drift"] = self.contract_drift.to_dict()
        else:
            assert self.synthetic_commit is not None
            receipt = self.synthetic_commit
            result["source_provenance"] = {
                "origin": self.pair.baseline.origin,
                "commit": receipt.synthetic_commit,
                "tree_sha256": receipt.synthetic_tree_sha256,
                "source_tree_sha256": receipt.synthetic_source_tree_sha256,
                "baseline_commit": self.pair.baseline.commit,
                "baseline_tree_sha256": self.pair.baseline.tree_sha256,
                "archive_sha256": self.pair.baseline.archive_sha256,
                "anchor_identity_sha256": self.pair.anchor.identity_sha256,
                "target_path": self.pair.anchor.path,
                "baseline_target_file_sha256": self.pair.anchor.target_file_sha256,
                "target_file_sha256": receipt.target_file_sha256,
                "context_sha256": self.pair.anchor.context_sha256,
                "required_occurrences": self.pair.anchor.required_occurrences,
            }
            result["source_injection"] = {
                "ref": _patch_artifact_ref(self.variant.variant_id),
                "path": self.pair.anchor.path,
                "text": self.variant.patch_text,
                "sha256": self.variant.patch_sha256,
                "field": self.variant.difference_field,
                "right_hand_side": self.variant.right_hand_side,
            }
            result["discovery_source_materialization"] = {
                "source_root": self.context_acquisition.source_root,
                "pristine_tree_sha256": self.pair.baseline.tree_sha256,
                "pristine_source_tree_sha256": receipt.parent_source_tree_sha256,
                "patch_applied": receipt.patch_applied,
                "runtime_build_worktree": False,
                "synthetic_commit": receipt.synthetic_commit,
                "synthetic_tree_sha256": receipt.synthetic_tree_sha256,
                "receipt_identity_sha256": receipt.identity_sha256,
            }
            result["synthetic_project_commit"] = receipt.to_dict()

        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceRichDiscoveryPackage:
        _reject_unknown(
            data,
            {
                "schema_version",
                "package_kind",
                "package_id",
                "catalog_id",
                "target_kind",
                "variant",
                "source_id",
                "target",
                "matched_source_pair",
                "source_provenance",
                "patch",
                "source_injection",
                "discovery_source_materialization",
                "synthetic_project_commit",
                "context_acquisition",
                "campaign",
                "behavior_delta",
                "contract_drift",
                "neutral_contracts",
                "exploration_policy_id",
                "identity_sha256",
            },
            "package_schema_mismatch",
        )
        if data.get("package_kind") != "source_rich_discovery_package":
            _fail("package_kind_mismatch")
        target_kind = data.get("target_kind")
        if target_kind not in {"ChangeTarget", "ProjectTarget"}:
            _fail("package_target_kind_mismatch")
        target_data = _as_mapping(data.get("target"), "package_schema_mismatch")
        try:
            if target_kind == "ChangeTarget":
                target = ChangeTarget.from_dict(target_data)
            else:
                target = ProjectTarget.from_dict(target_data)
        except (DiscoveryContractError, ValueError) as error:
            raise ChangeTargetAdmissionError("package_schema_mismatch") from error
        if target_kind == "ProjectTarget" and (
            data.get("patch") is not None
            or data.get("behavior_delta") is not None
            or data.get("contract_drift") is not None
        ):
            _fail("package_project_diff_present")
        if target_kind == "ChangeTarget" and (
            data.get("source_injection") is not None
            or data.get("synthetic_project_commit") is not None
        ):
            _fail("package_change_materialization_mismatch")
        pair = MatchedRuntimeSourcePair.from_dict(
            _as_mapping(data.get("matched_source_pair"), "package_schema_mismatch")
        )
        contracts = _as_mapping(data.get("neutral_contracts"), "package_schema_mismatch")
        try:
            package = cls(
                package_id=data["package_id"],
                catalog_id=data["catalog_id"],
                target=target,
                pair=pair,
                variant=pair.variant(data["variant"]),
                context_acquisition=OpenCalcContextAcquisition.from_dict(
                    _as_mapping(data["context_acquisition"], "package_schema_mismatch")
                ),
                campaign=DiscoveryCampaignPackage.from_dict(
                    _as_mapping(data["campaign"], "package_schema_mismatch")
                ),
                behavior_delta=(
                    BehaviorDelta.from_dict(
                        _as_mapping(data["behavior_delta"], "package_schema_mismatch")
                    )
                    if target_kind == "ChangeTarget"
                    else None
                ),
                contract_drift=(
                    ContractDrift.from_dict(
                        _as_mapping(data["contract_drift"], "package_schema_mismatch")
                    )
                    if target_kind == "ChangeTarget"
                    else None
                ),
                quality_contract=QualityContract.from_dict(
                    _as_mapping(contracts["quality_contract"], "package_schema_mismatch")
                ),
                risk_prior=RiskPrior.from_dict(
                    _as_mapping(contracts["risk_prior"], "package_schema_mismatch")
                ),
                attack_operator=AttackOperator.from_dict(
                    _as_mapping(contracts["attack_operator"], "package_schema_mismatch")
                ),
                risk_hypothesis=RiskHypothesis.from_dict(
                    _as_mapping(contracts["risk_hypothesis"], "package_schema_mismatch")
                ),
                attack_plan=AttackPlan.from_dict(
                    _as_mapping(contracts["attack_plan"], "package_schema_mismatch")
                ),
                risk_priority=RiskPriority.from_dict(
                    _as_mapping(contracts["risk_priority"], "package_schema_mismatch")
                ),
                exploration_policy_id=data["exploration_policy_id"],
                schema_version=data.get("schema_version", SCHEMA_VERSION),
                synthetic_commit=(
                    SyntheticProjectCommit.from_dict(
                        _as_mapping(data["synthetic_project_commit"], "package_schema_mismatch")
                    )
                    if target_kind == "ProjectTarget"
                    else None
                ),
            )
        except (KeyError, DiscoveryContractError, OpenCalcDiscoveryError):
            _fail("package_schema_mismatch")
        expected = package.to_dict(include_identity=False)
        for field, expected_value in expected.items():
            if data.get(field) != expected_value:
                _fail("package_identity_mismatch")
        identity = data.get("identity_sha256")
        if identity is not None and identity != package.identity_sha256:
            _fail("package_identity_mismatch")
        return package


@dataclass(frozen=True)
class BlindRuntimeProjection:
    """The only target-neutral discovery data allowed toward the driver."""

    projection_id: str
    opaque_lane_id: str
    opaque_identity: str
    family_id: str
    family_version: str
    quality_contract_id: str
    risk_prior_id: str
    attack_operator_id: str
    risk_hypothesis_id: str
    attack_plan_id: str
    exploration_policy_id: str
    context_budget: int
    required_context_count: int
    projection_commitment: str
    driver_plan_commitment: str
    recipe_commitment: str
    run_spec_commitment: str
    model_calls: bool = False
    diff: None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.opaque_lane_id, "projection_lane_id")
        if not re.fullmatch(r"ocrc-v1-lane-0[1-4]", self.opaque_lane_id):
            _fail("projection_lane_identity_mismatch")
        for field in (
            "projection_id",
            "opaque_identity",
            "family_id",
            "family_version",
            "quality_contract_id",
            "risk_prior_id",
            "attack_operator_id",
            "risk_hypothesis_id",
            "attack_plan_id",
            "exploration_policy_id",
        ):
            _required_text(getattr(self, field), f"projection_{field}")
        for field in (
            "opaque_identity",
            "projection_commitment",
            "driver_plan_commitment",
            "recipe_commitment",
            "run_spec_commitment",
        ):
            if not _HEX_64.fullmatch(getattr(self, field)):
                _fail("projection_commitment_invalid")
        if self.family_id != FAMILY_ID or self.family_version != FAMILY_VERSION:
            _fail("projection_family_mismatch")
        expected_contracts = {
            "quality_contract_id": QUALITY_CONTRACT_ID,
            "risk_prior_id": RISK_PRIOR_ID,
            "attack_operator_id": ATTACK_OPERATOR_ID,
            "risk_hypothesis_id": RISK_HYPOTHESIS_ID,
            "attack_plan_id": ATTACK_PLAN_ID,
            "exploration_policy_id": EXPLORATION_POLICY_ID,
        }
        if any(
            getattr(self, field) != expected
            for field, expected in expected_contracts.items()
        ):
            _fail("projection_contract_mismatch")
        if self.context_budget != REQUIRED_CONTEXT_BUDGET:
            _fail("projection_context_budget_mismatch")
        if self.required_context_count != len(REQUIRED_CONTEXT_PATHS):
            _fail("projection_context_count_mismatch")
        if self.model_calls is not False:
            _fail("projection_model_policy_mismatch")
        if self.diff is not None:
            _fail("projection_diff_present")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")
        expected_id = _projection_id(
            self.opaque_lane_id,
            self.opaque_identity,
            self.quality_contract_id,
            self.risk_prior_id,
            self.attack_operator_id,
            self.risk_hypothesis_id,
            self.attack_plan_id,
            self.exploration_policy_id,
        )
        if self.projection_id != expected_id:
            _fail("projection_identity_mismatch")

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "document_kind": "blind_runtime_projection",
            "family_id": self.family_id,
            "family_version": self.family_version,
            "projection_id": self.projection_id,
            "opaque_lane_id": self.opaque_lane_id,
            "opaque_identity": self.opaque_identity,
            "quality_contract_id": self.quality_contract_id,
            "risk_prior_id": self.risk_prior_id,
            "attack_operator_id": self.attack_operator_id,
            "risk_hypothesis_id": self.risk_hypothesis_id,
            "attack_plan_id": self.attack_plan_id,
            "exploration_policy_id": self.exploration_policy_id,
            "context_budget": self.context_budget,
            "required_context_count": self.required_context_count,
            "execution_commitments": {
                "projection": self.projection_commitment,
                "driver_plan": self.driver_plan_commitment,
                "recipe": self.recipe_commitment,
                "run_spec": self.run_spec_commitment,
            },
            "model_policy": {"model_calls": self.model_calls},
            "diff": self.diff,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BlindRuntimeProjection:
        try:
            _reject_unknown(
                data,
                {
                    "schema_version",
                    "document_kind",
                    "family_id",
                    "family_version",
                    "projection_id",
                    "opaque_lane_id",
                    "opaque_identity",
                    "quality_contract_id",
                    "risk_prior_id",
                    "attack_operator_id",
                    "risk_hypothesis_id",
                    "attack_plan_id",
                    "exploration_policy_id",
                    "context_budget",
                    "required_context_count",
                    "execution_commitments",
                    "model_policy",
                    "diff",
                },
                "projection_leakage",
            )
            if data.get("document_kind") != "blind_runtime_projection":
                _fail("projection_document_kind_mismatch")
            commitments = _as_mapping(
                data.get("execution_commitments"), "projection_leakage"
            )
            _reject_unknown(
                commitments,
                {"projection", "driver_plan", "recipe", "run_spec"},
                "projection_leakage",
            )
            model_policy = _as_mapping(data.get("model_policy"), "projection_leakage")
            _reject_unknown(model_policy, {"model_calls"}, "projection_leakage")
            projection = cls(
                projection_id=data["projection_id"],
                opaque_lane_id=data["opaque_lane_id"],
                opaque_identity=data["opaque_identity"],
                family_id=data["family_id"],
                family_version=data["family_version"],
                quality_contract_id=data["quality_contract_id"],
                risk_prior_id=data["risk_prior_id"],
                attack_operator_id=data["attack_operator_id"],
                risk_hypothesis_id=data["risk_hypothesis_id"],
                attack_plan_id=data["attack_plan_id"],
                exploration_policy_id=data["exploration_policy_id"],
                context_budget=data["context_budget"],
                required_context_count=data["required_context_count"],
                projection_commitment=commitments["projection"],
                driver_plan_commitment=commitments["driver_plan"],
                recipe_commitment=commitments["recipe"],
                run_spec_commitment=commitments["run_spec"],
                model_calls=model_policy["model_calls"],
                diff=data.get("diff"),
                schema_version=data.get("schema_version", SCHEMA_VERSION),
            )
        except (KeyError, TypeError, ChangeTargetAdmissionError):
            if isinstance(locals().get("projection"), BlindRuntimeProjection):
                raise
            _fail("projection_leakage")
        _assert_no_projection_leakage(projection.to_dict())
        return projection


def _projection_id(
    lane_id: str,
    opaque_identity: str,
    quality_contract_id: str,
    risk_prior_id: str,
    operator_id: str,
    hypothesis_id: str,
    plan_id: str,
    exploration_policy_id: str,
) -> str:
    return "ocrc-v1-projection-" + _digest(
        {
            "lane": lane_id,
            "identity": opaque_identity,
            "quality_contract": quality_contract_id,
            "risk_prior": risk_prior_id,
            "operator": operator_id,
            "hypothesis": hypothesis_id,
            "plan": plan_id,
            "exploration_policy": exploration_policy_id,
        }
    )[:24]


def _walk_strings(value: Any) -> Sequence[str]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        strings: list[str] = []
        for key, item in value.items():
            strings.extend(_walk_strings(key))
            strings.extend(_walk_strings(item))
        return tuple(strings)
    if isinstance(value, (list, tuple)):
        strings = []
        for item in value:
            strings.extend(_walk_strings(item))
        return tuple(strings)
    return ()


def _assert_no_projection_leakage(value: Mapping[str, Any]) -> None:
    haystack = "\n".join(_walk_strings(value)).lower()
    if any(term in haystack for term in PROJECTION_LEAKAGE_TERMS):
        _fail("projection_leakage")


@dataclass(frozen=True)
class LeakageAudit:
    """Receipt proving every driver-visible projection was checked."""

    checked_projection_ids: tuple[str, ...]
    serialization_sha256: str
    status: str = "passed"
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _text_tuple(self.checked_projection_ids, "checked_projection_ids", allow_empty=False)
        if len(set(self.checked_projection_ids)) != len(self.checked_projection_ids):
            _fail("projection_identity_mismatch")
        _required_text(self.serialization_sha256, "leakage_audit_digest")
        if not _HEX_64.fullmatch(self.serialization_sha256):
            _fail("leakage_audit_digest_invalid")
        if self.status != "passed":
            _fail("leakage_audit_failed")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "checked_projection_ids": list(self.checked_projection_ids),
            "serialization_sha256": self.serialization_sha256,
        }


def audit_projection_leakage(
    projections: Sequence[BlindRuntimeProjection | Mapping[str, Any]],
) -> LeakageAudit:
    """Validate every verifier/driver-visible projection without redaction."""

    parsed: list[BlindRuntimeProjection] = []
    for value in projections:
        if isinstance(value, BlindRuntimeProjection):
            projection = value
            _assert_no_projection_leakage(projection.to_dict())
        elif isinstance(value, Mapping):
            projection = BlindRuntimeProjection.from_dict(value)
        else:
            _fail("projection_leakage")
        parsed.append(projection)
    if not parsed:
        _fail("projection_leakage")
    shapes = [tuple(projection.to_dict().keys()) for projection in parsed]
    if any(shape != shapes[0] for shape in shapes[1:]):
        _fail("projection_shape_mismatch")
    documents = [projection.to_dict() for projection in parsed]
    return LeakageAudit(
        checked_projection_ids=tuple(projection.projection_id for projection in parsed),
        serialization_sha256=_digest(documents),
    )


audit_driver_serializations = audit_projection_leakage


@dataclass(frozen=True)
class ChangeTargetDiscoveryResult:
    """The complete auditor result for the two admitted ChangeTarget campaigns."""

    candidate_identity_sha256: str
    candidate_manifest_sha256: str
    candidate_artifact_inventory_sha256: str
    pair: MatchedRuntimeSourcePair
    packages: tuple[SourceRichDiscoveryPackage, ...]
    projections: tuple[BlindRuntimeProjection, ...]
    leakage_audit: LeakageAudit
    build_calls: int = 0
    device_calls: int = 0
    model_calls: int = 0
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "candidate_identity_sha256",
            "candidate_manifest_sha256",
            "candidate_artifact_inventory_sha256",
        ):
            _required_text(getattr(self, field), field)
            if not _HEX_64.fullmatch(getattr(self, field)):
                _fail("candidate_identity_invalid")
        if len(self.packages) != 2 or len(self.projections) != 2:
            _fail("matched_pair_cardinality_mismatch")
        if tuple(item.variant.variant_id for item in self.packages) != VARIANT_IDS:
            _fail("package_variant_order_mismatch")
        if tuple(item.opaque_lane_id for item in self.projections) != (
            CONTROL_LANE_ID,
            DEFECT_LANE_ID,
        ):
            _fail("projection_lane_identity_mismatch")
        if any(item.pair != self.pair for item in self.packages):
            _fail("package_pair_mismatch")
        if self.leakage_audit.checked_projection_ids != tuple(
            item.projection_id for item in self.projections
        ):
            _fail("leakage_audit_mismatch")
        if any(
            not isinstance(getattr(self, field), int)
            or isinstance(getattr(self, field), bool)
            or getattr(self, field) != 0
            for field in ("build_calls", "device_calls", "model_calls")
        ):
            _fail("unexpected_side_effect")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def admitted(self) -> bool:
        return True

    @property
    def auditor_packages(self) -> tuple[SourceRichDiscoveryPackage, ...]:
        return self.packages

    @property
    def driver_projections(self) -> tuple[BlindRuntimeProjection, ...]:
        return self.projections

    @property
    def identity_sha256(self) -> str:
        return _digest(self.to_dict(include_identity=False))

    def driver_visible_serializations(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_dict() for item in self.projections)

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "document_kind": "opencalc_change_target_discovery_admission",
            "family_id": FAMILY_ID,
            "family_version": FAMILY_VERSION,
            "candidate": {
                "identity_sha256": self.candidate_identity_sha256,
                "manifest_sha256": self.candidate_manifest_sha256,
                "artifact_inventory_sha256": self.candidate_artifact_inventory_sha256,
            },
            "matched_source_pair": self.pair.to_dict(),
            "source_rich_packages": [item.to_dict() for item in self.packages],
            "blind_runtime_projections": [item.to_dict() for item in self.projections],
            "leakage_audit": self.leakage_audit.to_dict(),
            "side_effects": {
                "build_calls": self.build_calls,
                "device_calls": self.device_calls,
                "model_calls": self.model_calls,
            },
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result


@dataclass(frozen=True)
class ProjectTargetDiscoveryResult:
    """The complete auditor result for two synthetic ProjectTarget campaigns."""

    candidate_identity_sha256: str
    candidate_manifest_sha256: str
    candidate_artifact_inventory_sha256: str
    pair: MatchedRuntimeSourcePair
    packages: tuple[SourceRichDiscoveryPackage, ...]
    projections: tuple[BlindRuntimeProjection, ...]
    source_materializations: tuple[SyntheticProjectCommit, ...]
    leakage_audit: LeakageAudit
    build_calls: int = 0
    device_calls: int = 0
    model_calls: int = 0
    source_patches_applied: int = 2
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "candidate_identity_sha256",
            "candidate_manifest_sha256",
            "candidate_artifact_inventory_sha256",
        ):
            _required_text(getattr(self, field), field)
            if not _HEX_64.fullmatch(getattr(self, field)):
                _fail("candidate_identity_invalid")
        if len(self.packages) != 2 or len(self.projections) != 2:
            _fail("matched_pair_cardinality_mismatch")
        if tuple(item.variant.variant_id for item in self.packages) != VARIANT_IDS:
            _fail("package_variant_order_mismatch")
        if tuple(item.target.kind for item in self.packages) != ("project", "project"):
            _fail("package_target_kind_mismatch")
        if tuple(item.opaque_lane_id for item in self.projections) != PROJECT_LANE_IDS:
            _fail("projection_lane_identity_mismatch")
        if len(self.source_materializations) != 2:
            _fail("synthetic_commit_cardinality_mismatch")
        if tuple(item.variant_id for item in self.source_materializations) != VARIANT_IDS:
            _fail("synthetic_commit_variant_order_mismatch")
        if any(item.pair != self.pair for item in self.packages):
            _fail("package_pair_mismatch")
        if any(
            package.synthetic_commit != receipt
            for package, receipt in zip(self.packages, self.source_materializations)
        ):
            _fail("package_synthetic_commit_mismatch")
        if len({item.synthetic_commit for item in self.source_materializations}) != 2:
            _fail("synthetic_commit_not_distinct")
        if len({item.worktree_path for item in self.source_materializations}) != 2:
            _fail("synthetic_worktree_not_distinct")
        if self.leakage_audit.checked_projection_ids != tuple(
            item.projection_id for item in self.projections
        ):
            _fail("leakage_audit_mismatch")
        if any(
            not isinstance(getattr(self, field), int)
            or isinstance(getattr(self, field), bool)
            or getattr(self, field) != 0
            for field in ("build_calls", "device_calls", "model_calls")
        ):
            _fail("unexpected_side_effect")
        if self.source_patches_applied != 2:
            _fail("synthetic_patch_cardinality_mismatch")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            _fail("schema_version_mismatch")

    @property
    def admitted(self) -> bool:
        return True

    @property
    def auditor_packages(self) -> tuple[SourceRichDiscoveryPackage, ...]:
        return self.packages

    @property
    def project_packages(self) -> tuple[SourceRichDiscoveryPackage, ...]:
        return self.packages

    @property
    def driver_projections(self) -> tuple[BlindRuntimeProjection, ...]:
        return self.projections

    @property
    def synthetic_commits(self) -> tuple[SyntheticProjectCommit, ...]:
        return self.source_materializations

    @property
    def materialization_receipts(self) -> tuple[SyntheticProjectCommit, ...]:
        return self.source_materializations

    @property
    def identity_sha256(self) -> str:
        return _digest(_project_normalized_identity(self.to_dict(include_identity=False)))

    def driver_visible_serializations(self) -> tuple[dict[str, Any], ...]:
        return tuple(item.to_dict() for item in self.projections)

    def to_dict(self, *, include_identity: bool = True) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "document_kind": "opencalc_project_target_discovery_admission",
            "family_id": FAMILY_ID,
            "family_version": FAMILY_VERSION,
            "candidate": {
                "identity_sha256": self.candidate_identity_sha256,
                "manifest_sha256": self.candidate_manifest_sha256,
                "artifact_inventory_sha256": self.candidate_artifact_inventory_sha256,
            },
            "matched_source_pair": self.pair.to_dict(),
            "source_materializations": [
                item.to_dict() for item in self.source_materializations
            ],
            "source_rich_packages": [item.to_dict() for item in self.packages],
            "blind_runtime_projections": [item.to_dict() for item in self.projections],
            "leakage_audit": self.leakage_audit.to_dict(),
            "side_effects": {
                "source_patches_applied": self.source_patches_applied,
                "build_calls": self.build_calls,
                "device_calls": self.device_calls,
                "model_calls": self.model_calls,
            },
        }
        if include_identity:
            result["identity_sha256"] = self.identity_sha256
        return result


ProjectTargetDiscoveryAdmission = ProjectTargetDiscoveryResult


def _git(root: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *arguments], cwd=root, check=True, capture_output=True
        )
    except (OSError, subprocess.CalledProcessError):
        _fail("source_identity_unavailable")
    try:
        return completed.stdout.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        _fail("source_identity_unavailable")


def _source_root(root_value: str | Path) -> Path:
    raw = Path(root_value).expanduser()
    if raw.is_symlink():
        _fail("source_root_symlink")
    try:
        root = raw.resolve(strict=True)
    except (OSError, RuntimeError):
        _fail("source_root_unavailable")
    if not root.is_dir():
        _fail("source_root_unavailable")
    return root


def _verify_pristine_source(root: Path, baseline: SourceBaseline) -> None:
    repository_root = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    if repository_root != root:
        _fail("source_root_not_repository")
    if _git(root, "rev-parse", "HEAD") != baseline.commit:
        _fail("source_commit_mismatch")
    if _canonical_origin(_git(root, "remote", "get-url", "origin")) != _canonical_origin(
        baseline.origin
    ):
        _fail("source_origin_mismatch")
    if _git(root, "status", "--porcelain=v1", "--untracked-files=all"):
        _fail("source_worktree_dirty")
    if _git(root, "rev-parse", "HEAD^{tree}") != baseline.tree_sha256:
        _fail("source_tree_mismatch")


def _project_fail(code: str) -> None:
    raise ProjectTargetAdmissionError(code)


def _project_git(
    root: Path,
    *arguments: str,
    input_bytes: bytes | None = None,
    env: Mapping[str, str] | None = None,
) -> bytes:
    """Run one non-interactive Git command inside a project materialization."""

    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            input=input_bytes,
            capture_output=True,
            env=dict(env) if env is not None else _project_git_environment(),
        )
    except (OSError, subprocess.CalledProcessError):
        _project_fail("project_materialization_failed")
    return completed.stdout


def _project_git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GIT_")
    }
    environment.update(
        {
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    return environment


def _project_git_text(root: Path, *arguments: str) -> str:
    try:
        return _project_git(root, *arguments).decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        _project_fail("project_materialization_failed")


def _project_source_tree_sha256(root: Path, commit: str) -> str:
    return _bytes_digest(
        _project_git(root, "ls-tree", "-r", "--full-tree", "-z", commit)
    )


def _project_materialization_root(
    root_value: str | Path | None,
    source_root: Path,
) -> Path:
    if root_value is None:
        try:
            return Path(tempfile.mkdtemp(prefix="opencalc-project-target-")).resolve()
        except OSError:
            _project_fail("project_materialization_root_unavailable")
    raw = Path(root_value).expanduser()
    if raw.is_symlink():
        _project_fail("project_materialization_root_symlink")
    try:
        root = raw.resolve()
        root.relative_to(source_root)
        _project_fail("project_materialization_root_unsafe")
    except ValueError:
        try:
            source_root.relative_to(root)
            _project_fail("project_materialization_root_unsafe")
        except ValueError:
            pass
        except (OSError, RuntimeError):
            _project_fail("project_materialization_root_unavailable")
    except (OSError, RuntimeError):
        _project_fail("project_materialization_root_unavailable")
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError:
        _project_fail("project_materialization_root_unavailable")
    if root.is_symlink() or not root.is_dir():
        _project_fail("project_materialization_root_unavailable")
    try:
        if any(root.iterdir()):
            _project_fail("project_materialization_root_not_empty")
    except OSError:
        _project_fail("project_materialization_root_unavailable")
    return root


def _project_patch_addition(
    pair: MatchedRuntimeSourcePair,
    variant: MatchedSourceVariant,
) -> str:
    additions = [
        line[1:]
        for line in variant.patch_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]
    removals = [
        line
        for line in variant.patch_text.splitlines()
        if line.startswith("-") and not line.startswith("---")
    ]
    expected = f"        binding.input.isSaveEnabled = {variant.right_hand_side}"
    if len(additions) != 1 or removals or additions[0] != expected:
        _project_fail("project_patch_mismatch")
    if pair.anchor.insertion_after not in pair.anchor.context:
        _project_fail("source_anchor_baseline_mismatch")
    return additions[0]


def _project_commit_metadata(
    root: Path,
    commit: str,
) -> tuple[str, str, str, str, str, str, str]:
    try:
        raw = _project_git(
            root,
            "show",
            "-s",
            "--format=%an%x00%ae%x00%aI%x00%cn%x00%ce%x00%cI%x00%B",
            commit,
        ).decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _project_fail("project_commit_metadata_unavailable")
    fields = raw.split("\0", 6)
    if len(fields) != 7:
        _project_fail("project_commit_metadata_unavailable")
    message = fields[6].rstrip("\n")
    return (*fields[:6], message)


def _project_commit_environment() -> dict[str, str]:
    environment = _project_git_environment()
    environment.update(
        {
            "GIT_AUTHOR_NAME": SYNTHETIC_AUTHOR_NAME,
            "GIT_AUTHOR_EMAIL": SYNTHETIC_AUTHOR_EMAIL,
            "GIT_AUTHOR_DATE": SYNTHETIC_COMMIT_TIMESTAMP,
            "GIT_COMMITTER_NAME": SYNTHETIC_AUTHOR_NAME,
            "GIT_COMMITTER_EMAIL": SYNTHETIC_AUTHOR_EMAIL,
            "GIT_COMMITTER_DATE": SYNTHETIC_COMMIT_TIMESTAMP,
        }
    )
    return environment


def _project_result_diff(root: Path, parent: str, commit: str) -> bytes:
    return _project_git(
        root,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--no-renames",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        "--diff-algorithm=myers",
        "--no-indent-heuristic",
        "--inter-hunk-context=0",
        "-U3",
        "--no-relative",
        parent,
        commit,
        "--",
    )


def _materialize_project_variant(
    source_root: Path,
    pair: MatchedRuntimeSourcePair,
    variant: MatchedSourceVariant,
    materialization_root: Path,
) -> SyntheticProjectCommit:
    worktree = materialization_root / variant.source_id
    if worktree.exists() or worktree.is_symlink():
        _project_fail("project_materialization_path_exists")
    try:
        # Claim the destination atomically so rejection cleanup cannot remove
        # a directory another process placed at the requested child path.
        worktree.mkdir()
    except FileExistsError:
        _project_fail("project_materialization_path_exists")
    except OSError:
        _project_fail("project_materialization_path_unavailable")
    try:
        # Git accepts an existing empty destination; the exclusive mkdir above
        # establishes ownership before any clone bytes are written.
        _project_git(
            materialization_root,
            "clone",
            "--no-local",
            "--no-hardlinks",
            str(source_root),
            str(worktree),
        )
        _project_git(worktree, "remote", "set-url", "origin", pair.baseline.origin)
        _project_git(worktree, "checkout", "--detach", pair.baseline.commit)
        repository_root = Path(
            _project_git_text(worktree, "rev-parse", "--show-toplevel")
        ).resolve()
        if repository_root != worktree.resolve():
            _project_fail("project_materialization_failed")
        if _project_git_text(worktree, "rev-parse", "HEAD") != pair.baseline.commit:
            _project_fail("project_parent_commit_mismatch")
        if _canonical_origin(
            _project_git_text(worktree, "remote", "get-url", "origin")
        ) != _canonical_origin(pair.baseline.origin):
            _project_fail("project_source_origin_mismatch")
        if _project_git_text(
            worktree, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            _project_fail("project_materialization_dirty")
        parent_tree = _project_git_text(worktree, "rev-parse", "HEAD^{tree}")
        if parent_tree != pair.baseline.tree_sha256:
            _project_fail("project_parent_tree_mismatch")
        parent_source_tree = _project_source_tree_sha256(worktree, pair.baseline.commit)
        addition = _project_patch_addition(pair, variant)
        target_path = _contained_source_path(worktree.resolve(), pair.anchor.path)
        try:
            raw = target_path.read_bytes()
            text = raw.decode("utf-8", errors="strict")
        except (OSError, UnicodeDecodeError):
            _project_fail("project_source_target_unreadable")
        if _bytes_digest(raw) != pair.anchor.target_file_sha256:
            _project_fail("project_source_target_digest_mismatch")
        if text.count(pair.anchor.context) != pair.anchor.required_occurrences:
            _project_fail("project_anchor_context_mismatch")
        updated = text.replace(
            pair.anchor.context,
            pair.anchor.context + "\n" + addition,
            pair.anchor.required_occurrences,
        )
        if updated == text:
            _project_fail("project_patch_did_not_change_source")
        try:
            target_path.write_bytes(updated.encode("utf-8"))
        except OSError:
            _project_fail("project_source_target_unwritable")
        _project_git(worktree, "add", "--", pair.anchor.path)
        staged_paths = _project_git(worktree, "diff", "--cached", "--name-only", "-z", "--")
        if staged_paths != (pair.anchor.path + "\0").encode("utf-8"):
            _project_fail("project_staged_scope_mismatch")
        numstat = _project_git(
            worktree, "diff", "--cached", "--numstat", "--", pair.anchor.path
        ).decode("utf-8", errors="strict").strip()
        if not numstat.startswith("1\t0\t"):
            _project_fail("project_staged_delta_mismatch")
        synthetic_tree = _project_git_text(worktree, "write-tree")
        if synthetic_tree == parent_tree:
            _project_fail("synthetic_tree_unchanged")
        commit_output = _project_git(
            worktree,
            "commit-tree",
            synthetic_tree,
            "-p",
            pair.baseline.commit,
            "--no-gpg-sign",
            input_bytes=(SYNTHETIC_COMMIT_MESSAGE + "\n").encode("utf-8"),
            env=_project_commit_environment(),
        )
        try:
            synthetic_commit = commit_output.decode("ascii", errors="strict").strip()
        except UnicodeDecodeError:
            _project_fail("project_commit_identity_unavailable")
        if not _HEX_40.fullmatch(synthetic_commit):
            _project_fail("project_commit_identity_unavailable")
        _project_git(worktree, "reset", "--hard", synthetic_commit)
        if _project_git_text(worktree, "rev-parse", "HEAD") != synthetic_commit:
            _project_fail("project_commit_identity_mismatch")
        if _project_git_text(
            worktree, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            _project_fail("project_materialization_dirty")
        committed_tree = _project_git_text(
            worktree, "rev-parse", f"{synthetic_commit}^{{tree}}"
        )
        if committed_tree != synthetic_tree:
            _project_fail("project_commit_tree_mismatch")
        if _project_git_text(worktree, "rev-parse", f"{synthetic_commit}^") != pair.baseline.commit:
            _project_fail("project_parent_commit_mismatch")
        synthetic_source_tree = _project_source_tree_sha256(worktree, synthetic_commit)
        result_diff = _project_result_diff(worktree, pair.baseline.commit, synthetic_commit)
        if not result_diff:
            _project_fail("project_result_diff_missing")
        target_file_sha256 = _bytes_digest(target_path.read_bytes())
        metadata = _project_commit_metadata(worktree, synthetic_commit)
        if metadata != (
            SYNTHETIC_AUTHOR_NAME,
            SYNTHETIC_AUTHOR_EMAIL,
            SYNTHETIC_COMMIT_TIMESTAMP,
            SYNTHETIC_AUTHOR_NAME,
            SYNTHETIC_AUTHOR_EMAIL,
            SYNTHETIC_COMMIT_TIMESTAMP,
            SYNTHETIC_COMMIT_MESSAGE,
        ):
            _project_fail("project_commit_metadata_mismatch")
        return SyntheticProjectCommit(
            variant_id=variant.variant_id,
            source_id=variant.source_id,
            parent_commit=pair.baseline.commit,
            parent_tree_sha256=parent_tree,
            parent_source_tree_sha256=parent_source_tree,
            synthetic_commit=synthetic_commit,
            synthetic_tree_sha256=committed_tree,
            synthetic_source_tree_sha256=synthetic_source_tree,
            target_file_sha256=target_file_sha256,
            patch_sha256=variant.patch_sha256,
            result_diff_sha256=_bytes_digest(result_diff),
            author_name=metadata[0],
            author_email=metadata[1],
            author_timestamp=metadata[2],
            committer_name=metadata[3],
            committer_email=metadata[4],
            committer_timestamp=metadata[5],
            message=metadata[6],
            worktree_path=str(worktree.resolve()),
        )
    except ProjectTargetAdmissionError:
        _discard_project_worktree(materialization_root, worktree)
        raise
    except (OSError, UnicodeDecodeError, ValueError):
        _discard_project_worktree(materialization_root, worktree)
        _project_fail("project_materialization_failed")


def _verify_project_materialization(
    materialization_root: Path,
    pair: MatchedRuntimeSourcePair,
    variant: MatchedSourceVariant,
    receipt: SyntheticProjectCommit,
) -> None:
    """Revalidate a receipt before any later consumer can use its worktree."""

    expected_worktree = materialization_root / variant.source_id
    worktree = Path(receipt.worktree_path)
    if worktree != expected_worktree or worktree.is_symlink():
        _project_fail("project_materialization_path_drift")
    try:
        if worktree.resolve(strict=True) != expected_worktree.resolve(strict=True):
            _project_fail("project_materialization_path_drift")
        if not worktree.is_dir():
            _project_fail("project_materialization_missing")
        repository_root = Path(
            _project_git_text(worktree, "rev-parse", "--show-toplevel")
        ).resolve()
        if repository_root != expected_worktree.resolve(strict=True):
            _project_fail("project_materialization_path_drift")
        if _project_git_text(worktree, "rev-parse", "HEAD") != receipt.synthetic_commit:
            _project_fail("project_materialization_commit_drift")
        if _project_git_text(worktree, "rev-parse", "HEAD^") != receipt.parent_commit:
            _project_fail("project_materialization_parent_drift")
        if _project_git_text(worktree, "rev-parse", "HEAD^{tree}") != receipt.synthetic_tree_sha256:
            _project_fail("project_materialization_tree_drift")
        if _canonical_origin(
            _project_git_text(worktree, "remote", "get-url", "origin")
        ) != _canonical_origin(pair.baseline.origin):
            _project_fail("project_source_origin_mismatch")
        if _project_git_text(
            worktree, "status", "--porcelain=v1", "--untracked-files=all"
        ):
            _project_fail("project_materialization_dirty")
        if _project_source_tree_sha256(worktree, receipt.synthetic_commit) != (
            receipt.synthetic_source_tree_sha256
        ):
            _project_fail("project_materialization_source_tree_drift")
        target_path = _contained_source_path(worktree, pair.anchor.path)
        if _bytes_digest(target_path.read_bytes()) != receipt.target_file_sha256:
            _project_fail("project_materialization_target_drift")
        result_diff = _project_result_diff(
            worktree, receipt.parent_commit, receipt.synthetic_commit
        )
        if _bytes_digest(result_diff) != receipt.result_diff_sha256:
            _project_fail("project_materialization_diff_drift")
        if _project_commit_metadata(worktree, receipt.synthetic_commit) != (
            receipt.author_name,
            receipt.author_email,
            receipt.author_timestamp,
            receipt.committer_name,
            receipt.committer_email,
            receipt.committer_timestamp,
            receipt.message,
        ):
            _project_fail("project_materialization_metadata_drift")
    except ProjectTargetAdmissionError:
        raise
    except (OSError, UnicodeDecodeError, RuntimeError, ValueError):
        _project_fail("project_materialization_drift")


def _discard_project_worktree(materialization_root: Path, worktree: Path) -> None:
    """Remove only a child created by this admission attempt after rejection."""

    try:
        if worktree.parent != materialization_root or worktree.is_symlink():
            return
        if worktree.exists():
            shutil.rmtree(worktree)
    except OSError:
        return


def _contained_source_path(root: Path, relative_path: str) -> Path:
    relative_path = _safe_relative_path(relative_path, "source_path")
    path = root.joinpath(*PurePosixPath(relative_path).parts)
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if current.is_symlink():
            _fail("source_path_symlink")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError):
        _fail("source_context_missing")
    if not path.is_file():
        _fail("source_context_missing")
    return path


def _validate_anchor_against_source(root: Path, pair: MatchedRuntimeSourcePair) -> bytes:
    anchor = pair.anchor
    if anchor.origin != pair.baseline.origin or anchor.commit != pair.baseline.commit:
        _fail("source_anchor_baseline_mismatch")
    path = _contained_source_path(root, anchor.path)
    try:
        raw = path.read_bytes()
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail("source_context_unreadable")
    except OSError:
        _fail("source_context_unreadable")
    occurrences = text.count(anchor.context)
    if occurrences > anchor.required_occurrences:
        _fail("anchor_ambiguous")
    if occurrences < anchor.required_occurrences:
        _fail("anchor_context_missing")
    if _bytes_digest(raw) != anchor.target_file_sha256:
        _fail("anchor_target_digest_mismatch")
    return raw


def _validate_required_context(root: Path) -> None:
    tracked_raw = _git(root, "ls-files", "-z")
    tracked = {item for item in tracked_raw.split("\0") if item}
    required = set(REQUIRED_CONTEXT_PATHS)
    if required - tracked:
        _fail("context_required_path_missing")
    if len(required) > REQUIRED_CONTEXT_BUDGET:
        _fail("context_budget_exhausted")
    for relative_path in REQUIRED_CONTEXT_PATHS:
        try:
            path = _contained_source_path(root, relative_path)
        except ChangeTargetAdmissionError as error:
            if error.code == "source_context_missing":
                raise ChangeTargetAdmissionError(
                    "context_required_path_missing"
                ) from error
            raise
        try:
            path.read_bytes().decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail("context_required_path_unreadable")
        except OSError:
            _fail("context_required_path_unreadable")


def _load_declared_pair(candidate_root: Path) -> MatchedRuntimeSourcePair:
    path = candidate_root / "source-pair.json"
    try:
        raw = path.read_bytes()
        document = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _fail("source_pair_unreadable")
    if not isinstance(document, Mapping):
        _fail("source_pair_schema_mismatch")
    try:
        if document.get("family_id") != FAMILY_ID or document.get("family_version") != FAMILY_VERSION:
            _fail("source_pair_family_mismatch")
        pair = MatchedRuntimeSourcePair.from_dict(
            {
                "schema_version": document.get("schema_version", SCHEMA_VERSION),
                "pair_id": document.get("pair_id"),
                "population_classification": document.get("population_classification"),
                "taxonomy_id": document.get("taxonomy_id"),
                "mutation_operator_id": document.get("mutation_operator_id"),
                "baseline": document.get("baseline"),
                "upstream_source_anchor": document.get("upstream_source_anchor"),
                "variants": document.get("variants"),
            }
        )
    except ChangeTargetAdmissionError:
        raise
    except (TypeError, ValueError):
        _fail("source_pair_schema_mismatch")
    return pair


def _validate_candidate(candidate_root: str | Path) -> tuple[runtime_calibration.CandidateInputs, MatchedRuntimeSourcePair]:
    root = Path(candidate_root).expanduser()
    try:
        pair = _load_declared_pair(root.resolve(strict=True))
    except ChangeTargetAdmissionError:
        raise
    except (OSError, RuntimeError):
        _fail("candidate_root_unavailable")
    try:
        candidate = runtime_calibration.verify_candidate_inputs(root)
    except runtime_calibration.CandidateVerificationError as error:
        if error.code == "candidate_patch_context_mismatch" and any(
            variant.patch_text.count("diff --git") != 1
            or variant.patch_text.count("@@") != 1
            for variant in pair.variants
        ):
            raise ChangeTargetAdmissionError("extra_source_hunk") from error
        raise ChangeTargetAdmissionError(error.code) from error
    return candidate, pair


def _artifact_digest_map(candidate: runtime_calibration.CandidateInputs) -> dict[str, str]:
    return {artifact.path: artifact.sha256 for artifact in candidate.artifacts}


def _patch_artifact_ref(variant_id: str) -> str:
    if variant_id not in VARIANT_IDS:
        _fail("pair_variant_mismatch")
    return f"{PATCH_ARTIFACT_DIRECTORY}/{variant_id}.patch"


def _validate_patch_artifacts(pair: MatchedRuntimeSourcePair) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    for variant in pair.variants:
        reference = _patch_artifact_ref(variant.variant_id)
        path = repository_root.joinpath(*PurePosixPath(reference).parts)
        if path.is_symlink():
            _fail("change_target_patch_symlink")
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(repository_root)
            raw = path.read_bytes()
        except (OSError, RuntimeError, ValueError):
            _fail("change_target_patch_unavailable")
        if _bytes_digest(raw) != variant.patch_sha256:
            _fail("change_target_patch_mismatch")
        try:
            patch_text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _fail("change_target_patch_unreadable")
        if patch_text != variant.patch_text:
            _fail("change_target_patch_mismatch")


def _source_facts(
    pair: MatchedRuntimeSourcePair,
    candidate: runtime_calibration.CandidateInputs,
    *,
    source_commit: str | None = None,
    source_file_sha256: str | None = None,
) -> tuple[ContextFact, ...]:
    artifact_digests = _artifact_digest_map(candidate)
    effective_source_commit = source_commit or pair.baseline.commit
    source_sha256 = source_file_sha256 or pair.anchor.target_file_sha256
    anchor_fact = ContextFact(
        fact_id="opencalc-source-anchor-v1",
        subject=pair.anchor.path,
        predicate="source_anchor",
        value={
            "anchor_sha256": pair.anchor.identity_sha256,
            "context_sha256": pair.anchor.context_sha256,
            "required_occurrences": pair.anchor.required_occurrences,
            "insertion_after": pair.anchor.insertion_after,
        },
        source_kind="declared",
        provenance=(
            ProvenanceRef(
                ref=pair.anchor.path,
                source_sha256=source_sha256,
                locator="unique-context",
            ),
        ),
        source_version=effective_source_commit,
        confidence=1.0,
        status="known",
    )
    quality_fact = ContextFact(
        fact_id="opencalc-quality-contract-v1",
        subject="opencalc-input",
        predicate="quality_contract",
        value="input text remains 12+34 across orientation-driven Activity recreation",
        source_kind="declared",
        provenance=(
            ProvenanceRef(
                ref="candidate/source-pair.json",
                source_sha256=artifact_digests["source-pair.json"],
                locator="matched-source-pair",
            ),
        ),
        source_version=effective_source_commit,
        confidence=1.0,
        status="known",
    )
    change_context_fact = ContextFact(
        fact_id="opencalc-change-context-v1",
        subject=pair.anchor.path,
        predicate="change_context",
        value={
            "field": "binding.input.isSaveEnabled",
            "insertion_after": pair.anchor.insertion_after,
            "baseline": pair.baseline.identity_sha256,
        },
        source_kind="declared",
        provenance=(
            ProvenanceRef(
                ref="candidate/source-pair.json",
                source_sha256=artifact_digests["source-pair.json"],
                locator="variants",
            ),
        ),
        source_version=effective_source_commit,
        confidence=1.0,
        status="known",
    )
    return anchor_fact, quality_fact, change_context_fact


def _augment_context(
    acquisition: ContextAcquisitionResult,
    facts: tuple[ContextFact, ...],
) -> ContextAcquisitionResult:
    existing_ids = {fact.fact_id for fact in acquisition.graph.facts}
    if existing_ids.intersection(fact.fact_id for fact in facts):
        _fail("context_fact_id_collision")
    graph = replace(acquisition.graph, facts=(*acquisition.graph.facts, *facts))
    receipt = replace(
        acquisition.receipt,
        graph_sha256=_digest(graph.to_dict()),
    )
    return ContextAcquisitionResult(
        target=acquisition.target,
        graph=graph,
        receipt=receipt,
    )


def _make_neutral_prior() -> RiskPrior:
    return RiskPrior(
        prior_id=RISK_PRIOR_ID,
        name="state evolution across orientation recreation",
        description=(
            "Prioritize bounded state-preservation risks at an orientation-driven "
            "activity recreation boundary."
        ),
        signals=("state", "orientation", "recreation"),
        operator_ids=(ATTACK_OPERATOR_ID,),
        version="ocrc-v1",
    )


def _make_neutral_operator() -> AttackOperator:
    return AttackOperator(
        operator_id=ATTACK_OPERATOR_ID,
        name="orientation activity recreation",
        description="Observe one bounded orientation-driven activity recreation.",
        action="perform one prescribed orientation recreation and read the bounded state",
        safety_boundary=(
            "local target only; one bounded recreation; no unbounded wait or "
            "external side effect"
        ),
    )


def _make_strategy(
    prior: RiskPrior,
    operator: AttackOperator,
):
    def derive(
        target: ChangeTarget,
        graph: Any,
        *,
        mode: str,
        behavior_delta: BehaviorDelta | None = None,
        contract_drift: ContractDrift | None = None,
    ) -> RiskDerivationResult:
        if mode != "change" or behavior_delta is None or contract_drift is None:
            return RiskDerivationResult(
                prior=prior,
                operator=operator,
                hypothesis=None,
                failure_chain=None,
                priority=None,
                attack_plan=None,
                rejection_reasons=("OpenCalc ChangeTarget strategy requires a matched delta",),
            )
        chain_id = f"{RISK_HYPOTHESIS_ID}-failure-chain-v1"
        priority_id = f"{RISK_HYPOTHESIS_ID}-priority-v1"
        supporting_fact_ids = (
            "opencalc-source-anchor-v1",
            "opencalc-quality-contract-v1",
            "opencalc-change-context-v1",
        )
        hypothesis = RiskHypothesis(
            hypothesis_id=RISK_HYPOTHESIS_ID,
            target_id=target.target_id,
            quality_property=(
                "input text remains 12+34 across orientation-driven Activity recreation"
            ),
            assumptions=(
                "the orientation transition recreates the activity",
                "the input state is observed before and after that transition",
            ),
            trigger="one bounded orientation-driven Activity recreation",
            mechanism=(
                "the target's declared input state-saving configuration participates "
                "in recreation"
            ),
            consequence="the quality contract may be violated after recreation",
            rationale=(
                "The hypothesis is frozen from the shared source anchor and target "
                "context; it is not an observed runtime outcome."
            ),
            required_evidence=(
                "pre-transition input observation",
                "lifecycle transition receipt",
                "post-transition input observation",
            ),
            confidence=0.9,
            status="frozen",
            supporting_fact_ids=supporting_fact_ids,
            prior_id=prior.prior_id,
            failure_chain_id=chain_id,
            unknowns=("runtime lifecycle evidence remains unknown before execution",),
            behavior_delta_id=behavior_delta.delta_id,
            contract_drift_id=contract_drift.drift_id,
            priority_id=priority_id,
        )
        chain = FailureChain(
            chain_id=chain_id,
            steps=(
                "the target has the declared input state-saving configuration",
                "one bounded orientation-driven activity recreation occurs",
                "the input quality contract is checked after recreation",
            ),
            consequence="input text remains 12+34 across orientation-driven Activity recreation",
            fact_ids=supporting_fact_ids,
            causal_roles=("local_behavior", "dependency_propagation", "system_impact"),
        )
        priority = RiskPriority(
            priority_id=priority_id,
            impact=0.8,
            propagation_reach=0.5,
            context_sensitivity=0.9,
            uncertainty=0.2,
            evidence_gap=0.6,
            estimated_probe_cost=0.4,
            rationale=(
                "Factors order the bounded discovery probe; the score is not a "
                "probability or runtime conclusion."
            ),
        )
        plan = AttackPlan(
            plan_id=ATTACK_PLAN_ID,
            target_id=target.target_id,
            hypothesis_id=hypothesis.hypothesis_id,
            operator_id=operator.operator_id,
            trigger="one bounded orientation-driven Activity recreation",
            observations=(
                "input before recreation",
                "lifecycle transition",
                "input after recreation",
            ),
            evidence_expectations=hypothesis.required_evidence,
            oracle="quality-contract-oracle-v1",
            abort_boundary="abort before an unbounded wait or external side effect",
            claim_boundary="the frozen local target and its recorded runtime evidence only",
            fixture_refs=("opencalc-change-target-context",),
            status="frozen",
        )
        return RiskDerivationResult(
            prior=prior,
            operator=operator,
            hypothesis=hypothesis,
            failure_chain=chain,
            priority=priority,
            attack_plan=plan,
        )

    return make_risk_derivation_strategy(
        strategy_id="opencalc-change-target-discovery-v1",
        version="ocrc-v1",
        compatible_prior_ids=(prior.prior_id,),
        compatible_operator_ids=(operator.operator_id,),
        target_modes=("change",),
        deriver=derive,
    )


def _make_neutral_quality_contract() -> QualityContract:
    return QualityContract(
        contract_id=QUALITY_CONTRACT_ID,
        name="bounded response quality contract",
        scope="opencalc-input",
        quality_property=(
            "input text remains 12+34 across orientation-driven Activity recreation"
        ),
        constraint=(
            "input text remains 12+34 across orientation-driven Activity recreation"
        ),
        source_fact_ids=("opencalc-quality-contract-v1",),
        status="derived",
    )


def _make_project_strategy(
    prior: RiskPrior,
    operator: AttackOperator,
):
    def derive(
        target: ProjectTarget,
        graph: Any,
        *,
        mode: str,
        behavior_delta: BehaviorDelta | None = None,
        contract_drift: ContractDrift | None = None,
    ) -> RiskDerivationResult:
        if (
            mode != "project"
            or behavior_delta is not None
            or contract_drift is not None
            or not isinstance(target, ProjectTarget)
        ):
            return RiskDerivationResult(
                prior=prior,
                operator=operator,
                hypothesis=None,
                failure_chain=None,
                priority=None,
                attack_plan=None,
                rejection_reasons=(
                    "OpenCalc ProjectTarget strategy does not consume a source diff",
                ),
            )
        chain_id = f"{RISK_HYPOTHESIS_ID}-failure-chain-v1"
        priority_id = f"{RISK_HYPOTHESIS_ID}-priority-v1"
        supporting_fact_ids = (
            "opencalc-source-anchor-v1",
            "opencalc-quality-contract-v1",
            "opencalc-change-context-v1",
        )
        hypothesis = RiskHypothesis(
            hypothesis_id=RISK_HYPOTHESIS_ID,
            target_id=target.target_id,
            quality_property=(
                "input text remains 12+34 across orientation-driven Activity recreation"
            ),
            assumptions=(
                "the orientation transition recreates the activity",
                "the input state is observed before and after that transition",
            ),
            trigger="one bounded orientation-driven Activity recreation",
            mechanism=(
                "the target's declared input state-saving configuration participates "
                "in recreation"
            ),
            consequence="the quality contract may be violated after recreation",
            rationale=(
                "The hypothesis is frozen from the shared source anchor and target "
                "context; it is not an observed runtime outcome."
            ),
            required_evidence=(
                "pre-transition input observation",
                "lifecycle transition receipt",
                "post-transition input observation",
            ),
            confidence=0.9,
            status="frozen",
            supporting_fact_ids=supporting_fact_ids,
            prior_id=prior.prior_id,
            failure_chain_id=chain_id,
            unknowns=("runtime lifecycle evidence remains unknown before execution",),
            priority_id=priority_id,
        )
        chain = FailureChain(
            chain_id=chain_id,
            steps=(
                "the target has the declared input state-saving configuration",
                "one bounded orientation-driven activity recreation occurs",
                "the input quality contract is checked after recreation",
            ),
            consequence="input text remains 12+34 across orientation-driven Activity recreation",
            fact_ids=supporting_fact_ids,
            causal_roles=("local_behavior", "dependency_propagation", "system_impact"),
        )
        priority = RiskPriority(
            priority_id=priority_id,
            impact=0.8,
            propagation_reach=0.5,
            context_sensitivity=0.9,
            uncertainty=0.2,
            evidence_gap=0.6,
            estimated_probe_cost=0.4,
            rationale=(
                "Factors order the bounded discovery probe; the score is not a "
                "probability or runtime conclusion."
            ),
        )
        plan = AttackPlan(
            plan_id=ATTACK_PLAN_ID,
            target_id=target.target_id,
            hypothesis_id=hypothesis.hypothesis_id,
            operator_id=operator.operator_id,
            trigger="one bounded orientation-driven Activity recreation",
            observations=(
                "input before recreation",
                "lifecycle transition",
                "input after recreation",
            ),
            evidence_expectations=hypothesis.required_evidence,
            oracle="quality-contract-oracle-v1",
            abort_boundary="abort before an unbounded wait or external side effect",
            claim_boundary="the frozen local target and its recorded runtime evidence only",
            fixture_refs=("opencalc-change-target-context",),
            status="frozen",
        )
        return RiskDerivationResult(
            prior=prior,
            operator=operator,
            hypothesis=hypothesis,
            failure_chain=chain,
            priority=priority,
            attack_plan=plan,
        )

    return make_risk_derivation_strategy(
        strategy_id="opencalc-project-target-discovery-v1",
        version="ocrc-v1",
        compatible_prior_ids=(prior.prior_id,),
        compatible_operator_ids=(operator.operator_id,),
        target_modes=("project",),
        deriver=derive,
    )


def _make_behavior_delta(
    target: ChangeTarget,
    variant: MatchedSourceVariant,
) -> tuple[BehaviorDelta, ContractDrift]:
    drift_id = f"{PAIR_ID}-{variant.variant_id}-contract-drift"
    delta = BehaviorDelta(
        delta_id=f"{variant.source_id}-behavior-delta",
        target_id=target.target_id,
        subject=variant.difference_field,
        before="the pristine source has no explicit input save setting at the anchor",
        after=(
            f"the curated injection sets {variant.difference_field} to "
            f"{variant.right_hand_side}"
        ),
        source_fact_ids=("opencalc-source-anchor-v1", "opencalc-change-context-v1"),
        confidence=1.0,
        status="inferred",
        contract_drift_id=drift_id,
        rationale=(
            "This is the real bounded source delta retained separately from the "
            "pristine Context Facts; it is not an observed outcome."
        ),
    )
    drift = ContractDrift(
        drift_id=drift_id,
        contract_id=QUALITY_CONTRACT_ID,
        before="input state-saving configuration is absent at the anchor",
        after=(
            f"input state-saving configuration is declared as "
            f"{variant.right_hand_side}"
        ),
        delta="one state-saving boolean changes at the uniquely anchored insertion point",
        source_fact_ids=("opencalc-source-anchor-v1", "opencalc-change-context-v1"),
        status="suspected",
        rationale="The matched source pair supplies a bounded contract-drift signal for discovery.",
    )
    return delta, drift


def _make_campaign(
    target: ChangeTarget,
    acquisition: ContextAcquisitionResult,
    variant: MatchedSourceVariant,
    prior: RiskPrior,
    operator: AttackOperator,
    strategy: Any,
) -> tuple[DiscoveryCampaignPackage, BehaviorDelta, ContractDrift]:
    delta, drift = _make_behavior_delta(target, variant)
    request = ContextExpansionRequest(
        request_id=f"{target.target_id}-context-request",
        campaign_id=f"{target.target_id}-campaign",
        target_id=target.target_id,
        required_predicates=("source_anchor", "quality_contract", "change_context"),
        probe_refs=(),
        budget=REQUIRED_CONTEXT_BUDGET,
        unresolved_questions=tuple(
            f"fact {fact.fact_id} remains {fact.status}"
            for fact in acquisition.graph.facts
            if fact.status in {"unknown", "contradictory", "stale"}
        ),
    )
    expansion_result = ContextExpansionResult(
        request_id=request.request_id,
        target_id=target.target_id,
        graph=acquisition.graph,
        resolved_fact_ids=tuple(
            fact.fact_id for fact in acquisition.graph.facts if fact.status == "known"
        ),
        unresolved_questions=request.unresolved_questions,
        budget_used=acquisition.receipt.budget_used,
        status="partial" if request.unresolved_questions else "complete",
    )
    try:
        package = seed_change_campaign(
            request.campaign_id,
            target,
            acquisition.graph,
            behavior_delta=delta,
            contract_drift=drift,
            context_request=request,
            context_result=expansion_result,
            prior=prior,
            operator=operator,
            strategy=strategy,
        )
        admission = admit_campaign_plan(package)
    except (DiscoveryContractError, ValueError) as error:
        raise ChangeTargetAdmissionError("campaign_admission_rejected") from error
    if not admission.admission.admitted:
        _fail("campaign_admission_rejected")
    return admission.package, delta, drift


def _make_project_campaign(
    target: ProjectTarget,
    acquisition: ContextAcquisitionResult,
    prior: RiskPrior,
    operator: AttackOperator,
    strategy: Any,
) -> DiscoveryCampaignPackage:
    request = ContextExpansionRequest(
        request_id=f"{target.target_id}-context-request",
        campaign_id=f"{target.target_id}-campaign",
        target_id=target.target_id,
        required_predicates=("source_anchor", "quality_contract", "change_context"),
        probe_refs=(),
        budget=REQUIRED_CONTEXT_BUDGET,
        unresolved_questions=tuple(
            f"fact {fact.fact_id} remains {fact.status}"
            for fact in acquisition.graph.facts
            if fact.status in {"unknown", "contradictory", "stale"}
        ),
    )
    expansion_result = ContextExpansionResult(
        request_id=request.request_id,
        target_id=target.target_id,
        graph=acquisition.graph,
        resolved_fact_ids=tuple(
            fact.fact_id for fact in acquisition.graph.facts if fact.status == "known"
        ),
        unresolved_questions=request.unresolved_questions,
        budget_used=acquisition.receipt.budget_used,
        status="partial" if request.unresolved_questions else "complete",
    )
    try:
        package = seed_project_campaign(
            request.campaign_id,
            target,
            acquisition.graph,
            context_request=request,
            context_result=expansion_result,
            prior=prior,
            operator=operator,
            strategy=strategy,
        )
        # ProjectTarget has no ContractDrift to provide the shared contract
        # identity. Bind the same neutral Quality Contract used by ChangeTarget
        # after seeding, while retaining the campaign's immutable graph.
        campaign = replace(
            package.campaign,
            quality_contracts=(_make_neutral_quality_contract(),),
        )
        package = replace(package, campaign=campaign)
        admission = admit_campaign_plan(package)
    except (DiscoveryContractError, ValueError) as error:
        raise ProjectTargetAdmissionError("campaign_admission_rejected") from error
    if not admission.admission.admitted:
        raise ProjectTargetAdmissionError("campaign_admission_rejected")
    return admission.package


def _build_projection(
    candidate: runtime_calibration.CandidateInputs,
    package: SourceRichDiscoveryPackage,
    lane_id: str,
) -> BlindRuntimeProjection:
    artifact_digests = _artifact_digest_map(candidate)
    number = lane_id[-2:]
    prefix = f"runtime/lanes/lane-{number}"
    try:
        projection_commitment = artifact_digests[f"{prefix}/projection.json"]
        driver_plan_commitment = artifact_digests[f"{prefix}/driver-plan.json"]
        recipe_commitment = artifact_digests[f"{prefix}/recipe.json"]
        run_spec_commitment = artifact_digests[f"{prefix}/run-spec.yaml"]
    except KeyError as error:
        raise ChangeTargetAdmissionError("candidate_lane_artifact_missing") from error
    opaque_identity = _digest(
        {
            "candidate": candidate.candidate_identity_sha256,
            "pair": package.pair.identity_sha256,
            "package": package.identity_sha256,
            "lane": lane_id,
        }
    )
    return BlindRuntimeProjection(
        projection_id=_projection_id(
            lane_id,
            opaque_identity,
            QUALITY_CONTRACT_ID,
            RISK_PRIOR_ID,
            ATTACK_OPERATOR_ID,
            RISK_HYPOTHESIS_ID,
            ATTACK_PLAN_ID,
            EXPLORATION_POLICY_ID,
        ),
        opaque_lane_id=lane_id,
        opaque_identity=opaque_identity,
        family_id=FAMILY_ID,
        family_version=FAMILY_VERSION,
        quality_contract_id=QUALITY_CONTRACT_ID,
        risk_prior_id=RISK_PRIOR_ID,
        attack_operator_id=ATTACK_OPERATOR_ID,
        risk_hypothesis_id=RISK_HYPOTHESIS_ID,
        attack_plan_id=ATTACK_PLAN_ID,
        exploration_policy_id=EXPLORATION_POLICY_ID,
        context_budget=REQUIRED_CONTEXT_BUDGET,
        required_context_count=len(REQUIRED_CONTEXT_PATHS),
        projection_commitment=projection_commitment,
        driver_plan_commitment=driver_plan_commitment,
        recipe_commitment=recipe_commitment,
        run_spec_commitment=run_spec_commitment,
    )


def admit_change_target_pair(
    candidate_root: str | Path = DEFAULT_CANDIDATE_ROOT,
    source_root: str | Path = DEFAULT_SOURCE_ROOT,
) -> ChangeTargetDiscoveryResult:
    """Admit both OpenCalc ChangeTarget campaigns from pristine source.

    The function is deterministic for the same candidate and upstream source
    identities.  It never applies either patch and never creates a build or
    device side effect.
    """

    candidate, pair = _validate_candidate(candidate_root)
    _validate_patch_artifacts(pair)
    root = _source_root(source_root)
    _verify_pristine_source(root, pair.baseline)
    _validate_anchor_against_source(root, pair)
    _validate_required_context(root)

    prior = _make_neutral_prior()
    operator = _make_neutral_operator()
    strategy = _make_strategy(prior, operator)
    source_facts = _source_facts(pair, candidate)
    packages: list[SourceRichDiscoveryPackage] = []
    for variant in pair.variants:
        target = ChangeTarget(
            target_id=variant.source_id,
            source_origin=pair.baseline.origin,
            source_commit=pair.baseline.commit,
            worktree=str(root),
            diff_ref=_patch_artifact_ref(variant.variant_id),
            diff_sha256=variant.patch_sha256,
            spec_ref="bench/runtime-calibration/opencalc-input-save-enabled-v1/source-pair.json",
        )
        try:
            acquisition_target = ProjectTarget(
                target_id=target.target_id,
                source_origin=pair.baseline.origin,
                source_commit=pair.baseline.commit,
                worktree=str(root),
                scope=REQUIRED_CONTEXT_PATHS,
                discovery_budget=REQUIRED_CONTEXT_BUDGET,
            )
            acquired = acquire_project_context(acquisition_target)
        except (DiscoveryContractError, ValueError) as error:
            message = str(error).lower()
            if "unreadable" in message or "non-utf" in message:
                code = "context_required_path_unreadable"
            elif "budget" in message or "skipped" in message:
                code = "context_budget_exhausted"
            else:
                code = "context_acquisition_rejected"
            raise ChangeTargetAdmissionError(code) from error
        acquired = _augment_context(acquired, source_facts)
        context = OpenCalcContextAcquisition(acquired)
        campaign, delta, drift = _make_campaign(
            target,
            acquired,
            variant,
            prior,
            operator,
            strategy,
        )
        quality_contract = campaign.campaign.quality_contracts[0]
        risk_hypothesis = campaign.campaign.hypotheses[0]
        attack_plan = campaign.campaign.attack_plans[0]
        risk_priority = campaign.risk_priority
        if risk_priority is None:
            _fail("campaign_priority_missing")
        packages.append(
            SourceRichDiscoveryPackage(
                package_id=f"{PAIR_ID}-{variant.variant_id}-package-v1",
                catalog_id=f"opencalc-input-save-enabled-{variant.variant_id}-v1",
                target=target,
                pair=pair,
                variant=variant,
                context_acquisition=context,
                campaign=campaign,
                behavior_delta=delta,
                contract_drift=drift,
                quality_contract=quality_contract,
                risk_prior=campaign.campaign.risk_priors[0],
                attack_operator=campaign.campaign.attack_operators[0],
                risk_hypothesis=risk_hypothesis,
                attack_plan=attack_plan,
                risk_priority=risk_priority,
                exploration_policy_id=EXPLORATION_POLICY_ID,
            )
        )

    projections = [
        _build_projection(candidate, packages[0], CONTROL_LANE_ID),
        _build_projection(candidate, packages[1], DEFECT_LANE_ID),
    ]
    leakage = audit_projection_leakage(projections)
    # Re-read identity after acquisition and before returning.  This protects
    # the result from a source mutation between the generic adapter's own
    # before/after checks and result assembly.
    _verify_pristine_source(root, pair.baseline)
    return ChangeTargetDiscoveryResult(
        candidate_identity_sha256=candidate.candidate_identity_sha256,
        candidate_manifest_sha256=candidate.manifest_sha256,
        candidate_artifact_inventory_sha256=candidate.artifact_inventory_sha256,
        pair=pair,
        packages=tuple(packages),
        projections=tuple(projections),
        leakage_audit=leakage,
    )


def _acquire_project_context_for_admission(
    target: ProjectTarget,
) -> ContextAcquisitionResult:
    try:
        return acquire_project_context(target)
    except (DiscoveryContractError, ValueError) as error:
        message = str(error).lower()
        if "unreadable" in message or "non-utf" in message:
            code = "context_required_path_unreadable"
        elif "budget" in message or "skipped" in message:
            code = "context_budget_exhausted"
        elif "changed during" in message or "identity" in message:
            code = "context_source_identity_drift"
        else:
            code = "context_acquisition_rejected"
        raise ProjectTargetAdmissionError(code) from error


def admit_project_target_pair(
    candidate_root: str | Path = DEFAULT_CANDIDATE_ROOT,
    source_root: str | Path = DEFAULT_SOURCE_ROOT,
    materialization_root: str | Path | None = None,
) -> ProjectTargetDiscoveryResult:
    """Admit two complete synthetic OpenCalc ProjectTarget campaigns.

    Candidate and pristine-source identities are checked before any source
    materialization. Each variant then receives a fresh clone, one declared
    anchored source injection, and a deterministic synthetic commit. The
    materialized repositories remain clean and are never used as a runtime
    build worktree by this seam.
    """

    created_worktrees: list[Path] = []
    output_root: Path | None = None
    try:
        candidate, pair = _validate_candidate(candidate_root)
        _validate_patch_artifacts(pair)
        root = _source_root(source_root)
        _verify_pristine_source(root, pair.baseline)
        _validate_anchor_against_source(root, pair)
        _validate_required_context(root)
        output_root = _project_materialization_root(materialization_root, root)

        prior = _make_neutral_prior()
        operator = _make_neutral_operator()
        strategy = _make_project_strategy(prior, operator)
        packages: list[SourceRichDiscoveryPackage] = []
        receipts: list[SyntheticProjectCommit] = []
        for variant in pair.variants:
            _verify_pristine_source(root, pair.baseline)
            worktree_path = output_root / variant.source_id
            receipt = _materialize_project_variant(root, pair, variant, output_root)
            created_worktrees.append(worktree_path)
            receipts.append(receipt)
            target = ProjectTarget(
                target_id=variant.source_id,
                source_origin=pair.baseline.origin,
                source_commit=receipt.synthetic_commit,
                worktree=receipt.worktree_path,
                scope=REQUIRED_CONTEXT_PATHS,
                discovery_budget=REQUIRED_CONTEXT_BUDGET,
            )
            acquired = _acquire_project_context_for_admission(target)
            _verify_project_materialization(output_root, pair, variant, receipt)
            source_facts = _source_facts(
                pair,
                candidate,
                source_commit=receipt.synthetic_commit,
                source_file_sha256=receipt.target_file_sha256,
            )
            acquired = _augment_context(acquired, source_facts)
            context = OpenCalcContextAcquisition(acquired)
            campaign = _make_project_campaign(
                target,
                acquired,
                prior,
                operator,
                strategy,
            )
            quality_contract = campaign.campaign.quality_contracts[0]
            risk_hypothesis = campaign.campaign.hypotheses[0]
            attack_plan = campaign.campaign.attack_plans[0]
            risk_priority = campaign.risk_priority
            if risk_priority is None:
                _project_fail("campaign_priority_missing")
            packages.append(
                SourceRichDiscoveryPackage(
                    package_id=f"{PAIR_ID}-{variant.variant_id}-project-package-v1",
                    catalog_id=(
                        f"opencalc-input-save-enabled-{variant.variant_id}-project-v1"
                    ),
                    target=target,
                    pair=pair,
                    variant=variant,
                    context_acquisition=context,
                    campaign=campaign,
                    behavior_delta=None,
                    contract_drift=None,
                    quality_contract=quality_contract,
                    risk_prior=campaign.campaign.risk_priors[0],
                    attack_operator=campaign.campaign.attack_operators[0],
                    risk_hypothesis=risk_hypothesis,
                    attack_plan=attack_plan,
                    risk_priority=risk_priority,
                    exploration_policy_id=EXPLORATION_POLICY_ID,
                    synthetic_commit=receipt,
                )
            )

        final_candidate, final_pair = _validate_candidate(candidate_root)
        _validate_patch_artifacts(final_pair)
        if (
            final_candidate.candidate_identity_sha256
            != candidate.candidate_identity_sha256
            or final_candidate.manifest_sha256 != candidate.manifest_sha256
            or final_candidate.artifact_inventory_sha256
            != candidate.artifact_inventory_sha256
            or final_pair != pair
        ):
            _project_fail("candidate_input_drift")
        candidate = final_candidate
        for variant, receipt in zip(pair.variants, receipts):
            _verify_project_materialization(output_root, pair, variant, receipt)
        projections = [
            _build_projection(candidate, packages[0], PROJECT_CONTROL_LANE_ID),
            _build_projection(candidate, packages[1], PROJECT_DEFECT_LANE_ID),
        ]
        leakage = audit_projection_leakage(projections)
        _verify_pristine_source(root, pair.baseline)
        return ProjectTargetDiscoveryResult(
            candidate_identity_sha256=candidate.candidate_identity_sha256,
            candidate_manifest_sha256=candidate.manifest_sha256,
            candidate_artifact_inventory_sha256=candidate.artifact_inventory_sha256,
            pair=pair,
            packages=tuple(packages),
            projections=tuple(projections),
            source_materializations=tuple(receipts),
            leakage_audit=leakage,
        )
    except ProjectTargetAdmissionError:
        if output_root is not None:
            for worktree in created_worktrees:
                _discard_project_worktree(output_root, worktree)
        raise
    except ChangeTargetAdmissionError as error:
        if output_root is not None:
            for worktree in created_worktrees:
                _discard_project_worktree(output_root, worktree)
        raise ProjectTargetAdmissionError(error.code) from error


admit_opencalc_change_pair = admit_change_target_pair
run_change_target_discovery = admit_change_target_pair
build_change_target_campaigns = admit_change_target_pair
admit_opencalc_project_pair = admit_project_target_pair
admit_opencalc_project_target_pair = admit_project_target_pair
run_project_target_discovery = admit_project_target_pair
build_project_target_campaigns = admit_project_target_pair


__all__ = [
    "ATTACK_OPERATOR_ID",
    "ATTACK_PLAN_ID",
    "CONTROL_LANE_ID",
    "DEFAULT_CANDIDATE_ROOT",
    "DEFAULT_SOURCE_ROOT",
    "DEFECT_LANE_ID",
    "ENGINE_CONTEXT_ADAPTERS",
    "EXPLORATION_POLICY_ID",
    "PAIR_ID",
    "PATCH_ARTIFACT_DIRECTORY",
    "PROJECTION_LEAKAGE_TERMS",
    "PROJECT_CONTROL_LANE_ID",
    "PROJECT_DEFECT_LANE_ID",
    "PROJECT_LANE_IDS",
    "QUALITY_CONTRACT_ID",
    "REQUIRED_CONTEXT_ADAPTERS",
    "REQUIRED_CONTEXT_BUDGET",
    "REQUIRED_CONTEXT_PATHS",
    "RISK_HYPOTHESIS_ID",
    "RISK_PRIOR_ID",
    "SYNTHETIC_AUTHOR_EMAIL",
    "SYNTHETIC_AUTHOR_NAME",
    "SYNTHETIC_COMMIT_MESSAGE",
    "SYNTHETIC_COMMIT_TIMESTAMP",
    "TARGET_SOURCE_PATH",
    "BlindRuntimeProjection",
    "ChangeTargetAdmissionError",
    "ChangeTargetDiscoveryResult",
    "LeakageAudit",
    "MatchedRuntimeSourcePair",
    "MatchedSourceVariant",
    "OpenCalcContextAcquisition",
    "OpenCalcDiscoveryError",
    "ProjectTargetAdmissionError",
    "ProjectTargetDiscoveryAdmission",
    "ProjectTargetDiscoveryError",
    "ProjectTargetDiscoveryResult",
    "ProjectTargetMaterializationReceipt",
    "SourceBaseline",
    "SourceRichDiscoveryPackage",
    "SyntheticCommitReceipt",
    "SyntheticProjectCommit",
    "UpstreamSourceAnchor",
    "admit_change_target_pair",
    "admit_opencalc_change_pair",
    "admit_opencalc_project_pair",
    "admit_opencalc_project_target_pair",
    "admit_project_target_pair",
    "audit_driver_serializations",
    "audit_projection_leakage",
    "build_change_target_campaigns",
    "build_project_target_campaigns",
    "run_change_target_discovery",
    "run_project_target_discovery",
]
