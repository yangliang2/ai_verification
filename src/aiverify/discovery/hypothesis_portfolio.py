"""Strict, side-effect-free generation and freezing of an M9 hypothesis portfolio.

The generator boundary accepts only a provenance-bound ``ProjectTarget``, its
acquired context graph, the approved three-prior registry, and a finite budget.
Backend output is captured by digest and parsed into strict candidate
contracts.  All validation, priority calculation, ordering, ledger decisions,
and frontier accounting happen deterministically after that capture.

No scenario, journey, expected result, oracle, verdict, cohort, or execution
contract is part of the generation request or candidate response.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from aiverify.discovery.campaign import HypothesisSelectionLedger
from aiverify.discovery.contracts import (
    AttackOperator,
    FailureChain,
    RiskHypothesis,
    RiskPrior,
)
from aiverify.discovery.lifetime_ownership_risk import (
    LIFETIME_OWNERSHIP_OPERATOR_ID,
    LIFETIME_OWNERSHIP_PRIOR_ID,
    make_lifetime_ownership_operator,
    make_lifetime_ownership_prior,
    make_lifetime_ownership_strategy,
)
from aiverify.discovery.models import (
    DiscoveryContractError,
    ProjectTarget,
    QualityContextGraph,
    target_from_dict,
)
from aiverify.discovery.risk import (
    RiskDerivationStrategy,
    RiskPriority,
    make_latency_operator,
    make_temporal_prior,
    make_temporal_strategy,
)
from aiverify.discovery.state_evolution_risk import (
    STATE_EVOLUTION_OPERATOR_ID,
    STATE_EVOLUTION_PRIOR_ID,
    make_historical_state_replay_operator,
    make_state_evolution_prior,
    make_state_evolution_strategy,
)


GENERATOR_ROLE_ID = "verification-agent-hypothesis-generator-v1"
PORTFOLIO_SCHEMA_VERSION = 1
MAX_PORTFOLIO_SIZE = 3
OUTCOME_LEAKAGE_TERMS = frozenset(
    {
        "journey",
        "hidden",
        "mapping",
        "expected",
        "oracle",
        "verdict",
        "outcome",
        "finding",
        "defect",
        "control",
        "holdout",
        "cohort",
        "scenario",
    }
)
_GENERIC_SUSPICION_PHRASES = (
    "something may go wrong",
    "the app may fail",
    "quality may degrade",
    "there may be a bug",
    "some problem may occur",
    "potential issue",
    "it might fail",
    "unknown issue",
)
_DECISIONS = frozenset({"selected", "deferred", "rejected"})
_STATUSES = frozenset({"complete", "partial", "rejected"})


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _text_tuple(
    value: object,
    field: str,
    *,
    allow_empty: bool = True,
    unique: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    if unique and len(set(value)) != len(value):
        raise DiscoveryContractError(f"{field} must contain unique values")
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
        raise DiscoveryContractError("portfolio value is not canonical JSON") from error
    return hashlib.sha256(encoded).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(
            f"unknown {label} field(s): " + ", ".join(unknown)
        )


def _list_to_tuple(data: Mapping[str, Any], field: str, label: str) -> tuple[Any, ...]:
    value = data[field]
    if not isinstance(value, list):
        raise DiscoveryContractError(f"{label} {field} must be an array")
    return tuple(value)


def _text_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_text_values(key))
            result.extend(_text_values(item))
        return tuple(result)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = []
        for item in value:
            result.extend(_text_values(item))
        return tuple(result)
    return ()


def _leakage_terms(values: Sequence[object]) -> tuple[str, ...]:
    found: set[str] = set()
    for text in _text_values(values):
        lowered = text.lower()
        for term in OUTCOME_LEAKAGE_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                found.add(term)
    return tuple(sorted(found))


@dataclass(frozen=True)
class HypothesisGeneratorIdentity:
    """Captured backend/requested/effective model identity for one generation."""

    backend: str
    requested_model: str
    effective_model: str
    invocation_id: str
    identity_sha256: str | None = None
    role: str = GENERATOR_ROLE_ID
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("backend", "requested_model", "effective_model", "invocation_id", "role"):
            _required_text(getattr(self, field), field)
        _version(self.schema_version, "hypothesis generator identity")
        payload = {
            "backend": self.backend,
            "effective_model": self.effective_model,
            "invocation_id": self.invocation_id,
            "requested_model": self.requested_model,
            "role": self.role,
        }
        expected = _digest(payload)
        if self.identity_sha256 is None:
            object.__setattr__(self, "identity_sha256", expected)
        elif self.identity_sha256 != expected or not _is_digest(self.identity_sha256):
            raise DiscoveryContractError("hypothesis generator identity digest does not match")

    @classmethod
    def capture(
        cls,
        *,
        backend: str,
        requested_model: str,
        effective_model: str,
        invocation_id: str,
        role: str = GENERATOR_ROLE_ID,
    ) -> "HypothesisGeneratorIdentity":
        return cls(
            backend=backend,
            requested_model=requested_model,
            effective_model=effective_model,
            invocation_id=invocation_id,
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
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisGeneratorIdentity":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis generator identity must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "role",
                "backend",
                "requested_model",
                "effective_model",
                "invocation_id",
                "identity_sha256",
            },
            "hypothesis generator identity",
        )
        try:
            return cls(
                backend=data["backend"],
                requested_model=data["requested_model"],
                effective_model=data["effective_model"],
                invocation_id=data["invocation_id"],
                identity_sha256=data.get("identity_sha256"),
                role=data.get("role", GENERATOR_ROLE_ID),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis generator identity requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class ApprovedPriorDefinition:
    """One prior/operator/strategy binding allowed into generation."""

    prior: RiskPrior
    operator: AttackOperator
    strategy: RiskDerivationStrategy
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.prior, RiskPrior):
            raise DiscoveryContractError("approved prior definition requires RiskPrior")
        if not isinstance(self.operator, AttackOperator):
            raise DiscoveryContractError("approved prior definition requires AttackOperator")
        if not isinstance(self.strategy, RiskDerivationStrategy):
            raise DiscoveryContractError("approved prior definition requires strategy")
        if self.operator.operator_id not in self.prior.operator_ids:
            raise DiscoveryContractError("approved operator is not compatible with prior")
        if self.prior.prior_id not in self.strategy.compatible_prior_ids:
            raise DiscoveryContractError("approved strategy is not compatible with prior")
        if self.operator.operator_id not in self.strategy.compatible_operator_ids:
            raise DiscoveryContractError("approved strategy is not compatible with operator")
        _version(self.schema_version, "approved prior definition")

    @property
    def prior_id(self) -> str:
        return self.prior.prior_id

    @property
    def operator_id(self) -> str:
        return self.operator.operator_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prior": self.prior.to_dict(),
            "operator": self.operator.to_dict(),
            "strategy": self.strategy.to_dict(),
        }


def approved_m9_prior_registry() -> tuple[ApprovedPriorDefinition, ...]:
    """Return the exactly-three versioned M9 prior definitions in stable order."""

    temporal_prior = make_temporal_prior()
    state_prior = make_state_evolution_prior()
    lifetime_prior = make_lifetime_ownership_prior()
    return (
        ApprovedPriorDefinition(
            prior=temporal_prior,
            operator=make_latency_operator(temporal_prior.operator_ids[0]),
            strategy=make_temporal_strategy(prior=temporal_prior),
        ),
        ApprovedPriorDefinition(
            prior=state_prior,
            operator=make_historical_state_replay_operator(
                state_prior.operator_ids[0]
            ),
            strategy=make_state_evolution_strategy(prior=state_prior),
        ),
        ApprovedPriorDefinition(
            prior=lifetime_prior,
            operator=make_lifetime_ownership_operator(
                lifetime_prior.operator_ids[0]
            ),
            strategy=make_lifetime_ownership_strategy(prior=lifetime_prior),
        ),
    )


approved_prior_registry = approved_m9_prior_registry


@dataclass(frozen=True)
class HypothesisGenerationRequest:
    """The only input envelope visible to the hypothesis generation role."""

    request_id: str
    target: ProjectTarget
    graph: QualityContextGraph
    approved_priors: tuple[RiskPrior, ...]
    budget: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.request_id, "generation request_id")
        if not isinstance(self.target, ProjectTarget):
            raise DiscoveryContractError("hypothesis generation requires ProjectTarget")
        if not isinstance(self.graph, QualityContextGraph):
            raise DiscoveryContractError("hypothesis generation requires QualityContextGraph")
        if self.graph.target_id != self.target.target_id:
            raise DiscoveryContractError("generation graph target does not match target")
        if (
            self.graph.source_origin != self.target.source_origin
            or self.graph.source_commit != self.target.source_commit
            or self.graph.source_tree_sha256 is None
        ):
            raise DiscoveryContractError(
                "generation graph provenance does not match ProjectTarget"
            )
        if not isinstance(self.approved_priors, tuple) or len(self.approved_priors) != 3:
            raise DiscoveryContractError("generation request requires exactly three approved priors")
        if any(not isinstance(prior, RiskPrior) for prior in self.approved_priors):
            raise DiscoveryContractError("generation approved_priors are invalid")
        if len({prior.prior_id for prior in self.approved_priors}) != 3:
            raise DiscoveryContractError("generation approved priors must be unique")
        if not isinstance(self.budget, int) or isinstance(self.budget, bool) or self.budget < 1:
            raise DiscoveryContractError("generation budget must be a positive integer")
        _version(self.schema_version, "hypothesis generation request")
        leakage = _leakage_terms(self.approved_priors)
        if leakage:
            raise DiscoveryContractError(
                "generation prior definitions contain outcome leakage: "
                + ", ".join(leakage)
            )

    @property
    def graph_sha256(self) -> str:
        return _digest(self.graph.to_dict())

    @property
    def approved_prior_ids(self) -> tuple[str, ...]:
        return tuple(prior.prior_id for prior in self.approved_priors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "target": self.target.to_dict(),
            "graph": self.graph.to_dict(),
            "approved_priors": [prior.to_dict() for prior in self.approved_priors],
            "budget": self.budget,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisGenerationRequest":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis generation request must be an object")
        _reject_unknown(
            data,
            {"schema_version", "request_id", "target", "graph", "approved_priors", "budget"},
            "hypothesis generation request",
        )
        try:
            target = target_from_dict(data["target"])
            if not isinstance(target, ProjectTarget):
                raise DiscoveryContractError("hypothesis generation requires ProjectTarget")
            return cls(
                request_id=data["request_id"],
                target=target,
                graph=QualityContextGraph.from_dict(data["graph"]),
                approved_priors=tuple(
                    RiskPrior.from_dict(item)
                    for item in _list_to_tuple(data, "approved_priors", "generation request")
                ),
                budget=data["budget"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis generation request requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class HypothesisCandidate:
    """One strict, backend-authored candidate before deterministic validation."""

    candidate_id: str
    prior_id: str
    operator_id: str
    hypothesis: RiskHypothesis
    failure_chain: FailureChain
    uncertainty: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("candidate_id", "prior_id", "operator_id"):
            _required_text(getattr(self, field), field)
        if not isinstance(self.hypothesis, RiskHypothesis):
            raise DiscoveryContractError("hypothesis candidate hypothesis is invalid")
        if not isinstance(self.failure_chain, FailureChain):
            raise DiscoveryContractError("hypothesis candidate failure_chain is invalid")
        _text_tuple(self.uncertainty, "candidate uncertainty", allow_empty=False, unique=True)
        _version(self.schema_version, "hypothesis candidate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "prior_id": self.prior_id,
            "operator_id": self.operator_id,
            "hypothesis": self.hypothesis.to_dict(),
            "failure_chain": self.failure_chain.to_dict(),
            "uncertainty": list(self.uncertainty),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisCandidate":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis candidate must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "candidate_id",
                "prior_id",
                "operator_id",
                "hypothesis",
                "failure_chain",
                "uncertainty",
            },
            "hypothesis candidate",
        )
        try:
            uncertainty = _list_to_tuple(data, "uncertainty", "hypothesis candidate")
            return cls(
                candidate_id=data["candidate_id"],
                prior_id=data["prior_id"],
                operator_id=data["operator_id"],
                hypothesis=RiskHypothesis.from_dict(data["hypothesis"]),
                failure_chain=FailureChain.from_dict(data["failure_chain"]),
                uncertainty=tuple(uncertainty),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis candidate requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class CandidateRejection:
    """Auditable rejection for a malformed or unsupported backend candidate."""

    candidate_id: str
    raw_sha256: str
    reasons: tuple[str, ...]
    prior_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.candidate_id, "candidate rejection candidate_id")
        if not _is_digest(self.raw_sha256):
            raise DiscoveryContractError("candidate rejection raw_sha256 is invalid")
        _text_tuple(self.reasons, "candidate rejection reasons", allow_empty=False, unique=True)
        if self.prior_id is not None:
            _required_text(self.prior_id, "candidate rejection prior_id")
        _version(self.schema_version, "candidate rejection")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "raw_sha256": self.raw_sha256,
            "reasons": list(self.reasons),
        }
        if self.prior_id is not None:
            result["prior_id"] = self.prior_id
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "CandidateRejection":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("candidate rejection must be an object")
        _reject_unknown(
            data,
            {"schema_version", "candidate_id", "raw_sha256", "reasons", "prior_id"},
            "candidate rejection",
        )
        try:
            return cls(
                candidate_id=data["candidate_id"],
                raw_sha256=data["raw_sha256"],
                reasons=tuple(_list_to_tuple(data, "reasons", "candidate rejection")),
                prior_id=data.get("prior_id"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"candidate rejection requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class HypothesisGenerationResponse:
    """Captured authoritative output, including parseable and rejected candidates."""

    request_id: str
    target_id: str
    graph_sha256: str
    generator_identity: HypothesisGeneratorIdentity
    authoritative_output_sha256: str
    candidates: tuple[HypothesisCandidate, ...]
    rejected_candidates: tuple[CandidateRejection, ...] = ()
    status: str = "complete"
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.request_id, "generation response request_id")
        _required_text(self.target_id, "generation response target_id")
        if not _is_digest(self.graph_sha256):
            raise DiscoveryContractError("generation response graph_sha256 is invalid")
        if not isinstance(self.generator_identity, HypothesisGeneratorIdentity):
            raise DiscoveryContractError("generation response identity is invalid")
        if not _is_digest(self.authoritative_output_sha256):
            raise DiscoveryContractError("authoritative output digest is invalid")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, HypothesisCandidate) for item in self.candidates
        ):
            raise DiscoveryContractError("generation response candidates are invalid")
        if not isinstance(self.rejected_candidates, tuple) or any(
            not isinstance(item, CandidateRejection) for item in self.rejected_candidates
        ):
            raise DiscoveryContractError("generation response rejected candidates are invalid")
        ids = [item.candidate_id for item in self.candidates]
        ids.extend(item.candidate_id for item in self.rejected_candidates)
        if len(ids) != len(set(ids)):
            raise DiscoveryContractError("generation response candidate ids must be unique")
        if self.status not in _STATUSES:
            raise DiscoveryContractError("invalid generation response status")
        if self.status == "complete" and self.rejected_candidates:
            raise DiscoveryContractError("complete generation response cannot contain rejections")
        if self.status == "rejected" and self.candidates:
            raise DiscoveryContractError("rejected generation response cannot contain candidates")
        _version(self.schema_version, "hypothesis generation response")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "target_id": self.target_id,
            "graph_sha256": self.graph_sha256,
            "generator_identity": self.generator_identity.to_dict(),
            "authoritative_output_sha256": self.authoritative_output_sha256,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "rejected_candidates": [item.to_dict() for item in self.rejected_candidates],
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisGenerationResponse":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis generation response must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "request_id",
                "target_id",
                "graph_sha256",
                "generator_identity",
                "authoritative_output_sha256",
                "candidates",
                "rejected_candidates",
                "status",
            },
            "hypothesis generation response",
        )
        try:
            return cls(
                request_id=data["request_id"],
                target_id=data["target_id"],
                graph_sha256=data["graph_sha256"],
                generator_identity=HypothesisGeneratorIdentity.from_dict(
                    data["generator_identity"]
                ),
                authoritative_output_sha256=data["authoritative_output_sha256"],
                candidates=tuple(
                    HypothesisCandidate.from_dict(item)
                    for item in _list_to_tuple(data, "candidates", "generation response")
                ),
                rejected_candidates=tuple(
                    CandidateRejection.from_dict(item)
                    for item in _list_to_tuple(
                        {"rejected_candidates": data.get("rejected_candidates", [])},
                        "rejected_candidates",
                        "generation response",
                    )
                ),
                status=data.get("status", "complete"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis generation response requires {error.args[0]}"
            ) from error


HypothesisGeneratorBackend = Callable[
    [HypothesisGenerationRequest], Mapping[str, Any]
]


def generate_hypothesis_response(
    request: HypothesisGenerationRequest,
    backend: HypothesisGeneratorBackend,
    identity: HypothesisGeneratorIdentity,
) -> HypothesisGenerationResponse:
    """Call one bounded backend and capture its authoritative structured output."""

    if not isinstance(request, HypothesisGenerationRequest):
        raise DiscoveryContractError("hypothesis generation request is invalid")
    if not callable(backend):
        raise DiscoveryContractError("hypothesis generation backend must be callable")
    if not isinstance(identity, HypothesisGeneratorIdentity):
        raise DiscoveryContractError("hypothesis generation identity is invalid")
    try:
        raw = backend(request)
    except Exception as error:  # backend failures stay outside deterministic validation
        raise DiscoveryContractError(
            f"hypothesis generation backend failed: {type(error).__name__}"
        ) from error
    if not isinstance(raw, Mapping):
        raise DiscoveryContractError("hypothesis generation backend output must be an object")
    _reject_unknown(raw, {"schema_version", "candidates"}, "generation backend output")
    if raw.get("schema_version", 1) != 1 or isinstance(raw.get("schema_version", 1), bool):
        raise DiscoveryContractError("unsupported generation backend output schema_version")
    raw_candidates = raw.get("candidates")
    if not isinstance(raw_candidates, list):
        raise DiscoveryContractError("generation backend candidates must be an array")
    authoritative_digest = _digest(raw)
    candidates: list[HypothesisCandidate] = []
    rejected: list[CandidateRejection] = []
    used_ids: set[str] = set()
    for raw_candidate in raw_candidates:
        raw_digest = _digest(raw_candidate)
        if isinstance(raw_candidate, Mapping):
            proposed_id = raw_candidate.get("candidate_id")
            candidate_id = (
                proposed_id.strip()
                if isinstance(proposed_id, str) and proposed_id.strip()
                else f"candidate-raw-{raw_digest[:16]}"
            )
            prior_id = (
                raw_candidate.get("prior_id")
                if isinstance(raw_candidate.get("prior_id"), str)
                else None
            )
        else:
            candidate_id = f"candidate-raw-{raw_digest[:16]}"
            prior_id = None
        if candidate_id in used_ids:
            candidate_id = f"{candidate_id}-raw-{raw_digest[:8]}"
        used_ids.add(candidate_id)
        try:
            if not isinstance(raw_candidate, Mapping):
                raise DiscoveryContractError("candidate must be an object")
            candidate = HypothesisCandidate.from_dict(raw_candidate)
            if candidate.candidate_id != candidate_id:
                raise DiscoveryContractError("candidate id normalization changed authoritative output")
            candidates.append(candidate)
        except (DiscoveryContractError, KeyError, TypeError, ValueError) as error:
            rejected.append(
                CandidateRejection(
                    candidate_id=candidate_id,
                    raw_sha256=raw_digest,
                    prior_id=prior_id,
                    reasons=(f"candidate schema invalid: {error}",),
                )
            )
    status = "complete" if not rejected else ("partial" if candidates else "rejected")
    return HypothesisGenerationResponse(
        request_id=request.request_id,
        target_id=request.target.target_id,
        graph_sha256=request.graph_sha256,
        generator_identity=identity,
        authoritative_output_sha256=authoritative_digest,
        candidates=tuple(candidates),
        rejected_candidates=tuple(rejected),
        status=status,
    )


generate_hypotheses = generate_hypothesis_response


def _candidate_fingerprint(candidate: HypothesisCandidate) -> str:
    hypothesis = candidate.hypothesis
    return _digest(
        {
            "consequence": _normalize(hypothesis.consequence),
            "mechanism": _normalize(hypothesis.mechanism),
            "supporting_fact_ids": sorted(hypothesis.supporting_fact_ids),
            "trigger": _normalize(hypothesis.trigger),
        }
    )


def _normalize(value: str) -> str:
    return " ".join(value.lower().split())


def validate_hypothesis_candidate(
    candidate: HypothesisCandidate,
    request: HypothesisGenerationRequest,
    prior_definition: ApprovedPriorDefinition | None = None,
) -> tuple[str, ...]:
    """Return deterministic rejection reasons; an empty tuple means valid."""

    reasons: list[str] = []
    if not isinstance(candidate, HypothesisCandidate):
        return ("candidate contract is invalid",)
    if not isinstance(request, HypothesisGenerationRequest):
        return ("generation request contract is invalid",)
    if candidate.prior_id not in request.approved_prior_ids:
        reasons.append("candidate prior is not in the approved registry")
    if prior_definition is None:
        reasons.append("candidate prior definition is missing")
    else:
        if candidate.prior_id != prior_definition.prior_id:
            reasons.append("candidate prior does not match selected prior definition")
        if candidate.operator_id != prior_definition.operator_id:
            reasons.append("candidate operator does not match selected prior definition")
        if candidate.operator_id not in prior_definition.prior.operator_ids:
            reasons.append("candidate operator is unsupported by selected prior")
    hypothesis = candidate.hypothesis
    chain = candidate.failure_chain
    if hypothesis.target_id != request.target.target_id:
        reasons.append("candidate hypothesis target does not match ProjectTarget")
    if hypothesis.prior_id != candidate.prior_id:
        reasons.append("candidate hypothesis prior does not match candidate prior")
    if hypothesis.failure_chain_id != chain.chain_id:
        reasons.append("candidate failure chain does not match hypothesis")
    if hypothesis.priority_id is not None:
        reasons.append("candidate must not supply priority before deterministic calculation")
    if hypothesis.status not in {"draft", "frozen"}:
        reasons.append("candidate hypothesis status is not draft or frozen")
    if len(set(hypothesis.supporting_fact_ids)) != len(hypothesis.supporting_fact_ids):
        reasons.append("candidate supporting fact ids are duplicated")

    facts = {fact.fact_id: fact for fact in request.graph.facts}
    for fact_id in hypothesis.supporting_fact_ids:
        fact = facts.get(fact_id)
        if fact is None:
            reasons.append(f"candidate references missing fact: {fact_id}")
        elif fact.status != "known":
            reasons.append(f"candidate fact {fact_id} is {fact.status}")
        elif not fact.provenance:
            reasons.append(f"candidate fact {fact_id} lacks provenance")
    if not chain.fact_ids:
        reasons.append("candidate failure chain has no supporting facts")
    if len(set(chain.fact_ids)) != len(chain.fact_ids):
        reasons.append("candidate failure chain is circular because fact ids repeat")
    if not set(chain.fact_ids).issubset(set(hypothesis.supporting_fact_ids)):
        reasons.append("candidate failure chain references unsupported facts")
    if len(chain.steps) < 2:
        reasons.append("candidate failure chain is not falsifiable with two causal steps")
    if not chain.causal_roles:
        reasons.append("candidate failure chain causal roles are missing")
    normalized_steps = tuple(_normalize(step) for step in chain.steps)
    if len(set(normalized_steps)) != len(normalized_steps):
        reasons.append("candidate failure chain is circular because causal steps repeat")
    if chain.consequence not in {hypothesis.quality_property, hypothesis.consequence}:
        reasons.append("candidate failure chain consequence does not match hypothesis")

    leakage = _leakage_terms((candidate.to_dict(),))
    if leakage:
        reasons.append("candidate contains outcome leakage: " + ", ".join(leakage))
    semantic_text = " ".join(
        (
            hypothesis.quality_property,
            hypothesis.trigger,
            hypothesis.mechanism,
            hypothesis.consequence,
        )
    ).lower()
    if any(phrase in semantic_text for phrase in _GENERIC_SUSPICION_PHRASES):
        reasons.append("candidate is generic and not falsifiable")
    if _normalize(hypothesis.trigger) == _normalize(hypothesis.mechanism):
        reasons.append("candidate trigger and mechanism are not distinct")
    if not hypothesis.required_evidence:
        reasons.append("candidate required evidence is incomplete")
    return tuple(dict.fromkeys(reasons))


validate_candidate = validate_hypothesis_candidate


def calculate_risk_priority(
    candidate: HypothesisCandidate,
    graph: QualityContextGraph,
) -> RiskPriority:
    """Calculate transparent deterministic priority factors after output capture."""

    hypothesis = candidate.hypothesis
    text = " ".join(
        (hypothesis.quality_property, hypothesis.consequence, hypothesis.rationale)
    ).lower()
    impact = 1.0 if any(term in text for term in ("critical", "high impact", "data loss")) else 0.6
    propagation_reach = min(
        1.0,
        len(set(candidate.failure_chain.fact_ids)) / max(1, min(6, len(graph.facts))),
    )
    context_sensitivity = min(
        1.0,
        len(set(candidate.hypothesis.supporting_fact_ids))
        / max(1, len(candidate.failure_chain.steps)),
    )
    uncertainty = min(
        1.0,
        (len(candidate.uncertainty) + len(hypothesis.unknowns))
        / max(1, len(hypothesis.required_evidence)),
    )
    evidence_gap = min(
        1.0,
        max(0, len(hypothesis.required_evidence) - len(hypothesis.supporting_fact_ids))
        / max(1, len(hypothesis.required_evidence)),
    )
    estimated_probe_cost = min(
        1.0,
        (len(hypothesis.required_evidence) + len(candidate.failure_chain.steps)) / 10.0,
    )
    priority_id = "priority-portfolio-" + candidate.candidate_id
    rationale = (
        "Deterministic post-capture factors: "
        f"impact={impact:.6f}; propagation_reach={propagation_reach:.6f}; "
        f"context_sensitivity={context_sensitivity:.6f}; uncertainty={uncertainty:.6f}; "
        f"evidence_gap={evidence_gap:.6f}; estimated_probe_cost={estimated_probe_cost:.6f}. "
        "The score is an ordering aid, not a probability or verdict."
    )
    return RiskPriority(
        priority_id=priority_id,
        impact=impact,
        propagation_reach=propagation_reach,
        context_sensitivity=context_sensitivity,
        uncertainty=uncertainty,
        evidence_gap=evidence_gap,
        estimated_probe_cost=estimated_probe_cost,
        rationale=rationale,
    )


@dataclass(frozen=True)
class HypothesisPortfolioItem:
    """One selected, frozen candidate and its deterministic priority."""

    candidate_id: str
    prior_id: str
    operator_id: str
    hypothesis: RiskHypothesis
    failure_chain: FailureChain
    priority: RiskPriority
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.candidate_id, "portfolio item candidate_id")
        _required_text(self.prior_id, "portfolio item prior_id")
        _required_text(self.operator_id, "portfolio item operator_id")
        if not isinstance(self.hypothesis, RiskHypothesis):
            raise DiscoveryContractError("portfolio item hypothesis is invalid")
        if not isinstance(self.failure_chain, FailureChain):
            raise DiscoveryContractError("portfolio item failure chain is invalid")
        if not isinstance(self.priority, RiskPriority):
            raise DiscoveryContractError("portfolio item priority is invalid")
        if self.hypothesis.status != "frozen":
            raise DiscoveryContractError("portfolio item hypothesis must be frozen")
        if self.hypothesis.priority_id != self.priority.priority_id:
            raise DiscoveryContractError("portfolio item priority does not match hypothesis")
        if self.hypothesis.prior_id != self.prior_id:
            raise DiscoveryContractError("portfolio item prior does not match hypothesis")
        if self.hypothesis.failure_chain_id != self.failure_chain.chain_id:
            raise DiscoveryContractError("portfolio item chain does not match hypothesis")
        _version(self.schema_version, "portfolio item")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_id": self.candidate_id,
            "prior_id": self.prior_id,
            "operator_id": self.operator_id,
            "hypothesis": self.hypothesis.to_dict(),
            "failure_chain": self.failure_chain.to_dict(),
            "priority": self.priority.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisPortfolioItem":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("portfolio item must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "candidate_id",
                "prior_id",
                "operator_id",
                "hypothesis",
                "failure_chain",
                "priority",
            },
            "portfolio item",
        )
        try:
            return cls(
                candidate_id=data["candidate_id"],
                prior_id=data["prior_id"],
                operator_id=data["operator_id"],
                hypothesis=RiskHypothesis.from_dict(data["hypothesis"]),
                failure_chain=FailureChain.from_dict(data["failure_chain"]),
                priority=RiskPriority.from_dict(data["priority"]),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"portfolio item requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class HypothesisPortfolio:
    """Frozen ordered top-three portfolio with complete decision accounting."""

    portfolio_id: str
    request_id: str
    target_id: str
    source_origin: str
    source_commit: str
    source_tree_sha256: str
    graph_sha256: str
    generator_identity: HypothesisGeneratorIdentity
    authoritative_output_sha256: str
    approved_prior_ids: tuple[str, ...]
    candidates: tuple[HypothesisCandidate, ...]
    selected: tuple[HypothesisPortfolioItem, ...]
    rejected_candidates: tuple[CandidateRejection, ...]
    selection_ledger: HypothesisSelectionLedger
    budget: int
    budget_consumed: int
    remaining_budget: int
    remaining_prior_ids: tuple[str, ...]
    remaining_fact_ids: tuple[str, ...]
    coverage_frontier: tuple[str, ...]
    status: str = "frozen"
    schema_version: int = PORTFOLIO_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in (
            "portfolio_id",
            "request_id",
            "target_id",
            "source_origin",
            "source_commit",
        ):
            _required_text(getattr(self, field), field)
        if not _is_digest(self.source_tree_sha256):
            raise DiscoveryContractError("portfolio source_tree_sha256 is invalid")
        if not _is_digest(self.graph_sha256):
            raise DiscoveryContractError("portfolio graph_sha256 is invalid")
        if not isinstance(self.generator_identity, HypothesisGeneratorIdentity):
            raise DiscoveryContractError("portfolio generator identity is invalid")
        if not _is_digest(self.authoritative_output_sha256):
            raise DiscoveryContractError("portfolio authoritative output digest is invalid")
        _text_tuple(self.approved_prior_ids, "approved prior ids", allow_empty=False, unique=True)
        if len(self.approved_prior_ids) != 3:
            raise DiscoveryContractError("portfolio requires exactly three approved priors")
        if not isinstance(self.candidates, tuple) or any(
            not isinstance(item, HypothesisCandidate) for item in self.candidates
        ):
            raise DiscoveryContractError("portfolio candidates are invalid")
        if not isinstance(self.selected, tuple) or len(self.selected) > MAX_PORTFOLIO_SIZE:
            raise DiscoveryContractError("portfolio selected set exceeds three candidates")
        if any(not isinstance(item, HypothesisPortfolioItem) for item in self.selected):
            raise DiscoveryContractError("portfolio selected items are invalid")
        if len({item.candidate_id for item in self.selected}) != len(self.selected):
            raise DiscoveryContractError("portfolio selected candidate ids must be unique")
        if not isinstance(self.rejected_candidates, tuple) or any(
            not isinstance(item, CandidateRejection) for item in self.rejected_candidates
        ):
            raise DiscoveryContractError("portfolio rejected candidates are invalid")
        if not isinstance(self.selection_ledger, HypothesisSelectionLedger):
            raise DiscoveryContractError("portfolio selection ledger is invalid")
        candidate_ids = {item.candidate_id for item in self.candidates}
        candidate_ids.update(item.candidate_id for item in self.rejected_candidates)
        ledger_ids = {entry.hypothesis_id for entry in self.selection_ledger.entries}
        if ledger_ids != candidate_ids:
            raise DiscoveryContractError("portfolio ledger does not account for every candidate")
        selected_ids = {item.candidate_id for item in self.selected}
        if not selected_ids.issubset(candidate_ids):
            raise DiscoveryContractError("portfolio selected item is not an accounted candidate")
        if not isinstance(self.budget, int) or isinstance(self.budget, bool) or self.budget < 1:
            raise DiscoveryContractError("portfolio budget must be positive")
        if self.budget_consumed != len(self.selected):
            raise DiscoveryContractError("portfolio budget_consumed does not match selected set")
        if self.remaining_budget != self.budget - self.budget_consumed:
            raise DiscoveryContractError("portfolio remaining_budget does not match budget")
        _text_tuple(self.remaining_prior_ids, "remaining prior ids", unique=True)
        _text_tuple(self.remaining_fact_ids, "remaining fact ids", unique=True)
        _text_tuple(self.coverage_frontier, "portfolio coverage frontier", unique=True)
        if self.status not in {"frozen", "rejected"}:
            raise DiscoveryContractError("invalid portfolio status")
        if self.status == "frozen" and not self.selected:
            raise DiscoveryContractError("frozen portfolio requires a selected candidate")
        if self.status == "rejected" and self.selected:
            raise DiscoveryContractError("rejected portfolio cannot contain selected candidates")
        _version(self.schema_version, "hypothesis portfolio")

    @property
    def selected_hypotheses(self) -> tuple[RiskHypothesis, ...]:
        return tuple(item.hypothesis for item in self.selected)

    @property
    def ordered_hypotheses(self) -> tuple[RiskHypothesis, ...]:
        return self.selected_hypotheses

    @property
    def selected_prior_ids(self) -> tuple[str, ...]:
        return tuple(item.prior_id for item in self.selected)

    @property
    def priorities(self) -> tuple[RiskPriority, ...]:
        return tuple(item.priority for item in self.selected)

    @property
    def frontier(self) -> tuple[str, ...]:
        return self.coverage_frontier

    def decision_for(self, candidate_id: str) -> str:
        for entry in self.selection_ledger.entries:
            if entry.hypothesis_id == candidate_id:
                return entry.decision
        raise KeyError(candidate_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "portfolio_id": self.portfolio_id,
            "request_id": self.request_id,
            "target_id": self.target_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "source_tree_sha256": self.source_tree_sha256,
            "graph_sha256": self.graph_sha256,
            "generator_identity": self.generator_identity.to_dict(),
            "authoritative_output_sha256": self.authoritative_output_sha256,
            "approved_prior_ids": list(self.approved_prior_ids),
            "candidates": [item.to_dict() for item in self.candidates],
            "selected": [item.to_dict() for item in self.selected],
            "rejected_candidates": [item.to_dict() for item in self.rejected_candidates],
            "selection_ledger": self.selection_ledger.to_dict(),
            "budget": self.budget,
            "budget_consumed": self.budget_consumed,
            "remaining_budget": self.remaining_budget,
            "remaining_prior_ids": list(self.remaining_prior_ids),
            "remaining_fact_ids": list(self.remaining_fact_ids),
            "coverage_frontier": list(self.coverage_frontier),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisPortfolio":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis portfolio must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "portfolio_id",
                "request_id",
                "target_id",
                "source_origin",
                "source_commit",
                "source_tree_sha256",
                "graph_sha256",
                "generator_identity",
                "authoritative_output_sha256",
                "approved_prior_ids",
                "candidates",
                "selected",
                "rejected_candidates",
                "selection_ledger",
                "budget",
                "budget_consumed",
                "remaining_budget",
                "remaining_prior_ids",
                "remaining_fact_ids",
                "coverage_frontier",
                "status",
            },
            "hypothesis portfolio",
        )
        try:
            return cls(
                portfolio_id=data["portfolio_id"],
                request_id=data["request_id"],
                target_id=data["target_id"],
                source_origin=data["source_origin"],
                source_commit=data["source_commit"],
                source_tree_sha256=data["source_tree_sha256"],
                graph_sha256=data["graph_sha256"],
                generator_identity=HypothesisGeneratorIdentity.from_dict(
                    data["generator_identity"]
                ),
                authoritative_output_sha256=data["authoritative_output_sha256"],
                approved_prior_ids=tuple(
                    _list_to_tuple(data, "approved_prior_ids", "hypothesis portfolio")
                ),
                candidates=tuple(
                    HypothesisCandidate.from_dict(item)
                    for item in _list_to_tuple(data, "candidates", "hypothesis portfolio")
                ),
                selected=tuple(
                    HypothesisPortfolioItem.from_dict(item)
                    for item in _list_to_tuple(data, "selected", "hypothesis portfolio")
                ),
                rejected_candidates=tuple(
                    CandidateRejection.from_dict(item)
                    for item in _list_to_tuple(
                        {"rejected_candidates": data.get("rejected_candidates", [])},
                        "rejected_candidates",
                        "hypothesis portfolio",
                    )
                ),
                selection_ledger=HypothesisSelectionLedger.from_dict(
                    data["selection_ledger"]
                ),
                budget=data["budget"],
                budget_consumed=data["budget_consumed"],
                remaining_budget=data["remaining_budget"],
                remaining_prior_ids=tuple(
                    _list_to_tuple(data, "remaining_prior_ids", "hypothesis portfolio")
                ),
                remaining_fact_ids=tuple(
                    _list_to_tuple(data, "remaining_fact_ids", "hypothesis portfolio")
                ),
                coverage_frontier=tuple(
                    _list_to_tuple(data, "coverage_frontier", "hypothesis portfolio")
                ),
                status=data.get("status", "frozen"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis portfolio requires {error.args[0]}"
            ) from error


def freeze_hypothesis_portfolio(
    request: HypothesisGenerationRequest,
    response: HypothesisGenerationResponse,
    *,
    registry: tuple[ApprovedPriorDefinition, ...] | None = None,
) -> HypothesisPortfolio:
    """Validate, prioritize, order, and freeze at most three candidates."""

    if not isinstance(request, HypothesisGenerationRequest):
        raise DiscoveryContractError("portfolio freeze request is invalid")
    if not isinstance(response, HypothesisGenerationResponse):
        raise DiscoveryContractError("portfolio freeze response is invalid")
    if response.request_id != request.request_id:
        raise DiscoveryContractError("portfolio response request does not match request")
    if response.target_id != request.target.target_id:
        raise DiscoveryContractError("portfolio response target does not match request")
    if response.graph_sha256 != request.graph_sha256:
        raise DiscoveryContractError("portfolio response graph does not match request")
    selected_registry = registry or approved_m9_prior_registry()
    if len(selected_registry) != 3:
        raise DiscoveryContractError("portfolio registry must contain exactly three priors")
    registry_map = {definition.prior_id: definition for definition in selected_registry}
    if set(registry_map) != set(request.approved_prior_ids):
        raise DiscoveryContractError("portfolio registry does not match request priors")

    parsed_candidates = sorted(response.candidates, key=lambda item: item.candidate_id)
    valid: list[HypothesisCandidate] = []
    rejection_map: dict[str, CandidateRejection] = {
        item.candidate_id: item for item in response.rejected_candidates
    }
    seen_fingerprints: dict[str, str] = {}
    priority_map: dict[str, RiskPriority] = {}
    for candidate in parsed_candidates:
        definition = registry_map.get(candidate.prior_id)
        reasons = list(validate_hypothesis_candidate(candidate, request, definition))
        fingerprint = _candidate_fingerprint(candidate)
        if not reasons and fingerprint in seen_fingerprints:
            reasons.append(
                "duplicate semantic candidate of " + seen_fingerprints[fingerprint]
            )
        if reasons:
            rejection_map[candidate.candidate_id] = CandidateRejection(
                candidate_id=candidate.candidate_id,
                raw_sha256=_digest(candidate.to_dict()),
                prior_id=candidate.prior_id,
                reasons=tuple(dict.fromkeys(reasons)),
            )
            continue
        seen_fingerprints[fingerprint] = candidate.candidate_id
        valid.append(candidate)
        priority_map[candidate.candidate_id] = calculate_risk_priority(
            candidate, request.graph
        )

    ranked = sorted(
        valid,
        key=lambda item: (
            -priority_map[item.candidate_id].score,
            item.prior_id,
            item.candidate_id,
        ),
    )
    selected_candidates = ranked[: min(MAX_PORTFOLIO_SIZE, request.budget)]
    selected_ids = {item.candidate_id for item in selected_candidates}
    selected_items: list[HypothesisPortfolioItem] = []
    for candidate in selected_candidates:
        priority = priority_map[candidate.candidate_id]
        frozen_hypothesis = replace(
            candidate.hypothesis,
            status="frozen",
            priority_id=priority.priority_id,
        )
        selected_items.append(
            HypothesisPortfolioItem(
                candidate_id=candidate.candidate_id,
                prior_id=candidate.prior_id,
                operator_id=candidate.operator_id,
                hypothesis=frozen_hypothesis,
                failure_chain=candidate.failure_chain,
                priority=priority,
            )
        )

    accounted_ids = set(rejection_map) | {candidate.candidate_id for candidate in parsed_candidates}
    ledger = HypothesisSelectionLedger()
    for candidate_id in sorted(accounted_ids):
        candidate = next(
            (item for item in parsed_candidates if item.candidate_id == candidate_id),
            None,
        )
        rejection = rejection_map.get(candidate_id)
        if rejection is not None:
            decision = "rejected"
            score = 0.0
            rationale = "; ".join(rejection.reasons)
            prior_id = rejection.prior_id
        elif candidate_id in selected_ids:
            decision = "selected"
            score = priority_map[candidate_id].score
            rationale = (
                f"Selected after deterministic priority ordering for prior "
                f"{candidate.prior_id}; score is an ordering aid only."
            )
            prior_id = candidate.prior_id
        else:
            decision = "deferred"
            score = priority_map[candidate_id].score
            rationale = (
                "Deferred after the three-candidate portfolio capacity or bounded "
                "budget was reached."
            )
            prior_id = candidate.prior_id
        assert decision in _DECISIONS
        ledger = ledger.append(
            hypothesis_id=candidate_id,
            decision=decision,
            priority_score=score,
            rationale=rationale,
            prior_id=prior_id,
        )

    selected_prior_ids = {item.prior_id for item in selected_items}
    remaining_prior_ids = tuple(
        sorted(prior_id for prior_id in request.approved_prior_ids if prior_id not in selected_prior_ids)
    )
    covered_fact_ids = {
        fact_id
        for item in selected_items
        for fact_id in item.hypothesis.supporting_fact_ids
    }
    remaining_fact_ids = tuple(
        sorted(
            fact.fact_id
            for fact in request.graph.facts
            if fact.fact_id not in covered_fact_ids
        )
    )
    frontier = tuple(
        [*(f"prior:{prior_id}" for prior_id in remaining_prior_ids), *(f"fact:{fact_id}" for fact_id in remaining_fact_ids)]
    )
    rejected = tuple(rejection_map[key] for key in sorted(rejection_map))
    digest_input = {
        "request": request.to_dict(),
        "response": response.to_dict(),
        "selected": [item.to_dict() for item in selected_items],
        "rejected": [item.to_dict() for item in rejected],
        "ledger": ledger.to_dict(),
        "frontier": frontier,
    }
    portfolio_id = "portfolio-" + _digest(digest_input)[:16]
    return HypothesisPortfolio(
        portfolio_id=portfolio_id,
        request_id=request.request_id,
        target_id=request.target.target_id,
        source_origin=request.target.source_origin,
        source_commit=request.target.source_commit,
        source_tree_sha256=request.graph.source_tree_sha256 or "",
        graph_sha256=request.graph_sha256,
        generator_identity=response.generator_identity,
        authoritative_output_sha256=response.authoritative_output_sha256,
        approved_prior_ids=request.approved_prior_ids,
        candidates=tuple(parsed_candidates),
        selected=tuple(selected_items),
        rejected_candidates=rejected,
        selection_ledger=ledger,
        budget=request.budget,
        budget_consumed=len(selected_items),
        remaining_budget=request.budget - len(selected_items),
        remaining_prior_ids=remaining_prior_ids,
        remaining_fact_ids=remaining_fact_ids,
        coverage_frontier=frontier,
        status="frozen" if selected_items else "rejected",
    )


freeze_portfolio = freeze_hypothesis_portfolio


__all__ = [
    "ApprovedPriorDefinition",
    "CandidateRejection",
    "GENERATOR_ROLE_ID",
    "HypothesisCandidate",
    "HypothesisGenerationRequest",
    "HypothesisGenerationResponse",
    "HypothesisGeneratorBackend",
    "HypothesisGeneratorIdentity",
    "HypothesisPortfolio",
    "HypothesisPortfolioItem",
    "LIFETIME_OWNERSHIP_OPERATOR_ID",
    "LIFETIME_OWNERSHIP_PRIOR_ID",
    "MAX_PORTFOLIO_SIZE",
    "OUTCOME_LEAKAGE_TERMS",
    "PORTFOLIO_SCHEMA_VERSION",
    "approved_m9_prior_registry",
    "approved_prior_registry",
    "calculate_risk_priority",
    "freeze_hypothesis_portfolio",
    "freeze_portfolio",
    "generate_hypotheses",
    "generate_hypothesis_response",
    "validate_candidate",
    "validate_hypothesis_candidate",
]
