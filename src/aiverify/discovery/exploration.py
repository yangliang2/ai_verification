"""Auditable, side-effect-free project exploration state machine.

This module is the campaign state machine for the M9 discovery boundary.  It
consumes a frozen ProjectTarget and HypothesisPortfolio, records every
decision/attempt/outcome as a hash-chained immutable event, and derives the
Project Risk Map and coverage frontier from that event stream.  It never builds,
installs, launches, drives a device, or mutates a source tree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from aiverify.discovery.campaign import AttemptEvidence
from aiverify.discovery.contracts import Finding, ProjectRiskMap, ResidualRisk
from aiverify.discovery.falsification_review import (
    FalsificationReviewResult,
    ImmutableArtifactRef,
)
from aiverify.discovery.hypothesis_portfolio import HypothesisPortfolio
from aiverify.discovery.models import DiscoveryContractError, ProjectTarget, QualityContextGraph


EXPLORATION_SCHEMA_VERSION = 1
EMPTY_EVENT_DIGEST = "0" * 64
CAMPAIGN_ARTIFACT_KIND = "campaign-artifact"
EVENT_TYPES = (
    "campaign_initialized",
    "hypothesis_decision",
    "attack_decision",
    "attempt_recorded",
    "finding_recorded",
    "residual_risk_recorded",
    "falsification_review_recorded",
    "stop_recorded",
)
STOP_REASONS = (
    "budget_exhausted",
    "no_admissible_attack",
    "terminal_finding",
    "evidence_gap",
    "frontier_exhausted",
    "policy_abort",
)
HYPOTHESIS_DECISIONS = ("selected", "deferred", "rejected")
ATTACK_DECISIONS = ("admitted", "rejected")
CAMPAIGN_STATUSES = ("created", "exploring", "stopped")


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DiscoveryContractError(f"{field} must be a non-empty string")
    return value


def _text_tuple(value: object, field: str, *, allow_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise DiscoveryContractError(f"{field} must be a tuple of strings")
    if not allow_empty and not value:
        raise DiscoveryContractError(f"{field} must not be empty")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DiscoveryContractError(f"{field} must contain non-empty strings")
    return value


def _is_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _canonical(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise DiscoveryContractError("exploration value is not canonical JSON") from error


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _stable_id(*parts: str) -> str:
    return _digest(list(parts))[:16]


def _list(data: Mapping[str, Any], field: str, label: str) -> tuple[Any, ...]:
    value = data[field]
    if not isinstance(value, list):
        raise DiscoveryContractError(f"{label} {field} must be an array")
    return tuple(value)


def _reject_unknown(data: Mapping[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise DiscoveryContractError(f"unknown {label} field(s): " + ", ".join(unknown))


def _artifact_refs(value: object, field: str = "artifact_refs") -> tuple[ImmutableArtifactRef, ...]:
    if not isinstance(value, (tuple, list)):
        raise DiscoveryContractError(f"{field} must be an array of immutable artifacts")
    refs = tuple(value)
    if not refs or any(not isinstance(item, ImmutableArtifactRef) for item in refs):
        raise DiscoveryContractError(f"{field} must contain immutable artifacts")
    if len({item.ref for item in refs}) != len(refs):
        raise DiscoveryContractError(f"{field} refs must be unique")
    return refs


def make_campaign_artifact(
    ref: str,
    kind: str,
    content: object,
) -> ImmutableArtifactRef:
    """Create a checksum-bound local artifact reference for a transition."""

    return ImmutableArtifactRef(ref=ref, kind=kind, sha256=_digest(content))


CampaignArtifactRef = ImmutableArtifactRef


@dataclass(frozen=True)
class ExplorationEvent:
    """One typed, provenance-bound, hash-chained campaign transition."""

    event_id: str
    sequence: int
    event_type: str
    target_id: str
    artifact_refs: tuple[ImmutableArtifactRef, ...]
    payload_json: str
    previous_digest: str
    event_digest: str
    hypothesis_id: str | None = None
    attempt_ref: str | None = None
    schema_version: int = EXPLORATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.event_id, "event_id")
        _required_text(self.target_id, "event target_id")
        if not isinstance(self.sequence, int) or isinstance(self.sequence, bool) or self.sequence < 1:
            raise DiscoveryContractError("event sequence must be a positive integer")
        if self.event_type not in EVENT_TYPES:
            raise DiscoveryContractError("unknown exploration event type")
        _artifact_refs(self.artifact_refs)
        if not isinstance(self.payload_json, str):
            raise DiscoveryContractError("event payload_json must be a string")
        try:
            payload = json.loads(self.payload_json)
        except json.JSONDecodeError as error:
            raise DiscoveryContractError("event payload_json is invalid JSON") from error
        if not isinstance(payload, dict):
            raise DiscoveryContractError("event payload must be an object")
        if not _is_digest(self.previous_digest) or not _is_digest(self.event_digest):
            raise DiscoveryContractError("event digests must be lowercase SHA-256")
        for field in ("hypothesis_id", "attempt_ref"):
            value = getattr(self, field)
            if value is not None:
                _required_text(value, f"event {field}")
        if self.schema_version != EXPLORATION_SCHEMA_VERSION:
            raise DiscoveryContractError("unsupported exploration event schema_version")
        expected = _event_digest(
            self.sequence,
            self.event_type,
            self.target_id,
            self.hypothesis_id,
            self.attempt_ref,
            self.artifact_refs,
            payload,
            self.previous_digest,
        )
        if self.event_digest != expected:
            raise DiscoveryContractError("exploration event digest does not match content")
        if self.event_id != "event-" + self.event_digest[:16]:
            raise DiscoveryContractError("exploration event id does not match digest")

    @classmethod
    def create(
        cls,
        *,
        sequence: int,
        event_type: str,
        target_id: str,
        artifact_refs: tuple[ImmutableArtifactRef, ...],
        payload: Mapping[str, Any],
        previous_digest: str,
        hypothesis_id: str | None = None,
        attempt_ref: str | None = None,
    ) -> "ExplorationEvent":
        _artifact_refs(artifact_refs)
        payload_json = _canonical(dict(payload))
        event_digest = _event_digest(
            sequence,
            event_type,
            target_id,
            hypothesis_id,
            attempt_ref,
            artifact_refs,
            dict(payload),
            previous_digest,
        )
        return cls(
            event_id="event-" + event_digest[:16],
            sequence=sequence,
            event_type=event_type,
            target_id=target_id,
            artifact_refs=artifact_refs,
            payload_json=payload_json,
            previous_digest=previous_digest,
            event_digest=event_digest,
            hypothesis_id=hypothesis_id,
            attempt_ref=attempt_ref,
        )

    @property
    def payload(self) -> dict[str, Any]:
        return json.loads(self.payload_json)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "event_type": self.event_type,
            "target_id": self.target_id,
            "hypothesis_id": self.hypothesis_id,
            "attempt_ref": self.attempt_ref,
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "payload": self.payload,
            "previous_digest": self.previous_digest,
            "event_digest": self.event_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExplorationEvent":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("exploration event must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "event_id", "sequence", "event_type", "target_id",
                "hypothesis_id", "attempt_ref", "artifact_refs", "payload",
                "previous_digest", "event_digest",
            },
            "exploration event",
        )
        try:
            payload = data["payload"]
            if not isinstance(payload, Mapping):
                raise DiscoveryContractError("exploration event payload must be an object")
            return cls(
                event_id=data["event_id"],
                sequence=data["sequence"],
                event_type=data["event_type"],
                target_id=data["target_id"],
                hypothesis_id=data.get("hypothesis_id"),
                attempt_ref=data.get("attempt_ref"),
                artifact_refs=tuple(
                    ImmutableArtifactRef.from_dict(item)
                    for item in _list(data, "artifact_refs", "exploration event")
                ),
                payload_json=_canonical(dict(payload)),
                previous_digest=data["previous_digest"],
                event_digest=data["event_digest"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"exploration event requires {error.args[0]}") from error


def _event_digest(
    sequence: int,
    event_type: str,
    target_id: str,
    hypothesis_id: str | None,
    attempt_ref: str | None,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
    payload: Mapping[str, Any],
    previous_digest: str,
) -> str:
    return _digest(
        {
            "sequence": sequence,
            "event_type": event_type,
            "target_id": target_id,
            "hypothesis_id": hypothesis_id,
            "attempt_ref": attempt_ref,
            "artifact_refs": [item.to_dict() for item in artifact_refs],
            "payload": dict(payload),
            "previous_digest": previous_digest,
        }
    )


@dataclass(frozen=True)
class ExplorationStop:
    """An explicit, evidence-backed terminal decision."""

    stop_id: str
    reason: str
    rationale: str
    evidence_refs: tuple[str, ...]
    artifact_refs: tuple[ImmutableArtifactRef, ...]
    decision_digest: str
    schema_version: int = EXPLORATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.stop_id, "stop_id")
        _required_text(self.rationale, "stop rationale")
        if self.reason not in STOP_REASONS:
            raise DiscoveryContractError("invalid exploration stop reason")
        _text_tuple(self.evidence_refs, "stop evidence_refs", allow_empty=False)
        _artifact_refs(self.artifact_refs)
        if not _is_digest(self.decision_digest):
            raise DiscoveryContractError("stop decision digest is invalid")
        expected = _digest(
            {
                "reason": self.reason,
                "rationale": self.rationale,
                "evidence_refs": list(self.evidence_refs),
                "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            }
        )
        if self.decision_digest != expected or self.stop_id != "stop-" + expected[:16]:
            raise DiscoveryContractError("stop decision digest does not match content")
        if self.schema_version != EXPLORATION_SCHEMA_VERSION:
            raise DiscoveryContractError("unsupported exploration stop schema_version")

    @classmethod
    def create(
        cls,
        *,
        reason: str,
        rationale: str,
        evidence_refs: tuple[str, ...],
        artifact_refs: tuple[ImmutableArtifactRef, ...],
    ) -> "ExplorationStop":
        decision_digest = _digest(
            {
                "reason": reason,
                "rationale": rationale,
                "evidence_refs": list(evidence_refs),
                "artifact_refs": [item.to_dict() for item in artifact_refs],
            }
        )
        return cls(
            stop_id="stop-" + decision_digest[:16],
            reason=reason,
            rationale=rationale,
            evidence_refs=evidence_refs,
            artifact_refs=artifact_refs,
            decision_digest=decision_digest,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "stop_id": self.stop_id,
            "reason": self.reason,
            "rationale": self.rationale,
            "evidence_refs": list(self.evidence_refs),
            "artifact_refs": [item.to_dict() for item in self.artifact_refs],
            "decision_digest": self.decision_digest,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExplorationStop":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("exploration stop must be an object")
        _reject_unknown(
            data,
            {"schema_version", "stop_id", "reason", "rationale", "evidence_refs", "artifact_refs", "decision_digest"},
            "exploration stop",
        )
        try:
            return cls(
                stop_id=data["stop_id"],
                reason=data["reason"],
                rationale=data["rationale"],
                evidence_refs=tuple(_list(data, "evidence_refs", "exploration stop")),
                artifact_refs=tuple(
                    ImmutableArtifactRef.from_dict(item)
                    for item in _list(data, "artifact_refs", "exploration stop")
                ),
                decision_digest=data["decision_digest"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"exploration stop requires {error.args[0]}") from error


@dataclass(frozen=True)
class NextProbe:
    """A deterministic ranking entry derived only from recorded campaign state."""

    hypothesis_id: str
    candidate_id: str
    priority_score: float
    admissible: bool
    reason: str
    attempt_count: int
    schema_version: int = EXPLORATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.hypothesis_id, "next probe hypothesis_id")
        _required_text(self.candidate_id, "next probe candidate_id")
        _required_text(self.reason, "next probe reason")
        if not isinstance(self.priority_score, (int, float)) or isinstance(self.priority_score, bool):
            raise DiscoveryContractError("next probe priority_score must be numeric")
        if not 0 <= self.priority_score <= 1:
            raise DiscoveryContractError("next probe priority_score must be between 0 and 1")
        if not isinstance(self.admissible, bool):
            raise DiscoveryContractError("next probe admissible must be boolean")
        if not isinstance(self.attempt_count, int) or isinstance(self.attempt_count, bool) or self.attempt_count < 0:
            raise DiscoveryContractError("next probe attempt_count must be non-negative")
        if self.schema_version != EXPLORATION_SCHEMA_VERSION:
            raise DiscoveryContractError("unsupported next probe schema_version")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "hypothesis_id": self.hypothesis_id,
            "candidate_id": self.candidate_id,
            "priority_score": self.priority_score,
            "admissible": self.admissible,
            "reason": self.reason,
            "attempt_count": self.attempt_count,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "NextProbe":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("next probe must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "hypothesis_id", "candidate_id", "priority_score",
                "admissible", "reason", "attempt_count",
            },
            "next probe",
        )
        try:
            return cls(
                hypothesis_id=data["hypothesis_id"],
                candidate_id=data["candidate_id"],
                priority_score=data["priority_score"],
                admissible=data["admissible"],
                reason=data["reason"],
                attempt_count=data["attempt_count"],
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"next probe requires {error.args[0]}") from error


@dataclass(frozen=True)
class ExplorationCampaign:
    """The complete immutable state of one ProjectTarget exploration."""

    campaign_id: str
    target: ProjectTarget
    context_graph: QualityContextGraph
    portfolio: HypothesisPortfolio
    events: tuple[ExplorationEvent, ...]
    attempts: tuple[AttemptEvidence, ...]
    findings: tuple[Finding, ...]
    residual_risks: tuple[ResidualRisk, ...]
    falsification_reviews: tuple[FalsificationReviewResult, ...]
    risk_map: ProjectRiskMap
    remaining_budget: int
    coverage_frontier: tuple[str, ...]
    status: str = "created"
    stop: ExplorationStop | None = None
    schema_version: int = EXPLORATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _required_text(self.campaign_id, "exploration campaign_id")
        if not isinstance(self.target, ProjectTarget):
            raise DiscoveryContractError("exploration requires ProjectTarget")
        if not isinstance(self.context_graph, QualityContextGraph):
            raise DiscoveryContractError("exploration requires QualityContextGraph")
        if self.context_graph.target_id != self.target.target_id:
            raise DiscoveryContractError("exploration graph target does not match target")
        if (
            self.context_graph.source_origin != self.target.source_origin
            or self.context_graph.source_commit != self.target.source_commit
            or self.context_graph.source_tree_sha256 is None
        ):
            raise DiscoveryContractError("exploration graph provenance does not match target")
        if not isinstance(self.portfolio, HypothesisPortfolio):
            raise DiscoveryContractError("exploration requires frozen HypothesisPortfolio")
        if self.portfolio.status != "frozen" or not self.portfolio.selected:
            raise DiscoveryContractError("exploration requires a frozen selected portfolio")
        if self.portfolio.target_id != self.target.target_id:
            raise DiscoveryContractError("exploration portfolio target does not match target")
        if (
            self.portfolio.source_origin != self.target.source_origin
            or self.portfolio.source_commit != self.target.source_commit
            or self.portfolio.source_tree_sha256 != self.context_graph.source_tree_sha256
        ):
            raise DiscoveryContractError("exploration portfolio provenance does not match target")
        if self.status not in CAMPAIGN_STATUSES:
            raise DiscoveryContractError("invalid exploration campaign status")
        if self.stop is not None and not isinstance(self.stop, ExplorationStop):
            raise DiscoveryContractError("exploration stop is invalid")
        if not isinstance(self.events, tuple) or any(
            not isinstance(event, ExplorationEvent) for event in self.events
        ):
            raise DiscoveryContractError("exploration events are invalid")
        _validate_event_chain(self.events, self.target.target_id)
        if self.events:
            initialization = self.events[0].payload
            if initialization.get("campaign_id") != self.campaign_id:
                raise DiscoveryContractError("initialization campaign does not match campaign")
            if initialization.get("portfolio_id") != self.portfolio.portfolio_id:
                raise DiscoveryContractError("initialization portfolio does not match campaign")
            if initialization.get("graph_id") != self.context_graph.graph_id:
                raise DiscoveryContractError("initialization graph does not match campaign")
            if initialization.get("selected_candidate_ids") != [
                item.candidate_id for item in self.portfolio.selected
            ]:
                raise DiscoveryContractError("initialization selected portfolio does not match campaign")
            if initialization.get("budget") != self.target.discovery_budget:
                raise DiscoveryContractError("initialization budget does not match target")
        views = _event_views(self.events)
        if self.attempts != views.attempts:
            raise DiscoveryContractError("exploration attempts are not reconstructed from events")
        if self.findings != views.findings:
            raise DiscoveryContractError("exploration findings are not reconstructed from events")
        if self.residual_risks != views.residual_risks:
            raise DiscoveryContractError("exploration residual risks are not reconstructed from events")
        if self.falsification_reviews != views.reviews:
            raise DiscoveryContractError("exploration reviews are not reconstructed from events")
        if self.stop != views.stop:
            raise DiscoveryContractError("exploration stop is not reconstructed from events")
        attempt_hypotheses = [item.hypothesis_id for item in self.attempts]
        if any(item.target_id != self.target.target_id for item in self.attempts):
            raise DiscoveryContractError("exploration attempt target does not match target")
        if len(set(item.attempt_ref for item in self.attempts)) != len(self.attempts):
            raise DiscoveryContractError("exploration attempts cannot be retried or replaced")
        if len({item.evidence_id for item in self.attempts}) != len(self.attempts):
            raise DiscoveryContractError("exploration attempt evidence ids must be unique")
        if len(set(attempt_hypotheses)) != len(attempt_hypotheses):
            raise DiscoveryContractError("exploration allows one attempt per hypothesis")
        selected_hypotheses = {item.hypothesis.hypothesis_id for item in self.portfolio.selected}
        if any(item.hypothesis_id not in selected_hypotheses for item in self.attempts):
            raise DiscoveryContractError("exploration attempt references non-selected hypothesis")
        if any(item.hypothesis_id not in selected_hypotheses for item in self.findings):
            raise DiscoveryContractError("exploration finding references non-selected hypothesis")
        if any(item.hypothesis_id not in selected_hypotheses for item in self.residual_risks):
            raise DiscoveryContractError("exploration residual risk references non-selected hypothesis")
        for result in self.falsification_reviews:
            if result.review is not None:
                if result.review.target_id != self.target.target_id:
                    raise DiscoveryContractError("exploration review target does not match target")
                if result.review.candidate_finding.hypothesis_id not in selected_hypotheses:
                    raise DiscoveryContractError("exploration review references non-selected hypothesis")
        if not isinstance(self.remaining_budget, int) or isinstance(self.remaining_budget, bool):
            raise DiscoveryContractError("exploration remaining_budget must be an integer")
        expected_budget = self.target.discovery_budget - len(self.attempts)
        if self.remaining_budget != expected_budget or self.remaining_budget < 0:
            raise DiscoveryContractError("exploration remaining budget contradicts attempts")
        _text_tuple(self.coverage_frontier, "exploration coverage frontier")
        expected_frontier = _compute_frontier(
            self.portfolio,
            self.context_graph,
            self.attempts,
            self.findings,
            self.residual_risks,
        )
        if self.coverage_frontier != expected_frontier:
            raise DiscoveryContractError("exploration coverage frontier is not derived from state")
        if not isinstance(self.risk_map, ProjectRiskMap):
            raise DiscoveryContractError("exploration risk_map is invalid")
        if self.risk_map.target_id != self.target.target_id:
            raise DiscoveryContractError("exploration risk_map target does not match")
        if self.risk_map.findings != self.findings or self.risk_map.residual_risks != self.residual_risks:
            raise DiscoveryContractError("exploration risk_map is not derived from outcomes")
        expected_explored = _explored_fact_ids(self.portfolio, self.attempts, self.findings, self.residual_risks)
        if self.risk_map.explored_fact_ids != expected_explored:
            raise DiscoveryContractError("exploration risk_map facts are not derived from events")
        if self.stop is not None and self.status != "stopped":
            raise DiscoveryContractError("exploration stop requires stopped status")
        if self.stop is None and self.status == "stopped":
            raise DiscoveryContractError("stopped exploration requires stop decision")
        if self.schema_version != EXPLORATION_SCHEMA_VERSION:
            raise DiscoveryContractError("unsupported exploration campaign schema_version")

    @property
    def event_head_digest(self) -> str:
        return self.events[-1].event_digest if self.events else EMPTY_EVENT_DIGEST

    @property
    def hypothesis_decisions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            event.payload
            for event in self.events
            if event.event_type == "hypothesis_decision"
        )

    @property
    def attack_decisions(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            event.payload
            for event in self.events
            if event.event_type == "attack_decision"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "campaign_id": self.campaign_id,
            "target": self.target.to_dict(),
            "context_graph": self.context_graph.to_dict(),
            "portfolio": self.portfolio.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "attempts": [item.to_dict() for item in self.attempts],
            "findings": [item.to_dict() for item in self.findings],
            "residual_risks": [item.to_dict() for item in self.residual_risks],
            "falsification_reviews": [item.to_dict() for item in self.falsification_reviews],
            "risk_map": self.risk_map.to_dict(),
            "remaining_budget": self.remaining_budget,
            "coverage_frontier": list(self.coverage_frontier),
            "status": self.status,
            "stop": self.stop.to_dict() if self.stop is not None else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExplorationCampaign":
        if not isinstance(data, Mapping):
            raise DiscoveryContractError("exploration campaign must be an object")
        _reject_unknown(
            data,
            {
                "schema_version", "campaign_id", "target", "context_graph", "portfolio",
                "events", "attempts", "findings", "residual_risks", "falsification_reviews",
                "risk_map", "remaining_budget", "coverage_frontier", "status", "stop",
            },
            "exploration campaign",
        )
        try:
            return cls(
                campaign_id=data["campaign_id"],
                target=ProjectTarget.from_dict(data["target"]),
                context_graph=QualityContextGraph.from_dict(data["context_graph"]),
                portfolio=HypothesisPortfolio.from_dict(data["portfolio"]),
                events=tuple(
                    ExplorationEvent.from_dict(item)
                    for item in _list(data, "events", "exploration campaign")
                ),
                attempts=tuple(
                    AttemptEvidence.from_dict(item)
                    for item in _list(data, "attempts", "exploration campaign")
                ),
                findings=tuple(
                    Finding.from_dict(item)
                    for item in _list(data, "findings", "exploration campaign")
                ),
                residual_risks=tuple(
                    ResidualRisk.from_dict(item)
                    for item in _list(data, "residual_risks", "exploration campaign")
                ),
                falsification_reviews=tuple(
                    FalsificationReviewResult.from_dict(item)
                    for item in _list(data, "falsification_reviews", "exploration campaign")
                ),
                risk_map=ProjectRiskMap.from_dict(data["risk_map"]),
                remaining_budget=data["remaining_budget"],
                coverage_frontier=tuple(_list(data, "coverage_frontier", "exploration campaign")),
                status=data.get("status", "created"),
                stop=(
                    ExplorationStop.from_dict(data["stop"])
                    if data.get("stop") is not None
                    else None
                ),
                schema_version=data.get("schema_version", 1),
            )
        except KeyError as error:
            raise DiscoveryContractError(f"exploration campaign requires {error.args[0]}") from error


@dataclass(frozen=True)
class _EventViews:
    attempts: tuple[AttemptEvidence, ...] = ()
    findings: tuple[Finding, ...] = ()
    residual_risks: tuple[ResidualRisk, ...] = ()
    reviews: tuple[FalsificationReviewResult, ...] = ()
    stop: ExplorationStop | None = None


def _event_views(events: tuple[ExplorationEvent, ...]) -> _EventViews:
    attempts: list[AttemptEvidence] = []
    findings: list[Finding] = []
    residual_risks: list[ResidualRisk] = []
    reviews: list[FalsificationReviewResult] = []
    stop: ExplorationStop | None = None
    for event in events:
        payload = event.payload
        try:
            if event.event_type == "attempt_recorded":
                attempts.append(AttemptEvidence.from_dict(payload["attempt"]))
            elif event.event_type == "finding_recorded":
                findings.append(Finding.from_dict(payload["finding"]))
            elif event.event_type == "residual_risk_recorded":
                residual_risks.append(ResidualRisk.from_dict(payload["residual_risk"]))
            elif event.event_type == "falsification_review_recorded":
                reviews.append(FalsificationReviewResult.from_dict(payload["review_result"]))
            elif event.event_type == "stop_recorded":
                if stop is not None:
                    raise DiscoveryContractError("exploration has more than one stop decision")
                stop = ExplorationStop.from_dict(payload["stop"])
        except KeyError as error:
            raise DiscoveryContractError(
                f"{event.event_type} event requires {error.args[0]}"
            ) from error
    return _EventViews(
        attempts=tuple(attempts),
        findings=tuple(findings),
        residual_risks=tuple(residual_risks),
        reviews=tuple(reviews),
        stop=stop,
    )


def _validate_event_chain(events: tuple[ExplorationEvent, ...], target_id: str) -> None:
    if not events:
        return
    if events[0].event_type != "campaign_initialized":
        raise DiscoveryContractError("exploration event stream must start with initialization")
    previous = EMPTY_EVENT_DIGEST
    ids: set[str] = set()
    for sequence, event in enumerate(events, start=1):
        if event.sequence != sequence or event.previous_digest != previous:
            raise DiscoveryContractError("exploration event chain is not contiguous")
        if event.target_id != target_id:
            raise DiscoveryContractError("exploration event target does not match campaign")
        if event.event_id in ids:
            raise DiscoveryContractError("exploration event ids must be unique")
        ids.add(event.event_id)
        _validate_event_semantics(event, first=sequence == 1)
        previous = event.event_digest
    _event_views(events)


def _validate_event_semantics(event: ExplorationEvent, *, first: bool) -> None:
    """Validate typed event metadata in addition to its content digest."""

    payload = event.payload
    if first:
        if event.event_type != "campaign_initialized":
            raise DiscoveryContractError("first exploration event must initialize campaign")
        if payload.get("target_id") != event.target_id:
            raise DiscoveryContractError("initialization target does not match event target")
        if not isinstance(payload.get("selected_candidate_ids"), list):
            raise DiscoveryContractError("initialization selected candidates must be recorded")
        budget = payload.get("budget")
        if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
            raise DiscoveryContractError("initialization budget must be positive")
        for field in ("campaign_id", "portfolio_id", "graph_id", "source_origin", "source_commit", "source_tree_sha256"):
            _required_text(payload.get(field), "initialization " + field)
        return
    if event.event_type == "campaign_initialized":
        raise DiscoveryContractError("exploration can only have one initialization event")
    if event.event_type == "hypothesis_decision":
        _required_text(payload.get("candidate_id"), "hypothesis decision candidate_id")
        if payload.get("hypothesis_id") != event.hypothesis_id:
            raise DiscoveryContractError("hypothesis decision metadata does not match payload")
        if payload.get("decision") not in HYPOTHESIS_DECISIONS:
            raise DiscoveryContractError("hypothesis decision payload is invalid")
    elif event.event_type == "attack_decision":
        _required_text(payload.get("attack_ref"), "attack decision attack_ref")
        _required_text(payload.get("rationale"), "attack decision rationale")
        if payload.get("hypothesis_id") != event.hypothesis_id:
            raise DiscoveryContractError("attack decision metadata does not match payload")
        if payload.get("decision") not in ATTACK_DECISIONS:
            raise DiscoveryContractError("attack decision payload is invalid")
    elif event.event_type == "attempt_recorded":
        attempt = payload.get("attempt")
        if not isinstance(attempt, Mapping):
            raise DiscoveryContractError("attempt event must contain an attempt object")
        if attempt.get("hypothesis_id") != event.hypothesis_id:
            raise DiscoveryContractError("attempt metadata does not match payload")
        if attempt.get("attempt_ref") != event.attempt_ref:
            raise DiscoveryContractError("attempt reference metadata does not match payload")
    elif event.event_type == "finding_recorded":
        finding = payload.get("finding")
        if not isinstance(finding, Mapping):
            raise DiscoveryContractError("finding event must contain a Finding object")
        if finding.get("hypothesis_id") != event.hypothesis_id:
            raise DiscoveryContractError("finding metadata does not match payload")
        source_attempt_ref = payload.get("source_attempt_ref")
        if source_attempt_ref is not None and source_attempt_ref != event.attempt_ref:
            raise DiscoveryContractError("finding attempt metadata does not match payload")
    elif event.event_type == "residual_risk_recorded":
        residual = payload.get("residual_risk")
        if not isinstance(residual, Mapping):
            raise DiscoveryContractError("residual event must contain a ResidualRisk object")
        if residual.get("hypothesis_id") != event.hypothesis_id:
            raise DiscoveryContractError("residual metadata does not match payload")
        source_attempt_ref = payload.get("source_attempt_ref")
        if source_attempt_ref is not None and source_attempt_ref != event.attempt_ref:
            raise DiscoveryContractError("residual attempt metadata does not match payload")
    elif event.event_type == "falsification_review_recorded":
        _required_text(payload.get("review_key"), "review event review_key")
        if payload.get("hypothesis_id") != event.hypothesis_id:
            raise DiscoveryContractError("review metadata does not match payload")
    elif event.event_type == "stop_recorded":
        if not isinstance(payload.get("stop"), Mapping):
            raise DiscoveryContractError("stop event must contain a stop object")


def _selected_by_hypothesis(portfolio: HypothesisPortfolio) -> dict[str, Any]:
    return {item.hypothesis.hypothesis_id: item for item in portfolio.selected}


def _candidate_map(portfolio: HypothesisPortfolio) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in portfolio.candidates:
        result[item.candidate_id] = item
    for item in portfolio.selected:
        result[item.candidate_id] = item
    for item in portfolio.rejected_candidates:
        result[item.candidate_id] = item
    return result


def _explored_fact_ids(
    portfolio: HypothesisPortfolio,
    attempts: tuple[AttemptEvidence, ...],
    findings: tuple[Finding, ...],
    residual_risks: tuple[ResidualRisk, ...],
) -> tuple[str, ...]:
    selected = _selected_by_hypothesis(portfolio)
    ids: list[str] = []
    for hypothesis_id in (
        item.hypothesis_id for item in (*attempts, *findings, *residual_risks)
    ):
        item = selected.get(hypothesis_id)
        if item is not None:
            ids.extend(item.hypothesis.supporting_fact_ids)
    return tuple(dict.fromkeys(ids))


def _compute_frontier(
    portfolio: HypothesisPortfolio,
    graph: QualityContextGraph,
    attempts: tuple[AttemptEvidence, ...],
    findings: tuple[Finding, ...],
    residual_risks: tuple[ResidualRisk, ...],
) -> tuple[str, ...]:
    completed = {
        item.hypothesis_id for item in (*attempts, *findings, *residual_risks)
    }
    explored_facts = set(_explored_fact_ids(portfolio, attempts, findings, residual_risks))
    frontier: list[str] = []
    for item in portfolio.selected:
        hypothesis_id = item.hypothesis.hypothesis_id
        if hypothesis_id not in completed:
            frontier.append("hypothesis:" + hypothesis_id)
    for fact in graph.facts:
        if fact.status != "known" and fact.fact_id not in explored_facts:
            frontier.append("fact:" + fact.fact_id)
    for entry in portfolio.coverage_frontier:
        if entry.startswith("fact:") and entry[5:] in explored_facts:
            continue
        if entry not in frontier:
            frontier.append(entry)
    return tuple(dict.fromkeys(frontier))


def _risk_map(
    campaign_id: str,
    event_head: str,
    target_id: str,
    findings: tuple[Finding, ...],
    residual_risks: tuple[ResidualRisk, ...],
    explored_fact_ids: tuple[str, ...],
    frontier: tuple[str, ...],
) -> ProjectRiskMap:
    return ProjectRiskMap(
        map_id="risk-map-" + _stable_id(campaign_id, event_head),
        target_id=target_id,
        findings=findings,
        residual_risks=residual_risks,
        explored_fact_ids=explored_fact_ids,
        coverage_frontier=frontier or ("frontier exhausted",),
    )


def _empty_campaign(
    campaign_id: str,
    target: ProjectTarget,
    graph: QualityContextGraph,
    portfolio: HypothesisPortfolio,
) -> ExplorationCampaign:
    frontier = _compute_frontier(portfolio, graph, (), (), ())
    return ExplorationCampaign(
        campaign_id=campaign_id,
        target=target,
        context_graph=graph,
        portfolio=portfolio,
        events=(),
        attempts=(),
        findings=(),
        residual_risks=(),
        falsification_reviews=(),
        risk_map=_risk_map(campaign_id, EMPTY_EVENT_DIGEST, target.target_id, (), (), (), frontier),
        remaining_budget=target.discovery_budget,
        coverage_frontier=frontier,
        status="created",
    )


def _materialize(state: ExplorationCampaign, events: tuple[ExplorationEvent, ...]) -> ExplorationCampaign:
    views = _event_views(events)
    frontier = _compute_frontier(
        state.portfolio,
        state.context_graph,
        views.attempts,
        views.findings,
        views.residual_risks,
    )
    head = events[-1].event_digest if events else EMPTY_EVENT_DIGEST
    status = "stopped" if views.stop is not None else "created" if len(events) <= 1 else "exploring"
    return ExplorationCampaign(
        campaign_id=state.campaign_id,
        target=state.target,
        context_graph=state.context_graph,
        portfolio=state.portfolio,
        events=events,
        attempts=views.attempts,
        findings=views.findings,
        residual_risks=views.residual_risks,
        falsification_reviews=views.reviews,
        risk_map=_risk_map(
            state.campaign_id,
            head,
            state.target.target_id,
            views.findings,
            views.residual_risks,
            _explored_fact_ids(state.portfolio, views.attempts, views.findings, views.residual_risks),
            frontier,
        ),
        remaining_budget=state.target.discovery_budget - len(views.attempts),
        coverage_frontier=frontier,
        status=status,
        stop=views.stop,
    )


def _append_event(
    state: ExplorationCampaign,
    *,
    event_type: str,
    payload: Mapping[str, Any],
    artifact_refs: tuple[ImmutableArtifactRef, ...],
    hypothesis_id: str | None = None,
    attempt_ref: str | None = None,
) -> ExplorationCampaign:
    if state.stop is not None:
        raise DiscoveryContractError("exploration is stopped; no further transitions are allowed")
    event = ExplorationEvent.create(
        sequence=len(state.events) + 1,
        event_type=event_type,
        target_id=state.target.target_id,
        artifact_refs=_artifact_refs(artifact_refs),
        payload=payload,
        previous_digest=state.event_head_digest,
        hypothesis_id=hypothesis_id,
        attempt_ref=attempt_ref,
    )
    return _materialize(state, (*state.events, event))


def _ensure_open(state: ExplorationCampaign) -> None:
    if state.stop is not None:
        raise DiscoveryContractError("exploration is stopped; no further transitions are allowed")


def initialize_exploration_campaign(
    campaign_id: str,
    target: ProjectTarget,
    graph: QualityContextGraph,
    portfolio: HypothesisPortfolio,
    *,
    artifact_refs: tuple[ImmutableArtifactRef, ...] | None = None,
) -> ExplorationCampaign:
    """Initialize M9 exploration from one frozen, provenance-bound portfolio."""

    if not isinstance(target, ProjectTarget):
        raise DiscoveryContractError("exploration initialization requires ProjectTarget")
    if not isinstance(graph, QualityContextGraph):
        raise DiscoveryContractError("exploration initialization requires QualityContextGraph")
    if not isinstance(portfolio, HypothesisPortfolio):
        raise DiscoveryContractError("exploration initialization requires HypothesisPortfolio")
    base = _empty_campaign(campaign_id, target, graph, portfolio)
    refs = artifact_refs or (
        make_campaign_artifact("target:" + target.target_id, "target", target.to_dict()),
        make_campaign_artifact("context-graph:" + graph.graph_id, "context-graph", graph.to_dict()),
        make_campaign_artifact("portfolio:" + portfolio.portfolio_id, "hypothesis-portfolio", portfolio.to_dict()),
    )
    return _append_event(
        base,
        event_type="campaign_initialized",
        payload={
            "campaign_id": campaign_id,
            "target_id": target.target_id,
            "portfolio_id": portfolio.portfolio_id,
            "graph_id": graph.graph_id,
            "source_origin": target.source_origin,
            "source_commit": target.source_commit,
            "source_tree_sha256": graph.source_tree_sha256,
            "selected_candidate_ids": [item.candidate_id for item in portfolio.selected],
            "budget": target.discovery_budget,
        },
        artifact_refs=tuple(refs),
    )


start_exploration_campaign = initialize_exploration_campaign
create_exploration_campaign = initialize_exploration_campaign


def record_hypothesis_decision(
    state: ExplorationCampaign,
    candidate_id: str,
    decision: str,
    *,
    rationale: str,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
) -> ExplorationCampaign:
    """Append one portfolio decision without changing the frozen portfolio."""

    _ensure_open(state)
    if decision not in HYPOTHESIS_DECISIONS:
        raise DiscoveryContractError("invalid exploration hypothesis decision")
    _required_text(candidate_id, "candidate_id")
    _required_text(rationale, "hypothesis decision rationale")
    candidate_map = _candidate_map(state.portfolio)
    candidate = candidate_map.get(candidate_id)
    if candidate is None:
        raise DiscoveryContractError("hypothesis decision references unknown candidate")
    expected = state.portfolio.decision_for(candidate_id)
    if decision != expected:
        raise DiscoveryContractError("hypothesis decision contradicts frozen portfolio")
    if any(item.get("candidate_id") == candidate_id for item in state.hypothesis_decisions):
        raise DiscoveryContractError("hypothesis decision has already been recorded")
    hypothesis_id = getattr(getattr(candidate, "hypothesis", None), "hypothesis_id", None)
    return _append_event(
        state,
        event_type="hypothesis_decision",
        hypothesis_id=hypothesis_id,
        payload={
            "candidate_id": candidate_id,
            "hypothesis_id": hypothesis_id,
            "decision": decision,
            "priority_score": next(
                (item.priority.score for item in state.portfolio.selected if item.candidate_id == candidate_id),
                0.0,
            ),
            "rationale": rationale,
        },
        artifact_refs=artifact_refs,
    )


def _selected_item(state: ExplorationCampaign, hypothesis_id: str) -> Any:
    selected = _selected_by_hypothesis(state.portfolio).get(hypothesis_id)
    if selected is None:
        raise DiscoveryContractError("exploration references a non-selected hypothesis")
    return selected


def record_attack_decision(
    state: ExplorationCampaign,
    hypothesis_id: str,
    *,
    decision: str,
    attack_ref: str,
    rationale: str,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
    admission: Mapping[str, Any] | None = None,
) -> ExplorationCampaign:
    """Append an admitted/rejected attack decision before any attempt."""

    _ensure_open(state)
    _selected_item(state, hypothesis_id)
    selected_decision = next(
        (
            item.get("decision")
            for item in state.hypothesis_decisions
            if item.get("hypothesis_id") == hypothesis_id
        ),
        None,
    )
    if selected_decision != "selected":
        raise DiscoveryContractError("attack decision requires a recorded selected hypothesis")
    if decision not in ATTACK_DECISIONS:
        raise DiscoveryContractError("invalid exploration attack decision")
    _required_text(attack_ref, "attack_ref")
    _required_text(rationale, "attack decision rationale")
    for existing in state.attack_decisions:
        if existing.get("attack_ref") == attack_ref:
            raise DiscoveryContractError("attack decision has already been recorded")
        if existing.get("hypothesis_id") == hypothesis_id and existing.get("decision") == "admitted":
            raise DiscoveryContractError("hypothesis already has an admitted attack")
    payload: dict[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "attack_ref": attack_ref,
        "decision": decision,
        "rationale": rationale,
    }
    if admission is not None:
        payload["admission"] = dict(admission)
    return _append_event(
        state,
        event_type="attack_decision",
        hypothesis_id=hypothesis_id,
        payload=payload,
        artifact_refs=artifact_refs,
    )


def _latest_attack(state: ExplorationCampaign, hypothesis_id: str) -> Mapping[str, Any] | None:
    decisions = [
        item for item in state.attack_decisions
        if item.get("hypothesis_id") == hypothesis_id
    ]
    return decisions[-1] if decisions else None


def _finding_for_attempt(state: ExplorationCampaign, evidence: AttemptEvidence) -> Finding:
    item = _selected_item(state, evidence.hypothesis_id)
    return Finding(
        finding_id="finding-" + _stable_id(evidence.evidence_id, evidence.attempt_ref),
        target_id=evidence.target_id,
        hypothesis_id=evidence.hypothesis_id,
        conclusion=evidence.outcome,
        evidence_refs=tuple(dict.fromkeys((*evidence.evidence_refs, evidence.execution_record_ref))),
        impact=item.hypothesis.consequence,
        claim_boundary=evidence.claim_boundary,
        rationale=evidence.rationale,
    )


def _residual_for_attempt(state: ExplorationCampaign, evidence: AttemptEvidence) -> ResidualRisk:
    _selected_item(state, evidence.hypothesis_id)
    refs = tuple(dict.fromkeys((*evidence.evidence_refs, evidence.execution_record_ref)))
    return ResidualRisk(
        risk_id="risk-" + _stable_id(evidence.evidence_id, evidence.attempt_ref),
        target_id=evidence.target_id,
        hypothesis_id=evidence.hypothesis_id,
        reason=evidence.rationale,
        evidence_gap="The attempt was non-accountable; no Finding is supported.",
        scope=evidence.claim_boundary,
        basis_refs=refs,
        next_probe="No retry or replacement; continue only with an unattempted portfolio entry.",
    )


def record_attempt(
    state: ExplorationCampaign,
    evidence: AttemptEvidence,
    *,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
) -> ExplorationCampaign:
    """Record one terminal attempt and its derived Finding or Residual Risk."""

    _ensure_open(state)
    if not isinstance(evidence, AttemptEvidence):
        raise DiscoveryContractError("exploration attempt must be AttemptEvidence")
    _selected_item(state, evidence.hypothesis_id)
    if evidence.target_id != state.target.target_id:
        raise DiscoveryContractError("attempt target does not match exploration")
    selected_decision = next(
        (
            item.get("decision")
            for item in state.hypothesis_decisions
            if item.get("hypothesis_id") == evidence.hypothesis_id
        ),
        None,
    )
    if selected_decision != "selected":
        raise DiscoveryContractError("attempt requires a recorded selected hypothesis")
    if state.remaining_budget < 1:
        raise DiscoveryContractError("exploration budget is exhausted")
    admitted = _latest_attack(state, evidence.hypothesis_id)
    if admitted is None or admitted.get("decision") != "admitted":
        raise DiscoveryContractError("attempt requires an admitted attack")
    if any(item.hypothesis_id == evidence.hypothesis_id for item in state.attempts):
        raise DiscoveryContractError("attempt would be a retry or replacement")
    if any(item.hypothesis_id == evidence.hypothesis_id for item in (*state.findings, *state.residual_risks)):
        raise DiscoveryContractError("attempt would replace an existing terminal outcome")
    refs = _artifact_refs(artifact_refs)
    updated = _append_event(
        state,
        event_type="attempt_recorded",
        hypothesis_id=evidence.hypothesis_id,
        attempt_ref=evidence.attempt_ref,
        payload={"attempt": evidence.to_dict(), "attack_ref": admitted.get("attack_ref")},
        artifact_refs=refs,
    )
    if evidence.accountable:
        finding = _finding_for_attempt(updated, evidence)
        return _append_event(
            updated,
            event_type="finding_recorded",
            hypothesis_id=finding.hypothesis_id,
            attempt_ref=evidence.attempt_ref,
            payload={"finding": finding.to_dict(), "source_attempt_ref": evidence.attempt_ref},
            artifact_refs=refs,
        )
    residual = _residual_for_attempt(updated, evidence)
    return _append_event(
        updated,
        event_type="residual_risk_recorded",
        hypothesis_id=residual.hypothesis_id,
        attempt_ref=evidence.attempt_ref,
        payload={"residual_risk": residual.to_dict(), "source_attempt_ref": evidence.attempt_ref},
        artifact_refs=refs,
    )


record_attempt_evidence = record_attempt


def record_finding(
    state: ExplorationCampaign,
    finding: Finding,
    *,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
) -> ExplorationCampaign:
    """Append an externally reduced Finding without changing its evidence."""

    _ensure_open(state)
    _selected_item(state, finding.hypothesis_id)
    if finding.target_id != state.target.target_id:
        raise DiscoveryContractError("finding target does not match exploration")
    if any(item.hypothesis_id == finding.hypothesis_id for item in (*state.attempts, *state.findings, *state.residual_risks)):
        raise DiscoveryContractError("finding would replace an existing terminal outcome")
    if any(item.finding_id == finding.finding_id for item in state.findings):
        raise DiscoveryContractError("finding has already been recorded")
    return _append_event(
        state,
        event_type="finding_recorded",
        hypothesis_id=finding.hypothesis_id,
        payload={"finding": finding.to_dict(), "source_attempt_ref": None},
        artifact_refs=artifact_refs,
    )


def record_residual_risk(
    state: ExplorationCampaign,
    residual_risk: ResidualRisk,
    *,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
) -> ExplorationCampaign:
    """Append an explicit unresolved risk without promoting it to a Finding."""

    _ensure_open(state)
    _selected_item(state, residual_risk.hypothesis_id)
    if residual_risk.target_id != state.target.target_id:
        raise DiscoveryContractError("residual risk target does not match exploration")
    if any(item.hypothesis_id == residual_risk.hypothesis_id for item in (*state.attempts, *state.findings, *state.residual_risks)):
        raise DiscoveryContractError("residual risk would replace an existing terminal outcome")
    if any(item.risk_id == residual_risk.risk_id for item in state.residual_risks):
        raise DiscoveryContractError("residual risk has already been recorded")
    return _append_event(
        state,
        event_type="residual_risk_recorded",
        hypothesis_id=residual_risk.hypothesis_id,
        payload={"residual_risk": residual_risk.to_dict(), "source_attempt_ref": None},
        artifact_refs=artifact_refs,
    )


def record_falsification_review(
    state: ExplorationCampaign,
    result: FalsificationReviewResult,
    *,
    hypothesis_id: str | None = None,
    artifact_refs: tuple[ImmutableArtifactRef, ...],
) -> ExplorationCampaign:
    """Append a review state; challenged/inconclusive reviews never rewrite findings."""

    _ensure_open(state)
    if not isinstance(result, FalsificationReviewResult):
        raise DiscoveryContractError("falsification review result is invalid")
    if result.review is not None:
        finding_id = result.review.candidate_finding.finding_id
        if not any(item.finding_id == finding_id for item in state.findings):
            raise DiscoveryContractError("falsification review references an unknown Finding")
        selected_hypothesis = result.review.candidate_finding.hypothesis_id
    else:
        selected_hypothesis = hypothesis_id
    if selected_hypothesis is None:
        raise DiscoveryContractError("rejected review requires a hypothesis_id")
    _selected_item(state, selected_hypothesis)
    review_key = result.review.review_id if result.review is not None else result.context_id
    if any(
        item.get("review_key") == review_key
        for item in (
            event.payload
            for event in state.events
            if event.event_type == "falsification_review_recorded"
        )
    ):
        raise DiscoveryContractError("falsification review has already been recorded")
    return _append_event(
        state,
        event_type="falsification_review_recorded",
        hypothesis_id=selected_hypothesis,
        payload={
            "review_key": review_key,
            "hypothesis_id": selected_hypothesis,
            "review_result": result.to_dict(),
        },
        artifact_refs=artifact_refs,
    )


def rank_next_probes(state: ExplorationCampaign) -> tuple[NextProbe, ...]:
    """Rank only unattempted selected hypotheses using frozen priority and state."""

    if state.stop is not None:
        return ()
    attempted = {item.hypothesis_id for item in state.attempts}
    budget_available = state.remaining_budget > 0
    result: list[NextProbe] = []
    for item in state.portfolio.selected:
        hypothesis_id = item.hypothesis.hypothesis_id
        if hypothesis_id in attempted:
            continue
        attack = _latest_attack(state, hypothesis_id)
        if not budget_available:
            admissible = False
            reason = "remaining discovery budget is exhausted"
        elif attack is None:
            admissible = False
            reason = "attack not yet admitted"
        elif attack.get("decision") == "admitted":
            admissible = True
            reason = "admitted attack is ready for one terminal attempt"
        else:
            admissible = False
            reason = "latest attack decision rejected"
        result.append(
            NextProbe(
                hypothesis_id=hypothesis_id,
                candidate_id=item.candidate_id,
                priority_score=item.priority.score,
                admissible=admissible,
                reason=reason,
                attempt_count=0,
            )
        )
    return tuple(sorted(result, key=lambda probe: (-probe.priority_score, probe.candidate_id)))


next_probes = rank_next_probes


def recompute_coverage_frontier(state: ExplorationCampaign) -> tuple[str, ...]:
    """Recompute the frontier from recorded events, never hidden outcomes."""

    return _compute_frontier(
        state.portfolio,
        state.context_graph,
        state.attempts,
        state.findings,
        state.residual_risks,
    )


coverage_frontier = recompute_coverage_frontier


def evaluate_stop(state: ExplorationCampaign) -> ExplorationStop | None:
    """Return the deterministic stop decision currently justified by state."""

    if state.stop is not None:
        return state.stop
    if state.remaining_budget == 0:
        return ExplorationStop.create(
            reason="budget_exhausted",
            rationale="The bounded discovery budget has been consumed by terminal attempts.",
            evidence_refs=tuple(item.attempt_ref for item in state.attempts),
            artifact_refs=(make_campaign_artifact("event-head:" + state.event_head_digest, "event-head", state.event_head_digest),),
        )
    if any(item.conclusion in {"supported", "rejected"} for item in state.findings):
        finding = next(item for item in state.findings if item.conclusion in {"supported", "rejected"})
        return ExplorationStop.create(
            reason="terminal_finding",
            rationale="A recorded Finding has a terminal supported or rejected conclusion.",
            evidence_refs=finding.evidence_refs,
            artifact_refs=(make_campaign_artifact("finding:" + finding.finding_id, "finding", finding.to_dict()),),
        )
    if not state.coverage_frontier:
        return ExplorationStop.create(
            reason="frontier_exhausted",
            rationale="No unexplored hypothesis, unresolved fact, or portfolio frontier remains.",
            evidence_refs=("coverage-frontier:empty",),
            artifact_refs=(make_campaign_artifact("frontier:" + state.event_head_digest, "coverage-frontier", []),),
        )
    probes = rank_next_probes(state)
    if probes and all(not item.admissible for item in probes) and all(
        _latest_attack(state, item.hypothesis_id) is not None for item in probes
    ):
        return ExplorationStop.create(
            reason="no_admissible_attack",
            rationale="Every remaining selected hypothesis has an explicit rejected attack decision.",
            evidence_refs=tuple(
                str(_latest_attack(state, item.hypothesis_id).get("attack_ref")) for item in probes
            ),
            artifact_refs=(make_campaign_artifact("attacks:" + state.event_head_digest, "attack-decisions", state.attack_decisions),),
        )
    if state.residual_risks and not probes:
        residual = state.residual_risks[-1]
        return ExplorationStop.create(
            reason="evidence_gap",
            rationale="Only unresolved residual risk remains and its evidence gap is recorded.",
            evidence_refs=residual.basis_refs,
            artifact_refs=(make_campaign_artifact("residual:" + residual.risk_id, "residual-risk", residual.to_dict()),),
        )
    return None


def stop_exploration(
    state: ExplorationCampaign,
    *,
    reason: str,
    rationale: str,
    evidence_refs: tuple[str, ...],
    artifact_refs: tuple[ImmutableArtifactRef, ...],
) -> ExplorationCampaign:
    """Record one explicit terminal stop; no later transition is permitted."""

    _ensure_open(state)
    if reason not in STOP_REASONS:
        raise DiscoveryContractError("invalid exploration stop reason")
    if reason == "budget_exhausted" and state.remaining_budget != 0:
        raise DiscoveryContractError("budget_exhausted stop requires zero remaining budget")
    if reason == "terminal_finding" and not any(
        item.conclusion in {"supported", "rejected"} for item in state.findings
    ):
        raise DiscoveryContractError("terminal_finding stop requires a terminal Finding")
    if reason == "frontier_exhausted" and state.coverage_frontier:
        raise DiscoveryContractError("frontier_exhausted stop requires an empty frontier")
    if reason == "evidence_gap" and not state.residual_risks:
        raise DiscoveryContractError("evidence_gap stop requires a Residual Risk")
    if reason == "no_admissible_attack":
        probes = rank_next_probes(state)
        if not probes or any(
            item.admissible or _latest_attack(state, item.hypothesis_id) is None
            for item in probes
        ):
            raise DiscoveryContractError("no_admissible_attack stop is not justified by state")
    stop = ExplorationStop.create(
        reason=reason,
        rationale=rationale,
        evidence_refs=evidence_refs,
        artifact_refs=artifact_refs,
    )
    return _append_event(
        state,
        event_type="stop_recorded",
        payload={"stop": stop.to_dict()},
        artifact_refs=artifact_refs,
    )


record_stop = stop_exploration


def replay_exploration_campaign(
    campaign: ExplorationCampaign | Mapping[str, Any],
) -> ExplorationCampaign:
    """Reconstruct state from the event stream and reject state/event drift."""

    state = (
        ExplorationCampaign.from_dict(campaign)
        if isinstance(campaign, Mapping)
        else campaign
    )
    if not isinstance(state, ExplorationCampaign):
        raise DiscoveryContractError("replay requires ExplorationCampaign")
    base = _empty_campaign(state.campaign_id, state.target, state.context_graph, state.portfolio)
    replayed = _materialize(base, state.events)
    if replayed != state:
        raise DiscoveryContractError("exploration event replay does not match serialized state")
    return replayed


resume_exploration_campaign = replay_exploration_campaign
replay_campaign_events = replay_exploration_campaign


__all__ = [
    "ATTACK_DECISIONS",
    "CAMPAIGN_ARTIFACT_KIND",
    "CAMPAIGN_STATUSES",
    "CampaignArtifactRef",
    "EMPTY_EVENT_DIGEST",
    "EVENT_TYPES",
    "EXPLORATION_SCHEMA_VERSION",
    "ExplorationCampaign",
    "ExplorationEvent",
    "ExplorationStop",
    "HYPOTHESIS_DECISIONS",
    "NextProbe",
    "STOP_REASONS",
    "CampaignArtifactRef",
    "coverage_frontier",
    "create_exploration_campaign",
    "evaluate_stop",
    "initialize_exploration_campaign",
    "make_campaign_artifact",
    "next_probes",
    "rank_next_probes",
    "record_attack_decision",
    "record_attempt",
    "record_attempt_evidence",
    "record_falsification_review",
    "record_finding",
    "record_hypothesis_decision",
    "record_residual_risk",
    "record_stop",
    "recompute_coverage_frontier",
    "replay_campaign_events",
    "replay_exploration_campaign",
    "resume_exploration_campaign",
    "start_exploration_campaign",
    "stop_exploration",
]
