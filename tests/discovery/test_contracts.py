from __future__ import annotations

import pytest

from aiverify.discovery import (
    AttackOperator,
    AttackPlan,
    ChangeTarget,
    ContextFact,
    ContractDrift,
    DiscoveryContractError,
    DiscoveryCampaign,
    FailureChain,
    Finding,
    ProvenanceRef,
    ProjectRiskMap,
    ProjectTarget,
    QualityContract,
    QualityContextGraph,
    ResidualRisk,
    RiskHypothesis,
    RiskPrior,
    admit_attack_plan,
    self_validate_schema,
    target_from_dict,
    validate_contract,
)


def test_change_target_round_trips_with_diff_identity() -> None:
    target = ChangeTarget(
        target_id="change-001",
        source_origin="https://example.invalid/app",
        source_commit="abc123",
        worktree="/workspace/app",
        diff_ref="artifacts/change.diff",
        diff_sha256="a" * 64,
        spec_ref="artifacts/spec.md",
    )

    restored = target_from_dict(target.to_dict())

    assert restored == target
    assert restored.kind == "change"
    assert restored.diff_ref == "artifacts/change.diff"


def test_project_target_round_trips_without_a_diff() -> None:
    target = ProjectTarget(
        target_id="project-001",
        source_origin="https://example.invalid/app",
        source_commit="abc123",
        worktree="/workspace/app",
        scope=("systemui", "weather-service"),
        discovery_budget=20,
    )

    restored = target_from_dict(target.to_dict())

    assert restored == target
    assert restored.kind == "project"
    assert restored.scope == ("systemui", "weather-service")


def test_target_union_rejects_diff_on_project_target() -> None:
    with pytest.raises(DiscoveryContractError, match="project target must not include diff"):
        target_from_dict(
            {
                "kind": "project",
                "target_id": "project-001",
                "source_origin": "https://example.invalid/app",
                "source_commit": "abc123",
                "worktree": "/workspace/app",
                "scope": ["systemui"],
                "discovery_budget": 20,
                "diff_ref": "unexpected.diff",
            }
        )


def test_target_union_rejects_missing_change_diff_identity() -> None:
    with pytest.raises(DiscoveryContractError, match="change target requires diff"):
        target_from_dict(
            {
                "kind": "change",
                "target_id": "change-001",
                "source_origin": "https://example.invalid/app",
                "source_commit": "abc123",
                "worktree": "/workspace/app",
            }
        )


def test_context_graph_round_trips_provenance_bound_facts() -> None:
    fact = ContextFact(
        fact_id="fact-001",
        subject="weather.fetch",
        predicate="synchronously_called_by",
        value="systemui.refresh",
        source_kind="derived",
        provenance=(
            ProvenanceRef(
                ref="src/systemui/WeatherClient.kt:42",
                source_sha256="b" * 64,
            ),
        ),
        source_version="commit-abc123",
        confidence=0.9,
        status="known",
    )
    graph = QualityContextGraph(
        graph_id="graph-001",
        target_id="project-001",
        facts=(fact,),
    )

    restored = QualityContextGraph.from_dict(graph.to_dict())

    assert restored == graph
    assert restored.fact("fact-001") == fact


def test_context_fact_requires_provenance_for_known_state() -> None:
    with pytest.raises(DiscoveryContractError, match="known fact requires provenance"):
        ContextFact(
            fact_id="fact-001",
            subject="weather.fetch",
            predicate="latency_budget_ms",
            value=500,
            source_kind="derived",
            provenance=(),
            source_version="commit-abc123",
            confidence=0.8,
            status="known",
        )


def test_context_fact_keeps_unknown_state_explicit() -> None:
    fact = ContextFact(
        fact_id="fact-unknown",
        subject="weather.fetch",
        predicate="caller_thread",
        value=None,
        source_kind="unknown",
        provenance=(),
        source_version="commit-abc123",
        confidence=0.0,
        status="unknown",
        rationale="No caller source or runtime trace was available.",
    )

    assert fact.status == "unknown"
    assert fact.to_dict()["provenance"] == []


