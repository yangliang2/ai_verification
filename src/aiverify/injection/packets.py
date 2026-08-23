"""Blind-safe, verifier-facing source-target packet compilation.

This module is deliberately a packet-contract boundary.  It consumes a sealed
auditor-side pair, rechecks its catalog and Disclosure Policy provenance, and
returns a public packet that contains only the bounded source target needed by
a future Verification Agent.  It neither invokes Discovery Campaign nor creates
a Run Spec or an execution attempt.
"""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from aiverify.injection.admission import InjectionAdmission
from aiverify.injection.catalog import (
    CheckedInCuratedSourceCatalog,
    CuratedCatalogError,
    CuratedSourceEntry,
    load_curated_source_catalog,
)
from aiverify.injection.disclosure import (
    CataloguedDisclosureReview,
    DisclosurePolicy,
    review_catalogued_admission,
    review_visible_packet_material,
)
from aiverify.injection.materialization import (
    InjectionMaterializerError,
    source_tree_sha256_from_worktree,
)
from aiverify.injection.models import (
    SCHEMA_VERSION,
    InjectionContractError,
    InjectionReceipt,
    canonical_json_bytes,
    sha256_hex,
)

_CHANGE_TARGET_KIND = "change_target"
_CHANGE_TARGET_CLAIM_BOUNDARY = "m0_structural_blind_change_target_packet_only"
_PROJECT_TARGET_KIND = "project_target"
_PROJECT_TARGET_CLAIM_BOUNDARY = "m0_structural_blind_project_target_packet_only"
_FOUR_CELL_FAMILY_CLAIM_BOUNDARY = "m0_structural_four_cell_verifier_packet_only"
_AUDITOR_MAPPING_CLAIM_BOUNDARY = "m0_structural_four_cell_auditor_mapping_only"
_SHA256_CHARS = frozenset("0123456789abcdef")
_VARIANTS = frozenset({"defect", "control"})
_PROJECT_SCOPE_GLOB_CHARS = frozenset("*?[]{}")


class PacketCompilationError(InjectionContractError):
    """A deterministic, non-disclosing rejection at the packet boundary.

    Lower-level exceptions are deliberately suppressed when this error crosses
    the public boundary because filesystem and catalog messages can name
    auditor-private paths or values.
    """

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InjectionContractError(f"{field} must be a non-empty string")
    return value


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field)
    if len(text) != 64 or any(character not in _SHA256_CHARS for character in text):
        raise InjectionContractError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise InjectionContractError(
            f"unknown {label} field(s): " + ", ".join(unknown)
        )


def _identity(value: Mapping[str, Any]) -> str:
    return sha256_hex(canonical_json_bytes(value))


@dataclass(frozen=True)
class AuditorCase:
    """Private audit context for one sealed source variant.

    ``expected_symptom``, ``oracle``, and ``admission_rationale`` deliberately
    have no public serializer.  Their values remain available to the auditor
    but must never become fields in :class:`VerifierPacket`.
    """

    admission: InjectionAdmission
    disclosure_review: CataloguedDisclosureReview
    expected_symptom: str
    oracle: str
    admission_rationale: str

    def __post_init__(self) -> None:
        if not isinstance(self.admission, InjectionAdmission):
            raise InjectionContractError("auditor case admission must be InjectionAdmission")
        if not isinstance(self.disclosure_review, CataloguedDisclosureReview):
            raise InjectionContractError(
                "auditor case disclosure_review must be CataloguedDisclosureReview"
            )
        for field in ("expected_symptom", "oracle", "admission_rationale"):
            _required_text(getattr(self, field), f"auditor case {field}")


@dataclass(frozen=True)
class AuditorPair:
    """Private defect/control pairing required before a packet can compile."""

    defect: AuditorCase
    control: AuditorCase

    def __post_init__(self) -> None:
        if not isinstance(self.defect, AuditorCase):
            raise InjectionContractError("auditor pair defect must be AuditorCase")
        if not isinstance(self.control, AuditorCase):
            raise InjectionContractError("auditor pair control must be AuditorCase")


