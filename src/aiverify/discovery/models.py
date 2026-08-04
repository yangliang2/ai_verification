"""Domain contracts for evidence-bound quality-risk discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class DiscoveryContractError(ValueError):
    """Raised when a discovery domain contract is incomplete or contradictory."""


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _sha256(value: object, field: str) -> str:
    text = _required_text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise DiscoveryContractError(f"{field} must be a lowercase SHA-256 hex digest")
    return text


def _reject_unknown(data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(
            "unknown discovery contract field(s): " + ", ".join(unknown)
        )


_SOURCE_KINDS = frozenset({"declared", "derived", "observed", "historical", "unknown"})
_FACT_STATUSES = frozenset({"known", "unknown", "contradictory", "stale"})
_NODE_KINDS = frozenset(
    {"component", "api", "operation", "thread", "process", "quality_contract", "resource"}
)
_EDGE_KINDS = frozenset(
    {"calls", "provides", "depends_on", "runs_on", "runs_in", "constrained_by", "critical_path"}
)
_EDGE_SEMANTICS = frozenset({"synchronous", "asynchronous", "unknown"})


@dataclass(frozen=True)
class ProvenanceRef:
    """A source locator for one context fact."""

    ref: str
    source_sha256: str | None = None
    locator: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.ref, "provenance.ref")
        if self.source_sha256 is not None:
            _sha256(self.source_sha256, "provenance.source_sha256")
        if self.locator is not None:
            _required_text(self.locator, "provenance.locator")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"ref": self.ref}
        if self.source_sha256 is not None:
            result["source_sha256"] = self.source_sha256
        if self.locator is not None:
            result["locator"] = self.locator
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProvenanceRef":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("provenance must be an object")
        _reject_unknown(data, {"ref", "source_sha256", "locator"})
        try:
            return cls(
                ref=data["ref"],
                source_sha256=data.get("source_sha256"),
                locator=data.get("locator"),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"provenance requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class ContextFact:
    """A provenance-bound fact, inference, observation, or explicit unknown."""

    fact_id: str
    subject: str
    predicate: str
    value: Any
    source_kind: str
    provenance: tuple[ProvenanceRef, ...]
    source_version: str
    confidence: float
    status: str
    rationale: str | None = None

    def __post_init__(self) -> None:
        _required_text(self.fact_id, "fact_id")
        _required_text(self.subject, "subject")
        _required_text(self.predicate, "predicate")
        _required_text(self.source_version, "source_version")
        if self.source_kind not in _SOURCE_KINDS:
            raise DiscoveryContractError(
                "source_kind must be one of " + ", ".join(sorted(_SOURCE_KINDS))
            )
        if self.status not in _FACT_STATUSES:
            raise DiscoveryContractError(
                "status must be one of " + ", ".join(sorted(_FACT_STATUSES))
            )
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0.0 <= self.confidence <= 1.0
        ):
            raise DiscoveryContractError("confidence must be between 0 and 1")
        if not isinstance(self.provenance, tuple) or any(
            not isinstance(item, ProvenanceRef) for item in self.provenance
        ):
            raise DiscoveryContractError("provenance must contain ProvenanceRef values")
        if self.status == "unknown":
            if self.source_kind != "unknown":
                raise DiscoveryContractError(
                    "unknown fact must use source_kind unknown"
                )
            if not self.rationale or not self.rationale.strip():
                raise DiscoveryContractError("unknown fact requires rationale")
        elif not self.provenance:
            raise DiscoveryContractError(f"{self.status} fact requires provenance")
        if self.source_kind == "unknown" and self.status != "unknown":
            raise DiscoveryContractError(
                "source_kind unknown can only represent unknown status"
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "fact_id": self.fact_id,
            "subject": self.subject,
            "predicate": self.predicate,
            "value": self.value,
            "source_kind": self.source_kind,
            "provenance": [item.to_dict() for item in self.provenance],
            "source_version": self.source_version,
            "confidence": self.confidence,
            "status": self.status,
        }
        if self.rationale is not None:
            result["rationale"] = self.rationale
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextFact":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context fact must be an object")
        _reject_unknown(
            data,
            {
                "fact_id",
                "subject",
                "predicate",
                "value",
                "source_kind",
                "provenance",
                "source_version",
                "confidence",
                "status",
                "rationale",
            },
        )
        try:
            raw_value = data["value"]
            raw_provenance = data["provenance"]
            if not isinstance(raw_provenance, list):
                raise DiscoveryContractError("fact provenance must be an array")
            return cls(
                fact_id=data["fact_id"],
                subject=data["subject"],
                predicate=data["predicate"],
                value=raw_value,
                source_kind=data["source_kind"],
                provenance=tuple(ProvenanceRef.from_dict(item) for item in raw_provenance),
                source_version=data["source_version"],
                confidence=data["confidence"],
                status=data["status"],
                rationale=data.get("rationale"),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"context fact requires {error.args[0]}"
            ) from error


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    return value


@dataclass(frozen=True)
class ContextNode:
    """A graph node whose material meaning is backed by Context Facts."""

    node_id: str
    kind: str
    label: str
    source_fact_ids: tuple[str, ...]
    status: str = "known"

    def __post_init__(self) -> None:
        _required_text(self.node_id, "node_id")
        _required_text(self.label, "node label")
        if self.kind not in _NODE_KINDS:
            raise DiscoveryContractError("invalid context node kind")
        _text_tuple(self.source_fact_ids, "node source_fact_ids", allow_empty=False)
        if self.status not in _FACT_STATUSES:
            raise DiscoveryContractError("invalid context node status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "label": self.label,
            "source_fact_ids": list(self.source_fact_ids),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextNode":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context node must be an object")
        _reject_unknown(data, {"node_id", "kind", "label", "source_fact_ids", "status"})
        try:
            raw_facts = data["source_fact_ids"]
            if not isinstance(raw_facts, list):
                raise DiscoveryContractError("node source_fact_ids must be an array")
            return cls(
                node_id=data["node_id"],
                kind=data["kind"],
                label=data["label"],
                source_fact_ids=tuple(raw_facts),
                status=data.get("status", "known"),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"context node requires {error.args[0]}") from error


@dataclass(frozen=True)
class ContextEdge:
    """A directed dependency edge with explicit temporal semantics and evidence."""

    edge_id: str
    from_node_id: str
    to_node_id: str
    kind: str
    semantics: str
    source_fact_ids: tuple[str, ...]
    status: str = "known"

    def __post_init__(self) -> None:
        for field in ("edge_id", "from_node_id", "to_node_id"):
            _required_text(getattr(self, field), field)
        if self.kind not in _EDGE_KINDS:
            raise DiscoveryContractError("invalid context edge kind")
        if self.semantics not in _EDGE_SEMANTICS:
            raise DiscoveryContractError("invalid context edge semantics")
        _text_tuple(self.source_fact_ids, "edge source_fact_ids", allow_empty=False)
        if self.status not in _FACT_STATUSES:
            raise DiscoveryContractError("invalid context edge status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "kind": self.kind,
            "semantics": self.semantics,
            "source_fact_ids": list(self.source_fact_ids),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextEdge":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context edge must be an object")
        _reject_unknown(
            data,
            {
                "edge_id",
                "from_node_id",
                "to_node_id",
                "kind",
                "semantics",
                "source_fact_ids",
                "status",
            },
        )
        try:
            raw_facts = data["source_fact_ids"]
            if not isinstance(raw_facts, list):
                raise DiscoveryContractError("edge source_fact_ids must be an array")
            return cls(
                edge_id=data["edge_id"],
                from_node_id=data["from_node_id"],
                to_node_id=data["to_node_id"],
                kind=data["kind"],
                semantics=data["semantics"],
                source_fact_ids=tuple(raw_facts),
                status=data.get("status", "known"),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"context edge requires {error.args[0]}") from error


@dataclass(frozen=True)
class ContextPath:
    """A deterministic graph traversal result with unresolved evidence retained."""

    direction: str
    start_node_id: str
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    unresolved_edge_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.direction not in {"forward", "backward"}:
            raise DiscoveryContractError("path direction must be forward or backward")
        _required_text(self.start_node_id, "start_node_id")
        _text_tuple(self.node_ids, "path node_ids", allow_empty=False)
        _text_tuple(self.edge_ids, "path edge_ids")
        _text_tuple(self.unresolved_edge_ids, "path unresolved_edge_ids")

    def to_dict(self) -> dict[str, Any]:
        return {
            "direction": self.direction,
            "start_node_id": self.start_node_id,
            "node_ids": list(self.node_ids),
            "edge_ids": list(self.edge_ids),
            "unresolved_edge_ids": list(self.unresolved_edge_ids),
        }


@dataclass(frozen=True)
class QualityContextGraph:
    """An immutable snapshot of context facts used by discovery reasoning."""

    graph_id: str
    target_id: str
    facts: tuple[ContextFact, ...]
    schema_version: int = 1
    nodes: tuple[ContextNode, ...] = ()
    edges: tuple[ContextEdge, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.graph_id, "graph_id")
        _required_text(self.target_id, "target_id")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != 1
        ):
            raise DiscoveryContractError("unsupported context graph schema_version")
        if not isinstance(self.facts, tuple):
            raise DiscoveryContractError("facts must be a tuple")
        if any(not isinstance(fact, ContextFact) for fact in self.facts):
            raise DiscoveryContractError("facts must contain ContextFact values")
        fact_ids = [fact.fact_id for fact in self.facts]
        if len(set(fact_ids)) != len(fact_ids):
            raise DiscoveryContractError("fact ids must be unique")
        if not isinstance(self.nodes, tuple) or any(
            not isinstance(node, ContextNode) for node in self.nodes
        ):
            raise DiscoveryContractError("nodes must contain ContextNode values")
        if not isinstance(self.edges, tuple) or any(
            not isinstance(edge, ContextEdge) for edge in self.edges
        ):
            raise DiscoveryContractError("edges must contain ContextEdge values")
        _text_tuple(tuple(node.node_id for node in self.nodes), "node ids")
        _text_tuple(tuple(edge.edge_id for edge in self.edges), "edge ids")
        if len({node.node_id for node in self.nodes}) != len(self.nodes):
            raise DiscoveryContractError("node ids must be unique")
        if len({edge.edge_id for edge in self.edges}) != len(self.edges):
            raise DiscoveryContractError("edge ids must be unique")
        fact_ids_set = set(fact_ids)
        node_ids = {node.node_id for node in self.nodes}
        if any(
            not set(node.source_fact_ids).issubset(fact_ids_set) for node in self.nodes
        ):
            raise DiscoveryContractError("node references missing context fact")
        if any(
            edge.from_node_id not in node_ids or edge.to_node_id not in node_ids
            for edge in self.edges
        ):
            raise DiscoveryContractError("edge references missing context node")
        if any(
            not set(edge.source_fact_ids).issubset(fact_ids_set) for edge in self.edges
        ):
            raise DiscoveryContractError("edge references missing context fact")

    def fact(self, fact_id: str) -> ContextFact:
        for fact in self.facts:
            if fact.fact_id == fact_id:
                return fact
        raise KeyError(fact_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "graph_id": self.graph_id,
            "target_id": self.target_id,
            "facts": [fact.to_dict() for fact in self.facts],
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "QualityContextGraph":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context graph must be an object")
        _reject_unknown(
            data,
            {"schema_version", "graph_id", "target_id", "facts", "nodes", "edges"},
        )
        try:
            raw_facts = data["facts"]
            if not isinstance(raw_facts, list):
                raise DiscoveryContractError("context graph facts must be an array")
            return cls(
                graph_id=data["graph_id"],
                target_id=data["target_id"],
                facts=tuple(ContextFact.from_dict(item) for item in raw_facts),
                schema_version=data.get("schema_version", 1),
                nodes=tuple(
                    ContextNode.from_dict(item)
                    for item in data.get("nodes", [])
                ),
                edges=tuple(
                    ContextEdge.from_dict(item)
                    for item in data.get("edges", [])
                ),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"context graph requires {error.args[0]}"
            ) from error

    def trace_forward(self, start_node_id: str) -> ContextPath:
        return self._trace(start_node_id, "forward")

    def trace_backward(self, start_node_id: str) -> ContextPath:
        return self._trace(start_node_id, "backward")

    def _trace(self, start_node_id: str, direction: str) -> ContextPath:
        node_ids = {node.node_id for node in self.nodes}
        if start_node_id not in node_ids:
            raise KeyError(start_node_id)
        facts = {fact.fact_id: fact for fact in self.facts}
        nodes_by_id = {node.node_id: node for node in self.nodes}
        frontier = [start_node_id]
        visited = {start_node_id}
        ordered_nodes = [start_node_id]
        ordered_edges: list[str] = []
        unresolved: list[str] = []
        while frontier:
            current = frontier.pop(0)
            candidates = [
                edge
                for edge in self.edges
                if (
                    edge.from_node_id == current
                    if direction == "forward"
                    else edge.to_node_id == current
                )
            ]
            for edge in candidates:
                next_node = (
                    edge.to_node_id if direction == "forward" else edge.from_node_id
                )
                if (
                    nodes_by_id[current].status != "known"
                    or nodes_by_id[next_node].status != "known"
                    or edge.status != "known"
                    or any(
                        facts[fact_id].status != "known"
                        for fact_id in edge.source_fact_ids
                    )
                ):
                    unresolved.append(edge.edge_id)
                    continue
                ordered_edges.append(edge.edge_id)
                if next_node not in visited:
                    visited.add(next_node)
                    ordered_nodes.append(next_node)
                    frontier.append(next_node)
        return ContextPath(
            direction=direction,
            start_node_id=start_node_id,
            node_ids=tuple(ordered_nodes),
            edge_ids=tuple(ordered_edges),
            unresolved_edge_ids=tuple(unresolved),
        )


@dataclass(frozen=True)
class ChangeTarget:
    """A discovery target whose seed is a checksum-bound code change."""

    target_id: str
    source_origin: str
    source_commit: str
    worktree: str
    diff_ref: str
    diff_sha256: str
    spec_ref: str | None = None
    schema_version: int = 1

    @property
    def kind(self) -> str:
        return "change"

    def __post_init__(self) -> None:
        _required_text(self.target_id, "target_id")
        _required_text(self.source_origin, "source_origin")
        _required_text(self.source_commit, "source_commit")
        _required_text(self.worktree, "worktree")
        _required_text(self.diff_ref, "diff_ref")
        _sha256(self.diff_sha256, "diff_sha256")
        if self.spec_ref is not None:
            _required_text(self.spec_ref, "spec_ref")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != 1
        ):
            raise DiscoveryContractError("unsupported change target schema_version")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "kind": self.kind,
            "target_id": self.target_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "worktree": self.worktree,
            "diff_ref": self.diff_ref,
            "diff_sha256": self.diff_sha256,
            "schema_version": self.schema_version,
        }
        if self.spec_ref is not None:
            result["spec_ref"] = self.spec_ref
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ChangeTarget":
        parsed = target_from_dict(data)
        if not isinstance(parsed, cls):
            raise DiscoveryContractError("expected a change target")
        return parsed


@dataclass(frozen=True)
class ProjectTarget:
    """A discovery target whose seed is a complete project, not a diff."""

    target_id: str
    source_origin: str
    source_commit: str
    worktree: str
    scope: tuple[str, ...]
    discovery_budget: int
    schema_version: int = 1

    @property
    def kind(self) -> str:
        return "project"

    def __post_init__(self) -> None:
        _required_text(self.target_id, "target_id")
        _required_text(self.source_origin, "source_origin")
        _required_text(self.source_commit, "source_commit")
        _required_text(self.worktree, "worktree")
        if not isinstance(self.scope, tuple):
            raise DiscoveryContractError("project scope must be a tuple")
        if not self.scope or any(
            not isinstance(item, str) or not item.strip() for item in self.scope
        ):
            raise DiscoveryContractError("project scope must contain non-empty strings")
        if (
            not isinstance(self.discovery_budget, int)
            or isinstance(self.discovery_budget, bool)
            or self.discovery_budget <= 0
        ):
            raise DiscoveryContractError("discovery_budget must be positive")
        if (
            not isinstance(self.schema_version, int)
            or isinstance(self.schema_version, bool)
            or self.schema_version != 1
        ):
            raise DiscoveryContractError("unsupported project target schema_version")

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target_id": self.target_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "worktree": self.worktree,
            "scope": list(self.scope),
            "discovery_budget": self.discovery_budget,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ProjectTarget":
        parsed = target_from_dict(data)
        if not isinstance(parsed, cls):
            raise DiscoveryContractError("expected a project target")
        return parsed


DiscoveryTarget = ChangeTarget | ProjectTarget


def target_from_dict(data: Mapping[str, Any]) -> DiscoveryTarget:
    """Parse and strictly validate one change/project target."""
    if not isinstance(data, Mapping):
        raise DiscoveryContractError("discovery target must be an object")
    kind = data.get("kind")
    if kind == "change":
        _reject_unknown(
            data,
            {
                "kind",
                "target_id",
                "source_origin",
                "source_commit",
                "worktree",
                "diff_ref",
                "diff_sha256",
                "spec_ref",
                "schema_version",
            },
        )
        try:
            return ChangeTarget(
                target_id=data["target_id"],
                source_origin=data["source_origin"],
                source_commit=data["source_commit"],
                worktree=data["worktree"],
                diff_ref=data["diff_ref"],
                diff_sha256=data["diff_sha256"],
                spec_ref=data.get("spec_ref"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"change target requires {error.args[0]}"
            ) from error
    if kind == "project":
        if "diff_ref" in data or "diff_sha256" in data or "spec_ref" in data:
            raise DiscoveryContractError("project target must not include diff")
        _reject_unknown(
            data,
            {
                "kind",
                "target_id",
                "source_origin",
                "source_commit",
                "worktree",
                "scope",
                "discovery_budget",
                "schema_version",
            },
        )
        try:
            raw_scope = data["scope"]
            if not isinstance(raw_scope, list):
                raise DiscoveryContractError("project scope must be an array")
            return ProjectTarget(
                target_id=data["target_id"],
                source_origin=data["source_origin"],
                source_commit=data["source_commit"],
                worktree=data["worktree"],
                scope=tuple(raw_scope),
                discovery_budget=data["discovery_budget"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"project target requires {error.args[0]}"
            ) from error
    raise DiscoveryContractError("target kind must be 'change' or 'project'")