def test_context_graph_rejects_duplicate_fact_ids() -> None:
    fact = ContextFact(
        fact_id="fact-001",
        subject="a",
        predicate="b",
        value="c",
        source_kind="declared",
        provenance=(ProvenanceRef(ref="docs/contract.md"),),
        source_version="commit-abc123",
        confidence=1.0,
        status="known",
    )

    with pytest.raises(DiscoveryContractError, match="fact ids must be unique"):
        QualityContextGraph(
            graph_id="graph-001",
            target_id="project-001",
            facts=(fact, fact),
        )


def test_v1_compatibility_defaults_schema_version_but_rejects_future_version() -> None:
    target = ProjectTarget(
        target_id="project-001",
        source_origin="https://example.invalid/app",
        source_commit="abc123",
        worktree="/workspace/app",
        scope=("systemui",),
        discovery_budget=1,
    )
    legacy = target.to_dict()
    legacy.pop("schema_version")

    assert target_from_dict(legacy).schema_version == 1

    future = target.to_dict()
    future["schema_version"] = 2
    with pytest.raises(DiscoveryContractError, match="unsupported project target"):
        target_from_dict(future)


def test_context_fact_serialization_requires_value_key_even_for_null() -> None:
    fact = ContextFact(
        fact_id="fact-unknown",
        subject="weather.fetch",
        predicate="caller_thread",
        value=None,
        source_kind="unknown",
        provenance=(),
        source_version="commit-abc123",
        confidence=0.0,
        status="unknown",
        rationale="No caller source was available.",
    )
    serialized = fact.to_dict()
    serialized.pop("value")

    with pytest.raises(DiscoveryContractError, match="context fact requires value"):
        ContextFact.from_dict(serialized)


def _discovery_fixture() -> tuple[QualityContextGraph, RiskHypothesis, AttackPlan]:
    fact = ContextFact(
        fact_id="fact-thread",
        subject="weather.fetch",
        predicate="caller_thread",
        value="systemui-main",
        source_kind="derived",
        provenance=(ProvenanceRef(ref="src/systemui/WeatherClient.kt:42"),),
        source_version="commit-abc123",
        confidence=0.95,
        status="known",
    )
    graph = QualityContextGraph(
        graph_id="graph-001",
        target_id="project-001",
        facts=(fact,),
    )
    hypothesis = RiskHypothesis(
        hypothesis_id="hypothesis-anr",
        target_id="project-001",
        quality_property="critical-path latency remains within the UI budget",
        assumptions=("weather service is called synchronously",),
        trigger="weather service adds a blocking delay",
        mechanism="main-thread call waits past the UI response budget",
        consequence="SystemUI becomes non-responsive",
        rationale="The caller and service share a synchronous temporal contract.",
        required_evidence=("main-thread stall", "ANR signal"),
        confidence=0.8,
        status="frozen",
        supporting_fact_ids=("fact-thread",),
    )
    plan = AttackPlan(
        plan_id="plan-anr",
        target_id="project-001",
        hypothesis_id="hypothesis-anr",
        operator_id="operator-delay",
        trigger="inject a bounded service delay",
        observations=("main-thread duration", "ANR signal"),
        evidence_expectations=("main-thread stall", "ANR signal"),
        oracle="android-anr-oracle-v1",
        abort_boundary="stop after one bounded delay",
        claim_boundary="local project checkout and emulator only",
        fixture_refs=("fixture-weather-delay",),
    )
    return graph, hypothesis, plan


