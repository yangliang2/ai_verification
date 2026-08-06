"""Bounded, source-backed Context Acquisition for ProjectTarget discovery.

The acquisition entry point is deliberately read-only.  It verifies the target
identity and clean worktree with Git, inspects only tracked files in the target
scope, and turns syntax-level evidence into immutable context facts.  It is a
bounded source adapter, not a compiler, an LLM planner, or an execution
scanner.  In particular, suggestions are retained in the receipt and are
never promoted to facts without independent source evidence.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from aiverify.discovery.models import (
    ContextEdge,
    ContextFact,
    ContextNode,
    DiscoveryContractError,
    ProjectTarget,
    ProvenanceRef,
    QualityContextGraph,
    target_from_dict,
)


_DEFAULT_EVIDENCE = (
    "manifest",
    "build",
    "symbols_calls",
    "persistence_state",
    "lifecycle_ownership",
    "quality_version",
)
_ADAPTER_STATUS = frozenset({"complete", "partial", "unsupported", "budget-exhausted"})
_RESULT_STATUS = frozenset({"complete", "partial", "rejected"})
_STALE_REF_RE = re.compile(
    r"\b(?:source[_ -]?commit|commit|revision|source[_ -]?revision)\b"
    r"\s*(?:=|:|\(|\s)\s*[\"']?([0-9a-f]{40})\b",
    re.IGNORECASE,
)
_ANDROID_NAME_RE = re.compile(r"\bandroid:name\s*=\s*[\"']([^\"']+)")
_APPLICATION_ID_RE = re.compile(
    r"\bapplicationId\s*(?:=|\s)\s*[\"']([^\"']+)[\"']"
)
_VERSION_RE = re.compile(
    r"\b(?:versionName|versionCode|schemaVersion|schema_version|compileSdk|"
    r"minSdk|targetSdk|version)\s*(?:=|:|\(|\s)\s*[\"']?([0-9]+(?:\.[0-9]+)*)",
    re.IGNORECASE,
)
_CLASS_RE = re.compile(r"\b(class|interface|object|enum\s+class)\s+([A-Za-z_]\w*)")
_FUNCTION_RE = re.compile(
    r"\b(?:(?:public|private|protected|internal|override|suspend|static|final)\s+)*"
    r"(?:fun\s+|(?:[A-Za-z_$][\w$<>.?\[\]]*\s+)+)([A-Za-z_]\w*)\s*\([^)]*\)"
)
_CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\.\s*([A-Za-z_]\w*)\s*\(")
_STALE_STATUS_PRIORITY = {"known": 0, "inferred": 1, "unknown": 2, "stale": 3, "contradictory": 4}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    return value


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _sha256_text(value: object, field: str) -> str:
    value = _required_text(value, field)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise DiscoveryContractError(f"{field} must be a lowercase SHA-256 hex digest")
    return value


def _schema_version(value: object, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value != 1:
        raise DiscoveryContractError(f"unsupported {field} schema_version")


def _reject_unknown(data: Mapping[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(
            "unknown context acquisition field(s): " + ", ".join(unknown)
        )


def _canonical_origin(value: str) -> str:
    return value.strip().rstrip("/").removesuffix(".git")


def _git(worktree: Path, *arguments: str) -> bytes:
    try:
        completed = subprocess.run(
            ["git", *arguments],
            cwd=worktree,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        detail = ""
        if isinstance(error, subprocess.CalledProcessError):
            detail = error.stderr.decode("utf-8", errors="replace").strip()
        raise DiscoveryContractError(
            f"source identity command failed: git {' '.join(arguments)}"
            + (f": {detail}" if detail else "")
        ) from error
    return completed.stdout


def _git_text(worktree: Path, *arguments: str) -> str:
    return _git(worktree, *arguments).decode("utf-8", errors="strict").strip()


def _verify_project_identity(target: ProjectTarget) -> tuple[Path, str, str]:
    worktree = Path(target.worktree).expanduser()
    if not worktree.is_dir():
        raise DiscoveryContractError(f"project worktree does not exist: {target.worktree}")
    requested_root = worktree.resolve()
    try:
        repository_root = Path(_git_text(worktree, "rev-parse", "--show-toplevel")).resolve()
    except DiscoveryContractError:
        raise
    if repository_root != requested_root:
        raise DiscoveryContractError(
            "project worktree must be the repository root; refusing a subdirectory"
        )
    head = _git_text(worktree, "rev-parse", "HEAD")
    if target.source_commit != head:
        raise DiscoveryContractError(
            f"project source commit mismatch: target={target.source_commit} actual={head}"
        )
    try:
        origin = _git_text(worktree, "remote", "get-url", "origin")
    except DiscoveryContractError as error:
        raise DiscoveryContractError("project source origin could not be verified") from error
    if _canonical_origin(target.source_origin) != _canonical_origin(origin):
        raise DiscoveryContractError(
            f"project source origin mismatch: target={target.source_origin} actual={origin}"
        )
    dirty = _git_text(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    if dirty:
        raise DiscoveryContractError(
            "project worktree is not clean; acquisition refuses diffs and untracked files"
        )
    tree_listing = _git(worktree, "ls-tree", "-r", "--full-tree", "-z", "HEAD")
    tree_sha256 = _sha256_bytes(tree_listing)
    return repository_root, head, tree_sha256


def _path_in_scope(path: str, scopes: tuple[str, ...]) -> bool:
    normalized = path.strip("/")
    for raw_scope in scopes:
        scope = raw_scope.replace("\\", "/").strip("/")
        if scope in {"", ".", "*", "**"}:
            return True
        if normalized == scope or normalized.startswith(scope.rstrip("/") + "/"):
            return True
        if fnmatch.fnmatchcase(normalized, scope):
            return True
        try:
            if Path(normalized).match(scope):
                return True
        except ValueError:
            continue
        wildcard = min(
            (index for index, char in enumerate(scope) if char in "*?["),
            default=len(scope),
        )
        prefix = scope[:wildcard].rstrip("/")
        if prefix and (normalized == prefix or normalized.startswith(prefix + "/")):
            return True
    return False


@dataclass(frozen=True)
class _FileEvidence:
    path: str
    raw: bytes
    text: str
    sha256: str


@dataclass(frozen=True)
class AdapterReceipt:
    """Deterministic receipt for one source evidence adapter."""

    adapter_id: str
    status: str
    inspected_files: tuple[str, ...]
    facts_emitted: int
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _required_text(self.adapter_id, "adapter_id")
        if self.status not in _ADAPTER_STATUS:
            raise DiscoveryContractError("invalid context adapter status")
        _text_tuple(self.inspected_files, "adapter inspected_files")
        if (
            not isinstance(self.facts_emitted, int)
            or isinstance(self.facts_emitted, bool)
            or self.facts_emitted < 0
        ):
            raise DiscoveryContractError("adapter facts_emitted must be non-negative")
        _text_tuple(self.unresolved, "adapter unresolved")

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "status": self.status,
            "inspected_files": list(self.inspected_files),
            "facts_emitted": self.facts_emitted,
            "unresolved": list(self.unresolved),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AdapterReceipt":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("adapter receipt must be an object")
        _reject_unknown(data, {"adapter_id", "status", "inspected_files", "facts_emitted", "unresolved"})
        try:
            inspected = data["inspected_files"]
            unresolved = data.get("unresolved", [])
            if not isinstance(inspected, list) or not isinstance(unresolved, list):
                raise DiscoveryContractError("adapter file and unresolved fields must be arrays")
            return cls(
                adapter_id=data["adapter_id"],
                status=data["status"],
                inspected_files=tuple(inspected),
                facts_emitted=data["facts_emitted"],
                unresolved=tuple(unresolved),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"adapter receipt requires {error.args[0]}") from error


@dataclass(frozen=True)
class ContextAcquisitionRequest:
    """Serializable bounded request supplied to Context Acquisition."""

    target: ProjectTarget
    requested_evidence: tuple[str, ...] = _DEFAULT_EVIDENCE
    suggestions: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.target, ProjectTarget):
            raise DiscoveryContractError("acquisition request target must be a ProjectTarget")
        object.__setattr__(self, "requested_evidence", _requested_tuple(self.requested_evidence))
        _text_tuple(self.suggestions, "request suggestions")
        _schema_version(self.schema_version, "context acquisition request")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "requested_evidence": list(self.requested_evidence),
            "suggestions": list(self.suggestions),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextAcquisitionRequest":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context acquisition request must be an object")
        _reject_unknown(data, {"schema_version", "target", "requested_evidence", "suggestions"})
        try:
            raw_evidence = data.get("requested_evidence", list(_DEFAULT_EVIDENCE))
            raw_suggestions = data.get("suggestions", [])
            if not isinstance(raw_evidence, list) or not isinstance(raw_suggestions, list):
                raise DiscoveryContractError("request evidence and suggestions must be arrays")
            target = target_from_dict(data["target"])
            if not isinstance(target, ProjectTarget):
                raise DiscoveryContractError("acquisition request target must be a project target")
            return cls(
                schema_version=data.get("schema_version", 1),
                target=target,
                requested_evidence=tuple(raw_evidence),
                suggestions=tuple(raw_suggestions),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"acquisition request requires {error.args[0]}") from error


@dataclass(frozen=True)
class ContextAcquisitionReceipt:
    """Immutable identity, scope, budget, and coverage receipt."""

    target_id: str
    source_origin: str
    source_commit: str
    source_tree_sha256: str
    requested_evidence: tuple[str, ...]
    inspected_scope: tuple[str, ...]
    skipped_scope: tuple[str, ...]
    discovery_budget: int
    budget_used: int
    graph_sha256: str
    adapters: tuple[AdapterReceipt, ...]
    unresolved: tuple[str, ...]
    suggested_probes: tuple[str, ...]
    coverage_frontier: tuple[str, ...]
    no_diff: bool
    status: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        _required_text(self.target_id, "receipt target_id")
        _required_text(self.source_origin, "receipt source_origin")
        _required_text(self.source_commit, "receipt source_commit")
        _sha256_text(self.source_tree_sha256, "receipt source_tree_sha256")
        _text_tuple(self.requested_evidence, "requested_evidence", allow_empty=False)
        _text_tuple(self.inspected_scope, "inspected_scope")
        _text_tuple(self.skipped_scope, "skipped_scope")
        for field, value in (
            ("discovery_budget", self.discovery_budget),
            ("budget_used", self.budget_used),
        ):
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise DiscoveryContractError(f"{field} must be a non-negative integer")
        if self.discovery_budget == 0:
            raise DiscoveryContractError("discovery_budget must be positive")
        if self.budget_used > self.discovery_budget:
            raise DiscoveryContractError("budget_used exceeds discovery_budget")
        _sha256_text(self.graph_sha256, "receipt graph_sha256")
        if not isinstance(self.adapters, tuple) or any(
            not isinstance(item, AdapterReceipt) for item in self.adapters
        ):
            raise DiscoveryContractError("adapters must contain AdapterReceipt values")
        _text_tuple(self.unresolved, "receipt unresolved")
        _text_tuple(self.suggested_probes, "receipt suggested_probes")
        _text_tuple(self.coverage_frontier, "receipt coverage_frontier")
        if self.no_diff is not True:
            raise DiscoveryContractError("receipt no_diff must be true")
        if self.status not in _RESULT_STATUS:
            raise DiscoveryContractError("invalid context acquisition status")
        _schema_version(self.schema_version, "context acquisition receipt")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target_id": self.target_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "source_tree_sha256": self.source_tree_sha256,
            "requested_evidence": list(self.requested_evidence),
            "inspected_scope": list(self.inspected_scope),
            "skipped_scope": list(self.skipped_scope),
            "discovery_budget": self.discovery_budget,
            "budget_used": self.budget_used,
            "graph_sha256": self.graph_sha256,
            "adapters": [item.to_dict() for item in self.adapters],
            "unresolved": list(self.unresolved),
            "suggested_probes": list(self.suggested_probes),
            "coverage_frontier": list(self.coverage_frontier),
            "no_diff": self.no_diff,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextAcquisitionReceipt":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context acquisition receipt must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "target_id",
                "source_origin",
                "source_commit",
                "source_tree_sha256",
                "requested_evidence",
                "inspected_scope",
                "skipped_scope",
                "discovery_budget",
                "budget_used",
                "graph_sha256",
                "adapters",
                "unresolved",
                "suggested_probes",
                "coverage_frontier",
                "no_diff",
                "status",
            },
        )
        try:
            arrays = {
                key: data[key]
                for key in (
                    "requested_evidence",
                    "inspected_scope",
                    "skipped_scope",
                    "unresolved",
                    "suggested_probes",
                    "coverage_frontier",
                )
            }
            if any(not isinstance(value, list) for value in arrays.values()):
                raise DiscoveryContractError("receipt list fields must be arrays")
            raw_adapters = data["adapters"]
            if not isinstance(raw_adapters, list):
                raise DiscoveryContractError("receipt adapters must be an array")
            return cls(
                schema_version=data.get("schema_version", 1),
                target_id=data["target_id"],
                source_origin=data["source_origin"],
                source_commit=data["source_commit"],
                source_tree_sha256=data["source_tree_sha256"],
                requested_evidence=tuple(arrays["requested_evidence"]),
                inspected_scope=tuple(arrays["inspected_scope"]),
                skipped_scope=tuple(arrays["skipped_scope"]),
                discovery_budget=data["discovery_budget"],
                budget_used=data["budget_used"],
                graph_sha256=data["graph_sha256"],
                adapters=tuple(AdapterReceipt.from_dict(item) for item in raw_adapters),
                unresolved=tuple(arrays["unresolved"]),
                suggested_probes=tuple(arrays["suggested_probes"]),
                coverage_frontier=tuple(arrays["coverage_frontier"]),
                no_diff=data["no_diff"],
                status=data["status"],
            )
        except KeyError as error:
            raise DiscoveryContractError(f"receipt requires {error.args[0]}") from error


@dataclass(frozen=True)
class ContextAcquisitionResult:
    """Graph plus the complete bounded acquisition receipt."""

    target: ProjectTarget
    graph: QualityContextGraph
    receipt: ContextAcquisitionReceipt
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.target, ProjectTarget):
            raise DiscoveryContractError("acquisition target must be a ProjectTarget")
        if not isinstance(self.graph, QualityContextGraph):
            raise DiscoveryContractError("acquisition graph must be a QualityContextGraph")
        if not isinstance(self.receipt, ContextAcquisitionReceipt):
            raise DiscoveryContractError("acquisition receipt must be a ContextAcquisitionReceipt")
        if self.graph.target_id != self.target.target_id:
            raise DiscoveryContractError("acquisition graph target does not match target")
        if self.receipt.target_id != self.target.target_id:
            raise DiscoveryContractError("acquisition receipt target does not match target")
        if self.graph.source_origin != self.target.source_origin:
            raise DiscoveryContractError("acquisition graph origin does not match target")
        if self.graph.source_commit != self.target.source_commit:
            raise DiscoveryContractError("acquisition graph commit does not match target")
        if self.receipt.source_origin != self.target.source_origin:
            raise DiscoveryContractError("acquisition receipt origin does not match target")
        if self.receipt.source_commit != self.target.source_commit:
            raise DiscoveryContractError("acquisition receipt commit does not match target")
        if self.graph.source_origin != self.receipt.source_origin:
            raise DiscoveryContractError("acquisition graph origin does not match receipt")
        if self.graph.source_commit != self.receipt.source_commit:
            raise DiscoveryContractError("acquisition graph commit does not match receipt")
        if self.graph.source_tree_sha256 != self.receipt.source_tree_sha256:
            raise DiscoveryContractError("acquisition graph tree identity does not match receipt")
        if _sha256_json(self.graph.to_dict()) != self.receipt.graph_sha256:
            raise DiscoveryContractError("acquisition graph checksum does not match receipt")
        _schema_version(self.schema_version, "context acquisition result")

    @property
    def unresolved(self) -> tuple[str, ...]:
        return self.receipt.unresolved

    @property
    def suggested_probes(self) -> tuple[str, ...]:
        return self.receipt.suggested_probes

    @property
    def coverage_frontier(self) -> tuple[str, ...]:
        return self.receipt.coverage_frontier

    @property
    def status(self) -> str:
        return self.receipt.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "target": self.target.to_dict(),
            "graph": self.graph.to_dict(),
            "receipt": self.receipt.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContextAcquisitionResult":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("context acquisition result must be an object")
        _reject_unknown(data, {"schema_version", "target", "graph", "receipt"})
        try:
            target = target_from_dict(data["target"])
            if not isinstance(target, ProjectTarget):
                raise DiscoveryContractError("acquisition result target must be a project target")
            return cls(
                schema_version=data.get("schema_version", 1),
                target=target,
                graph=QualityContextGraph.from_dict(data["graph"]),
                receipt=ContextAcquisitionReceipt.from_dict(data["receipt"]),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"acquisition result requires {error.args[0]}") from error


class _FactCollector:
    def __init__(self, target: ProjectTarget, files: Mapping[str, _FileEvidence]) -> None:
        self.target = target
        self.files = files
        self.facts: dict[str, ContextFact] = {}
        self.by_key: dict[tuple[str, str], list[str]] = {}
        self.nodes: dict[tuple[str, str], set[str]] = {}
        self.edges: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
        self.unresolved: list[str] = []

    def _fact_id(self, subject: str, predicate: str, value: Any, ref: str, line: int) -> str:
        token = _canonical_json(
            {"subject": subject, "predicate": predicate, "value": value, "ref": ref, "line": line}
        )
        return "fact-" + _sha256_bytes(token.encode("utf-8"))[:20]

    def add(
        self,
        *,
        subject: str,
        predicate: str,
        value: Any,
        path: str,
        line: int,
        source_kind: str = "observed",
        confidence: float = 1.0,
        status: str = "known",
        rationale: str | None = None,
    ) -> str:
        evidence = self.files[path]
        fact_id = self._fact_id(subject, predicate, value, path, line)
        fact = ContextFact(
            fact_id=fact_id,
            subject=subject,
            predicate=predicate,
            value=value,
            source_kind=source_kind,
            provenance=(
                ProvenanceRef(
                    ref=path,
                    source_sha256=evidence.sha256,
                    locator=f"line:{max(line, 1)}",
                ),
            ),
            source_version=evidence.sha256,
            confidence=confidence,
            status=status,
            rationale=rationale,
        )
        if fact_id not in self.facts:
            self.facts[fact_id] = fact
            self.by_key.setdefault((subject, predicate), []).append(fact_id)
        return fact_id

    def add_unknown(self, *, subject: str, predicate: str, rationale: str) -> str:
        key = (subject, predicate)
        existing = self.by_key.get(key, [])
        for fact_id in existing:
            fact = self.facts[fact_id]
            if fact.status == "unknown":
                return fact_id
        value = None
        token = _canonical_json(
            {"subject": subject, "predicate": predicate, "value": value, "source": self.target.source_commit}
        )
        fact_id = "fact-" + _sha256_bytes(token.encode("utf-8"))[:20]
        self.facts[fact_id] = ContextFact(
            fact_id=fact_id,
            subject=subject,
            predicate=predicate,
            value=None,
            source_kind="unknown",
            provenance=(),
            source_version=self.target.source_commit,
            confidence=0.0,
            status="unknown",
            rationale=rationale,
        )
        self.by_key.setdefault(key, []).append(fact_id)
        return fact_id

    def unresolved_once(self, message: str) -> None:
        if message not in self.unresolved:
            self.unresolved.append(message)

    def add_node(self, kind: str, label: str, fact_id: str) -> str:
        key = (kind, label)
        self.nodes.setdefault(key, set()).add(fact_id)
        return _node_id(kind, label)

    def add_edge(
        self,
        from_node: tuple[str, str],
        to_node: tuple[str, str],
        kind: str,
        semantics: str,
        fact_ids: Iterable[str],
    ) -> None:
        source_fact_ids = tuple(sorted(set(fact_ids)))
        if not source_fact_ids:
            return
        self.edges.add(
            (
                _node_id(*from_node),
                _node_id(*to_node),
                kind,
                semantics,
                source_fact_ids,
            )
        )

    def finalize(self) -> tuple[tuple[ContextFact, ...], tuple[ContextNode, ...], tuple[ContextEdge, ...]]:
        for key, fact_ids in self.by_key.items():
            values = {_canonical_json(self.facts[fact_id].value) for fact_id in fact_ids}
            if len(values) > 1:
                self.unresolved_once(
                    f"contradictory evidence for {key[0]} predicate {key[1]}"
                )
                for fact_id in fact_ids:
                    fact = self.facts[fact_id]
                    if fact.status in {"known", "inferred"}:
                        self.facts[fact_id] = replace(fact, status="contradictory")
        facts = tuple(self.facts[fact_id] for fact_id in sorted(self.facts))
        fact_by_id = {fact.fact_id: fact for fact in facts}
        nodes: list[ContextNode] = []
        for (kind, label), fact_ids in sorted(self.nodes.items()):
            ordered_ids = tuple(sorted(fact_ids))
            statuses = [fact_by_id[fact_id].status for fact_id in ordered_ids]
            status = max(statuses, key=lambda value: _STALE_STATUS_PRIORITY[value])
            nodes.append(
                ContextNode(
                    node_id=_node_id(kind, label),
                    kind=kind,
                    label=label,
                    source_fact_ids=ordered_ids,
                    status=status,
                )
            )
        edges = tuple(
            ContextEdge(
                edge_id="edge-" + _sha256_json(
                    {
                        "from": from_node,
                        "to": to_node,
                        "kind": kind,
                        "semantics": semantics,
                        "facts": fact_ids,
                    }
                )[:20],
                from_node_id=from_node,
                to_node_id=to_node,
                kind=kind,
                semantics=semantics,
                source_fact_ids=fact_ids,
                status=max(
                    (fact_by_id[fact_id].status for fact_id in fact_ids),
                    key=lambda value: _STALE_STATUS_PRIORITY[value],
                ),
            )
            for from_node, to_node, kind, semantics, fact_ids in sorted(self.edges)
        )
        return facts, tuple(nodes), edges


def _node_id(kind: str, label: str) -> str:
    return f"{kind}-" + _sha256_bytes(label.encode("utf-8"))[:16]


def _line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _lines(text: str) -> Iterable[tuple[int, str]]:
    yield from enumerate(text.splitlines(), start=1)


def _source_files(files: Mapping[str, _FileEvidence]) -> tuple[_FileEvidence, ...]:
    return tuple(
        evidence
        for path, evidence in sorted(files.items())
        if Path(path).suffix.lower() in {".kt", ".kts", ".java", ".groovy", ".gradle"}
    )


def _manifest_files(files: Mapping[str, _FileEvidence]) -> tuple[_FileEvidence, ...]:
    return tuple(
        evidence
        for path, evidence in sorted(files.items())
        if Path(path).name.lower() == "androidmanifest.xml"
    )


def _build_files(files: Mapping[str, _FileEvidence]) -> tuple[_FileEvidence, ...]:
    recognized = {
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
        "settings.gradle.kts",
        "gradle.properties",
        "libs.versions.toml",
        "pom.xml",
        "build.xml",
        "version.properties",
    }
    return tuple(
        evidence
        for path, evidence in sorted(files.items())
        if Path(path).name.lower() in recognized
        or Path(path).name.lower().startswith("build.gradle.")
    )


def _add_stale_references(collector: _FactCollector, evidence: _FileEvidence) -> int:
    emitted = 0
    for match in _STALE_REF_RE.finditer(evidence.text):
        referenced = match.group(1).lower()
        if referenced == collector.target.source_commit.lower():
            continue
        line = _line_number(evidence.text, match.start())
        collector.add(
            subject=evidence.path,
            predicate="source_revision",
            value=referenced,
            path=evidence.path,
            line=line,
            source_kind="declared",
            confidence=1.0,
            status="stale",
            rationale="The source descriptor references a revision different from ProjectTarget.",
        )
        collector.unresolved_once(
            f"stale source revision reference in {evidence.path}:line:{line}"
        )
        emitted += 1
    return emitted


def _run_manifest_adapter(collector: _FactCollector, files: Mapping[str, _FileEvidence]) -> tuple[tuple[str, ...], list[str]]:
    manifest_files = _manifest_files(files)
    unresolved: list[str] = []
    emitted = 0
    for evidence in manifest_files:
        emitted += _add_stale_references(collector, evidence)
        package_match = re.search(r"<manifest\b[^>]*\bpackage\s*=\s*[\"']([^\"']+)", evidence.text, re.S)
        if package_match:
            line = _line_number(evidence.text, package_match.start())
            fact_id = collector.add(
                subject="project",
                predicate="manifest_package",
                value=package_match.group(1),
                path=evidence.path,
                line=line,
                source_kind="declared",
            )
            collector.add_node("component", package_match.group(1), fact_id)
            emitted += 1
        else:
            unresolved.append(f"manifest package is absent or unreadable in {evidence.path}")
        for match in re.finditer(
            r"<(activity|service|receiver|provider)\b([^>]*)>", evidence.text, re.S | re.I
        ):
            kind = match.group(1).lower()
            attrs = match.group(2)
            name_match = _ANDROID_NAME_RE.search(attrs)
            if not name_match:
                line = _line_number(evidence.text, match.start())
                unresolved.append(f"manifest component name is ambiguous in {evidence.path}:line:{line}")
                continue
            name = name_match.group(1)
            line = _line_number(evidence.text, match.start())
            fact_id = collector.add(
                subject=name,
                predicate="component_kind",
                value=kind,
                path=evidence.path,
                line=line,
                source_kind="declared",
            )
            collector.add_node("component", name, fact_id)
            emitted += 1
            exported = re.search(r"\bandroid:exported\s*=\s*[\"']([^\"']+)", attrs)
            if exported:
                exported_id = collector.add(
                    subject=name,
                    predicate="component_exported",
                    value=exported.group(1).lower() == "true",
                    path=evidence.path,
                    line=line,
                    source_kind="declared",
                )
                collector.add_node("component", name, exported_id)
                emitted += 1
        for match in re.finditer(r"<application\b([^>]*)>", evidence.text, re.S | re.I):
            attrs = match.group(1)
            name_match = _ANDROID_NAME_RE.search(attrs)
            if name_match:
                line = _line_number(evidence.text, match.start())
                fact_id = collector.add(
                    subject="application",
                    predicate="application_class",
                    value=name_match.group(1),
                    path=evidence.path,
                    line=line,
                    source_kind="declared",
                )
                collector.add_node("component", name_match.group(1), fact_id)
                emitted += 1
    if not manifest_files:
        fact_id = collector.add_unknown(
            subject="project",
            predicate="manifest_package",
            rationale="No tracked AndroidManifest.xml was found in the inspected ProjectTarget scope.",
        )
        collector.add_node("component", "manifest package (unknown)", fact_id)
        unresolved.append("Android manifest is missing from the inspected scope")
    return tuple(evidence.path for evidence in manifest_files), unresolved


def _run_build_adapter(collector: _FactCollector, files: Mapping[str, _FileEvidence]) -> tuple[tuple[str, ...], list[str]]:
    build_files = _build_files(files)
    unresolved: list[str] = []
    if not build_files:
        fact_id = collector.add_unknown(
            subject="project",
            predicate="build_system",
            rationale="No recognized build descriptor was found in the inspected ProjectTarget scope.",
        )
        collector.add_node("quality_contract", "build system (unknown)", fact_id)
        unresolved.append("unsupported or missing build layout in the inspected scope")
    emitted = 0
    for evidence in build_files:
        emitted += _add_stale_references(collector, evidence)
        name = Path(evidence.path).name.lower()
        system = "gradle" if "gradle" in name or name == "libs.versions.toml" else "maven" if name == "pom.xml" else "ant" if name == "build.xml" else "properties"
        for line, _ in _lines(evidence.text):
            if line == 1:
                fact_id = collector.add(
                    subject=evidence.path,
                    predicate="build_system",
                    value=system,
                    path=evidence.path,
                    line=line,
                    source_kind="declared",
                )
                collector.add_node("quality_contract", f"build:{system}", fact_id)
                emitted += 1
                break
        for match in _APPLICATION_ID_RE.finditer(evidence.text):
            line = _line_number(evidence.text, match.start())
            fact_id = collector.add(
                subject="project",
                predicate="application_id",
                value=match.group(1),
                path=evidence.path,
                line=line,
                source_kind="declared",
            )
            collector.add_node("component", match.group(1), fact_id)
            emitted += 1
        for match in _VERSION_RE.finditer(evidence.text):
            line = _line_number(evidence.text, match.start())
            key = match.group(0).split(match.group(1), 1)[0].strip(" =:(\t\"")
            fact_id = collector.add(
                subject=evidence.path,
                predicate="build_version",
                value={"field": key, "value": match.group(1)},
                path=evidence.path,
                line=line,
                source_kind="declared",
            )
            collector.add_node("quality_contract", f"version:{key}", fact_id)
            emitted += 1
    return tuple(evidence.path for evidence in build_files), unresolved


def _nearest_function(lines: list[tuple[int, str]], index: int, path: str) -> str:
    for line_number, text in reversed(lines[: index + 1]):
        match = _FUNCTION_RE.search(text)
        if match:
            return f"{path}:{match.group(1)}"
    return f"{path}:top-level"


def _run_symbols_adapter(collector: _FactCollector, files: Mapping[str, _FileEvidence]) -> tuple[tuple[str, ...], list[str]]:
    source_files = _source_files(files)
    unresolved: list[str] = []
    if not source_files:
        for predicate, rationale in (
            ("symbol", "No Kotlin, Java, or Gradle source file was inspected."),
            ("call_site", "No source file was available to resolve call sites."),
        ):
            collector.add_unknown(subject="project", predicate=predicate, rationale=rationale)
        unresolved.append("source symbols and call sites are unavailable in the inspected scope")
    for evidence in source_files:
        lines = list(_lines(evidence.text))
        _add_stale_references(collector, evidence)
        for line_number, text in lines:
            for match in _CLASS_RE.finditer(text):
                kind = match.group(1).replace(" ", "_").lower()
                name = match.group(2)
                fact_id = collector.add(
                    subject=name,
                    predicate="symbol_kind",
                    value=kind,
                    path=evidence.path,
                    line=line_number,
                    source_kind="derived",
                    confidence=0.98,
                )
                collector.add_node("component", name, fact_id)
            function_match = _FUNCTION_RE.search(text)
            if function_match:
                name = function_match.group(1)
                subject = f"{evidence.path}:{name}"
                fact_id = collector.add(
                    subject=subject,
                    predicate="function_signature",
                    value=name,
                    path=evidence.path,
                    line=line_number,
                    source_kind="derived",
                    confidence=0.96,
                )
                collector.add_node("operation", subject, fact_id)
            call_match = _CALL_RE.search(text)
            if call_match and call_match.group(2) not in {"if", "for", "while", "when", "catch", "require", "check"}:
                caller = _nearest_function(lines, line_number - 1, evidence.path)
                callee = f"{call_match.group(1)}.{call_match.group(2)}"
                asynchronous = bool(
                    re.search(r"\b(?:launch|async|withContext|flowOn|submit)\b", text)
                )
                fact_id = collector.add(
                    subject=caller,
                    predicate="call_site",
                    value={"callee": callee, "asynchronous": asynchronous},
                    path=evidence.path,
                    line=line_number,
                    source_kind="derived",
                    confidence=0.9,
                )
                collector.add_node("operation", caller, fact_id)
                callee_kind = "resource" if call_match.group(2).lower() in {"read", "write", "save", "load", "query", "insert", "update", "delete"} else "api"
                collector.add_node(callee_kind, callee, fact_id)
                collector.add_edge(
                    ("operation", caller),
                    (callee_kind, callee),
                    "calls",
                    "asynchronous" if asynchronous else "synchronous",
                    (fact_id,),
                )
        if not any(fact.provenance and fact.provenance[0].ref == evidence.path for fact in collector.facts.values()):
            unresolved.append(f"no parseable symbols were found in {evidence.path}")
    return tuple(evidence.path for evidence in source_files), unresolved


def _run_lifecycle_adapter(collector: _FactCollector, files: Mapping[str, _FileEvidence]) -> tuple[tuple[str, ...], list[str]]:
    source_files = _source_files(files)
    unresolved: list[str] = []
    found = False
    for evidence in source_files:
        lines = list(_lines(evidence.text))
        for line_number, text in lines:
            for term in re.findall(
                r"\b(lifecycleScope|viewModelScope|repeatOnLifecycle|onCreate|onStart|onStop|onDestroy|onCleared|CoroutineScope|cancel|close|Disposable|rememberCoroutineScope)\b",
                text,
            ):
                found = True
                subject = _nearest_function(lines, line_number - 1, evidence.path)
                predicate = "lifecycle_boundary" if term in {"onCreate", "onStart", "onStop", "onDestroy", "onCleared", "repeatOnLifecycle"} else "ownership_boundary"
                fact_id = collector.add(
                    subject=subject,
                    predicate=predicate,
                    value=term,
                    path=evidence.path,
                    line=line_number,
                    source_kind="derived",
                    confidence=0.94,
                )
                collector.add_node("operation", subject, fact_id)
                collector.add_node("resource", term, fact_id)
                collector.add_edge(
                    ("operation", subject),
                    ("resource", term),
                    "runs_on" if predicate == "lifecycle_boundary" else "depends_on",
                    "asynchronous" if term in {"lifecycleScope", "viewModelScope", "CoroutineScope", "repeatOnLifecycle"} else "unknown",
                    (fact_id,),
                )
    if not found:
        fact_id = collector.add_unknown(
            subject="project",
            predicate="lifecycle_ownership",
            rationale="No deterministic lifecycle or ownership boundary was found in the inspected source scope.",
        )
        collector.add_node("resource", "lifecycle/ownership (unknown)", fact_id)
        unresolved.append("lifecycle and ownership boundaries are unresolved")
    return tuple(evidence.path for evidence in source_files), unresolved


def _run_persistence_adapter(collector: _FactCollector, files: Mapping[str, _FileEvidence]) -> tuple[tuple[str, ...], list[str]]:
    text_files = tuple(evidence for _, evidence in sorted(files.items()))
    unresolved: list[str] = []
    categories = {
        "writer": (r"\b(?:insert|update|delete|write|save|put|upsert)\b", "persistence_writer"),
        "reader": (r"\b(?:select|query|read|load|get|fetch|observe|collect)\b", "persistence_reader"),
        "version": (r"\b(?:schemaVersion|schema_version|version)\b", "persistence_version"),
        "migration": (r"\b(?:Migration|migrate|migration)\b", "persistence_migration"),
        "restore_fallback": (r"\b(?:restore|backup|fallback|default)\b", "persistence_restore_fallback"),
    }
    found: dict[str, bool] = {key: False for key in categories}
    for evidence in text_files:
        _add_stale_references(collector, evidence)
        for line_number, text in _lines(evidence.text):
            lower = text.lower()
            if not re.search(r"\b(?:room|database|dao|datastore|sharedpreferences|sqlite|serializer|repository|storage|migration|schema|backup|restore)\b", lower):
                continue
            subject = f"{evidence.path}:{line_number}"
            for category, (pattern, predicate) in categories.items():
                match = re.search(pattern, text, re.IGNORECASE)
                if not match:
                    continue
                found[category] = True
                value = match.group(0)
                fact_id = collector.add(
                    subject=subject,
                    predicate=predicate,
                    value=value,
                    path=evidence.path,
                    line=line_number,
                    source_kind="derived",
                    confidence=0.92,
                )
                collector.add_node("resource", subject, fact_id)
                if category in {"writer", "reader"}:
                    collector.add_node("operation", subject, fact_id)
                    collector.add_edge(
                        ("operation", subject),
                        ("resource", subject),
                        "depends_on",
                        "synchronous",
                        (fact_id,),
                    )
    for category, (_, predicate) in categories.items():
        if not found[category]:
            collector.add_unknown(
                subject="project",
                predicate=predicate,
                rationale=f"No deterministic source evidence for {category} persistence behavior was found in scope.",
            )
            unresolved.append(f"persistence {category} evidence is unresolved")
    return tuple(evidence.path for evidence in text_files), unresolved


def _run_quality_adapter(collector: _FactCollector, files: Mapping[str, _FileEvidence]) -> tuple[tuple[str, ...], list[str]]:
    unresolved: list[str] = []
    signal_re = re.compile(
        r"\b(?:latency|timeout|performance|responsiveness|lifecycle|process death|"
        r"restore|migration|ownership|cancel(?:lation)?|thread|consisten(?:t|cy)|quality|"
        r"accessib(?:ility|le))\b",
        re.IGNORECASE,
    )
    version_seen = False
    for evidence in (item for _, item in sorted(files.items())):
        for line_number, text in _lines(evidence.text):
            if signal_re.search(text):
                fact_id = collector.add(
                    subject=f"{evidence.path}:{line_number}",
                    predicate="quality_contract_signal",
                    value=text.strip()[:240],
                    path=evidence.path,
                    line=line_number,
                    source_kind="declared" if Path(evidence.path).suffix.lower() in {".md", ".txt", ".yaml", ".yml", ".json"} else "derived",
                    confidence=0.85,
                )
                collector.add_node("quality_contract", f"quality:{evidence.path}:{line_number}", fact_id)
            if _VERSION_RE.search(text):
                version_seen = True
    if not version_seen:
        fact_id = collector.add_unknown(
            subject="project",
            predicate="quality_version",
            rationale="No deterministic build or schema version evidence was found in the inspected scope.",
        )
        collector.add_node("quality_contract", "quality version (unknown)", fact_id)
        unresolved.append("quality/build version evidence is unresolved")
    return tuple(sorted(files)), unresolved


def _load_files(root: Path, paths: Sequence[str]) -> tuple[dict[str, _FileEvidence], tuple[str, ...]]:
    files: dict[str, _FileEvidence] = {}
    unreadable: list[str] = []
    root_resolved = root.resolve()
    for path in sorted(paths):
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root_resolved)
            raw = candidate.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            unreadable.append(path)
            continue
        files[path] = _FileEvidence(path=path, raw=raw, text=text, sha256=_sha256_bytes(raw))
    return files, tuple(unreadable)


def _requested_tuple(requested_evidence: Sequence[str] | None) -> tuple[str, ...]:
    if requested_evidence is None:
        return _DEFAULT_EVIDENCE
    result = tuple(requested_evidence)
    _text_tuple(result, "requested_evidence", allow_empty=False)
    if len(set(result)) != len(result):
        raise DiscoveryContractError("requested_evidence must be unique")
    unknown = sorted(set(result) - set(_DEFAULT_EVIDENCE))
    if unknown:
        raise DiscoveryContractError("unsupported requested evidence class(es): " + ", ".join(unknown))
    return result


def acquire_project_context(
    target: ProjectTarget,
    *,
    requested_evidence: Sequence[str] | None = None,
    suggestions: Sequence[str] = (),
) -> ContextAcquisitionResult:
    """Acquire a bounded graph from a clean, immutable ProjectTarget.

    The function performs only read-only Git and filesystem operations.  A
    target identity mismatch or dirty worktree raises before source inspection,
    so a result can never accidentally describe a different revision.
    """

    if not isinstance(target, ProjectTarget):
        raise DiscoveryContractError("context acquisition requires a ProjectTarget")
    requested = _requested_tuple(requested_evidence)
    suggestion_tuple = tuple(suggestions)
    _text_tuple(suggestion_tuple, "suggestions")
    root, source_commit, source_tree_sha256 = _verify_project_identity(target)
    tracked = _git(root, "ls-files", "-z").decode("utf-8", errors="strict").split("\0")
    tracked = tuple(path for path in tracked if path and _path_in_scope(path, target.scope))
    selected_paths = tracked[: target.discovery_budget]
    skipped_paths = tracked[target.discovery_budget :]
    files, unreadable = _load_files(root, selected_paths)

    collector = _FactCollector(target, files)
    if unreadable:
        for path in unreadable:
            collector.unresolved_once(f"source file is unreadable or non-UTF-8: {path}")
    if skipped_paths:
        collector.unresolved_once(
            f"discovery budget exhausted: {len(skipped_paths)} in-scope tracked file(s) were skipped"
        )

    adapter_functions: dict[str, Callable[[_FactCollector, Mapping[str, _FileEvidence]], tuple[tuple[str, ...], list[str]]]] = {
        "manifest": _run_manifest_adapter,
        "build": _run_build_adapter,
        "symbols_calls": _run_symbols_adapter,
        "persistence_state": _run_persistence_adapter,
        "lifecycle_ownership": _run_lifecycle_adapter,
        "quality_version": _run_quality_adapter,
    }
    adapters: list[AdapterReceipt] = []
    for adapter_id in requested:
        before = len(collector.facts)
        inspected, unresolved = adapter_functions[adapter_id](collector, files)
        for message in unresolved:
            collector.unresolved_once(message)
        status = "complete" if not unresolved else "partial"
        if skipped_paths:
            status = "budget-exhausted"
        adapters.append(
            AdapterReceipt(
                adapter_id=adapter_id,
                status=status,
                inspected_files=inspected,
                facts_emitted=len(collector.facts) - before,
                unresolved=tuple(unresolved),
            )
        )

    # Re-check the immutable source identity after all reads.  If another
    # process changes the checkout during acquisition, fail closed instead of
    # returning a graph assembled from more than one source snapshot.
    final_root, final_commit, final_tree_sha256 = _verify_project_identity(target)
    if (
        final_root != root
        or final_commit != source_commit
        or final_tree_sha256 != source_tree_sha256
    ):
        raise DiscoveryContractError(
            "project source changed during context acquisition; refusing a mixed snapshot"
        )

    # A lifecycle adapter is intentionally separate in the receipt even though
    # both slices use the deterministic source-symbol parser.  This preserves
    # the three-prior coverage boundary without pretending to have a complete
    # language index.
    facts, nodes, edges = collector.finalize()
    graph = QualityContextGraph(
        graph_id=f"{target.target_id}-context-{source_tree_sha256[:12]}",
        target_id=target.target_id,
        facts=facts,
        nodes=nodes,
        edges=edges,
        source_origin=target.source_origin,
        source_commit=source_commit,
        source_tree_sha256=source_tree_sha256,
    )
    unresolved = tuple(collector.unresolved)
    derived_suggestions = list(suggestion_tuple)
    for message in unresolved:
        probe = f"Resolve: {message}"
        if probe not in derived_suggestions:
            derived_suggestions.append(probe)
    suggested_probes = tuple(derived_suggestions)
    frontier = [
        "runtime-thread-and-process-observation",
        "complete-language-data-flow-index",
        "out-of-scope-tracked-files",
    ]
    if skipped_paths:
        frontier.extend(f"skipped:{path}" for path in skipped_paths)
    if unreadable:
        frontier.extend(f"unreadable:{path}" for path in unreadable)
    coverage_frontier = tuple(sorted(set(frontier)))
    status = "partial" if unresolved or skipped_paths or unreadable else "complete"
    receipt = ContextAcquisitionReceipt(
        target_id=target.target_id,
        source_origin=target.source_origin,
        source_commit=source_commit,
        source_tree_sha256=source_tree_sha256,
        requested_evidence=requested,
        inspected_scope=tuple(sorted(files)),
        skipped_scope=tuple(sorted(set(skipped_paths) | set(unreadable))),
        discovery_budget=target.discovery_budget,
        budget_used=len(selected_paths),
        graph_sha256=_sha256_json(graph.to_dict()),
        adapters=tuple(adapters),
        unresolved=unresolved,
        suggested_probes=suggested_probes,
        coverage_frontier=coverage_frontier,
        no_diff=True,
        status=status,
    )
    return ContextAcquisitionResult(target=target, graph=graph, receipt=receipt)


def acquire_context(
    target: ProjectTarget | ContextAcquisitionRequest,
    *,
    requested_evidence: Sequence[str] | None = None,
    suggestions: Sequence[str] = (),
) -> ContextAcquisitionResult:
    """Public short alias for :func:`acquire_project_context`."""

    if isinstance(target, ContextAcquisitionRequest):
        if requested_evidence is not None or suggestions:
            raise DiscoveryContractError(
                "request arguments cannot be overridden at acquisition time"
            )
        return acquire_project_context(
            target.target,
            requested_evidence=target.requested_evidence,
            suggestions=target.suggestions,
        )
    return acquire_project_context(
        target,
        requested_evidence=requested_evidence,
        suggestions=suggestions,
    )


__all__ = [
    "AdapterReceipt",
    "ContextAcquisitionRequest",
    "ContextAcquisitionReceipt",
    "ContextAcquisitionResult",
    "acquire_context",
    "acquire_project_context",
]
