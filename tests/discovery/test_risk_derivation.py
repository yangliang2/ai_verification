from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from aiverify.discovery import (
    BehaviorDelta,
    ChangeTarget,
    ContextFact,
    ContractDrift,
    ProjectTarget,
    QualityContextGraph,
    RiskPriority,
    admit_attack_plan,
    derive_synchronous_risk,
    load_context_manifest,
    make_latency_operator,
    make_temporal_prior,
    validate_contract,
)


_FIXTURE = Path("bench/discovery-fixtures/synchronous-weather/context-manifest.json")


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-weather-001",
        source_origin="https://example.invalid/aiverify-discovery-fixture",
        source_commit="fixture-commit-v1",
        worktree="/workspace/discovery-fixture",
        scope=("weather-service", "systemui-consumer"),
        discovery_budget=8,
    )


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-weather-001",
        source_origin="https://example.invalid/aiverify-discovery-fixture",
        source_commit="fixture-commit-v1",
        worktree="/workspace/discovery-fixture",
        diff_ref="change.diff",
        diff_sha256="a" * 64,
    )


def _change_inputs() -> tuple[BehaviorDelta, ContractDrift]:
    return (
        BehaviorDelta(
            delta_id="delta-weather-delay",
            target_id="change-weather-001",
            subject="WeatherService.current",
            before="returns promptly",
            after="may wait before returning",
            source_fact_ids=("fact-service-operation",),
            confidence=0.85,
            status="inferred",
            contract_drift_id="drift-weather-latency",
            rationale="The change description changes a temporal assumption.",
        ),
        ContractDrift(
            drift_id="drift-weather-latency",
            contract_id="contract-ui-latency",
            before="dependency returns within the caller budget",
            after="dependency may wait before returning",
            delta="synchronous temporal budget widened",
            source_fact_ids=("fact-service-operation",),
            rationale="This is an inferred drift, not an observed outcome.",
        ),
    )


def test_project_mode_derives_frozen_hypothesis_chain_priority_and_plan() -> None:
    target = _project_target()
    graph = load_context_manifest(_FIXTURE, target).graph

    result = derive_synchronous_risk(target, graph, mode="project")

    assert result.accepted is True
    assert result.hypothesis is not None
    assert result.hypothesis.status == "frozen"
    assert result.hypothesis.behavior_delta_id is None
    assert result.hypothesis.failure_chain_id == result.failure_chain.chain_id
    assert result.failure_chain.causal_roles == (
        "local_behavior",
        "dependency_propagation",
        "caller_constraint",
        "system_impact",
    )
    assert result.priority.score < 1.0
    assert result.attack_plan.status == "frozen"
    assert admit_attack_plan(result.attack_plan, result.hypothesis, graph).admitted is True
    validate_contract(result.hypothesis.to_dict(), "risk_hypothesis")
    validate_contract(result.failure_chain.to_dict(), "failure_chain")
    validate_contract(result.priority.to_dict(), "risk_priority")
    validate_contract(result.attack_plan.to_dict(), "attack_plan")


def test_change_mode_keeps_behavior_delta_and_contract_drift_separate() -> None:
    target = _change_target()
    graph = load_context_manifest(_FIXTURE, target).graph
    delta, drift = _change_inputs()

    result = derive_synchronous_risk(
        target,
        graph,
        mode="change",
        behavior_delta=delta,
        contract_drift=drift,
    )

    assert result.accepted is True
    assert result.hypothesis.behavior_delta_id == delta.delta_id
    assert result.hypothesis.contract_drift_id == drift.drift_id
    assert result.hypothesis.status != "supported"
    assert "observed outcome" in drift.rationale
    validate_contract(delta.to_dict(), "behavior_delta")


def test_derivation_is_deterministic_and_priority_score_is_not_truth() -> None:
    target = _project_target()
    graph = load_context_manifest(_FIXTURE, target).graph

    first = derive_synchronous_risk(target, graph, mode="project")
    second = derive_synchronous_risk(target, graph, mode="project")

    assert first == second
    assert first.priority.to_dict()["score"] == first.priority.score
    assert "not a probability" in first.priority.rationale
    assert "defect" not in json.dumps(first.hypothesis.to_dict()).lower()
    assert "verdict" not in json.dumps(first.attack_plan.to_dict()).lower()
    assert "journey" not in json.dumps(first.attack_plan.to_dict()).lower()


