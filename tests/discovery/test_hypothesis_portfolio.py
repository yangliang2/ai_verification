from __future__ import annotations

import json
from dataclasses import replace

import pytest

from aiverify.discovery import (
    CandidateRejection,
    ChangeTarget,
    ContextFact,
    DiscoveryContractError,
    FailureChain,
    HypothesisCandidate,
    HypothesisGenerationRequest,
    HypothesisGenerationResponse,
    HypothesisGeneratorIdentity,
    HypothesisPortfolio,
    ProjectTarget,
    ProvenanceRef,
    QualityContextGraph,
    RiskHypothesis,
    approved_m9_prior_registry,
    calculate_risk_priority,
    freeze_hypothesis_portfolio,
    generate_hypothesis_response,
    validate_contract,
    validate_hypothesis_candidate,
)


_TREE = "a" * 64
_FACT_SHA = "b" * 64


def _target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-portfolio-fixture",
        source_origin="https://example.invalid/portfolio-fixture",
        source_commit="portfolio-source-v1",
        worktree="/tmp/portfolio-fixture",
        scope=("src",),
        discovery_budget=16,
    )


def _fact(fact_id: str, predicate: str, value: str) -> ContextFact:
    return ContextFact(
        fact_id=fact_id,
        subject="MainScreen",
        predicate=predicate,
        value=value,
        source_kind="derived",
        provenance=(ProvenanceRef(ref="src/MainScreen.kt", source_sha256=_FACT_SHA, locator="1"),),
        source_version="portfolio-source-v1",
        confidence=0.9,
        status="known",
    )


def _graph(target: ProjectTarget | None = None) -> QualityContextGraph:
    target = target or _target()
    return QualityContextGraph(
        graph_id="graph-portfolio-fixture",
        target_id=target.target_id,
        facts=(
            _fact("fact-lifecycle", "lifecycle_boundary", "onStop"),
            _fact("fact-ownership", "ownership_boundary", "viewModelScope"),
            _fact(
                "fact-quality",
                "quality_contract_signal",
                "lifecycle ownership continuity",
            ),
        ),
        source_origin=target.source_origin,
        source_commit=target.source_commit,
        source_tree_sha256=_TREE,
    )


def _request(budget: int = 8) -> HypothesisGenerationRequest:
    target = _target()
    return HypothesisGenerationRequest(
        request_id="generation-request-1",
        target=target,
        graph=_graph(target),
        approved_priors=tuple(item.prior for item in approved_m9_prior_registry()),
        budget=budget,
    )


def _candidate(
    request: HypothesisGenerationRequest,
    *,
    index: int,
    prior_index: int,
    trigger: str | None = None,
) -> HypothesisCandidate:
    definition = approved_m9_prior_registry()[prior_index]
    hypothesis_id = f"candidate-hypothesis-{index}"
    chain_id = f"candidate-chain-{index}"
    quality = "lifecycle ownership continuity"
    hypothesis = RiskHypothesis(
        hypothesis_id=hypothesis_id,
        target_id=request.target.target_id,
        quality_property=quality,
        assumptions=("the recorded owner remains active",),
        trigger=trigger or f"owner boundary {index} releases a task resource",
        mechanism=f"task resource {index} remains active across the owner handoff",
        consequence=quality,
        rationale="The candidate is bound to three provenance-backed context facts.",
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
        candidate_id=f"candidate-{index}",
        prior_id=definition.prior_id,
        operator_id=definition.operator_id,
        hypothesis=hypothesis,
        failure_chain=chain,
        uncertainty=("cancellation timing",),
    )


def _identity() -> HypothesisGeneratorIdentity:
    return HypothesisGeneratorIdentity.capture(
        backend="fake-hypothesis-backend",
        requested_model="fixture-model-v1",
        effective_model="fixture-model-v1",
        invocation_id="fake-invocation-1",
    )


