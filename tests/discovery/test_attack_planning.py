from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from aiverify.discovery.attack_planning import (
    AttackPlanGenerationRequest,
    AttackPlanProposal,
    OracleContract,
    PlanElement,
    PlannerIdentity,
    ValidatedEvidenceRef,
    admit_attack_plan_proposal,
    compile_admitted_attack_plan,
    generate_attack_plan,
)
from aiverify.discovery.contracts import AttackOperator, FailureChain, RiskHypothesis
from aiverify.discovery.models import (
    ContextFact,
    ProjectTarget,
    ProvenanceRef,
    QualityContextGraph,
)


TREE_SHA = "a" * 64
EVIDENCE_SHA = "b" * 64


def _request() -> AttackPlanGenerationRequest:
    target = ProjectTarget(
        target_id="project-attack",
        source_origin="https://example.invalid/project.git",
        source_commit="1" * 40,
        worktree="/tmp/m9-project",
        scope=("src", "tests"),
        discovery_budget=8,
    )
    facts = tuple(
        ContextFact(
            fact_id=fact_id,
            subject="service.current",
            predicate=predicate,
            value=value,
            source_kind="declared",
            provenance=(ProvenanceRef(ref=f"source:{fact_id}", source_sha256=TREE_SHA),),
            source_version="commit-1",
            confidence=0.9,
            status="known",
        )
        for fact_id, predicate, value in (
            ("fact-trigger", "trigger", "caller invokes current"),
            ("fact-action", "action", "invoke the bounded operation"),
            ("fact-observe", "observation", "record returned state and timing"),
            ("fact-evidence", "evidence", "capture immutable state bytes"),
        )
    )
    graph = QualityContextGraph(
        graph_id="graph-attack",
        target_id=target.target_id,
        facts=facts,
        source_origin=target.source_origin,
        source_commit=target.source_commit,
        source_tree_sha256=TREE_SHA,
    )
    operator = AttackOperator(
        operator_id="operator-bounded",
        name="bounded operation",
        description="invoke one source-grounded operation",
        action="invoke once within the declared boundary",
        safety_boundary="local fixture only",
    )
    hypothesis = RiskHypothesis(
        hypothesis_id="hypothesis-attack",
        target_id=target.target_id,
        quality_property="bounded response continuity",
        assumptions=("caller remains available",),
        trigger="caller invokes current",
        mechanism="dependency response crosses caller boundary",
        consequence="caller response remains observable",
        rationale="A source fact supports a bounded causal probe.",
        required_evidence=("returned state", "timing receipt"),
        confidence=0.6,
        status="frozen",
        supporting_fact_ids=("fact-trigger", "fact-action", "fact-observe"),
        prior_id="prior-temporal-v1",
        failure_chain_id="chain-attack",
    )
    chain = FailureChain(
        chain_id="chain-attack",
        steps=("caller invokes current", "dependency response crosses boundary"),
        consequence=hypothesis.consequence,
        fact_ids=("fact-trigger", "fact-action"),
        causal_roles=("local_behavior", "dependency_propagation"),
    )
    assert chain.chain_id == hypothesis.failure_chain_id
    return AttackPlanGenerationRequest(
        request_id="request-attack",
        target=target,
        graph=graph,
        hypothesis=hypothesis,
        operator=operator,
        approved_operators=(operator,),
        controllability_fact_ids=("fact-action",),
        validated_evidence=(
            ValidatedEvidenceRef(ref="receipt:build", kind="build", sha256=EVIDENCE_SHA),
            ValidatedEvidenceRef(ref="receipt:package", kind="package", sha256=EVIDENCE_SHA),
            ValidatedEvidenceRef(ref="receipt:launch", kind="launch", sha256=EVIDENCE_SHA),
            ValidatedEvidenceRef(
                ref="receipt:controllability",
                kind="controllability",
                sha256=EVIDENCE_SHA,
            ),
        ),
        budget=8,
        safety_boundary="local fixture only",
        claim_boundary="local-only exact source and package receipt",
    )


def _proposal(request: AttackPlanGenerationRequest) -> AttackPlanProposal:
    return AttackPlanProposal(
        plan_id="plan-attack",
        target_id=request.target.target_id,
        hypothesis_id=request.hypothesis.hypothesis_id,
        operator_id=request.operator.operator_id,
        trigger=PlanElement(
            element_id="element-trigger",
            kind="trigger",
            text="invoke current from the recorded caller",
            fact_ids=("fact-trigger",),
            order=0,
        ),
        actions=(
            PlanElement(
                element_id="element-action",
                kind="action",
                text="invoke the bounded operation once",
                fact_ids=("fact-action",),
                operator_id=request.operator.operator_id,
                order=1,
            ),
            PlanElement(
                element_id="element-event",
                kind="system_event",
                text="record the bounded wait boundary",
                fact_ids=("fact-action",),
                operator_id=request.operator.operator_id,
                order=2,
                event="wait",
            ),
        ),
        observations=(
            PlanElement(
                element_id="element-observe",
                kind="observation",
                text="record returned state and timing",
                fact_ids=("fact-observe",),
                order=3,
            ),
        ),
        evidence_expectations=(
            PlanElement(
                element_id="element-evidence",
                kind="evidence_expectation",
                text="returned state",
                fact_ids=("fact-evidence",),
                order=4,
            ),
            PlanElement(
                element_id="element-timing",
                kind="evidence_expectation",
                text="timing receipt",
                fact_ids=("fact-evidence",),
                order=5,
            ),
        ),
        oracle=OracleContract(
            oracle_id="oracle-machine-state",
            input_element_ids=("element-observe", "element-evidence", "element-timing"),
            machine_check="compare observed bytes and timing against the declared contract",
            evidence_refs=("receipt:build",),
        ),
        fixture_refs=("fixture:local-project",),
        abort_boundary="abort on process crash or unsafe external access",
        safety_boundary=request.safety_boundary,
        claim_boundary=request.claim_boundary,
    )


