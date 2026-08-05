from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.bench.state_evolution import load_state_evolution_context
from aiverify.discovery import (
    BehaviorDelta,
    ChangeTarget,
    ContractDrift,
    ProjectTarget,
    QualityContextGraph,
    RiskPriority,
    admit_attack_plan,
    derive_state_evolution_risk,
    derive_with_strategy,
    make_historical_state_replay_operator,
    make_state_evolution_prior,
    make_state_evolution_strategy,
    seed_project_campaign,
    validate_contract,
)

_FIXTURE = Path("bench/discovery-fixtures/state-evolution")
_CONTRACT = _FIXTURE / "contract.json"
_CONTEXT = _FIXTURE / "context-manifest.json"
_DIFF = Path("bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch")


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(Path.cwd()),
        scope=("state-evolution",),
        discovery_budget=8,
    )


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(Path.cwd()),
        diff_ref=str(_DIFF),
        diff_sha256="7109a3a3e7d1e0416ffe4c0a06de10982c8fdc99f1cfc888c266acc328674a42",
    )


def _graph(target):
    return load_state_evolution_context(
        _CONTEXT,
        target,
        contract_path=_CONTRACT,
    ).graph


def _change_inputs() -> tuple[BehaviorDelta, ContractDrift]:
    return (
        BehaviorDelta(
            delta_id="delta-state-transition",
            target_id="change-state-evolution-001",
            subject="StateStoreV2.migrate",
            before="historical state follows the recorded transition",
            after="the changed transition may alter compatibility",
            source_fact_ids=("fact-schema-migration",),
            confidence=0.84,
            contract_drift_id="drift-state-continuity",
            rationale="The change is a bounded compatibility concern.",
        ),
        ContractDrift(
            drift_id="drift-state-continuity",
            contract_id="durable-state-continuity-v1",
            before="historical state remains compatible across recovery",
            after="the transition may alter compatibility across recovery",
            delta="state transition compatibility changed",
            source_fact_ids=("fact-quality-contract",),
            rationale="This records the changed contract assumption.",
        ),
    )


def test_project_mode_derives_complete_state_evolution_contract() -> None:
    target = _project_target()
    result = derive_state_evolution_risk(target, _graph(target), mode="project")

    assert result.accepted is True
    assert result.hypothesis is not None
    assert result.hypothesis.status == "frozen"
    assert result.hypothesis.behavior_delta_id is None
    assert result.hypothesis.contract_drift_id is None
    assert result.failure_chain is not None
    assert result.priority is not None
    assert result.attack_plan is not None
    assert result.attack_plan.status == "frozen"
    assert admit_attack_plan(result.attack_plan, result.hypothesis, _graph(target)).admitted
    for contract_name, value in (
        ("risk_hypothesis", result.hypothesis),
        ("failure_chain", result.failure_chain),
        ("risk_priority", result.priority),
        ("attack_plan", result.attack_plan),
    ):
        validate_contract(value.to_dict(), contract_name)


def test_change_mode_binds_delta_and_drift_while_project_has_no_diff() -> None:
    target = _change_target()
    delta, drift = _change_inputs()
    result = derive_state_evolution_risk(
        target,
        _graph(target),
        mode="change",
        behavior_delta=delta,
        contract_drift=drift,
    )

    assert result.accepted is True
    assert result.hypothesis.behavior_delta_id == delta.delta_id
    assert result.hypothesis.contract_drift_id == drift.drift_id

    project = _project_target()
    project_result = derive_state_evolution_risk(
        project,
        _graph(project),
        mode="project",
        behavior_delta=delta,
    )
    assert project_result.accepted is False
    assert any(
        "must not require a behavior delta" in reason
        for reason in project_result.rejection_reasons
    )


def test_strategy_seam_and_campaign_preserve_state_evolution_identity() -> None:
    target = _project_target()
    graph = _graph(target)
    prior = make_state_evolution_prior()
    operator = make_historical_state_replay_operator()
    strategy = make_state_evolution_strategy(prior=prior, operator=operator)
    result = derive_with_strategy(
        strategy,
        target,
        graph,
        mode="project",
        prior=prior,
        operator=operator,
    )

    assert result.accepted is True
    package = seed_project_campaign(
        "campaign-state-evolution-001",
        target,
        graph,
        prior=prior,
        operator=operator,
        strategy=strategy,
    )
    assert package.campaign.derivation_strategy_id == strategy.strategy_id
    assert package.campaign.risk_priors == (prior,)
    assert package.campaign.attack_operators == (operator,)
    assert package.campaign.quality_contracts[0].quality_property == (
        "durable state continuity"
    )
    assert package.campaign.quality_contracts[0].scope == "recorded state path"
    assert package.campaign.findings == ()


