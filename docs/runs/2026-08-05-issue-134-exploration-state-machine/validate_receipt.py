from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aiverify.discovery import (
    AttemptEvidence,
    ContextFact,
    FailureChain,
    HypothesisCandidate,
    HypothesisGenerationRequest,
    HypothesisGeneratorIdentity,
    ProjectTarget,
    ProvenanceRef,
    QualityContextGraph,
    RiskHypothesis,
    approved_m9_prior_registry,
    evaluate_stop,
    freeze_hypothesis_portfolio,
    generate_hypothesis_response,
    initialize_exploration_campaign,
    make_campaign_artifact,
    record_attack_decision,
    record_attempt,
    record_hypothesis_decision,
    rank_next_probes,
    replay_exploration_campaign,
)
from aiverify.discovery.schema import self_validate_schema, validate_contract


ROOT = Path(__file__).resolve().parent
TREE_SHA = "a" * 64
FACT_SHA = "b" * 64


def digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def fixture_state():
    target = ProjectTarget(
        target_id="project-exploration-fixture",
        source_origin="https://example.invalid/exploration-fixture",
        source_commit="exploration-source-v1",
        worktree="/tmp/exploration-fixture",
        scope=("src",),
        discovery_budget=8,
    )
    graph = QualityContextGraph(
        graph_id="graph-exploration-fixture",
        target_id=target.target_id,
        facts=tuple(
            ContextFact(
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
            for fact_id, predicate, value in (
                ("fact-lifecycle", "lifecycle_boundary", "onStop"),
                ("fact-ownership", "ownership_boundary", "viewModelScope"),
                ("fact-quality", "quality_contract_signal", "lifecycle ownership continuity"),
            )
        ),
        source_origin=target.source_origin,
        source_commit=target.source_commit,
        source_tree_sha256=TREE_SHA,
    )
    request = HypothesisGenerationRequest(
        request_id="generation-exploration-fixture",
        target=target,
        graph=graph,
        approved_priors=tuple(item.prior for item in approved_m9_prior_registry()),
        budget=8,
    )
    candidates = []
    for index in range(1, 4):
        definition = approved_m9_prior_registry()[(index - 1) % 3]
        hypothesis_id = f"hypothesis-exploration-{index}"
        chain_id = f"chain-exploration-{index}"
        hypothesis = RiskHypothesis(
            hypothesis_id=hypothesis_id,
            target_id=target.target_id,
            quality_property="lifecycle ownership continuity",
            assumptions=("the recorded owner remains active",),
            trigger=f"owner boundary {index} releases a task resource",
            mechanism=f"task resource {index} remains active across the owner handoff",
            consequence="lifecycle ownership continuity",
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
            consequence="lifecycle ownership continuity",
            fact_ids=("fact-lifecycle", "fact-ownership", "fact-quality"),
            causal_roles=("local_behavior", "dependency_propagation", "system_impact"),
        )
        candidates.append(
            HypothesisCandidate(
                candidate_id=f"candidate-exploration-{index}",
                prior_id=definition.prior_id,
                operator_id=definition.operator_id,
                hypothesis=hypothesis,
                failure_chain=chain,
                uncertainty=("cancellation timing",),
            )
        )
    generator_identity = HypothesisGeneratorIdentity.capture(
        backend="fake-hypothesis-backend",
        requested_model="fixture-model-v1",
        effective_model="fixture-model-v1",
        invocation_id="exploration-generator-1",
    )
    response = generate_hypothesis_response(
        request,
        lambda _: {"schema_version": 1, "candidates": [item.to_dict() for item in candidates]},
        generator_identity,
    )
    portfolio = freeze_hypothesis_portfolio(request, response)
    state = initialize_exploration_campaign("campaign-exploration-fixture", target, graph, portfolio)

    def artifact(name: str, content: object | None = None):
        return make_campaign_artifact("fixture:" + name, "bounded-fixture", content or {"name": name})

    for candidate in portfolio.candidates:
        state = record_hypothesis_decision(
            state,
            candidate.candidate_id,
            portfolio.decision_for(candidate.candidate_id),
            rationale="The frozen portfolio decision is recorded before attack admission.",
            artifact_refs=(artifact("decision-" + candidate.candidate_id),),
        )
    for item in portfolio.selected[:2]:
        state = record_attack_decision(
            state,
            item.hypothesis.hypothesis_id,
            decision="admitted",
            attack_ref="attack:" + item.hypothesis.hypothesis_id,
            rationale="The bounded fixture attack has an explicit admission decision.",
            artifact_refs=(artifact("attack-" + item.hypothesis.hypothesis_id),),
            admission={"status": "admitted", "side_effects": False},
        )
    first, second = portfolio.selected[:2]
    for number, item, outcome, accountable in (
        (1, first, "supported", True),
        (2, second, "non_accountable", False),
    ):
        evidence = AttemptEvidence(
            evidence_id=f"evidence-{number}",
            target_id=target.target_id,
            hypothesis_id=item.hypothesis.hypothesis_id,
            attempt_ref=f"attempt-{number}",
            execution_record_ref=f"attempt-{number}/execution-record.json",
            outcome=outcome,
            evidence_refs=(f"attempt-{number}/raw-evidence.json",) if accountable else (),
            claim_boundary="bounded local fixture only",
            rationale="The result remains local, immutable, and explicitly bounded.",
            accountable=accountable,
            execution_identity_sha256=("c" * 64) if accountable else None,
        )
        state = record_attempt(
            state,
            evidence,
            artifact_refs=(artifact(f"attempt-{number}"),),
        )
    return state


def main() -> None:
    receipt = json.loads((ROOT / "bounded-exploration-receipt.json").read_text(encoding="utf-8"))
    assert receipt["scope"] == "non-holdout-local-fixture"
    assert receipt["formal_holdout"] is False
    assert receipt["side_effects"] == {
        "agent": False,
        "build": False,
        "device": False,
        "production": False,
        "runtime": False,
    }
    state = fixture_state()
    expected = receipt["expected_state"]
    assert state.campaign_id == receipt["fixture"]["campaign_id"]
    assert state.target.target_id == receipt["fixture"]["target_id"]
    assert state.portfolio.portfolio_id == receipt["fixture"]["portfolio_id"]
    assert state.portfolio.generator_identity.to_dict() == {
        "schema_version": 1,
        "role": receipt["identity"]["role"],
        "backend": receipt["identity"]["backend"],
        "requested_model": receipt["identity"]["requested_model"],
        "effective_model": receipt["identity"]["effective_model"],
        "invocation_id": receipt["identity"]["invocation_id"],
        "identity_sha256": receipt["identity"]["identity_sha256"],
    }
    assert state.context_graph.source_tree_sha256 == receipt["identity"]["source_tree_sha256"]
    assert state.status == expected["status"]
    assert len(state.events) == expected["event_count"]
    assert [event.event_type for event in state.events] == expected["event_types"]
    assert state.event_head_digest == expected["event_head_digest"]
    assert [item.outcome for item in state.attempts] == expected["attempt_outcomes"]
    assert [item.conclusion for item in state.findings] == expected["finding_conclusions"]
    assert [item.hypothesis_id for item in state.residual_risks] == expected["residual_hypotheses"]
    assert len(state.attempts) == expected["attempt_count"]
    assert len(state.findings) == expected["finding_count"]
    assert len(state.residual_risks) == expected["residual_risk_count"]
    assert len(state.falsification_reviews) == expected["falsification_review_count"]
    assert state.remaining_budget == expected["remaining_budget"]
    assert list(state.coverage_frontier) == expected["coverage_frontier"]
    assert digest(state.risk_map.to_dict()) == expected["risk_map_digest"]
    assert digest(state.to_dict()) == expected["state_digest"]
    assert evaluate_stop(state).reason == expected["evaluated_stop"]
    assert len(rank_next_probes(state)) == 1
    assert replay_exploration_campaign(state.to_dict()) == state

    self_validate_schema()
    validate_contract(state.to_dict(), "exploration_campaign")
    for event in state.events:
        validate_contract(event.to_dict(), "exploration_event")
    packages = sorted(
        path for path in (ROOT / "artifacts").iterdir()
        if path.suffix in {".whl", ".gz"}
    )
    assert len(packages) == 2
    manifest = {}
    for line in (ROOT / "checksums.sha256").read_text(encoding="utf-8").splitlines():
        if line.strip():
            checksum, relative = line.split("  ", 1)
            manifest[relative] = checksum
    assert manifest
    for relative, checksum in manifest.items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == checksum, relative
    print(json.dumps({
        "status": "passed",
        "source_contract_checks": 4,
        "event_chain_checks": len(state.events),
        "state_replay_checks": 2,
        "package_artifact_checks": len(packages),
        "checksum_manifest_checks": len(manifest),
        "formal_holdout_executed": False,
        "side_effects": False,
    }, indent=2))


if __name__ == "__main__":
    main()
