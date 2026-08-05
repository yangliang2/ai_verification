from __future__ import annotations

from pathlib import Path

import pytest

from aiverify.discovery import (
    AttemptEvidence,
    ChangeTarget,
    ContextExpansionRequest,
    ContextExpansionResult,
    DiscoveryContractError,
    HypothesisSelectionLedger,
    ProjectTarget,
    AttackOperator,
    BehaviorDelta,
    ContractDrift,
    admit_campaign_plan,
    apply_context_expansion,
    compile_attack_plan_to_run_spec,
    create_campaign,
    freeze_campaign_hypothesis,
    load_context_manifest,
    reduce_attempt_evidence,
    resume_campaign,
    derive_synchronous_risk,
    derive_with_strategy,
    make_risk_derivation_strategy,
    RiskPrior,
    seed_change_campaign,
    seed_project_campaign,
    validate_contract,
)
from aiverify.runner.run_spec import MetricContextSpec, ScenarioSpec


_FIXTURE = Path("bench/discovery-fixtures/synchronous-weather/context-manifest.json")


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-weather-103",
        source_origin="https://example.invalid/discovery",
        source_commit="fixture-v1",
        worktree="/workspace/discovery",
        scope=("weather-service", "systemui-consumer"),
        discovery_budget=8,
    )


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-weather-103",
        source_origin="https://example.invalid/discovery",
        source_commit="fixture-v1",
        worktree="/workspace/discovery",
        diff_ref="changes/weather-delay.diff",
        diff_sha256="a" * 64,
    )


def _graph(target):
    return load_context_manifest(_FIXTURE, target).graph


def _change_inputs(target: ChangeTarget) -> tuple[BehaviorDelta, ContractDrift]:
    return (
        BehaviorDelta(
            delta_id="delta-weather-103",
            target_id=target.target_id,
            subject="WeatherService.current",
            before="returns promptly",
            after="may wait before returning",
            source_fact_ids=("fact-service-operation",),
            confidence=0.85,
            contract_drift_id="drift-weather-103",
            rationale="The change signal widens a temporal assumption.",
        ),
        ContractDrift(
            drift_id="drift-weather-103",
            contract_id="contract-weather-103",
            before="dependency returns within the caller budget",
            after="dependency may wait before returning",
            delta="synchronous temporal budget widened",
            source_fact_ids=("fact-service-operation",),
            rationale="This is inferred drift, not an observed outcome.",
        ),
    )


def test_context_expansion_is_target_bound_and_schema_validated() -> None:
    target = _project_target()
    graph = _graph(target)
    request = ContextExpansionRequest(
        request_id="request-weather-103",
        campaign_id="campaign-weather-103",
        target_id=target.target_id,
        required_predicates=("caller_thread", "quality_contract"),
        probe_refs=("probe:runtime-thread",),
        budget=2,
        unresolved_questions=("runtime thread remains unknown",),
    )
    package = create_campaign(
        request.campaign_id,
        target,
        graph,
        expansion_request=request,
    )
    assert package.campaign.status == "created"
    result = ContextExpansionResult(
        request_id=request.request_id,
        target_id=target.target_id,
        graph=graph,
        resolved_fact_ids=("fact-caller-thread", "fact-quality-contract"),
        unresolved_questions=("runtime thread remains unknown",),
        probe_refs=request.probe_refs,
        budget_used=1,
        status="partial",
    )
    expanded = apply_context_expansion(package, result)
    assert expanded.campaign.status == "context-ready"
    validate_contract(expanded.context_result.to_dict(), "context_expansion_result")
    validate_contract(expanded.to_dict(), "discovery_campaign_package")
    assert resume_campaign(expanded.to_dict()) == expanded