def test_registry_has_three_families_and_lifetime_contract() -> None:
    registry = approved_m9_prior_registry()
    assert len(registry) == 3
    assert [item.prior_id for item in registry] == [
        "prior-synchronous-critical-path-v1",
        "prior-state-evolution-compatibility-v1",
        "prior-lifetime-ownership-drift-v1",
    ]
    assert registry[-1].operator_id == "operator-bounded-lifecycle-ownership-drift"
    assert registry[-1].strategy.version == "m9.1"
    lifetime_result = registry[-1].strategy.derive(_target(), _graph(), mode="project")
    assert lifetime_result.accepted is True
    assert lifetime_result.hypothesis is not None
    assert lifetime_result.hypothesis.prior_id == registry[-1].prior_id


def test_fake_generation_is_identity_bound_and_freezes_three_deterministically() -> None:
    request = _request()
    candidates = tuple(
        _candidate(request, index=index, prior_index=index - 1)
        for index in (1, 2, 3)
    )
    calls: list[HypothesisGenerationRequest] = []

    def backend(received: HypothesisGenerationRequest) -> dict:
        calls.append(received)
        return {"schema_version": 1, "candidates": [item.to_dict() for item in candidates]}

    response = generate_hypothesis_response(request, backend, _identity())
    portfolio = freeze_hypothesis_portfolio(request, response)

    assert calls == [request]
    assert response.authoritative_output_sha256
    assert response.generator_identity.requested_model == "fixture-model-v1"
    assert len(portfolio.selected) == 3
    assert portfolio.status == "frozen"
    assert portfolio.budget_consumed == 3
    assert portfolio.remaining_budget == 5
    assert [entry.decision for entry in portfolio.selection_ledger.entries] == [
        "selected",
        "selected",
        "selected",
    ]
    assert portfolio == HypothesisPortfolio.from_dict(portfolio.to_dict())
    validate_contract(response.to_dict(), "hypothesis_generation_response")
    validate_contract(portfolio.to_dict(), "hypothesis_portfolio")
    serialized_request = json.dumps(request.to_dict(), sort_keys=True).lower()
    assert all(term not in serialized_request for term in ("journey", "hidden_mapping", "expected_oracle", "verdict"))


def test_priority_and_order_are_deterministic_after_backend_capture() -> None:
    request = _request()
    first_candidates = tuple(
        _candidate(request, index=index, prior_index=(index - 1) % 3)
        for index in (1, 2, 3, 4)
    )
    raw = {"schema_version": 1, "candidates": [item.to_dict() for item in first_candidates]}

    def backend(_: HypothesisGenerationRequest) -> dict:
        return raw

    first = freeze_hypothesis_portfolio(
        request,
        generate_hypothesis_response(request, backend, _identity()),
    )
    second = freeze_hypothesis_portfolio(
        request,
        generate_hypothesis_response(request, backend, _identity()),
    )
    assert first == second
    assert len(first.selected) == 3
    assert first.decision_for("candidate-4") == "deferred"
    assert first.coverage_frontier == ()
    assert first.remaining_prior_ids == ()
    assert first.remaining_fact_ids == ()
    assert "not a probability" in first.priorities[0].rationale
    assert calculate_risk_priority(first_candidates[0], request.graph) == calculate_risk_priority(
        first_candidates[0], request.graph
    )


