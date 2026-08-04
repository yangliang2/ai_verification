"""Deterministic, blinded M7 discovery qualification over the local fixture.

This module qualifies the discovery/admission/evidence seam, not Android
execution.  The verifier-facing packet is built without the cell variant,
oracle outcome, or expected evidence.  A deterministic auditor oracle applies
the preregistered defect/control observation only after the hypothesis and
attack plan are frozen and admitted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping

from jsonschema import Draft202012Validator

from aiverify.discovery import (
    AttemptEvidence,
    BehaviorDelta,
    ChangeTarget,
    ContextExpansionRequest,
    ContextExpansionResult,
    ContractDrift,
    DiscoveryCampaignPackage,
    DiscoveryContractError,
    ProjectTarget,
    apply_context_expansion,
    admit_campaign_plan,
    compile_attack_plan_to_run_spec,
    create_campaign,
    freeze_campaign_hypothesis,
    load_context_manifest,
    reduce_attempt_evidence,
)
from aiverify.runner.run_spec import ScenarioSpec


_SCHEMA_PATH = Path(__file__).with_name("m7_qualification_schema.json")
_CELL_IDS = (
    "change-defect",
    "change-control",
    "project-defect",
    "project-control",
)
_MODES = {"change", "project"}
_VARIANTS = {"defect", "control"}
_FORBIDDEN_PACKET_TERMS = (
    "defect",
    "control",
    "variant",
    "expected",
    "verdict",
    "finding",
    "outcome",
    "oracle",
    "supported",
    "rejected",
    "anr",
    "p-03",
)


class M7QualificationError(ValueError):
    """Raised when a frozen M7 manifest, packet, or aggregate is invalid."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(dict.fromkeys(str(error) for error in errors))
        super().__init__(
            "M7 qualification is invalid:\n" + "\n".join(f"- {e}" for e in self.errors)
        )


@dataclass(frozen=True)
class M7QualificationManifest:
    """Frozen manifest and exact source identity consumed by the run."""

    source_path: Path
    source_sha256: str
    canonical_sha256: str
    document: Mapping[str, Any]

    @property
    def qualification_id(self) -> str:
        return str(self.document["qualification_id"])

    @property
    def cells(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(self.document["cells"])


@dataclass(frozen=True)
class M7VerificationPacket:
    """Verifier-facing input with no cell variant or expected result."""

    packet_id: str
    lane_id: str
    target_mode: str
    target_id: str
    source_origin: str
    source_commit: str
    worktree: str
    scope: tuple[str, ...]
    diff_ref: str | None
    diff_sha256: str | None
    context_manifest_ref: str
    context_manifest_sha256: str
    discovery_budget: int

    def __post_init__(self) -> None:
        for field in (
            "packet_id",
            "lane_id",
            "target_id",
            "source_origin",
            "source_commit",
            "worktree",
            "context_manifest_ref",
            "context_manifest_sha256",
        ):
            _required_text(getattr(self, field), field)
        if self.target_mode not in _MODES:
            raise M7QualificationError(("packet target_mode is invalid",))
        if not self.scope or any(
            not isinstance(item, str) or not item.strip() for item in self.scope
        ):
            raise M7QualificationError(("packet scope must be non-empty",))
        if self.target_mode == "change":
            if not self.diff_ref or not self.diff_sha256 or not _is_sha256(self.diff_sha256):
                raise M7QualificationError(("change packet requires diff identity",))
        elif self.diff_ref is not None or self.diff_sha256 is not None:
            raise M7QualificationError(("project packet must not carry a diff",))
        if not isinstance(self.discovery_budget, int) or self.discovery_budget < 1:
            raise M7QualificationError(("packet discovery_budget must be positive",))
        leakage = _packet_leakage(self.to_dict())
        if leakage:
            raise M7QualificationError(
                ("verifier packet leaks hidden qualification fields: " + ", ".join(leakage),)
            )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": 1,
            "packet_id": self.packet_id,
            "lane_id": self.lane_id,
            "target_mode": self.target_mode,
            "target_id": self.target_id,
            "source_origin": self.source_origin,
            "source_commit": self.source_commit,
            "worktree": self.worktree,
            "scope": list(self.scope),
            "context_manifest_ref": self.context_manifest_ref,
            "context_manifest_sha256": self.context_manifest_sha256,
            "discovery_budget": self.discovery_budget,
        }
        if self.diff_ref is not None:
            result["diff_ref"] = self.diff_ref
            result["diff_sha256"] = self.diff_sha256
        return result