def test_risk_contracts_round_trip_as_separate_domain_objects() -> None:
    graph, hypothesis, plan = _discovery_fixture()
    quality_contract = QualityContract(
        contract_id="contract-ui-latency",
        name="SystemUI response budget",
        scope="SystemUI refresh path",
        quality_property="critical-path latency",
        constraint="must remain below the UI response budget",
        source_fact_ids=("fact-thread",),
    )
    drift = ContractDrift(
        drift_id="drift-delay",
        contract_id=quality_contract.contract_id,
        before="service returns within the UI budget",
        after="service may block for an unbounded delay",
        delta="blocking latency budget widened",
        source_fact_ids=("fact-thread",),
        rationale="A service change changes the caller's temporal assumption.",
    )
    prior = RiskPrior(
        prior_id="prior-sync-critical-path",
        name="synchronous critical path",
        description="Prefer attacks that stretch a synchronous critical path.",
        signals=("main-thread call", "remote service"),
        operator_ids=("operator-delay",),
        version="m7.1",
    )
    operator = AttackOperator(
        operator_id="operator-delay",
        name="bounded delay",
        description="Add a bounded delay at the service boundary.",
        action="delay service response",
        safety_boundary="local emulator only",
    )
    chain = FailureChain(
        chain_id="chain-anr",
        steps=("service delays", "main thread waits", "UI misses response budget"),
        consequence="ANR",
        fact_ids=("fact-thread",),
    )
    finding = Finding(
        finding_id="finding-anr",
        target_id="project-001",
        hypothesis_id=hypothesis.hypothesis_id,
        conclusion="supported",
        evidence_refs=("runs/anr/logcat.txt",),
        impact="SystemUI unavailable during the delay",
        claim_boundary="local emulator only",
        rationale="The recorded stall and ANR satisfy the expected evidence.",
    )
    residual = ResidualRisk(
        risk_id="risk-oem",
        target_id="project-001",
        hypothesis_id=hypothesis.hypothesis_id,
        reason="OEM scheduler behavior was not exercised",
        evidence_gap="No physical or OEM runtime evidence",
        scope="physical devices and OEM variants",
        basis_refs=("fact-thread",),
        next_probe="repeat on a physical OEM device",
    )
    risk_map = ProjectRiskMap(
        map_id="map-001",
        target_id="project-001",
        findings=(finding,),
        residual_risks=(residual,),
        explored_fact_ids=("fact-thread",),
        coverage_frontier=("OEM scheduling",),
    )
    campaign = DiscoveryCampaign(
        campaign_id="campaign-001",
        target=ProjectTarget(
            target_id="project-001",
            source_origin="https://example.invalid/app",
            source_commit="abc123",
            worktree="/workspace/app",
            scope=("systemui",),
            discovery_budget=20,
        ),
        context_graph=graph,
        quality_contracts=(quality_contract,),
        contract_drifts=(drift,),
        risk_priors=(prior,),
        attack_operators=(operator,),
        hypotheses=(hypothesis,),
        failure_chains=(chain,),
        attack_plans=(plan,),
        experiment_refs=("run-spec-anr",),
        findings=(finding,),
        residual_risks=(residual,),
        project_risk_map=risk_map,
    )

    restored = DiscoveryCampaign.from_dict(campaign.to_dict())

    assert restored == campaign
    assert restored.attack_plans[0].oracle_ref == "android-anr-oracle-v1"
    assert restored.findings[0].conclusion == "supported"
    assert restored.residual_risks[0].evidence_gap.startswith("No physical")


def test_experiment_admission_is_side_effect_free_and_fail_closed() -> None:
    graph, hypothesis, plan = _discovery_fixture()

    admitted = admit_attack_plan(plan, hypothesis, graph)

    assert admitted.admitted is True
    assert admitted.to_dict()["status"] == "admitted"

    rejected = admit_attack_plan(
        AttackPlan(
            plan_id=plan.plan_id,
            target_id=plan.target_id,
            hypothesis_id=plan.hypothesis_id,
            operator_id=plan.operator_id,
        ),
        hypothesis,
        graph,
    )

    assert rejected.admitted is False
    assert "missing fixture relationship" in rejected.errors
    assert "missing oracle relationship" in rejected.errors
    assert "missing claim boundary" in rejected.errors