def test_change_and_project_modes_share_admission_and_run_spec_seam() -> None:
    project_target = _project_target()
    project = seed_project_campaign(
        "campaign-project-103",
        project_target,
        _graph(project_target),
    )
    change_target = _change_target()
    delta, drift = _change_inputs(change_target)
    change = seed_change_campaign(
        "campaign-change-103",
        change_target,
        _graph(change_target),
        behavior_delta=delta,
        contract_drift=drift,
    )
    assert project.behavior_delta is None
    assert change.behavior_delta == delta
    assert project.campaign.attack_plans[0].status == "frozen"
    assert not project.campaign.findings
    assert not change.campaign.findings

    for package in (project, change):
        with pytest.raises(DiscoveryContractError, match="plan-admitted"):
            compile_attack_plan_to_run_spec(
                package,
                host_project="/workspace/discovery",
                apk_glob="build/*.apk",
                package_name="com.example.systemui",
                activity=".MainActivity",
                scenario=ScenarioSpec(id="weather-delay"),
            )
        admitted = admit_campaign_plan(package)
        assert admitted.admission.admitted is True
        assert admitted.package.campaign.status == "plan-admitted"
        compiled = compile_attack_plan_to_run_spec(
            admitted.package,
            host_project="/workspace/discovery",
            apk_glob="build/*.apk",
            package_name="com.example.systemui",
            activity=".MainActivity",
            scenario=ScenarioSpec(id="weather-delay"),
            diff="change.diff" if package is change else None,
        )
        assert compiled.admission.admitted is True
        assert compiled.package.campaign.status == "executing"
        assert compiled.run_spec.scenario.id == "weather-delay"
        if package is project:
            assert compiled.run_spec.diff is None
        else:
            assert compiled.run_spec.diff is not None

    marked_scenario = ScenarioSpec(
        id="marked",
        expected_behavior="hidden expected defect outcome",
        metric_context=MetricContextSpec(
            seed_kind="injected_defect",
            taxonomy_category="hidden",
            taxonomy_pattern_id="hidden-pattern",
            expected_oracle_level="L3",
            expected_oracle_defect_class="performance_regression",
        ),
    )
    admitted_project = admit_campaign_plan(project).package
    sanitized = compile_attack_plan_to_run_spec(
        admitted_project,
        host_project="/workspace/discovery",
        apk_glob="build/*.apk",
        package_name="com.example.systemui",
        activity=".MainActivity",
        scenario=marked_scenario,
    )
    assert sanitized.run_spec.scenario.expected_behavior == ""
    assert sanitized.run_spec.scenario.metric_context.seed_kind == "unspecified"
    assert sanitized.run_spec.scenario.metric_context.taxonomy_category is None


def test_selection_ledger_is_append_only_and_tamper_evident() -> None:
    ledger = HypothesisSelectionLedger().append(
        hypothesis_id="hypothesis-one",
        decision="considered",
        priority_score=0.4,
        rationale="considered from known context",
    ).append(
        hypothesis_id="hypothesis-one",
        decision="selected",
        priority_score=0.8,
        rationale="selected after transparent ordering",
    )
    restored = HypothesisSelectionLedger.from_dict(ledger.to_dict())
    assert restored == ledger
    tampered = ledger.to_dict()
    tampered["entries"][1]["rationale"] = "changed"
    with pytest.raises(DiscoveryContractError, match="digest"):
        HypothesisSelectionLedger.from_dict(tampered)