@dataclass(frozen=True)
class M7LaneResult:
    """One formal lane plus auditor-only variant and final campaign package."""

    lane_id: str
    cell_id: str
    target_mode: str
    repetition: int
    hidden_variant: str
    packet: M7VerificationPacket
    admitted_package: DiscoveryCampaignPackage
    final_package: DiscoveryCampaignPackage
    attempt: AttemptEvidence
    adjudication: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.hidden_variant not in _VARIANTS:
            raise M7QualificationError(("lane hidden variant is invalid",))
        if self.packet.lane_id != self.lane_id:
            raise M7QualificationError(("lane packet identity mismatch",))
        if self.admitted_package.campaign.target.target_id != self.packet.target_id:
            raise M7QualificationError(("lane admitted target mismatch",))
        if self.final_package.campaign.target.target_id != self.packet.target_id:
            raise M7QualificationError(("lane final target mismatch",))
        if self.attempt.target_id != self.packet.target_id:
            raise M7QualificationError(("lane attempt target mismatch",))
        if self.attempt.accountable is not True:
            raise M7QualificationError(("formal M7 lane must be accountable",))

    @property
    def conclusion(self) -> str:
        return self.final_package.campaign.findings[0].conclusion

    def to_dict(self) -> dict[str, Any]:
        hypothesis = self.admitted_package.campaign.hypotheses[0]
        plan = self.admitted_package.campaign.attack_plans[0]
        return {
            "lane_id": self.lane_id,
            "cell_id": self.cell_id,
            "target_mode": self.target_mode,
            "repetition": self.repetition,
            "hidden_variant": self.hidden_variant,
            "packet_id": self.packet.packet_id,
            "hypothesis_frozen": hypothesis.status == "frozen",
            "hypothesis_id": hypothesis.hypothesis_id,
            "plan_admitted": plan.status == "admitted",
            "plan_id": plan.plan_id,
            "attempt_id": self.attempt.attempt_ref,
            "attempt_count": 1,
            "retry_count": 0,
            "accountable": self.attempt.accountable,
            "oracle_outcome": self.attempt.outcome,
            "finding_conclusion": self.conclusion,
            "campaign_status": self.final_package.campaign.status,
            "adjudication": dict(self.adjudication),
            "package_sha256": _canonical_sha256(self.final_package.to_dict()),
        }


@dataclass(frozen=True)
class M7QualificationReport:
    """Auditable aggregate with separate mode/cell summaries."""

    manifest: M7QualificationManifest
    packets: tuple[M7VerificationPacket, ...]
    lanes: tuple[M7LaneResult, ...]
    preflight: Mapping[str, Any]
    leakage_audit: Mapping[str, Any]

    @property
    def aggregate(self) -> dict[str, Any]:
        return _aggregate(self.manifest, self.lanes, self.preflight, self.leakage_audit)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "qualification_id": self.manifest.qualification_id,
            "manifest": {
                "path": self.manifest.source_path.as_posix(),
                "sha256": self.manifest.source_sha256,
                "canonical_sha256": self.manifest.canonical_sha256,
            },
            "packets": [packet.to_dict() for packet in self.packets],
            "lanes": [lane.to_dict() for lane in self.lanes],
            "preflight": dict(self.preflight),
            "leakage_audit": dict(self.leakage_audit),
            "aggregate": self.aggregate,
            "claim_boundary": {
                "local_only": True,
                "no_android_execution_claim": True,
                "no_rate_claim": True,
            },
        }


def load_manifest(path: str | Path) -> M7QualificationManifest:
    """Load and fail closed on the frozen four-cell manifest."""

    source_path = Path(path).resolve()
    try:
        raw = source_path.read_bytes()
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, M7QualificationError) as error:
        raise M7QualificationError((f"manifest cannot be read: {error}",)) from error
    if not isinstance(document, dict):
        raise M7QualificationError(("manifest root must be an object",))
    try:
        Draft202012Validator.check_schema(load_schema())
        errors = sorted(
            Draft202012Validator(load_schema()).iter_errors(document),
            key=lambda error: (tuple(str(item) for item in error.absolute_path), error.message),
        )
    except Exception as error:
        raise M7QualificationError((f"manifest schema is invalid: {error}",)) from error
    if errors:
        raise M7QualificationError(tuple(_render_schema_error(error) for error in errors))
    semantic_errors = _manifest_errors(document)
    if semantic_errors:
        raise M7QualificationError(semantic_errors)
    canonical = _canonical_bytes(document)
    return M7QualificationManifest(
        source_path=source_path,
        source_sha256=sha256(raw).hexdigest(),
        canonical_sha256=sha256(canonical).hexdigest(),
        document=document,
    )