@dataclass(frozen=True)
class VerifierPacket:
    """The public, bounded ChangeTarget packet for a future Verification Agent.

    It keeps the actual unified diff and its immutable provenance, while
    omitting source/catalog IDs, hidden variant, operator/taxonomy details,
    expected symptom, oracle, and audit admission rationale.
    """

    packet_id: str
    source_origin: str
    source_commit: str
    baseline_source_tree_sha256: str
    materialized_source_tree_sha256: str
    worktree_path: str
    patch_format: str
    patch_path: str
    patch_text: str
    patch_sha256: str
    result_diff_sha256: str
    receipt_identity_sha256: str
    target_kind: str = _CHANGE_TARGET_KIND
    claim_boundary: str = _CHANGE_TARGET_CLAIM_BOUNDARY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.packet_id, "verifier packet packet_id")
        _required_text(self.source_origin, "verifier packet source_origin")
        _required_text(self.source_commit, "verifier packet source_commit")
        _sha256(
            self.baseline_source_tree_sha256,
            "verifier packet baseline_source_tree_sha256",
        )
        _sha256(
            self.materialized_source_tree_sha256,
            "verifier packet materialized_source_tree_sha256",
        )
        path = Path(self.worktree_path)
        if not self.worktree_path or not path.is_absolute():
            raise InjectionContractError("verifier packet worktree_path must be absolute")
        if self.patch_format != "unified_diff":
            raise InjectionContractError("verifier packet patch_format must be unified_diff")
        patch_path = Path(self.patch_path)
        if not self.patch_path or not patch_path.is_absolute():
            raise InjectionContractError("verifier packet patch_path must be absolute")
        _required_text(self.patch_text, "verifier packet patch_text")
        _sha256(self.patch_sha256, "verifier packet patch_sha256")
        if self.patch_sha256 != sha256_hex(self.patch_text):
            raise InjectionContractError("verifier packet patch_sha256 does not match patch_text")
        _sha256(self.result_diff_sha256, "verifier packet result_diff_sha256")
        _sha256(
            self.receipt_identity_sha256,
            "verifier packet receipt_identity_sha256",
        )
        if self.target_kind != _CHANGE_TARGET_KIND:
            raise InjectionContractError("verifier packet target_kind must be change_target")
        if self.claim_boundary != _CHANGE_TARGET_CLAIM_BOUNDARY:
            raise InjectionContractError(
                "verifier packet claim_boundary must be M0 blind ChangeTarget only"
            )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported verifier packet schema_version")

    def _identity_dict(self) -> dict[str, Any]:
        """Return immutable source binding fields, excluding delivery location."""
        return {
            "schema_version": self.schema_version,
            "target_kind": self.target_kind,
            "packet_id": self.packet_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "baseline_source_tree_sha256": self.baseline_source_tree_sha256,
            "materialized_source_tree_sha256": self.materialized_source_tree_sha256,
            "patch_format": self.patch_format,
            "patch_text": self.patch_text,
            "patch_sha256": self.patch_sha256,
            "result_diff_sha256": self.result_diff_sha256,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "claim_boundary": self.claim_boundary,
        }

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_dict(),
            # A worktree location is verifier-visible delivery context, not a
            # source identity: fresh owned materializations intentionally get
            # distinct paths for the same immutable source result.
            "worktree_path": self.worktree_path,
            "patch_path": self.patch_path,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VerifierPacket:
        """Parse one complete public packet and revalidate its identity."""
        if not isinstance(data, Mapping):
            raise InjectionContractError("verifier packet must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "target_kind",
                "packet_id",
                "source_origin",
                "source_commit",
                "baseline_source_tree_sha256",
                "materialized_source_tree_sha256",
                "worktree_path",
                "patch_format",
                "patch_path",
                "patch_text",
                "patch_sha256",
                "result_diff_sha256",
                "receipt_identity_sha256",
                "claim_boundary",
                "identity_sha256",
            },
            "verifier packet",
        )
        try:
            value = cls(
                schema_version=data["schema_version"],
                target_kind=data["target_kind"],
                packet_id=data["packet_id"],
                source_origin=data["source_origin"],
                source_commit=data["source_commit"],
                baseline_source_tree_sha256=data["baseline_source_tree_sha256"],
                materialized_source_tree_sha256=data[
                    "materialized_source_tree_sha256"
                ],
                worktree_path=data["worktree_path"],
                patch_format=data["patch_format"],
                patch_path=data["patch_path"],
                patch_text=data["patch_text"],
                patch_sha256=data["patch_sha256"],
                result_diff_sha256=data["result_diff_sha256"],
                receipt_identity_sha256=data["receipt_identity_sha256"],
                claim_boundary=data["claim_boundary"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "verifier packet identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"verifier packet requires {error.args[0]}"
            ) from error

    @property
    def canonical_bytes(self) -> bytes:
        """Return the exact deterministic verifier-visible packet bytes."""
        return canonical_json_bytes(self.to_dict())


def _canonical_project_scope(scope: object) -> tuple[str, ...]:
    """Require a finite, canonical set of project-relative source paths."""
    if not isinstance(scope, tuple) or not scope:
        raise InjectionContractError(
            "project target packet scope must be a non-empty tuple"
        )
    if any(not isinstance(item, str) or not item.strip() for item in scope):
        raise InjectionContractError(
            "project target packet scope must contain non-empty strings"
        )
    if scope != tuple(sorted(scope)) or len(set(scope)) != len(scope):
        raise InjectionContractError(
            "project target packet scope must be sorted and unique"
        )
    for item in scope:
        path = PurePosixPath(item)
        if (
            item != path.as_posix()
            or path.is_absolute()
            or path == PurePosixPath(".")
            or "\\" in item
            or any(part in {".", "..", ".git"} for part in path.parts)
            or any(character in _PROJECT_SCOPE_GLOB_CHARS for character in item)
        ):
            raise InjectionContractError(
                "project target packet scope must contain canonical relative paths"
            )
    return scope


def _bounded_discovery_budget(value: object) -> int:
    """Require an explicit finite Discovery Campaign budget."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        raise InjectionContractError(
            "project target packet discovery_budget must be a positive integer"
        )
    return value


@dataclass(frozen=True)
class ProjectTargetPacket:
    """The public, bounded ProjectTarget packet for a future Verification Agent.

    The packet binds the complete materialized project through its immutable
    source-tree digest, then bounds any later discovery work by exact source
    scope and an explicit finite budget.  It intentionally contains no diff,
    patch, hidden variant, operator/taxonomy details, expected symptom, oracle,
    or audit admission rationale.
    """

    packet_id: str
    source_origin: str
    source_commit: str
    baseline_source_tree_sha256: str
    materialized_source_tree_sha256: str
    worktree_path: str
    scope: tuple[str, ...]
    discovery_budget: int
    receipt_identity_sha256: str
    target_kind: str = _PROJECT_TARGET_KIND
    claim_boundary: str = _PROJECT_TARGET_CLAIM_BOUNDARY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.packet_id, "project target packet packet_id")
        _required_text(self.source_origin, "project target packet source_origin")
        _required_text(self.source_commit, "project target packet source_commit")
        _sha256(
            self.baseline_source_tree_sha256,
            "project target packet baseline_source_tree_sha256",
        )
        _sha256(
            self.materialized_source_tree_sha256,
            "project target packet materialized_source_tree_sha256",
        )
        path = Path(self.worktree_path)
        if not self.worktree_path or not path.is_absolute():
            raise InjectionContractError(
                "project target packet worktree_path must be absolute"
            )
        _canonical_project_scope(self.scope)
        _bounded_discovery_budget(self.discovery_budget)
        _sha256(
            self.receipt_identity_sha256,
            "project target packet receipt_identity_sha256",
        )
        if self.target_kind != _PROJECT_TARGET_KIND:
            raise InjectionContractError(
                "project target packet target_kind must be project_target"
            )
        if self.claim_boundary != _PROJECT_TARGET_CLAIM_BOUNDARY:
            raise InjectionContractError(
                "project target packet claim_boundary must be M0 blind ProjectTarget only"
            )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError(
                "unsupported project target packet schema_version"
            )

    def _identity_dict(self) -> dict[str, Any]:
        """Return immutable source and discovery bounds, excluding delivery path."""
        return {
            "schema_version": self.schema_version,
            "target_kind": self.target_kind,
            "packet_id": self.packet_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "baseline_source_tree_sha256": self.baseline_source_tree_sha256,
            "materialized_source_tree_sha256": self.materialized_source_tree_sha256,
            "scope": list(self.scope),
            "discovery_budget": self.discovery_budget,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "claim_boundary": self.claim_boundary,
        }

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_dict(),
            # The owned worktree is verifier-visible delivery context, not
            # immutable source identity: a fresh materialization has a new
            # location while preserving the same source result.
            "worktree_path": self.worktree_path,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ProjectTargetPacket:
        """Parse one complete public ProjectTarget packet and rebind its identity."""
        if not isinstance(data, Mapping):
            raise InjectionContractError("project target packet must be an object")
        allowed = {
            "schema_version",
            "target_kind",
            "packet_id",
            "source_origin",
            "source_commit",
            "baseline_source_tree_sha256",
            "materialized_source_tree_sha256",
            "worktree_path",
            "scope",
            "discovery_budget",
            "receipt_identity_sha256",
            "claim_boundary",
            "identity_sha256",
        }
        if set(data) - allowed:
            # A malformed verifier-visible packet might itself carry a private
            # sentinel in an unexpected field name.  Keep parser failures
            # fixed rather than reflecting that name to a caller.
            raise InjectionContractError(
                "project target packet contains unknown fields"
            )
        try:
            raw_scope = data["scope"]
            if not isinstance(raw_scope, list):
                raise InjectionContractError(
                    "project target packet scope must be an array"
                )
            value = cls(
                schema_version=data["schema_version"],
                target_kind=data["target_kind"],
                packet_id=data["packet_id"],
                source_origin=data["source_origin"],
                source_commit=data["source_commit"],
                baseline_source_tree_sha256=data["baseline_source_tree_sha256"],
                materialized_source_tree_sha256=data[
                    "materialized_source_tree_sha256"
                ],
                worktree_path=data["worktree_path"],
                scope=tuple(raw_scope),
                discovery_budget=data["discovery_budget"],
                receipt_identity_sha256=data["receipt_identity_sha256"],
                claim_boundary=data["claim_boundary"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "project target packet identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"project target packet requires {error.args[0]}"
            ) from error

    @property
    def canonical_bytes(self) -> bytes:
        """Return the exact deterministic verifier-visible packet bytes."""
        return canonical_json_bytes(self.to_dict())


def _canonical_family_packets(
    packets: object,
) -> tuple[VerifierPacket | ProjectTargetPacket, ...]:
    """Require exactly two packets for each public target mode.

    The public side intentionally has no variant field.  It can establish only
    that the four bounded packet shapes are complete and uniquely identified;
    the private mapping establishes which hidden variant produced each packet.
    """
    if not isinstance(packets, tuple) or len(packets) != 4:
        raise InjectionContractError(
            "verifier packet family must contain exactly four packets"
        )
    if not all(isinstance(packet, (VerifierPacket, ProjectTargetPacket)) for packet in packets):
        raise InjectionContractError(
            "verifier packet family packets must be public packet objects"
        )
    target_kinds = tuple(packet.target_kind for packet in packets)
    if target_kinds.count(_CHANGE_TARGET_KIND) != 2 or target_kinds.count(
        _PROJECT_TARGET_KIND
    ) != 2:
        raise InjectionContractError(
            "verifier packet family must contain two packets for each target kind"
        )
    packet_ids = tuple(packet.packet_id for packet in packets)
    if len(set(packet_ids)) != len(packet_ids):
        raise InjectionContractError("verifier packet family packet IDs must be unique")
    return tuple(
        sorted(
            packets,
            key=lambda packet: (
                packet.target_kind,
                packet.packet_id,
                packet.identity_sha256,
            ),
        )
    )


def _four_cell_family_id(
    packets: tuple[VerifierPacket | ProjectTargetPacket, ...],
) -> str:
    """Derive an opaque stable family ID from public packet identities only."""
    binding = _identity(
        {
            "schema_version": SCHEMA_VERSION,
            "claim_boundary": _FOUR_CELL_FAMILY_CLAIM_BOUNDARY,
            "packets": [
                {
                    "target_kind": packet.target_kind,
                    "packet_id": packet.packet_id,
                    "identity_sha256": packet.identity_sha256,
                }
                for packet in packets
            ],
        }
    )
    return f"four-cell-family-{binding[:24]}"


@dataclass(frozen=True)
class VerifierPacketFamily:
    """The four public packet shapes, without audit-side mapping information.

    This is the only family-shaped object that can be serialized for a future
    Verification Agent.  Its parser rejects any attached auditor mapping and
    it has no field through which private variant or audit-package data can
    cross into verifier input.
    """

    packets: tuple[VerifierPacket | ProjectTargetPacket, ...]
    family_id: str = ""
    claim_boundary: str = _FOUR_CELL_FAMILY_CLAIM_BOUNDARY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        canonical_packets = _canonical_family_packets(self.packets)
        object.__setattr__(self, "packets", canonical_packets)
        expected_family_id = _four_cell_family_id(canonical_packets)
        if self.family_id == "":
            object.__setattr__(self, "family_id", expected_family_id)
        else:
            _required_text(self.family_id, "verifier packet family family_id")
        if self.family_id != expected_family_id:
            raise InjectionContractError(
                "verifier packet family ID does not match its packets"
            )
        if self.claim_boundary != _FOUR_CELL_FAMILY_CLAIM_BOUNDARY:
            raise InjectionContractError(
                "verifier packet family claim boundary must be four-cell structural only"
            )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported verifier packet family schema_version")

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "claim_boundary": self.claim_boundary,
            "packets": [
                {
                    "packet_id": packet.packet_id,
                    "identity_sha256": packet.identity_sha256,
                }
                for packet in self.packets
            ],
        }

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "claim_boundary": self.claim_boundary,
            "packets": [packet.to_dict() for packet in self.packets],
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> VerifierPacketFamily:
        """Parse public family bytes while refusing any private attachment."""
        if not isinstance(data, Mapping):
            raise InjectionContractError("verifier packet family must be an object")
        allowed = {
            "schema_version",
            "family_id",
            "claim_boundary",
            "packets",
            "identity_sha256",
        }
        if set(data) - allowed:
            raise InjectionContractError("verifier packet family contains unknown fields")
        try:
            raw_packets = data["packets"]
            if not isinstance(raw_packets, list):
                raise InjectionContractError("verifier packet family packets must be an array")
            packets: list[VerifierPacket | ProjectTargetPacket] = []
            for raw_packet in raw_packets:
                if not isinstance(raw_packet, Mapping):
                    raise InjectionContractError(
                        "verifier packet family packets must be objects"
                    )
                target_kind = raw_packet.get("target_kind")
                if target_kind == _CHANGE_TARGET_KIND:
                    packets.append(VerifierPacket.from_dict(raw_packet))
                elif target_kind == _PROJECT_TARGET_KIND:
                    packets.append(ProjectTargetPacket.from_dict(raw_packet))
                else:
                    raise InjectionContractError(
                        "verifier packet family contains an unsupported packet"
                    )
            value = cls(
                schema_version=data["schema_version"],
                family_id=data["family_id"],
                claim_boundary=data["claim_boundary"],
                packets=tuple(packets),
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "verifier packet family identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"verifier packet family requires {error.args[0]}"
            ) from error

    @property
    def canonical_bytes(self) -> bytes:
        """Return the deterministic public-family bytes without audit data."""
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class AuditorMappingEntry:
    """One private binding from a public packet to its audit-side package."""

    packet_id: str
    target_kind: str
    hidden_variant: str
    audit_package_identity_sha256: str

    def __post_init__(self) -> None:
        _required_text(self.packet_id, "auditor mapping entry packet_id")
        if self.target_kind not in {_CHANGE_TARGET_KIND, _PROJECT_TARGET_KIND}:
            raise InjectionContractError(
                "auditor mapping entry target_kind must be a supported target kind"
            )
        if self.hidden_variant not in _VARIANTS:
            raise InjectionContractError(
                "auditor mapping entry hidden_variant must be defect or control"
            )
        _sha256(
            self.audit_package_identity_sha256,
            "auditor mapping entry audit_package_identity_sha256",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "packet_id": self.packet_id,
            "target_kind": self.target_kind,
            "hidden_variant": self.hidden_variant,
            "audit_package_identity_sha256": self.audit_package_identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AuditorMappingEntry:
        if not isinstance(data, Mapping):
            raise InjectionContractError("auditor mapping entry must be an object")
        allowed = {
            "packet_id",
            "target_kind",
            "hidden_variant",
            "audit_package_identity_sha256",
        }
        if set(data) - allowed:
            raise InjectionContractError("auditor mapping entry contains unknown fields")
        try:
            return cls(
                packet_id=data["packet_id"],
                target_kind=data["target_kind"],
                hidden_variant=data["hidden_variant"],
                audit_package_identity_sha256=data["audit_package_identity_sha256"],
            )
        except KeyError as error:
            raise InjectionContractError(
                f"auditor mapping entry requires {error.args[0]}"
            ) from error


def _canonical_mapping_entries(
    entries: object,
) -> tuple[AuditorMappingEntry, ...]:
    """Require the one complete private matrix in canonical audit order."""
    if not isinstance(entries, tuple) or len(entries) != 4:
        raise InjectionContractError("auditor mapping must contain exactly four entries")
    if not all(isinstance(entry, AuditorMappingEntry) for entry in entries):
        raise InjectionContractError("auditor mapping entries must be mapping entry objects")
    cells = {(entry.target_kind, entry.hidden_variant) for entry in entries}
    expected_cells = {
        (target_kind, variant)
        for target_kind in (_CHANGE_TARGET_KIND, _PROJECT_TARGET_KIND)
        for variant in ("defect", "control")
    }
    if cells != expected_cells:
        raise InjectionContractError("auditor mapping must bind all four target cells")
    packet_ids = tuple(entry.packet_id for entry in entries)
    if len(set(packet_ids)) != len(packet_ids):
        raise InjectionContractError("auditor mapping packet IDs must be unique")
    return tuple(
        sorted(
            entries,
            key=lambda entry: (
                entry.target_kind,
                entry.hidden_variant,
                entry.packet_id,
            ),
        )
    )


@dataclass(frozen=True)
class AuditorMapping:
    """A separately serializable, audit-only four-cell mapping.

    Its bytes name the hidden variants and audit-package identities, so they are
    intentionally not accepted by any verifier-facing packet parser.
    """

    family_id: str
    entries: tuple[AuditorMappingEntry, ...]
    claim_boundary: str = _AUDITOR_MAPPING_CLAIM_BOUNDARY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.family_id, "auditor mapping family_id")
        canonical_entries = _canonical_mapping_entries(self.entries)
        object.__setattr__(self, "entries", canonical_entries)
        if self.claim_boundary != _AUDITOR_MAPPING_CLAIM_BOUNDARY:
            raise InjectionContractError(
                "auditor mapping claim boundary must be four-cell structural only"
            )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported auditor mapping schema_version")

    def _identity_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "family_id": self.family_id,
            "claim_boundary": self.claim_boundary,
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @property
    def identity_sha256(self) -> str:
        return _identity(self._identity_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            **self._identity_dict(),
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AuditorMapping:
        if not isinstance(data, Mapping):
            raise InjectionContractError("auditor mapping must be an object")
        allowed = {
            "schema_version",
            "family_id",
            "claim_boundary",
            "entries",
            "identity_sha256",
        }
        if set(data) - allowed:
            raise InjectionContractError("auditor mapping contains unknown fields")
        try:
            raw_entries = data["entries"]
            if not isinstance(raw_entries, list):
                raise InjectionContractError("auditor mapping entries must be an array")
            value = cls(
                schema_version=data["schema_version"],
                family_id=data["family_id"],
                claim_boundary=data["claim_boundary"],
                entries=tuple(
                    AuditorMappingEntry.from_dict(entry) for entry in raw_entries
                ),
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("auditor mapping identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(f"auditor mapping requires {error.args[0]}") from error

    @property
    def canonical_bytes(self) -> bytes:
        """Return private auditor bytes, separately from verifier-family bytes."""
        return canonical_json_bytes(self.to_dict())


@dataclass(frozen=True)
class AuditorCaseFamily:
    """The audit-side aggregate that binds the private pair, map, and public set.

    Deliberately no ``to_dict`` or ``canonical_bytes`` is provided: serializing
    this aggregate would combine the private mapping with verifier-facing input.
    Callers serialize ``verifier_packet_family`` or ``auditor_mapping`` at their
    respective boundaries instead.
    """

    verifier_packet_family: VerifierPacketFamily
    auditor_mapping: AuditorMapping
    pair: AuditorPair

    def __post_init__(self) -> None:
        if not isinstance(self.verifier_packet_family, VerifierPacketFamily):
            raise InjectionContractError(
                "auditor case family verifier_packet_family must be VerifierPacketFamily"
            )
        if not isinstance(self.auditor_mapping, AuditorMapping):
            raise InjectionContractError(
                "auditor case family auditor_mapping must be AuditorMapping"
            )
        if not isinstance(self.pair, AuditorPair):
            raise InjectionContractError("auditor case family pair must be AuditorPair")
        if self.auditor_mapping.family_id != self.verifier_packet_family.family_id:
            raise InjectionContractError(
                "auditor case family mapping family ID does not match public packets"
            )
        public_packet_ids = {
            packet.packet_id for packet in self.verifier_packet_family.packets
        }
        public_packet_kinds = {
            packet.packet_id: packet.target_kind
            for packet in self.verifier_packet_family.packets
        }
        mapped_packet_ids = {entry.packet_id for entry in self.auditor_mapping.entries}
        if mapped_packet_ids != public_packet_ids:
            raise InjectionContractError(
                "auditor case family mapping does not bind its packets"
            )
        if any(
            public_packet_kinds[entry.packet_id] != entry.target_kind
            for entry in self.auditor_mapping.entries
        ):
            raise InjectionContractError(
                "auditor case family mapping does not bind its packets"
            )
        package_identity_by_variant: dict[str, str] = {}
        for variant, case in (
            ("defect", self.pair.defect),
            ("control", self.pair.control),
        ):
            admission = case.admission
            if admission.status != "sealed" or admission.package is None:
                raise InjectionContractError(
                    "auditor case family requires sealed audit packages"
                )
            package_identity_by_variant[variant] = admission.package.identity_sha256
        if any(
            entry.audit_package_identity_sha256
            != package_identity_by_variant[entry.hidden_variant]
            for entry in self.auditor_mapping.entries
        ):
            raise InjectionContractError(
                "auditor case family mapping does not bind its packets"
            )


def _packet_id(
    *,
    source_origin: str,
    source_commit: str,
    baseline_source_tree_sha256: str,
    materialized_source_tree_sha256: str,
    patch_sha256: str,
    result_diff_sha256: str,
    receipt_identity_sha256: str,
) -> str:
    """Derive an opaque stable ID without an audit-side source or variant label."""
    binding = _identity(
        {
            "schema_version": SCHEMA_VERSION,
            "target_kind": _CHANGE_TARGET_KIND,
            "source_origin": source_origin,
            "source_commit": source_commit,
            "baseline_source_tree_sha256": baseline_source_tree_sha256,
            "materialized_source_tree_sha256": materialized_source_tree_sha256,
            "patch_sha256": patch_sha256,
            "result_diff_sha256": result_diff_sha256,
            "receipt_identity_sha256": receipt_identity_sha256,
        }
    )
    return f"change-target-{binding[:24]}"


def _project_packet_id(
    *,
    source_origin: str,
    source_commit: str,
    baseline_source_tree_sha256: str,
    materialized_source_tree_sha256: str,
    scope: tuple[str, ...],
    discovery_budget: int,
    receipt_identity_sha256: str,
) -> str:
    """Derive an opaque ID bound to project source and discovery limits."""
    binding = _identity(
        {
            "schema_version": SCHEMA_VERSION,
            "target_kind": _PROJECT_TARGET_KIND,
            "source_origin": source_origin,
            "source_commit": source_commit,
            "baseline_source_tree_sha256": baseline_source_tree_sha256,
            "materialized_source_tree_sha256": materialized_source_tree_sha256,
            "scope": list(scope),
            "discovery_budget": discovery_budget,
            "receipt_identity_sha256": receipt_identity_sha256,
        }
    )
    return f"project-target-{binding[:24]}"


def _require_packet_request(
    pair: object,
    variant: object,
    policy: object,
) -> tuple[AuditorPair, str, DisclosurePolicy]:
    """Validate the shared private input boundary before catalog access."""
    if not isinstance(pair, AuditorPair):
        raise PacketCompilationError("pair_missing")
    if not isinstance(variant, str) or variant not in _VARIANTS:
        raise PacketCompilationError("variant_not_declared")
    if not isinstance(policy, DisclosurePolicy):
        raise PacketCompilationError("disclosure_policy_invalid")
    return pair, variant, policy


def _entry_for_case(
    catalog: CheckedInCuratedSourceCatalog,
    case: AuditorCase,
) -> CuratedSourceEntry:
    try:
        return catalog.select(case.disclosure_review.source_id)
    except InjectionContractError:
        raise PacketCompilationError("pair_source_missing") from None


def _require_sealed_case(
    *,
    catalog_path: str | Path,
    catalog: CheckedInCuratedSourceCatalog,
    entry: CuratedSourceEntry,
    case: AuditorCase,
    policy: DisclosurePolicy,
) -> InjectionReceipt:
    """Rebind one private case to current catalog, admission, and policy bytes."""
    admission = case.admission
    if admission.status != "sealed" or admission.package is None or admission.receipt is None:
        raise PacketCompilationError("admission_not_sealed")
    receipt = admission.receipt
    if receipt.outcome != "materialized" or receipt.worktree is None:
        raise PacketCompilationError("admission_not_sealed")
    package = admission.package
    candidate = entry.candidate
    if not all(
        (
            package.source_id == entry.source_id,
            package.catalog_identity_sha256 == catalog.identity_sha256,
            package.catalog_source_sha256 == catalog.catalog_source_sha256,
            package.catalog_entry_identity_sha256 == entry.identity_sha256,
            package.candidate_identity_sha256 == candidate.identity_sha256,
            package.baseline_identity_sha256 == candidate.baseline.identity_sha256,
            package.patch_identity_sha256 == candidate.source_delta.identity_sha256,
            package.receipt_identity_sha256 == receipt.receipt_identity_sha256,
            receipt.candidate_identity_sha256 == candidate.identity_sha256,
            receipt.baseline_identity_sha256 == candidate.baseline.identity_sha256,
            receipt.patch_identity_sha256 == candidate.source_delta.identity_sha256,
            receipt.worktree.baseline_commit == candidate.baseline.commit,
        )
    ):
        raise PacketCompilationError("admission_provenance_mismatch")
    try:
        expected_review = review_catalogued_admission(
            catalog_path,
            entry.source_id,
            admission,
            policy,
        )
    except (
        CuratedCatalogError,
        InjectionContractError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        raise PacketCompilationError("disclosure_review_unavailable") from None
    if case.disclosure_review != expected_review:
        raise PacketCompilationError("disclosure_review_mismatch")
    if expected_review.status != "eligible":
        raise PacketCompilationError("disclosure_policy_rejected")
    return receipt


def _require_compatible_pair(
    defect_entry: CuratedSourceEntry,
    control_entry: CuratedSourceEntry,
) -> None:
    """Require one distinct defect/control pair over the same immutable baseline."""
    defect = defect_entry.candidate
    control = control_entry.candidate
    if defect_entry.source_id == control_entry.source_id:
        raise PacketCompilationError("pair_missing")
    if defect.variant != "defect" or control.variant != "control":
        raise PacketCompilationError("pair_variant_mismatch")
    if defect.baseline.identity_sha256 != control.baseline.identity_sha256:
        raise PacketCompilationError("pair_provenance_mismatch")
    if defect.source_delta.identity_sha256 == control.source_delta.identity_sha256:
        raise PacketCompilationError("pair_change_not_distinct")
    if defect_entry.population_classification != control_entry.population_classification:
        raise PacketCompilationError("pair_population_mismatch")
    if defect_entry.taxonomy_relationship != control_entry.taxonomy_relationship:
        raise PacketCompilationError("pair_taxonomy_mismatch")
    if defect_entry.fixture_anchor != control_entry.fixture_anchor:
        raise PacketCompilationError("pair_fixture_anchor_mismatch")


def _require_materialized_source(receipt: InjectionReceipt) -> None:
    """Confirm that the packet points at the receipt's actual source tree."""
    if receipt.worktree is None or receipt.result_source_tree_sha256 is None:
        raise PacketCompilationError("materialized_source_unavailable")
    try:
        observed = source_tree_sha256_from_worktree(receipt.worktree.path)
    except (
        InjectionMaterializerError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ):
        raise PacketCompilationError("materialized_source_unavailable") from None
    if observed != receipt.result_source_tree_sha256:
        raise PacketCompilationError("materialized_source_identity_mismatch")


def _selected_sealed_packet_input(
    *,
    catalog_path: str | Path,
    pair: AuditorPair,
    variant: str,
    policy: DisclosurePolicy,
) -> tuple[CuratedSourceEntry, InjectionReceipt]:
    """Rebind a pair and return the selected, unchanged materialized source."""
    try:
        catalog = load_curated_source_catalog(catalog_path)
    except CuratedCatalogError as error:
        raise PacketCompilationError(error.code) from None
    except (OSError, RuntimeError, TypeError, ValueError):
        raise PacketCompilationError("catalog_file_unavailable") from None
    defect_entry = _entry_for_case(catalog, pair.defect)
    control_entry = _entry_for_case(catalog, pair.control)
    defect_receipt = _require_sealed_case(
        catalog_path=catalog_path,
        catalog=catalog,
        entry=defect_entry,
        case=pair.defect,
        policy=policy,
    )
    control_receipt = _require_sealed_case(
        catalog_path=catalog_path,
        catalog=catalog,
        entry=control_entry,
        case=pair.control,
        policy=policy,
    )
    _require_compatible_pair(defect_entry, control_entry)
    selected_entry, selected_receipt = (
        (defect_entry, defect_receipt)
        if variant == "defect"
        else (control_entry, control_receipt)
    )
    _require_materialized_source(selected_receipt)
    return selected_entry, selected_receipt


def _require_project_scope_in_worktree(
    worktree_path: str,
    scope: tuple[str, ...],
) -> None:
    """Bind each public scope path to the selected immutable project tree."""
    try:
        root = Path(worktree_path).resolve(strict=True)
        if not root.is_dir():
            raise OSError
        for item in scope:
            resolved = root.joinpath(*PurePosixPath(item).parts).resolve(strict=True)
            resolved.relative_to(root)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise PacketCompilationError("project_scope_path_unavailable") from None


def _raise_walk_error(error: OSError) -> None:
    """Make an unreadable delivered source tree fail closed."""
    raise error


def _require_internal_project_link(root: Path, path: Path) -> str:
    """Return a symlink target only when it stays inside the delivered tree."""
    target = path.resolve(strict=True)
    target.relative_to(root)
    return os.readlink(path)


def _project_source_visibility_material(worktree_path: str) -> dict[str, Any]:
    """Build finite audit-side material for every delivered project entry.

    The verifier receives the worktree root, rather than only the requested
    scope paths.  Therefore the whole source tree—not merely the scope—must be
    checked for declared disclosures.  Regular-file bytes use UTF-8 replacement
    decoding so ordinary textual sentinels remain detectable without claiming a
    semantic analysis of binary material.
    """
    root = Path(worktree_path).resolve(strict=True)
    if not root.is_dir():
        raise OSError
    entries: list[dict[str, str]] = []
    for current, directory_names, file_names in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=_raise_walk_error,
    ):
        current_path = Path(current)
        directory_names.sort(key=os.fsencode)
        file_names.sort(key=os.fsencode)

        retained_directories: list[str] = []
        for name in directory_names:
            path = current_path / name
            relative_path = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if current_path == root and name == ".git":
                # A materialized linked worktree has a .git control file.  A
                # directory would expose unbounded repository metadata.
                raise OSError
            if stat.S_ISDIR(mode):
                entries.append({"kind": "directory", "path": relative_path})
                retained_directories.append(name)
            elif stat.S_ISLNK(mode):
                entries.append(
                    {
                        "kind": "symlink",
                        "path": relative_path,
                        "target": _require_internal_project_link(root, path),
                    }
                )
            else:
                raise OSError
        directory_names[:] = retained_directories

        for name in file_names:
            path = current_path / name
            relative_path = path.relative_to(root).as_posix()
            mode = path.lstat().st_mode
            if stat.S_ISREG(mode):
                entries.append(
                    {
                        "kind": "file",
                        "path": relative_path,
                        "text": path.read_bytes().decode(
                            "utf-8",
                            errors="replace",
                        ),
                    }
                )
            elif stat.S_ISLNK(mode):
                entries.append(
                    {
                        "kind": "symlink",
                        "path": relative_path,
                        "target": _require_internal_project_link(root, path),
                    }
                )
            else:
                raise OSError
    return {"source_tree": entries}