def test_evidence_reducer_keeps_non_accountable_attempts_out_of_findings() -> None:
    target = _project_target()
    package = admit_campaign_plan(
        seed_project_campaign("campaign-reduce-103", target, _graph(target))
    ).package
    hypothesis = package.campaign.hypotheses[0]
    supported = AttemptEvidence(
        evidence_id="evidence-supported",
        target_id=target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        attempt_ref="attempt-1",
        execution_record_ref="attempt-1/execution-record.json",
        outcome="supported",
        evidence_refs=("attempt-1/logcat.txt",),
        claim_boundary="local fixture and accountable emulator attempt only",
        rationale="The accountable oracle evidence supports the frozen mechanism.",
        accountable=True,
        execution_identity_sha256="a" * 64,
    )
    concluded, reduction = reduce_attempt_evidence(package, supported)
    validate_contract(supported.to_dict(), "attempt_evidence")
    assert reduction.finding is not None
    assert reduction.residual_risk is None
    assert concluded.campaign.findings[0].conclusion == "supported"
    assert not concluded.campaign.residual_risks

    non_accountable = AttemptEvidence(
        evidence_id="evidence-non-accountable",
        target_id=target.target_id,
        hypothesis_id=hypothesis.hypothesis_id,
        attempt_ref="attempt-2",
        execution_record_ref="attempt-2/execution-record.json",
        outcome="non_accountable",
        evidence_refs=(),
        claim_boundary="local fixture only",
        rationale="Preflight failed before an accountable attempt existed.",
        accountable=False,
    )
    reduced, non_accountable_result = reduce_attempt_evidence(package, non_accountable)
    assert non_accountable_result.finding is None
    assert non_accountable_result.residual_risk is not None
    assert reduced.campaign.residual_risks[0].status == "open"


def test_attempt_evidence_cannot_claim_accountable_without_evidence() -> None:
    with pytest.raises(DiscoveryContractError, match="accountable"):
        AttemptEvidence(
            evidence_id="evidence-invalid",
            target_id="project",
            hypothesis_id="hypothesis",
            attempt_ref="attempt",
            execution_record_ref="record",
            outcome="supported",
            evidence_refs=(),
            claim_boundary="local",
            rationale="unsupported",
            accountable=True,
        )


def test_freeze_from_context_ready_and_resume_is_deterministic() -> None:
    target = _project_target()
    request = ContextExpansionRequest(
        request_id="request-freeze-103",
        campaign_id="campaign-freeze-103",
        target_id=target.target_id,
        required_predicates=("quality_contract",),
        probe_refs=(),
        budget=1,
    )
    created = create_campaign(
        request.campaign_id,
        target,
        _graph(target),
        expansion_request=request,
    )
    expanded = apply_context_expansion(
        created,
        ContextExpansionResult(
            request_id=request.request_id,
            target_id=target.target_id,
            graph=_graph(target),
            resolved_fact_ids=("fact-quality-contract",),
            status="partial",
        ),
    )
    frozen = freeze_campaign_hypothesis(expanded)
    assert frozen.campaign.status == "hypothesis-frozen"
    assert frozen.context_result == expanded.context_result
    assert resume_campaign(frozen.to_dict()) == frozen

    tampered = frozen.to_dict()
    tampered["selection_ledger"]["head_digest"] = "f" * 64
    with pytest.raises(DiscoveryContractError, match="head_digest"):
        resume_campaign(tampered)


def test_explicit_non_temporal_strategy_seeds_both_modes_and_resumes() -> None:
    prior = RiskPrior(
        prior_id="prior-test-family-v1",
        name="test family",
        description="A deterministic test family.",
        signals=("test-signal",),
        operator_ids=("operator-test-replay",),
        version="test-1",
    )
    operator = AttackOperator(
        operator_id="operator-test-replay",
        name="test operator",
        description="A bounded test operator.",
        action="observe a local fixture",
        safety_boundary="local fixture only",
    )

    def derive_test_family(
        target,
        graph,
        *,
        mode,
        behavior_delta=None,
        contract_drift=None,
    ):
        return derive_synchronous_risk(
            target,
            graph,
            mode=mode,
            behavior_delta=behavior_delta,
            contract_drift=contract_drift,
            prior=prior,
            operator=operator,
        )

    strategy = make_risk_derivation_strategy(
        strategy_id="strategy-test-family-v1",
        version="test-1",
        compatible_prior_ids=("prior-test-family-v1",),
        compatible_operator_ids=("operator-test-replay",),
        deriver=derive_test_family,
    )
    project_target = _project_target()
    project = seed_project_campaign(
        "campaign-test-family-project",
        project_target,
        _graph(project_target),
        prior=prior,
        operator=operator,
        strategy=strategy,
    )
    change_target = _change_target()
    delta, drift = _change_inputs(change_target)
    change = seed_change_campaign(
        "campaign-test-family-change",
        change_target,
        _graph(change_target),
        behavior_delta=delta,
        contract_drift=drift,
        prior=prior,
        operator=operator,
        derivation_strategy=strategy,
    )

    for package in (project, change):
        assert package.campaign.derivation_strategy_id == strategy.strategy_id
        assert package.campaign.derivation_strategy_version == strategy.version
        assert package.selection_ledger.entries[0].prior_id == prior.prior_id
        assert resume_campaign(package.to_dict(), strategy=strategy) == package
    validate_contract(strategy.to_dict(), "risk_derivation_strategy")