def load_schema() -> dict[str, Any]:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def self_validate_schema() -> None:
    Draft202012Validator.check_schema(load_schema())


def audit_packet(packet: M7VerificationPacket) -> dict[str, Any]:
    """Scan one verifier input for hidden variant/outcome terms."""

    leakage = _packet_leakage(packet.to_dict())
    return {
        "packet_id": packet.packet_id,
        "status": "pass" if not leakage else "fail",
        "forbidden_terms": leakage,
        "variant_withheld": True,
        "outcome_withheld": True,
        "evidence_withheld": True,
    }


def run_qualification(
    manifest_path: str | Path,
    *,
    context_manifest_path: str | Path,
) -> M7QualificationReport:
    """Run all twelve deterministic discovery lanes without device side effects."""

    manifest = load_manifest(manifest_path)
    context_path = Path(context_manifest_path).resolve()
    context_bytes = context_path.read_bytes()
    context_sha = sha256(context_bytes).hexdigest()
    packets = _build_packets(manifest, context_path, context_sha)
    leakage_checks = tuple(audit_packet(packet) for packet in packets)
    if any(check["status"] != "pass" for check in leakage_checks):
        raise M7QualificationError(("formal lanes cannot start after leakage audit failure",))
    leakage_audit = {
        "status": "pass",
        "packet_count": len(packets),
        "checks": list(leakage_checks),
        "network_policy": "disabled",
        "variant_mapping_available_only_to_auditor": True,
    }
    preflight = _contradictory_preflight(context_path)
    if preflight["status"] != "rejected" or preflight["formal_denominator"] is not False:
        raise M7QualificationError(("contradictory preflight did not fail closed",))
    lanes = tuple(
        _run_lane(manifest, packet, context_path)
        for packet in packets
    )
    if len(lanes) != 12:
        raise M7QualificationError(("formal qualification must contain exactly twelve lanes",))
    return M7QualificationReport(
        manifest=manifest,
        packets=packets,
        lanes=lanes,
        preflight=preflight,
        leakage_audit=leakage_audit,
    )


def _build_packets(
    manifest: M7QualificationManifest,
    context_path: Path,
    context_sha: str,
) -> tuple[M7VerificationPacket, ...]:
    packets: list[M7VerificationPacket] = []
    for cell in manifest.cells:
        for repetition in range(1, int(cell["repetitions"]) + 1):
            lane_number = len(packets) + 1
            lane_id = f"lane-{lane_number:02d}"
            mode = str(cell["target_mode"])
            target_id = f"m7-{mode}-target-{lane_number:02d}"
            diff_ref = f"inputs/{lane_id}/change.diff" if mode == "change" else None
            diff_sha = (
                sha256(b"neutral temporal contract change input v1").hexdigest()
                if mode == "change"
                else None
            )
            packets.append(
                M7VerificationPacket(
                    packet_id=f"packet-{lane_id}",
                    lane_id=lane_id,
                    target_mode=mode,
                    target_id=target_id,
                    source_origin="https://example.invalid/aiverify-m7-fixture",
                    source_commit="synchronous-weather-v1",
                    worktree="/workspace/aiverify-m7-fixture",
                    scope=("weather-service", "systemui-consumer"),
                    diff_ref=diff_ref,
                    diff_sha256=diff_sha,
                    context_manifest_ref=context_path.as_posix(),
                    context_manifest_sha256=context_sha,
                    discovery_budget=8,
                )
            )
    return tuple(packets)


