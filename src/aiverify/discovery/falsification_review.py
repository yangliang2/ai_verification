"""Independent, clean-context Falsification Review contracts for M9.

This module is intentionally a discovery-layer implementation.  It accepts
immutable references and a candidate Finding, invokes a separately identified
challenge role, and never imports or delegates to the production adjudication
path.  A review can block aggregation, but it cannot rewrite the Finding or
any raw evidence reference.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from aiverify.discovery.contracts import AttackPlan, Finding, RiskHypothesis
from aiverify.discovery.models import DiscoveryContractError, ProjectTarget


FALSIFICATION_REVIEW_ROLE_ID = "verification-agent-falsification-reviewer-v1"
FALSIFICATION_REVIEW_SCHEMA_VERSION = 1
REVIEW_DIMENSIONS = (
    "alternative_explanations",
    "assumption_violations",
    "evidence_integrity",
    "causal_attribution",
    "control_comparison",
    "claim_boundary",
)
_DIMENSION_STATUSES = frozenset({"supported", "challenged", "inconclusive"})
_OUTCOMES = frozenset({"survived", "challenged", "inconclusive"})
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")
_FORBIDDEN_CONTEXT_TERMS = frozenset(
    {"hidden", "mapping", "holdout", "cohort", "transcript", "ground truth", "mutable"}
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _version(value: object, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value != 1:
        raise DiscoveryContractError(f"unsupported {field} schema_version")


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DiscoveryContractError("falsification value is not canonical JSON") from error
    return hashlib.sha256(encoded).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_DIGEST_RE.fullmatch(value))


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    return value


def _list(data: Mapping[str, Any], field: str, label: str) -> tuple[Any, ...]:
    value = data[field]
    if not isinstance(value, list):
        raise DiscoveryContractError(f"{label} {field} must be an array")
    return tuple(value)


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(f"unknown {label} field(s): " + ", ".join(unknown))


def _free_text(value: object) -> tuple[str, ...]:
    """Extract prose values without treating contract field names as evidence."""

    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        result: list[str] = []
        for item in value.values():
            result.extend(_free_text(item))
        return tuple(result)
    if isinstance(value, (list, tuple, set, frozenset)):
        result = []
        for item in value:
            result.extend(_free_text(item))
        return tuple(result)
    return ()


def _forbidden_terms(value: object) -> tuple[str, ...]:
    found = set()
    for text in _free_text(value):
        lowered = text.lower()
        for term in _FORBIDDEN_CONTEXT_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                found.add(term)
    return tuple(sorted(found))


@dataclass(frozen=True)
class ImmutableArtifactRef:
    """A checksum-bound artifact reference; contents are not mutable review input."""

    ref: str
    kind: str
    sha256: str
    immutable: bool = True
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.ref, "artifact ref")
        _required_text(self.kind, "artifact kind")
        if not _is_digest(self.sha256):
            raise DiscoveryContractError("artifact ref sha256 must be a lowercase SHA-256 digest")
        if self.immutable is not True:
            raise DiscoveryContractError("falsification review accepts immutable artifacts only")
        _version(self.schema_version, "immutable artifact ref")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ref": self.ref,
            "kind": self.kind,
            "sha256": self.sha256,
            "immutable": self.immutable,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ImmutableArtifactRef":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("immutable artifact ref must be an object")
        _reject_unknown(data, {"schema_version", "ref", "kind", "sha256", "immutable"}, "immutable artifact ref")
        try:
            return cls(
                ref=data["ref"],
                kind=data["kind"],
                sha256=data["sha256"],
                immutable=data.get("immutable", True),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"immutable artifact ref requires {error.args[0]}") from error


@dataclass(frozen=True)
class FalsificationReviewContext:
    """Allowlisted clean context visible to the independent review role."""

    context_id: str
    target: ProjectTarget
    source_refs: tuple[ImmutableArtifactRef, ...]
    validated_fact_ids: tuple[str, ...]
    hypothesis: RiskHypothesis
    admitted_attack_plan: AttackPlan
    oracle_contract: ImmutableArtifactRef
    candidate_finding: Finding
    execution_record: ImmutableArtifactRef
    effective_identity: ImmutableArtifactRef
    raw_evidence: tuple[ImmutableArtifactRef, ...]
    control_evidence: tuple[ImmutableArtifactRef, ...]
    claim_boundary: str
    production_invocation_id: str
    production_provider_family: str
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.context_id, "review context_id")
        if not isinstance(self.target, ProjectTarget):
            raise DiscoveryContractError("review context requires ProjectTarget")
        if not isinstance(self.hypothesis, RiskHypothesis):
            raise DiscoveryContractError("review context hypothesis is invalid")
        if not isinstance(self.admitted_attack_plan, AttackPlan):
            raise DiscoveryContractError("review context attack plan is invalid")
        if self.admitted_attack_plan.status != "admitted":
            raise DiscoveryContractError("review context requires an admitted attack plan")
        if not isinstance(self.candidate_finding, Finding):
            raise DiscoveryContractError("review context candidate Finding is invalid")
        if self.hypothesis.target_id != self.target.target_id:
            raise DiscoveryContractError("review hypothesis target does not match target")
        if self.admitted_attack_plan.target_id != self.target.target_id:
            raise DiscoveryContractError("review attack plan target does not match target")
        if self.candidate_finding.target_id != self.target.target_id:
            raise DiscoveryContractError("review Finding target does not match target")
        if self.candidate_finding.hypothesis_id != self.hypothesis.hypothesis_id:
            raise DiscoveryContractError("review Finding hypothesis does not match hypothesis")
        _text_tuple(self.validated_fact_ids, "validated fact ids", allow_empty=False)
        for field in (
            "source_refs",
            "raw_evidence",
            "control_evidence",
        ):
            values = getattr(self, field)
            if not isinstance(values, tuple) or any(not isinstance(item, ImmutableArtifactRef) for item in values):
                raise DiscoveryContractError(f"review {field} contains invalid artifact refs")
        if not self.source_refs:
            raise DiscoveryContractError("review requires source refs")
        if not self.raw_evidence:
            raise DiscoveryContractError("review requires immutable raw evidence refs")
        if not self.control_evidence:
            raise DiscoveryContractError("review requires relevant control evidence refs")
        if not isinstance(self.oracle_contract, ImmutableArtifactRef):
            raise DiscoveryContractError("review oracle contract ref is invalid")
        if not isinstance(self.execution_record, ImmutableArtifactRef):
            raise DiscoveryContractError("review ExecutionRecord ref is invalid")
        if not isinstance(self.effective_identity, ImmutableArtifactRef):
            raise DiscoveryContractError("review Effective Identity ref is invalid")
        all_artifacts = (
            *self.source_refs,
            self.oracle_contract,
            self.execution_record,
            self.effective_identity,
            *self.raw_evidence,
            *self.control_evidence,
        )
        artifact_leakage = _forbidden_terms(
            tuple(item.ref for item in all_artifacts)
            + tuple(item.kind for item in all_artifacts)
        )
        if artifact_leakage:
            raise DiscoveryContractError(
                "review artifact refs contain forbidden material: "
                + ", ".join(artifact_leakage)
            )
        raw_refs = {item.ref for item in self.raw_evidence}
        if not set(self.candidate_finding.evidence_refs).issubset(raw_refs):
            raise DiscoveryContractError("candidate Finding evidence is not present in raw evidence refs")
        _required_text(self.claim_boundary, "review claim boundary")
        _required_text(self.production_invocation_id, "production invocation id")
        _required_text(self.production_provider_family, "production provider family")
        _version(self.schema_version, "falsification review context")
        leakage = _forbidden_terms(self.to_dict())
        if leakage:
            raise DiscoveryContractError("review context contains forbidden material: " + ", ".join(leakage))

    @property
    def context_sha256(self) -> str:
        return _digest(self.to_dict())

    @property
    def candidate_finding_id(self) -> str:
        return self.candidate_finding.finding_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "target": self.target.to_dict(),
            "source_refs": [item.to_dict() for item in self.source_refs],
            "validated_fact_ids": list(self.validated_fact_ids),
            "hypothesis": self.hypothesis.to_dict(),
            "admitted_attack_plan": self.admitted_attack_plan.to_dict(),
            "oracle_contract": self.oracle_contract.to_dict(),
            "candidate_finding": self.candidate_finding.to_dict(),
            "execution_record": self.execution_record.to_dict(),
            "effective_identity": self.effective_identity.to_dict(),
            "raw_evidence": [item.to_dict() for item in self.raw_evidence],
            "control_evidence": [item.to_dict() for item in self.control_evidence],
            "claim_boundary": self.claim_boundary,
            "production_invocation_id": self.production_invocation_id,
            "production_provider_family": self.production_provider_family,
        }


@dataclass(frozen=True)
class FalsificationReviewerIdentity:
    """Separate invocation identity, with same-provider limitation disclosure."""

    backend: str
    requested_model: str
    effective_model: str
    invocation_id: str
    provider_family: str
    same_family_limitation: str
    identity_sha256: str | None = None
    role: str = FALSIFICATION_REVIEW_ROLE_ID
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "backend",
            "requested_model",
            "effective_model",
            "invocation_id",
            "provider_family",
            "same_family_limitation",
            "role",
        ):
            _required_text(getattr(self, field), field)
        _version(self.schema_version, "falsification reviewer identity")
        expected = _digest(
            {
                "backend": self.backend,
                "effective_model": self.effective_model,
                "invocation_id": self.invocation_id,
                "provider_family": self.provider_family,
                "requested_model": self.requested_model,
                "role": self.role,
                "same_family_limitation": self.same_family_limitation,
            }
        )
        if self.identity_sha256 is None:
            object.__setattr__(self, "identity_sha256", expected)
        elif self.identity_sha256 != expected or not _is_digest(self.identity_sha256):
            raise DiscoveryContractError("falsification reviewer identity digest does not match")

    @classmethod
    def capture(
        cls,
        *,
        backend: str,
        requested_model: str,
        effective_model: str,
        invocation_id: str,
        provider_family: str,
        same_family_limitation: str,
        role: str = FALSIFICATION_REVIEW_ROLE_ID,
    ) -> "FalsificationReviewerIdentity":
        return cls(
            backend=backend,
            requested_model=requested_model,
            effective_model=effective_model,
            invocation_id=invocation_id,
            provider_family=provider_family,
            same_family_limitation=same_family_limitation,
            role=role,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "role": self.role,
            "backend": self.backend,
            "requested_model": self.requested_model,
            "effective_model": self.effective_model,
            "invocation_id": self.invocation_id,
            "provider_family": self.provider_family,
            "same_family_limitation": self.same_family_limitation,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FalsificationReviewerIdentity":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("falsification reviewer identity must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "role",
                "backend",
                "requested_model",
                "effective_model",
                "invocation_id",
                "provider_family",
                "same_family_limitation",
                "identity_sha256",
            },
            "falsification reviewer identity",
        )
        try:
            return cls(
                backend=data["backend"],
                requested_model=data["requested_model"],
                effective_model=data["effective_model"],
                invocation_id=data["invocation_id"],
                provider_family=data["provider_family"],
                same_family_limitation=data["same_family_limitation"],
                identity_sha256=data.get("identity_sha256"),
                role=data.get("role", FALSIFICATION_REVIEW_ROLE_ID),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"falsification reviewer identity requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class ReviewReason:
    """Typed reason that explains a challenged or inconclusive dimension."""

    code: str
    message: str
    evidence_refs: tuple[str, ...]
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.code, "review reason code")
        _required_text(self.message, "review reason message")
        _text_tuple(self.evidence_refs, "review reason evidence refs", allow_empty=False)
        _version(self.schema_version, "review reason")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "code": self.code,
            "message": self.message,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewReason":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("review reason must be an object")
        _reject_unknown(data, {"schema_version", "code", "message", "evidence_refs"}, "review reason")
        try:
            return cls(
                code=data["code"],
                message=data["message"],
                evidence_refs=tuple(_list(data, "evidence_refs", "review reason")),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"review reason requires {error.args[0]}") from error


@dataclass(frozen=True)
class ReviewDimension:
    """One of the six mandatory falsification dimensions."""

    dimension: str
    status: str
    analysis: str
    evidence_refs: tuple[str, ...]
    reason_codes: tuple[str, ...] = ()
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.dimension not in REVIEW_DIMENSIONS:
            raise DiscoveryContractError("unknown falsification review dimension")
        if self.status not in _DIMENSION_STATUSES:
            raise DiscoveryContractError("invalid falsification dimension status")
        _required_text(self.analysis, "review dimension analysis")
        _text_tuple(self.evidence_refs, "review dimension evidence refs", allow_empty=False)
        _text_tuple(self.reason_codes, "review dimension reason codes")
        if self.status != "supported" and not self.reason_codes:
            raise DiscoveryContractError("challenged or inconclusive dimension requires a reason code")
        _version(self.schema_version, "review dimension")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "dimension": self.dimension,
            "status": self.status,
            "analysis": self.analysis,
            "evidence_refs": list(self.evidence_refs),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReviewDimension":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("review dimension must be an object")
        _reject_unknown(
            data,
            {"schema_version", "dimension", "status", "analysis", "evidence_refs", "reason_codes"},
            "review dimension",
        )
        try:
            return cls(
                dimension=data["dimension"],
                status=data["status"],
                analysis=data["analysis"],
                evidence_refs=tuple(_list(data, "evidence_refs", "review dimension")),
                reason_codes=tuple(
                    _list(
                        {"reason_codes": data.get("reason_codes", [])},
                        "reason_codes",
                        "review dimension",
                    )
                ),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"review dimension requires {error.args[0]}") from error


@dataclass(frozen=True)
class FalsificationReview:
    """Immutable review outcome; candidate Finding and refs are preserved."""

    review_id: str
    context_id: str
    context_sha256: str
    target_id: str
    candidate_finding: Finding
    reviewer_identity: FalsificationReviewerIdentity
    dimensions: tuple[ReviewDimension, ...]
    outcome: str
    reasons: tuple[ReviewReason, ...]
    raw_evidence_refs: tuple[ImmutableArtifactRef, ...]
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.review_id, "review_id")
        _required_text(self.context_id, "review context_id")
        if not _is_digest(self.context_sha256):
            raise DiscoveryContractError("review context_sha256 is invalid")
        _required_text(self.target_id, "review target_id")
        if not isinstance(self.candidate_finding, Finding):
            raise DiscoveryContractError("review candidate Finding is invalid")
        if self.candidate_finding.target_id != self.target_id:
            raise DiscoveryContractError("review candidate Finding target does not match")
        if not isinstance(self.reviewer_identity, FalsificationReviewerIdentity):
            raise DiscoveryContractError("reviewer identity is invalid")
        if not isinstance(self.dimensions, tuple) or len(self.dimensions) != len(REVIEW_DIMENSIONS):
            raise DiscoveryContractError("review must include exactly six dimensions")
        if any(not isinstance(item, ReviewDimension) for item in self.dimensions):
            raise DiscoveryContractError("review dimensions are invalid")
        if tuple(item.dimension for item in self.dimensions) != REVIEW_DIMENSIONS:
            raise DiscoveryContractError("review dimensions must appear in frozen order")
        if self.outcome not in _OUTCOMES:
            raise DiscoveryContractError("invalid falsification review outcome")
        if not isinstance(self.reasons, tuple) or any(not isinstance(item, ReviewReason) for item in self.reasons):
            raise DiscoveryContractError("review reasons are invalid")
        if not isinstance(self.raw_evidence_refs, tuple) or any(
            not isinstance(item, ImmutableArtifactRef) for item in self.raw_evidence_refs
        ):
            raise DiscoveryContractError("review raw evidence refs are invalid")
        if not self.raw_evidence_refs:
            raise DiscoveryContractError("review raw evidence refs must not be empty")
        expected = _derived_outcome(self.dimensions)
        if self.outcome != expected:
            raise DiscoveryContractError("review outcome contradicts dimension assessments")
        if self.outcome == "survived" and self.reasons:
            raise DiscoveryContractError("survived review cannot contain challenge reasons")
        if self.outcome != "survived" and not self.reasons:
            raise DiscoveryContractError("challenged or inconclusive review requires reasons")
        reason_codes = {item.code for item in self.reasons}
        if any(
            code not in reason_codes
            for dimension in self.dimensions
            for code in dimension.reason_codes
        ):
            raise DiscoveryContractError("review dimension reason code has no typed review reason")
        _version(self.schema_version, "falsification review")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "review_id": self.review_id,
            "context_id": self.context_id,
            "context_sha256": self.context_sha256,
            "target_id": self.target_id,
            "candidate_finding": self.candidate_finding.to_dict(),
            "reviewer_identity": self.reviewer_identity.to_dict(),
            "dimensions": [item.to_dict() for item in self.dimensions],
            "outcome": self.outcome,
            "reasons": [item.to_dict() for item in self.reasons],
            "raw_evidence_refs": [item.to_dict() for item in self.raw_evidence_refs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FalsificationReview":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("falsification review must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "review_id", "context_id", "context_sha256", "target_id",
                "candidate_finding", "reviewer_identity", "dimensions", "outcome", "reasons",
                "raw_evidence_refs",
            },
            "falsification review",
        )
        try:
            return cls(
                review_id=data["review_id"],
                context_id=data["context_id"],
                context_sha256=data["context_sha256"],
                target_id=data["target_id"],
                candidate_finding=Finding.from_dict(data["candidate_finding"]),
                reviewer_identity=FalsificationReviewerIdentity.from_dict(data["reviewer_identity"]),
                dimensions=tuple(
                    ReviewDimension.from_dict(item)
                    for item in _list(data, "dimensions", "falsification review")
                ),
                outcome=data["outcome"],
                reasons=tuple(
                    ReviewReason.from_dict(item)
                    for item in _list(data, "reasons", "falsification review")
                ),
                raw_evidence_refs=tuple(
                    ImmutableArtifactRef.from_dict(item)
                    for item in _list(data, "raw_evidence_refs", "falsification review")
                ),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"falsification review requires {error.args[0]}") from error


def _derived_outcome(dimensions: tuple[ReviewDimension, ...]) -> str:
    statuses = {item.status for item in dimensions}
    if "challenged" in statuses:
        return "challenged"
    if "inconclusive" in statuses:
        return "inconclusive"
    return "survived"


def validate_falsification_context(
    context: FalsificationReviewContext,
    reviewer_identity: FalsificationReviewerIdentity,
) -> tuple[str, ...]:
    """Validate context and identity separation before invoking the reviewer."""

    reasons: list[str] = []
    if not isinstance(context, FalsificationReviewContext):
        return ("review context contract is invalid",)
    if not isinstance(reviewer_identity, FalsificationReviewerIdentity):
        return ("reviewer identity contract is invalid",)
    if reviewer_identity.invocation_id == context.production_invocation_id:
        reasons.append("review invocation identity is not separate from production invocation")
    if reviewer_identity.role == "production-adjudicator":
        reasons.append("review identity uses the production adjudicator role")
    if reviewer_identity.provider_family == context.production_provider_family and not reviewer_identity.same_family_limitation.strip():
        reasons.append("same-provider review requires an explicit same-family limitation")
    all_refs = (
        *context.source_refs,
        context.oracle_contract,
        context.execution_record,
        context.effective_identity,
        *context.raw_evidence,
        *context.control_evidence,
    )
    refs = {item.ref for item in all_refs}
    if len(refs) != len(all_refs):
        reasons.append("review evidence references are duplicated")
    if _forbidden_terms(context.to_dict().get("claim_boundary")):
        reasons.append("review claim boundary contains forbidden cohort material")
    return tuple(dict.fromkeys(reasons))


def validate_falsification_review(
    review: FalsificationReview,
    context: FalsificationReviewContext,
) -> tuple[str, ...]:
    """Return deterministic post-invocation review validation reasons."""

    reasons = list(validate_falsification_context(context, review.reviewer_identity))
    if review.context_id != context.context_id:
        reasons.append("review context id does not match")
    if review.context_sha256 != context.context_sha256:
        reasons.append("review context digest does not match clean context")
    if review.target_id != context.target.target_id:
        reasons.append("review target does not match clean context")
    if review.candidate_finding != context.candidate_finding:
        reasons.append("review changed the candidate Finding")
    context_refs = {
        item.ref
        for item in (
            *context.source_refs,
            context.oracle_contract,
            context.execution_record,
            context.effective_identity,
            *context.raw_evidence,
            *context.control_evidence,
        )
    }
    for dimension in review.dimensions:
        for ref in dimension.evidence_refs:
            if ref not in context_refs:
                reasons.append(f"review dimension references evidence outside clean context: {ref}")
    for reason in review.reasons:
        for ref in reason.evidence_refs:
            if ref not in context_refs:
                reasons.append(f"review reason references evidence outside clean context: {ref}")
    for item in review.raw_evidence_refs:
        if item.ref not in context_refs:
            reasons.append(f"review references evidence outside clean context: {item.ref}")
    return tuple(dict.fromkeys(reasons))


FalsificationReviewBackend = Callable[[FalsificationReviewContext], Mapping[str, Any]]


@dataclass(frozen=True)
class FalsificationReviewResult:
    """One bounded reviewer invocation, including fail-closed rejection."""

    context_id: str
    reviewer_identity: FalsificationReviewerIdentity
    authoritative_output_sha256: str
    status: str
    review: FalsificationReview | None = None
    rejection_reasons: tuple[str, ...] = ()
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.context_id, "review result context_id")
        if not isinstance(self.reviewer_identity, FalsificationReviewerIdentity):
            raise DiscoveryContractError("review result identity is invalid")
        if not _is_digest(self.authoritative_output_sha256):
            raise DiscoveryContractError("review result output digest is invalid")
        if self.status not in {"complete", "rejected"}:
            raise DiscoveryContractError("review result status is invalid")
        if self.status == "complete" and not isinstance(self.review, FalsificationReview):
            raise DiscoveryContractError("complete review result requires review")
        if self.status == "rejected" and (self.review is not None or not self.rejection_reasons):
            raise DiscoveryContractError("rejected review result requires reasons only")
        if self.review is not None and self.review.context_id != self.context_id:
            raise DiscoveryContractError("review result context id does not match review")
        _text_tuple(self.rejection_reasons, "review result rejection reasons")
        _version(self.schema_version, "falsification review result")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "context_id": self.context_id,
            "reviewer_identity": self.reviewer_identity.to_dict(),
            "authoritative_output_sha256": self.authoritative_output_sha256,
            "status": self.status,
            "review": self.review.to_dict() if self.review is not None else None,
            "rejection_reasons": list(self.rejection_reasons),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FalsificationReviewResult":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("falsification review result must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "context_id", "reviewer_identity",
                "authoritative_output_sha256", "status", "review", "rejection_reasons",
            },
            "falsification review result",
        )
        try:
            raw_review = data.get("review")
            return cls(
                context_id=data["context_id"],
                reviewer_identity=FalsificationReviewerIdentity.from_dict(data["reviewer_identity"]),
                authoritative_output_sha256=data["authoritative_output_sha256"],
                status=data["status"],
                review=FalsificationReview.from_dict(raw_review) if raw_review is not None else None,
                rejection_reasons=tuple(
                    _list(data, "rejection_reasons", "falsification review result")
                ),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"falsification review result requires {error.args[0]}"
            ) from error


def run_falsification_review(
    context: FalsificationReviewContext,
    backend: FalsificationReviewBackend,
    identity: FalsificationReviewerIdentity,
) -> FalsificationReviewResult:
    """Invoke one separately identified reviewer on clean context only."""

    context_reasons = validate_falsification_context(context, identity)
    if context_reasons:
        digest = _digest({"rejected_context": context_reasons})
        return FalsificationReviewResult(
            context_id=context.context_id,
            reviewer_identity=identity,
            authoritative_output_sha256=digest,
            status="rejected",
            rejection_reasons=context_reasons,
        )
    if not callable(backend):
        raise DiscoveryContractError("falsification review backend must be callable")
    try:
        raw = backend(context)
    except Exception as error:
        reasons = (f"review backend failed: {type(error).__name__}",)
        return FalsificationReviewResult(
            context_id=context.context_id,
            reviewer_identity=identity,
            authoritative_output_sha256=_digest({"backend_error": reasons[0]}),
            status="rejected",
            rejection_reasons=reasons,
        )
    raw_digest = _digest(raw)
    reasons: list[str] = []
    review: FalsificationReview | None = None
    try:
        if not isinstance(raw, Mapping):
            raise DiscoveryContractError("review output must be an object")
        _reject_unknown(raw, {"schema_version", "review_id", "outcome", "dimensions", "reasons"}, "review output")
        version = raw.get("schema_version", 1)
        if version != 1 or isinstance(version, bool):
            raise DiscoveryContractError("unsupported review output schema_version")
        raw_dimensions = _list(raw, "dimensions", "review output")
        if len(raw_dimensions) != len(REVIEW_DIMENSIONS):
            raise DiscoveryContractError("review output must include six dimensions")
        dimensions = tuple(ReviewDimension.from_dict(item) for item in raw_dimensions)
        review_reasons = tuple(
            ReviewReason.from_dict(item)
            for item in _list({"reasons": raw.get("reasons", [])}, "reasons", "review output")
        )
        review = FalsificationReview(
            review_id=raw["review_id"],
            context_id=context.context_id,
            context_sha256=context.context_sha256,
            target_id=context.target.target_id,
            candidate_finding=context.candidate_finding,
            reviewer_identity=identity,
            dimensions=dimensions,
            outcome=raw["outcome"],
            reasons=review_reasons,
            raw_evidence_refs=context.raw_evidence,
        )
        reasons.extend(validate_falsification_review(review, context))
    except (DiscoveryContractError, KeyError, TypeError, ValueError) as error:
        reasons.append(f"review output is malformed or contradictory: {error}")
    if reasons or review is None:
        return FalsificationReviewResult(
            context_id=context.context_id,
            reviewer_identity=identity,
            authoritative_output_sha256=raw_digest,
            status="rejected",
            rejection_reasons=tuple(dict.fromkeys(reasons or ("review output was empty",))),
        )
    return FalsificationReviewResult(
        context_id=context.context_id,
        reviewer_identity=identity,
        authoritative_output_sha256=raw_digest,
        status="complete",
        review=review,
    )


run_review = run_falsification_review


@dataclass(frozen=True)
class FalsificationReconciliation:
    """Aggregate gate that preserves the candidate Finding and evidence refs."""

    finding: Finding
    review_id: str
    review_outcome: str
    aggregate_supported: bool
    blocking_reasons: tuple[str, ...]
    raw_evidence_refs: tuple[ImmutableArtifactRef, ...]
    schema_version: int = FALSIFICATION_REVIEW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.finding, Finding):
            raise DiscoveryContractError("reconciliation Finding is invalid")
        _required_text(self.review_id, "reconciliation review_id")
        if self.review_outcome not in _OUTCOMES:
            raise DiscoveryContractError("reconciliation review outcome is invalid")
        if not isinstance(self.aggregate_supported, bool):
            raise DiscoveryContractError("reconciliation aggregate_supported must be boolean")
        _text_tuple(self.blocking_reasons, "reconciliation blocking reasons")
        if not isinstance(self.raw_evidence_refs, tuple) or any(
            not isinstance(item, ImmutableArtifactRef) for item in self.raw_evidence_refs
        ):
            raise DiscoveryContractError("reconciliation evidence refs are invalid")
        if self.review_outcome != "survived" and self.aggregate_supported:
            raise DiscoveryContractError("non-survived review cannot support aggregate")
        if not self.raw_evidence_refs:
            raise DiscoveryContractError("reconciliation raw evidence refs must not be empty")
        _version(self.schema_version, "falsification reconciliation")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "finding": self.finding.to_dict(),
            "review_id": self.review_id,
            "review_outcome": self.review_outcome,
            "aggregate_supported": self.aggregate_supported,
            "blocking_reasons": list(self.blocking_reasons),
            "raw_evidence_refs": [item.to_dict() for item in self.raw_evidence_refs],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FalsificationReconciliation":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("falsification reconciliation must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "finding", "review_id", "review_outcome",
                "aggregate_supported", "blocking_reasons", "raw_evidence_refs",
            },
            "falsification reconciliation",
        )
        try:
            return cls(
                finding=Finding.from_dict(data["finding"]),
                review_id=data["review_id"],
                review_outcome=data["review_outcome"],
                aggregate_supported=data["aggregate_supported"],
                blocking_reasons=tuple(
                    _list(data, "blocking_reasons", "falsification reconciliation")
                ),
                raw_evidence_refs=tuple(
                    ImmutableArtifactRef.from_dict(item)
                    for item in _list(data, "raw_evidence_refs", "falsification reconciliation")
                ),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"falsification reconciliation requires {error.args[0]}"
            ) from error


def reconcile_finding(
    finding: Finding,
    review: FalsificationReview,
    context: FalsificationReviewContext,
) -> FalsificationReconciliation:
    """Gate aggregate support without changing the candidate Finding."""

    errors = validate_falsification_review(review, context)
    if errors:
        raise DiscoveryContractError("cannot reconcile invalid review: " + "; ".join(errors))
    if finding != context.candidate_finding or finding != review.candidate_finding:
        raise DiscoveryContractError("reconciliation cannot replace the candidate Finding")
    supported = finding.conclusion == "supported" and review.outcome == "survived"
    blocking = () if supported else (
        "falsification review blocks aggregate support",
    )
    return FalsificationReconciliation(
        finding=finding,
        review_id=review.review_id,
        review_outcome=review.outcome,
        aggregate_supported=supported,
        blocking_reasons=blocking,
        raw_evidence_refs=context.raw_evidence,
    )


reconcile_review = reconcile_finding


__all__ = [
    "FALSIFICATION_REVIEW_ROLE_ID",
    "FALSIFICATION_REVIEW_SCHEMA_VERSION",
    "REVIEW_DIMENSIONS",
    "FalsificationReconciliation",
    "FalsificationReview",
    "FalsificationReviewBackend",
    "FalsificationReviewContext",
    "FalsificationReviewResult",
    "FalsificationReviewerIdentity",
    "ImmutableArtifactRef",
    "ReviewDimension",
    "ReviewReason",
    "reconcile_finding",
    "reconcile_review",
    "run_falsification_review",
    "run_review",
    "validate_falsification_context",
    "validate_falsification_review",
]