def test_invalid_missing_generic_leaking_and_duplicate_candidates_are_audited() -> None:
    request = _request()
    valid = _candidate(request, index=1, prior_index=0)
    missing = replace(
        valid,
        candidate_id="candidate-missing",
        hypothesis=replace(
            valid.hypothesis,
            hypothesis_id="hypothesis-missing",
            supporting_fact_ids=("fact-missing",),
            failure_chain_id="chain-missing",
        ),
        failure_chain=replace(
            valid.failure_chain,
            chain_id="chain-missing",
            fact_ids=("fact-missing",),
        ),
    )
    generic = replace(
        valid,
        candidate_id="candidate-generic",
        hypothesis=replace(
            valid.hypothesis,
            hypothesis_id="hypothesis-generic",
            trigger="something may go wrong",
            mechanism="quality may degrade",
            failure_chain_id="chain-generic",
        ),
        failure_chain=replace(valid.failure_chain, chain_id="chain-generic"),
    )
    leaking = replace(
        valid,
        candidate_id="candidate-leaking",
        hypothesis=replace(
            valid.hypothesis,
            hypothesis_id="hypothesis-leaking",
            trigger="the expected oracle verdict uses a hidden mapping",
            failure_chain_id="chain-leaking",
        ),
        failure_chain=replace(valid.failure_chain, chain_id="chain-leaking"),
    )
    duplicate = replace(
        valid,
        candidate_id="candidate-duplicate",
        hypothesis=replace(valid.hypothesis, hypothesis_id="hypothesis-duplicate"),
        failure_chain=replace(valid.failure_chain, chain_id="chain-duplicate"),
    )
    duplicate = replace(
        duplicate,
        hypothesis=replace(duplicate.hypothesis, failure_chain_id="chain-duplicate"),
    )
    for candidate, term in (
        (missing, "missing fact"),
        (generic, "generic"),
        (leaking, "outcome leakage"),
    ):
        reasons = validate_hypothesis_candidate(
            candidate,
            request,
            next(item for item in approved_m9_prior_registry() if item.prior_id == candidate.prior_id),
        )
        assert any(term in reason for reason in reasons)

    response = generate_hypothesis_response(
        request,
        lambda _: {
            "schema_version": 1,
            "candidates": [
                valid.to_dict(),
                missing.to_dict(),
                generic.to_dict(),
                leaking.to_dict(),
                duplicate.to_dict(),
            ],
        },
        _identity(),
    )
    portfolio = freeze_hypothesis_portfolio(request, response)
    decisions = {entry.hypothesis_id: entry.decision for entry in portfolio.selection_ledger.entries}
    assert decisions["candidate-1"] == "selected"
    assert decisions["candidate-missing"] == "rejected"
    assert decisions["candidate-generic"] == "rejected"
    assert decisions["candidate-leaking"] == "rejected"
    assert decisions["candidate-duplicate"] == "rejected"
    assert len(portfolio.rejected_candidates) == 4
    assert all(item.reasons for item in portfolio.rejected_candidates)


def test_malformed_backend_candidate_is_captured_as_rejection() -> None:
    request = _request(budget=1)
    valid = _candidate(request, index=1, prior_index=0)
    response = generate_hypothesis_response(
        request,
        lambda _: {
            "schema_version": 1,
            "candidates": [valid.to_dict(), {"candidate_id": "candidate-incomplete"}],
        },
        _identity(),
    )
    assert response.status == "partial"
    assert len(response.rejected_candidates) == 1
    portfolio = freeze_hypothesis_portfolio(request, response)
    assert portfolio.decision_for("candidate-incomplete") == "rejected"
    assert portfolio.decision_for("candidate-1") == "selected"


def test_response_and_request_reject_identity_or_target_drift() -> None:
    request = _request()
    valid = _candidate(request, index=1, prior_index=0)
    response = generate_hypothesis_response(
        request,
        lambda _: {"schema_version": 1, "candidates": [valid.to_dict()]},
        _identity(),
    )
    with pytest.raises(DiscoveryContractError, match="target"):
        freeze_hypothesis_portfolio(
            request,
            replace(response, target_id="other-target"),
        )
    with pytest.raises(DiscoveryContractError, match="identity digest"):
        HypothesisGeneratorIdentity(
            backend="fake",
            requested_model="m",
            effective_model="m",
            invocation_id="i",
            identity_sha256="c" * 64,
        )
    with pytest.raises(DiscoveryContractError, match="ProjectTarget"):
        HypothesisGenerationRequest(
            request_id="change-request",
            target=ChangeTarget(
                target_id="change-target",
                source_origin=request.target.source_origin,
                source_commit=request.target.source_commit,
                worktree=request.target.worktree,
                diff_ref="fixture.patch",
                diff_sha256="c" * 64,
            ),
            graph=request.graph,
            approved_priors=request.approved_priors,
            budget=1,
        )