def _run_lane(
    manifest: M7QualificationManifest,
    packet: M7VerificationPacket,
    context_path: Path,
) -> M7LaneResult:
    cell = next(cell for cell in manifest.cells if packet.lane_id in _cell_lane_ids(manifest, cell))
    cell_id = str(cell["cell_id"])
    repetition = _cell_repetition(packet.lane_id, manifest, cell)
    if packet.target_mode == "change":
        target = ChangeTarget(
            target_id=packet.target_id,
            source_origin=packet.source_origin,
            source_commit=packet.source_commit,
            worktree=packet.worktree,
            diff_ref=packet.diff_ref or "inputs/change.diff",
            diff_sha256=packet.diff_sha256 or sha256(b"neutral").hexdigest(),
        )
    else:
        target = ProjectTarget(
            target_id=packet.target_id,
            source_origin=packet.source_origin,
            source_commit=packet.source_commit,
            worktree=packet.worktree,
            scope=packet.scope,
            discovery_budget=packet.discovery_budget,
        )
    graph = load_context_manifest(context_path, target).graph
    request = ContextExpansionRequest(
        request_id=f"request-{packet.lane_id}",
        campaign_id=f"campaign-{packet.lane_id}",
        target_id=target.target_id,
        required_predicates=("caller_thread", "quality_contract"),
        probe_refs=("probe:runtime-thread",),
        budget=1,
        unresolved_questions=("runtime thread remains unknown",),
    )
    created = create_campaign(
        request.campaign_id,
        target,
        graph,
        expansion_request=request,
    )
    expanded = apply_context_expansion(
        created,
        ContextExpansionResult(
            request_id=request.request_id,
            target_id=target.target_id,
            graph=graph,
            resolved_fact_ids=tuple(
                fact.fact_id for fact in graph.facts if fact.status == "known"
            ),
            unresolved_questions=request.unresolved_questions,
            probe_refs=request.probe_refs,
            budget_used=0,
            status="partial",
        ),
    )
    if packet.target_mode == "change":
        delta, drift = _neutral_change_inputs(target)
        frozen = freeze_campaign_hypothesis(
            expanded,
            behavior_delta=delta,
            contract_drift=drift,
        )
    else:
        frozen = freeze_campaign_hypothesis(expanded)
    admission = admit_campaign_plan(frozen)
    if not admission.admission.admitted:
        raise M7QualificationError((f"lane {packet.lane_id} admission failed",))
    admitted = admission.package
    compiled = compile_attack_plan_to_run_spec(
        admitted,
        host_project=target.worktree,
        apk_glob="build/outputs/**/*.apk",
        package_name="com.example.systemui",
        activity=".MainActivity",
        scenario=ScenarioSpec(id=f"m7-temporal-probe-{packet.lane_id}"),
        diff=packet.diff_ref if packet.target_mode == "change" else None,
    )
    hidden_variant = str(cell["variant"])
    outcome = "supported" if hidden_variant == "defect" else "rejected"
    attempt = AttemptEvidence(
        evidence_id=f"evidence-{packet.lane_id}",
        target_id=target.target_id,
        hypothesis_id=admitted.campaign.hypotheses[0].hypothesis_id,
        attempt_ref=f"attempt-{packet.lane_id}-1",
        execution_record_ref=f"evidence/{packet.lane_id}/execution-record.json",
        outcome=outcome,
        evidence_refs=(f"evidence/{packet.lane_id}/oracle.json",),
        claim_boundary="local fixture and deterministic auditor receipt only",
        rationale=(
            "Auditor oracle records the preregistered temporal perturbation observation"
            if hidden_variant == "defect"
            else "Matched control receipt records no temporal contract violation"
        ),
        accountable=True,
        execution_identity_sha256=sha256(
            f"m7-execution-identity-{packet.lane_id}".encode("utf-8")
        ).hexdigest(),
    )
    final_package, reduction = reduce_attempt_evidence(compiled.package, attempt)
    adjudication = _adjudicate_lane(
        packet,
        hidden_variant,
        admitted,
        final_package,
        reduction,
    )
    if adjudication["agreement"] is not True:
        raise M7QualificationError((f"lane {packet.lane_id} adjudication disagreed",))
    return M7LaneResult(
        lane_id=packet.lane_id,
        cell_id=cell_id,
        target_mode=packet.target_mode,
        repetition=repetition,
        hidden_variant=hidden_variant,
        packet=packet,
        admitted_package=admitted,
        final_package=final_package,
        attempt=attempt,
        adjudication=adjudication,
    )


def _neutral_change_inputs(target: ChangeTarget) -> tuple[BehaviorDelta, ContractDrift]:
    drift_id = "drift-" + _short_digest(target.target_id)
    return (
        BehaviorDelta(
            delta_id="delta-" + _short_digest(target.target_id),
            target_id=target.target_id,
            subject="WeatherService.current",
            before="returns within the caller budget",
            after="may wait before returning",
            source_fact_ids=("fact-service-operation",),
            confidence=0.75,
            contract_drift_id=drift_id,
            rationale="Neutral change input describes a temporal contract question only.",
        ),
        ContractDrift(
            drift_id=drift_id,
            contract_id="contract-" + _short_digest(target.target_id),
            before="dependency returns within the caller budget",
            after="dependency may wait before returning",
            delta="synchronous temporal assumption requires a bounded probe",
            source_fact_ids=("fact-service-operation",),
            rationale="Neutral inferred drift; no execution outcome is supplied.",
        ),
    )


