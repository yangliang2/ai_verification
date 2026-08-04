from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiverify.discovery import (
    ChangeTarget,
    ContextEdge,
    ContextFact,
    ContextNode,
    DiscoveryContractError,
    ProjectTarget,
    QualityContextGraph,
    ProvenanceRef,
    load_context_manifest,
    validate_contract,
)


_FIXTURE = Path("bench/discovery-fixtures/synchronous-weather/context-manifest.json")


def _change_target() -> ChangeTarget:
    return ChangeTarget(
        target_id="change-weather-001",
        source_origin="https://example.invalid/aiverify-discovery-fixture",
        source_commit="fixture-commit-v1",
        worktree="/workspace/discovery-fixture",
        diff_ref="change.diff",
        diff_sha256="a" * 64,
    )


def _project_target() -> ProjectTarget:
    return ProjectTarget(
        target_id="project-weather-001",
        source_origin="https://example.invalid/aiverify-discovery-fixture",
        source_commit="fixture-commit-v1",
        worktree="/workspace/discovery-fixture",
        scope=("weather-service", "systemui-consumer"),
        discovery_budget=8,
    )


def test_fixture_graph_supports_change_and_project_seeds_and_queries_paths() -> None:
    change = load_context_manifest(_FIXTURE, _change_target())
    project = load_context_manifest(_FIXTURE, _project_target())

    assert change.graph.target_id == "change-weather-001"
    assert project.graph.target_id == "project-weather-001"
    assert change.graph.fact("fact-runtime-thread").status == "unknown"

    forward = change.graph.trace_forward("service-operation")
    backward = project.graph.trace_backward("systemui-consumer")

    assert forward.node_ids[:4] == (
        "service-operation",
        "api-boundary",
        "systemui-consumer",
        "systemui-process",
    )
    assert "edge-runtime-thread-unknown" in forward.unresolved_edge_ids
    assert backward.node_ids[0] == "systemui-consumer"
    assert "service-operation" in backward.node_ids
    assert change.unresolved == (
        "Runtime thread/process observation is not available in the static fixture.",
    )
    assert project.suggested_probes == (
        "Capture a runtime thread/process trace before formal execution.",
    )


def test_graph_schema_and_fact_provenance_are_preserved() -> None:
    result = load_context_manifest(_FIXTURE, _project_target())

    validate_contract(result.graph.to_dict(), "context_graph")
    for fact in result.graph.facts:
        if fact.status == "unknown":
            assert fact.provenance == ()
            assert fact.rationale
        else:
            assert fact.provenance
            assert fact.source_version == "synchronous-weather-v1"
    assert {fact.source_kind for fact in result.graph.facts} >= {"declared", "derived", "unknown"}


def test_runtime_observation_keeps_observed_source_kind_distinct() -> None:
    observed = ContextFact(
        fact_id="fact-runtime-thread-observed",
        subject="SystemUiWeatherConsumer.refresh",
        predicate="runtime_thread",
        value="ui-main",
        source_kind="observed",
        provenance=(ProvenanceRef(ref="runtime/thread-trace.json"),),
        source_version="trace-001",
        confidence=0.99,
        status="known",
    )

    assert observed.source_kind == "observed"
    assert observed.status == "known"
    assert observed.provenance[0].ref == "runtime/thread-trace.json"


def test_missing_provenance_is_rejected_before_graph_construction(tmp_path: Path) -> None:
    data = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    data["facts"][0]["provenance"] = []
    path = tmp_path / "missing-provenance.json"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(DiscoveryContractError, match="known fact requires provenance"):
        load_context_manifest(path, _project_target())


def test_stale_and_contradictory_edges_remain_unresolved() -> None:
    result = load_context_manifest(_FIXTURE, _project_target())
    stale_edges = tuple(
        ContextEdge(
            edge_id=edge.edge_id,
            from_node_id=edge.from_node_id,
            to_node_id=edge.to_node_id,
            kind=edge.kind,
            semantics=edge.semantics,
            source_fact_ids=edge.source_fact_ids,
            status="stale" if edge.edge_id == "edge-api-consumer" else edge.status,
        )
        for edge in result.graph.edges
    )
    stale_graph = QualityContextGraph(
        graph_id=result.graph.graph_id,
        target_id=result.graph.target_id,
        facts=result.graph.facts,
        nodes=result.graph.nodes,
        edges=stale_edges,
    )

    stale_path = stale_graph.trace_forward("service-operation")

    assert "edge-api-consumer" in stale_path.unresolved_edge_ids
    assert "systemui-consumer" not in stale_path.node_ids

    contradictory_fact = ContextFact(
        fact_id="fact-sync-call",
        subject="SystemUiWeatherConsumer.refresh",
        predicate="calls_synchronously",
        value="unknown",
        source_kind="observed",
        provenance=(ProvenanceRef(ref="runtime/trace.json"),),
        source_version="synchronous-weather-v1",
        confidence=0.4,
        status="contradictory",
    )
    facts = tuple(
        contradictory_fact if fact.fact_id == contradictory_fact.fact_id else fact
        for fact in result.graph.facts
    )
    contradictory_graph = QualityContextGraph(
        graph_id=result.graph.graph_id,
        target_id=result.graph.target_id,
        facts=facts,
        nodes=result.graph.nodes,
        edges=result.graph.edges,
    )

    contradictory_path = contradictory_graph.trace_forward("service-operation")

    assert "edge-api-consumer" in contradictory_path.unresolved_edge_ids
    assert "systemui-consumer" not in contradictory_path.node_ids


def test_graph_rejects_dangling_node_or_edge_evidence() -> None:
    fact = ContextFact(
        fact_id="fact-component",
        subject="component",
        predicate="kind",
        value="service",
        source_kind="declared",
        provenance=(ProvenanceRef(ref="Service.kt"),),
        source_version="fixture-v1",
        confidence=1.0,
        status="known",
    )
    node = ContextNode(
        node_id="service",
        kind="component",
        label="Service",
        source_fact_ids=(fact.fact_id,),
    )
    with pytest.raises(DiscoveryContractError, match="edge references missing context node"):
        QualityContextGraph(
            graph_id="graph",
            target_id="project",
            facts=(fact,),
            nodes=(node,),
            edges=(
                ContextEdge(
                    edge_id="edge",
                    from_node_id="service",
                    to_node_id="missing",
                    kind="calls",
                    semantics="synchronous",
                    source_fact_ids=(fact.fact_id,),
                ),
            ),
        )


def test_generic_graph_logic_contains_no_fixture_outcome_or_journey_shortcut() -> None:
    source = Path("src/aiverify/discovery/context.py").read_text(encoding="utf-8")
    lowered = source.lower()

    assert "expected_verdict" not in lowered
    assert "fixture-weather" not in lowered
    assert "anr" not in lowered
    assert "journey" not in lowered
    assert "synchronous-weather" not in lowered