def _require_project_packet_disclosure_safe(
    policy: DisclosurePolicy,
    packet: ProjectTargetPacket,
) -> None:
    """Reject any declared sentinel in a public packet or delivered project."""
    try:
        material = {
            "packet": packet.to_dict(),
            **_project_source_visibility_material(packet.worktree_path),
        }
        review = review_visible_packet_material(policy, material)
    except (
        InjectionContractError,
        OSError,
        RuntimeError,
        TypeError,
        UnicodeError,
        ValueError,
    ):
        raise PacketCompilationError("project_source_visibility_unavailable") from None
    if review.status != "eligible":
        raise PacketCompilationError("packet_disclosure_detected")


def _require_declared_patch_path(
    catalog_path: str | Path,
    entry: CuratedSourceEntry,
) -> str:
    """Return the real checked-in patch path bound to the selected entry."""
    try:
        root = Path(catalog_path).resolve().parent
        candidate = root.joinpath(*PurePosixPath(entry.patch_path).parts)
        path = candidate.resolve(strict=True)
        path.relative_to(root)
        if not path.is_file() or path.read_bytes() != entry.candidate.source_delta.patch_text.encode(
            "utf-8"
        ):
            raise OSError
    except (OSError, RuntimeError, ValueError, TypeError):
        raise PacketCompilationError("packet_patch_unavailable") from None
    return str(path)