def test_strategy_selection_rejects_unsupported_prior_before_campaign() -> None:
    strategy = make_risk_derivation_strategy(
        strategy_id="strategy-only-v1",
        version="test-1",
        compatible_prior_ids=("prior-supported",),
        compatible_operator_ids=("operator-supported",),
        deriver=lambda *args, **kwargs: None,
    )
    prior = RiskPrior(
        prior_id="prior-unsupported",
        name="unsupported",
        description="unsupported",
        signals=("signal",),
        operator_ids=("operator-supported",),
        version="test-1",
    )
    operator = AttackOperator(
        operator_id="operator-supported",
        name="supported",
        description="supported",
        action="observe",
        safety_boundary="local",
    )
    target = _project_target()
    with pytest.raises(DiscoveryContractError, match="risk prior"):
        seed_project_campaign(
            "campaign-unsupported-prior",
            target,
            _graph(target),
            prior=prior,
            operator=operator,
            strategy=strategy,
        )


def test_non_temporal_prior_requires_explicit_strategy() -> None:
    prior = RiskPrior(
        prior_id="prior-non-temporal",
        name="non-temporal",
        description="non-temporal",
        signals=("signal",),
        operator_ids=("operator-non-temporal",),
        version="test-1",
    )
    operator = AttackOperator(
        operator_id="operator-non-temporal",
        name="non-temporal",
        description="non-temporal",
        action="observe",
        safety_boundary="local",
    )
    target = _project_target()
    with pytest.raises(DiscoveryContractError, match="explicit derivation strategy"):
        seed_project_campaign(
            "campaign-implicit-non-temporal",
            target,
            _graph(target),
            prior=prior,
            operator=operator,
        )


def test_strategy_seam_rejects_contradictory_change_inputs_before_deriver() -> None:
    strategy = make_risk_derivation_strategy(
        strategy_id="strategy-contradiction-v1",
        version="test-1",
        compatible_prior_ids=("prior-contradiction",),
        compatible_operator_ids=("operator-contradiction",),
        deriver=lambda *args, **kwargs: None,
    )
    prior = RiskPrior(
        prior_id="prior-contradiction",
        name="test family",
        description="test family",
        signals=("signal",),
        operator_ids=("operator-contradiction",),
        version="test-1",
    )
    operator = AttackOperator(
        operator_id="operator-contradiction",
        name="test operator",
        description="test operator",
        action="observe",
        safety_boundary="local",
    )
    target = _change_target()
    delta, drift = _change_inputs(target)
    contradictory = BehaviorDelta(
        delta_id=delta.delta_id,
        target_id=delta.target_id,
        subject=delta.subject,
        before=delta.before,
        after=delta.after,
        source_fact_ids=delta.source_fact_ids,
        confidence=delta.confidence,
        status="contradictory",
        contract_drift_id=delta.contract_drift_id,
        rationale="The change signal has contradictory provenance.",
    )
    result = derive_with_strategy(
        strategy,
        target,
        _graph(target),
        mode="change",
        behavior_delta=contradictory,
        contract_drift=drift,
        prior=prior,
        operator=operator,
    )
    assert result.accepted is False
    assert any("unresolved" in reason for reason in result.rejection_reasons)
