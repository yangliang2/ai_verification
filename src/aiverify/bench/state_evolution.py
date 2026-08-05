"""Bounded state-evolution fixture, context, adapter, and oracle contracts.

This module is the fixture-side contract for M8.  It deliberately stops at a
historical-state replay boundary: the context graph describes a writer,
durable representation, schema transition, reader, and recovery boundary, the
runtime adapter describes bounded reversible evidence collection, and the
oracle reduces observations without receiving a variant, expected outcome, or
Journey.  Campaign selection and execution accounting remain owned by the
discovery and runner packages respectively.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from aiverify.discovery.context import ContextCollectionResult, load_context_manifest
from aiverify.discovery.models import (
    ChangeTarget,
    ContextFact,
    DiscoveryContractError,
    DiscoveryTarget,
    ProjectTarget,
    ProvenanceRef,
    QualityContextGraph,
)

_SCHEMA_PATH = Path(__file__).with_name("state_evolution_schema.json")


class StateEvolutionContractError(DiscoveryContractError):
    """Raised when a state-evolution contract or observation is contradictory."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StateEvolutionContractError(f"{field} must be a non-empty string")
    return value


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise StateEvolutionContractError(f"{field} must be a positive integer")
    return value


def _non_negative_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise StateEvolutionContractError(f"{field} must be a non-negative integer")
    return value


def _sha256(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise StateEvolutionContractError(f"{field} must be a lowercase SHA-256 digest")
    return text


def _tuple_text(value: object, field: str, *, non_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise StateEvolutionContractError(f"{field} must be a tuple of strings")
    if non_empty and not value:
        raise StateEvolutionContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise StateEvolutionContractError(f"{field} must contain non-empty strings")
    if len(set(value)) != len(value):
        raise StateEvolutionContractError(f"{field} must not contain duplicates")
    return value


def _canonical_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise StateEvolutionContractError(
            f"unknown {label} field(s): " + ", ".join(unknown)
        )


@dataclass(frozen=True)
class StateSnapshot:
    """The observable state invariant before or after one recovery epoch."""

    sentinel: str
    schema_version: int
    revision: int
    migration_status: str
    snapshot_id: str = ""

    def __post_init__(self) -> None:
        _text(self.sentinel, "state snapshot sentinel")
        _positive_int(self.schema_version, "state snapshot schema_version")
        _non_negative_int(self.revision, "state snapshot revision")
        _text(self.migration_status, "state snapshot migration_status")
        if self.snapshot_id:
            _text(self.snapshot_id, "state snapshot snapshot_id")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "sentinel": self.sentinel,
            "schema_version": self.schema_version,
            "revision": self.revision,
            "migration_status": self.migration_status,
        }
        if self.snapshot_id:
            result["snapshot_id"] = self.snapshot_id
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, label: str = "state snapshot") -> StateSnapshot:
        if not isinstance(data, Mapping):
            raise StateEvolutionContractError(f"{label} must be an object")
        _reject_unknown(
            data,
            {"sentinel", "schema_version", "revision", "migration_status", "snapshot_id"},
            label,
        )
        try:
            return cls(
                sentinel=data["sentinel"],
                schema_version=data["schema_version"],
                revision=data["revision"],
                migration_status=data["migration_status"],
                snapshot_id=data.get("snapshot_id", ""),
            )
        except KeyError as error:
            raise StateEvolutionContractError(
                f"{label} requires {error.args[0]}"
            ) from error


# A descriptive alias keeps callers that use the issue's terminology concise.
StateInvariant = StateSnapshot


