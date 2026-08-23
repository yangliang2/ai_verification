"""Audit-side declared-token checks for future verifier-visible packets.

M0.3 deliberately models only a bounded structural disclosure defense.  It
does not claim to detect every semantic leak; it rejects material containing a
token that an auditor explicitly declared forbidden before the material can be
used as verifier-facing input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from aiverify.injection.admission import InjectionAdmission
from aiverify.injection.catalog import (
    CheckedInCuratedSourceCatalog,
    CuratedSourceEntry,
    load_curated_source_catalog,
)
from aiverify.injection.models import (
    InjectionContractError,
    SCHEMA_VERSION,
    canonical_json_bytes,
    sha256_hex,
)


_CLAIM_BOUNDARY = "m0_structural_blind_packet_eligibility_only"
_REJECTION_CODE = "declared_disclosure_detected"
_SHA256_CHARS = frozenset("0123456789abcdef")


def _require_nonempty_text(value: object, field: str) -> str:
    """Validate text without silently changing identity-bearing values."""
    if not isinstance(value, str) or not value.strip():
        raise InjectionContractError(f"{field} must be a non-empty string")
    return value


def _sha256(value: object, field: str) -> str:
    text = _require_nonempty_text(value, field)
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


def _normalized_token(value: str) -> str:
    """Normalize only declared token spelling variation, never source meaning."""
    normalized = "".join(character for character in value.casefold() if character.isalnum())
    if not normalized:
        raise InjectionContractError("disclosure token must contain an alphanumeric character")
    return normalized


def _json_pointer_segment(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True)
class DisclosurePolicy:
    """Audit-side declaration of text that may not cross a packet boundary."""

    policy_id: str
    forbidden_tokens: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_text(self.policy_id, "disclosure policy policy_id")
        if not isinstance(self.forbidden_tokens, tuple) or not self.forbidden_tokens:
            raise InjectionContractError(
                "disclosure policy forbidden_tokens must be a non-empty tuple"
            )
        normalized: dict[str, str] = {}
        for token in self.forbidden_tokens:
            text = _require_nonempty_text(
                token, "disclosure policy forbidden token"
            ).strip()
            normalized_token = _normalized_token(text)
            if normalized_token in normalized:
                raise InjectionContractError(
                    "disclosure policy contains duplicate normalized forbidden token"
                )
            normalized[normalized_token] = text
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported disclosure policy schema_version")
        object.__setattr__(
            self,
            "forbidden_tokens",
            tuple(normalized[key] for key in sorted(normalized)),
        )

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "policy_id": self.policy_id,
                "forbidden_tokens": list(self.forbidden_tokens),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "forbidden_tokens": list(self.forbidden_tokens),
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DisclosurePolicy":
        if not isinstance(data, Mapping):
            raise InjectionContractError("disclosure policy must be an object")
        _reject_unknown(
            data,
            {"schema_version", "policy_id", "forbidden_tokens", "identity_sha256"},
            "disclosure policy",
        )
        try:
            raw_tokens = data["forbidden_tokens"]
            if not isinstance(raw_tokens, list):
                raise InjectionContractError(
                    "disclosure policy forbidden_tokens must be an array"
                )
            value = cls(
                policy_id=data["policy_id"],
                forbidden_tokens=tuple(raw_tokens),
                schema_version=data["schema_version"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "disclosure policy identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"disclosure policy requires {error.args[0]}"
            ) from error


# The required M0.3 negative fixture keeps this policy auditor-side.  Its
# declared tokens must never be added to verifier-facing packet material.
STALE_RESULT_DISCLOSURE_POLICY = DisclosurePolicy(
    policy_id="curated-deterministic-concurrency-stale-result-v1",
    forbidden_tokens=("APPLY_STALE", "injected_defect", "expected_oracle"),
)


@dataclass(frozen=True)
class DisclosureFinding:
    """An audit-side record of one declared token in visible material."""

    forbidden_token: str
    visible_path: str
    value_sha256: str
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_text(
            self.forbidden_token, "disclosure finding forbidden_token"
        )
        _require_nonempty_text(self.visible_path, "disclosure finding visible_path")
        _sha256(self.value_sha256, "disclosure finding value_sha256")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported disclosure finding schema_version")

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "forbidden_token": self.forbidden_token,
                "visible_path": self.visible_path,
                "value_sha256": self.value_sha256,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "forbidden_token": self.forbidden_token,
            "visible_path": self.visible_path,
            "value_sha256": self.value_sha256,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DisclosureFinding":
        if not isinstance(data, Mapping):
            raise InjectionContractError("disclosure finding must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "forbidden_token",
                "visible_path",
                "value_sha256",
                "identity_sha256",
            },
            "disclosure finding",
        )
        try:
            value = cls(
                forbidden_token=data["forbidden_token"],
                visible_path=data["visible_path"],
                value_sha256=data["value_sha256"],
                schema_version=data["schema_version"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "disclosure finding identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"disclosure finding requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class DisclosureReview:
    """The terminal audit-side eligibility result for one visible material tree."""

    status: str
    policy_identity_sha256: str
    visible_material_identity_sha256: str
    findings: tuple[DisclosureFinding, ...]
    rejection_code: str | None = None
    claim_boundary: str = _CLAIM_BOUNDARY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _sha256(self.policy_identity_sha256, "disclosure review policy_identity_sha256")
        _sha256(
            self.visible_material_identity_sha256,
            "disclosure review visible_material_identity_sha256",
        )
        if not isinstance(self.findings, tuple) or not all(
            isinstance(finding, DisclosureFinding) for finding in self.findings
        ):
            raise InjectionContractError(
                "disclosure review findings must be DisclosureFinding values"
            )
        expected_findings = tuple(
            sorted(
                self.findings,
                key=lambda finding: (
                    _normalized_token(finding.forbidden_token),
                    finding.visible_path,
                    finding.value_sha256,
                ),
            )
        )
        if self.findings != expected_findings:
            raise InjectionContractError("disclosure review findings must be canonical")
        if self.status == "eligible":
            if self.findings or self.rejection_code is not None:
                raise InjectionContractError(
                    "eligible disclosure review cannot contain rejection evidence"
                )
        elif self.status == "rejected":
            if not self.findings or self.rejection_code != _REJECTION_CODE:
                raise InjectionContractError(
                    "rejected disclosure review requires declared disclosure evidence"
                )
        else:
            raise InjectionContractError("disclosure review status must be eligible or rejected")
        if self.claim_boundary != _CLAIM_BOUNDARY:
            raise InjectionContractError("disclosure review claim boundary is not M0 structural")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError("unsupported disclosure review schema_version")

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "status": self.status,
                "policy_identity_sha256": self.policy_identity_sha256,
                "visible_material_identity_sha256": self.visible_material_identity_sha256,
                "finding_identities": [
                    finding.identity_sha256 for finding in self.findings
                ],
                "rejection_code": self.rejection_code,
                "claim_boundary": self.claim_boundary,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "policy_identity_sha256": self.policy_identity_sha256,
            "visible_material_identity_sha256": self.visible_material_identity_sha256,
            "findings": [finding.to_dict() for finding in self.findings],
            "rejection_code": self.rejection_code,
            "claim_boundary": self.claim_boundary,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DisclosureReview":
        if not isinstance(data, Mapping):
            raise InjectionContractError("disclosure review must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "status",
                "policy_identity_sha256",
                "visible_material_identity_sha256",
                "findings",
                "rejection_code",
                "claim_boundary",
                "identity_sha256",
            },
            "disclosure review",
        )
        try:
            raw_findings = data["findings"]
            if not isinstance(raw_findings, list):
                raise InjectionContractError("disclosure review findings must be an array")
            value = cls(
                schema_version=data["schema_version"],
                status=data["status"],
                policy_identity_sha256=data["policy_identity_sha256"],
                visible_material_identity_sha256=data[
                    "visible_material_identity_sha256"
                ],
                findings=tuple(
                    DisclosureFinding.from_dict(finding) for finding in raw_findings
                ),
                rejection_code=data["rejection_code"],
                claim_boundary=data["claim_boundary"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "disclosure review identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"disclosure review requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class CataloguedDisclosureReview:
    """A disclosure review bound to one sealed audit package and catalog entry.

    The record remains auditor-side.  A rejected result retains the sealed M0
    audit package and its materialization receipt; it only prevents that source
    from becoming verifier-facing packet material.
    """

    source_id: str
    catalog_identity_sha256: str
    catalog_source_sha256: str
    catalog_entry_identity_sha256: str
    admission_identity_sha256: str
    audit_package_identity_sha256: str
    review: DisclosureReview
    claim_boundary: str = _CLAIM_BOUNDARY
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_nonempty_text(
            self.source_id, "catalogued disclosure review source_id"
        )
        for field in (
            "catalog_identity_sha256",
            "catalog_source_sha256",
            "catalog_entry_identity_sha256",
            "admission_identity_sha256",
            "audit_package_identity_sha256",
        ):
            _sha256(getattr(self, field), f"catalogued disclosure review {field}")
        if not isinstance(self.review, DisclosureReview):
            raise InjectionContractError(
                "catalogued disclosure review requires DisclosureReview"
            )
        if self.claim_boundary != _CLAIM_BOUNDARY:
            raise InjectionContractError(
                "catalogued disclosure review claim boundary is not M0 structural"
            )
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != SCHEMA_VERSION
        ):
            raise InjectionContractError(
                "unsupported catalogued disclosure review schema_version"
            )

    @property
    def status(self) -> str:
        return self.review.status

    @property
    def rejection_code(self) -> str | None:
        return self.review.rejection_code

    @property
    def findings(self) -> tuple[DisclosureFinding, ...]:
        return self.review.findings

    @property
    def identity_sha256(self) -> str:
        return _identity(
            {
                "schema_version": self.schema_version,
                "source_id": self.source_id,
                "catalog_identity_sha256": self.catalog_identity_sha256,
                "catalog_source_sha256": self.catalog_source_sha256,
                "catalog_entry_identity_sha256": self.catalog_entry_identity_sha256,
                "admission_identity_sha256": self.admission_identity_sha256,
                "audit_package_identity_sha256": self.audit_package_identity_sha256,
                "review_identity_sha256": self.review.identity_sha256,
                "claim_boundary": self.claim_boundary,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_id": self.source_id,
            "catalog_identity_sha256": self.catalog_identity_sha256,
            "catalog_source_sha256": self.catalog_source_sha256,
            "catalog_entry_identity_sha256": self.catalog_entry_identity_sha256,
            "admission_identity_sha256": self.admission_identity_sha256,
            "audit_package_identity_sha256": self.audit_package_identity_sha256,
            "review": self.review.to_dict(),
            "claim_boundary": self.claim_boundary,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CataloguedDisclosureReview":
        if not isinstance(data, Mapping):
            raise InjectionContractError("catalogued disclosure review must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "source_id",
                "catalog_identity_sha256",
                "catalog_source_sha256",
                "catalog_entry_identity_sha256",
                "admission_identity_sha256",
                "audit_package_identity_sha256",
                "review",
                "claim_boundary",
                "identity_sha256",
            },
            "catalogued disclosure review",
        )
        try:
            value = cls(
                schema_version=data["schema_version"],
                source_id=data["source_id"],
                catalog_identity_sha256=data["catalog_identity_sha256"],
                catalog_source_sha256=data["catalog_source_sha256"],
                catalog_entry_identity_sha256=data[
                    "catalog_entry_identity_sha256"
                ],
                admission_identity_sha256=data["admission_identity_sha256"],
                audit_package_identity_sha256=data[
                    "audit_package_identity_sha256"
                ],
                review=DisclosureReview.from_dict(data["review"]),
                claim_boundary=data["claim_boundary"],
            )
            if data["identity_sha256"] != value.identity_sha256:
                raise InjectionContractError(
                    "catalogued disclosure review identity digest does not match"
                )
            return value
        except KeyError as error:
            raise InjectionContractError(
                f"catalogued disclosure review requires {error.args[0]}"
            ) from error


def _visible_strings(value: object, path: str = "") -> tuple[tuple[str, str], ...]:
    """Return all JSON string values and field names at deterministic locations."""
    if isinstance(value, str):
        return ((path or "/", value),)
    if value is None or isinstance(value, (bool, int, float)):
        return ()
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InjectionContractError("visible material object keys must be strings")
        strings: list[tuple[str, str]] = []
        for key in sorted(value):
            escaped = _json_pointer_segment(key)
            strings.append((f"{path}/$key/{escaped}" or "/$key", key))
            strings.extend(_visible_strings(value[key], f"{path}/{escaped}"))
        return tuple(strings)
    if isinstance(value, (list, tuple)):
        strings = []
        for index, item in enumerate(value):
            strings.extend(_visible_strings(item, f"{path}/{index}"))
        return tuple(strings)
    raise InjectionContractError("visible material must contain JSON-compatible values")


def review_visible_packet_material(
    policy: DisclosurePolicy,
    visible_material: Mapping[str, Any],
) -> DisclosureReview:
    """Return a deterministic, audit-side eligibility review of visible material.

    Matching is case-insensitive and separator-insensitive for the declared
    token only.  This catches a declared marker in source, a path, or an ID
    derived by replacing underscores with separators, without asserting that
    the policy detects semantic equivalence.
    """
    if not isinstance(policy, DisclosurePolicy):
        raise InjectionContractError("disclosure review requires DisclosurePolicy")
    if not isinstance(visible_material, Mapping):
        raise InjectionContractError("visible material must be an object")
    material_identity = sha256_hex(canonical_json_bytes(visible_material))
    normalized_tokens = tuple(
        (token, _normalized_token(token)) for token in policy.forbidden_tokens
    )
    findings: list[DisclosureFinding] = []
    for visible_path, text in _visible_strings(visible_material):
        normalized_text = _normalized_token(text) if text else ""
        for token, normalized_token in normalized_tokens:
            if normalized_token in normalized_text:
                findings.append(
                    DisclosureFinding(
                        forbidden_token=token,
                        visible_path=visible_path,
                        value_sha256=sha256_hex(text),
                    )
                )
    canonical_findings = tuple(
        sorted(
            findings,
            key=lambda finding: (
                _normalized_token(finding.forbidden_token),
                finding.visible_path,
                finding.value_sha256,
            ),
        )
    )
    return DisclosureReview(
        status="rejected" if canonical_findings else "eligible",
        policy_identity_sha256=policy.identity_sha256,
        visible_material_identity_sha256=material_identity,
        findings=canonical_findings,
        rejection_code=_REJECTION_CODE if canonical_findings else None,
    )


def _catalogued_review_material(
    catalog_path: str | Path,
    entry: CuratedSourceEntry,
) -> dict[str, Any]:
    """Build the declared, finite audit material that a packet could expose."""
    try:
        root = Path(catalog_path).resolve().parent
    except (OSError, ValueError) as error:
        raise InjectionContractError("catalogued disclosure material is unavailable") from error
    audit_artifacts: list[dict[str, str]] = []
    for artifact in entry.disclosure_audit_artifacts:
        path = root.joinpath(*PurePosixPath(artifact.path).parts)
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise InjectionContractError(
                "catalogued disclosure artifact is unavailable"
            ) from error
        if sha256_hex(raw) != artifact.sha256:
            raise InjectionContractError("catalogued disclosure artifact bytes drifted")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise InjectionContractError(
                "catalogued disclosure artifact must be UTF-8 text"
            ) from error
        audit_artifacts.append(
            {"path": artifact.path, "sha256": artifact.sha256, "text": text}
        )
    candidate = entry.candidate
    return {
        "source": {"patch_text": candidate.source_delta.patch_text},
        "metadata": {
            "source_id": entry.source_id,
            "candidate_id": candidate.candidate_id,
            "delta_id": candidate.source_delta.delta_id,
            "format": candidate.source_delta.format,
        },
        "paths": {
            "patch_path": entry.patch_path,
            "source_ref": candidate.source_delta.source_ref,
            "fixture_anchor_path": entry.fixture_anchor.path,
        },
        "derived_identifiers": {
            "source_id": f"source:{entry.source_id}",
            "candidate_id": f"candidate:{candidate.candidate_id}",
            "delta_id": f"delta:{candidate.source_delta.delta_id}",
        },
        "audit_artifacts": audit_artifacts,
    }


def _require_sealed_catalogued_admission(
    catalog: CheckedInCuratedSourceCatalog,
    entry: CuratedSourceEntry,
    admission: InjectionAdmission,
) -> None:
    if not isinstance(admission, InjectionAdmission):
        raise InjectionContractError(
            "catalogued disclosure review requires InjectionAdmission"
        )
    if admission.status != "sealed" or admission.package is None or admission.receipt is None:
        raise InjectionContractError(
            "catalogued disclosure review requires a sealed M0 audit package"
        )
    package = admission.package
    candidate = entry.candidate
    expected = (
        package.source_id == entry.source_id,
        package.catalog_identity_sha256 == catalog.identity_sha256,
        package.catalog_source_sha256 == catalog.catalog_source_sha256,
        package.catalog_entry_identity_sha256 == entry.identity_sha256,
        package.candidate_identity_sha256 == candidate.identity_sha256,
        package.baseline_identity_sha256 == candidate.baseline.identity_sha256,
        package.patch_identity_sha256 == candidate.source_delta.identity_sha256,
        package.receipt_identity_sha256 == admission.receipt.receipt_identity_sha256,
    )
    if not all(expected):
        raise InjectionContractError(
            "catalogued disclosure review admission provenance mismatch"
        )


def review_catalogued_admission(
    catalog_path: str | Path,
    source_id: str,
    admission: InjectionAdmission,
    policy: DisclosurePolicy,
) -> CataloguedDisclosureReview:
    """Review one sealed catalogued audit package for blind-packet eligibility.

    The catalog is reloaded through its checked-in-byte gate.  This binds the
    policy result to the same catalog/entry/receipt chain that produced the M0
    audit package, while retaining that package after rejection.
    """
    if not isinstance(policy, DisclosurePolicy):
        raise InjectionContractError("catalogued disclosure review requires DisclosurePolicy")
    catalog = load_curated_source_catalog(catalog_path)
    try:
        entry = catalog.select(source_id)
    except InjectionContractError as error:
        raise InjectionContractError(
            "catalogued disclosure review source_id is not declared"
        ) from error
    _require_sealed_catalogued_admission(catalog, entry, admission)
    review = review_visible_packet_material(
        policy,
        _catalogued_review_material(catalog_path, entry),
    )
    return CataloguedDisclosureReview(
        source_id=entry.source_id,
        catalog_identity_sha256=catalog.identity_sha256,
        catalog_source_sha256=catalog.catalog_source_sha256,
        catalog_entry_identity_sha256=entry.identity_sha256,
        admission_identity_sha256=admission.identity_sha256,
        audit_package_identity_sha256=admission.package.identity_sha256,
        review=review,
    )


__all__ = [
    "DisclosureFinding",
    "CataloguedDisclosureReview",
    "DisclosurePolicy",
    "DisclosureReview",
    "STALE_RESULT_DISCLOSURE_POLICY",
    "review_visible_packet_material",
    "review_catalogued_admission",
]
