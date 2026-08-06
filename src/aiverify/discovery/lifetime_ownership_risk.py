"""Bounded lifecycle and ownership-drift risk derivation for M9.

This family is intentionally parallel to the existing temporal and state
evolution derivations.  It consumes only a target and immutable context, and
stops at a frozen hypothesis/plan boundary.  It does not execute a task,
cancel a resource, or inspect an outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

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
    DiscoveryContractError,
    DiscoveryTarget,
    ProjectTarget,
    QualityContextGraph,
)
from aiverify.discovery.risk import (
    BehaviorDelta,
    RiskDerivationResult,
    RiskDerivationStrategy,
    RiskPriority,
)


LIFETIME_OWNERSHIP_SIGNAL_TERMS = (
    "lifecycle",
    "ownership",
    "coroutine",
    "task",
    "cancellation",
    "resource",
    "dispose",
    "close",
    "scope",
)
LIFETIME_OWNERSHIP_PRIOR_ID = "prior-lifetime-ownership-drift-v1"
LIFETIME_OWNERSHIP_OPERATOR_ID = "operator-bounded-lifecycle-ownership-drift"


def _stable_id(*parts: str) -> str:
    encoded = json.dumps(parts, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def make_lifetime_ownership_prior(
    operator_id: str = LIFETIME_OWNERSHIP_OPERATOR_ID,
) -> RiskPrior:
    """Return the versioned M9 lifecycle/ownership prior."""

    return RiskPrior(
        prior_id=LIFETIME_OWNERSHIP_PRIOR_ID,
        name="lifecycle and resource ownership drift",
        description=(
            "Prioritize lifecycle-bound coroutine, task, cancellation, close, "
            "and resource ownership paths whose lifetime may drift from the "
            "recorded quality contract."
        ),
        signals=LIFETIME_OWNERSHIP_SIGNAL_TERMS,
        operator_ids=(operator_id,),
        version="m9.1",
    )


def make_lifetime_ownership_operator(
    operator_id: str = LIFETIME_OWNERSHIP_OPERATOR_ID,
) -> AttackOperator:
    """Return the bounded local ownership/cancellation operator vocabulary."""

    return AttackOperator(
        operator_id=operator_id,
        name="bounded lifecycle ownership drift",
        description=(
            "Observe one locally bounded cancellation, disposal, or lifecycle "
            "boundary while preserving the recorded resource owner."
        ),
        action=(
            "apply one bounded lifecycle or ownership boundary observation "
            "without an unbounded task or resource wait"
        ),
        safety_boundary=(
            "local target only; reversible fixture and one bounded attempt; "
            "abort before unsafe state or external side effect"
        ),
    )


# Family-name aliases make the registry ergonomic without duplicating contracts.
make_lifecycle_ownership_prior = make_lifetime_ownership_prior
make_lifecycle_ownership_operator = make_lifetime_ownership_operator


def make_lifetime_ownership_strategy(
    *,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
) -> RiskDerivationStrategy:
    """Return a pure strategy for the lifetime/ownership family."""

    selected_prior = prior or make_lifetime_ownership_prior(
        operator.operator_id if operator is not None else LIFETIME_OWNERSHIP_OPERATOR_ID
    )
    selected_operator = operator or make_lifetime_ownership_operator(
        selected_prior.operator_ids[0]
    )

    def derive(
        target: DiscoveryTarget,
        graph: QualityContextGraph,
        *,
        mode: str,
        behavior_delta: BehaviorDelta | None = None,
        contract_drift: ContractDrift | None = None,
    ) -> RiskDerivationResult:
        return derive_lifetime_ownership_risk(
            target,
            graph,
            mode=mode,
            behavior_delta=behavior_delta,
            contract_drift=contract_drift,
            prior=selected_prior,
            operator=selected_operator,
        )

    return RiskDerivationStrategy(
        strategy_id="strategy-lifetime-ownership-drift-v1",
        version="m9.1",
        compatible_prior_ids=(selected_prior.prior_id,),
        compatible_operator_ids=(selected_operator.operator_id,),
        target_modes=("change", "project"),
        deriver=derive,
    )


def derive_lifetime_ownership_risk(
    target: DiscoveryTarget,
    graph: QualityContextGraph,
    *,
    mode: str,
    behavior_delta: BehaviorDelta | None = None,
    contract_drift: ContractDrift | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
) -> RiskDerivationResult:
    """Derive one bounded lifecycle/ownership hypothesis or explicit rejection."""

    prior = prior or make_lifetime_ownership_prior(
        operator.operator_id if operator is not None else LIFETIME_OWNERSHIP_OPERATOR_ID
    )
    operator = operator or make_lifetime_ownership_operator(prior.operator_ids[0])
    reasons: list[str] = []
    if mode not in {"change", "project"}:
        reasons.append("mode must be change or project")
    if not isinstance(target, (ChangeTarget, ProjectTarget)):
        reasons.append("lifetime ownership target must be ChangeTarget or ProjectTarget")
    if graph.target_id != target.target_id:
        reasons.append("graph target does not match discovery target")
    if operator.operator_id not in prior.operator_ids:
        reasons.append("attack operator is not compatible with selected risk prior")
    if mode == "change" and not isinstance(target, ChangeTarget):
        reasons.append("change mode requires ChangeTarget")
    if mode == "project" and not isinstance(target, ProjectTarget):
        reasons.append("project mode requires ProjectTarget")
    if mode == "project" and behavior_delta is not None:
        reasons.append("project mode must not require a behavior delta")
    if mode == "project" and contract_drift is not None:
        reasons.append("project mode must not require contract drift")

    selected = _select_facts(graph, reasons)
    if mode == "change":
        _validate_change_inputs(graph, target, behavior_delta, contract_drift, reasons)
    if reasons:
        return _rejected(prior, operator, *dict.fromkeys(reasons))
    assert selected is not None

    fact_ids = tuple(fact.fact_id for fact in selected)
    quality_property = _quality_property(selected)
    identity = _stable_id(target.target_id, mode, *fact_ids)
    hypothesis_id = f"hypothesis-lifetime-ownership-{identity}"
    chain_id = f"chain-lifetime-ownership-{_stable_id(hypothesis_id, 'chain')}"
    priority_id = f"priority-lifetime-ownership-{_stable_id(hypothesis_id, 'priority')}"
    hypothesis = RiskHypothesis(
        hypothesis_id=hypothesis_id,
        target_id=target.target_id,
        quality_property=quality_property,
        assumptions=(
            "the recorded lifecycle and ownership boundaries remain applicable",
            "one bounded local observation does not introduce an external side effect",
        ),
        trigger=(
            "one lifecycle boundary cancels, disposes, or releases a resource "
            "while its task remains active"
        ),
        mechanism=(
            "the task or resource lifetime crosses the recorded owner boundary "
            "without a verified cancellation or disposal handoff"
        ),
        consequence=(
            "the recorded lifecycle ownership contract may be violated: "
            + quality_property
        ),
        rationale=(
            "The lifecycle and ownership facts are provenance-bound. This remains "
            "a hypothesis until an admitted bounded observation produces evidence."
        ),
        required_evidence=(
            "owner and lifecycle boundary identity",
            "bounded cancellation or disposal observation",
            "resource release and quality-contract observation",
        ),
        confidence=min(fact.confidence for fact in selected),
        status="frozen",
        supporting_fact_ids=fact_ids,
        prior_id=prior.prior_id,
        failure_chain_id=chain_id,
        unknowns=(),
        behavior_delta_id=behavior_delta.delta_id if behavior_delta is not None else None,
        contract_drift_id=contract_drift.drift_id if contract_drift is not None else None,
        priority_id=priority_id,
    )
    chain = FailureChain(
        chain_id=chain_id,
        steps=(
            "a lifecycle-bound operation owns a task or resource",
            "the owner boundary applies cancellation or disposal",
            "the resource lifetime crosses the recorded handoff",
            f"the quality contract is exposed: {quality_property}",
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
        impact=0.8,
        propagation_reach=min(1.0, len(fact_ids) / 4.0),
        context_sensitivity=1.0,
        uncertainty=0.0,
        evidence_gap=min(1.0, len(hypothesis.required_evidence) / 6.0),
        estimated_probe_cost=0.55,
        rationale=(
            "Transparent factors order a bounded ownership probe; the score is "
            "not a probability or execution evidence."
        ),
    )
    plan = AttackPlan(
        plan_id=f"plan-lifetime-ownership-{_stable_id(hypothesis_id, operator.operator_id)}",
        target_id=target.target_id,
        hypothesis_id=hypothesis_id,
        operator_id=operator.operator_id,
        trigger="observe one bounded lifecycle cancellation or ownership handoff",
        observations=(
            "lifecycle owner and task/resource identity",
            "cancellation or disposal boundary",
            "quality-contract evidence after the bounded observation",
        ),
        evidence_expectations=hypothesis.required_evidence,
        oracle="quality-contract-oracle-v1",
        abort_boundary=(
            "abort before an unbounded task, unsafe resource state, or external side effect"
        ),
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


def _select_facts(
    graph: QualityContextGraph,
    reasons: list[str],
) -> tuple[ContextFact, ...] | None:
    by_predicate: dict[str, list[ContextFact]] = {}
    for fact in graph.facts:
        by_predicate.setdefault(fact.predicate, []).append(fact)
    selected: list[ContextFact] = []
    for predicates, label in (
        (("lifecycle_boundary",), "lifecycle boundary"),
        (("ownership_boundary",), "ownership boundary"),
        (("quality_contract", "quality_contract_signal"), "quality contract"),
    ):
        matches = sorted(
            (
                fact
                for predicate in predicates
                for fact in by_predicate.get(predicate, ())
                if fact.status == "known" and fact.provenance
            ),
            key=lambda item: item.fact_id,
        )
        if not matches:
            reasons.append(f"missing known lifetime ownership fact: {label}")
            continue
        selected.append(matches[0])
    for fact in graph.facts:
        if fact.status in {"contradictory", "stale"}:
            reasons.append(f"lifetime ownership context fact {fact.fact_id} is {fact.status}")
    return tuple(selected) if len(selected) == 3 else None


def _quality_property(facts: tuple[ContextFact, ...]) -> str:
    quality = facts[-1].value
    return quality.strip() if isinstance(quality, str) and quality.strip() else "lifecycle ownership continuity"


def _validate_change_inputs(
    graph: QualityContextGraph,
    target: DiscoveryTarget,
    delta: BehaviorDelta | None,
    drift: ContractDrift | None,
    reasons: list[str],
) -> None:
    if delta is None:
        reasons.append("change mode requires BehaviorDelta")
    else:
        if delta.target_id != target.target_id:
            reasons.append("behavior delta target does not match discovery target")
        if delta.status in {"unknown", "contradictory"}:
            reasons.append("behavior delta is unresolved")
        if not _known_facts(graph, delta.source_fact_ids):
            reasons.append("behavior delta references unknown or contradictory facts")
    if drift is None:
        reasons.append("change mode requires separate ContractDrift")
    else:
        if drift.status in {"unknown", "contradictory"}:
            reasons.append("contract drift is unresolved")
        if not _known_facts(graph, drift.source_fact_ids):
            reasons.append("contract drift references unknown or contradictory facts")


def _known_facts(graph: QualityContextGraph, fact_ids: tuple[str, ...]) -> bool:
    facts = {fact.fact_id: fact for fact in graph.facts}
    return all(
        facts.get(fact_id) is not None
        and facts[fact_id].status == "known"
        and bool(facts[fact_id].provenance)
        for fact_id in fact_ids
    )


def _rejected(
    prior: RiskPrior,
    operator: AttackOperator,
    *reasons: str,
) -> RiskDerivationResult:
    if not reasons:
        raise DiscoveryContractError("rejected derivation requires an explicit reason")
    return RiskDerivationResult(
        prior=prior,
        operator=operator,
        hypothesis=None,
        failure_chain=None,
        priority=None,
        attack_plan=None,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


__all__ = [
    "LIFETIME_OWNERSHIP_OPERATOR_ID",
    "LIFETIME_OWNERSHIP_PRIOR_ID",
    "LIFETIME_OWNERSHIP_SIGNAL_TERMS",
    "derive_lifetime_ownership_risk",
    "make_lifecycle_ownership_operator",
    "make_lifecycle_ownership_prior",
    "make_lifetime_ownership_operator",
    "make_lifetime_ownership_prior",
    "make_lifetime_ownership_strategy",
]
