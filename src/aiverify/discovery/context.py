"""Bounded context collection and path queries for the M7 graph slice.

This is intentionally a descriptor-driven collector, not a Kotlin indexer. A
caller supplies source/build/runtime facts and graph topology; this module binds
them to the target and refuses to invent missing context.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from aiverify.discovery.models import (
    ContextEdge,
    ContextFact,
    ContextNode,
    ContextPath,
    DiscoveryContractError,
    DiscoveryTarget,
    QualityContextGraph,
)


@dataclass(frozen=True)
class ContextCollectionResult:
    """Collected graph plus unresolved questions and bounded probe suggestions."""

    graph: QualityContextGraph
    unresolved: tuple[str, ...] = ()
    suggested_probes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.graph, QualityContextGraph):
            raise DiscoveryContractError("collection graph must be a QualityContextGraph")
        for field, value in (
            ("unresolved", self.unresolved),
            ("suggested_probes", self.suggested_probes),
        ):
            if not isinstance(value, tuple) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                raise DiscoveryContractError(f"{field} must contain non-empty strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph": self.graph.to_dict(),
            "unresolved": list(self.unresolved),
            "suggested_probes": list(self.suggested_probes),
        }


def collect_context(
    target: DiscoveryTarget,
    *,
    graph_id: str,
    facts: tuple[ContextFact, ...],
    nodes: tuple[ContextNode, ...],
    edges: tuple[ContextEdge, ...],
    unresolved: tuple[str, ...] = (),
    suggested_probes: tuple[str, ...] = (),
) -> ContextCollectionResult:
    """Bind supplied evidence descriptors to either target mode.

    The target is only used for identity binding. No fixture name, expected
    outcome, or hidden defect is consulted by the generic collector.
    """

    if not hasattr(target, "target_id"):
        raise DiscoveryContractError("context target must be a DiscoveryTarget")
    graph = QualityContextGraph(
        graph_id=graph_id,
        target_id=target.target_id,
        facts=facts,
        nodes=nodes,
        edges=edges,
    )
    return ContextCollectionResult(
        graph=graph,
        unresolved=unresolved,
        suggested_probes=suggested_probes,
    )


def load_context_manifest(
    path: str | Path,
    target: DiscoveryTarget,
) -> ContextCollectionResult:
    """Load a generic descriptor manifest without interpreting fixture outcomes."""

    manifest_path = Path(path)
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryContractError(f"context manifest could not be read: {error}") from error
    if not isinstance(data, Mapping):
        raise DiscoveryContractError("context manifest must be an object")
    allowed = {
        "schema_version",
        "graph_id",
        "facts",
        "nodes",
        "edges",
        "unresolved",
        "suggested_probes",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(
            "unknown context manifest field(s): " + ", ".join(unknown)
        )
    if data.get("schema_version", 1) != 1:
        raise DiscoveryContractError("unsupported context manifest schema_version")
    try:
        raw_facts = data["facts"]
        raw_nodes = data["nodes"]
        raw_edges = data["edges"]
        if not all(isinstance(value, list) for value in (raw_facts, raw_nodes, raw_edges)):
            raise DiscoveryContractError("context manifest facts/nodes/edges must be arrays")
        return collect_context(
            target,
            graph_id=data["graph_id"],
            facts=tuple(ContextFact.from_dict(item) for item in raw_facts),
            nodes=tuple(ContextNode.from_dict(item) for item in raw_nodes),
            edges=tuple(ContextEdge.from_dict(item) for item in raw_edges),
            unresolved=tuple(data.get("unresolved", [])),
            suggested_probes=tuple(data.get("suggested_probes", [])),
        )
    except KeyError as error:
        raise DiscoveryContractError(f"context manifest requires {error.args[0]}") from error


def trace_forward(graph: QualityContextGraph, start_node_id: str) -> ContextPath:
    return graph.trace_forward(start_node_id)


def trace_backward(graph: QualityContextGraph, start_node_id: str) -> ContextPath:
    return graph.trace_backward(start_node_id)
