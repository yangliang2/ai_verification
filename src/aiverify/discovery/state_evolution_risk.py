"""Fixture-neutral historical-state risk derivation for M8.

This module owns the static reasoning slice for state evolution.  It consumes
only a target, an immutable :class:`QualityContextGraph`, and (for Change
Mode) separately bound change inputs.  It stops at a frozen hypothesis and a
bounded attack plan; execution evidence and Findings remain outside this
module.
"""

from __future__ import annotations

import hashlib
from collections import deque
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
    ContextNode,
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

STATE_EVOLUTION_SIGNAL_TERMS = (
    "historical_state",
    "durable_state",
    "schema_transition",
    "migration",
    "recovery_epoch",
    "restore",
    "process_death",
    "state_continuity",
)

STATE_EVOLUTION_PRIOR_ID = "prior-state-evolution-compatibility-v1"
STATE_EVOLUTION_OPERATOR_ID = "operator-bounded-historical-state-replay"

_ROLE_PREDICATES = (
    "writes_legacy_state",
    "stores_durable_state",
    "schema_version",
    "migrates_to_schema",
    "reads_current_state",
    "crosses_recovery_boundary",
    "quality_contract",
)


def make_state_evolution_prior(
    operator_id: str = STATE_EVOLUTION_OPERATOR_ID,
) -> RiskPrior:
    """Build the single M8 state-evolution prior without target identity."""

    return RiskPrior(
        prior_id=STATE_EVOLUTION_PRIOR_ID,
        name="historical-state compatibility across recovery",
        description=(
            "Prioritize provenance-bound writer, durable-storage, schema-"
            "transition, reader, and recovery paths where historical state "
            "must remain compatible with a known quality contract."
        ),
        signals=STATE_EVOLUTION_SIGNAL_TERMS,
        operator_ids=(operator_id,),
        version="m8.1",
    )


def make_historical_state_replay_operator(
    operator_id: str = STATE_EVOLUTION_OPERATOR_ID,
) -> AttackOperator:
    """Build the bounded historical-state replay operator."""

    return AttackOperator(
        operator_id=operator_id,
        name="bounded historical-state replay",
        description=(
            "Create or import one historical state, then observe one bounded "
            "upgrade and recovery epoch at the recorded state boundary."
        ),
        action=(
            "create or import one old state and run one bounded local "
            "upgrade/recovery epoch"
        ),
        safety_boundary=(
            "local target only; reversible state and one attempt; abort before "
            "an unbounded wait, unsafe state, or external side effect"
        ),
    )


# The shorter name is useful to callers that already use the family name.
make_state_evolution_operator = make_historical_state_replay_operator


def make_state_evolution_strategy(
    *,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
) -> RiskDerivationStrategy:
    """Return the versioned M8 strategy for both target modes."""

    selected_operator = operator or make_historical_state_replay_operator(
        prior.operator_ids[0] if prior is not None else STATE_EVOLUTION_OPERATOR_ID
    )
    selected_prior = prior or make_state_evolution_prior(selected_operator.operator_id)

    def derive_state_evolution(
        target: DiscoveryTarget,
        graph: QualityContextGraph,
        *,
        mode: str,
        behavior_delta: BehaviorDelta | None = None,
        contract_drift: ContractDrift | None = None,
    ) -> RiskDerivationResult:
        return derive_state_evolution_risk(
            target,
            graph,
            mode=mode,
            behavior_delta=behavior_delta,
            contract_drift=contract_drift,
            prior=selected_prior,
            operator=selected_operator,
        )

    return RiskDerivationStrategy(
        strategy_id="strategy-state-evolution-compatibility-v1",
        version="m8.1",
        compatible_prior_ids=(selected_prior.prior_id,),
        compatible_operator_ids=(selected_operator.operator_id,),
        target_modes=("change", "project"),
        deriver=derive_state_evolution,
    )


