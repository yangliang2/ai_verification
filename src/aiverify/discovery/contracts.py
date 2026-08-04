"""Versioned contracts for reasoning about quality risk before execution.

The objects in this module deliberately stop at the boundary of execution.  A
``DiscoveryCampaign`` can describe what should be probed, while a ``RunSpec``
continues to describe how one reproducible experiment is run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from aiverify.discovery.models import (
    ChangeTarget,
    DiscoveryContractError,
    DiscoveryTarget,
    QualityContextGraph,
    ProjectTarget,
    _reject_unknown,
    _required_text,
)


_QUALITY_CONTRACT_STATUSES = frozenset({"declared", "derived", "observed", "unknown"})
_DRIFT_STATUSES = frozenset({"suspected", "observed", "contradictory", "unknown"})
_HYPOTHESIS_STATUSES = frozenset(
    {"draft", "frozen", "supported", "rejected", "inconclusive"}
)
_PLAN_STATUSES = frozenset({"draft", "frozen", "admitted", "rejected"})
_FINDING_CONCLUSIONS = frozenset({"supported", "rejected", "inconclusive"})
_CAMPAIGN_STATUSES = frozenset(
    {
        "created",
        "draft",
        "context-ready",
        "hypothesis-frozen",
        "plan-admitted",
        "admitted",
        "executing",
        "running",
        "concluded",
        "completed",
        "inconclusive",
        "non-accountable",
    }
)


def _version(value: object, field: str, expected: int = 1) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value != expected:
        raise DiscoveryContractError(f"unsupported {field} schema_version")


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


def _required(data: Mapping[str, Any], field: str) -> Any:
    try:
        return data[field]
    except KeyError as error:
        raise DiscoveryContractError(f"contract requires {field}") from error


def _validate_confidence(value: object) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not 0 <= value <= 1
    ):
        raise DiscoveryContractError("confidence must be between 0 and 1")


def _unique_ids(values: tuple[Any, ...], field: str, id_field: str) -> None:
    ids = [getattr(value, id_field) for value in values]
    if len(ids) != len(set(ids)):
        raise DiscoveryContractError(f"{field} ids must be unique")


@dataclass(frozen=True)
class QualityContract:
    """A quality property and the constraint that should remain true."""

    contract_id: str
    name: str
    scope: str
    quality_property: str
    constraint: str
    source_fact_ids: tuple[str, ...]
    status: str = "declared"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("contract_id", "name", "scope", "quality_property", "constraint"):
            _required_text(getattr(self, field), field)
        _text_tuple(self.source_fact_ids, "source_fact_ids", allow_empty=False)
        if self.status not in _QUALITY_CONTRACT_STATUSES:
            raise DiscoveryContractError("invalid quality contract status")
        _version(self.schema_version, "quality contract")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "name": self.name,
            "scope": self.scope,
            "quality_property": self.quality_property,
            "constraint": self.constraint,
            "source_fact_ids": list(self.source_fact_ids),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "QualityContract":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("quality contract must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "contract_id",
                "name",
                "scope",
                "quality_property",
                "constraint",
                "source_fact_ids",
                "status",
            },
        )
        return cls(
            contract_id=_required(data, "contract_id"),
            name=_required(data, "name"),
            scope=_required(data, "scope"),
            quality_property=_required(data, "quality_property"),
            constraint=_required(data, "constraint"),
            source_fact_ids=tuple(_list_to_tuple(data, "source_fact_ids")),
            status=data.get("status", "declared"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class ContractDrift:
    """A bounded before/after change to one quality contract."""

    drift_id: str
    contract_id: str
    before: str
    after: str
    delta: str
    source_fact_ids: tuple[str, ...]
    status: str = "suspected"
    rationale: str = ""
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("drift_id", "contract_id", "before", "after", "delta"):
            _required_text(getattr(self, field), field)
        _text_tuple(self.source_fact_ids, "source_fact_ids", allow_empty=False)
        if self.status not in _DRIFT_STATUSES:
            raise DiscoveryContractError("invalid contract drift status")
        _required_text(self.rationale, "rationale")
        _version(self.schema_version, "contract drift")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "drift_id": self.drift_id,
            "contract_id": self.contract_id,
            "before": self.before,
            "after": self.after,
            "delta": self.delta,
            "source_fact_ids": list(self.source_fact_ids),
            "status": self.status,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContractDrift":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("contract drift must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "drift_id",
                "contract_id",
                "before",
                "after",
                "delta",
                "source_fact_ids",
                "status",
                "rationale",
            },
        )
        return cls(
            drift_id=_required(data, "drift_id"),
            contract_id=_required(data, "contract_id"),
            before=_required(data, "before"),
            after=_required(data, "after"),
            delta=_required(data, "delta"),
            source_fact_ids=tuple(_list_to_tuple(data, "source_fact_ids")),
            status=data.get("status", "suspected"),
            rationale=data.get("rationale", ""),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class RiskPrior:
    """A reusable, explicitly named prior for selecting risk hypotheses."""

    prior_id: str
    name: str
    description: str
    signals: tuple[str, ...]
    operator_ids: tuple[str, ...]
    version: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("prior_id", "name", "description", "version"):
            _required_text(getattr(self, field), field)
        _text_tuple(self.signals, "signals", allow_empty=False)
        _text_tuple(self.operator_ids, "operator_ids", allow_empty=False)
        _version(self.schema_version, "risk prior")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "prior_id": self.prior_id,
            "name": self.name,
            "description": self.description,
            "signals": list(self.signals),
            "operator_ids": list(self.operator_ids),
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RiskPrior":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("risk prior must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "prior_id",
                "name",
                "description",
                "signals",
                "operator_ids",
                "version",
            },
        )
        return cls(
            prior_id=_required(data, "prior_id"),
            name=_required(data, "name"),
            description=_required(data, "description"),
            signals=tuple(_list_to_tuple(data, "signals")),
            operator_ids=tuple(_list_to_tuple(data, "operator_ids")),
            version=_required(data, "version"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class AttackOperator:
    """A bounded perturbation or observation strategy for one risk prior."""

    operator_id: str
    name: str
    description: str
    action: str
    safety_boundary: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("operator_id", "name", "description", "action", "safety_boundary"):
            _required_text(getattr(self, field), field)
        _version(self.schema_version, "attack operator")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "operator_id": self.operator_id,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "safety_boundary": self.safety_boundary,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackOperator":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attack operator must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "operator_id",
                "name",
                "description",
                "action",
                "safety_boundary",
            },
        )
        return cls(
            operator_id=_required(data, "operator_id"),
            name=_required(data, "name"),
            description=_required(data, "description"),
            action=_required(data, "action"),
            safety_boundary=_required(data, "safety_boundary"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class FailureChain:
    """An ordered causal chain from trigger to consequence."""

    chain_id: str
    steps: tuple[str, ...]
    consequence: str
    fact_ids: tuple[str, ...] = ()
    causal_roles: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.chain_id, "chain_id")
        _text_tuple(self.steps, "steps", allow_empty=False)
        _required_text(self.consequence, "consequence")
        _text_tuple(self.fact_ids, "fact_ids")
        _text_tuple(self.causal_roles, "causal_roles")
        if self.causal_roles and len(self.causal_roles) != len(self.steps):
            raise DiscoveryContractError("causal_roles must align with steps")
        if any(
            role not in {
                "local_behavior",
                "dependency_propagation",
                "caller_constraint",
                "system_impact",
            }
            for role in self.causal_roles
        ):
            raise DiscoveryContractError("invalid failure chain causal role")
        _version(self.schema_version, "failure chain")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "chain_id": self.chain_id,
            "steps": list(self.steps),
            "consequence": self.consequence,
            "fact_ids": list(self.fact_ids),
            "causal_roles": list(self.causal_roles),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "FailureChain":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("failure chain must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "chain_id",
                "steps",
                "consequence",
                "fact_ids",
                "causal_roles",
            },
        )
        return cls(
            chain_id=_required(data, "chain_id"),
            steps=tuple(_list_to_tuple(data, "steps")),
            consequence=_required(data, "consequence"),
            fact_ids=tuple(_list_to_tuple(data, "fact_ids")) if "fact_ids" in data else (),
            causal_roles=(
                tuple(_list_to_tuple(data, "causal_roles"))
                if "causal_roles" in data
                else ()
            ),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class RiskHypothesis:
    """A falsifiable, confidence-bearing explanation of a quality failure."""

    hypothesis_id: str
    target_id: str
    quality_property: str
    assumptions: tuple[str, ...]
    trigger: str
    mechanism: str
    consequence: str
    rationale: str
    required_evidence: tuple[str, ...]
    confidence: float
    status: str
    supporting_fact_ids: tuple[str, ...]
    prior_id: str | None = None
    failure_chain_id: str | None = None
    unknowns: tuple[str, ...] = ()
    behavior_delta_id: str | None = None
    contract_drift_id: str | None = None
    priority_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in (
            "hypothesis_id",
            "target_id",
            "quality_property",
            "trigger",
            "mechanism",
            "consequence",
            "rationale",
        ):
            _required_text(getattr(self, field), field)
        _text_tuple(self.assumptions, "assumptions")
        _text_tuple(self.required_evidence, "required_evidence", allow_empty=False)
        _text_tuple(self.supporting_fact_ids, "supporting_fact_ids", allow_empty=False)
        _text_tuple(self.unknowns, "unknowns")
        _validate_confidence(self.confidence)
        if self.status not in _HYPOTHESIS_STATUSES:
            raise DiscoveryContractError("invalid risk hypothesis status")
        if self.prior_id is not None:
            _required_text(self.prior_id, "prior_id")
        if self.failure_chain_id is not None:
            _required_text(self.failure_chain_id, "failure_chain_id")
        for field in ("behavior_delta_id", "contract_drift_id", "priority_id"):
            value = getattr(self, field)
            if value is not None:
                _required_text(value, field)
        _version(self.schema_version, "risk hypothesis")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "hypothesis_id": self.hypothesis_id,
            "target_id": self.target_id,
            "quality_property": self.quality_property,
            "assumptions": list(self.assumptions),
            "trigger": self.trigger,
            "mechanism": self.mechanism,
            "consequence": self.consequence,
            "rationale": self.rationale,
            "required_evidence": list(self.required_evidence),
            "confidence": self.confidence,
            "status": self.status,
            "supporting_fact_ids": list(self.supporting_fact_ids),
            "unknowns": list(self.unknowns),
        }
        if self.prior_id is not None:
            result["prior_id"] = self.prior_id
        if self.failure_chain_id is not None:
            result["failure_chain_id"] = self.failure_chain_id
        if self.behavior_delta_id is not None:
            result["behavior_delta_id"] = self.behavior_delta_id
        if self.contract_drift_id is not None:
            result["contract_drift_id"] = self.contract_drift_id
        if self.priority_id is not None:
            result["priority_id"] = self.priority_id
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RiskHypothesis":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("risk hypothesis must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "hypothesis_id",
                "target_id",
                "quality_property",
                "assumptions",
                "trigger",
                "mechanism",
                "consequence",
                "rationale",
                "required_evidence",
                "confidence",
                "status",
                "supporting_fact_ids",
                "prior_id",
                "failure_chain_id",
                "unknowns",
                "behavior_delta_id",
                "contract_drift_id",
                "priority_id",
            },
        )
        return cls(
            hypothesis_id=_required(data, "hypothesis_id"),
            target_id=_required(data, "target_id"),
            quality_property=_required(data, "quality_property"),
            assumptions=tuple(_list_to_tuple(data, "assumptions")),
            trigger=_required(data, "trigger"),
            mechanism=_required(data, "mechanism"),
            consequence=_required(data, "consequence"),
            rationale=_required(data, "rationale"),
            required_evidence=tuple(_list_to_tuple(data, "required_evidence")),
            confidence=_required(data, "confidence"),
            status=_required(data, "status"),
            supporting_fact_ids=tuple(_list_to_tuple(data, "supporting_fact_ids")),
            prior_id=data.get("prior_id"),
            failure_chain_id=data.get("failure_chain_id"),
            unknowns=tuple(_list_to_tuple(data, "unknowns")) if "unknowns" in data else (),
            behavior_delta_id=data.get("behavior_delta_id"),
            contract_drift_id=data.get("contract_drift_id"),
            priority_id=data.get("priority_id"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class AttackPlan:
    """A bounded attack and observation plan, before a Run Spec is generated."""

    plan_id: str
    target_id: str
    hypothesis_id: str
    operator_id: str
    trigger: str = ""
    observations: tuple[str, ...] = ()
    evidence_expectations: tuple[str, ...] = ()
    oracle: str = ""
    abort_boundary: str = ""
    claim_boundary: str = ""
    fixture_refs: tuple[str, ...] = ()
    experiment_refs: tuple[str, ...] = ()
    status: str = "draft"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("plan_id", "target_id", "hypothesis_id", "operator_id"):
            _required_text(getattr(self, field), field)
        for field in (
            "trigger",
            "oracle",
            "abort_boundary",
            "claim_boundary",
        ):
            if not isinstance(getattr(self, field), str):
                raise DiscoveryContractError(f"{field} must be a string")
        for field in ("observations", "evidence_expectations", "fixture_refs", "experiment_refs"):
            _text_tuple(getattr(self, field), field)
        if self.status not in _PLAN_STATUSES:
            raise DiscoveryContractError("invalid attack plan status")
        _version(self.schema_version, "attack plan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "target_id": self.target_id,
            "hypothesis_id": self.hypothesis_id,
            "operator_id": self.operator_id,
            "trigger": self.trigger,
            "observations": list(self.observations),
            "evidence_expectations": list(self.evidence_expectations),
            "oracle": self.oracle,
            "abort_boundary": self.abort_boundary,
            "claim_boundary": self.claim_boundary,
            "fixture_refs": list(self.fixture_refs),
            "experiment_refs": list(self.experiment_refs),
            "status": self.status,
        }

    @property
    def oracle_ref(self) -> str:
        """Compatibility name for callers that call the oracle a reference."""

        return self.oracle

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackPlan":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attack plan must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "plan_id",
                "target_id",
                "hypothesis_id",
                "operator_id",
                "trigger",
                "observations",
                "evidence_expectations",
                "oracle",
                "abort_boundary",
                "claim_boundary",
                "fixture_refs",
                "experiment_refs",
                "status",
            },
        )
        return cls(
            plan_id=_required(data, "plan_id"),
            target_id=_required(data, "target_id"),
            hypothesis_id=_required(data, "hypothesis_id"),
            operator_id=_required(data, "operator_id"),
            trigger=data.get("trigger", ""),
            observations=(
                tuple(_list_to_tuple(data, "observations"))
                if "observations" in data
                else ()
            ),
            evidence_expectations=(
                tuple(_list_to_tuple(data, "evidence_expectations"))
                if "evidence_expectations" in data
                else ()
            ),
            oracle=data.get("oracle", ""),
            abort_boundary=data.get("abort_boundary", ""),
            claim_boundary=data.get("claim_boundary", ""),
            fixture_refs=(
                tuple(_list_to_tuple(data, "fixture_refs"))
                if "fixture_refs" in data
                else ()
            ),
            experiment_refs=(
                tuple(_list_to_tuple(data, "experiment_refs"))
                if "experiment_refs" in data
                else ()
            ),
            status=data.get("status", "draft"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class Finding:
    """An evidence-backed local conclusion for one hypothesis."""

    finding_id: str
    target_id: str
    hypothesis_id: str
    conclusion: str
    evidence_refs: tuple[str, ...]
    impact: str
    claim_boundary: str
    rationale: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in (
            "finding_id",
            "target_id",
            "hypothesis_id",
            "impact",
            "claim_boundary",
            "rationale",
        ):
            _required_text(getattr(self, field), field)
        if self.conclusion not in _FINDING_CONCLUSIONS:
            raise DiscoveryContractError("invalid finding conclusion")
        _text_tuple(self.evidence_refs, "evidence_refs", allow_empty=False)
        _version(self.schema_version, "finding")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "finding_id": self.finding_id,
            "target_id": self.target_id,
            "hypothesis_id": self.hypothesis_id,
            "conclusion": self.conclusion,
            "evidence_refs": list(self.evidence_refs),
            "impact": self.impact,
            "claim_boundary": self.claim_boundary,
            "rationale": self.rationale,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Finding":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("finding must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "finding_id",
                "target_id",
                "hypothesis_id",
                "conclusion",
                "evidence_refs",
                "impact",
                "claim_boundary",
                "rationale",
            },
        )
        return cls(
            finding_id=_required(data, "finding_id"),
            target_id=_required(data, "target_id"),
            hypothesis_id=_required(data, "hypothesis_id"),
            conclusion=_required(data, "conclusion"),
            evidence_refs=tuple(_list_to_tuple(data, "evidence_refs")),
            impact=_required(data, "impact"),
            claim_boundary=_required(data, "claim_boundary"),
            rationale=_required(data, "rationale"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class ResidualRisk:
    """An explicit unresolved risk, never a substitute for a Finding."""

    risk_id: str
    target_id: str
    hypothesis_id: str
    reason: str
    evidence_gap: str
    scope: str
    basis_refs: tuple[str, ...]
    next_probe: str | None = None
    status: str = "open"
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("risk_id", "target_id", "hypothesis_id", "reason", "evidence_gap", "scope"):
            _required_text(getattr(self, field), field)
        _text_tuple(self.basis_refs, "basis_refs", allow_empty=False)
        if self.next_probe is not None:
            _required_text(self.next_probe, "next_probe")
        if self.status not in {"open", "accepted", "closed"}:
            raise DiscoveryContractError("invalid residual risk status")
        _version(self.schema_version, "residual risk")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "risk_id": self.risk_id,
            "target_id": self.target_id,
            "hypothesis_id": self.hypothesis_id,
            "reason": self.reason,
            "evidence_gap": self.evidence_gap,
            "scope": self.scope,
            "basis_refs": list(self.basis_refs),
            "status": self.status,
        }
        if self.next_probe is not None:
            result["next_probe"] = self.next_probe
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ResidualRisk":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("residual risk must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "risk_id",
                "target_id",
                "hypothesis_id",
                "reason",
                "evidence_gap",
                "scope",
                "basis_refs",
                "next_probe",
                "status",
            },
        )
        return cls(
            risk_id=_required(data, "risk_id"),
            target_id=_required(data, "target_id"),
            hypothesis_id=_required(data, "hypothesis_id"),
            reason=_required(data, "reason"),
            evidence_gap=_required(data, "evidence_gap"),
            scope=_required(data, "scope"),
            basis_refs=tuple(_list_to_tuple(data, "basis_refs")),
            next_probe=data.get("next_probe"),
            status=data.get("status", "open"),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class ProjectRiskMap:
    """The current explored frontier: findings plus unresolved residual risks."""

    map_id: str
    target_id: str
    findings: tuple[Finding, ...]
    residual_risks: tuple[ResidualRisk, ...]
    explored_fact_ids: tuple[str, ...]
    coverage_frontier: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.map_id, "map_id")
        _required_text(self.target_id, "target_id")
        if not isinstance(self.findings, tuple):
            raise DiscoveryContractError("findings must be a tuple")
        if not isinstance(self.residual_risks, tuple):
            raise DiscoveryContractError("residual_risks must be a tuple")
        if any(not isinstance(item, Finding) for item in self.findings):
            raise DiscoveryContractError("findings must contain Finding values")
        if any(not isinstance(item, ResidualRisk) for item in self.residual_risks):
            raise DiscoveryContractError("residual_risks must contain ResidualRisk values")
        finding_ids = [item.finding_id for item in self.findings]
        risk_ids = [item.risk_id for item in self.residual_risks]
        if len(set(finding_ids)) != len(finding_ids):
            raise DiscoveryContractError("finding ids must be unique")
        if len(set(risk_ids)) != len(risk_ids):
            raise DiscoveryContractError("residual risk ids must be unique")
        if any(item.target_id != self.target_id for item in self.findings):
            raise DiscoveryContractError("finding target does not match risk map")
        if any(item.target_id != self.target_id for item in self.residual_risks):
            raise DiscoveryContractError("residual risk target does not match risk map")
        _text_tuple(self.explored_fact_ids, "explored_fact_ids")
        _text_tuple(self.coverage_frontier, "coverage_frontier", allow_empty=False)
        _version(self.schema_version, "project risk map")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "map_id": self.map_id,
            "target_id": self.target_id,
            "findings": [item.to_dict() for item in self.findings],
            "residual_risks": [item.to_dict() for item in self.residual_risks],
            "explored_fact_ids": list(self.explored_fact_ids),
            "coverage_frontier": list(self.coverage_frontier),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectRiskMap":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("project risk map must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "map_id",
                "target_id",
                "findings",
                "residual_risks",
                "explored_fact_ids",
                "coverage_frontier",
            },
        )
        raw_findings = _list_to_tuple(data, "findings")
        raw_risks = _list_to_tuple(data, "residual_risks")
        return cls(
            map_id=_required(data, "map_id"),
            target_id=_required(data, "target_id"),
            findings=tuple(Finding.from_dict(item) for item in raw_findings),
            residual_risks=tuple(ResidualRisk.from_dict(item) for item in raw_risks),
            explored_fact_ids=tuple(_list_to_tuple(data, "explored_fact_ids")),
            coverage_frontier=tuple(_list_to_tuple(data, "coverage_frontier")),
            schema_version=data.get("schema_version", 1),
        )


@dataclass(frozen=True)
class DiscoveryCampaign:
    """The discovery layer that produces bounded experiments and outcomes."""

    campaign_id: str
    target: DiscoveryTarget
    context_graph: QualityContextGraph
    quality_contracts: tuple[QualityContract, ...] = ()
    contract_drifts: tuple[ContractDrift, ...] = ()
    risk_priors: tuple[RiskPrior, ...] = ()
    attack_operators: tuple[AttackOperator, ...] = ()
    hypotheses: tuple[RiskHypothesis, ...] = ()
    failure_chains: tuple[FailureChain, ...] = ()
    attack_plans: tuple[AttackPlan, ...] = ()
    experiment_refs: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()
    residual_risks: tuple[ResidualRisk, ...] = ()
    project_risk_map: ProjectRiskMap | None = None
    status: str = "draft"
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.campaign_id, "campaign_id")
        if not isinstance(self.target, (ChangeTarget, ProjectTarget)):
            raise DiscoveryContractError("campaign target must be a DiscoveryTarget")
        if not isinstance(self.context_graph, QualityContextGraph):
            raise DiscoveryContractError("campaign context_graph must be a QualityContextGraph")
        if self.context_graph.target_id != self.target.target_id:
            raise DiscoveryContractError("campaign context target does not match target")
        collections = {
            "quality_contracts": (QualityContract, self.quality_contracts),
            "contract_drifts": (ContractDrift, self.contract_drifts),
            "risk_priors": (RiskPrior, self.risk_priors),
            "attack_operators": (AttackOperator, self.attack_operators),
            "hypotheses": (RiskHypothesis, self.hypotheses),
            "failure_chains": (FailureChain, self.failure_chains),
            "attack_plans": (AttackPlan, self.attack_plans),
            "findings": (Finding, self.findings),
            "residual_risks": (ResidualRisk, self.residual_risks),
        }
        for field, (kind, values) in collections.items():
            if not isinstance(values, tuple) or any(not isinstance(item, kind) for item in values):
                raise DiscoveryContractError(f"{field} contains an invalid contract")
        _unique_ids(self.quality_contracts, "quality contract", "contract_id")
        _unique_ids(self.contract_drifts, "contract drift", "drift_id")
        _unique_ids(self.risk_priors, "risk prior", "prior_id")
        _unique_ids(self.attack_operators, "attack operator", "operator_id")
        _unique_ids(self.hypotheses, "hypothesis", "hypothesis_id")
        _unique_ids(self.failure_chains, "failure chain", "chain_id")
        _unique_ids(self.attack_plans, "attack plan", "plan_id")
        _unique_ids(self.findings, "finding", "finding_id")
        _unique_ids(self.residual_risks, "residual risk", "risk_id")
        fact_ids = {fact.fact_id for fact in self.context_graph.facts}
        contract_ids = {item.contract_id for item in self.quality_contracts}
        prior_ids = {item.prior_id for item in self.risk_priors}
        operator_ids = {item.operator_id for item in self.attack_operators}
        hypothesis_ids = {item.hypothesis_id for item in self.hypotheses}
        chain_ids = {item.chain_id for item in self.failure_chains}
        for contract in self.quality_contracts:
            if not set(contract.source_fact_ids).issubset(fact_ids):
                raise DiscoveryContractError("quality contract references missing context fact")
        for drift in self.contract_drifts:
            if drift.contract_id not in contract_ids:
                raise DiscoveryContractError("contract drift references missing quality contract")
            if not set(drift.source_fact_ids).issubset(fact_ids):
                raise DiscoveryContractError("contract drift references missing context fact")
        for prior in self.risk_priors:
            if not set(prior.operator_ids).issubset(operator_ids):
                raise DiscoveryContractError("risk prior references missing attack operator")
        for hypothesis in self.hypotheses:
            if not set(hypothesis.supporting_fact_ids).issubset(fact_ids):
                raise DiscoveryContractError("hypothesis references missing context fact")
            if hypothesis.prior_id is not None and hypothesis.prior_id not in prior_ids:
                raise DiscoveryContractError("hypothesis references missing risk prior")
            if (
                hypothesis.failure_chain_id is not None
                and hypothesis.failure_chain_id not in chain_ids
            ):
                raise DiscoveryContractError("hypothesis references missing failure chain")
        for chain in self.failure_chains:
            if not set(chain.fact_ids).issubset(fact_ids):
                raise DiscoveryContractError("failure chain references missing context fact")
        for plan in self.attack_plans:
            if plan.hypothesis_id not in hypothesis_ids:
                raise DiscoveryContractError("attack plan references missing hypothesis")
            if plan.operator_id not in operator_ids:
                raise DiscoveryContractError("attack plan references missing attack operator")
        for finding in self.findings:
            if finding.hypothesis_id not in hypothesis_ids:
                raise DiscoveryContractError("finding references missing hypothesis")
        for risk in self.residual_risks:
            if risk.hypothesis_id not in hypothesis_ids:
                raise DiscoveryContractError("residual risk references missing hypothesis")
        if any(item.target_id != self.target.target_id for item in self.hypotheses):
            raise DiscoveryContractError("hypothesis target does not match campaign target")
        if any(item.target_id != self.target.target_id for item in self.attack_plans):
            raise DiscoveryContractError("attack plan target does not match campaign target")
        if any(item.target_id != self.target.target_id for item in self.findings):
            raise DiscoveryContractError("finding target does not match campaign target")
        if any(item.target_id != self.target.target_id for item in self.residual_risks):
            raise DiscoveryContractError("residual risk target does not match campaign target")
        if self.project_risk_map is not None:
            if not isinstance(self.project_risk_map, ProjectRiskMap):
                raise DiscoveryContractError("project_risk_map must be a ProjectRiskMap")
            if self.project_risk_map.target_id != self.target.target_id:
                raise DiscoveryContractError("risk map target does not match campaign target")
            if self.project_risk_map.findings != self.findings:
                raise DiscoveryContractError("risk map findings must match campaign findings")
            if self.project_risk_map.residual_risks != self.residual_risks:
                raise DiscoveryContractError(
                    "risk map residual risks must match campaign residual risks"
                )
        _text_tuple(self.experiment_refs, "experiment_refs")
        if self.status not in _CAMPAIGN_STATUSES:
            raise DiscoveryContractError("invalid discovery campaign status")
        _version(self.schema_version, "discovery campaign")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "target": self.target.to_dict(),
            "context_graph": self.context_graph.to_dict(),
            "quality_contracts": [item.to_dict() for item in self.quality_contracts],
            "contract_drifts": [item.to_dict() for item in self.contract_drifts],
            "risk_priors": [item.to_dict() for item in self.risk_priors],
            "attack_operators": [item.to_dict() for item in self.attack_operators],
            "hypotheses": [item.to_dict() for item in self.hypotheses],
            "failure_chains": [item.to_dict() for item in self.failure_chains],
            "attack_plans": [item.to_dict() for item in self.attack_plans],
            "experiment_refs": list(self.experiment_refs),
            "findings": [item.to_dict() for item in self.findings],
            "residual_risks": [item.to_dict() for item in self.residual_risks],
            "status": self.status,
        }
        if self.project_risk_map is not None:
            result["project_risk_map"] = self.project_risk_map.to_dict()
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "DiscoveryCampaign":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("discovery campaign must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "campaign_id",
                "target",
                "context_graph",
                "quality_contracts",
                "contract_drifts",
                "risk_priors",
                "attack_operators",
                "hypotheses",
                "failure_chains",
                "attack_plans",
                "experiment_refs",
                "findings",
                "residual_risks",
                "project_risk_map",
                "status",
            },
        )
        return cls(
            campaign_id=_required(data, "campaign_id"),
            target=_target_from_dict(_required(data, "target")),
            context_graph=QualityContextGraph.from_dict(_required(data, "context_graph")),
            quality_contracts=_contracts_from_dict(data, "quality_contracts", QualityContract),
            contract_drifts=_contracts_from_dict(data, "contract_drifts", ContractDrift),
            risk_priors=_contracts_from_dict(data, "risk_priors", RiskPrior),
            attack_operators=_contracts_from_dict(data, "attack_operators", AttackOperator),
            hypotheses=_contracts_from_dict(data, "hypotheses", RiskHypothesis),
            failure_chains=_contracts_from_dict(data, "failure_chains", FailureChain),
            attack_plans=_contracts_from_dict(data, "attack_plans", AttackPlan),
            experiment_refs=(
                tuple(_list_to_tuple(data, "experiment_refs"))
                if "experiment_refs" in data
                else ()
            ),
            findings=_contracts_from_dict(data, "findings", Finding),
            residual_risks=_contracts_from_dict(data, "residual_risks", ResidualRisk),
            project_risk_map=(
                ProjectRiskMap.from_dict(data["project_risk_map"])
                if data.get("project_risk_map") is not None
                else None
            ),
            status=data.get("status", "draft"),
            schema_version=data.get("schema_version", 1),
        )


def _target_from_dict(data: Mapping[str, Any]) -> DiscoveryTarget:
    from aiverify.discovery.models import target_from_dict

    return target_from_dict(data)


def _contracts_from_dict(
    data: Mapping[str, Any], field: str, contract_type: type[Any]
) -> tuple[Any, ...]:
    if field not in data:
        return ()
    raw = _list_to_tuple(data, field)
    return tuple(contract_type.from_dict(item) for item in raw)


@dataclass(frozen=True)
class AdmissionResult:
    """A side-effect-free admission decision for a generated experiment."""

    status: str
    errors: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.status not in {"admitted", "rejected"}:
            raise DiscoveryContractError("admission status must be admitted or rejected")
        _text_tuple(self.errors, "admission errors")
        if self.status == "admitted" and self.errors:
            raise DiscoveryContractError("admitted result cannot contain errors")
        if self.status == "rejected" and not self.errors:
            raise DiscoveryContractError("rejected result requires errors")
        _version(self.schema_version, "admission result")

    @property
    def admitted(self) -> bool:
        return self.status == "admitted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "errors": list(self.errors),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdmissionResult":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("admission result must be an object")
        _reject_unknown(data, {"schema_version", "status", "errors"})
        return cls(
            status=_required(data, "status"),
            errors=tuple(_list_to_tuple(data, "errors")),
            schema_version=data.get("schema_version", 1),
        )


def admit_attack_plan(
    plan: AttackPlan,
    hypothesis: RiskHypothesis,
    context_graph: QualityContextGraph,
) -> AdmissionResult:
    """Validate all preconditions before a plan can cause an external side effect."""

    errors: list[str] = []
    if plan.status not in {"draft", "frozen"}:
        errors.append("attack plan must be draft or frozen before admission")
    if plan.target_id != hypothesis.target_id:
        errors.append("attack plan target does not match hypothesis")
    if plan.target_id != context_graph.target_id:
        errors.append("attack plan target does not match context graph")
    if plan.hypothesis_id != hypothesis.hypothesis_id:
        errors.append("attack plan hypothesis does not match supplied hypothesis")
    if hypothesis.status != "frozen":
        errors.append("hypothesis must be frozen before admission")
    if not plan.trigger.strip():
        errors.append("missing trigger")
    if not plan.observations:
        errors.append("missing observations")
    if not plan.fixture_refs:
        errors.append("missing fixture relationship")
    if not plan.evidence_expectations:
        errors.append("missing evidence expectations")
    if not plan.oracle.strip():
        errors.append("missing oracle relationship")
    if not plan.abort_boundary.strip():
        errors.append("missing abort boundary")
    if not plan.claim_boundary.strip():
        errors.append("missing claim boundary")

    try:
        facts = {fact.fact_id: fact for fact in context_graph.facts}
        for fact_id in hypothesis.supporting_fact_ids:
            fact = facts.get(fact_id)
            if fact is None:
                errors.append(f"missing supporting context fact: {fact_id}")
            elif fact.status in {"contradictory", "stale"}:
                errors.append(f"contradictory or stale supporting context fact: {fact_id}")
        if not set(hypothesis.required_evidence).issubset(set(plan.evidence_expectations)):
            errors.append("evidence expectations do not cover hypothesis requirements")
    except AttributeError as error:
        errors.append(f"invalid admission input: {error}")

    return AdmissionResult("rejected", tuple(errors)) if errors else AdmissionResult("admitted")


def admit_experiment(
    plan: AttackPlan,
    hypothesis: RiskHypothesis,
    context_graph: QualityContextGraph,
) -> AdmissionResult:
    """Public alias emphasizing that admission precedes Run Spec generation."""

    return admit_attack_plan(plan, hypothesis, context_graph)
