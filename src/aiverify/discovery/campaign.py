"""Side-effect-free orchestration above the Run Spec boundary.

The campaign layer owns discovery state, not Android execution.  It can bind a
target to context, freeze and admit one hypothesis, compile a validated Run
Spec, and reduce an immutable attempt receipt into a new risk-map snapshot.
Every operation returns a new value; no build, device, or source-tree action is
performed here.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field as dataclass_field, replace
from pathlib import Path
from typing import Any, Mapping

from aiverify.discovery.contracts import (
    AdmissionResult,
    AttackOperator,
    ContractDrift,
    DiscoveryCampaign,
    Finding,
    ProjectRiskMap,
    QualityContract,
    ResidualRisk,
    RiskHypothesis,
    RiskPrior,
    admit_attack_plan,
)
from aiverify.discovery.models import (
    ChangeTarget,
    DiscoveryContractError,
    DiscoveryTarget,
    ProjectTarget,
    QualityContextGraph,
)
from aiverify.discovery.risk import (
    BehaviorDelta,
    RiskPriority,
    RiskDerivationStrategy,
    derive_with_strategy,
    make_latency_operator,
    make_temporal_prior,
    make_temporal_strategy,
)
from aiverify.runner.run_spec import (
    LiveValidationSpec,
    RunSpec,
    ScenarioSpec,
    parse_run_spec,
)


_EMPTY_DIGEST = "0" * 64
_DECISIONS = frozenset({"considered", "selected", "deferred", "rejected"})
_EXPANSION_STATUSES = frozenset({"complete", "partial", "rejected"})
_ATTEMPT_OUTCOMES = frozenset(
    {"supported", "rejected", "inconclusive", "non_accountable"}
)


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    return value


def _list_to_tuple(data: Mapping[str, Any], field: str) -> tuple[Any, ...]:
    value = data[field]
    if not isinstance(value, list):
        raise DiscoveryContractError(f"{field} must be an array")
    return tuple(value)


def _digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _stable_id(*parts: str) -> str:
    return _digest(list(parts))[:16]


@dataclass(frozen=True)
class ContextExpansionRequest:
    """A bounded request for facts or probes needed by campaign discovery."""

    request_id: str
    campaign_id: str
    target_id: str
    required_predicates: tuple[str, ...]
    probe_refs: tuple[str, ...]
    budget: int
    unresolved_questions: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("request_id", "campaign_id", "target_id"):
            _required_text(getattr(self, field), field)
        _text_tuple(self.required_predicates, "required_predicates", allow_empty=False)
        _text_tuple(self.probe_refs, "probe_refs")
        _text_tuple(self.unresolved_questions, "unresolved_questions")
        if not isinstance(self.budget, int) or isinstance(self.budget, bool) or self.budget < 1:
            raise DiscoveryContractError("context expansion budget must be a positive integer")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported context expansion request schema_version")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "campaign_id": self.campaign_id,
            "target_id": self.target_id,
            "required_predicates": list(self.required_predicates),
            "probe_refs": list(self.probe_refs),
            "budget": self.budget,
            "unresolved_questions": list(self.unresolved_questions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextExpansionRequest":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context expansion request must be an object")
        allowed = {
            "schema_version",
            "request_id",
            "campaign_id",
            "target_id",
            "required_predicates",
            "probe_refs",
            "budget",
            "unresolved_questions",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown context expansion request field(s): " + ", ".join(unknown)
            )
        try:
            return cls(
                request_id=data["request_id"],
                campaign_id=data["campaign_id"],
                target_id=data["target_id"],
                required_predicates=tuple(_list_to_tuple(data, "required_predicates")),
                probe_refs=tuple(_list_to_tuple(data, "probe_refs")),
                budget=data["budget"],
                unresolved_questions=(
                    tuple(_list_to_tuple(data, "unresolved_questions"))
                    if "unresolved_questions" in data
                    else ()
                ),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"context expansion request requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class ContextExpansionResult:
    """The immutable result of one bounded context expansion request."""

    request_id: str
    target_id: str
    graph: QualityContextGraph
    resolved_fact_ids: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    probe_refs: tuple[str, ...] = ()
    budget_used: int = 0
    status: str = "complete"
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.request_id, "request_id")
        _required_text(self.target_id, "target_id")
        if not isinstance(self.graph, QualityContextGraph):
            raise DiscoveryContractError("context expansion graph must be a QualityContextGraph")
        if self.graph.target_id != self.target_id:
            raise DiscoveryContractError("context expansion graph target does not match result")
        _text_tuple(self.resolved_fact_ids, "resolved_fact_ids")
        _text_tuple(self.unresolved_questions, "unresolved_questions")
        _text_tuple(self.probe_refs, "probe_refs")
        known_ids = {fact.fact_id for fact in self.graph.facts}
        if not set(self.resolved_fact_ids).issubset(known_ids):
            raise DiscoveryContractError("context expansion references missing fact")
        if (
            not isinstance(self.budget_used, int)
            or isinstance(self.budget_used, bool)
            or self.budget_used < 0
        ):
            raise DiscoveryContractError("context expansion budget_used must be non-negative")
        if self.status not in _EXPANSION_STATUSES:
            raise DiscoveryContractError("invalid context expansion status")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported context expansion result schema_version")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "target_id": self.target_id,
            "graph": self.graph.to_dict(),
            "resolved_fact_ids": list(self.resolved_fact_ids),
            "unresolved_questions": list(self.unresolved_questions),
            "probe_refs": list(self.probe_refs),
            "budget_used": self.budget_used,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextExpansionResult":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context expansion result must be an object")
        allowed = {
            "schema_version",
            "request_id",
            "target_id",
            "graph",
            "resolved_fact_ids",
            "unresolved_questions",
            "probe_refs",
            "budget_used",
            "status",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown context expansion result field(s): " + ", ".join(unknown)
            )
        try:
            return cls(
                request_id=data["request_id"],
                target_id=data["target_id"],
                graph=QualityContextGraph.from_dict(data["graph"]),
                resolved_fact_ids=(
                    tuple(_list_to_tuple(data, "resolved_fact_ids"))
                    if "resolved_fact_ids" in data
                    else ()
                ),
                unresolved_questions=(
                    tuple(_list_to_tuple(data, "unresolved_questions"))
                    if "unresolved_questions" in data
                    else ()
                ),
                probe_refs=(
                    tuple(_list_to_tuple(data, "probe_refs"))
                    if "probe_refs" in data
                    else ()
                ),
                budget_used=data.get("budget_used", 0),
                status=data.get("status", "complete"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"context expansion result requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class HypothesisSelectionEntry:
    """One append-only selection decision in the campaign ledger."""

    entry_id: str
    sequence: int
    hypothesis_id: str
    decision: str
    priority_score: float
    rationale: str
    previous_digest: str
    entry_digest: str
    prior_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in (
            "entry_id",
            "hypothesis_id",
            "rationale",
            "previous_digest",
            "entry_digest",
        ):
            _required_text(getattr(self, field), field)
        if self.prior_id is not None:
            _required_text(self.prior_id, "prior_id")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise DiscoveryContractError("selection sequence must be a positive integer")
        if self.decision not in _DECISIONS:
            raise DiscoveryContractError("invalid hypothesis selection decision")
        if (
            not isinstance(self.priority_score, (int, float))
            or isinstance(self.priority_score, bool)
            or not 0 <= self.priority_score <= 1
        ):
            raise DiscoveryContractError("selection priority_score must be between 0 and 1")
        if not _is_digest(self.previous_digest) or not _is_digest(self.entry_digest):
            raise DiscoveryContractError("selection ledger digests must be lowercase SHA-256")
        expected = _selection_digest(
            self.sequence,
            self.hypothesis_id,
            self.decision,
            self.priority_score,
            self.rationale,
            self.previous_digest,
            self.prior_id,
        )
        if self.entry_digest != expected:
            raise DiscoveryContractError("selection entry digest does not match content")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported selection entry schema_version")

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        hypothesis_id: str,
        decision: str,
        priority_score: float,
        rationale: str,
        previous_digest: str,
        prior_id: str | None = None,
    ) -> "HypothesisSelectionEntry":
        digest = _selection_digest(
            sequence,
            hypothesis_id,
            decision,
            priority_score,
            rationale,
            previous_digest,
            prior_id,
        )
        return cls(
            entry_id="selection-" + digest[:16],
            sequence=sequence,
            hypothesis_id=hypothesis_id,
            decision=decision,
            priority_score=priority_score,
            rationale=rationale,
            previous_digest=previous_digest,
            entry_digest=digest,
            prior_id=prior_id,
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "sequence": self.sequence,
            "hypothesis_id": self.hypothesis_id,
            "decision": self.decision,
            "priority_score": self.priority_score,
            "rationale": self.rationale,
            "previous_digest": self.previous_digest,
            "entry_digest": self.entry_digest,
        }
        if self.prior_id is not None:
            result["prior_id"] = self.prior_id
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisSelectionEntry":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis selection entry must be an object")
        allowed = {
            "schema_version",
            "entry_id",
            "sequence",
            "hypothesis_id",
            "decision",
            "priority_score",
            "rationale",
            "previous_digest",
            "entry_digest",
            "prior_id",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown hypothesis selection field(s): " + ", ".join(unknown)
            )
        try:
            return cls(
                entry_id=data["entry_id"],
                sequence=data["sequence"],
                hypothesis_id=data["hypothesis_id"],
                decision=data["decision"],
                priority_score=data["priority_score"],
                rationale=data["rationale"],
                previous_digest=data["previous_digest"],
                entry_digest=data["entry_digest"],
                prior_id=data.get("prior_id"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis selection entry requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class HypothesisSelectionLedger:
    """A deterministic hash-chained ledger for considered/selected risks."""

    entries: tuple[HypothesisSelectionEntry, ...] = ()
    head_digest: str = _EMPTY_DIGEST
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple) or any(
            not isinstance(entry, HypothesisSelectionEntry) for entry in self.entries
        ):
            raise DiscoveryContractError("selection ledger entries are invalid")
        previous = _EMPTY_DIGEST
        for sequence, entry in enumerate(self.entries, start=1):
            if entry.sequence != sequence or entry.previous_digest != previous:
                raise DiscoveryContractError("selection ledger chain is not contiguous")
            previous = entry.entry_digest
        if not _is_digest(self.head_digest):
            raise DiscoveryContractError("selection ledger head_digest is invalid")
        if self.head_digest != previous:
            raise DiscoveryContractError("selection ledger head_digest does not match entries")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported selection ledger schema_version")

    def append(
        self,
        *,
        hypothesis_id: str,
        decision: str,
        priority_score: float,
        rationale: str,
        prior_id: str | None = None,
    ) -> "HypothesisSelectionLedger":
        entry = HypothesisSelectionEntry.create(
            sequence=len(self.entries) + 1,
            hypothesis_id=hypothesis_id,
            decision=decision,
            priority_score=priority_score,
            rationale=rationale,
            previous_digest=self.head_digest,
            prior_id=prior_id,
        )
        return HypothesisSelectionLedger(
            entries=(*self.entries, entry),
            head_digest=entry.entry_digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries": [entry.to_dict() for entry in self.entries],
            "head_digest": self.head_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "HypothesisSelectionLedger":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("hypothesis selection ledger must be an object")
        allowed = {"schema_version", "entries", "head_digest"}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown hypothesis selection ledger field(s): " + ", ".join(unknown)
            )
        try:
            raw_entries = data.get("entries", [])
            if not isinstance(raw_entries, list):
                raise DiscoveryContractError("selection ledger entries must be an array")
            return cls(
                entries=tuple(HypothesisSelectionEntry.from_dict(item) for item in raw_entries),
                head_digest=data.get("head_digest", _EMPTY_DIGEST),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"hypothesis selection ledger requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class AttemptEvidence:
    """An immutable terminal attempt receipt consumed by the evidence reducer."""

    evidence_id: str
    target_id: str
    hypothesis_id: str
    attempt_ref: str
    execution_record_ref: str
    outcome: str
    evidence_refs: tuple[str, ...]
    claim_boundary: str
    rationale: str
    accountable: bool
    execution_identity_sha256: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in (
            "evidence_id",
            "target_id",
            "hypothesis_id",
            "attempt_ref",
            "execution_record_ref",
            "claim_boundary",
            "rationale",
        ):
            _required_text(getattr(self, field), field)
        if self.outcome not in _ATTEMPT_OUTCOMES:
            raise DiscoveryContractError("invalid attempt evidence outcome")
        _text_tuple(self.evidence_refs, "evidence_refs")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise DiscoveryContractError("attempt evidence references must be unique")
        if not isinstance(self.accountable, bool):
            raise DiscoveryContractError("attempt evidence accountable must be boolean")
        if self.accountable != (self.outcome != "non_accountable"):
            raise DiscoveryContractError("accountability contradicts attempt outcome")
        if self.outcome != "non_accountable" and not self.evidence_refs:
            raise DiscoveryContractError("accountable attempt evidence requires evidence_refs")
        if self.outcome != "non_accountable" and self.execution_identity_sha256 is None:
            raise DiscoveryContractError(
                "accountable attempt evidence requires execution identity digest"
            )
        if self.execution_identity_sha256 is not None and not _is_digest(
            self.execution_identity_sha256
        ):
            raise DiscoveryContractError("execution identity digest is invalid")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported attempt evidence schema_version")

    @classmethod
    def from_execution(
        cls,
        *,
        target_id: str,
        hypothesis_id: str,
        attempt_ref: str,
        execution_record_ref: str,
        execution_record: Mapping[str, Any],
        verdict: Mapping[str, Any],
        claim_boundary: str,
        rationale: str,
        execution_identity_sha256: str | None = None,
    ) -> "AttemptEvidence":
        """Convert authoritative runner artifacts without inventing an outcome."""

        from aiverify.agent.oracle import validate_verdict
        from aiverify.runner.execution_record import validate_execution_record

        validate_execution_record(dict(execution_record))
        validate_verdict(dict(verdict))
        execution = execution_record.get("execution")
        accountable = bool(
            execution_record.get("lifecycle_state") == "completed"
            and isinstance(execution, Mapping)
            and execution.get("status") == "completed"
            and execution.get("accounting_eligible") is True
        )
        outcome_map = {"fail": "supported", "pass": "rejected", "inconclusive": "inconclusive"}
        outcome = outcome_map[verdict["outcome"]] if accountable else "non_accountable"
        raw_evidence = verdict.get("evidence", [])
        evidence_refs = tuple(
            item["ref"]
            for item in raw_evidence
            if (
                isinstance(item, Mapping)
                and isinstance(item.get("ref"), str)
                and item["ref"].strip()
            )
        )
        if accountable and not evidence_refs:
            raise DiscoveryContractError("accountable verdict has no evidence references")
        evidence_id = "evidence-" + _stable_id(
            attempt_ref, execution_record_ref, verdict["verdict_id"]
        )
        if accountable and execution_identity_sha256 is None:
            raw_provenance = (
                execution_record.get("evidence_refs", {})
                if isinstance(execution_record, Mapping)
                else {}
            )
            provenance = (
                raw_provenance.get("execution_provenance")
                if isinstance(raw_provenance, Mapping)
                else None
            )
            if isinstance(provenance, Mapping):
                execution_identity_sha256 = provenance.get("sha256")
        return cls(
            evidence_id=evidence_id,
            target_id=target_id,
            hypothesis_id=hypothesis_id,
            attempt_ref=attempt_ref,
            execution_record_ref=execution_record_ref,
            outcome=outcome,
            evidence_refs=evidence_refs,
            claim_boundary=claim_boundary,
            rationale=rationale,
            accountable=accountable,
            execution_identity_sha256=execution_identity_sha256,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "evidence_id": self.evidence_id,
            "target_id": self.target_id,
            "hypothesis_id": self.hypothesis_id,
            "attempt_ref": self.attempt_ref,
            "execution_record_ref": self.execution_record_ref,
            "outcome": self.outcome,
            "evidence_refs": list(self.evidence_refs),
            "claim_boundary": self.claim_boundary,
            "rationale": self.rationale,
            "accountable": self.accountable,
        }
        if self.execution_identity_sha256 is not None:
            result["execution_identity_sha256"] = self.execution_identity_sha256
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttemptEvidence":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attempt evidence must be an object")
        allowed = {
            "schema_version",
            "evidence_id",
            "target_id",
            "hypothesis_id",
            "attempt_ref",
            "execution_record_ref",
            "outcome",
            "evidence_refs",
            "claim_boundary",
            "rationale",
            "accountable",
            "execution_identity_sha256",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown attempt evidence field(s): " + ", ".join(unknown)
            )
        try:
            return cls(
                evidence_id=data["evidence_id"],
                target_id=data["target_id"],
                hypothesis_id=data["hypothesis_id"],
                attempt_ref=data["attempt_ref"],
                execution_record_ref=data["execution_record_ref"],
                outcome=data["outcome"],
                evidence_refs=tuple(_list_to_tuple(data, "evidence_refs")),
                claim_boundary=data["claim_boundary"],
                rationale=data["rationale"],
                accountable=data["accountable"],
                execution_identity_sha256=data.get("execution_identity_sha256"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"attempt evidence requires {error.args[0]}") from error


@dataclass(frozen=True)
class EvidenceReduction:
    """The append-only result of reducing one attempt receipt."""

    risk_map: ProjectRiskMap
    finding: Finding | None
    residual_risk: ResidualRisk | None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.risk_map, ProjectRiskMap):
            raise DiscoveryContractError("evidence reduction requires a ProjectRiskMap")
        if (self.finding is None) == (self.residual_risk is None):
            raise DiscoveryContractError("evidence reduction must produce exactly one outcome")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported evidence reduction schema_version")


@dataclass(frozen=True)
class CampaignAdmission:
    """A campaign snapshot after a side-effect-free plan admission."""

    package: "DiscoveryCampaignPackage"
    admission: AdmissionResult

    def __post_init__(self) -> None:
        if not isinstance(self.package, DiscoveryCampaignPackage):
            raise DiscoveryContractError("campaign admission requires a campaign package")
        if not isinstance(self.admission, AdmissionResult):
            raise DiscoveryContractError("campaign admission requires an AdmissionResult")


@dataclass(frozen=True)
class CompiledExperiment:
    """A validated Run Spec plus the immutable campaign snapshot that emitted it."""

    package: "DiscoveryCampaignPackage"
    experiment_ref: str
    plan_id: str
    run_spec: RunSpec
    admission: AdmissionResult
    input_digest: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.package, DiscoveryCampaignPackage):
            raise DiscoveryContractError("compiled experiment requires a campaign package")
        _required_text(self.experiment_ref, "experiment_ref")
        _required_text(self.plan_id, "plan_id")
        if not isinstance(self.run_spec, RunSpec):
            raise DiscoveryContractError("compiled experiment requires a RunSpec")
        if not isinstance(self.admission, AdmissionResult) or not self.admission.admitted:
            raise DiscoveryContractError("compiled experiment requires admitted input")
        if not _is_digest(self.input_digest):
            raise DiscoveryContractError("compiled experiment input_digest is invalid")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported compiled experiment schema_version")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_ref": self.experiment_ref,
            "plan_id": self.plan_id,
            "admission": self.admission.to_dict(),
            "input_digest": self.input_digest,
            "status": "validated",
        }


@dataclass(frozen=True)
class DiscoveryCampaignPackage:
    """Serializable campaign envelope used for deterministic resume."""

    campaign: DiscoveryCampaign
    selection_ledger: HypothesisSelectionLedger = dataclass_field(
        default_factory=HypothesisSelectionLedger
    )
    context_request: ContextExpansionRequest | None = None
    context_result: ContextExpansionResult | None = None
    behavior_delta: BehaviorDelta | None = None
    risk_priority: RiskPriority | None = None
    attempts: tuple[AttemptEvidence, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.campaign, DiscoveryCampaign):
            raise DiscoveryContractError("campaign package requires DiscoveryCampaign")
        if not isinstance(self.selection_ledger, HypothesisSelectionLedger):
            raise DiscoveryContractError("campaign package selection ledger is invalid")
        if self.context_request is not None and not isinstance(
            self.context_request, ContextExpansionRequest
        ):
            raise DiscoveryContractError("campaign package context request is invalid")
        if self.context_request is not None and (
            self.context_request.campaign_id != self.campaign.campaign_id
            or self.context_request.target_id != self.campaign.target.target_id
        ):
            raise DiscoveryContractError("campaign package context request target mismatch")
        if self.context_result is not None and not isinstance(
            self.context_result, ContextExpansionResult
        ):
            raise DiscoveryContractError("campaign package context result is invalid")
        if (
            self.context_result is not None
            and self.context_result.target_id != self.campaign.target.target_id
        ):
            raise DiscoveryContractError("campaign package context result target mismatch")
        if (
            self.context_result is not None
            and self.context_result.graph != self.campaign.context_graph
        ):
            raise DiscoveryContractError("campaign package context graph is not current")
        if self.behavior_delta is not None:
            if not isinstance(self.behavior_delta, BehaviorDelta):
                raise DiscoveryContractError("campaign package behavior delta is invalid")
            if self.behavior_delta.target_id != self.campaign.target.target_id:
                raise DiscoveryContractError("campaign package behavior delta target mismatch")
        if self.risk_priority is not None and not isinstance(self.risk_priority, RiskPriority):
            raise DiscoveryContractError("campaign package risk priority is invalid")
        if self.risk_priority is not None and self.campaign.hypotheses:
            priority_id = self.campaign.hypotheses[0].priority_id
            if priority_id is not None and priority_id != self.risk_priority.priority_id:
                raise DiscoveryContractError("campaign package priority does not match hypothesis")
        if not isinstance(self.attempts, tuple) or any(
            not isinstance(attempt, AttemptEvidence) for attempt in self.attempts
        ):
            raise DiscoveryContractError("campaign package attempts are invalid")
        if any(attempt.target_id != self.campaign.target.target_id for attempt in self.attempts):
            raise DiscoveryContractError("campaign package attempt target mismatch")
        hypothesis_ids = {hypothesis.hypothesis_id for hypothesis in self.campaign.hypotheses}
        if any(attempt.hypothesis_id not in hypothesis_ids for attempt in self.attempts):
            raise DiscoveryContractError("campaign package attempt references missing hypothesis")
        if len({attempt.evidence_id for attempt in self.attempts}) != len(self.attempts):
            raise DiscoveryContractError("campaign package attempt evidence ids must be unique")
        if any(
            entry.hypothesis_id not in hypothesis_ids
            for entry in self.selection_ledger.entries
        ):
            raise DiscoveryContractError("campaign package selection references missing hypothesis")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported campaign package schema_version")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "campaign": self.campaign.to_dict(),
            "selection_ledger": self.selection_ledger.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
        }
        if self.context_request is not None:
            result["context_request"] = self.context_request.to_dict()
        if self.context_result is not None:
            result["context_result"] = self.context_result.to_dict()
        if self.behavior_delta is not None:
            result["behavior_delta"] = self.behavior_delta.to_dict()
        if self.risk_priority is not None:
            result["risk_priority"] = self.risk_priority.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DiscoveryCampaignPackage":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("campaign package must be an object")
        allowed = {
            "schema_version",
            "campaign",
            "selection_ledger",
            "context_request",
            "context_result",
            "behavior_delta",
            "risk_priority",
            "attempts",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown campaign package field(s): " + ", ".join(unknown)
            )
        try:
            raw_attempts = data.get("attempts", [])
            if not isinstance(raw_attempts, list):
                raise DiscoveryContractError("campaign package attempts must be an array")
            return cls(
                campaign=DiscoveryCampaign.from_dict(data["campaign"]),
                selection_ledger=HypothesisSelectionLedger.from_dict(
                    data.get("selection_ledger", {})
                ),
                context_request=(
                    ContextExpansionRequest.from_dict(data["context_request"])
                    if data.get("context_request") is not None
                    else None
                ),
                context_result=(
                    ContextExpansionResult.from_dict(data["context_result"])
                    if data.get("context_result") is not None
                    else None
                ),
                behavior_delta=(
                    BehaviorDelta.from_dict(data["behavior_delta"])
                    if data.get("behavior_delta") is not None
                    else None
                ),
                risk_priority=(
                    RiskPriority.from_dict(data["risk_priority"])
                    if data.get("risk_priority") is not None
                    else None
                ),
                attempts=tuple(AttemptEvidence.from_dict(item) for item in raw_attempts),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"campaign package requires {error.args[0]}") from error


def create_campaign(
    campaign_id: str,
    target: DiscoveryTarget,
    graph: QualityContextGraph,
    *,
    expansion_request: ContextExpansionRequest | None = None,
) -> DiscoveryCampaignPackage:
    """Create a target-bound campaign before context or hypothesis side effects."""

    _validate_target_graph(target, graph)
    if expansion_request is not None:
        if expansion_request.campaign_id != campaign_id:
            raise DiscoveryContractError("context expansion request campaign mismatch")
        if expansion_request.target_id != target.target_id:
            raise DiscoveryContractError("context expansion request target mismatch")
    campaign = DiscoveryCampaign(
        campaign_id=campaign_id,
        target=target,
        context_graph=graph,
        status="created",
    )
    return DiscoveryCampaignPackage(
        campaign=campaign,
        context_request=expansion_request,
    )


def apply_context_expansion(
    package: DiscoveryCampaignPackage,
    result: ContextExpansionResult,
) -> DiscoveryCampaignPackage:
    """Attach a context result and transition the campaign to context-ready."""

    if package.campaign.status not in {"created", "draft", "context-ready"}:
        raise DiscoveryContractError("context expansion is closed after hypothesis freeze")
    request = package.context_request
    if request is None:
        raise DiscoveryContractError("context expansion requires a recorded request")
    if (
        result.request_id != request.request_id
        or result.target_id != package.campaign.target.target_id
    ):
        raise DiscoveryContractError("context expansion result does not match request")
    if result.status == "rejected":
        raise DiscoveryContractError("rejected context expansion cannot become campaign state")
    if result.budget_used > request.budget:
        raise DiscoveryContractError("context expansion exceeded its bounded budget")
    campaign = replace(
        package.campaign,
        context_graph=result.graph,
        status="context-ready",
    )
    return replace(package, campaign=campaign, context_result=result)


def seed_change_campaign(
    campaign_id: str,
    target: ChangeTarget,
    graph: QualityContextGraph,
    *,
    behavior_delta: BehaviorDelta,
    contract_drift: ContractDrift,
    context_request: ContextExpansionRequest | None = None,
    context_result: ContextExpansionResult | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
    strategy: RiskDerivationStrategy | None = None,
    derivation_strategy: RiskDerivationStrategy | None = None,
) -> DiscoveryCampaignPackage:
    """Seed ChangeTarget through the shared derivation and campaign seam."""

    return _seed_campaign(
        campaign_id,
        target,
        graph,
        mode="change",
        behavior_delta=behavior_delta,
        contract_drift=contract_drift,
        context_request=context_request,
        context_result=context_result,
        prior=prior,
        operator=operator,
        strategy=strategy,
        derivation_strategy=derivation_strategy,
    )


def seed_project_campaign(
    campaign_id: str,
    target: ProjectTarget,
    graph: QualityContextGraph,
    *,
    context_request: ContextExpansionRequest | None = None,
    context_result: ContextExpansionResult | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
    strategy: RiskDerivationStrategy | None = None,
    derivation_strategy: RiskDerivationStrategy | None = None,
) -> DiscoveryCampaignPackage:
    """Seed ProjectTarget from critical context without inventing a diff."""

    return _seed_campaign(
        campaign_id,
        target,
        graph,
        mode="project",
        context_request=context_request,
        context_result=context_result,
        prior=prior,
        operator=operator,
        strategy=strategy,
        derivation_strategy=derivation_strategy,
    )


def seed_change_target(*args: Any, **kwargs: Any) -> DiscoveryCampaignPackage:
    """Compatibility alias for the ChangeTarget seed adapter."""

    return seed_change_campaign(*args, **kwargs)


def seed_project_target(*args: Any, **kwargs: Any) -> DiscoveryCampaignPackage:
    """Compatibility alias for the ProjectTarget seed adapter."""

    return seed_project_campaign(*args, **kwargs)


def freeze_campaign_hypothesis(
    package: DiscoveryCampaignPackage,
    *,
    behavior_delta: BehaviorDelta | None = None,
    contract_drift: ContractDrift | None = None,
    strategy: RiskDerivationStrategy | None = None,
    derivation_strategy: RiskDerivationStrategy | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
) -> DiscoveryCampaignPackage:
    """Derive a frozen hypothesis from a context-ready campaign snapshot."""

    if package.campaign.status not in {"context-ready", "created", "draft"}:
        raise DiscoveryContractError("campaign hypothesis is already frozen or concluded")
    target = package.campaign.target
    if isinstance(target, ChangeTarget):
        if behavior_delta is None or contract_drift is None:
            raise DiscoveryContractError(
                "ChangeTarget freeze requires BehaviorDelta and ContractDrift"
            )
        return seed_change_campaign(
            package.campaign.campaign_id,
            target,
            package.campaign.context_graph,
            behavior_delta=behavior_delta,
            contract_drift=contract_drift,
            context_request=package.context_request,
            context_result=package.context_result,
            prior=prior,
            operator=operator,
            strategy=strategy,
            derivation_strategy=derivation_strategy,
        )
    if behavior_delta is not None or contract_drift is not None:
        raise DiscoveryContractError("ProjectTarget freeze does not consume a diff")
    return seed_project_campaign(
        package.campaign.campaign_id,
        target,
        package.campaign.context_graph,
        context_request=package.context_request,
        context_result=package.context_result,
        prior=prior,
        operator=operator,
        strategy=strategy,
        derivation_strategy=derivation_strategy,
    )


def admit_campaign_plan(package: DiscoveryCampaignPackage) -> CampaignAdmission:
    """Admit exactly the frozen plan after all campaign relationships validate."""

    if package.campaign.status != "hypothesis-frozen":
        raise DiscoveryContractError("campaign must be hypothesis-frozen before admission")
    if len(package.campaign.hypotheses) != 1 or len(package.campaign.attack_plans) != 1:
        raise DiscoveryContractError("bounded campaign admission requires one hypothesis and plan")
    hypothesis = package.campaign.hypotheses[0]
    plan = package.campaign.attack_plans[0]
    plan_for_validation = (
        replace(plan, status="frozen") if plan.status == "admitted" else plan
    )
    admission = admit_attack_plan(
        plan_for_validation,
        hypothesis,
        package.campaign.context_graph,
    )
    if not admission.admitted:
        return CampaignAdmission(package=package, admission=admission)
    admitted_plan = replace(plan, status="admitted")
    campaign = replace(
        package.campaign,
        attack_plans=(admitted_plan,),
        status="plan-admitted",
    )
    return CampaignAdmission(
        package=replace(package, campaign=campaign),
        admission=admission,
    )


def compile_attack_plan_to_run_spec(
    package: DiscoveryCampaignPackage,
    *,
    host_project: str | Path,
    apk_glob: str,
    package_name: str,
    activity: str | None,
    scenario: ScenarioSpec,
    diff: str | Path | None = None,
    spec: str | Path | None = None,
    live_validation: LiveValidationSpec | None = None,
) -> CompiledExperiment:
    """Compile a validated Run Spec only after side-effect-free admission."""

    if package.campaign.status != "plan-admitted":
        raise DiscoveryContractError("Run Spec compilation requires plan-admitted campaign")
    if len(package.campaign.hypotheses) != 1 or len(package.campaign.attack_plans) != 1:
        raise DiscoveryContractError("bounded compiler requires one hypothesis and plan")
    plan = package.campaign.attack_plans[0]
    hypothesis = package.campaign.hypotheses[0]
    plan_for_validation = (
        replace(plan, status="frozen") if plan.status == "admitted" else plan
    )
    admission = admit_attack_plan(
        plan_for_validation,
        hypothesis,
        package.campaign.context_graph,
    )
    if not admission.admitted:
        raise DiscoveryContractError(
            "cannot compile a rejected attack plan: " + "; ".join(admission.errors)
        )
    if not isinstance(scenario, ScenarioSpec):
        raise DiscoveryContractError("compiler requires a ScenarioSpec")
    execution_scenario = _discovery_scenario(scenario)
    run_spec = parse_run_spec(
        _run_spec_mapping(
            host_project=host_project,
            apk_glob=apk_glob,
            package_name=package_name,
            activity=activity,
            scenario=execution_scenario,
            diff=diff,
            spec=spec,
            live_validation=live_validation,
        ),
        base_dir=Path.cwd(),
    )
    experiment_ref = "experiment-" + _stable_id(
        package.campaign.campaign_id,
        plan.plan_id,
        scenario.id,
    )
    digest = _digest(
        {
            "campaign": package.campaign.to_dict(),
            "plan": plan.to_dict(),
            "hypothesis": hypothesis.to_dict(),
            "scenario": _scenario_mapping(execution_scenario),
        }
    )
    campaign = replace(
        package.campaign,
        experiment_refs=(*package.campaign.experiment_refs, experiment_ref),
        status="executing",
    )
    updated_package = replace(package, campaign=campaign)
    return CompiledExperiment(
        package=updated_package,
        experiment_ref=experiment_ref,
        plan_id=plan.plan_id,
        run_spec=run_spec,
        admission=admission,
        input_digest=digest,
    )


def compile_attack_plan(*args: Any, **kwargs: Any) -> CompiledExperiment:
    """Short alias for the Run Spec compiler."""

    return compile_attack_plan_to_run_spec(*args, **kwargs)


def reduce_attempt_evidence(
    package: DiscoveryCampaignPackage,
    evidence: AttemptEvidence,
    *,
    hypothesis: RiskHypothesis | None = None,
) -> tuple[DiscoveryCampaignPackage, EvidenceReduction]:
    """Append one accountable or non-accountable attempt to the risk map."""

    if evidence.target_id != package.campaign.target.target_id:
        raise DiscoveryContractError("attempt evidence target does not match campaign")
    if any(item.evidence_id == evidence.evidence_id for item in package.attempts):
        raise DiscoveryContractError("attempt evidence has already been reduced")
    selected = hypothesis or _single_hypothesis(package.campaign)
    if selected.target_id != evidence.target_id or selected.hypothesis_id != evidence.hypothesis_id:
        raise DiscoveryContractError("attempt evidence hypothesis does not match campaign")
    current_map = package.campaign.project_risk_map or empty_risk_map(evidence.target_id)
    reduction = _reduce_to_map(current_map, evidence, selected)
    if reduction.finding is not None:
        campaign = replace(
            package.campaign,
            findings=(*package.campaign.findings, reduction.finding),
            project_risk_map=reduction.risk_map,
            status="concluded",
        )
    else:
        campaign = replace(
            package.campaign,
            residual_risks=(*package.campaign.residual_risks, reduction.residual_risk),
            project_risk_map=reduction.risk_map,
            status="non-accountable",
        )
    updated = replace(package, campaign=campaign, attempts=(*package.attempts, evidence))
    return updated, reduction


def reduce_evidence(
    *args: Any, **kwargs: Any
) -> tuple[DiscoveryCampaignPackage, EvidenceReduction]:
    """Descriptive alias for attempt-evidence reduction."""

    return reduce_attempt_evidence(*args, **kwargs)


def resume_campaign(
    document: Mapping[str, Any],
    *,
    strategy: RiskDerivationStrategy | None = None,
    derivation_strategy: RiskDerivationStrategy | None = None,
) -> DiscoveryCampaignPackage:
    """Reload a campaign package without silently changing its strategy.

    A serialized package keeps strategy identity/version in the campaign.  A
    caller may provide the executable strategy again when it intends to
    continue a custom lifecycle; mismatched identity is rejected before any
    downstream operation.
    """

    if (
        strategy is not None
        and derivation_strategy is not None
        and not _same_strategy(strategy, derivation_strategy)
    ):
        raise DiscoveryContractError("strategy and derivation_strategy disagree")
    selected = strategy or derivation_strategy
    package = DiscoveryCampaignPackage.from_dict(document)
    campaign = package.campaign
    if selected is not None:
        if campaign.derivation_strategy_id != selected.strategy_id:
            raise DiscoveryContractError("resume strategy does not match campaign strategy")
        if campaign.derivation_strategy_version != selected.version:
            raise DiscoveryContractError("resume strategy version does not match campaign")
    return package


def empty_risk_map(
    target_id: str,
    *,
    coverage_frontier: tuple[str, ...] = ("unresolved discovery context",),
) -> ProjectRiskMap:
    """Create an explicit empty map; an empty frontier is not a conclusion."""

    return ProjectRiskMap(
        map_id="risk-map-" + _stable_id(target_id, "initial"),
        target_id=target_id,
        findings=(),
        residual_risks=(),
        explored_fact_ids=(),
        coverage_frontier=coverage_frontier,
    )


def _seed_campaign(
    campaign_id: str,
    target: DiscoveryTarget,
    graph: QualityContextGraph,
    *,
    mode: str,
    behavior_delta: BehaviorDelta | None = None,
    contract_drift: ContractDrift | None = None,
    context_request: ContextExpansionRequest | None = None,
    context_result: ContextExpansionResult | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
    strategy: RiskDerivationStrategy | None = None,
    derivation_strategy: RiskDerivationStrategy | None = None,
) -> DiscoveryCampaignPackage:
    _validate_target_graph(target, graph)
    if context_request is not None:
        if (
            context_request.campaign_id != campaign_id
            or context_request.target_id != target.target_id
        ):
            raise DiscoveryContractError("context request does not match campaign target")
    if context_result is not None:
        if context_result.target_id != target.target_id:
            raise DiscoveryContractError("context result does not match campaign target")
        if context_request is not None and context_result.request_id != context_request.request_id:
            raise DiscoveryContractError("context result does not match context request")
        if context_request is not None and context_result.budget_used > context_request.budget:
            raise DiscoveryContractError("context result exceeded its bounded request budget")
        if context_result.status == "rejected":
            raise DiscoveryContractError("rejected context expansion cannot seed a campaign")
        if context_result.graph != graph:
            raise DiscoveryContractError("context result graph does not match campaign graph")
    if (
        strategy is not None
        and derivation_strategy is not None
        and not _same_strategy(strategy, derivation_strategy)
    ):
        raise DiscoveryContractError("strategy and derivation_strategy disagree")
    selected_strategy = strategy or derivation_strategy
    if selected_strategy is None:
        selected_prior = prior or make_temporal_prior(
            operator.operator_id if operator is not None else "operator-bounded-latency"
        )
        selected_operator = operator or make_latency_operator(selected_prior.operator_ids[0])
        canonical_prior = make_temporal_prior()
        if (
            selected_prior.prior_id != canonical_prior.prior_id
            or selected_operator.operator_id != "operator-bounded-latency"
        ):
            raise DiscoveryContractError(
                "non-temporal prior or operator requires an explicit derivation strategy"
            )
        selected_strategy = make_temporal_strategy(
            prior=selected_prior,
            operator=selected_operator,
        )
    else:
        if prior is None or operator is None:
            raise DiscoveryContractError(
                "custom risk derivation strategy requires explicit prior and operator"
            )
        selected_prior = prior
        selected_operator = operator
    derivation = derive_with_strategy(
        selected_strategy,
        target,
        graph,
        mode=mode,
        behavior_delta=behavior_delta,
        contract_drift=contract_drift,
        prior=selected_prior,
        operator=selected_operator,
    )
    if not derivation.accepted:
        raise DiscoveryContractError(
            "campaign risk derivation rejected: " + "; ".join(derivation.rejection_reasons)
        )
    assert derivation.hypothesis is not None
    assert derivation.failure_chain is not None
    assert derivation.priority is not None
    assert derivation.attack_plan is not None
    quality_contract = _quality_contract_from_graph(
        target,
        graph,
        contract_drift,
        quality_property=derivation.hypothesis.quality_property,
    )
    campaign = DiscoveryCampaign(
        campaign_id=campaign_id,
        target=target,
        context_graph=graph,
        quality_contracts=(quality_contract,),
        contract_drifts=(contract_drift,) if contract_drift is not None else (),
        risk_priors=(derivation.prior,),
        attack_operators=(derivation.operator,),
        hypotheses=(derivation.hypothesis,),
        failure_chains=(derivation.failure_chain,),
        attack_plans=(derivation.attack_plan,),
        project_risk_map=empty_risk_map(target.target_id),
        status="hypothesis-frozen",
        derivation_strategy_id=selected_strategy.strategy_id,
        derivation_strategy_version=selected_strategy.version,
    )
    ledger = HypothesisSelectionLedger().append(
        hypothesis_id=derivation.hypothesis.hypothesis_id,
        decision="selected",
        priority_score=derivation.priority.score,
        rationale=(
            f"Selected prior {derivation.prior.prior_id} using strategy "
            f"{selected_strategy.strategy_id}@{selected_strategy.version}; "
            "the first provenance-bound candidate was ordered for probing."
        ),
        prior_id=derivation.prior.prior_id,
    )
    if context_result is None:
        unresolved = tuple(
            f"fact {fact.fact_id} remains unresolved"
            for fact in graph.facts
            if fact.status in {"unknown", "contradictory", "stale"}
        )
        context_result = ContextExpansionResult(
            request_id=(
                context_request.request_id
                if context_request is not None
                else "context-" + _stable_id(campaign_id, graph.graph_id)
            ),
            target_id=target.target_id,
            graph=graph,
            resolved_fact_ids=tuple(fact.fact_id for fact in graph.facts if fact.status == "known"),
            unresolved_questions=unresolved,
            status="partial" if unresolved else "complete",
        )
    return DiscoveryCampaignPackage(
        campaign=campaign,
        selection_ledger=ledger,
        context_request=context_request,
        context_result=context_result,
        behavior_delta=behavior_delta,
        risk_priority=derivation.priority,
    )


def _quality_contract_from_graph(
    target: DiscoveryTarget,
    graph: QualityContextGraph,
    contract_drift: ContractDrift | None,
    *,
    quality_property: str | None = None,
) -> QualityContract:
    facts = [
        fact
        for fact in graph.facts
        if fact.predicate == "quality_contract" and fact.status == "known"
    ]
    if not facts:
        raise DiscoveryContractError("campaign requires a known quality contract fact")
    fact = sorted(facts, key=lambda item: item.fact_id)[0]
    contract_id = (
        contract_drift.contract_id
        if contract_drift is not None
        else "contract-" + _stable_id(target.target_id, fact.fact_id)
    )
    constraint = str(fact.value)
    selected_property = quality_property or "bounded synchronous response latency"
    state_contract = selected_property.startswith("durable state continuity")
    return QualityContract(
        contract_id=contract_id,
        name=(
            "durable state continuity quality contract"
            if state_contract
            else "bounded response quality contract"
        ),
        scope="recorded state path" if state_contract else fact.subject,
        quality_property=selected_property,
        constraint=constraint,
        source_fact_ids=(fact.fact_id,),
        status="derived",
    )


def _validate_target_graph(target: DiscoveryTarget, graph: QualityContextGraph) -> None:
    if not isinstance(target, (ChangeTarget, ProjectTarget)):
        raise DiscoveryContractError("campaign target must be ChangeTarget or ProjectTarget")
    if not isinstance(graph, QualityContextGraph):
        raise DiscoveryContractError("campaign graph must be a QualityContextGraph")
    if graph.target_id != target.target_id:
        raise DiscoveryContractError("campaign graph target does not match target")


def _same_strategy(
    left: RiskDerivationStrategy,
    right: RiskDerivationStrategy,
) -> bool:
    """Compare strategy aliases, including executable callable identity."""

    if not isinstance(left, RiskDerivationStrategy) or not isinstance(
        right, RiskDerivationStrategy
    ):
        return False
    return (
        left.strategy_id == right.strategy_id
        and left.version == right.version
        and left.compatible_prior_ids == right.compatible_prior_ids
        and left.compatible_operator_ids == right.compatible_operator_ids
        and left.target_modes == right.target_modes
        and left.schema_version == right.schema_version
        and left.deriver is right.deriver
    )


def _single_hypothesis(campaign: DiscoveryCampaign) -> RiskHypothesis:
    if len(campaign.hypotheses) != 1:
        raise DiscoveryContractError("bounded campaign requires one hypothesis")
    return campaign.hypotheses[0]


def _reduce_to_map(
    risk_map: ProjectRiskMap,
    evidence: AttemptEvidence,
    hypothesis: RiskHypothesis,
) -> EvidenceReduction:
    refs = tuple(dict.fromkeys((*evidence.evidence_refs, evidence.execution_record_ref)))
    outcome_id = _stable_id(evidence.evidence_id, evidence.attempt_ref)
    if evidence.accountable:
        finding = Finding(
            finding_id="finding-" + outcome_id,
            target_id=evidence.target_id,
            hypothesis_id=hypothesis.hypothesis_id,
            conclusion=evidence.outcome,
            evidence_refs=refs,
            impact=hypothesis.consequence,
            claim_boundary=evidence.claim_boundary,
            rationale=evidence.rationale,
        )
        if finding.finding_id in {item.finding_id for item in risk_map.findings}:
            raise DiscoveryContractError("attempt evidence would duplicate a Finding")
        new_map = replace(
            risk_map,
            findings=(*risk_map.findings, finding),
            explored_fact_ids=tuple(
                dict.fromkeys((*risk_map.explored_fact_ids, *hypothesis.supporting_fact_ids))
            ),
        )
        return EvidenceReduction(risk_map=new_map, finding=finding, residual_risk=None)
    residual = ResidualRisk(
        risk_id="risk-" + outcome_id,
        target_id=evidence.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        reason=evidence.rationale,
        evidence_gap=(
            "The attempt was not accountable; execution evidence cannot support "
            "a Finding."
        ),
        scope=evidence.claim_boundary,
        basis_refs=refs,
        next_probe="repeat only after a fresh accountable ExecutionRecord is established",
    )
    if residual.risk_id in {item.risk_id for item in risk_map.residual_risks}:
        raise DiscoveryContractError("attempt evidence would duplicate a Residual Risk")
    new_map = replace(
        risk_map,
        residual_risks=(*risk_map.residual_risks, residual),
        explored_fact_ids=tuple(
            dict.fromkeys((*risk_map.explored_fact_ids, *hypothesis.supporting_fact_ids))
        ),
    )
    return EvidenceReduction(risk_map=new_map, finding=None, residual_risk=residual)


def _run_spec_mapping(
    *,
    host_project: str | Path,
    apk_glob: str,
    package_name: str,
    activity: str | None,
    scenario: ScenarioSpec,
    diff: str | Path | None,
    spec: str | Path | None,
    live_validation: LiveValidationSpec | None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "host_project": str(host_project),
        "apk_glob": apk_glob,
        "package": package_name,
        "activity": activity,
        "scenario": _scenario_mapping(scenario),
    }
    if diff is not None:
        data["diff"] = str(diff)
    if spec is not None:
        data["spec"] = str(spec)
    if live_validation is not None:
        data["live_validation"] = _live_validation_mapping(live_validation)
    return data


def _scenario_mapping(scenario: ScenarioSpec) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "user_actions": list(scenario.user_actions),
        "system_events": [
            {"step_index": event.step_index, "event": event.event, "args": dict(event.args)}
            for event in scenario.system_events
        ],
        "assertions": [
            {
                "resource_id": assertion.resource_id,
                "attr": assertion.attr,
                "expected": assertion.expected,
            }
            for assertion in scenario.assertions
        ],
        "l2_boundary_index": scenario.l2_boundary_index,
        "expected_behavior": scenario.expected_behavior,
        "metric_context": {
            "seed_kind": scenario.metric_context.seed_kind,
            "taxonomy_category": scenario.metric_context.taxonomy_category,
            "taxonomy_pattern_id": scenario.metric_context.taxonomy_pattern_id,
            "expected_oracle_level": scenario.metric_context.expected_oracle_level,
            "expected_oracle_defect_class": scenario.metric_context.expected_oracle_defect_class,
        },
        "l3_spec": scenario.l3_spec,
    }


def _discovery_scenario(scenario: ScenarioSpec) -> ScenarioSpec:
    """Remove benchmark outcome labels before a campaign emits a Run Spec."""

    metric = replace(
        scenario.metric_context,
        taxonomy_category=None,
        taxonomy_pattern_id=None,
        expected_oracle_level=None,
        expected_oracle_defect_class=None,
        seed_kind="unspecified",
    )
    return replace(
        scenario,
        expected_behavior="",
        metric_context=metric,
    )


def _live_validation_mapping(spec: LiveValidationSpec) -> dict[str, Any]:
    result: dict[str, Any] = {
        "android_bin": spec.android_bin,
        "adb_bin": spec.adb_bin,
        "timeout_seconds": spec.timeout_seconds,
        "snippet_chars": spec.snippet_chars,
    }
    if spec.app_smoke is not None:
        app = spec.app_smoke
        result["app_smoke"] = {
            "package": app.package,
            "activity": app.activity,
            "target_resource_id": app.target_resource_id,
            "target_text": app.target_text,
            "target_content_desc": app.target_content_desc,
            "app_settle_seconds": app.app_settle_seconds,
        }
    return result


def _selection_digest(
    sequence: int,
    hypothesis_id: str,
    decision: str,
    priority_score: float,
    rationale: str,
    previous_digest: str,
    prior_id: str | None = None,
) -> str:
    value = {
        "sequence": sequence,
        "hypothesis_id": hypothesis_id,
        "decision": decision,
        "priority_score": priority_score,
        "rationale": rationale,
        "previous_digest": previous_digest,
    }
    if prior_id is not None:
        value["prior_id"] = prior_id
    return _digest(value)


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
