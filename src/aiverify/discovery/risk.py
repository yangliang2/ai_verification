"""Bounded synchronous-critical-path risk derivation for M7.

The derivation is deliberately evidence-first: it can freeze a hypothesis and
attack plan, but it never emits a Finding or treats its priority score as truth.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Mapping

from aiverify.discovery.contracts import (
    AttackOperator,
    AttackPlan,
    ContractDrift,
    FailureChain,
    RiskHypothesis,
    RiskPrior,
)
from aiverify.discovery.models import (
    ChangeTarget,
    ContextFact,
    ContextNode,
    DiscoveryContractError,
    DiscoveryTarget,
    ProjectTarget,
    QualityContextGraph,
)


TEMPORAL_SIGNAL_TERMS = (
    "delay",
    "latency",
    "blocking",
    "retry",
    "io",
    "lock",
    "wait",
    "availability",
)


@dataclass(frozen=True)
class BehaviorDelta:
    """A change-scoped, evidence-referenced delta kept separate from facts."""

    delta_id: str
    target_id: str
    subject: str
    before: str
    after: str
    source_fact_ids: tuple[str, ...]
    confidence: float
    status: str = "inferred"
    contract_drift_id: str | None = None
    rationale: str = ""
    schema_version: int = 1

    def __post_init__(self) -> None:
        for field in ("delta_id", "target_id", "subject", "before", "after"):
            if not isinstance(getattr(self, field), str) or not getattr(self, field).strip():
                raise DiscoveryContractError(f"{field} must be a non-empty string")
        if not isinstance(self.source_fact_ids, tuple) or not self.source_fact_ids:
            raise DiscoveryContractError("behavior delta source_fact_ids must not be empty")
        if any(not isinstance(item, str) or not item.strip() for item in self.source_fact_ids):
            raise DiscoveryContractError("behavior delta source_fact_ids must contain strings")
        if not isinstance(self.confidence, (int, float)) or isinstance(self.confidence, bool):
            raise DiscoveryContractError("behavior delta confidence must be between 0 and 1")
        if not 0 <= self.confidence <= 1:
            raise DiscoveryContractError("behavior delta confidence must be between 0 and 1")
        if self.status not in {"inferred", "observed", "unknown", "contradictory"}:
            raise DiscoveryContractError("invalid behavior delta status")
        if self.status == "unknown" and not self.rationale.strip():
            raise DiscoveryContractError("unknown behavior delta requires rationale")
        if self.contract_drift_id is not None and not self.contract_drift_id.strip():
            raise DiscoveryContractError("contract_drift_id must be non-empty")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported behavior delta schema_version")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "delta_id": self.delta_id,
            "target_id": self.target_id,
            "subject": self.subject,
            "before": self.before,
            "after": self.after,
            "source_fact_ids": list(self.source_fact_ids),
            "confidence": self.confidence,
            "status": self.status,
            "rationale": self.rationale,
        }
        if self.contract_drift_id is not None:
            result["contract_drift_id"] = self.contract_drift_id
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "BehaviorDelta":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("behavior delta must be an object")
        allowed = {
            "schema_version",
            "delta_id",
            "target_id",
            "subject",
            "before",
            "after",
            "source_fact_ids",
            "confidence",
            "status",
            "contract_drift_id",
            "rationale",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown behavior delta field(s): " + ", ".join(unknown)
            )
        try:
            raw_facts = data["source_fact_ids"]
            if not isinstance(raw_facts, list):
                raise DiscoveryContractError("behavior delta source_fact_ids must be an array")
            return cls(
                delta_id=data["delta_id"],
                target_id=data["target_id"],
                subject=data["subject"],
                before=data["before"],
                after=data["after"],
                source_fact_ids=tuple(raw_facts),
                confidence=data["confidence"],
                status=data.get("status", "inferred"),
                contract_drift_id=data.get("contract_drift_id"),
                rationale=data.get("rationale", ""),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"behavior delta requires {error.args[0]}") from error


@dataclass(frozen=True)
class RiskPriority:
    """Transparent risk factors; ``score`` is a sorting aid, not a verdict."""

    priority_id: str
    impact: float
    propagation_reach: float
    context_sensitivity: float
    uncertainty: float
    evidence_gap: float
    estimated_probe_cost: float
    rationale: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if (
            not isinstance(self.priority_id, str)
            or not isinstance(self.rationale, str)
            or not self.priority_id.strip()
            or not self.rationale.strip()
        ):
            raise DiscoveryContractError("priority_id and rationale must be non-empty")
        for field in (
            "impact",
            "propagation_reach",
            "context_sensitivity",
            "uncertainty",
            "evidence_gap",
            "estimated_probe_cost",
        ):
            value = getattr(self, field)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not 0 <= value <= 1
            ):
                raise DiscoveryContractError(f"{field} must be between 0 and 1")
        if self.schema_version != 1:
            raise DiscoveryContractError("unsupported risk priority schema_version")

    @property
    def score(self) -> float:
        """Deterministic ordering aid; it is explicitly not a probability or verdict."""

        value = (
            0.30 * self.impact
            + 0.20 * self.propagation_reach
            + 0.20 * self.context_sensitivity
            + 0.15 * self.uncertainty
            + 0.10 * self.evidence_gap
            + 0.05 * (1.0 - self.estimated_probe_cost)
        )
        return round(value, 6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "priority_id": self.priority_id,
            "impact": self.impact,
            "propagation_reach": self.propagation_reach,
            "context_sensitivity": self.context_sensitivity,
            "uncertainty": self.uncertainty,
            "evidence_gap": self.evidence_gap,
            "estimated_probe_cost": self.estimated_probe_cost,
            "rationale": self.rationale,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RiskPriority":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("risk priority must be an object")
        allowed = {
            "schema_version",
            "priority_id",
            "impact",
            "propagation_reach",
            "context_sensitivity",
            "uncertainty",
            "evidence_gap",
            "estimated_probe_cost",
            "rationale",
            "score",
        }
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise DiscoveryContractError(
                "unknown risk priority field(s): " + ", ".join(unknown)
            )
        try:
            priority = cls(
                priority_id=data["priority_id"],
                impact=data["impact"],
                propagation_reach=data["propagation_reach"],
                context_sensitivity=data["context_sensitivity"],
                uncertainty=data["uncertainty"],
                evidence_gap=data["evidence_gap"],
                estimated_probe_cost=data["estimated_probe_cost"],
                rationale=data["rationale"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"risk priority requires {error.args[0]}") from error
        if "score" in data and data["score"] != priority.score:
            raise DiscoveryContractError("risk priority score does not match its factors")
        return priority


@dataclass(frozen=True)
class RiskDerivationResult:
    """A derivation outcome that never conflates a hypothesis with a finding."""

    prior: RiskPrior
    operator: AttackOperator
    hypothesis: RiskHypothesis | None
    failure_chain: FailureChain | None
    priority: RiskPriority | None
    attack_plan: AttackPlan | None
    rejection_reasons: tuple[str, ...] = ()

    @property
    def accepted(self) -> bool:
        return self.hypothesis is not None and not self.rejection_reasons

    def __post_init__(self) -> None:
        if not isinstance(self.rejection_reasons, tuple) or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in self.rejection_reasons
        ):
            raise DiscoveryContractError("rejection_reasons must contain strings")
        if self.accepted and any(
            value is None
            for value in (self.failure_chain, self.priority, self.attack_plan)
        ):
            raise DiscoveryContractError("accepted derivation requires complete outputs")


def make_temporal_prior(operator_id: str = "operator-bounded-latency") -> RiskPrior:
    return RiskPrior(
        prior_id="prior-synchronous-critical-path-v1",
        name="synchronous critical-path temporal propagation",
        description=(
            "Prioritize bounded latency, blocking, retry, I/O, lock, wait, or "
            "availability changes that cross a synchronous critical path."
        ),
        signals=TEMPORAL_SIGNAL_TERMS,
        operator_ids=(operator_id,),
        version="m7.1",
    )


def make_latency_operator(operator_id: str = "operator-bounded-latency") -> AttackOperator:
    return AttackOperator(
        operator_id=operator_id,
        name="bounded latency or availability perturbation",
        description=(
            "Apply a bounded delay or unavailable response at one dependency "
            "boundary and observe caller contract evidence."
        ),
        action="perturb dependency latency or availability within an abort budget",
        safety_boundary="local target only; abort before unbounded wait or external side effect",
    )


def derive_synchronous_risk(
    target: DiscoveryTarget,
    graph: QualityContextGraph,
    *,
    mode: str,
    behavior_delta: BehaviorDelta | None = None,
    contract_drift: ContractDrift | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
) -> RiskDerivationResult:
    """Derive one frozen synchronous-path hypothesis or explicit rejection."""

    prior = prior or make_temporal_prior()
    operator = operator or make_latency_operator(prior.operator_ids[0])
    reasons: list[str] = []
    if mode not in {"change", "project"}:
        reasons.append("mode must be change or project")
    if graph.target_id != target.target_id:
        reasons.append("graph target does not match discovery target")
    if mode == "change" and not isinstance(target, ChangeTarget):
        reasons.append("change mode requires ChangeTarget")
    if mode == "project" and not isinstance(target, ProjectTarget):
        reasons.append("project mode requires ProjectTarget")
    if mode == "project" and behavior_delta is not None:
        reasons.append("project mode must not require a behavior delta")
    if mode == "change":
        if behavior_delta is None:
            reasons.append("change mode requires BehaviorDelta")
        elif behavior_delta.target_id != target.target_id:
            reasons.append("behavior delta target does not match discovery target")
        elif behavior_delta.status in {"unknown", "contradictory"}:
            reasons.append("behavior delta is unresolved")
        elif not _facts_are_known(graph, behavior_delta.source_fact_ids):
            reasons.append("behavior delta references unknown or contradictory facts")
        if contract_drift is None:
            reasons.append("change mode requires separate ContractDrift")
        elif contract_drift.status in {"unknown", "contradictory"}:
            reasons.append("contract drift is unresolved")
        elif not _facts_are_known(graph, contract_drift.source_fact_ids):
            reasons.append("contract drift references unknown or contradictory facts")

    candidates = _candidate_operation_paths(graph, behavior_delta, mode)
    if not candidates:
        reasons.append("no synchronous path to a critical caller was established")
    selected: tuple[ContextNode, tuple[str, ...], tuple[str, ...], ContextNode] | None = None
    if not reasons:
        for operation, node_ids, edge_ids, caller in candidates:
            if _caller_context_is_known(graph, caller):
                selected = (operation, node_ids, edge_ids, caller)
                break
        if selected is None:
            reasons.append("critical caller thread or process context is unresolved")

    if reasons:
        return RiskDerivationResult(
            prior=prior,
            operator=operator,
            hypothesis=None,
            failure_chain=None,
            priority=None,
            attack_plan=None,
            rejection_reasons=tuple(dict.fromkeys(reasons)),
        )

    operation, node_ids, edge_ids, caller = selected
    fact_ids = _path_fact_ids(graph, node_ids, edge_ids)
    quality_fact = _quality_contract_fact(graph, caller)
    if quality_fact is None:
        return _rejected(prior, operator, "critical caller has no quality contract fact")
    unknown_fact_ids = tuple(
        fact.fact_id for fact in graph.facts if fact.status == "unknown"
    )
    hypothesis_id = "hypothesis-" + _stable_id(
        target.target_id,
        mode,
        operation.label,
        ",".join(edge_ids),
    )
    chain_id = "chain-" + _stable_id(hypothesis_id, "failure-chain")
    priority_id = "priority-" + _stable_id(hypothesis_id, "priority")
    delta_id = behavior_delta.delta_id if behavior_delta is not None else None
    drift_id = contract_drift.drift_id if contract_drift is not None else None
    trigger = (
        behavior_delta.after
        if behavior_delta is not None
        else "the synchronous dependency becomes slower or unavailable"
    )
    path_labels = " -> ".join(
        next(node.label for node in graph.nodes if node.node_id == node_id)
        for node_id in node_ids
    )
    quality_property = str(quality_fact.value)
    required_evidence = (
        "dependency latency or availability observation",
        "critical caller responsiveness observation",
        "oracle evaluation against the recorded quality contract",
    )
    confidence = _confidence(graph, fact_ids, unknown_fact_ids, behavior_delta)
    hypothesis = RiskHypothesis(
        hypothesis_id=hypothesis_id,
        target_id=target.target_id,
        quality_property=quality_property,
        assumptions=(
            "the dependency call remains synchronous across the selected path",
            "the caller context and quality contract remain applicable at execution time",
        ),
        trigger=trigger,
        mechanism=f"latency propagates along {path_labels}",
        consequence=(
            f"the caller may violate its bounded quality contract: {quality_property}"
        ),
        rationale=(
            "The path, synchronous semantics, criticality, and caller context are "
            "evidence-bound; this remains a hypothesis until an admitted attack "
            "produces execution evidence."
        ),
        required_evidence=required_evidence,
        confidence=confidence,
        status="frozen",
        supporting_fact_ids=fact_ids,
        prior_id=prior.prior_id,
        failure_chain_id=chain_id,
        unknowns=tuple(
            f"fact {fact_id} remains unknown" for fact_id in unknown_fact_ids
        ),
        behavior_delta_id=delta_id,
        contract_drift_id=drift_id,
        priority_id=priority_id,
    )
    chain = FailureChain(
        chain_id=chain_id,
        steps=(
            f"local operation {operation.label} changes its temporal behavior",
            f"dependency propagation follows {path_labels}",
            f"critical caller {caller.label} must meet its response constraint",
            f"system impact is bounded by the quality contract: {quality_property}",
        ),
        consequence=quality_property,
        fact_ids=fact_ids,
        causal_roles=(
            "local_behavior",
            "dependency_propagation",
            "caller_constraint",
            "system_impact",
        ),
    )
    priority = RiskPriority(
        priority_id=priority_id,
        impact=1.0 if _fact_value(graph, caller, "criticality") in {"high", "critical"} else 0.5,
        propagation_reach=min(1.0, len(node_ids) / 6.0),
        context_sensitivity=1.0 if _path_is_synchronous(graph, edge_ids) else 0.0,
        uncertainty=min(1.0, len(unknown_fact_ids) / max(1, len(graph.facts))),
        evidence_gap=min(1.0, (len(required_evidence) + len(unknown_fact_ids)) / 5.0),
        estimated_probe_cost=0.5,
        rationale="Factors are transparent ordering aids; score is not a probability or finding.",
    )
    plan = AttackPlan(
        plan_id="plan-" + _stable_id(hypothesis_id, operator.operator_id),
        target_id=target.target_id,
        hypothesis_id=hypothesis_id,
        operator_id=operator.operator_id,
        trigger=(
            "apply a bounded latency or unavailable-response perturbation at "
            "the dependency boundary"
        ),
        observations=(
            "dependency latency and availability",
            "caller thread/process responsiveness",
            "quality-contract oracle evidence",
        ),
        evidence_expectations=required_evidence,
        oracle="quality-contract-oracle-v1",
        abort_boundary="abort before an unbounded wait, unsafe state, or external side effect",
        claim_boundary="local target, source, build, and recorded observation only",
        fixture_refs=(f"target:{target.target_id}",),
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


def derive_risk_hypothesis(*args: Any, **kwargs: Any) -> RiskDerivationResult:
    """Descriptive alias for the bounded derivation entry point."""

    return derive_synchronous_risk(*args, **kwargs)


def _rejected(
    prior: RiskPrior, operator: AttackOperator, reason: str
) -> RiskDerivationResult:
    return RiskDerivationResult(
        prior=prior,
        operator=operator,
        hypothesis=None,
        failure_chain=None,
        priority=None,
        attack_plan=None,
        rejection_reasons=(reason,),
    )


def _facts_are_known(graph: QualityContextGraph, fact_ids: tuple[str, ...]) -> bool:
    facts = {fact.fact_id: fact for fact in graph.facts}
    return all(
        facts.get(fact_id) is not None and facts[fact_id].status == "known"
        for fact_id in fact_ids
    )


def _candidate_operation_paths(
    graph: QualityContextGraph,
    behavior_delta: BehaviorDelta | None,
    mode: str,
) -> list[tuple[ContextNode, tuple[str, ...], tuple[str, ...], ContextNode]]:
    nodes = sorted(
        (node for node in graph.nodes if node.kind == "operation"),
        key=lambda item: item.node_id,
    )
    candidates: list[tuple[ContextNode, tuple[str, ...], tuple[str, ...], ContextNode]] = []
    for operation in nodes:
        if mode == "change" and behavior_delta is not None:
            if behavior_delta.subject not in {
                operation.label,
                *_subjects_for_node(graph, operation),
            }:
                continue
        for caller in sorted(
            (node for node in graph.nodes if node.kind == "component"),
            key=lambda item: item.node_id,
        ):
            path = _known_synchronous_path(graph, operation.node_id, caller.node_id)
            if path is None or not _is_critical_node(graph, caller):
                continue
            candidates.append((operation, path[0], path[1], caller))
    return candidates


def _known_synchronous_path(
    graph: QualityContextGraph, start_node_id: str, target_node_id: str
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    nodes = {node.node_id: node for node in graph.nodes}
    facts = {fact.fact_id: fact for fact in graph.facts}
    queue: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
        (start_node_id, (start_node_id,), ())
    ]
    visited = {start_node_id}
    while queue:
        current, node_path, edge_path = queue.pop(0)
        if current == target_node_id:
            return node_path, edge_path
        for edge in graph.edges:
            if edge.from_node_id != current or edge.semantics != "synchronous":
                continue
            if edge.status != "known" or nodes[edge.to_node_id].status != "known":
                continue
            if any(facts[fact_id].status != "known" for fact_id in edge.source_fact_ids):
                continue
            if edge.to_node_id in visited:
                continue
            visited.add(edge.to_node_id)
            queue.append(
                (
                    edge.to_node_id,
                    (*node_path, edge.to_node_id),
                    (*edge_path, edge.edge_id),
                )
            )
    return None


def _is_critical_node(graph: QualityContextGraph, node: ContextNode) -> bool:
    facts = {fact.fact_id: fact for fact in graph.facts}
    for fact in graph.facts:
        if fact.subject == node.label and fact.predicate == "criticality":
            return fact.status == "known" and fact.value in {"high", "critical"}
    return any(
        facts[fact_id].status == "known"
        and facts[fact_id].predicate == "criticality"
        and facts[fact_id].value in {"high", "critical"}
        for fact_id in node.source_fact_ids
    )


def _caller_context_is_known(graph: QualityContextGraph, caller: ContextNode) -> bool:
    relevant = [
        fact
        for fact in graph.facts
        if fact.subject == caller.label
        and fact.predicate in {"caller_thread", "caller_process"}
    ]
    if not relevant:
        relevant = [
            fact
            for fact_id in caller.source_fact_ids
            if (fact := graph.fact(fact_id)).predicate in {"caller_thread", "caller_process"}
        ]
    return bool(relevant) and all(fact.status == "known" for fact in relevant)


def _quality_contract_fact(graph: QualityContextGraph, caller: ContextNode) -> ContextFact | None:
    for fact in graph.facts:
        if fact.subject == caller.label and fact.predicate == "quality_contract":
            return fact if fact.status == "known" else None
    for fact_id in caller.source_fact_ids:
        fact = graph.fact(fact_id)
        if fact.predicate == "quality_contract":
            return fact if fact.status == "known" else None
    return None


def _path_fact_ids(
    graph: QualityContextGraph, node_ids: tuple[str, ...], edge_ids: tuple[str, ...]
) -> tuple[str, ...]:
    nodes = {node.node_id: node for node in graph.nodes}
    edges = {edge.edge_id: edge for edge in graph.edges}
    fact_ids: list[str] = []
    for node_id in node_ids:
        fact_ids.extend(nodes[node_id].source_fact_ids)
    for edge_id in edge_ids:
        fact_ids.extend(edges[edge_id].source_fact_ids)
    return tuple(dict.fromkeys(fact_ids))


def _subjects_for_node(graph: QualityContextGraph, node: ContextNode) -> tuple[str, ...]:
    return tuple(
        fact.subject for fact in graph.facts if fact.fact_id in node.source_fact_ids
    )


def _fact_value(graph: QualityContextGraph, node: ContextNode, predicate: str) -> Any:
    for fact_id in node.source_fact_ids:
        fact = graph.fact(fact_id)
        if fact.predicate == predicate:
            return fact.value
    return None


def _path_is_synchronous(graph: QualityContextGraph, edge_ids: tuple[str, ...]) -> bool:
    edges = {edge.edge_id: edge for edge in graph.edges}
    return all(edges[edge_id].semantics == "synchronous" for edge_id in edge_ids)


def _confidence(
    graph: QualityContextGraph,
    fact_ids: tuple[str, ...],
    unknown_fact_ids: tuple[str, ...],
    behavior_delta: BehaviorDelta | None,
) -> float:
    known_ratio = sum(graph.fact(fact_id).status == "known" for fact_id in fact_ids) / max(
        1, len(fact_ids)
    )
    value = 0.55 + 0.30 * known_ratio
    if unknown_fact_ids:
        value = min(value, 0.65)
    if behavior_delta is not None:
        value = min(value, float(behavior_delta.confidence))
    return round(value, 6)


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]
