"""Replay the durable #120 contract/schema/leakage seam check."""

from __future__ import annotations

import json
from pathlib import Path

from aiverify.bench.state_evolution import load_state_evolution_context
from aiverify.discovery import (
    BehaviorDelta,
    ChangeTarget,
    ContractDrift,
    ProjectTarget,
    derive_with_strategy,
    make_historical_state_replay_operator,
    make_state_evolution_prior,
    make_state_evolution_strategy,
    validate_contract,
)

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "bench/discovery-fixtures/state-evolution"
DIFF = ROOT / "bench/capability-slices/lifecycle-recovery/patches/stale-migration-guard.patch"


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(ROOT),
        scope=("state-evolution",),
        discovery_budget=8,
    )


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-state-evolution-001",
        source_origin="fixture://state-evolution",
        source_commit="state-evolution-v1",
        worktree=str(ROOT),
        diff_ref=str(DIFF),
        diff_sha256="7109a3a3e7d1e0416ffe4c0a06de10982c8fdc99f1cfc888c266acc328674a42",
    )


def main() -> None:
    project = _project_target()
    change = _change_target()
    project_graph = load_state_evolution_context(
        FIXTURE / "context-manifest.json",
        project,
        contract_path=FIXTURE / "contract.json",
    ).graph
    change_graph = load_state_evolution_context(
        FIXTURE / "context-manifest.json",
        change,
        contract_path=FIXTURE / "contract.json",
    ).graph
    prior = make_state_evolution_prior()
    operator = make_historical_state_replay_operator()
    strategy = make_state_evolution_strategy(prior=prior, operator=operator)
    delta = BehaviorDelta(
        delta_id="delta-state-transition",
        target_id=change.target_id,
        subject="StateStoreV2.migrate",
        before="historical state remains compatible",
        after="transition compatibility changes",
        source_fact_ids=("fact-schema-migration",),
        confidence=0.84,
        contract_drift_id="drift-state-continuity",
        rationale="bounded change",
    )
    drift = ContractDrift(
        drift_id="drift-state-continuity",
        contract_id="durable-state-continuity-v1",
        before="continuity remains compatible",
        after="continuity assumption changes",
        delta="state transition compatibility changed",
        source_fact_ids=("fact-quality-contract",),
        rationale="bounded drift",
    )
    project_result = derive_with_strategy(
        strategy,
        project,
        project_graph,
        mode="project",
        prior=prior,
        operator=operator,
    )
    change_result = derive_with_strategy(
        strategy,
        change,
        change_graph,
        mode="change",
        behavior_delta=delta,
        contract_drift=drift,
        prior=prior,
        operator=operator,
    )
    assert project_result.accepted and change_result.accepted
    for result in (project_result, change_result):
        for name, value in (
            ("risk_hypothesis", result.hypothesis),
            ("failure_chain", result.failure_chain),
            ("risk_priority", result.priority),
            ("attack_plan", result.attack_plan),
        ):
            validate_contract(value.to_dict(), name)
            assert type(value).from_dict(value.to_dict()) == value
        payload = json.dumps(
            {"hypothesis": result.hypothesis.to_dict(), "plan": result.attack_plan.to_dict()},
            sort_keys=True,
        ).lower()
        for forbidden in ("lifecycle_fixture", "journey", "expected", "verdict"):
            assert forbidden not in payload
    output = {
        "schema_valid": True,
        "project_strategy_accepted": project_result.accepted,
        "change_strategy_accepted": change_result.accepted,
        "project_hypothesis": project_result.hypothesis.hypothesis_id,
        "change_hypothesis": change_result.hypothesis.hypothesis_id,
        "project_plan": project_result.attack_plan.plan_id,
        "change_plan": change_result.attack_plan.plan_id,
        "priority_score_is_nonprobabilistic": "not a probability"
        in project_result.priority.rationale,
        "finding_count": 0,
        "leakage_checks": 4,
    }
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
