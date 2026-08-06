from __future__ import annotations

import pytest

from aiverify.discovery import (
    AttemptEvidence,
    ContextFact,
    DiscoveryContractError,
    FailureChain,
    FalsificationReviewerIdentity,
    FalsificationReviewResult,
    HypothesisCandidate,
    HypothesisGenerationRequest,
    HypothesisGeneratorIdentity,
    ProjectTarget,
    ProvenanceRef,
    QualityContextGraph,
    RiskHypothesis,
    approved_m9_prior_registry,
    freeze_hypothesis_portfolio,
    generate_hypothesis_response,
    validate_contract,
)
from aiverify.discovery.exploration import (
    evaluate_stop,
    initialize_exploration_campaign,
    make_campaign_artifact,
    rank_next_probes,
    record_attack_decision,
    record_attempt,
    record_falsification_review,
    record_hypothesis_decision,
    record_stop,
    replay_exploration_campaign,
    stop_exploration,
)


TREE_SHA = "a" * 64
FACT_SHA = "b" * 64


def _target(*, discovery_budget: int = 8) -> ProjectTarget:
    return ProjectTarget(
        target_id="project-exploration-fixture",
        source_origin="https://example.invalid/exploration-fixture",
        source_commit="exploration-source-v1",
        worktree="/tmp/exploration-fixture",
        scope=("src",),
        discovery_budget=discovery_budget,
    )


def _fact(fact_id: str, predicate: str, value: str) -> ContextFact:
    return ContextFact(
        fact_id=fact_id,
        subject="MainScreen",
        predicate=predicate,
        value=value,
        source_kind="derived",
        provenance=(ProvenanceRef(ref="src/MainScreen.kt", source_sha256=FACT_SHA, locator="1"),),
        source_version="exploration-source-v1",
        confidence=0.9,
        status="known",
    )


def _graph(target: ProjectTarget, *, include_unknown: bool = False) -> QualityContextGraph:
    facts = [
        _fact("fact-lifecycle", "lifecycle_boundary", "onStop"),
        _fact("fact-ownership", "ownership_boundary", "viewModelScope"),
        _fact("fact-quality", "quality_contract_signal", "lifecycle ownership continuity"),
    ]
    if include_unknown:
        facts.append(
            ContextFact(
                fact_id="fact-unresolved",
                subject="MainScreen",
                predicate="runtime_owner",
                value="unknown",
                source_kind="unknown",
                provenance=(),
                source_version="exploration-source-v1",
                confidence=0.0,
                status="unknown",
                rationale="The bounded fixture does not identify the runtime owner.",
            )
        )
    return QualityContextGraph(
        graph_id="graph-exploration-fixture",
        target_id=target.target_id,
        facts=tuple(facts),
        source_origin=target.source_origin,
        source_commit=target.source_commit,
        source_tree_sha256=TREE_SHA,
    )


def _request(*, target: ProjectTarget, graph: QualityContextGraph, budget: int = 8) -> HypothesisGenerationRequest:
    return HypothesisGenerationRequest(
        request_id="generation-exploration-fixture",
        target=target,
        graph=graph,
        approved_priors=tuple(item.prior for item in approved_m9_prior_registry()),
        budget=budget,
    )


def _candidate(request: HypothesisGenerationRequest, index: int) -> HypothesisCandidate:
    definition = approved_m9_prior_registry()[(index - 1) % 3]
    hypothesis_id = f"hypothesis-exploration-{index}"
    chain_id = f"chain-exploration-{index}"
    quality = "lifecycle ownership continuity"
    hypothesis = RiskHypothesis(
        hypothesis_id=hypothesis_id,
        target_id=request.target.target_id,
        quality_property=quality,
        assumptions=("the recorded owner remains active",),
        trigger=f"owner boundary {index} releases a task resource",
        mechanism=f"task resource {index} remains active across the owner handoff",
        consequence=quality,
        rationale="The candidate is bound to provenance-backed context facts.",
        required_evidence=("owner boundary identity", "release observation"),
        confidence=0.8,
        status="draft",
        supporting_fact_ids=("fact-lifecycle", "fact-ownership", "fact-quality"),
        prior_id=definition.prior_id,
        failure_chain_id=chain_id,
        unknowns=("cancellation timing",),
    )
    chain = FailureChain(
        chain_id=chain_id,
        steps=(
            f"owner {index} owns a task resource",
            f"owner boundary {index} releases the task",
            f"resource {index} crosses the recorded handoff",
        ),
        consequence=quality,
        fact_ids=("fact-lifecycle", "fact-ownership", "fact-quality"),
        causal_roles=("local_behavior", "dependency_propagation", "system_impact"),
    )
    return HypothesisCandidate(
        candidate_id=f"candidate-exploration-{index}",
        prior_id=definition.prior_id,
        operator_id=definition.operator_id,
        hypothesis=hypothesis,
        failure_chain=chain,
        uncertainty=("cancellation timing",),
    )