@dataclass(frozen=True)
class MigrationEdge:
    """A single deterministic schema transition in the fixture contract."""

    edge_id: str
    from_schema: int
    to_schema: int
    from_revision: int
    to_revision: int
    operation: str
    exactly_once: bool = True

    def __post_init__(self) -> None:
        _text(self.edge_id, "migration edge_id")
        _positive_int(self.from_schema, "migration from_schema")
        _positive_int(self.to_schema, "migration to_schema")
        _non_negative_int(self.from_revision, "migration from_revision")
        _non_negative_int(self.to_revision, "migration to_revision")
        _text(self.operation, "migration operation")
        if not isinstance(self.exactly_once, bool):
            raise StateEvolutionContractError("migration exactly_once must be boolean")
        if self.from_schema == self.to_schema:
            raise StateEvolutionContractError("migration must cross a schema boundary")

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "from_schema": self.from_schema,
            "to_schema": self.to_schema,
            "from_revision": self.from_revision,
            "to_revision": self.to_revision,
            "operation": self.operation,
            "exactly_once": self.exactly_once,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MigrationEdge:
        if not isinstance(data, Mapping):
            raise StateEvolutionContractError("migration must be an object")
        _reject_unknown(
            data,
            {
                "edge_id",
                "from_schema",
                "to_schema",
                "from_revision",
                "to_revision",
                "operation",
                "exactly_once",
            },
            "migration",
        )
        try:
            return cls(
                edge_id=data["edge_id"],
                from_schema=data["from_schema"],
                to_schema=data["to_schema"],
                from_revision=data["from_revision"],
                to_revision=data["to_revision"],
                operation=data["operation"],
                exactly_once=data.get("exactly_once", True),
            )
        except KeyError as error:
            raise StateEvolutionContractError(
                f"migration requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class RecoveryBoundary:
    """A local, bounded, reversible sequence used by the runtime adapter."""

    boundary_id: str
    events: tuple[str, ...]
    timeout_seconds: int = 30
    reversible: bool = True
    local_only: bool = True
    transport: str = "com.android.localtransport/.LocalTransport"

    def __post_init__(self) -> None:
        _text(self.boundary_id, "recovery boundary_id")
        _tuple_text(self.events, "recovery events", non_empty=True)
        _positive_int(self.timeout_seconds, "recovery timeout_seconds")
        if not isinstance(self.reversible, bool) or not isinstance(self.local_only, bool):
            raise StateEvolutionContractError("recovery reversible/local_only must be boolean")
        _text(self.transport, "recovery transport")
        if self.events != ("rotate", "process_death", "backup_restore"):
            raise StateEvolutionContractError(
                "recovery events must be rotate, process_death, backup_restore in order"
            )
        if not self.reversible or not self.local_only:
            raise StateEvolutionContractError(
                "state-evolution recovery must be reversible and local-only"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "boundary_id": self.boundary_id,
            "events": list(self.events),
            "timeout_seconds": self.timeout_seconds,
            "reversible": self.reversible,
            "local_only": self.local_only,
            "transport": self.transport,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> RecoveryBoundary:
        if not isinstance(data, Mapping):
            raise StateEvolutionContractError("recovery must be an object")
        _reject_unknown(
            data,
            {"boundary_id", "events", "timeout_seconds", "reversible", "local_only", "transport"},
            "recovery",
        )
        try:
            events = data["events"]
            if not isinstance(events, list):
                raise StateEvolutionContractError("recovery events must be an array")
            return cls(
                boundary_id=data["boundary_id"],
                events=tuple(events),
                timeout_seconds=data.get("timeout_seconds", 30),
                reversible=data.get("reversible", True),
                local_only=data.get("local_only", True),
                transport=data.get("transport", cls.transport),
            )
        except KeyError as error:
            raise StateEvolutionContractError(
                f"recovery requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class StateResourceIds:
    """Stable UI/resource IDs used only to decode observed layout evidence."""

    sentinel: str = "fixture_sentinel"
    schema_version: str = "fixture_schema_version"
    revision: str = "fixture_revision"
    migration_status: str = "fixture_migration_status"

    def __post_init__(self) -> None:
        for resource_field in ("sentinel", "schema_version", "revision", "migration_status"):
            _text(getattr(self, resource_field), f"resource {resource_field}")

    def to_dict(self) -> dict[str, str]:
        return {
            "sentinel": self.sentinel,
            "schema_version": self.schema_version,
            "revision": self.revision,
            "migration_status": self.migration_status,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StateResourceIds:
        if not isinstance(data, Mapping):
            raise StateEvolutionContractError("resources must be an object")
        _reject_unknown(
            data,
            {"sentinel", "schema_version", "revision", "migration_status"},
            "resources",
        )
        return cls(
            sentinel=data.get("sentinel", cls.sentinel),
            schema_version=data.get("schema_version", cls.schema_version),
            revision=data.get("revision", cls.revision),
            migration_status=data.get("migration_status", cls.migration_status),
        )


@dataclass(frozen=True)
class DurableStateContract:
    """Quality Contract for continuity and exactly-once migration."""

    contract_id: str
    property: str
    constraint: str
    source_fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _text(self.contract_id, "quality contract_id")
        _text(self.property, "quality property")
        _text(self.constraint, "quality constraint")
        _tuple_text(self.source_fact_ids, "quality source_fact_ids", non_empty=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "property": self.property,
            "constraint": self.constraint,
            "source_fact_ids": list(self.source_fact_ids),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DurableStateContract:
        if not isinstance(data, Mapping):
            raise StateEvolutionContractError("quality_contract must be an object")
        _reject_unknown(data, {"contract_id", "property", "constraint", "source_fact_ids"}, "quality_contract")
        try:
            source_fact_ids = data["source_fact_ids"]
            if not isinstance(source_fact_ids, list):
                raise StateEvolutionContractError("quality source_fact_ids must be an array")
            return cls(
                contract_id=data["contract_id"],
                property=data["property"],
                constraint=data["constraint"],
                source_fact_ids=tuple(source_fact_ids),
            )
        except KeyError as error:
            raise StateEvolutionContractError(
                f"quality_contract requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class StateEvolutionFixtureContract:
    """Neutral identity and invariant contract for matched fixture variants."""

    contract_id: str
    fixture_pair_id: str
    package: str
    activity: str
    old_state: StateSnapshot
    current_state: StateSnapshot
    migration: MigrationEdge
    recovery: RecoveryBoundary
    quality_contract: DurableStateContract
    resources: StateResourceIds = field(default_factory=StateResourceIds)
    provenance: tuple[ProvenanceRef, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        _text(self.contract_id, "contract_id")
        _text(self.fixture_pair_id, "fixture_pair_id")
        _text(self.package, "package")
        _text(self.activity, "activity")
        if not isinstance(self.old_state, StateSnapshot):
            raise StateEvolutionContractError("old_state must be StateSnapshot")
        if not isinstance(self.current_state, StateSnapshot):
            raise StateEvolutionContractError("current_state must be StateSnapshot")
        if not isinstance(self.migration, MigrationEdge):
            raise StateEvolutionContractError("migration must be MigrationEdge")
        if not isinstance(self.recovery, RecoveryBoundary):
            raise StateEvolutionContractError("recovery must be RecoveryBoundary")
        if not isinstance(self.quality_contract, DurableStateContract):
            raise StateEvolutionContractError("quality_contract must be DurableStateContract")
        if not isinstance(self.resources, StateResourceIds):
            raise StateEvolutionContractError("resources must be StateResourceIds")
        if not isinstance(self.provenance, tuple) or any(
            not isinstance(item, ProvenanceRef) for item in self.provenance
        ):
            raise StateEvolutionContractError("provenance must contain ProvenanceRef values")
        if not self.provenance:
            raise StateEvolutionContractError("fixture contract requires provenance")
        if not isinstance(self.schema_version, int) or isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise StateEvolutionContractError("unsupported fixture contract schema_version")
        if self.old_state.schema_version != self.migration.from_schema:
            raise StateEvolutionContractError("old state does not match migration source schema")
        if self.current_state.schema_version != self.migration.to_schema:
            raise StateEvolutionContractError("current state does not match migration target schema")
        if self.old_state.revision != self.migration.from_revision:
            raise StateEvolutionContractError("old state does not match migration source revision")
        if self.current_state.revision != self.migration.to_revision:
            raise StateEvolutionContractError("current state does not match migration target revision")
        if self.old_state.sentinel != self.current_state.sentinel:
            raise StateEvolutionContractError("state continuity requires a stable sentinel")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_id": self.contract_id,
            "fixture_pair_id": self.fixture_pair_id,
            "package": self.package,
            "activity": self.activity,
            "old_state": self.old_state.to_dict(),
            "current_state": self.current_state.to_dict(),
            "migration": self.migration.to_dict(),
            "recovery": self.recovery.to_dict(),
            "quality_contract": self.quality_contract.to_dict(),
            "resources": self.resources.to_dict(),
            "provenance": [item.to_dict() for item in self.provenance],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> StateEvolutionFixtureContract:
        if not isinstance(data, Mapping):
            raise StateEvolutionContractError("fixture contract must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "contract_id",
                "fixture_pair_id",
                "package",
                "activity",
                "old_state",
                "current_state",
                "migration",
                "recovery",
                "quality_contract",
                "resources",
                "provenance",
            },
            "fixture contract",
        )
        try:
            raw_provenance = data["provenance"]
            if not isinstance(raw_provenance, list):
                raise StateEvolutionContractError("fixture provenance must be an array")
            return cls(
                contract_id=data["contract_id"],
                fixture_pair_id=data["fixture_pair_id"],
                package=data["package"],
                activity=data["activity"],
                old_state=StateSnapshot.from_dict(data["old_state"], label="old_state"),
                current_state=StateSnapshot.from_dict(data["current_state"], label="current_state"),
                migration=MigrationEdge.from_dict(data["migration"]),
                recovery=RecoveryBoundary.from_dict(data["recovery"]),
                quality_contract=DurableStateContract.from_dict(data["quality_contract"]),
                resources=StateResourceIds.from_dict(data.get("resources", {})),
                provenance=tuple(ProvenanceRef.from_dict(item) for item in raw_provenance),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise StateEvolutionContractError(
                f"fixture contract requires {error.args[0]}"
            ) from error


# Short name used by callers that do not need to mention the fixture pairing.
StateEvolutionContract = StateEvolutionFixtureContract


@dataclass(frozen=True)
class ProvenanceVerification:
    """Checksum receipt for one neutral fixture contract's source inputs."""

    contract_path: str
    checks: tuple[Mapping[str, Any], ...]

    @property
    def valid(self) -> bool:
        return all(item.get("status") == "pass" for item in self.checks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "contract_path": self.contract_path,
            "checks": [dict(item) for item in self.checks],
            "valid": self.valid,
        }


def load_state_evolution_contract(path: str | Path) -> StateEvolutionFixtureContract:
    """Read one strict, neutral fixture contract from JSON."""

    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StateEvolutionContractError(f"fixture contract cannot be read: {error}") from error
    return StateEvolutionFixtureContract.from_dict(data)


def verify_state_evolution_provenance(
    contract_path: str | Path,
    *,
    base_dir: str | Path | None = None,
) -> ProvenanceVerification:
    """Verify every identity-bearing source reference in a contract.

    The verifier returns an explicit failed receipt instead of treating a
    missing source as an observed fact.  Callers may use ``valid`` as a
    fail-closed admission gate before deriving or executing a probe.
    """

    source = Path(contract_path).resolve()
    root = Path(base_dir).resolve() if base_dir is not None else source.parent
    contract = load_state_evolution_contract(source)
    checks: list[Mapping[str, Any]] = []
    for provenance in contract.provenance:
        path = _bound_source_path(root, provenance.ref)
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        passed = actual == provenance.source_sha256
        checks.append(
            {
                "ref": provenance.ref,
                "path": str(path),
                "expected_sha256": provenance.source_sha256,
                "actual_sha256": actual,
                "status": "pass" if passed else "fail",
            }
        )
    return ProvenanceVerification(contract_path=str(source), checks=tuple(checks))


def _bound_source_path(root: Path, reference: str) -> Path:
    """Resolve a provenance reference without allowing it to escape its root."""

    candidate = (root / reference).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise StateEvolutionContractError(
            f"provenance reference escapes source root: {reference}"
        ) from error
    return candidate


def verify_state_context_provenance(
    context_path: str | Path,
    graph: QualityContextGraph,
    *,
    base_dir: str | Path,
) -> ProvenanceVerification:
    """Verify known ContextFact provenance before the graph is trusted."""

    source = Path(context_path).resolve()
    root = Path(base_dir).resolve()
    checks: list[Mapping[str, Any]] = []
    for fact in graph.facts:
        if fact.status == "unknown":
            continue
        for provenance in fact.provenance:
            path = _bound_source_path(root, provenance.ref)
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            passed = provenance.source_sha256 is not None and actual == provenance.source_sha256
            checks.append(
                {
                    "fact_id": fact.fact_id,
                    "ref": provenance.ref,
                    "path": str(path),
                    "expected_sha256": provenance.source_sha256,
                    "actual_sha256": actual,
                    "status": "pass" if passed else "fail",
                }
            )
    return ProvenanceVerification(contract_path=str(source), checks=tuple(checks))


def verify_change_target_diff(
    target: ChangeTarget,
    *,
    repo_root: str | Path,
) -> ProvenanceVerification:
    """Bind a ChangeTarget diff to bytes before state context is trusted."""

    root = Path(repo_root).resolve()
    checks: list[Mapping[str, Any]] = []
    if not isinstance(target, ChangeTarget):
        return ProvenanceVerification(
            contract_path=str(root),
            checks=({"target_id": getattr(target, "target_id", ""), "status": "fail", "detail": "state change validation requires ChangeTarget"},),
        )
    try:
        path = _bound_source_path(root, target.diff_ref)
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        passed = actual == target.diff_sha256
        checks.append(
            {
                "target_id": target.target_id,
                "diff_ref": target.diff_ref,
                "path": str(path),
                "expected_sha256": target.diff_sha256,
                "actual_sha256": actual,
                "status": "pass" if passed else "fail",
            }
        )
    except StateEvolutionContractError as error:
        checks.append(
            {
                "target_id": getattr(target, "target_id", ""),
                "diff_ref": getattr(target, "diff_ref", ""),
                "status": "fail",
                "detail": str(error),
            }
        )
    return ProvenanceVerification(contract_path=str(root), checks=tuple(checks))


def verify_state_evolution_matched_pair(
    pair_path: str | Path,
    *,
    repo_root: str | Path,
) -> ProvenanceVerification:
    """Verify auditor-only source/build identity and protocol equivalence."""

    source = Path(pair_path).resolve()
    root = Path(repo_root).resolve()
    checks: list[Mapping[str, Any]] = []
    try:
        document = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(document, Mapping):
            raise StateEvolutionContractError("matched pair must be an object")
        _reject_unknown(
            document,
            {"schema_version", "pair_id", "audit_mapping", "public_contract", "public_contract_sha256", "protocol", "build_recipe", "source_pair", "protocol_equivalence", "claim_boundary"},
            "matched pair",
        )
        if document.get("schema_version") != 1:
            raise StateEvolutionContractError("unsupported matched pair schema_version")
        for key in ("public_contract", "protocol", "build_recipe", "source_pair", "protocol_equivalence"):
            if key not in document:
                raise StateEvolutionContractError(f"matched pair requires {key}")
        def pair_source(reference: str) -> Path:
            candidate = (source.parent / reference).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as error:
                raise StateEvolutionContractError(
                    f"matched pair reference escapes repository root: {reference}"
                ) from error
            return candidate

        public_contract = pair_source(str(document["public_contract"]))
        contract_hash = hashlib.sha256(public_contract.read_bytes()).hexdigest() if public_contract.is_file() else None
        checks.append({"artifact": "public_contract", "path": str(public_contract), "expected_sha256": document.get("public_contract_sha256"), "actual_sha256": contract_hash, "status": "pass" if public_contract.is_file() and contract_hash == document.get("public_contract_sha256") else "fail"})
        for artifact_name in ("protocol", "build_recipe"):
            artifact = document[artifact_name]
            if not isinstance(artifact, Mapping):
                raise StateEvolutionContractError(f"matched pair {artifact_name} must be an object")
            path = pair_source(str(artifact.get("path", "")))
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
            passed = actual == artifact.get("sha256")
            checks.append({"artifact": artifact_name, "path": str(path), "expected_sha256": artifact.get("sha256"), "actual_sha256": actual, "status": "pass" if passed else "fail"})
        source_pair = document["source_pair"]
        if not isinstance(source_pair, Mapping):
            raise StateEvolutionContractError("matched pair source_pair must be an object")
        for member in ("base", "changed"):
            item = source_pair.get(member)
            if not isinstance(item, Mapping):
                raise StateEvolutionContractError(f"matched pair source_pair.{member} must be an object")
            if not isinstance(item.get("variant_id"), str) or not item.get("variant_id", "").strip():
                raise StateEvolutionContractError(f"matched pair source_pair.{member} requires variant_id")
            source_file = pair_source(str(item.get("source_path", "")))
            actual_source = hashlib.sha256(source_file.read_bytes()).hexdigest() if source_file.is_file() else None
            source_ok = actual_source == item.get("source_sha256")
            checks.append({"artifact": f"{member}.source", "path": str(source_file), "expected_sha256": item.get("source_sha256"), "actual_sha256": actual_source, "status": "pass" if source_ok else "fail"})
            change_path_raw = item.get("change_path")
            change_hash = item.get("change_sha256")
            if change_path_raw is None:
                change_ok = change_hash is None
                checks.append({"artifact": f"{member}.change", "status": "pass" if change_ok else "fail"})
            else:
                change_file = pair_source(str(change_path_raw))
                actual_change = hashlib.sha256(change_file.read_bytes()).hexdigest() if change_file.is_file() else None
                change_ok = actual_change == change_hash
                checks.append({"artifact": f"{member}.change", "path": str(change_file), "expected_sha256": change_hash, "actual_sha256": actual_change, "status": "pass" if change_ok else "fail"})
        equivalence = document["protocol_equivalence"]
        if not isinstance(equivalence, Mapping):
            raise StateEvolutionContractError("matched pair protocol_equivalence must be an object")
        equivalent = all(equivalence.get(key) is True for key in ("same_protocol_sha256", "same_package_activity", "same_resource_ids"))
        checks.append({"artifact": "protocol_equivalence", "status": "pass" if equivalent else "fail"})
        members = document["source_pair"]
        distinct_ids = members["base"].get("variant_id") != members["changed"].get("variant_id")
        checks.append({"artifact": "variant_identity", "status": "pass" if distinct_ids else "fail"})
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, StateEvolutionContractError) as error:
        checks.append({"artifact": "matched_pair", "status": "fail", "detail": f"{type(error).__name__}: {error}"})
    return ProvenanceVerification(contract_path=str(source), checks=tuple(checks))


def load_state_evolution_schema(path: str | Path | None = None) -> dict[str, Any]:
    """Load the checked-in JSON schema used by fixture contracts."""

    schema_path = Path(path) if path is not None else _SCHEMA_PATH
    try:
        data = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise StateEvolutionContractError(f"state-evolution schema cannot be read: {error}") from error
    return data


def self_validate_state_evolution_schema() -> None:
    """Fail before a contract is trusted when the checked-in schema is invalid."""

    Draft202012Validator.check_schema(load_state_evolution_schema())


@dataclass(frozen=True)
class StateEvolutionContext:
    """Target-bound context snapshot with an explicit evidence gap list."""

    target: DiscoveryTarget
    contract: StateEvolutionFixtureContract
    collection: ContextCollectionResult
    required_fact_ids: tuple[str, ...]
    unresolved: tuple[str, ...] = ()
    contract_provenance: ProvenanceVerification | None = None
    context_provenance: ProvenanceVerification | None = None

    @property
    def graph(self) -> QualityContextGraph:
        return self.collection.graph

    @property
    def provenance_bound(self) -> bool:
        facts = {fact.fact_id: fact for fact in self.graph.facts}
        return all(
            fact.status == "known" and bool(fact.provenance)
            for fact_id in self.required_fact_ids
            if (fact := facts.get(fact_id)) is not None
        ) and all(
            fact_id in facts and facts[fact_id].status == "known" and bool(facts[fact_id].provenance)
            for fact_id in self.required_fact_ids
        )

    @property
    def derivation_ready(self) -> bool:
        """Whether static state structure is sufficient to derive a probe.

        Runtime identity is intentionally unknown in a static snapshot.  It is
        an execution-admission requirement, not a reason to discard a known
        writer/storage/schema/reader path before an Attack Plan exists.
        """

        return self.provenance_bound and not any(
            reason.startswith(
                (
                    "missing required state fact",
                    "state fact ",
                    "state context graph",
                    "quality contract references",
                )
            )
            for reason in self.unresolved
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "target": self.target.to_dict(),
            "contract": self.contract.to_dict(),
            "graph": self.graph.to_dict(),
            "required_fact_ids": list(self.required_fact_ids),
            "unresolved": list(self.unresolved),
            "provenance": {
                "contract": self.contract_provenance.to_dict() if self.contract_provenance else None,
                "context": self.context_provenance.to_dict() if self.context_provenance else None,
            },
        }


_REQUIRED_PREDICATES = {
    "writes_legacy_state",
    "stores_durable_state",
    "schema_version",
    "migrates_to_schema",
    "reads_current_state",
    "crosses_recovery_boundary",
    "quality_contract",
}


def _context_requirements(
    graph: QualityContextGraph,
    contract: StateEvolutionFixtureContract,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return required fact IDs and deterministic unresolved reasons."""

    required: list[str] = []
    unresolved: list[str] = []
    by_predicate: dict[str, list[ContextFact]] = {}
    for fact in graph.facts:
        by_predicate.setdefault(fact.predicate, []).append(fact)
    for predicate in sorted(_REQUIRED_PREDICATES):
        matches = by_predicate.get(predicate, [])
        if not matches:
            unresolved.append(f"missing required state fact: {predicate}")
            continue
        required.extend(fact.fact_id for fact in matches)
        for fact in matches:
            if fact.status != "known":
                unresolved.append(f"state fact {fact.fact_id} is {fact.status}")
            if not fact.provenance:
                unresolved.append(f"state fact {fact.fact_id} lacks provenance")
    if graph.target_id == "":
        unresolved.append("context graph target identity is empty")

    # The graph topology must expose each causal boundary.  Exact node IDs are
    # intentionally not required, so a project can use its own source names.
    node_by_id = {node.node_id: node for node in graph.nodes}
    edge_by_id = {edge.edge_id: edge for edge in graph.edges}
    required_kinds = {"component", "resource", "operation", "quality_contract"}
    if not required_kinds.issubset({node.kind for node in graph.nodes}):
        unresolved.append("state context graph is missing writer/storage/migration/contract node kinds")
    if not any(edge.kind in {"depends_on", "critical_path"} for edge in graph.edges):
        unresolved.append("state context graph is missing a dependency path")
    if not node_by_id or not edge_by_id:
        unresolved.append("state context graph has no topology")

    # Contract-level linkage is itself a fact: a typo cannot silently turn a
    # different quality property into this risk family.
    if contract.quality_contract.source_fact_ids:
        fact_ids = {fact.fact_id for fact in graph.facts}
        missing = sorted(set(contract.quality_contract.source_fact_ids) - fact_ids)
        if missing:
            unresolved.append("quality contract references missing fact(s): " + ", ".join(missing))
    return tuple(dict.fromkeys(required)), tuple(dict.fromkeys(unresolved))


def load_state_evolution_context(
    context_path: str | Path,
    target: DiscoveryTarget,
    *,
    contract_path: str | Path,
) -> StateEvolutionContext:
    """Load the same neutral graph for ChangeTarget and ProjectTarget."""

    contract = load_state_evolution_contract(contract_path)
    contract_provenance = verify_state_evolution_provenance(contract_path)
    if not contract_provenance.valid:
        raise StateEvolutionContractError(
            "fixture contract provenance is not valid: "
            + ", ".join(
                str(item.get("ref"))
                for item in contract_provenance.checks
                if item.get("status") != "pass"
            )
        )
    collection = load_context_manifest(context_path, target)
    if isinstance(target, ChangeTarget):
        change_provenance = verify_change_target_diff(target, repo_root=target.worktree)
        if not change_provenance.valid:
            raise StateEvolutionContractError(
                "ChangeTarget diff provenance is not valid: "
                + ", ".join(
                    str(item.get("diff_ref", ""))
                    for item in change_provenance.checks
                    if item.get("status") != "pass"
                )
            )
    context_provenance = verify_state_context_provenance(
        context_path,
        collection.graph,
        base_dir=Path(contract_path).resolve().parent,
    )
    if not context_provenance.valid:
        raise StateEvolutionContractError(
            "state context provenance is not valid: "
            + ", ".join(
                str(item.get("ref"))
                for item in context_provenance.checks
                if item.get("status") != "pass"
            )
        )
    if collection.graph.target_id != target.target_id:
        raise StateEvolutionContractError("state context graph target does not match target")
    required, unresolved = _context_requirements(collection.graph, contract)
    return StateEvolutionContext(
        target=target,
        contract=contract,
        collection=collection,
        required_fact_ids=required,
        unresolved=tuple(dict.fromkeys((*collection.unresolved, *unresolved))),
        contract_provenance=contract_provenance,
        context_provenance=context_provenance,
    )


def validate_state_evolution_context(context: StateEvolutionContext) -> tuple[str, ...]:
    """Return deterministic reasons why a context cannot support derivation."""

    reasons = list(context.unresolved)
    if context.graph.target_id != context.target.target_id:
        reasons.append("state context graph target does not match target")
    if not context.provenance_bound:
        reasons.append("required state facts are not all known and provenance-bound")
    if not isinstance(context.target, (ChangeTarget, ProjectTarget)):
        reasons.append("state context target must be ChangeTarget or ProjectTarget")
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True)
class RuntimeStep:
    """One bounded adapter phase; it is not a verifier Journey."""

    step_id: str
    boundary: str
    action: str
    event: str | None = None

    def __post_init__(self) -> None:
        _text(self.step_id, "runtime step_id")
        _text(self.boundary, "runtime boundary")
        _text(self.action, "runtime action")
        if self.event is not None:
            _text(self.event, "runtime event")

    def to_dict(self) -> dict[str, Any]:
        result = {"step_id": self.step_id, "boundary": self.boundary, "action": self.action}
        if self.event is not None:
            result["event"] = self.event
        return result


@dataclass(frozen=True)
class RuntimeEvidenceCheck:
    """Structural evidence check, separate from oracle classification."""

    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": "pass" if self.passed else "fail", "detail": self.detail}


@dataclass(frozen=True)
class RuntimePhaseReceipt:
    """One deterministic adapter phase receipt, without an outcome."""

    phase_id: str
    status: str
    input_sha256: str
    evidence_ref: str
    detail: str = ""

    def __post_init__(self) -> None:
        _text(self.phase_id, "phase receipt phase_id")
        if self.status not in {"prepared", "requested", "recorded", "failed"}:
            raise StateEvolutionContractError("invalid runtime phase receipt status")
        _sha256(self.input_sha256, "phase receipt input_sha256")
        _text(self.evidence_ref, "phase receipt evidence_ref")

    def to_dict(self) -> dict[str, Any]:
        result = {
            "phase_id": self.phase_id,
            "status": self.status,
            "input_sha256": self.input_sha256,
            "evidence_ref": self.evidence_ref,
        }
        if self.detail:
            result["detail"] = self.detail
        return result


@dataclass(frozen=True)
class StateReplayReceipt:
    """Bounded adapter record returned before an oracle conclusion exists."""

    replay_id: str
    phases: tuple[RuntimePhaseReceipt, ...]
    seed: StateSnapshot
    terminal: bool
    local_only: bool = True
    reversible: bool = True

    def __post_init__(self) -> None:
        _text(self.replay_id, "replay_id")
        if not isinstance(self.phases, tuple) or not self.phases:
            raise StateEvolutionContractError("replay phases must not be empty")
        if any(not isinstance(item, RuntimePhaseReceipt) for item in self.phases):
            raise StateEvolutionContractError("replay phases must contain RuntimePhaseReceipt values")
        if not isinstance(self.seed, StateSnapshot):
            raise StateEvolutionContractError("replay seed must be StateSnapshot")
        if not isinstance(self.terminal, bool) or not isinstance(self.local_only, bool) or not isinstance(self.reversible, bool):
            raise StateEvolutionContractError("replay terminal/local_only/reversible must be boolean")
        if not self.local_only or not self.reversible:
            raise StateEvolutionContractError("replay must be local-only and reversible")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "replay_id": self.replay_id,
            "phases": [item.to_dict() for item in self.phases],
            "seed": self.seed.to_dict(),
            "terminal": self.terminal,
            "local_only": self.local_only,
            "reversible": self.reversible,
        }


@dataclass(frozen=True)
class StateEvolutionRuntimeAdapter:
    """Describe and validate one deterministic local state replay boundary."""

    contract: StateEvolutionFixtureContract

    def __post_init__(self) -> None:
        if not isinstance(self.contract, StateEvolutionFixtureContract):
            raise StateEvolutionContractError("runtime adapter requires fixture contract")

    @property
    def steps(self) -> tuple[RuntimeStep, ...]:
        return (
            RuntimeStep("seed-old-state", "before-recovery", "create or import the frozen old-state record"),
            RuntimeStep("observe-old-state", "before-recovery", "capture state identity and old-state observation"),
            RuntimeStep("rotate", "recovery", "cross configuration boundary", event="rotate"),
            RuntimeStep("process-death", "recovery", "cross process boundary", event="process_death"),
            RuntimeStep("backup-restore", "recovery", "cross backup and restore epoch", event="backup_restore"),
            RuntimeStep("observe-restored-state", "after-recovery", "capture restored state and process/transport evidence"),
        )

    def create_old_state(self) -> StateSnapshot:
        """Create the deterministic v1 record in memory, without device I/O."""

        return self.contract.old_state

    def import_old_state(self, state: Mapping[str, Any] | None = None) -> StateSnapshot:
        """Validate/import an old record supplied by an injectable runner."""

        if state is None:
            return self.create_old_state()
        imported = StateSnapshot.from_dict(state, label="imported old state")
        if imported != self.contract.old_state:
            raise StateEvolutionContractError("imported old state does not match fixture contract")
        return imported

    def replay(
        self,
        *,
        phase_runner: Callable[[RuntimeStep, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> StateReplayReceipt:
        """Record a bounded replay; only an injected runner may touch a device.

        With no runner this method is a deterministic preparation receipt. An
        injected runner receives each phase and may return its own evidence;
        the adapter never interprets that evidence as a verdict.
        """

        phases: list[RuntimePhaseReceipt] = []
        for step in self.steps:
            if step.step_id in {"seed-old-state", "observe-old-state"}:
                payload: Mapping[str, Any] = {"state": self.create_old_state().to_dict()}
            else:
                payload = {"event": step.event, "boundary": step.boundary}
            digest = _canonical_digest(payload)
            if phase_runner is None:
                status = "prepared" if step.step_id.startswith(("seed", "observe")) else "requested"
                evidence_ref = f"adapter://state-evolution/{step.step_id}"
                detail = "no external runner injected"
            else:
                result = phase_runner(step, payload)
                if not isinstance(result, Mapping):
                    raise StateEvolutionContractError("phase runner must return an evidence mapping")
                status_value = result.get("status", "recorded")
                status = status_value if status_value in {"recorded", "failed"} else "recorded"
                evidence_ref = str(result.get("evidence_ref", f"injected://{step.step_id}"))
                detail = str(result.get("detail", ""))
            phases.append(RuntimePhaseReceipt(step.step_id, status, digest, evidence_ref, detail))
        return StateReplayReceipt(
            replay_id="state-replay-" + _canonical_digest([item.to_dict() for item in phases])[:16],
            phases=tuple(phases),
            seed=self.create_old_state(),
            terminal=True,
        )

    def plan(self) -> tuple[dict[str, Any], ...]:
        """Return side-effect-free adapter phases with no expected conclusion."""

        return tuple(step.to_dict() for step in self.steps)

    def validate_evidence(self, evidence: Mapping[str, Any]) -> tuple[RuntimeEvidenceCheck, ...]:
        """Validate terminal/process/transport identity without classifying state."""

        if not isinstance(evidence, Mapping):
            return (RuntimeEvidenceCheck("evidence-object", False, "evidence must be an object"),)
        checks: list[RuntimeEvidenceCheck] = []
        checks.append(RuntimeEvidenceCheck("terminal", evidence.get("terminal") is True, "terminal evidence is required"))
        process = evidence.get("process_event")
        process_ok = _process_event_accountable(process, self.contract.package)
        checks.append(RuntimeEvidenceCheck("process-identity", process_ok, "process before/after identity must change"))
        restore = evidence.get("backup_event")
        restore_ok = _backup_event_accountable(
            restore,
            self.contract.package,
            self.contract.recovery.transport,
        )
        checks.append(RuntimeEvidenceCheck("restore-transport", restore_ok, "backup/restore and cleanup receipts are required"))
        identity = evidence.get("execution_identity")
        identity_ok = _execution_identity_matches(self.contract, identity)
        checks.append(RuntimeEvidenceCheck("execution-identity", identity_ok, "package/activity/state_epoch identity is required"))
        return tuple(checks)


def _pid_set(value: object) -> set[str]:
    if not isinstance(value, list) or not all(isinstance(pid, str) and pid.isdecimal() for pid in value):
        return set()
    return set(value)


def _execution_identity_matches(
    contract: StateEvolutionFixtureContract,
    identity: object,
) -> bool:
    return isinstance(identity, Mapping) and (
        identity.get("package") == contract.package
        and identity.get("activity") == contract.activity
        and identity.get("state_epoch") == contract.recovery.boundary_id
    )


def _process_event_accountable(event: object, package: str) -> bool:
    if not isinstance(event, Mapping) or event.get("status") != "passed":
        return False
    evidence = event.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    before = _pid_set(evidence.get("before_pids"))
    after = _pid_set(evidence.get("after_pids"))
    return bool(before) and bool(after) and before.isdisjoint(after) and all(
        evidence.get(key) == expected
        for key, expected in (
            ("background_status", "success"),
            ("target_resumed_after_home", False),
            ("kill_status", "success"),
            ("process_absent_after_kill", True),
            ("relaunch_status", "success"),
            ("target_resumed_after_relaunch", True),
        )
    ) and evidence.get("foreground_resumed_package") == package and bool(
        evidence.get("background_resumed_package")
    )


def _backup_event_accountable(event: object, package: str, transport: str) -> bool:
    if not isinstance(event, Mapping) or event.get("status") != "passed":
        return False
    evidence = event.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    previous_transport = evidence.get("previous_transport")
    backup_enabled = evidence.get("backup_was_enabled")
    return (
        evidence.get("backup_status") == "success"
        and evidence.get("clear_data_status") == "success"
        and evidence.get("clear_data_output") == "Success"
        and evidence.get("restore_status") == "success"
        and bool(evidence.get("restore_token"))
        and bool(evidence.get("transport"))
        and bool(previous_transport)
        and isinstance(backup_enabled, bool)
        and evidence.get("cleanup_status") == "success"
        and evidence.get("cleanup_transport") == previous_transport
        and evidence.get("cleanup_backup_enabled") is backup_enabled
        and evidence.get("package") == package
        and evidence.get("transport") == transport
    )


def _read_layout_observation(value: object, resources: StateResourceIds) -> dict[str, str | None]:
    if isinstance(value, str):
        data = json.loads(value)
    else:
        data = value
    if isinstance(data, Mapping):
        # Direct snapshots make deterministic unit tests and non-UI adapters
        # possible while retaining layout-json compatibility.
        return {
            "sentinel": _optional_text(data.get("sentinel")),
            "schema_version": _optional_text(data.get("schema_version")),
            "revision": _optional_text(data.get("revision")),
            "migration_status": _optional_text(data.get("migration_status")),
        }
    if not isinstance(data, list):
        raise TypeError("state observation must be a layout array or object")
    values: dict[str, str | None] = {}
    resource_names = {
        resources.sentinel: "sentinel",
        resources.schema_version: "schema_version",
        resources.revision: "revision",
        resources.migration_status: "migration_status",
    }
    for item in data:
        if not isinstance(item, Mapping):
            continue
        resource = str(item.get("resource-id", "")).rsplit("/", 1)[-1]
        key = resource_names.get(resource)
        if key is not None:
            raw = item.get("text")
            values[key] = raw if isinstance(raw, str) else None
    return {key: values.get(key) for key in ("sentinel", "schema_version", "revision", "migration_status")}


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return value if isinstance(value, str) else str(value)


def _snapshot_matches(observation: Mapping[str, str | None], expected: StateSnapshot) -> bool:
    return observation == {
        "sentinel": expected.sentinel,
        "schema_version": str(expected.schema_version),
        "revision": str(expected.revision),
        "migration_status": expected.migration_status,
    }


def judge_state_evolution(
    *,
    contract: StateEvolutionFixtureContract,
    initial_state: object,
    rotated_state: object,
    process_restored_state: object,
    backup_restored_state: object,
    process_event: Mapping[str, Any],
    backup_event: Mapping[str, Any],
    execution_identity: Mapping[str, Any] | None,
    state_loss_evidence: Mapping[str, Any] | None = None,
    crash_detected: bool = False,
) -> dict[str, Any]:
    """Classify one accountable local state replay, failing closed on gaps."""

    base = {
        "schema_version": 1,
        "oracle": "m8-state-evolution-v1",
        "claim_boundary": "local fixture, recorded recovery epoch, and bound execution identity only",
    }
    try:
        observations = {
            "initial": _read_layout_observation(initial_state, contract.resources),
            "rotation": _read_layout_observation(rotated_state, contract.resources),
            "process_death": _read_layout_observation(process_restored_state, contract.resources),
            "backup_restore": _read_layout_observation(backup_restored_state, contract.resources),
        }
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        return {
            **base,
            "conclusion": "non_accountable",
            "classification": "inconclusive",
            "reason": "state_observation_missing_or_invalid",
            "accountable": False,
            "observations": {},
            "evidence_error": f"{type(error).__name__}: {error}",
        }

    identity_ok = _execution_identity_matches(contract, execution_identity)
    process_ok = _process_event_accountable(process_event, contract.package)
    backup_ok = _backup_event_accountable(
        backup_event,
        contract.package,
        contract.recovery.transport,
    )
    events_ok = identity_ok and process_ok and backup_ok
    old_exact = all(_snapshot_matches(observations[name], contract.old_state) for name in ("initial", "rotation", "process_death"))
    missing = any(value is None for observation in observations.values() for value in observation.values())
    if not events_ok:
        reason = "execution_identity_missing_or_contradictory"
        if identity_ok and not process_ok:
            reason = "process_identity_missing_or_unchanged"
        elif identity_ok and process_ok and not backup_ok:
            reason = "backup_restore_evidence_missing_or_failed"
        return {
            **base,
            "conclusion": "non_accountable",
            "classification": "inconclusive",
            "reason": reason,
            "accountable": False,
            "observations": observations,
        }
    if crash_detected:
        return {
            **base,
            "conclusion": "locally_rejected",
            "classification": "crash",
            "reason": "crash_detected_during_recovery_epoch",
            "accountable": True,
            "observations": observations,
        }
    if missing:
        explicit_loss = isinstance(state_loss_evidence, Mapping) and (
            state_loss_evidence.get("status") == "passed"
            and state_loss_evidence.get("loss_confirmed") is True
            and isinstance(state_loss_evidence.get("boundary"), str)
            and bool(state_loss_evidence.get("boundary", "").strip())
            and isinstance(state_loss_evidence.get("reason"), str)
            and bool(state_loss_evidence.get("reason", "").strip())
        )
        if explicit_loss:
            return {
                **base,
                "conclusion": "locally_rejected",
                "classification": "state_loss",
                "reason": "required_state_missing_with_explicit_loss_evidence",
                "accountable": True,
                "observations": observations,
            }
        return {
            **base,
            "conclusion": "non_accountable",
            "classification": "inconclusive",
            "reason": "required_state_observation_missing_without_explicit_loss_evidence",
            "accountable": False,
            "observations": observations,
        }
    if not old_exact:
        return {
            **base,
            "conclusion": "non_accountable",
            "classification": "inconclusive",
            "reason": "old_state_seed_or_recovery_observation_is_contradictory",
            "accountable": False,
            "observations": observations,
        }
    restored = observations["backup_restore"]
    if _snapshot_matches(restored, contract.current_state):
        conclusion = "locally_supported"
        classification = "correct_restoration"
        reason = "state_continuity_and_single_schema_migration_observed"
        accountable = True
    elif restored.get("sentinel") == "UNINITIALIZED":
        conclusion = "locally_rejected"
        classification = "silent_reset"
        reason = "restored_state_matches_known_defaults"
        accountable = True
    elif _snapshot_matches(restored, contract.old_state):
        conclusion = "locally_rejected"
        classification = "stale_state"
        reason = "restored_state_remains_at_pre_migration_version"
        accountable = True
    else:
        conclusion = "non_accountable"
        classification = "inconclusive"
        reason = "state_outcome_unclassified"
        accountable = False
    return {
        **base,
        "conclusion": conclusion,
        "classification": classification,
        "reason": reason,
        "accountable": accountable,
        "observations": observations,
    }


__all__ = [
    "DurableStateContract",
    "MigrationEdge",
    "ProvenanceVerification",
    "RecoveryBoundary",
    "RuntimeEvidenceCheck",
    "RuntimePhaseReceipt",
    "RuntimeStep",
    "StateEvolutionContext",
    "StateEvolutionContract",
    "StateEvolutionContractError",
    "StateEvolutionFixtureContract",
    "StateEvolutionRuntimeAdapter",
    "StateInvariant",
    "StateReplayReceipt",
    "StateResourceIds",
    "StateSnapshot",
    "judge_state_evolution",
    "load_state_evolution_context",
    "load_state_evolution_contract",
    "load_state_evolution_schema",
    "self_validate_state_evolution_schema",
    "validate_state_evolution_context",
    "verify_change_target_diff",
    "verify_state_context_provenance",
    "verify_state_evolution_matched_pair",
    "verify_state_evolution_provenance",
]