def test_experiment_admission_rejects_contradictory_supporting_fact() -> None:
    graph, hypothesis, plan = _discovery_fixture()
    contradictory = ContextFact(
        fact_id="fact-thread",
        subject="weather.fetch",
        predicate="caller_thread",
        value="unknown",
        source_kind="observed",
        provenance=(ProvenanceRef(ref="trace/contradictory.json"),),
        source_version="commit-abc123",
        confidence=0.5,
        status="contradictory",
    )
    graph = QualityContextGraph(
        graph_id=graph.graph_id,
        target_id=graph.target_id,
        facts=(contradictory,),
    )

    result = admit_attack_plan(plan, hypothesis, graph)

    assert result.status == "rejected"
    assert any("contradictory" in error for error in result.errors)


def test_finding_and_residual_risk_require_evidence_basis() -> None:
    with pytest.raises(DiscoveryContractError, match="evidence_refs must not be empty"):
        Finding(
            finding_id="finding-001",
            target_id="project-001",
            hypothesis_id="hypothesis-001",
            conclusion="supported",
            evidence_refs=(),
            impact="impact",
            claim_boundary="local only",
            rationale="unsupported",
        )

    with pytest.raises(DiscoveryContractError, match="basis_refs must not be empty"):
        ResidualRisk(
            risk_id="risk-001",
            target_id="project-001",
            hypothesis_id="hypothesis-001",
            reason="unknown",
            evidence_gap="missing trace",
            scope="OEM",
            basis_refs=(),
        )


def test_versioned_schema_self_validation_and_campaign_validation() -> None:
    graph, hypothesis, plan = _discovery_fixture()
    campaign = DiscoveryCampaign(
        campaign_id="campaign-schema",
        target=ProjectTarget(
            target_id="project-001",
            source_origin="https://example.invalid/app",
            source_commit="abc123",
            worktree="/workspace/app",
            scope=("systemui",),
            discovery_budget=1,
        ),
        context_graph=graph,
        hypotheses=(hypothesis,),
        attack_operators=(
            AttackOperator(
                operator_id="operator-delay",
                name="bounded delay",
                description="Add a bounded delay at the service boundary.",
                action="delay service response",
                safety_boundary="local emulator only",
            ),
        ),
        attack_plans=(plan,),
    )

    self_validate_schema()
    validate_contract(campaign.to_dict(), "discovery_campaign")


def test_schema_rejects_tampered_and_ambiguous_documents() -> None:
    target = ProjectTarget(
        target_id="project-001",
        source_origin="https://example.invalid/app",
        source_commit="abc123",
        worktree="/workspace/app",
        scope=("systemui",),
        discovery_budget=1,
    )
    tampered = target.to_dict()
    tampered["unexpected"] = True

    with pytest.raises(DiscoveryContractError, match="unknown discovery contract field"):
        target_from_dict(tampered)
    with pytest.raises(DiscoveryContractError, match="invalid project_target contract"):
        validate_contract(tampered, "project_target")

    ambiguous = target.to_dict()
    ambiguous["kind"] = "change"
    with pytest.raises(DiscoveryContractError, match="invalid target contract"):
        validate_contract(ambiguous, "target")


def test_campaign_rejects_dangling_relationships() -> None:
    graph, hypothesis, plan = _discovery_fixture()
    with pytest.raises(DiscoveryContractError, match="missing attack operator"):
        DiscoveryCampaign(
            campaign_id="campaign-dangling",
            target=ProjectTarget(
                target_id="project-001",
                source_origin="https://example.invalid/app",
                source_commit="abc123",
                worktree="/workspace/app",
                scope=("systemui",),
                discovery_budget=1,
            ),
            context_graph=graph,
            hypotheses=(hypothesis,),
            attack_plans=(plan,),
        )