def _portfolio(*, target_budget: int = 8, request_budget: int = 8, candidate_count: int = 3):
    target = _target(discovery_budget=target_budget)
    graph = _graph(target)
    request = _request(target=target, graph=graph, budget=request_budget)
    candidates = tuple(_candidate(request, index) for index in range(1, candidate_count + 1))
    identity = HypothesisGeneratorIdentity.capture(
        backend="fake-hypothesis-backend",
        requested_model="fixture-model-v1",
        effective_model="fixture-model-v1",
        invocation_id="exploration-generator-1",
    )
    response = generate_hypothesis_response(
        request,
        lambda _: {"schema_version": 1, "candidates": [item.to_dict() for item in candidates]},
        identity,
    )
    return target, graph, freeze_hypothesis_portfolio(request, response)


def _artifact(name: str, content: object | None = None):
    return make_campaign_artifact(
        "fixture:" + name,
        "bounded-fixture",
        content if content is not None else {"name": name},
    )


def _prepared_state(*, target_budget: int = 8, request_budget: int = 8, unknown: bool = False):
    target, graph, portfolio = _portfolio(target_budget=target_budget, request_budget=request_budget)
    if unknown:
        graph = _graph(target, include_unknown=True)
        # The portfolio is intentionally regenerated against the graph because its provenance
        # digest is part of the frozen source contract.
        request = _request(target=target, graph=graph, budget=request_budget)
        candidates = tuple(_candidate(request, index) for index in range(1, 4))
        identity = HypothesisGeneratorIdentity.capture(
            backend="fake-hypothesis-backend",
            requested_model="fixture-model-v1",
            effective_model="fixture-model-v1",
            invocation_id="exploration-generator-unknown-1",
        )
        response = generate_hypothesis_response(
            request,
            lambda _: {"schema_version": 1, "candidates": [item.to_dict() for item in candidates]},
            identity,
        )
        portfolio = freeze_hypothesis_portfolio(request, response)
    state = initialize_exploration_campaign("campaign-exploration-fixture", target, graph, portfolio)
    for candidate in portfolio.candidates:
        state = record_hypothesis_decision(
            state,
            candidate.candidate_id,
            portfolio.decision_for(candidate.candidate_id),
            rationale="The frozen portfolio decision is recorded before attack admission.",
            artifact_refs=(_artifact("decision-" + candidate.candidate_id),),
        )
    return state


def _admit(state, hypothesis_id: str, *, decision: str = "admitted"):
    return record_attack_decision(
        state,
        hypothesis_id,
        decision=decision,
        attack_ref="attack:" + hypothesis_id,
        rationale="The bounded fixture attack has an explicit admission decision.",
        artifact_refs=(_artifact("attack-" + hypothesis_id),),
        admission={"status": decision, "side_effects": False},
    )


def _attempt(state, hypothesis_id: str, *, outcome: str, attempt_number: int, accountable: bool | None = None):
    if accountable is None:
        accountable = outcome != "non_accountable"
    return record_attempt(
        state,
        AttemptEvidence(
            evidence_id=f"evidence-{attempt_number}",
            target_id=state.target.target_id,
            hypothesis_id=hypothesis_id,
            attempt_ref=f"attempt-{attempt_number}",
            execution_record_ref=f"attempt-{attempt_number}/execution-record.json",
            outcome=outcome,
            evidence_refs=(f"attempt-{attempt_number}/raw-evidence.json",) if accountable else (),
            claim_boundary="bounded local fixture only",
            rationale="The result remains local, immutable, and explicitly bounded.",
            accountable=accountable,
            execution_identity_sha256=("c" * 64) if accountable else None,
        ),
        artifact_refs=(_artifact(f"attempt-{attempt_number}"),),
    )


def test_initialization_is_provenance_bound_and_schema_validated() -> None:
    state = _prepared_state()

    assert state.status == "exploring"
    assert state.events[0].event_type == "campaign_initialized"
    assert state.events[0].previous_digest == "0" * 64
    assert state.context_graph.source_tree_sha256 == state.portfolio.source_tree_sha256
    validate_contract(state.to_dict(), "exploration_campaign")
    for event in state.events:
        validate_contract(event.to_dict(), "exploration_event")
    assert replay_exploration_campaign(state.to_dict()) == state


