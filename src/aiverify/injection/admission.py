"""M0.2 structural admission for catalogued Injection Lab candidates.

Admission deliberately stops at a non-formal structural package.  It binds a
catalogued candidate and materialization receipt, but never treats absent build
or runtime evidence as a pass and never creates a Qualification Case Package.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aiverify.injection.catalog import (
    CuratedCatalogError,
    CuratedSourceEntry,
    load_curated_source_catalog,
)
from aiverify.injection.materialization import (
    InjectionMaterializer,
    InjectionMaterializerError,
)
from aiverify.injection.models import (
    InjectionContractError,
    InjectionReceipt,
    SCHEMA_VERSION,
    canonical_json_bytes,
    sha256_hex,
)


_SEALED_STATES = (
    "draft",
    "materialized",
    "source-identity-verified",
    "policy-accepted",
    "evidence-bound",
    "sealed",
)
_NOT_CLAIMED_EVIDENCE = (
    ("build", "not_claimed"),
    ("installation", "not_claimed"),
    ("runtime", "not_claimed"),
    ("oracle", "not_claimed"),
    ("flakiness", "not_claimed"),
    ("equivalence", "not_claimed"),
)
_SHA256_CHARS = frozenset("0123456789abcdef")


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
class AdmissionLedgerEntry:
    """One hash-chained, ordered structural admission transition."""

    sequence: int
    state: str
    reason: str
    previous_entry_sha256: str | None
    candidate_identity_sha256: str | None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool):
            raise InjectionContractError("ledger entry sequence must be an integer")
        if self.sequence < 1:
            raise InjectionContractError("ledger entry sequence must be positive")
        if self.state not in {*_SEALED_STATES, "rejected"}:
            raise InjectionContractError("ledger entry state is not an M0 transition")
        _required_text(self.reason, "ledger entry reason")
        if self.sequence == 1 and self.previous_entry_sha256 is not None:
            raise InjectionContractError("first ledger entry cannot have a predecessor")
        if self.sequence > 1:
            _sha256(self.previous_entry_sha256, "ledger entry previous_entry_sha256")
        if self.candidate_identity_sha256 is not None:
            _sha256(
                self.candidate_identity_sha256,
                "ledger entry candidate_identity_sha256",
            )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported ledger entry schema_version")

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "sequence": self.sequence,
                "state": self.state,
                "reason": self.reason,
                "previous_entry_sha256": self.previous_entry_sha256,
                "candidate_identity_sha256": self.candidate_identity_sha256,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "sequence": self.sequence,
            "state": self.state,
            "reason": self.reason,
            "previous_entry_sha256": self.previous_entry_sha256,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdmissionLedgerEntry":
        if not isinstance(data, Mapping):
            raise InjectionContractError("ledger entry must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "sequence",
                "state",
                "reason",
                "previous_entry_sha256",
                "candidate_identity_sha256",
                "identity_sha256",
            },
            "ledger entry",
        )
        try:
            value = cls(
                schema_version=data["schema_version"],
                sequence=data["sequence"],
                state=data["state"],
                reason=data["reason"],
                previous_entry_sha256=data["previous_entry_sha256"],
                candidate_identity_sha256=data["candidate_identity_sha256"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("ledger entry identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"ledger entry requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class AdmissionLedger:
    """An immutable, hash-chained history ending in one M0 terminal state."""

    entries: tuple[AdmissionLedgerEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or not self.entries:
            raise InjectionContractError("ledger must contain entries")
        if not all(isinstance(entry, AdmissionLedgerEntry) for entry in self.entries):
            raise InjectionContractError("ledger entries must be AdmissionLedgerEntry")
        for expected_sequence, entry in enumerate(self.entries, start=1):
            if entry.sequence != expected_sequence:
                raise InjectionContractError("ledger entry sequence is not contiguous")
            previous = self.entries[expected_sequence - 2] if expected_sequence > 1 else None
            if entry.previous_entry_sha256 != (
                previous.identity_sha256 if previous is not None else None
            ):
                raise InjectionContractError("ledger hash chain is contradictory")
        states = self.states
        if states[0] != "draft":
            raise InjectionContractError("ledger must begin at draft")
        candidate_identities = {
            entry.candidate_identity_sha256
            for entry in self.entries
            if entry.candidate_identity_sha256 is not None
        }
        if len(candidate_identities) > 1:
            raise InjectionContractError("ledger cannot mix candidate identities")
        if states == _SEALED_STATES:
            return
        if states[-1] != "rejected":
            raise InjectionContractError("ledger must terminate sealed or rejected")
        if states[:-1] != _SEALED_STATES[: len(states) - 1]:
            raise InjectionContractError("rejected ledger has invalid transition order")

    @property
    def states(self) -> tuple[str, ...]:
        return tuple(entry.state for entry in self.entries)

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": SCHEMA_VERSION,
                "entries": [entry.identity_sha256 for entry in self.entries],
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": [entry.to_dict() for entry in self.entries],
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdmissionLedger":
        if not isinstance(data, Mapping):
            raise InjectionContractError("ledger must be an object")
        _reject_unknown(data, {"schema_version", "entries", "identity_sha256"}, "ledger")
        try:
            if (
                not isinstance(data["schema_version"], int)
                or isinstance(data["schema_version"], bool)
                or data["schema_version"] != SCHEMA_VERSION
            ):
                raise InjectionContractError("unsupported ledger schema_version")
            raw_entries = data["entries"]
            if not isinstance(raw_entries, list):
                raise InjectionContractError("ledger entries must be an array")
            value = cls(
                entries=tuple(AdmissionLedgerEntry.from_dict(entry) for entry in raw_entries)
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("ledger identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(f"ledger requires {error.args[0]}") from error


@dataclass(frozen=True)
class InjectedCasePackage:
    """A sealed M0 audit package, never a formal qualification artifact."""

    source_id: str
    catalog_identity_sha256: str
    catalog_source_sha256: str
    catalog_entry_identity_sha256: str
    candidate_identity_sha256: str
    baseline_identity_sha256: str
    patch_identity_sha256: str
    receipt_identity_sha256: str
    population_classification: str
    formal_status: str = "non_formal"
    cohort_membership: str = "not_a_cohort_member"
    claim_boundary: str = "m0_structural_audit_only"
    _not_claimed_evidence: tuple[tuple[str, str], ...] = _NOT_CLAIMED_EVIDENCE
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.source_id, "package source_id")
        for field in (
            "catalog_identity_sha256",
            "catalog_source_sha256",
            "catalog_entry_identity_sha256",
            "candidate_identity_sha256",
            "baseline_identity_sha256",
            "patch_identity_sha256",
            "receipt_identity_sha256",
        ):
            _sha256(getattr(self, field), f"package {field}")
        if self.population_classification != "curated_controlled_injection":
            raise InjectionContractError("package population is not a curated controlled injection")
        if self.formal_status != "non_formal":
            raise InjectionContractError("M0 package must be non_formal")
        if self.cohort_membership != "not_a_cohort_member":
            raise InjectionContractError("M0 package cannot be a Qualification Cohort member")
        if self.claim_boundary != "m0_structural_audit_only":
            raise InjectionContractError("M0 package claim boundary must be structural audit only")
        if self._not_claimed_evidence != _NOT_CLAIMED_EVIDENCE:
            raise InjectionContractError("M0 package evidence claims must be explicitly not_claimed")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported package schema_version")

    @property
    def not_claimed_evidence(self) -> dict[str, str]:
        return dict(self._not_claimed_evidence)

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "source_id": self.source_id,
                "catalog_identity_sha256": self.catalog_identity_sha256,
                "catalog_source_sha256": self.catalog_source_sha256,
                "catalog_entry_identity_sha256": self.catalog_entry_identity_sha256,
                "candidate_identity_sha256": self.candidate_identity_sha256,
                "baseline_identity_sha256": self.baseline_identity_sha256,
                "patch_identity_sha256": self.patch_identity_sha256,
                "receipt_identity_sha256": self.receipt_identity_sha256,
                "population_classification": self.population_classification,
                "formal_status": self.formal_status,
                "cohort_membership": self.cohort_membership,
                "claim_boundary": self.claim_boundary,
                "not_claimed_evidence": dict(self._not_claimed_evidence),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "catalog_identity_sha256": self.catalog_identity_sha256,
            "catalog_source_sha256": self.catalog_source_sha256,
            "catalog_entry_identity_sha256": self.catalog_entry_identity_sha256,
            "candidate_identity_sha256": self.candidate_identity_sha256,
            "baseline_identity_sha256": self.baseline_identity_sha256,
            "patch_identity_sha256": self.patch_identity_sha256,
            "receipt_identity_sha256": self.receipt_identity_sha256,
            "population_classification": self.population_classification,
            "formal_status": self.formal_status,
            "cohort_membership": self.cohort_membership,
            "claim_boundary": self.claim_boundary,
            "not_claimed_evidence": self.not_claimed_evidence,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InjectedCasePackage":
        if not isinstance(data, Mapping):
            raise InjectionContractError("package must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "source_id",
                "catalog_identity_sha256",
                "catalog_source_sha256",
                "catalog_entry_identity_sha256",
                "candidate_identity_sha256",
                "baseline_identity_sha256",
                "patch_identity_sha256",
                "receipt_identity_sha256",
                "population_classification",
                "formal_status",
                "cohort_membership",
                "claim_boundary",
                "not_claimed_evidence",
                "identity_sha256",
            },
            "package",
        )
        try:
            raw_evidence = data["not_claimed_evidence"]
            if not isinstance(raw_evidence, Mapping):
                raise InjectionContractError("package not_claimed_evidence must be an object")
            value = cls(
                schema_version=data["schema_version"],
                source_id=data["source_id"],
                catalog_identity_sha256=data["catalog_identity_sha256"],
                catalog_source_sha256=data["catalog_source_sha256"],
                catalog_entry_identity_sha256=data["catalog_entry_identity_sha256"],
                candidate_identity_sha256=data["candidate_identity_sha256"],
                baseline_identity_sha256=data["baseline_identity_sha256"],
                patch_identity_sha256=data["patch_identity_sha256"],
                receipt_identity_sha256=data["receipt_identity_sha256"],
                population_classification=data["population_classification"],
                formal_status=data["formal_status"],
                cohort_membership=data["cohort_membership"],
                claim_boundary=data["claim_boundary"],
                _not_claimed_evidence=tuple(
                    (dimension, raw_evidence.get(dimension))
                    for dimension, _ in _NOT_CLAIMED_EVIDENCE
                ),
            )
            if set(raw_evidence) != {dimension for dimension, _ in _NOT_CLAIMED_EVIDENCE}:
                raise InjectionContractError("package not_claimed_evidence dimensions are incomplete")
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("package identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(f"package requires {error.args[0]}") from error


@dataclass(frozen=True)
class InjectionAdmission:
    """The terminal sealed or rejected result of one catalog selection."""

    status: str
    ledger: AdmissionLedger
    receipt: InjectionReceipt | None
    package: InjectedCasePackage | None = None
    rejection_code: str | None = None
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported admission schema_version")
        if not isinstance(self.ledger, AdmissionLedger):
            raise InjectionContractError("admission ledger must be AdmissionLedger")
        if self.receipt is not None and not isinstance(self.receipt, InjectionReceipt):
            raise InjectionContractError("admission receipt must be InjectionReceipt")
        if self.status == "sealed":
            if self.ledger.states != _SEALED_STATES:
                raise InjectionContractError("sealed admission requires the complete M0 ledger")
            if self.receipt is None or self.receipt.outcome != "materialized":
                raise InjectionContractError("sealed admission requires a materialized receipt")
            if not isinstance(self.package, InjectedCasePackage):
                raise InjectionContractError("sealed admission requires an InjectedCasePackage")
            if self.rejection_code is not None:
                raise InjectionContractError("sealed admission cannot have a rejection code")
            if self.package.receipt_identity_sha256 != self.receipt.receipt_identity_sha256:
                raise InjectionContractError("package receipt identity contradicts admission receipt")
            if (
                self.package.candidate_identity_sha256
                != self.receipt.candidate_identity_sha256
                or self.package.baseline_identity_sha256
                != self.receipt.baseline_identity_sha256
                or self.package.patch_identity_sha256 != self.receipt.patch_identity_sha256
            ):
                raise InjectionContractError("package source identities contradict admission receipt")
            ledger_candidate_identities = {
                entry.candidate_identity_sha256
                for entry in self.ledger.entries
                if entry.candidate_identity_sha256 is not None
            }
            if ledger_candidate_identities != {self.package.candidate_identity_sha256}:
                raise InjectionContractError("ledger candidate identity contradicts package")
            return
        if self.status != "rejected":
            raise InjectionContractError("admission status must be sealed or rejected")
        if self.ledger.states[-1] != "rejected":
            raise InjectionContractError("rejected admission requires a rejected ledger")
        if self.package is not None:
            raise InjectionContractError("rejected admission cannot contain a package")
        _required_text(self.rejection_code, "rejected admission rejection_code")

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "status": self.status,
                "ledger_identity_sha256": self.ledger.identity_sha256,
                "receipt_identity_sha256": (
                    self.receipt.receipt_identity_sha256 if self.receipt is not None else None
                ),
                "package_identity_sha256": (
                    self.package.identity_sha256 if self.package is not None else None
                ),
                "rejection_code": self.rejection_code,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "ledger": self.ledger.to_dict(),
            "receipt": self.receipt.to_dict() if self.receipt is not None else None,
            "package": self.package.to_dict() if self.package is not None else None,
            "rejection_code": self.rejection_code,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "InjectionAdmission":
        if not isinstance(data, Mapping):
            raise InjectionContractError("admission must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "status",
                "ledger",
                "receipt",
                "package",
                "rejection_code",
                "identity_sha256",
            },
            "admission",
        )
        try:
            raw_receipt = data["receipt"]
            raw_package = data["package"]
            value = cls(
                schema_version=data["schema_version"],
                status=data["status"],
                ledger=AdmissionLedger.from_dict(data["ledger"]),
                receipt=(
                    InjectionReceipt.from_dict(raw_receipt)
                    if raw_receipt is not None
                    else None
                ),
                package=(
                    InjectedCasePackage.from_dict(raw_package)
                    if raw_package is not None
                    else None
                ),
                rejection_code=data["rejection_code"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError("admission identity digest does not match")
            return value
        except KeyError as error:
            raise InjectionContractError(f"admission requires {error.args[0]}") from error


def _ledger(
    states: tuple[str, ...],
    *,
    candidate_identity_sha256: str | None,
    reasons: tuple[str, ...],
) -> AdmissionLedger:
    if len(states) != len(reasons):
        raise RuntimeError("admission ledger states and reasons must align")
    entries: list[AdmissionLedgerEntry] = []
    for sequence, (state, reason) in enumerate(zip(states, reasons), start=1):
        previous = entries[-1].identity_sha256 if entries else None
        entries.append(
            AdmissionLedgerEntry(
                sequence=sequence,
                state=state,
                reason=reason,
                previous_entry_sha256=previous,
                candidate_identity_sha256=candidate_identity_sha256,
            )
        )
    return AdmissionLedger(entries=tuple(entries))


def _rejected_admission(
    rejection_code: str,
    *,
    receipt: InjectionReceipt | None = None,
    candidate_identity_sha256: str | None = None,
    states_before_rejection: tuple[str, ...] = ("draft",),
) -> InjectionAdmission:
    states = (*states_before_rejection, "rejected")
    reasons = (
        "M0 admission draft created",
        *("structural prerequisite observed" for _ in states_before_rejection[1:]),
        rejection_code,
    )
    return InjectionAdmission(
        status="rejected",
        ledger=_ledger(
            states,
            candidate_identity_sha256=candidate_identity_sha256,
            reasons=reasons,
        ),
        receipt=receipt,
        rejection_code=rejection_code,
    )


def _receipt_binds_candidate(receipt: InjectionReceipt, entry: CuratedSourceEntry) -> bool:
    candidate = entry.candidate
    return (
        receipt.candidate_identity_sha256 == candidate.identity_sha256
        and receipt.baseline_identity_sha256 == candidate.baseline.identity_sha256
        and receipt.patch_identity_sha256 == candidate.source_delta.identity_sha256
    )


def admit_catalogued_candidate(
    catalog_path: str | Path,
    source_id: str,
    materializer: InjectionMaterializer,
) -> InjectionAdmission:
    """Reload, materialize, and structurally admit one declared source."""
    if not isinstance(catalog_path, (str, Path)):
        return _rejected_admission("catalog_not_verified")
    try:
        catalog = load_curated_source_catalog(catalog_path)
    except CuratedCatalogError as error:
        return _rejected_admission(error.code)
    try:
        entry = catalog.select(source_id)
    except InjectionContractError:
        return _rejected_admission("catalog_source_missing")

    candidate_identity = entry.candidate.identity_sha256
    try:
        receipt = materializer.materialize(entry.candidate)
    except (InjectionMaterializerError, OSError):
        return _rejected_admission(
            "materialization_unavailable",
            candidate_identity_sha256=candidate_identity,
        )
    if not isinstance(receipt, InjectionReceipt):
        return _rejected_admission(
            "receipt_invalid",
            candidate_identity_sha256=candidate_identity,
        )
    if not _receipt_binds_candidate(receipt, entry):
        return _rejected_admission(
            "receipt_identity_mismatch",
            receipt=receipt,
            candidate_identity_sha256=candidate_identity,
            states_before_rejection=(
                ("draft", "materialized")
                if receipt.outcome == "materialized"
                else ("draft",)
            ),
        )
    if receipt.outcome != "materialized":
        return _rejected_admission(
            "materialization_rejected",
            receipt=receipt,
            candidate_identity_sha256=candidate_identity,
        )

    package = InjectedCasePackage(
        source_id=entry.source_id,
        catalog_identity_sha256=catalog.identity_sha256,
        catalog_source_sha256=catalog.catalog_source_sha256,
        catalog_entry_identity_sha256=entry.identity_sha256,
        candidate_identity_sha256=candidate_identity,
        baseline_identity_sha256=entry.candidate.baseline.identity_sha256,
        patch_identity_sha256=entry.candidate.source_delta.identity_sha256,
        receipt_identity_sha256=receipt.receipt_identity_sha256,
        population_classification=entry.population_classification,
    )
    return InjectionAdmission(
        status="sealed",
        ledger=_ledger(
            _SEALED_STATES,
            candidate_identity_sha256=candidate_identity,
            reasons=(
                "M0 admission draft created",
                "catalogued candidate materialized",
                "materialized receipt binds declared source identities",
                "curated structural admission policy accepted",
                "required M0 evidence claims explicitly bound",
                "non-formal Injected Case Package sealed",
            ),
        ),
        receipt=receipt,
        package=package,
    )


__all__ = [
    "AdmissionLedger",
    "AdmissionLedgerEntry",
    "InjectedCasePackage",
    "InjectionAdmission",
    "admit_catalogued_candidate",
]