def compile_change_target_packet(
    *,
    catalog_path: str | Path,
    pair: AuditorPair,
    variant: str,
    policy: DisclosurePolicy,
) -> VerifierPacket:
    """Compile one blind-safe ChangeTarget packet from a sealed private pair.

    The result never contains the hidden variant or any auditor-only labels.
    Rejections use fixed codes and return no partial verifier-facing packet.
    """
    pair, variant, policy = _require_packet_request(pair, variant, policy)
    selected_entry, selected_receipt = _selected_sealed_packet_input(
        catalog_path=catalog_path,
        pair=pair,
        variant=variant,
        policy=policy,
    )
    patch_path = _require_declared_patch_path(catalog_path, selected_entry)
    if (
        selected_receipt.result_source_tree_sha256 is None
        or selected_receipt.result_diff_sha256 is None
        or selected_receipt.worktree is None
    ):
        raise PacketCompilationError("materialized_source_unavailable")
    candidate = selected_entry.candidate
    packet = VerifierPacket(
        packet_id=_packet_id(
            source_origin=candidate.baseline.source_origin,
            source_commit=candidate.baseline.commit,
            baseline_source_tree_sha256=candidate.baseline.source_tree_sha256,
            materialized_source_tree_sha256=selected_receipt.result_source_tree_sha256,
            patch_sha256=candidate.source_delta.patch_sha256,
            result_diff_sha256=selected_receipt.result_diff_sha256,
            receipt_identity_sha256=selected_receipt.receipt_identity_sha256,
        ),
        source_origin=candidate.baseline.source_origin,
        source_commit=candidate.baseline.commit,
        baseline_source_tree_sha256=candidate.baseline.source_tree_sha256,
        materialized_source_tree_sha256=selected_receipt.result_source_tree_sha256,
        worktree_path=selected_receipt.worktree.path,
        patch_format=candidate.source_delta.format,
        patch_path=patch_path,
        patch_text=candidate.source_delta.patch_text,
        patch_sha256=candidate.source_delta.patch_sha256,
        result_diff_sha256=selected_receipt.result_diff_sha256,
        receipt_identity_sha256=selected_receipt.receipt_identity_sha256,
    )
    if review_visible_packet_material(policy, packet.to_dict()).status != "eligible":
        raise PacketCompilationError("packet_disclosure_detected")
    return packet