def test_multiple_hypotheses_advance_from_recorded_state_and_ranking_is_deterministic() -> None:
    state = _prepared_state()
    first, second = state.portfolio.selected[:2]
    state = _admit(state, first.hypothesis.hypothesis_id)
    state = _admit(state, second.hypothesis.hypothesis_id)
    probes = rank_next_probes(state)
    assert [item.hypothesis_id for item in probes if item.admissible] == sorted(
        [first.hypothesis.hypothesis_id, second.hypothesis.hypothesis_id]
    )

    state = _attempt(state, first.hypothesis.hypothesis_id, outcome="supported", attempt_number=1)
    state = _attempt(state, second.hypothesis.hypothesis_id, outcome="inconclusive", attempt_number=2)
    assert len(state.attempts) == 2
    assert len(state.findings) == 2
    assert {item.hypothesis_id for item in state.findings} == {
        first.hypothesis.hypothesis_id,
        second.hypothesis.hypothesis_id,
    }
    assert state.remaining_budget == state.target.discovery_budget - 2
    assert state.coverage_frontier == ("hypothesis:" + state.portfolio.selected[2].hypothesis.hypothesis_id,)
    assert replay_exploration_campaign(state) == state


def test_unknown_context_and_non_accountable_outcome_remain_visible() -> None:
    state = _prepared_state(unknown=True)
    item = state.portfolio.selected[0]
    state = _admit(state, item.hypothesis.hypothesis_id)
    state = _attempt(
        state,
        item.hypothesis.hypothesis_id,
        outcome="non_accountable",
        attempt_number=3,
    )
    assert state.attempts[0].outcome == "non_accountable"
    assert state.attempts[0].accountable is False
    assert not state.findings
    assert state.residual_risks[0].evidence_gap
    assert "fact:fact-unresolved" in state.coverage_frontier
    assert state.risk_map.residual_risks == state.residual_risks


def test_deferred_decision_is_recorded_without_mutating_frozen_portfolio() -> None:
    state = _prepared_state(request_budget=8)
    # Build a separate four-candidate portfolio so the fourth candidate is deferred.
    target, graph, portfolio = _portfolio(request_budget=8, candidate_count=4)
    state = initialize_exploration_campaign("campaign-deferred", target, graph, portfolio)
    for candidate in portfolio.candidates:
        state = record_hypothesis_decision(
            state,
            candidate.candidate_id,
            portfolio.decision_for(candidate.candidate_id),
            rationale="Record every candidate decision, including deferred capacity.",
            artifact_refs=(_artifact("deferred-" + candidate.candidate_id),),
        )
    deferred = [
        item for item in state.hypothesis_decisions if item["decision"] == "deferred"
    ]
    assert deferred
    assert len(state.portfolio.selected) == 3
    assert state.portfolio == portfolio
    with pytest.raises(DiscoveryContractError, match="contradict"):
        record_hypothesis_decision(
            state,
            deferred[0]["candidate_id"],
            "selected",
            rationale="contradictory decision",
            artifact_refs=(_artifact("bad-decision"),),
        )


def test_rejected_attacks_stop_with_explicit_evidence() -> None:
    state = _prepared_state()
    for item in state.portfolio.selected:
        state = _admit(state, item.hypothesis.hypothesis_id, decision="rejected")
    stop = evaluate_stop(state)
    assert stop is not None
    assert stop.reason == "no_admissible_attack"
    validate_contract(stop.to_dict(), "exploration_stop")
    stopped = record_stop(
        state,
        reason=stop.reason,
        rationale=stop.rationale,
        evidence_refs=stop.evidence_refs,
        artifact_refs=stop.artifact_refs,
    )
    assert stopped.status == "stopped"
    assert stopped.stop == stop
    with pytest.raises(DiscoveryContractError, match="stopped"):
        _admit(stopped, state.portfolio.selected[0].hypothesis.hypothesis_id)


def test_budget_boundary_blocks_next_probe_and_stops_without_retry() -> None:
    state = _prepared_state(target_budget=1, request_budget=8)
    item = state.portfolio.selected[0]
    state = _admit(state, item.hypothesis.hypothesis_id)
    state = _attempt(state, item.hypothesis.hypothesis_id, outcome="rejected", attempt_number=4)
    assert state.remaining_budget == 0
    assert all(not probe.admissible for probe in rank_next_probes(state))
    assert evaluate_stop(state).reason == "budget_exhausted"
    with pytest.raises(DiscoveryContractError, match="budget"):
        _attempt(state, state.portfolio.selected[1].hypothesis.hypothesis_id, outcome="supported", attempt_number=5)


def test_terminal_finding_and_frontier_exhaustion_are_distinct_stop_reasons() -> None:
    terminal = _prepared_state()
    item = terminal.portfolio.selected[0]
    terminal = _admit(terminal, item.hypothesis.hypothesis_id)
    terminal = _attempt(terminal, item.hypothesis.hypothesis_id, outcome="supported", attempt_number=6)
    assert evaluate_stop(terminal).reason == "terminal_finding"

    exhausted = _prepared_state()
    for number, item in enumerate(exhausted.portfolio.selected, start=7):
        exhausted = _admit(exhausted, item.hypothesis.hypothesis_id)
        exhausted = _attempt(exhausted, item.hypothesis.hypothesis_id, outcome="non_accountable", attempt_number=number)
    assert exhausted.coverage_frontier == ()
    assert evaluate_stop(exhausted).reason == "frontier_exhausted"