def _adjudicate_lane(
    packet: M7VerificationPacket,
    hidden_variant: str,
    admitted: DiscoveryCampaignPackage,
    final_package: DiscoveryCampaignPackage,
    reduction: Any,
) -> dict[str, Any]:
    expected = "supported" if hidden_variant == "defect" else "rejected"
    finding = reduction.finding
    checks = {
        "mode_bound": packet.target_mode in _MODES,
        "hypothesis_frozen_before_oracle": admitted.campaign.hypotheses[0].status == "frozen",
        "plan_admitted_before_oracle": admitted.campaign.attack_plans[0].status == "admitted",
        "accountable_receipt": final_package.attempts[0].accountable is True,
        "expected_local_conclusion": finding is not None and finding.conclusion == expected,
        "no_residual_for_accountable": not final_package.campaign.residual_risks,
    }
    return {
        "auditor_id": "m7-independent-adjudicator-v1",
        "agreement": all(checks.values()),
        "expected_local_conclusion": expected,
        "checks": checks,
        "claim_boundary": "local fixture, campaign package, and deterministic auditor receipt only",
    }


def _contradictory_preflight(context_path: Path) -> dict[str, Any]:
    target = ProjectTarget(
        target_id="m7-preflight-contradictory",
        source_origin="https://example.invalid/aiverify-m7-fixture",
        source_commit="synchronous-weather-v1",
        worktree="/workspace/aiverify-m7-fixture",
        scope=("weather-service", "systemui-consumer"),
        discovery_budget=1,
    )
    graph = load_context_manifest(context_path, target).graph
    contradictory_facts = tuple(
        _contradictory_fact(fact) if fact.fact_id == "fact-sync-call" else fact
        for fact in graph.facts
    )
    from aiverify.discovery import QualityContextGraph

    contradictory_graph = QualityContextGraph(
        graph_id=graph.graph_id,
        target_id=graph.target_id,
        facts=contradictory_facts,
        nodes=graph.nodes,
        edges=graph.edges,
    )
    try:
        created = create_campaign("campaign-preflight", target, contradictory_graph)
        freeze_campaign_hypothesis(created)
        return {
            "status": "fail",
            "formal_denominator": False,
            "side_effects": True,
            "reason": "contradictory context was accepted",
        }
    except (DiscoveryContractError, M7QualificationError) as error:
        return {
            "status": "rejected",
            "formal_denominator": False,
            "side_effects": False,
            "reason": str(error),
            "route": "exclude_before_formal_invocation",
        }


def _contradictory_fact(fact):
    from dataclasses import replace

    return replace(
        fact,
        value="contradictory",
        status="contradictory",
        source_kind="observed",
        source_version="m7-contradictory-preflight",
        confidence=0.2,
    )


def _aggregate(
    manifest: M7QualificationManifest,
    lanes: tuple[M7LaneResult, ...],
    preflight: Mapping[str, Any],
    leakage_audit: Mapping[str, Any],
) -> dict[str, Any]:
    if len(lanes) != 12:
        raise M7QualificationError(("aggregate requires twelve lanes",))
    cells: dict[str, dict[str, Any]] = {}
    for cell_id in _CELL_IDS:
        subset = [lane for lane in lanes if lane.cell_id == cell_id]
        cells[cell_id] = {
            "target_mode": subset[0].target_mode if subset else None,
            "variant": subset[0].hidden_variant if subset else None,
            "planned_lanes": 3,
            "observed_lanes": len(subset),
            "admitted_attacks": sum(
                lane.admitted_package.campaign.attack_plans[0].status == "admitted"
                for lane in subset
            ),
            "accountable_lanes": sum(lane.attempt.accountable for lane in subset),
            "retry_count": sum(1 for lane in subset if lane.attempt.attempt_ref.endswith("-2")),
            "local_conclusions": [
                lane.conclusion
                for lane in sorted(subset, key=lambda item: item.repetition)
            ],
            "adjudication_agreements": sum(
                bool(lane.adjudication["agreement"]) for lane in subset
            ),
        }
    mode_summary: dict[str, dict[str, Any]] = {}
    for mode in sorted(_MODES):
        subset = [lane for lane in lanes if lane.target_mode == mode]
        mode_summary[mode] = {
            "planned_lanes": 6,
            "observed_lanes": len(subset),
            "accountable_lanes": sum(lane.attempt.accountable for lane in subset),
            "defect_conclusions": sum(lane.conclusion == "supported" for lane in subset),
            "control_conclusions": sum(lane.conclusion == "rejected" for lane in subset),
        }
    route = (
        "proceed_to_bounded_runtime_probe"
        if all(item["accountable_lanes"] == 6 for item in mode_summary.values())
        and leakage_audit.get("status") == "pass"
        and preflight.get("status") == "rejected"
        else "hold_for_discovery_contract_or_evidence_gap"
    )
    return {
        "qualification_id": manifest.qualification_id,
        "planned_lanes": 12,
        "observed_lanes": len(lanes),
        "accountable_lanes": sum(lane.attempt.accountable for lane in lanes),
        "retry_count": sum(1 for lane in lanes if lane.attempt.attempt_ref.endswith("-2")),
        "cells": cells,
        "modes": mode_summary,
        "defect_supporting_conclusions": sum(
            lane.conclusion == "supported"
            for lane in lanes
            if lane.hidden_variant == "defect"
        ),
        "matched_control_non_supporting_conclusions": sum(
            lane.conclusion == "rejected"
            for lane in lanes
            if lane.hidden_variant == "control"
        ),
        "adjudication_agreements": sum(bool(lane.adjudication["agreement"]) for lane in lanes),
        "contradictory_preflight_excluded": (
            preflight.get("status") == "rejected"
            and preflight.get("formal_denominator") is False
        ),
        "next_route": route,
        "claim_boundary": "local fixture and discovery/admission/evidence seam only",
    }