def compile_project_target_packet(
    *,
    catalog_path: str | Path,
    pair: AuditorPair,
    variant: str,
    policy: DisclosurePolicy,
    scope: tuple[str, ...],
    discovery_budget: int,
) -> ProjectTargetPacket:
    """Compile one blind-safe ProjectTarget packet from a sealed private pair.

    The packet names a complete, materialized source project and bounds a future
    discovery consumer to explicit source paths plus a finite budget.  It never
    emits a diff or an auditor-side outcome label, and it has no runtime effects.
    """
    pair, variant, policy = _require_packet_request(pair, variant, policy)
    try:
        canonical_scope = _canonical_project_scope(scope)
    except InjectionContractError:
        raise PacketCompilationError("project_scope_unbounded") from None
    try:
        bounded_budget = _bounded_discovery_budget(discovery_budget)
    except InjectionContractError:
        raise PacketCompilationError("discovery_budget_unbounded") from None
    selected_entry, selected_receipt = _selected_sealed_packet_input(
        catalog_path=catalog_path,
        pair=pair,
        variant=variant,
        policy=policy,
    )
    if (
        selected_receipt.result_source_tree_sha256 is None
        or selected_receipt.worktree is None
    ):
        raise PacketCompilationError("materialized_source_unavailable")
    candidate = selected_entry.candidate
    packet = ProjectTargetPacket(
        packet_id=_project_packet_id(
            source_origin=candidate.baseline.source_origin,
            source_commit=candidate.baseline.commit,
            baseline_source_tree_sha256=candidate.baseline.source_tree_sha256,
            materialized_source_tree_sha256=selected_receipt.result_source_tree_sha256,
            scope=canonical_scope,
            discovery_budget=bounded_budget,
            receipt_identity_sha256=selected_receipt.receipt_identity_sha256,
        ),
        source_origin=candidate.baseline.source_origin,
        source_commit=candidate.baseline.commit,
        baseline_source_tree_sha256=candidate.baseline.source_tree_sha256,
        materialized_source_tree_sha256=selected_receipt.result_source_tree_sha256,
        worktree_path=selected_receipt.worktree.path,
        scope=canonical_scope,
        discovery_budget=bounded_budget,
        receipt_identity_sha256=selected_receipt.receipt_identity_sha256,
    )
    # The visibility review precedes scope path resolution so a sentinel in an
    # otherwise invalid requested path cannot influence which error crosses the
    # public boundary.
    _require_project_packet_disclosure_safe(policy, packet)
    _require_project_scope_in_worktree(packet.worktree_path, packet.scope)
    return packet