def test_evidence_gap_and_policy_abort_require_explicit_stop_artifacts() -> None:
    state = _prepared_state(unknown=True)
    for number, item in enumerate(state.portfolio.selected, start=10):
        state = _admit(state, item.hypothesis.hypothesis_id)
        state = _attempt(state, item.hypothesis.hypothesis_id, outcome="non_accountable", attempt_number=number)
    stop = evaluate_stop(state)
    assert stop is not None and stop.reason == "evidence_gap"
    stopped = stop_exploration(
        state,
        reason=stop.reason,
        rationale=stop.rationale,
        evidence_refs=stop.evidence_refs,
        artifact_refs=stop.artifact_refs,
    )
    assert stopped.stop.reason == "evidence_gap"

    policy_state = _prepared_state()
    policy_stop = stop_exploration(
        policy_state,
        reason="policy_abort",
        rationale="The bounded operator requested a local policy abort.",
        evidence_refs=("policy:operator-abort",),
        artifact_refs=(_artifact("policy-abort"),),
    )
    assert policy_stop.stop.reason == "policy_abort"


def test_falsification_review_rejection_is_recorded_without_promoting_an_outcome() -> None:
    state = _prepared_state()
    item = state.portfolio.selected[0]
    state = _admit(state, item.hypothesis.hypothesis_id)
    state = _attempt(state, item.hypothesis.hypothesis_id, outcome="supported", attempt_number=20)
    identity = FalsificationReviewerIdentity.capture(
        backend="fake-falsifier",
        requested_model="fixture-model-v1",
        effective_model="fixture-model-v1",
        invocation_id="exploration-review-1",
        provider_family="fixture-family",
        same_family_limitation="bounded fixture review only",
    )
    result = FalsificationReviewResult(
        context_id="review-context-1",
        reviewer_identity=identity,
        authoritative_output_sha256="d" * 64,
        status="rejected",
        rejection_reasons=("clean context was incomplete",),
    )
    state = record_falsification_review(
        state,
        result,
        hypothesis_id=item.hypothesis.hypothesis_id,
        artifact_refs=(_artifact("rejected-review"),),
    )
    assert state.falsification_reviews == (result,)
    assert state.findings[0].conclusion == "supported"
    assert replay_exploration_campaign(state) == state


def test_duplicate_attempts_and_tampered_event_stream_are_rejected() -> None:
    state = _prepared_state()
    item = state.portfolio.selected[0]
    state = _admit(state, item.hypothesis.hypothesis_id)
    state = _attempt(state, item.hypothesis.hypothesis_id, outcome="inconclusive", attempt_number=21)
    with pytest.raises(DiscoveryContractError, match="retry|terminal outcome"):
        _attempt(state, item.hypothesis.hypothesis_id, outcome="supported", attempt_number=22)

    tampered = state.to_dict()
    tampered["events"][1]["payload"]["rationale"] = "changed"
    with pytest.raises(DiscoveryContractError, match="digest"):
        replay_exploration_campaign(tampered)

    tampered_artifact = state.to_dict()
    tampered_artifact["events"][0]["artifact_refs"][0]["sha256"] = "f" * 64
    with pytest.raises(DiscoveryContractError, match="digest"):
        replay_exploration_campaign(tampered_artifact)


def test_event_metadata_tampering_is_rejected_even_when_payload_is_valid() -> None:
    state = _prepared_state()
    item = state.portfolio.selected[0]
    state = _admit(state, item.hypothesis.hypothesis_id)
    state_dict = state.to_dict()
    event = state_dict["events"][-1]
    event["hypothesis_id"] = "hypothesis-not-in-payload"
    # The unchanged digest must fail first; this is the fail-closed boundary for the event.
    with pytest.raises(DiscoveryContractError, match="digest"):
        replay_exploration_campaign(state_dict)


def test_manual_finding_cannot_be_replaced_by_a_later_attempt() -> None:
    state = _prepared_state()
    item = state.portfolio.selected[0]
    state = _admit(state, item.hypothesis.hypothesis_id)
    # Use the public attempt path to derive the canonical Finding, then assert the
    # same hypothesis cannot receive a second terminal outcome.
    state = _attempt(state, item.hypothesis.hypothesis_id, outcome="rejected", attempt_number=30)
    assert state.findings
    with pytest.raises(DiscoveryContractError, match="terminal outcome|retry"):
        _attempt(state, item.hypothesis.hypothesis_id, outcome="inconclusive", attempt_number=31)