def test_derivation_is_deterministic_and_unknown_runtime_is_explicit() -> None:
    target = _project_target()
    graph = _graph(target)
    first = derive_state_evolution_risk(target, graph, mode="project")
    second = derive_state_evolution_risk(target, graph, mode="project")

    assert first == second
    assert first.hypothesis.unknowns == ("fact fact-runtime-identity remains unknown",)
    assert "not a probability" in first.priority.rationale
    assert "Finding" not in first.priority.rationale
    assert "lifecycle_fixture" not in json.dumps(first.hypothesis.to_dict())
    assert "lifecycle_fixture" not in json.dumps(first.attack_plan.to_dict())
    assert "journey" not in json.dumps(first.attack_plan.to_dict()).lower()
    assert "expected" not in json.dumps(first.attack_plan.to_dict()).lower()
    assert "verdict" not in json.dumps(first.attack_plan.to_dict()).lower()


@pytest.mark.parametrize("status", ["unknown", "contradictory", "stale"])
def test_required_history_status_fails_closed(status: str) -> None:
    target = _project_target()
    loaded = _graph(target)
    original = loaded.fact("fact-schema-migration")
    if status == "unknown":
        changed = replace(
            original,
            source_kind="unknown",
            provenance=(),
            confidence=0.0,
            status="unknown",
            rationale="Migration history is unavailable.",
        )
    else:
        changed = replace(original, status=status)
    graph = QualityContextGraph(
        graph_id=loaded.graph_id,
        target_id=loaded.target_id,
        facts=tuple(changed if fact.fact_id == changed.fact_id else fact for fact in loaded.facts),
        nodes=loaded.nodes,
        edges=loaded.edges,
    )

    result = derive_state_evolution_risk(target, graph, mode="project")

    assert result.accepted is False
    assert any(status in reason for reason in result.rejection_reasons)
    assert result.hypothesis is None


def test_mismatched_transition_and_disconnected_path_fail_closed() -> None:
    target = _project_target()
    loaded = _graph(target)
    migration = loaded.fact("fact-schema-migration")
    bad_value = dict(migration.value)
    bad_value["to"] = 7
    bad_migration = replace(migration, value=bad_value)
    bad_graph = QualityContextGraph(
        graph_id=loaded.graph_id,
        target_id=loaded.target_id,
        facts=tuple(
            bad_migration if fact.fact_id == bad_migration.fact_id else fact
            for fact in loaded.facts
        ),
        nodes=loaded.nodes,
        edges=loaded.edges,
    )
    mismatch = derive_state_evolution_risk(target, bad_graph, mode="project")
    assert mismatch.accepted is False
    assert any("mismatch" in reason for reason in mismatch.rejection_reasons)

    disconnected_edges = tuple(
        replace(edge, semantics="unknown")
        if edge.edge_id == "edge-migration-reader"
        else edge
        for edge in loaded.edges
    )
    disconnected = QualityContextGraph(
        graph_id=loaded.graph_id,
        target_id=loaded.target_id,
        facts=loaded.facts,
        nodes=loaded.nodes,
        edges=disconnected_edges,
    )
    no_path = derive_state_evolution_risk(target, disconnected, mode="project")
    assert no_path.accepted is False
    assert any("connected" in reason for reason in no_path.rejection_reasons)


def test_change_binding_mismatch_and_unresolved_facts_fail_closed() -> None:
    target = _change_target()
    graph = _graph(target)
    delta, drift = _change_inputs()
    mismatch = replace(delta, contract_drift_id="drift-other")
    result = derive_state_evolution_risk(
        target,
        graph,
        mode="change",
        behavior_delta=mismatch,
        contract_drift=drift,
    )
    assert result.accepted is False
    assert any("do not match" in reason for reason in result.rejection_reasons)

    unresolved = replace(graph.fact("fact-quality-contract"), status="stale")
    unresolved_graph = QualityContextGraph(
        graph_id=graph.graph_id,
        target_id=graph.target_id,
        facts=tuple(
            unresolved if fact.fact_id == unresolved.fact_id else fact
            for fact in graph.facts
        ),
        nodes=graph.nodes,
        edges=graph.edges,
    )
    result = derive_state_evolution_risk(
        target,
        unresolved_graph,
        mode="change",
        behavior_delta=delta,
        contract_drift=drift,
    )
    assert result.accepted is False
    assert any("stale" in reason for reason in result.rejection_reasons)


def test_round_trip_and_tamper_rejection_are_strict() -> None:
    target = _project_target()
    result = derive_state_evolution_risk(target, _graph(target), mode="project")
    assert result.accepted
    assert json.loads(json.dumps(result.hypothesis.to_dict())) == result.hypothesis.to_dict()
    assert RiskPriority.from_dict(result.priority.to_dict()) == result.priority
    tampered = result.priority.to_dict()
    tampered["score"] = 0.0
    with pytest.raises(Exception, match="score"):
        RiskPriority.from_dict(tampered)