def test_async_boundary_does_not_produce_high_confidence_hypothesis() -> None:
    target = _project_target()
    loaded = load_context_manifest(_FIXTURE, target).graph
    edges = tuple(
        replace(edge, semantics="asynchronous")
        if edge.edge_id == "edge-api-consumer"
        else edge
        for edge in loaded.edges
    )
    graph = QualityContextGraph(
        graph_id=loaded.graph_id,
        target_id=loaded.target_id,
        facts=loaded.facts,
        nodes=loaded.nodes,
        edges=edges,
    )

    result = derive_synchronous_risk(target, graph, mode="project")

    assert result.accepted is False
    assert result.hypothesis is None
    assert result.priority is None
    assert "synchronous path" in " ".join(result.rejection_reasons)


def test_unknown_caller_context_is_explicit_and_rejected_for_derivation() -> None:
    target = _project_target()
    loaded = load_context_manifest(_FIXTURE, target).graph
    unknown_thread = ContextFact(
        fact_id="fact-caller-thread",
        subject="SystemUiWeatherConsumer.refresh",
        predicate="caller_thread",
        value=None,
        source_kind="unknown",
        provenance=(),
        source_version="synchronous-weather-v1",
        confidence=0.0,
        status="unknown",
        rationale="The caller thread was not established.",
    )
    facts = tuple(
        unknown_thread if fact.fact_id == unknown_thread.fact_id else fact
        for fact in loaded.facts
    )
    graph = QualityContextGraph(
        graph_id=loaded.graph_id,
        target_id=loaded.target_id,
        facts=facts,
        nodes=loaded.nodes,
        edges=loaded.edges,
    )

    result = derive_synchronous_risk(target, graph, mode="project")

    assert result.accepted is False
    assert any("caller" in reason for reason in result.rejection_reasons)


def test_contradictory_graph_evidence_does_not_become_a_finding() -> None:
    target = _project_target()
    loaded = load_context_manifest(_FIXTURE, target).graph
    contradictory = ContextFact(
        fact_id="fact-sync-call",
        subject="SystemUiWeatherConsumer.refresh",
        predicate="calls_synchronously",
        value="unknown",
        source_kind="observed",
        provenance=(
            # Deliberately distinct evidence keeps contradiction explicit.
            loaded.fact("fact-sync-call").provenance[0],
        ),
        source_version="trace-contradictory",
        confidence=0.3,
        status="contradictory",
    )
    facts = tuple(
        contradictory if fact.fact_id == contradictory.fact_id else fact
        for fact in loaded.facts
    )
    graph = QualityContextGraph(
        graph_id=loaded.graph_id,
        target_id=loaded.target_id,
        facts=facts,
        nodes=loaded.nodes,
        edges=loaded.edges,
    )

    result = derive_synchronous_risk(target, graph, mode="project")

    assert result.accepted is False
    assert result.hypothesis is None
    assert result.rejection_reasons


def test_behavior_delta_and_priority_round_trip_and_tamper_rejection() -> None:
    delta, _ = _change_inputs()
    restored_delta = BehaviorDelta.from_dict(delta.to_dict())
    assert restored_delta == delta

    priority = RiskPriority(
        priority_id="priority-001",
        impact=0.8,
        propagation_reach=0.7,
        context_sensitivity=0.9,
        uncertainty=0.2,
        evidence_gap=0.4,
        estimated_probe_cost=0.3,
        rationale="Transparent calibration factors only; score is not truth.",
    )
    tampered = priority.to_dict()
    tampered["score"] = 0.0

    try:
        RiskPriority.from_dict(tampered)
    except Exception as error:
        assert "score" in str(error)
    else:
        raise AssertionError("tampered priority score was accepted")


def test_prior_and_operator_are_bounded_without_fixture_identifiers() -> None:
    prior = make_temporal_prior()
    operator = make_latency_operator()

    assert set(prior.signals) == {
        "delay",
        "latency",
        "blocking",
        "retry",
        "io",
        "lock",
        "wait",
        "availability",
    }
    assert operator.operator_id in prior.operator_ids
    assert "synchronous-weather" not in json.dumps(prior.to_dict())
    assert "synchronous-weather" not in json.dumps(operator.to_dict())