def derive_state_evolution_risk(
    target: DiscoveryTarget,
    graph: QualityContextGraph,
    *,
    mode: str,
    behavior_delta: BehaviorDelta | None = None,
    contract_drift: ContractDrift | None = None,
    prior: RiskPrior | None = None,
    operator: AttackOperator | None = None,
) -> RiskDerivationResult:
    """Derive one bounded historical-state compatibility hypothesis.

    Required state facts are checked independently of the graph labels.  The
    accepted path is therefore reusable across a ChangeTarget and a
    ProjectTarget while still rejecting missing, stale, contradictory, or
    mismatched history before a Run Spec or device action exists.
    """

    prior = prior or make_state_evolution_prior(
        operator.operator_id if operator is not None else STATE_EVOLUTION_OPERATOR_ID
    )
    operator = operator or make_historical_state_replay_operator(prior.operator_ids[0])
    reasons: list[str] = []

    if mode not in {"change", "project"}:
        reasons.append("mode must be change or project")
    if not isinstance(target, (ChangeTarget, ProjectTarget)):
        reasons.append("state-evolution target must be ChangeTarget or ProjectTarget")
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

    selected = _required_facts(graph, reasons)
    _reject_unresolved_graph_state(graph, reasons)

    if mode == "change":
        _validate_change_inputs(graph, target, behavior_delta, contract_drift, reasons)

    if selected is not None:
        _validate_state_values(selected, reasons)
        path = _state_path(graph, selected, reasons)
    else:
        path = None

    if reasons:
        return _rejected_state(prior, operator, *dict.fromkeys(reasons))
    assert selected is not None
    assert path is not None

    fact_ids = _path_fact_ids(graph, selected, path)
    unknowns = tuple(
        f"fact {fact.fact_id} remains {fact.status}"
        for fact in sorted(graph.facts, key=lambda item: item.fact_id)
        if fact.status == "unknown"
    )
    delta_id = behavior_delta.delta_id if behavior_delta is not None else None
    drift_id = contract_drift.drift_id if contract_drift is not None else None
    identity = _stable_id(
        target.target_id,
        mode,
        ",".join(path[1]),
        delta_id or "",
        drift_id or "",
    )
    hypothesis_id = f"hypothesis-state-evolution-{identity}"
    chain_id = f"chain-state-evolution-{_stable_id(hypothesis_id, 'chain')}"
    priority_id = f"priority-state-evolution-{_stable_id(hypothesis_id, 'priority')}"
    quality_property = "durable state continuity across a bounded recovery epoch"
    required_evidence = (
        "historical-state identity before the bounded epoch",
        "schema transition and migration-count observation",
        "state continuity observation after the bounded epoch",
        "oracle evaluation against the recorded quality contract",
    )
    confidence = _confidence(graph, fact_ids, behavior_delta)

    hypothesis = RiskHypothesis(
        hypothesis_id=hypothesis_id,
        target_id=target.target_id,
        quality_property=quality_property,
        assumptions=(
            "the recorded writer and durable storage remain the active state path",
            "the recorded schema transition and reader remain applicable",
            "the recovery epoch stays within the local abort boundary",
        ),
        trigger=(
            "a historical state is made available before one bounded recovery "
            "epoch"
            if mode == "project"
            else "the changed state transition alters historical-state compatibility"
        ),
        mechanism=(
            "historical state must traverse the legacy writer, durable storage, "
            "schema transition, current reader, and recovery boundary"
        ),
        consequence=(
            "the durable state continuity contract may be violated across the "
            "bounded recovery epoch"
        ),
        rationale=(
            "The complete causal path and its supporting facts are known and "
            "provenance-bound. This remains a hypothesis until an admitted "
            "local attack produces accountable runtime evidence."
        ),
        required_evidence=required_evidence,
        confidence=confidence,
        status="frozen",
        supporting_fact_ids=fact_ids,
        prior_id=prior.prior_id,
        failure_chain_id=chain_id,
        unknowns=unknowns,
        behavior_delta_id=delta_id,
        contract_drift_id=drift_id,
        priority_id=priority_id,
    )
    chain = FailureChain(
        chain_id=chain_id,
        steps=(
            "a historical state enters the writer and durable-storage path",
            "the schema transition applies one migration boundary",
            "the current reader consumes the transitioned representation",
            "the recovery boundary exercises the continuity contract",
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
        impact=0.9,
        propagation_reach=min(1.0, len(path[0]) / 8.0),
        context_sensitivity=1.0,
        uncertainty=min(1.0, len(unknowns) / max(1, len(graph.facts))),
        evidence_gap=min(1.0, len(required_evidence) / 6.0),
        estimated_probe_cost=0.6,
        rationale=(
            "Transparent factors order a bounded probe; the score is not a "
            "probability or execution evidence."
        ),
    )
    plan = AttackPlan(
        plan_id=f"plan-state-evolution-{_stable_id(hypothesis_id, operator.operator_id)}",
        target_id=target.target_id,
        hypothesis_id=hypothesis_id,
        operator_id=operator.operator_id,
        trigger=(
            "make one historical state available and observe one bounded local "
            "upgrade/recovery epoch"
        ),
        observations=(
            "historical-state identity and schema",
            "migration edge and exactly-once count",
            "state continuity at the recovery boundary",
        ),
        evidence_expectations=required_evidence,
        oracle="quality-contract-oracle-v1",
        abort_boundary=(
            "abort before an unbounded wait, unsafe state, or external side effect"
        ),
        claim_boundary=(
            "local target, provenance-bound source, build, and recorded observation only"
        ),
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


def _required_facts(
    graph: QualityContextGraph,
    reasons: list[str],
) -> dict[str, ContextFact] | None:
    by_predicate: dict[str, list[ContextFact]] = {}
    for fact in graph.facts:
        by_predicate.setdefault(fact.predicate, []).append(fact)
    selected: dict[str, ContextFact] = {}
    for predicate in _ROLE_PREDICATES:
        matches = sorted(by_predicate.get(predicate, ()), key=lambda item: item.fact_id)
        if not matches:
            reasons.append(f"missing required state fact: {predicate}")
            continue
        if len(matches) != 1:
            reasons.append(f"ambiguous state fact predicate: {predicate}")
            continue
        fact = matches[0]
        if fact.status != "known":
            reasons.append(f"state fact {fact.fact_id} is {fact.status}")
            continue
        if not fact.provenance:
            reasons.append(f"state fact {fact.fact_id} lacks provenance")
            continue
        selected[predicate] = fact
    return selected if len(selected) == len(_ROLE_PREDICATES) else None


def _reject_unresolved_graph_state(
    graph: QualityContextGraph,
    reasons: list[str],
) -> None:
    for fact in sorted(graph.facts, key=lambda item: item.fact_id):
        if fact.status in {"contradictory", "stale"}:
            reasons.append(f"state fact {fact.fact_id} is {fact.status}")
    for node in sorted(graph.nodes, key=lambda item: item.node_id):
        if node.status in {"contradictory", "stale"}:
            reasons.append(f"state node {node.node_id} is {node.status}")
    for edge in sorted(graph.edges, key=lambda item: item.edge_id):
        if edge.status in {"contradictory", "stale"}:
            reasons.append(f"state edge {edge.edge_id} is {edge.status}")


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
        if not delta.contract_drift_id:
            reasons.append("behavior delta must bind a contract drift")
        if drift is not None and delta.contract_drift_id != drift.drift_id:
            reasons.append("behavior delta and contract drift do not match")
        _validate_binding_facts(graph, delta.source_fact_ids, "behavior delta", reasons)
    if drift is None:
        reasons.append("change mode requires separate ContractDrift")
    else:
        if drift.status in {"unknown", "contradictory"}:
            reasons.append("contract drift is unresolved")
        _validate_binding_facts(graph, drift.source_fact_ids, "contract drift", reasons)


def _validate_binding_facts(
    graph: QualityContextGraph,
    fact_ids: tuple[str, ...],
    label: str,
    reasons: list[str],
) -> None:
    facts = {fact.fact_id: fact for fact in graph.facts}
    for fact_id in fact_ids:
        fact = facts.get(fact_id)
        if fact is None:
            reasons.append(f"{label} references missing fact: {fact_id}")
        elif fact.status != "known":
            reasons.append(f"{label} fact {fact_id} is {fact.status}")
        elif not fact.provenance:
            reasons.append(f"{label} fact {fact_id} lacks provenance")


def _validate_state_values(
    selected: Mapping[str, ContextFact],
    reasons: list[str],
) -> None:
    writer_value = selected["writes_legacy_state"].value
    schema_value = selected["schema_version"].value
    migration_value = selected["migrates_to_schema"].value
    reader_value = selected["reads_current_state"].value
    storage_value = selected["stores_durable_state"].value
    recovery_value = selected["crosses_recovery_boundary"].value
    quality_value = selected["quality_contract"].value
    if not isinstance(storage_value, str) or not storage_value.strip():
        reasons.append("state storage fact is malformed")
    if not isinstance(recovery_value, list) or not recovery_value:
        reasons.append("recovery boundary fact is malformed")
    if not isinstance(quality_value, str) or not quality_value.strip():
        reasons.append("quality contract fact is malformed")
    if not isinstance(writer_value, Mapping) or not isinstance(reader_value, Mapping):
        reasons.append("state writer or reader fact is malformed")
        return
    if not isinstance(migration_value, Mapping):
        reasons.append("schema migration fact is malformed")
        return
    if not isinstance(schema_value, int) or isinstance(schema_value, bool):
        reasons.append("legacy schema fact is malformed")
        return
    fields = ("schema_version", "revision")
    if any(field not in writer_value for field in fields) or any(
        field not in reader_value for field in fields
    ):
        reasons.append("state writer or reader fact is missing schema fields")
        return
    migration_fields = (
        "from",
        "to",
        "from_revision",
        "to_revision",
        "exactly_once",
    )
    if any(field not in migration_value for field in migration_fields):
        reasons.append("schema migration fact is missing transition fields")
        return
    if writer_value["schema_version"] != schema_value:
        reasons.append("state schema facts mismatch at legacy writer")
    if migration_value["from"] != schema_value:
        reasons.append("state schema migration mismatch with legacy schema")
    if migration_value["from_revision"] != writer_value["revision"]:
        reasons.append("state migration source revision mismatch with writer")
    if migration_value["to"] != reader_value["schema_version"]:
        reasons.append("state migration target schema mismatch with reader")
    if migration_value["to_revision"] != reader_value["revision"]:
        reasons.append("state migration target revision mismatch with reader")
    if migration_value["exactly_once"] is not True:
        reasons.append("state migration must be exactly once")


def _state_path(
    graph: QualityContextGraph,
    selected: Mapping[str, ContextFact],
    reasons: list[str],
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    role_nodes: dict[str, tuple[ContextNode, ...]] = {}
    for predicate, fact in selected.items():
        role_nodes[predicate] = tuple(
            sorted(
                (
                    node
                    for node in graph.nodes
                    if fact.fact_id in node.source_fact_ids and node.status == "known"
                ),
                key=lambda item: item.node_id,
            )
        )
        if not role_nodes[predicate]:
            reasons.append(f"state fact {fact.fact_id} has no known graph node")
    if any(not nodes for nodes in role_nodes.values()):
        return None

    ordered_predicates = _ROLE_PREDICATES
    candidate_paths: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def walk(
        index: int,
        node_path: tuple[str, ...],
        edge_path: tuple[str, ...],
    ) -> None:
        if index == len(ordered_predicates) - 1:
            candidate_paths.append((node_path, edge_path))
            return
        next_predicate = ordered_predicates[index + 1]
        for next_node in role_nodes[next_predicate]:
            segment = _known_synchronous_path(graph, node_path[-1], next_node.node_id)
            if segment is None:
                continue
            segment_nodes, segment_edges = segment
            walk(
                index + 1,
                (*node_path, *segment_nodes[1:]),
                (*edge_path, *segment_edges),
            )

    for start in role_nodes[ordered_predicates[0]]:
        walk(0, (start.node_id,), ())
    if not candidate_paths:
        reasons.append(
            "no connected provenance-bound synchronous writer/storage/schema-transition/reader/recovery path"
        )
        return None
    return min(candidate_paths, key=lambda item: (item[1], item[0]))


def _known_synchronous_path(
    graph: QualityContextGraph,
    start_node_id: str,
    target_node_id: str,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    nodes = {node.node_id: node for node in graph.nodes}
    facts = {fact.fact_id: fact for fact in graph.facts}
    queue: deque[tuple[str, tuple[str, ...], tuple[str, ...]]] = deque(
        [(start_node_id, (start_node_id,), ())]
    )
    visited = {start_node_id}
    while queue:
        current, node_path, edge_path = queue.popleft()
        if current == target_node_id:
            return node_path, edge_path
        current_node = nodes.get(current)
        if current_node is None or not _node_is_provenance_bound(current_node, facts):
            continue
        edges = sorted(
            (edge for edge in graph.edges if edge.from_node_id == current),
            key=lambda item: item.edge_id,
        )
        for edge in edges:
            if edge.semantics != "synchronous" or edge.status != "known":
                continue
            destination = nodes.get(edge.to_node_id)
            if (
                destination is None
                or destination.status != "known"
                or not _node_is_provenance_bound(destination, facts)
            ):
                continue
            edge_facts = (facts[fact_id] for fact_id in edge.source_fact_ids)
            if any(fact.status != "known" or not fact.provenance for fact in edge_facts):
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


def _node_is_provenance_bound(
    node: ContextNode,
    facts: Mapping[str, ContextFact],
) -> bool:
    return all(
        (fact := facts.get(fact_id)) is not None
        and fact.status == "known"
        and bool(fact.provenance)
        for fact_id in node.source_fact_ids
    )


def _path_fact_ids(
    graph: QualityContextGraph,
    selected: Mapping[str, ContextFact],
    path: tuple[tuple[str, ...], tuple[str, ...]],
) -> tuple[str, ...]:
    nodes = {node.node_id: node for node in graph.nodes}
    edges = {edge.edge_id: edge for edge in graph.edges}
    fact_ids: list[str] = [selected[predicate].fact_id for predicate in _ROLE_PREDICATES]
    for node_id in path[0]:
        fact_ids.extend(nodes[node_id].source_fact_ids)
    for edge_id in path[1]:
        fact_ids.extend(edges[edge_id].source_fact_ids)
    return tuple(dict.fromkeys(fact_ids))


def _confidence(
    graph: QualityContextGraph,
    fact_ids: tuple[str, ...],
    delta: BehaviorDelta | None,
) -> float:
    known = sum(graph.fact(fact_id).status == "known" for fact_id in fact_ids)
    ratio = known / max(1, len(fact_ids))
    value = 0.70 + 0.20 * ratio
    if delta is not None:
        value = min(value, float(delta.confidence))
    return round(value, 6)


def _rejected_state(
    prior: RiskPrior,
    operator: AttackOperator,
    *reasons: str,
) -> RiskDerivationResult:
    if not reasons:
        raise DiscoveryContractError("state-evolution rejection requires a reason")
    return RiskDerivationResult(
        prior=prior,
        operator=operator,
        hypothesis=None,
        failure_chain=None,
        priority=None,
        attack_plan=None,
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


def _stable_id(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


__all__ = [
    "STATE_EVOLUTION_OPERATOR_ID",
    "STATE_EVOLUTION_PRIOR_ID",
    "STATE_EVOLUTION_SIGNAL_TERMS",
    "derive_state_evolution_risk",
    "make_historical_state_replay_operator",
    "make_state_evolution_operator",
    "make_state_evolution_prior",
    "make_state_evolution_strategy",
]