def compile_four_cell_case_family(
    *,
    catalog_path: str | Path,
    pair: AuditorPair,
    policy: DisclosurePolicy,
    scope: tuple[str, ...],
    discovery_budget: int,
) -> AuditorCaseFamily:
    """Compile the complete private/public four-cell structural family.

    The paired sealed inputs are compiled through the already-established
    ChangeTarget and ProjectTarget boundaries for both hidden variants.  No
    partial public collection escapes: either all four packets and their
    separately serializable private mapping are returned, or a fixed
    :class:`PacketCompilationError` is raised.
    """
    if not isinstance(pair, AuditorPair):
        raise PacketCompilationError("pair_missing")
    if not isinstance(policy, DisclosurePolicy):
        raise PacketCompilationError("disclosure_policy_invalid")
    try:
        canonical_scope = _canonical_project_scope(scope)
    except InjectionContractError:
        raise PacketCompilationError("project_scope_unbounded") from None
    try:
        bounded_budget = _bounded_discovery_budget(discovery_budget)
    except InjectionContractError:
        raise PacketCompilationError("discovery_budget_unbounded") from None

    change_defect = compile_change_target_packet(
        catalog_path=catalog_path,
        pair=pair,
        variant="defect",
        policy=policy,
    )
    change_control = compile_change_target_packet(
        catalog_path=catalog_path,
        pair=pair,
        variant="control",
        policy=policy,
    )
    project_defect = compile_project_target_packet(
        catalog_path=catalog_path,
        pair=pair,
        variant="defect",
        policy=policy,
        scope=canonical_scope,
        discovery_budget=bounded_budget,
    )
    project_control = compile_project_target_packet(
        catalog_path=catalog_path,
        pair=pair,
        variant="control",
        policy=policy,
        scope=canonical_scope,
        discovery_budget=bounded_budget,
    )
    try:
        public_family = VerifierPacketFamily(
            packets=(
                change_defect,
                change_control,
                project_defect,
                project_control,
            )
        )
        defect_package = pair.defect.admission.package
        control_package = pair.control.admission.package
        if defect_package is None or control_package is None:
            raise InjectionContractError("sealed pair requires audit packages")
        auditor_mapping = AuditorMapping(
            family_id=public_family.family_id,
            entries=(
                AuditorMappingEntry(
                    packet_id=change_defect.packet_id,
                    target_kind=change_defect.target_kind,
                    hidden_variant="defect",
                    audit_package_identity_sha256=defect_package.identity_sha256,
                ),
                AuditorMappingEntry(
                    packet_id=change_control.packet_id,
                    target_kind=change_control.target_kind,
                    hidden_variant="control",
                    audit_package_identity_sha256=control_package.identity_sha256,
                ),
                AuditorMappingEntry(
                    packet_id=project_defect.packet_id,
                    target_kind=project_defect.target_kind,
                    hidden_variant="defect",
                    audit_package_identity_sha256=defect_package.identity_sha256,
                ),
                AuditorMappingEntry(
                    packet_id=project_control.packet_id,
                    target_kind=project_control.target_kind,
                    hidden_variant="control",
                    audit_package_identity_sha256=control_package.identity_sha256,
                ),
            ),
        )
        return AuditorCaseFamily(
            verifier_packet_family=public_family,
            auditor_mapping=auditor_mapping,
            pair=pair,
        )
    except InjectionContractError:
        raise PacketCompilationError("four_cell_family_invalid") from None


__all__ = [
    "AuditorCase",
    "AuditorCaseFamily",
    "AuditorMapping",
    "AuditorMappingEntry",
    "AuditorPair",
    "PacketCompilationError",
    "ProjectTargetPacket",
    "VerifierPacket",
    "VerifierPacketFamily",
    "compile_change_target_packet",
    "compile_four_cell_case_family",
    "compile_project_target_packet",
]
