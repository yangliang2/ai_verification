"""Blind-safe, verifier-facing ChangeTarget packet compilation.

This module is deliberately a packet-contract boundary.  It consumes a sealed
auditor-side pair, rechecks its catalog and Disclosure Policy provenance, and
returns a public packet that contains only the bounded source change needed by
a future Verification Agent.  It neither invokes Discovery Campaign nor
creates a Run Spec or an execution attempt.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

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
    InjectionContractError,
    InjectionReceipt,
    SCHEMA_VERSION,
    canonical_json_bytes,
    sha256_hex,
)


_CHANGE_TARGET_KIND = "change_target"
_CHANGE_TARGET_CLAIM_BOUNDARY = "m0_structural_blind_change_target_packet_only"
_SHA256_CHARS = frozenset("0123456789abcdef")
_VARIANTS = frozenset({"defect", "control"})


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
    def from_dict(cls, data: Mapping[str, Any]) -> "VerifierPacket":
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
    if not isinstance(pair, AuditorPair):
        raise PacketCompilationError("pair_missing")
    if variant not in _VARIANTS:
        raise PacketCompilationError("variant_not_declared")
    if not isinstance(policy, DisclosurePolicy):
        raise PacketCompilationError("disclosure_policy_invalid")
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


__all__ = [
    "AuditorCase",
    "AuditorPair",
    "PacketCompilationError",
    "VerifierPacket",
    "compile_change_target_packet",
]