def _manifest_errors(document: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if document.get("status") != "frozen":
        errors.append("manifest must be frozen before formal lanes")
    cells = document.get("cells", [])
    ids = [str(cell.get("cell_id")) for cell in cells]
    if tuple(ids) != _CELL_IDS:
        errors.append("cells must be exactly change/project defect/control in frozen order")
    if len(set(ids)) != len(ids):
        errors.append("cell ids must be unique")
    for cell in cells:
        if cell.get("target_mode") not in _MODES or cell.get("variant") not in _VARIANTS:
            errors.append(f"cell {cell.get('cell_id')} has invalid mode or variant")
        if cell.get("repetitions") != 3:
            errors.append(f"cell {cell.get('cell_id')} must have exactly three repetitions")
    if document.get("policy", {}).get("planned_lanes") != 12:
        errors.append("manifest planned_lanes must equal twelve")
    blinding = document.get("policy", {}).get("blinding", {})
    for field in (
        "withhold_variant",
        "withhold_expected_evidence",
        "withhold_verdict",
        "network_disabled",
    ):
        if blinding.get(field) is not True:
            errors.append(f"blinding policy requires {field}")
    retry = document.get("policy", {}).get("retry", {})
    if (
        retry.get("max_attempts_per_lane") != 1
        or retry.get("no_retry_after_accountable") is not True
    ):
        errors.append("M7 formal lanes must be single-attempt and non-retryable")
    contradiction = document.get("contradictory_preflight", {})
    if contradiction.get("formal_denominator") is not False:
        errors.append("contradictory preflight must remain outside formal denominator")
    return errors


def _cell_lane_ids(manifest: M7QualificationManifest, cell: Mapping[str, Any]) -> tuple[str, ...]:
    # The manifest order is stable; derive the range from the cell's index.
    index = manifest.cells.index(cell)
    start = 1 + sum(int(item["repetitions"]) for item in manifest.cells[:index])
    return tuple(f"lane-{number:02d}" for number in range(start, start + int(cell["repetitions"])))


def _cell_repetition(
    lane_id: str,
    manifest: M7QualificationManifest,
    cell: Mapping[str, Any],
) -> int:
    return int(lane_id.split("-")[-1]) - sum(
        int(item["repetitions"]) for item in manifest.cells[: manifest.cells.index(cell)]
    )


def _packet_leakage(document: Mapping[str, Any]) -> tuple[str, ...]:
    text = json.dumps(document, ensure_ascii=False, sort_keys=True).lower()
    return tuple(term for term in _FORBIDDEN_PACKET_TERMS if term in text)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise M7QualificationError((f"duplicate manifest key: {key}",))
        result[key] = value
    return result


def _render_schema_error(error: Any) -> str:
    path = ".".join(str(item) for item in error.absolute_path) or "<root>"
    return f"schema {path}: {error.message}"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_sha256(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _short_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()[:16]


def _required_text(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise M7QualificationError((f"{field} must be non-empty",))


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )
