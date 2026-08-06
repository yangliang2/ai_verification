"""Strict M9 Attack Plan synthesis, admission, and neutral compilation.

The planner boundary is deliberately above the runner.  A planner may propose
an executable attack shape, but it cannot execute it, evaluate a result, or
receive a cohort label.  Every material proposal element is bound to a known
context fact and/or the one approved operator supplied by the caller.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aiverify.discovery.contracts import (
    AdmissionResult,
    AttackOperator,
    AttackPlan,
    RiskHypothesis,
    admit_attack_plan,
)
from aiverify.discovery.models import (
    DiscoveryContractError,
    ProjectTarget,
    QualityContextGraph,
)
from aiverify.runner.run_spec import (
    RunSpec,
    ScenarioSpec,
    SystemEventSpec,
    SUPPORTED_SYSTEM_EVENTS,
    parse_run_spec,
)


ATTACK_PLANNER_ROLE_ID = "verification-agent-attack-planner-v1"
ATTACK_PLAN_SCHEMA_VERSION = 1
_ELEMENT_KINDS = frozenset(
    {
        "trigger",
        "action",
        "user_intent",
        "system_event",
        "observation",
        "evidence_expectation",
    }
)
_LEAKAGE_TERMS = frozenset(
    {
        "hidden",
        "mapping",
        "holdout",
        "cohort",
        "expected",
        "outcome",
        "verdict",
        "finding",
        "defect",
        "control",
        "journey",
        "scenario",
    }
)
_DIGEST_RE = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _version(value: object, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value != 1:
        raise DiscoveryContractError(f"unsupported {field} schema_version")


def _digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise DiscoveryContractError("attack planner value is not canonical JSON") from error
    return hashlib.sha256(encoded).hexdigest()


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and bool(_DIGEST_RE.fullmatch(value))


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    return value


def _list(data: Mapping[str, Any], field: str, label: str) -> tuple[Any, ...]:
    value = data[field]
    if not isinstance(value, list):
        raise DiscoveryContractError(f"{label} {field} must be an array")
    return tuple(value)


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(f"unknown {label} field(s): " + ", ".join(unknown))


def _text_values(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_text_values(key))
            result.extend(_text_values(item))
        return tuple(result)
    if isinstance(value, (list, tuple, set, frozenset)):
        result = []
        for item in value:
            result.extend(_text_values(item))
        return tuple(result)
    return ()


def _leakage_terms(value: object) -> tuple[str, ...]:
    found = set()
    for text in _text_values(value):
        lowered = text.lower()
        for term in _LEAKAGE_TERMS:
            if re.search(rf"\b{re.escape(term)}\b", lowered):
                found.add(term)
    return tuple(sorted(found))


@dataclass(frozen=True)
class PlannerIdentity:
    """Requested/effective identity for one bounded planner invocation."""

    backend: str
    requested_model: str
    effective_model: str
    invocation_id: str
    identity_sha256: str | None = None
    role: str = ATTACK_PLANNER_ROLE_ID
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in ("backend", "requested_model", "effective_model", "invocation_id", "role"):
            _required_text(getattr(self, field), field)
        _version(self.schema_version, "planner identity")
        expected = _digest(
            {
                "backend": self.backend,
                "effective_model": self.effective_model,
                "invocation_id": self.invocation_id,
                "requested_model": self.requested_model,
                "role": self.role,
            }
        )
        if self.identity_sha256 is None:
            object.__setattr__(self, "identity_sha256", expected)
        elif self.identity_sha256 != expected or not _is_digest(self.identity_sha256):
            raise DiscoveryContractError("planner identity digest does not match")

    @classmethod
    def capture(
        cls,
        *,
        backend: str,
        requested_model: str,
        effective_model: str,
        invocation_id: str,
        role: str = ATTACK_PLANNER_ROLE_ID,
    ) -> "PlannerIdentity":
        return cls(
            backend=backend,
            requested_model=requested_model,
            effective_model=effective_model,
            invocation_id=invocation_id,
            role=role,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "role": self.role,
            "backend": self.backend,
            "requested_model": self.requested_model,
            "effective_model": self.effective_model,
            "invocation_id": self.invocation_id,
            "identity_sha256": self.identity_sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlannerIdentity":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("planner identity must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "role",
                "backend",
                "requested_model",
                "effective_model",
                "invocation_id",
                "identity_sha256",
            },
            "planner identity",
        )
        try:
            return cls(
                backend=data["backend"],
                requested_model=data["requested_model"],
                effective_model=data["effective_model"],
                invocation_id=data["invocation_id"],
                identity_sha256=data.get("identity_sha256"),
                role=data.get("role", ATTACK_PLANNER_ROLE_ID),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"planner identity requires {error.args[0]}") from error


@dataclass(frozen=True)
class ValidatedEvidenceRef:
    """An immutable, already-validated build/package/launch receipt reference."""

    ref: str
    kind: str
    sha256: str
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.ref, "evidence ref")
        _required_text(self.kind, "evidence kind")
        if not _is_digest(self.sha256):
            raise DiscoveryContractError("evidence ref sha256 must be a lowercase SHA-256 digest")
        _version(self.schema_version, "validated evidence ref")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ref": self.ref,
            "kind": self.kind,
            "sha256": self.sha256,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ValidatedEvidenceRef":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("validated evidence ref must be an object")
        _reject_unknown(data, {"schema_version", "ref", "kind", "sha256"}, "validated evidence ref")
        try:
            return cls(
                ref=data["ref"],
                kind=data["kind"],
                sha256=data["sha256"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"validated evidence ref requires {error.args[0]}"
            ) from error


@dataclass(frozen=True)
class AttackPlanGenerationRequest:
    """The only context admitted to the Attack Planner."""

    request_id: str
    target: ProjectTarget
    graph: QualityContextGraph
    hypothesis: RiskHypothesis
    operator: AttackOperator
    approved_operators: tuple[AttackOperator, ...]
    controllability_fact_ids: tuple[str, ...]
    validated_evidence: tuple[ValidatedEvidenceRef, ...]
    budget: int
    safety_boundary: str
    claim_boundary: str
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.request_id, "planner request_id")
        if not isinstance(self.target, ProjectTarget):
            raise DiscoveryContractError("attack planning requires ProjectTarget")
        if not isinstance(self.graph, QualityContextGraph):
            raise DiscoveryContractError("attack planning requires QualityContextGraph")
        if not isinstance(self.hypothesis, RiskHypothesis):
            raise DiscoveryContractError("attack planning requires RiskHypothesis")
        if not isinstance(self.operator, AttackOperator):
            raise DiscoveryContractError("attack planning requires AttackOperator")
        if self.graph.target_id != self.target.target_id:
            raise DiscoveryContractError("planner graph target does not match ProjectTarget")
        if self.hypothesis.target_id != self.target.target_id:
            raise DiscoveryContractError("planner hypothesis target does not match ProjectTarget")
        if self.hypothesis.status != "frozen":
            raise DiscoveryContractError("planner requires a frozen hypothesis")
        if self.graph.source_origin != self.target.source_origin or self.graph.source_commit != self.target.source_commit:
            raise DiscoveryContractError("planner graph source identity does not match target")
        if self.graph.source_tree_sha256 is None:
            raise DiscoveryContractError("planner graph source tree identity is required")
        if not isinstance(self.approved_operators, tuple) or not self.approved_operators:
            raise DiscoveryContractError("planner approved operator registry must not be empty")
        if any(not isinstance(item, AttackOperator) for item in self.approved_operators):
            raise DiscoveryContractError("planner approved operator registry is invalid")
        if self.operator.operator_id not in {item.operator_id for item in self.approved_operators}:
            raise DiscoveryContractError("planner operator is not in approved registry")
        _text_tuple(self.controllability_fact_ids, "controllability fact ids", allow_empty=False)
        _text_tuple(self.controllability_fact_ids, "controllability fact ids")
        if not isinstance(self.validated_evidence, tuple) or not self.validated_evidence:
            raise DiscoveryContractError("planner requires validated build/package evidence")
        if any(not isinstance(item, ValidatedEvidenceRef) for item in self.validated_evidence):
            raise DiscoveryContractError("planner validated evidence is invalid")
        evidence_kinds = {item.kind for item in self.validated_evidence}
        missing_kinds = {"build", "package", "launch", "controllability"} - evidence_kinds
        if missing_kinds:
            raise DiscoveryContractError(
                "planner requires validated build/package/launch/controllability evidence: "
                + ", ".join(sorted(missing_kinds))
            )
        if not isinstance(self.budget, int) or isinstance(self.budget, bool) or self.budget < 1:
            raise DiscoveryContractError("planner budget must be a positive integer")
        _required_text(self.safety_boundary, "planner safety boundary")
        _required_text(self.claim_boundary, "planner claim boundary")
        _version(self.schema_version, "attack planning request")
        facts = {fact.fact_id: fact for fact in self.graph.facts}
        for fact_id in (*self.hypothesis.supporting_fact_ids, *self.controllability_fact_ids):
            fact = facts.get(fact_id)
            if fact is None or fact.status != "known" or not fact.provenance:
                raise DiscoveryContractError(f"planner requires known provenance-bound fact: {fact_id}")
        leakage = _leakage_terms(self.to_dict())
        if leakage:
            raise DiscoveryContractError("planner request contains leakage: " + ", ".join(leakage))

    @property
    def graph_sha256(self) -> str:
        return _digest(self.graph.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "target": self.target.to_dict(),
            "graph": self.graph.to_dict(),
            "hypothesis": self.hypothesis.to_dict(),
            "operator": self.operator.to_dict(),
            "approved_operators": [item.to_dict() for item in self.approved_operators],
            "controllability_fact_ids": list(self.controllability_fact_ids),
            "validated_evidence": [item.to_dict() for item in self.validated_evidence],
            "budget": self.budget,
            "safety_boundary": self.safety_boundary,
            "claim_boundary": self.claim_boundary,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackPlanGenerationRequest":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attack planning request must be an object")
        _reject_unknown(
            data,
            {
                "schema_version",
                "request_id",
                "target",
                "graph",
                "hypothesis",
                "operator",
                "approved_operators",
                "controllability_fact_ids",
                "validated_evidence",
                "budget",
                "safety_boundary",
                "claim_boundary",
            },
            "attack planning request",
        )
        try:
            return cls(
                request_id=data["request_id"],
                target=ProjectTarget.from_dict(data["target"]),
                graph=QualityContextGraph.from_dict(data["graph"]),
                hypothesis=RiskHypothesis.from_dict(data["hypothesis"]),
                operator=AttackOperator.from_dict(data["operator"]),
                approved_operators=tuple(
                    AttackOperator.from_dict(item) for item in _list(data, "approved_operators", "planner request")
                ),
                controllability_fact_ids=tuple(_list(data, "controllability_fact_ids", "planner request")),
                validated_evidence=tuple(
                    ValidatedEvidenceRef.from_dict(item)
                    for item in _list(data, "validated_evidence", "planner request")
                ),
                budget=data["budget"],
                safety_boundary=data["safety_boundary"],
                claim_boundary=data["claim_boundary"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"planner request requires {error.args[0]}") from error


@dataclass(frozen=True)
class PlanElement:
    """One ordered material element with explicit source/operator lineage."""

    element_id: str
    kind: str
    text: str
    fact_ids: tuple[str, ...]
    operator_id: str | None = None
    order: int = 0
    event: str | None = None
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.element_id, "plan element_id")
        if self.kind not in _ELEMENT_KINDS:
            raise DiscoveryContractError("invalid attack plan element kind")
        _required_text(self.text, "plan element text")
        _text_tuple(self.fact_ids, "plan element fact_ids", allow_empty=False)
        if self.operator_id is not None:
            _required_text(self.operator_id, "plan element operator_id")
        if not isinstance(self.order, int) or isinstance(self.order, bool) or self.order < 0:
            raise DiscoveryContractError("plan element order must be a non-negative integer")
        if self.kind == "system_event":
            if self.event not in SUPPORTED_SYSTEM_EVENTS:
                raise DiscoveryContractError("system event element must name a supported event")
        elif self.event is not None:
            raise DiscoveryContractError("only system event elements may carry event")
        _version(self.schema_version, "plan element")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": self.schema_version,
            "element_id": self.element_id,
            "kind": self.kind,
            "text": self.text,
            "fact_ids": list(self.fact_ids),
            "operator_id": self.operator_id,
            "order": self.order,
        }
        if self.event is not None:
            result["event"] = self.event
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PlanElement":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("plan element must be an object")
        _reject_unknown(
            data,
            {"schema_version", "element_id", "kind", "text", "fact_ids", "operator_id", "order", "event"},
            "plan element",
        )
        try:
            return cls(
                element_id=data["element_id"],
                kind=data["kind"],
                text=data["text"],
                fact_ids=tuple(_list(data, "fact_ids", "plan element")),
                operator_id=data.get("operator_id"),
                order=data.get("order", 0),
                event=data.get("event"),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"plan element requires {error.args[0]}") from error


@dataclass(frozen=True)
class OracleContract:
    """Machine-checkable inputs only; it intentionally has no expected result."""

    oracle_id: str
    input_element_ids: tuple[str, ...]
    machine_check: str
    evidence_refs: tuple[str, ...]
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.oracle_id, "oracle_id")
        _text_tuple(self.input_element_ids, "oracle input element ids", allow_empty=False)
        _required_text(self.machine_check, "oracle machine check")
        _text_tuple(self.evidence_refs, "oracle evidence refs", allow_empty=False)
        _version(self.schema_version, "oracle contract")
        if _leakage_terms(self.to_dict()):
            raise DiscoveryContractError("oracle contract contains outcome leakage")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "oracle_id": self.oracle_id,
            "input_element_ids": list(self.input_element_ids),
            "machine_check": self.machine_check,
            "evidence_refs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OracleContract":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("oracle contract must be an object")
        _reject_unknown(
            data,
            {"schema_version", "oracle_id", "input_element_ids", "machine_check", "evidence_refs"},
            "oracle contract",
        )
        try:
            return cls(
                oracle_id=data["oracle_id"],
                input_element_ids=tuple(_list(data, "input_element_ids", "oracle contract")),
                machine_check=data["machine_check"],
                evidence_refs=tuple(_list(data, "evidence_refs", "oracle contract")),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"oracle contract requires {error.args[0]}") from error


@dataclass(frozen=True)
class AttackPlanProposal:
    """Strict planner output before deterministic admission."""

    plan_id: str
    target_id: str
    hypothesis_id: str
    operator_id: str
    trigger: PlanElement
    actions: tuple[PlanElement, ...]
    observations: tuple[PlanElement, ...]
    evidence_expectations: tuple[PlanElement, ...]
    oracle: OracleContract
    fixture_refs: tuple[str, ...]
    abort_boundary: str
    safety_boundary: str
    claim_boundary: str
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for field in ("plan_id", "target_id", "hypothesis_id", "operator_id"):
            _required_text(getattr(self, field), field)
        if not isinstance(self.trigger, PlanElement) or self.trigger.kind != "trigger":
            raise DiscoveryContractError("attack plan requires a trigger element")
        for field in ("actions", "observations", "evidence_expectations"):
            values = getattr(self, field)
            if not isinstance(values, tuple) or not values:
                raise DiscoveryContractError(f"attack plan {field} must not be empty")
            if any(not isinstance(item, PlanElement) for item in values):
                raise DiscoveryContractError(f"attack plan {field} contains invalid elements")
        if any(item.kind not in {"action", "user_intent", "system_event"} for item in self.actions):
            raise DiscoveryContractError("attack plan actions contain a non-action element")
        if any(item.kind != "observation" for item in self.observations):
            raise DiscoveryContractError("attack plan observations contain a non-observation element")
        if any(item.kind != "evidence_expectation" for item in self.evidence_expectations):
            raise DiscoveryContractError("attack plan evidence expectations contain a non-evidence element")
        if not isinstance(self.oracle, OracleContract):
            raise DiscoveryContractError("attack plan oracle contract is invalid")
        _text_tuple(self.fixture_refs, "attack plan fixture refs", allow_empty=False)
        for field in ("abort_boundary", "safety_boundary", "claim_boundary"):
            _required_text(getattr(self, field), field)
        ids = [self.trigger.element_id]
        ids.extend(item.element_id for item in (*self.actions, *self.observations, *self.evidence_expectations))
        if len(ids) != len(set(ids)):
            raise DiscoveryContractError("attack plan element ids must be unique")
        all_elements = (self.trigger, *self.actions, *self.observations, *self.evidence_expectations)
        if any(item.order != index for index, item in enumerate(sorted(all_elements, key=lambda item: item.order))):
            raise DiscoveryContractError("attack plan element order must be contiguous")
        if not set(self.oracle.input_element_ids).issubset(set(ids)):
            raise DiscoveryContractError("oracle references an unknown plan element")
        if _leakage_terms(self.to_dict()):
            raise DiscoveryContractError("attack plan proposal contains formal outcome leakage")
        _version(self.schema_version, "attack plan proposal")

    @property
    def material_elements(self) -> tuple[PlanElement, ...]:
        return (self.trigger, *self.actions, *self.observations, *self.evidence_expectations)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "target_id": self.target_id,
            "hypothesis_id": self.hypothesis_id,
            "operator_id": self.operator_id,
            "trigger": self.trigger.to_dict(),
            "actions": [item.to_dict() for item in self.actions],
            "observations": [item.to_dict() for item in self.observations],
            "evidence_expectations": [item.to_dict() for item in self.evidence_expectations],
            "oracle": self.oracle.to_dict(),
            "fixture_refs": list(self.fixture_refs),
            "abort_boundary": self.abort_boundary,
            "safety_boundary": self.safety_boundary,
            "claim_boundary": self.claim_boundary,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackPlanProposal":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attack plan proposal must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "plan_id", "target_id", "hypothesis_id", "operator_id",
                "trigger", "actions", "observations", "evidence_expectations", "oracle",
                "fixture_refs", "abort_boundary", "safety_boundary", "claim_boundary",
            },
            "attack plan proposal",
        )
        try:
            return cls(
                plan_id=data["plan_id"],
                target_id=data["target_id"],
                hypothesis_id=data["hypothesis_id"],
                operator_id=data["operator_id"],
                trigger=PlanElement.from_dict(data["trigger"]),
                actions=tuple(PlanElement.from_dict(item) for item in _list(data, "actions", "attack plan proposal")),
                observations=tuple(PlanElement.from_dict(item) for item in _list(data, "observations", "attack plan proposal")),
                evidence_expectations=tuple(
                    PlanElement.from_dict(item)
                    for item in _list(data, "evidence_expectations", "attack plan proposal")
                ),
                oracle=OracleContract.from_dict(data["oracle"]),
                fixture_refs=tuple(_list(data, "fixture_refs", "attack plan proposal")),
                abort_boundary=data["abort_boundary"],
                safety_boundary=data["safety_boundary"],
                claim_boundary=data["claim_boundary"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"attack plan proposal requires {error.args[0]}") from error


@dataclass(frozen=True)
class AttackPlanAdmission:
    """Side-effect-free, typed admission result."""

    status: str
    reasons: tuple[str, ...] = ()
    proposal: AttackPlanProposal | None = None
    plan: AttackPlan | None = None
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in {"admitted", "rejected"}:
            raise DiscoveryContractError("attack plan admission status is invalid")
        _text_tuple(self.reasons, "attack plan admission reasons")
        if self.status == "admitted":
            if self.reasons or self.proposal is None or self.plan is None:
                raise DiscoveryContractError("admitted attack plan requires proposal and plan")
        elif not self.reasons or self.proposal is not None or self.plan is not None:
            raise DiscoveryContractError("rejected attack plan must contain reasons only")
        _version(self.schema_version, "attack plan admission")

    @property
    def admitted(self) -> bool:
        return self.status == "admitted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "reasons": list(self.reasons),
            "proposal": self.proposal.to_dict() if self.proposal is not None else None,
            "plan": self.plan.to_dict() if self.plan is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackPlanAdmission":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attack plan admission must be an object")
        _reject_unknown(data, {"schema_version", "status", "reasons", "proposal", "plan"}, "attack plan admission")
        try:
            raw_proposal = data.get("proposal")
            raw_plan = data.get("plan")
            if raw_proposal is not None and not isinstance(raw_proposal, Mapping):
                raise DiscoveryContractError("attack plan admission proposal must be an object or null")
            if raw_plan is not None and not isinstance(raw_plan, Mapping):
                raise DiscoveryContractError("attack plan admission plan must be an object or null")
            return cls(
                status=data["status"],
                reasons=tuple(_list(data, "reasons", "attack plan admission")),
                proposal=AttackPlanProposal.from_dict(raw_proposal) if raw_proposal is not None else None,
                plan=AttackPlan.from_dict(raw_plan) if raw_plan is not None else None,
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"attack plan admission requires {error.args[0]}") from error


def validate_attack_plan_proposal(
    proposal: AttackPlanProposal,
    request: AttackPlanGenerationRequest,
) -> tuple[str, ...]:
    """Return deterministic rejection reasons without performing side effects."""

    reasons: list[str] = []
    if not isinstance(proposal, AttackPlanProposal):
        return ("attack plan proposal contract is invalid",)
    if proposal.target_id != request.target.target_id:
        reasons.append("attack plan target does not match ProjectTarget")
    if proposal.hypothesis_id != request.hypothesis.hypothesis_id:
        reasons.append("attack plan hypothesis does not match frozen hypothesis")
    approved = {item.operator_id for item in request.approved_operators}
    if proposal.operator_id not in approved:
        reasons.append("attack plan operator is not in approved operator registry")
    if proposal.operator_id != request.operator.operator_id:
        reasons.append("attack plan operator does not match selected operator")
    facts = {fact.fact_id: fact for fact in request.graph.facts}
    known_fact_ids = set(facts)
    if request.hypothesis.supporting_fact_ids and not set(request.hypothesis.supporting_fact_ids).issubset(known_fact_ids):
        reasons.append("frozen hypothesis references a missing context fact")
    for element in proposal.material_elements:
        if not set(element.fact_ids).issubset(known_fact_ids):
            reasons.append(f"element {element.element_id} references a fabricated fact")
        for fact_id in element.fact_ids:
            fact = facts.get(fact_id)
            if fact is None or fact.status != "known" or not fact.provenance:
                reasons.append(f"element {element.element_id} lacks a known provenance-bound fact")
        if element.kind in {"action", "system_event"} and element.operator_id != proposal.operator_id:
            reasons.append(f"element {element.element_id} uses a disallowed operator")
        if not element.fact_ids and element.operator_id is None:
            reasons.append(f"element {element.element_id} has no source/operator lineage")
    for ref in proposal.oracle.evidence_refs:
        if ref not in {item.ref for item in request.validated_evidence}:
            reasons.append(f"oracle references unvalidated evidence: {ref}")
    observation_ids = {item.element_id for item in proposal.observations}
    evidence_ids = {item.element_id for item in proposal.evidence_expectations}
    oracle_inputs = set(proposal.oracle.input_element_ids)
    if not observation_ids.issubset(oracle_inputs):
        reasons.append("oracle does not cover every declared observation")
    if not evidence_ids.issubset(oracle_inputs):
        reasons.append("oracle does not cover every evidence expectation")
    if not set(request.controllability_fact_ids).issubset(known_fact_ids):
        reasons.append("planner controllability evidence references a missing fact")
    if len(proposal.actions) + len(proposal.observations) > request.budget:
        reasons.append("attack plan exceeds bounded planner budget")
    if proposal.safety_boundary != request.safety_boundary:
        reasons.append("attack plan safety boundary drifted from request")
    if proposal.claim_boundary != request.claim_boundary:
        reasons.append("attack plan claim boundary drifted from request")
    try:
        legacy = _legacy_attack_plan(proposal)
        admission = admit_attack_plan(legacy, request.hypothesis, request.graph)
        if not admission.admitted:
            reasons.extend(admission.errors)
    except DiscoveryContractError as error:
        reasons.append(str(error))
    return tuple(dict.fromkeys(reasons))


def _legacy_attack_plan(proposal: AttackPlanProposal, *, status: str = "frozen") -> AttackPlan:
    return AttackPlan(
        plan_id=proposal.plan_id,
        target_id=proposal.target_id,
        hypothesis_id=proposal.hypothesis_id,
        operator_id=proposal.operator_id,
        trigger=proposal.trigger.text,
        observations=tuple(item.text for item in proposal.observations),
        evidence_expectations=tuple(item.text for item in proposal.evidence_expectations),
        oracle=proposal.oracle.oracle_id,
        abort_boundary=proposal.abort_boundary,
        claim_boundary=proposal.claim_boundary,
        fixture_refs=proposal.fixture_refs,
        status=status,
    )


def admit_attack_plan_proposal(
    proposal: AttackPlanProposal,
    request: AttackPlanGenerationRequest,
) -> AttackPlanAdmission:
    """Admit a proposal before build, device, agent, or runtime effects."""

    reasons = validate_attack_plan_proposal(proposal, request)
    if reasons:
        return AttackPlanAdmission(status="rejected", reasons=reasons)
    return AttackPlanAdmission(
        status="admitted",
        proposal=proposal,
        plan=_legacy_attack_plan(proposal, status="admitted"),
    )


AttackPlannerBackend = Callable[[AttackPlanGenerationRequest], Mapping[str, Any]]


@dataclass(frozen=True)
class AttackPlanGenerationResult:
    """Captured planner output and its admission decision."""

    request_id: str
    target_id: str
    planner_identity: PlannerIdentity
    authoritative_output_sha256: str
    admission: AttackPlanAdmission
    status: str
    rejection_reasons: tuple[str, ...] = ()
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.request_id, "planner result request_id")
        _required_text(self.target_id, "planner result target_id")
        if not isinstance(self.planner_identity, PlannerIdentity):
            raise DiscoveryContractError("planner result identity is invalid")
        if not _is_digest(self.authoritative_output_sha256):
            raise DiscoveryContractError("planner result output digest is invalid")
        if not isinstance(self.admission, AttackPlanAdmission):
            raise DiscoveryContractError("planner result admission is invalid")
        if self.status not in {"admitted", "rejected"}:
            raise DiscoveryContractError("planner result status is invalid")
        _text_tuple(self.rejection_reasons, "planner result rejection reasons")
        if self.status == "admitted" and not self.admission.admitted:
            raise DiscoveryContractError("admitted planner result has rejected admission")
        if self.status == "rejected" and not self.rejection_reasons:
            raise DiscoveryContractError("rejected planner result requires reasons")
        _version(self.schema_version, "planner result")

    @property
    def admitted(self) -> bool:
        return self.status == "admitted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "target_id": self.target_id,
            "planner_identity": self.planner_identity.to_dict(),
            "authoritative_output_sha256": self.authoritative_output_sha256,
            "admission": self.admission.to_dict(),
            "status": self.status,
            "rejection_reasons": list(self.rejection_reasons),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "AttackPlanGenerationResult":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("attack plan generation result must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "request_id", "target_id", "planner_identity",
                "authoritative_output_sha256", "admission", "status", "rejection_reasons",
            },
            "attack plan generation result",
        )
        try:
            return cls(
                request_id=data["request_id"],
                target_id=data["target_id"],
                planner_identity=PlannerIdentity.from_dict(data["planner_identity"]),
                authoritative_output_sha256=data["authoritative_output_sha256"],
                admission=AttackPlanAdmission.from_dict(data["admission"]),
                status=data["status"],
                rejection_reasons=tuple(_list(data, "rejection_reasons", "attack plan generation result")),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(
                f"attack plan generation result requires {error.args[0]}"
            ) from error


def generate_attack_plan(
    request: AttackPlanGenerationRequest,
    backend: AttackPlannerBackend,
    identity: PlannerIdentity,
) -> AttackPlanGenerationResult:
    """Invoke exactly one bounded planner and fail closed on malformed output."""

    if not isinstance(request, AttackPlanGenerationRequest):
        raise DiscoveryContractError("attack planning request is invalid")
    if not callable(backend):
        raise DiscoveryContractError("attack planner backend must be callable")
    if not isinstance(identity, PlannerIdentity):
        raise DiscoveryContractError("attack planner identity is invalid")
    try:
        raw = backend(request)
    except Exception as error:
        raise DiscoveryContractError(
            f"attack planner backend failed: {type(error).__name__}"
        ) from error
    raw_digest = _digest(raw)
    reasons: list[str] = []
    proposal: AttackPlanProposal | None = None
    if not isinstance(raw, Mapping):
        reasons.append("planner output must be an object")
    else:
        try:
            _reject_unknown(raw, {"schema_version", "proposal"}, "planner output")
            version = raw.get("schema_version", 1)
            if version != 1 or isinstance(version, bool):
                raise DiscoveryContractError("unsupported planner output schema_version")
            proposal = AttackPlanProposal.from_dict(raw["proposal"])
        except (DiscoveryContractError, KeyError, TypeError, ValueError) as error:
            reasons.append(f"planner output is malformed: {error}")
    if proposal is not None:
        admission = admit_attack_plan_proposal(proposal, request)
        if not admission.admitted:
            reasons.extend(admission.reasons)
        else:
            return AttackPlanGenerationResult(
                request_id=request.request_id,
                target_id=request.target.target_id,
                planner_identity=identity,
                authoritative_output_sha256=raw_digest,
                admission=admission,
                status="admitted",
            )
    rejected = AttackPlanAdmission(status="rejected", reasons=tuple(dict.fromkeys(reasons)))
    return AttackPlanGenerationResult(
        request_id=request.request_id,
        target_id=request.target.target_id,
        planner_identity=identity,
        authoritative_output_sha256=raw_digest,
        admission=rejected,
        status="rejected",
        rejection_reasons=tuple(dict.fromkeys(reasons)),
    )


generate_attack_plan_proposal = generate_attack_plan


@dataclass(frozen=True)
class CompiledAttackPlan:
    """Neutral scenario/run representation retaining the admitted semantics."""

    proposal: AttackPlanProposal
    plan: AttackPlan
    scenario: ScenarioSpec
    run_spec: RunSpec
    semantics_sha256: str
    schema_version: int = ATTACK_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.proposal, AttackPlanProposal):
            raise DiscoveryContractError("compiled proposal is invalid")
        if not isinstance(self.plan, AttackPlan) or self.plan.status != "admitted":
            raise DiscoveryContractError("compiled plan must be admitted")
        if not isinstance(self.scenario, ScenarioSpec) or not isinstance(self.run_spec, RunSpec):
            raise DiscoveryContractError("compiled attack plan requires ScenarioSpec and RunSpec")
        if self.run_spec.scenario != self.scenario:
            raise DiscoveryContractError("compiled RunSpec scenario drifted")
        if not _is_digest(self.semantics_sha256):
            raise DiscoveryContractError("compiled semantics digest is invalid")
        _version(self.schema_version, "compiled attack plan")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal": self.proposal.to_dict(),
            "plan": self.plan.to_dict(),
            "scenario": _scenario_dict(self.scenario),
            "run_spec": {
                "host_project": str(self.run_spec.host_project),
                "apk_glob": self.run_spec.apk_glob,
                "package": self.run_spec.package,
                "activity": self.run_spec.activity,
            },
            "semantics_sha256": self.semantics_sha256,
        }


def compile_admitted_attack_plan(
    admission: AttackPlanAdmission,
    *,
    host_project: str | Path,
    apk_glob: str,
    package_name: str,
    activity: str | None,
    base_dir: Path | None = None,
) -> CompiledAttackPlan:
    """Compile only an admitted proposal into a neutral RunSpec, without running it."""

    if not isinstance(admission, AttackPlanAdmission) or not admission.admitted:
        raise DiscoveryContractError("only an admitted attack plan can be compiled")
    assert admission.proposal is not None
    assert admission.plan is not None
    proposal = admission.proposal
    ordered = sorted(proposal.material_elements, key=lambda item: item.order)
    user_elements = [item for item in ordered if item.kind in {"action", "user_intent"}]
    if not user_elements:
        raise DiscoveryContractError("admitted attack plan has no neutral user actions")
    user_actions = [item.text for item in user_elements]
    action_positions = {item.element_id: index for index, item in enumerate(user_elements)}
    events: list[SystemEventSpec] = []
    for element in ordered:
        if element.kind != "system_event":
            continue
        step_index = min(element.order, len(user_actions))
        if element.element_id in action_positions:
            step_index = action_positions[element.element_id]
        assert element.event is not None
        events.append(SystemEventSpec(step_index=step_index, event=element.event))
    scenario = ScenarioSpec(
        id=proposal.plan_id,
        user_actions=user_actions,
        system_events=events,
        assertions=[],
        expected_behavior="",
        l3_spec="",
    )
    data = {
        "host_project": str(host_project),
        "apk_glob": apk_glob,
        "package": package_name,
        "activity": activity,
        "scenario": _scenario_dict(scenario),
    }
    run_spec = parse_run_spec(data, base_dir=base_dir or Path.cwd())
    semantics = _digest(
        {
            "proposal": proposal.to_dict(),
            "plan": admission.plan.to_dict(),
            "scenario": _scenario_dict(scenario),
        }
    )
    return CompiledAttackPlan(
        proposal=proposal,
        plan=admission.plan,
        scenario=scenario,
        run_spec=run_spec,
        semantics_sha256=semantics,
    )


compile_attack_plan_proposal = compile_admitted_attack_plan


def _scenario_dict(scenario: ScenarioSpec) -> dict[str, Any]:
    return {
        "id": scenario.id,
        "user_actions": list(scenario.user_actions),
        "system_events": [
            {"step_index": event.step_index, "event": event.event, "args": dict(event.args)}
            for event in scenario.system_events
        ],
        "assertions": [],
    }


__all__ = [
    "ATTACK_PLAN_SCHEMA_VERSION",
    "ATTACK_PLANNER_ROLE_ID",
    "AttackPlanAdmission",
    "AttackPlanGenerationRequest",
    "AttackPlanGenerationResult",
    "AttackPlanProposal",
    "AttackPlannerBackend",
    "CompiledAttackPlan",
    "OracleContract",
    "PlanElement",
    "PlannerIdentity",
    "ValidatedEvidenceRef",
    "admit_attack_plan_proposal",
    "compile_admitted_attack_plan",
    "compile_attack_plan_proposal",
    "generate_attack_plan",
    "generate_attack_plan_proposal",
    "validate_attack_plan_proposal",
]