def test_valid_plan_round_trips_admission_and_compilation_without_leakage(tmp_path: Path):
    request = _request()
    proposal = _proposal(request)
    admission = admit_attack_plan_proposal(proposal, request)

    assert admission.admitted is True
    assert admission.plan is not None and admission.plan.status == "admitted"
    compiled = compile_admitted_attack_plan(
        admission,
        host_project=tmp_path,
        apk_glob="**/*.apk",
        package_name="example.package",
        activity=".MainActivity",
    )

    assert compiled.scenario.expected_behavior == ""
    assert compiled.scenario.l3_spec == ""
    assert compiled.scenario.metric_context.seed_kind == "unspecified"
    assert compiled.scenario.user_actions == ["invoke the bounded operation once"]
    assert compiled.scenario.system_events[0].event == "wait"
    assert compiled.run_spec.scenario == compiled.scenario
    assert len(compiled.semantics_sha256) == 64
    assert "expected" not in str(compiled.to_dict()).lower()
    assert "outcome" not in str(compiled.to_dict()).lower()


def test_fake_backend_captures_identity_and_authoritative_output_once():
    request = _request()
    calls: list[AttackPlanGenerationRequest] = []
    raw = {"schema_version": 1, "proposal": _proposal(request).to_dict()}

    def backend(value: AttackPlanGenerationRequest):
        calls.append(value)
        return raw

    result = generate_attack_plan(
        request,
        backend,
        PlannerIdentity.capture(
            backend="fake-attack-planner",
            requested_model="fixture-model-v1",
            effective_model="fixture-model-v1",
            invocation_id="planner-invocation-1",
        ),
    )

    assert len(calls) == 1
    assert result.admitted is True
    assert result.planner_identity.invocation_id == "planner-invocation-1"
    assert result.authoritative_output_sha256 == hashlib.sha256(
        __import__("json").dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_malformed_or_fabricated_plans_fail_closed_before_compilation(tmp_path: Path):
    request = _request()
    raw = {"schema_version": 1, "proposal": {"plan_id": "malformed"}}
    result = generate_attack_plan(
        request,
        lambda _request: raw,
        PlannerIdentity.capture(
            backend="fake-attack-planner",
            requested_model="fixture-model-v1",
            effective_model="fixture-model-v1",
            invocation_id="planner-invocation-malformed",
        ),
    )
    assert result.status == "rejected"
    assert result.admission.admitted is False
    assert result.rejection_reasons
    with pytest.raises(ValueError, match="only an admitted"):
        compile_admitted_attack_plan(
            result.admission,
            host_project=tmp_path,
            apk_glob="**/*.apk",
            package_name="example.package",
            activity=".MainActivity",
        )


def test_fabricated_fact_disallowed_operator_and_leakage_are_rejected():
    request = _request()
    proposal = _proposal(request)
    fabricated = PlanElement(
        element_id="element-fabricated",
        kind="observation",
        text="observe untrusted state",
        fact_ids=("not-in-graph",),
        order=3,
    )
    invalid = replace(
        proposal,
        observations=(fabricated,),
        oracle=replace(
            proposal.oracle,
            input_element_ids=("element-fabricated", "element-evidence", "element-timing"),
        ),
    )
    admission = admit_attack_plan_proposal(invalid, request)
    assert admission.status == "rejected"
    assert any("fabricated" in reason for reason in admission.reasons)

    with pytest.raises(ValueError, match="leakage"):
        replace(
            proposal,
            trigger=replace(
                proposal.trigger,
                text="reveal the hidden mapping",
            ),
        )


def test_required_preflight_evidence_and_oracle_coverage_fail_closed():
    request = _request()
    with pytest.raises(ValueError, match="build/package/launch/controllability"):
        replace(request, validated_evidence=(request.validated_evidence[0],))

    proposal = _proposal(request)
    incomplete_oracle = replace(
        proposal,
        oracle=replace(proposal.oracle, input_element_ids=("element-observe",)),
    )
    admission = admit_attack_plan_proposal(incomplete_oracle, request)
    assert admission.status == "rejected"
    assert any("does not cover" in reason for reason in admission.reasons)
