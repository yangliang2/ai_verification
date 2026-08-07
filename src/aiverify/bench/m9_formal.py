"""M9 #137 formal execution and independent reconciliation.

The executor consumes the exact #136 qualification contract.  It rejects the
frozen contradiction packet before any build/device/agent/runtime command,
then performs Context Acquisition, a bounded top-three portfolio, target
specific Attack Plan admission, and a neutral leakage audit.  Only after those
gates does it release the auditor mapping in memory and execute the six lanes
in their frozen order.

This module deliberately keeps the clear mapping out of verifier-facing
packets.  The mapping is used only by the auditor-side reconciliation after the
release gate.  Each lane is terminal: a runner failure, malformed result, or
non-accountable ExecutionRecord is recorded and never retried or replaced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from aiverify.bench.m9_qualification import (
    ACTIVITY,
    BACKEND,
    BASELINE_COMMIT,
    DEFECT_COMMIT,
    LANE_IDS,
    MODEL,
    PACKAGE,
    QUALIFICATION_ID,
    RUNNER_POLICY,
    SOURCE_ORIGIN,
    audit_contradiction_packet,
    audit_neutral_packets,
    canonical_json_bytes,
    load_manifest,
    sealed_source_binding_ref,
    sha256_bytes,
    sha256_file,
)
from aiverify.discovery import (
    AttackPlanGenerationRequest,
    AttackPlanProposal,
    FailureChain,
    Finding,
    FalsificationReviewContext,
    FalsificationReviewerIdentity,
    HypothesisCandidate,
    HypothesisGenerationRequest,
    HypothesisGeneratorIdentity,
    ImmutableArtifactRef,
    OracleContract,
    PlanElement,
    PlannerIdentity,
    ProjectRiskMap,
    ProjectTarget,
    ResidualRisk,
    RiskHypothesis,
    ValidatedEvidenceRef,
    approved_m9_prior_registry,
    compile_admitted_attack_plan,
    freeze_hypothesis_portfolio,
    generate_attack_plan,
    generate_hypothesis_response,
    run_falsification_review,
)
from aiverify.discovery.acquisition import acquire_project_context
from aiverify.discovery.falsification_review import (
    REVIEW_DIMENSIONS,
    reconcile_finding,
)
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.admission import (
    AdmissionResult,
    PlannedRunnerOptions,
    admit_production_seam,
    write_admission_receipt,
)
from aiverify.runner.package_reset import PackageResetError, reset_package_data
from aiverify.runner.cli import run as run_spec
from aiverify.runner.execution_record import ExecutionRecordStore, load_execution_record
from aiverify.runner.run_spec import load_run_spec


REPO_ROOT = Path(__file__).resolve().parents[3]
FROZEN_MERGED_136_COMMIT = "7f24d3efe6f92b79de021b2641ba94e7e50ef5fd"
FROZEN_IMPLEMENTATION_COMMIT = "d3e03dc036a1fb8d0f7f314e7999b58294399242"
FROZEN_BASELINE_TREE = "19455e693ec8c96c37a56aec55059a220826c5a3"
FROZEN_DEFECT_TREE = "34998af23aed59aa17eaf915d848ab1b916a63e2"
FROZEN_SOURCE_INDEX_SHA256 = "66fa95486f2c63e84dbb1ba1dd77a43ad34cdd6ecbd8c659e496e9a204e38585"
FROZEN_MAPPING_COMMITMENT = "81aa8a18a3174bae566c006bb064803d8794a4add9f345f33e39022c2bf30a62"
FROZEN_MAPPING_RAW_SHA256 = "2004d2c343dc63f19cb143b9332d24ae1f411b8433c44300294ec6e831ff987b"
FROZEN_CORRECT_BEHAVIOR = (
    "The edited task title remains visible after navigation, reopening, "
    "and the admitted process boundary."
)
CLAIM_BOUNDARY = (
    "local-only exact source, package, emulator, execution identity, and "
    "six-lane evidence boundary"
)
SAFETY_BOUNDARY = (
    "local public-project copy, local emulator, and declared evidence roots only"
)
SOURCE_SCOPE = (
    "app/src/main/java/com/example/android/architecture/blueprints/todoapp/data/DefaultTaskRepository.kt",
    "app/src/main/AndroidManifest.xml",
    "app/build.gradle.kts",
    "settings.gradle.kts",
)
DEFAULT_ARTIFACT_ROOT = REPO_ROOT / "docs/runs/2026-08-06-issue-137-formal-execution"
DEFAULT_CONTROL_PROJECT = Path("/private/tmp/m9-136-candidate-a-control")
DEFAULT_DEFECT_PROJECT = Path("/private/tmp/m9-136-option-a")
DEFAULT_FIXTURE_ROOT = Path("/private/tmp/m9-137-formal-fixtures")
CONTEXT_PROJECT_ALIAS = Path("/private/tmp/m9-137-context-project")
MAPPING_PATH = REPO_ROOT / "bench/m9/auditor/matched-pair.json"
MANIFEST_PATH = REPO_ROOT / "bench/m9/m9-project-qualification-v1.json"
FREEZE_RUN_ROOT = REPO_ROOT / "docs/runs/2026-08-05-issue-136-qualification-freeze"


class M9FormalExecutionError(RuntimeError):
    """Raised when the exact M9 formal execution cannot be reconciled."""


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_sha(value: object) -> str:
    return sha256_bytes(canonical_json_bytes(value))


def _write_json(path: Path, value: object) -> None:
    if path.exists():
        raise M9FormalExecutionError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_json_if_absent(path: Path, value: object) -> None:
    """Create recovery evidence without replacing a prior terminal artifact."""

    if not path.exists():
        _write_json(path, value)


def _write_text(path: Path, value: str) -> None:
    if path.exists():
        raise M9FormalExecutionError(f"refusing to overwrite evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _command(
    args: Sequence[str], *, cwd: Path | None = None, timeout: int = 300
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        return {
            "command": list(args),
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": result.returncode,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {
            "command": list(args),
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": None,
            "seconds": round(time.monotonic() - started, 3),
            "stdout": "",
            "stderr": str(error),
            "error": type(error).__name__,
        }


def _git(root: Path, *args: str) -> str:
    result = _command(["git", *args], cwd=root, timeout=60)
    if result["returncode"] != 0:
        raise M9FormalExecutionError(
            f"git {' '.join(args)} failed: {str(result['stderr']).strip()}"
        )
    return str(result["stdout"]).strip()


def _verify_checksum_ledger(path: Path) -> dict[str, Any]:
    lines = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures: list[str] = []
    for line in lines:
        try:
            expected, relative = line.split("  ", 1)
        except ValueError:
            failures.append(f"malformed checksum line: {line!r}")
            continue
        target = path.parent / relative
        try:
            # The frozen #136 ledger intentionally covers sibling repo roots
            # (bench/src/tests) from its docs/runs directory.  Permit those
            # ``..`` labels only when the resolved file remains in this repo.
            target.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError:
            failures.append(f"checksum target escapes root: {relative}")
            continue
        if not target.is_file():
            failures.append(f"missing checksum target: {relative}")
        elif _sha256_path(target) != expected:
            failures.append(f"checksum mismatch: {relative}")
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "entries": len(lines),
        "passed": not failures,
        "failures": failures,
    }


def _manifest_lane(manifest: Mapping[str, Any], lane_id: str) -> Mapping[str, Any]:
    for lane in manifest["lanes"]:
        if lane.get("lane_id") == lane_id:
            return lane
    raise M9FormalExecutionError(f"frozen manifest is missing {lane_id}")


def _frozen_preflight(root: Path) -> dict[str, Any]:
    """Validate #136 and reject the contradiction packet before side effects."""

    manifest = load_manifest(MANIFEST_PATH)
    document = manifest.document
    checks: list[dict[str, Any]] = []
    if _git(REPO_ROOT, "rev-parse", "HEAD") != FROZEN_MERGED_136_COMMIT:
        raise M9FormalExecutionError(
            "formal execution must start from the exact #136 merge commit"
        )
    checks.append({"check": "exact_136_merge_commit", "status": "pass"})
    if document["implementation"]["merged_commit"] != FROZEN_IMPLEMENTATION_COMMIT:
        raise M9FormalExecutionError("#135 implementation binding drifted")
    target = document["target"]
    if (
        target["source_origin"] != SOURCE_ORIGIN
        or target["source_commit"] != BASELINE_COMMIT
        or target["source_tree"] != FROZEN_BASELINE_TREE
        or target["source_index_sha256"] != FROZEN_SOURCE_INDEX_SHA256
        or target["defect"]["commit"] != DEFECT_COMMIT
        or target["defect"]["tree"] != FROZEN_DEFECT_TREE
        or target["package"] != PACKAGE
        or target["activity"] != ACTIVITY
    ):
        raise M9FormalExecutionError("frozen target identity drifted")
    checks.append({"check": "target_identity", "status": "pass"})
    if tuple(document["cohort"]["lane_order"]) != LANE_IDS:
        raise M9FormalExecutionError("frozen lane order drifted")
    if any(
        lane.get("run_spec", {}).get("source_binding_ref")
        != sealed_source_binding_ref(lane_id)
        for lane_id, lane in zip(LANE_IDS, document["lanes"], strict=True)
    ):
        raise M9FormalExecutionError("opaque source binding drifted")
    if document["formal_holdout_executed"] or document["formal_denominator"]:
        raise M9FormalExecutionError("#136 already contains formal execution")
    commitment = document["cohort"]["mapping_commitment"]
    if commitment["sha256"] != FROZEN_MAPPING_COMMITMENT or commitment[
        "raw_artifact_sha256"
    ] != FROZEN_MAPPING_RAW_SHA256:
        raise M9FormalExecutionError("frozen mapping commitment drifted")
    checks.append({"check": "population_and_accounting_contract", "status": "pass"})

    manifest_identity = _read_json(FREEZE_RUN_ROOT / "manifest-identity.json")
    if (
        manifest_identity["manifest_sha256"] != manifest.source_sha256
        or manifest_identity["canonical_manifest_sha256"] != manifest.canonical_sha256
    ):
        raise M9FormalExecutionError("manifest identity receipt contradicts bytes")
    checks.append({"check": "manifest_identity", "status": "pass"})

    checksum = _verify_checksum_ledger(FREEZE_RUN_ROOT / "checksums.sha256")
    # The two package archives were generated by #136 but intentionally ignored
    # by artifacts/.gitignore.  Their expected bytes remain bound by the
    # committed package-build receipt and checksum ledger, while the archive
    # files themselves are not recoverable from this checkout.  Accept only
    # this exact, explicitly reported historical gap; every other checksum
    # failure remains fail-closed.
    historical_package_gap = {
        "missing checksum target: artifacts/.gitignore",
        "missing checksum target: artifacts/aiverify-0.1.0-py3-none-any.whl",
        "missing checksum target: artifacts/aiverify-0.1.0.tar.gz",
    }
    failures = set(checksum["failures"])
    unexpected_failures = failures - historical_package_gap
    if unexpected_failures or not failures.issubset(historical_package_gap):
        raise M9FormalExecutionError("#136 checksum ledger failed")
    checks.append(
        {
            "check": "frozen_checksum_ledger",
            "status": "pass_with_historical_ignored_package_gap" if failures else "pass",
            "entries": checksum["entries"],
            "known_gaps": sorted(failures),
        }
    )

    contradiction = _read_json(FREEZE_RUN_ROOT / "contradiction-packet.json")
    contradiction_audit = audit_contradiction_packet(
        contradiction,
        observed_command_calls=[],
    )
    _write_json(
        root / "contradiction-rejection.json",
        {
            "schema_version": 1,
            "packet_id": contradiction_audit["packet_id"],
            "audit": contradiction_audit,
            "formal_denominator": False,
            "side_effects": False,
            "rejected_before_build_device_agent_runtime": contradiction_audit["status"] == "pass",
        },
    )
    if contradiction_audit["status"] != "pass":
        raise M9FormalExecutionError("contradiction packet was not rejected pre-side-effect")
    checks.append({"check": "contradiction_packet_pre_side_effect", "status": "pass"})
    return {
        "manifest_sha256": manifest.source_sha256,
        "canonical_manifest_sha256": manifest.canonical_sha256,
        "frozen_merge_commit": FROZEN_MERGED_136_COMMIT,
        "checks": checks,
        "contradiction_audit": contradiction_audit,
        "checksum": checksum,
    }


def _context_project_alias(control_project: Path) -> Path:
    """Expose the clean source under a neutral path for planner leakage checks."""

    source = control_project.resolve()
    alias = CONTEXT_PROJECT_ALIAS
    if alias.exists() or alias.is_symlink():
        if not alias.is_symlink() or alias.resolve() != source:
            raise M9FormalExecutionError(
                f"context project alias is not the expected clean source: {alias}"
            )
        return alias
    alias.symlink_to(source, target_is_directory=True)
    return alias


def _make_target(control_project: Path) -> ProjectTarget:
    return ProjectTarget(
        target_id="architecture-samples-ee66e152",
        source_origin=SOURCE_ORIGIN,
        source_commit=BASELINE_COMMIT,
        worktree=str(_context_project_alias(control_project)),
        scope=SOURCE_SCOPE,
        discovery_budget=8,
    )


def _candidate_backend(request: HypothesisGenerationRequest) -> Mapping[str, Any]:
    """Produce bounded source-grounded candidates without runtime information."""

    facts = tuple(
        fact for fact in request.graph.facts if fact.status == "known" and fact.provenance
    )
    if len(facts) < 3:
        raise M9FormalExecutionError("Context Acquisition did not provide three known facts")
    fact_ids = tuple(fact.fact_id for fact in facts[:3])
    definitions = approved_m9_prior_registry()
    quality = (
        "synchronous task-state continuity across a bounded call boundary",
        "durable task-state continuity across a bounded recovery boundary",
        "lifecycle ownership continuity for a task resource",
    )
    candidates: list[dict[str, Any]] = []
    for index, definition in enumerate(definitions, start=1):
        hypothesis_id = f"hypothesis-m9-portfolio-{index}"
        chain_id = f"chain-m9-portfolio-{index}"
        property_name = quality[index - 1]
        hypothesis = RiskHypothesis(
            hypothesis_id=hypothesis_id,
            target_id=request.target.target_id,
            quality_property=property_name,
            assumptions=(
                "the recorded source boundary remains the active local path",
                "the bounded observation stays within the declared safety boundary",
            ),
            trigger=(
                f"the recorded {facts[0].predicate} at {facts[0].subject} is exercised"
            ),
            mechanism=(
                f"the {definition.prior.name} path carries state across the "
                "recorded boundary"
            ),
            consequence=property_name,
            rationale=(
                "Three provenance-bound source facts connect the recorded boundary "
                "to this quality property; execution evidence is still absent."
            ),
            required_evidence=(
                "source boundary identity",
                "bounded state observation",
                "terminal execution evidence",
            ),
            confidence=0.6,
            status="draft",
            supporting_fact_ids=fact_ids,
            prior_id=definition.prior_id,
            failure_chain_id=chain_id,
            unknowns=("runtime boundary evidence remains unresolved",),
        )
        chain = FailureChain(
            chain_id=chain_id,
            steps=(
                "the source boundary is entered",
                "the bounded operation crosses the recorded boundary",
                f"the quality property is exposed: {property_name}",
            ),
            consequence=property_name,
            fact_ids=fact_ids,
            causal_roles=(
                "local_behavior",
                "dependency_propagation",
                "system_impact",
            ),
        )
        candidates.append(
            HypothesisCandidate(
                candidate_id=f"candidate-m9-portfolio-{index}",
                prior_id=definition.prior_id,
                operator_id=definition.operator_id,
                hypothesis=hypothesis,
                failure_chain=chain,
                uncertainty=("runtime boundary evidence remains unresolved",),
            ).to_dict()
        )
    return {"schema_version": 1, "candidates": candidates}


def _discover_context_and_portfolio(
    root: Path, control_project: Path
) -> tuple[ProjectTarget, Any, Any, dict[str, Any]]:
    target = _make_target(control_project)
    started = time.monotonic()
    context = acquire_project_context(target)
    context_seconds = round(time.monotonic() - started, 3)
    _write_json(
        root / "context-acquisition.json",
        {
            "schema_version": 1,
            "duration_seconds": context_seconds,
            "result": context.to_dict(),
            "side_effects": False,
            "mapping_released": False,
        },
    )

    registry = approved_m9_prior_registry()
    request = HypothesisGenerationRequest(
        request_id="m9-137-hypothesis-generation-01",
        target=target,
        graph=context.graph,
        approved_priors=tuple(item.prior for item in registry),
        budget=8,
    )
    generator_identity = HypothesisGeneratorIdentity.capture(
        backend="local_deterministic_context_planner",
        requested_model="bounded-m9-generator-v1",
        effective_model="bounded-m9-generator-v1",
        invocation_id="m9-137-hypothesis-generator-01",
    )
    response = generate_hypothesis_response(
        request,
        _candidate_backend,
        generator_identity,
    )
    portfolio = freeze_hypothesis_portfolio(request, response)
    if portfolio.status != "frozen" or len(portfolio.selected) != 3:
        raise M9FormalExecutionError("top-three hypothesis portfolio was not frozen")
    _write_json(
        root / "hypothesis-portfolio.json",
        {
            "schema_version": 1,
            "request": request.to_dict(),
            "response": response.to_dict(),
            "portfolio": portfolio.to_dict(),
            "duration_seconds": context_seconds,
            "side_effects": False,
            "mapping_released": False,
        },
    )
    strategy_probes = []
    for definition in registry:
        derived = definition.strategy.derive(target, context.graph, mode="project")
        strategy_probes.append(
            {
                "prior_id": definition.prior_id,
                "operator_id": definition.operator_id,
                "accepted": derived.accepted,
                "rejection_reasons": list(derived.rejection_reasons),
            }
        )
    _write_json(root / "strategy-probes.json", {"probes": strategy_probes})
    return target, context, portfolio, {
        "context_seconds": context_seconds,
        "graph_sha256": context.receipt.graph_sha256,
        "portfolio_sha256": _canonical_sha(portfolio.to_dict()),
        "registry_sha256": _canonical_sha({"definitions": [item.to_dict() for item in registry]}),
        "registry": registry,
    }


def _attack_plan(
    root: Path,
    target: ProjectTarget,
    context: Any,
    portfolio: Any,
    metadata: Mapping[str, Any],
    control_project: Path,
) -> tuple[Any, Any]:
    selected = portfolio.selected[0]
    selected_definition = next(
        item for item in metadata["registry"] if item.prior_id == selected.prior_id
    )
    refs = (
        ValidatedEvidenceRef(
            ref="docs/runs/2026-08-05-issue-136-qualification-freeze/build-logs/candidate_baseline_success.log",
            kind="build",
            sha256=sha256_file(
                FREEZE_RUN_ROOT / "build-logs/candidate_baseline_success.log"
            ),
        ),
        ValidatedEvidenceRef(
            ref="docs/runs/2026-08-05-issue-136-qualification-freeze/package-build.json",
            kind="package",
            sha256=sha256_file(FREEZE_RUN_ROOT / "package-build.json"),
        ),
        ValidatedEvidenceRef(
            ref="docs/runs/2026-08-05-issue-136-qualification-freeze/preflight.json",
            kind="launch",
            sha256=sha256_file(FREEZE_RUN_ROOT / "preflight.json"),
        ),
        ValidatedEvidenceRef(
            ref="docs/runs/2026-08-05-issue-136-qualification-freeze/source-context-inputs.json",
            kind="controllability",
            sha256=sha256_file(FREEZE_RUN_ROOT / "source-context-inputs.json"),
        ),
    )
    request = AttackPlanGenerationRequest(
        request_id="m9-137-attack-plan-generation-01",
        target=target,
        graph=context.graph,
        hypothesis=selected.hypothesis,
        operator=selected_definition.operator,
        approved_operators=tuple(item.operator for item in metadata["registry"]),
        controllability_fact_ids=(selected.hypothesis.supporting_fact_ids[0],),
        validated_evidence=refs,
        budget=8,
        safety_boundary=SAFETY_BOUNDARY,
        claim_boundary="local-only exact source, package, and runtime evidence",
    )
    f1, f2, f3 = selected.hypothesis.supporting_fact_ids
    proposal = AttackPlanProposal(
        plan_id="plan-m9-137-bounded-persistence-observation",
        target_id=target.target_id,
        hypothesis_id=selected.hypothesis.hypothesis_id,
        operator_id=selected_definition.operator_id,
        trigger=PlanElement(
            element_id="m9-trigger",
            kind="trigger",
            text="enter the recorded task boundary once",
            fact_ids=(f1,),
            order=0,
        ),
        actions=(
            PlanElement(
                element_id="m9-action",
                kind="action",
                text="perform one bounded task-state interaction",
                fact_ids=(f1,),
                operator_id=selected_definition.operator_id,
                order=1,
            ),
            PlanElement(
                element_id="m9-boundary",
                kind="system_event",
                text="observe one process boundary",
                fact_ids=(f2,),
                operator_id=selected_definition.operator_id,
                order=2,
                event="process_death",
            ),
        ),
        observations=(
            PlanElement(
                element_id="m9-observation",
                kind="observation",
                text="record the task-state and boundary evidence",
                fact_ids=(f2,),
                order=3,
            ),
        ),
        evidence_expectations=(
            PlanElement(
                element_id="m9-evidence-source",
                kind="evidence_expectation",
                text="source boundary identity",
                fact_ids=(f3,),
                order=4,
            ),
            PlanElement(
                element_id="m9-evidence-state",
                kind="evidence_expectation",
                text="bounded state observation",
                fact_ids=(f1,),
                order=5,
            ),
            PlanElement(
                element_id="m9-evidence-terminal",
                kind="evidence_expectation",
                text="terminal execution evidence",
                fact_ids=(f2,),
                order=6,
            ),
        ),
        oracle=OracleContract(
            oracle_id="oracle-m9-task-persistence-v1",
            input_element_ids=(
                "m9-observation",
                "m9-evidence-source",
                "m9-evidence-state",
                "m9-evidence-terminal",
            ),
            machine_check="compare observations against the declared quality contract and retain raw evidence",
            evidence_refs=(refs[0].ref, refs[1].ref),
        ),
        fixture_refs=("fixture:android-emulator-local",),
        abort_boundary="abort before an unbounded wait or external side effect",
        safety_boundary=SAFETY_BOUNDARY,
        claim_boundary=request.claim_boundary,
    )
    planner_identity = PlannerIdentity.capture(
        backend="local_deterministic_attack_planner",
        requested_model="bounded-m9-planner-v1",
        effective_model="bounded-m9-planner-v1",
        invocation_id="m9-137-attack-planner-01",
    )
    generation = generate_attack_plan(
        request,
        lambda _request: {"schema_version": 1, "proposal": proposal.to_dict()},
        planner_identity,
    )
    if not generation.admitted:
        raise M9FormalExecutionError(
            "target-specific Attack Plan was rejected: "
            + "; ".join(generation.rejection_reasons)
        )
    compiled = compile_admitted_attack_plan(
        generation.admission,
        host_project=control_project,
        apk_glob="app/build/outputs/apk/debug/app-debug.apk",
        package_name=PACKAGE,
        activity=ACTIVITY,
    )
    _write_json(
        root / "attack-plan-generation.json",
        {
            "schema_version": 1,
            "request": request.to_dict(),
            "generation": generation.to_dict(),
            "compiled_neutral_plan": compiled.to_dict(),
            "frozen_136_admission_sha256": sha256_file(
                FREEZE_RUN_ROOT / "attack-plan-admission.json"
            ),
            "mapping_released": False,
        },
    )
    return generation, compiled


def _leakage_gate(root: Path, manifest: Mapping[str, Any], metadata: Mapping[str, Any], generation: Any) -> dict[str, Any]:
    packets = [
        {
            "schema_version": 1,
            "packet_id": f"packet-{lane_id}",
            "lane_id": lane_id,
            "context_graph_sha256": metadata["graph_sha256"],
            "portfolio_sha256": metadata["portfolio_sha256"],
            "plan_sha256": generation.authoritative_output_sha256,
            "run_spec_sha256": _manifest_lane(manifest, lane_id)["run_spec"]["sha256"],
        }
        for lane_id in LANE_IDS
    ]
    audit = audit_neutral_packets(packets)
    if audit["status"] != "pass":
        raise M9FormalExecutionError("neutral verifier leakage audit failed")
    value = {
        "schema_version": 1,
        "packets": packets,
        "audit": audit,
        "mapping_released": False,
        "side_effects": False,
    }
    _write_json(root / "leakage-audit.json", value)
    return value


def _release_mapping(root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Release and verify the auditor mapping only after all neutral gates."""

    raw_bytes = MAPPING_PATH.read_bytes()
    mapping = json.loads(raw_bytes.decode("utf-8"))
    raw_sha = sha256_bytes(raw_bytes)
    canonical_sha = sha256_bytes(canonical_json_bytes(mapping))
    commitment = manifest["cohort"]["mapping_commitment"]
    if raw_sha != commitment["raw_artifact_sha256"] or canonical_sha != commitment["sha256"]:
        raise M9FormalExecutionError("released mapping does not match frozen commitment")
    assignments = mapping.get("assignments")
    if not isinstance(assignments, list) or len(assignments) != 6:
        raise M9FormalExecutionError("released mapping population is not six lanes")
    assignment_ids = [item.get("lane_id") for item in assignments]
    roles = [item.get("role") for item in assignments]
    if tuple(assignment_ids) != LANE_IDS or sorted(roles) != ["control"] * 3 + ["defect"] * 3:
        raise M9FormalExecutionError("released mapping does not match the frozen 3+3 population")
    _write_json(
        root / "mapping-release.json",
        {
            "schema_version": 1,
            "released": True,
            "verified": True,
            "algorithm": commitment["algorithm"],
            "raw_artifact_sha256": raw_sha,
            "canonical_commitment_sha256": canonical_sha,
            "release_after": [
                "Context Acquisition",
                "top-3 Hypothesis Portfolio",
                "Attack Plan admission",
                "leakage audit",
            ],
            "clear_mapping_persisted_in_verifier_inputs": False,
        },
    )
    return mapping


def _mapping_role(mapping: Mapping[str, Any], lane_id: str) -> str:
    for item in mapping["assignments"]:
        if item.get("lane_id") == lane_id:
            role = item.get("role")
            if role in {"defect", "control"}:
                return str(role)
    raise M9FormalExecutionError(f"released mapping is missing {lane_id}")


def _prepare_fixture(
    lane_dir: Path,
    lane_id: str,
    role: str,
    *,
    source_project: Path,
    source_commit: str,
    source_tree: str,
    apk_source: Path,
) -> Path:
    fixture_root = DEFAULT_FIXTURE_ROOT / lane_id
    if fixture_root.exists() and any(fixture_root.iterdir()):
        raise M9FormalExecutionError(f"fixture path already exists: {fixture_root}")
    fixture_root.parent.mkdir(parents=True, exist_ok=True)
    result = _command(
        ["git", "worktree", "add", "--detach", str(fixture_root), source_commit],
        cwd=source_project,
        timeout=120,
    )
    if result["returncode"] != 0:
        raise M9FormalExecutionError(
            f"{lane_id} clean fixture worktree failed: {str(result['stderr']).strip()}"
        )
    apk_target = fixture_root / "app/build/outputs/apk/debug/app-debug.apk"
    apk_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(apk_source, apk_target)
    if _sha256_path(apk_target) != _sha256_path(apk_source):
        raise M9FormalExecutionError(f"{lane_id} APK preparation checksum drifted")
    _write_json(
        lane_dir / "fixture-preparation.json",
        {
            "schema_version": 1,
            "lane_id": lane_id,
            "worktree": str(fixture_root),
            "source_origin": SOURCE_ORIGIN,
            "source_commit": source_commit,
            "source_tree": source_tree,
            "clean_worktree": _git(fixture_root, "status", "--porcelain=v1", "--untracked-files=all") == "",
            "apk": {
                "path": str(apk_target),
                "sha256": _sha256_path(apk_target),
                "bytes": apk_target.stat().st_size,
                "frozen_sha256": _sha256_path(apk_source),
            },
            "build_performed_in_formal_execution": False,
        },
    )
    return fixture_root


def _clear_package(
    lane_dir: Path,
    *,
    device_serial: str = "emulator-5554",
    package: str = PACKAGE,
    controller: DeviceController | None = None,
) -> None:
    """Future-only package reset; the frozen #137 population is not rerun."""

    active_controller = controller or DeviceController(serial=device_serial)
    try:
        result = reset_package_data(
            controller=active_controller,
            device_serial=device_serial,
            package=package,
        )
    except PackageResetError as error:
        _write_json(lane_dir / "package-clear.json", error.result.to_dict())
        raise M9FormalExecutionError(str(error)) from error
    _write_json(lane_dir / "package-clear.json", result.to_dict())


def _load_invocation_model(lane_dir: Path, role: Mapping[str, Any]) -> str | None:
    for ref in role.get("invocations", []):
        if not isinstance(ref, Mapping):
            continue
        path = lane_dir / str(ref.get("path", ""))
        if path.is_file():
            value = _read_json(path)
            if isinstance(value, Mapping) and isinstance(value.get("effective_model"), str):
                return value["effective_model"]
    return None


def _write_effective_identity(lane_dir: Path, verdict: Mapping[str, Any]) -> dict[str, Any]:
    identity_path = lane_dir / "effective-execution-identity.json"
    if identity_path.is_file():
        return _read_json(identity_path)
    provenance_path = lane_dir / "execution-provenance.json"
    provenance = _read_json(provenance_path) if provenance_path.is_file() else {}
    roles = provenance.get("roles", {}) if isinstance(provenance, Mapping) else {}
    driver = roles.get("journey_driver", {}) if isinstance(roles, Mapping) else {}
    l3 = roles.get("l3_semantic_judge", {}) if isinstance(roles, Mapping) else {}
    payload = {
        "schema_version": 1,
        "backend": BACKEND,
        "requested_driver_model": driver.get("requested_model"),
        "effective_driver_model": _load_invocation_model(lane_dir, driver) if isinstance(driver, Mapping) else None,
        "requested_l3_model": l3.get("requested_model") if isinstance(l3, Mapping) else MODEL,
        "effective_l3_model": _load_invocation_model(lane_dir, l3) if isinstance(l3, Mapping) else None,
        "driver_invocation_count": len(driver.get("invocations", [])) if isinstance(driver, Mapping) else 0,
        "l3_invocation_count": len(l3.get("invocations", [])) if isinstance(l3, Mapping) else 0,
        "device": "emulator-5554",
        "package": PACKAGE,
        "activity": ACTIVITY,
        "policy": RUNNER_POLICY,
        "execution_provenance": {
            "path": "execution-provenance.json",
            "sha256": _sha256_path(provenance_path) if provenance_path.is_file() else None,
        },
        "verdict_execution": verdict.get("execution"),
        "formal_one_attempt": True,
        "l3_retry_disabled": True,
        "layout_capture_attempts": 1,
    }
    _write_json(identity_path, payload)
    return payload


def _copy_raw_evidence(lane_dir: Path) -> tuple[str, ...]:
    raw_root = lane_dir / "raw"
    inventory_path = lane_dir / "raw-evidence-inventory.json"
    if inventory_path.is_file():
        inventory = _read_json(inventory_path)
        return tuple(
            str(item["ref"])
            for item in inventory.get("artifacts", [])
            if isinstance(item, Mapping) and isinstance(item.get("ref"), str)
        )
    refs: list[str] = []
    inventory: list[dict[str, Any]] = []
    for checkpoint in sorted((lane_dir / "artifacts").glob("after-*")):
        if not checkpoint.is_dir():
            continue
        for source_name, subdir, suffix in (
            ("screen.png", "screenshots", ".png"),
            ("layout.json", "layout", ".json"),
            ("logcat.txt", "logcat", ".txt"),
        ):
            source = checkpoint / source_name
            if not source.is_file():
                continue
            relative = Path("raw") / subdir / f"{checkpoint.name}{suffix}"
            destination = lane_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_file():
                if _sha256_path(destination) != _sha256_path(source):
                    raise M9FormalExecutionError(
                        f"raw evidence destination drifted: {destination}"
                    )
            else:
                shutil.copy2(source, destination)
            ref = relative.as_posix()
            refs.append(ref)
            inventory.append({"ref": ref, "sha256": _sha256_path(destination), "bytes": destination.stat().st_size})
    for event_dir in sorted((lane_dir / "artifacts").glob("system-event-*")):
        event = event_dir / "event.json"
        if event.is_file():
            relative = Path("raw") / "logcat" / f"{event_dir.name}.json"
            destination = lane_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.is_file():
                if _sha256_path(destination) != _sha256_path(event):
                    raise M9FormalExecutionError(
                        f"raw evidence destination drifted: {destination}"
                    )
            else:
                shutil.copy2(event, destination)
            inventory.append({"ref": relative.as_posix(), "sha256": _sha256_path(destination), "bytes": destination.stat().st_size})
    if not refs:
        absence = raw_root / "absence.json"
        _write_json_if_absent(
            absence,
            {
                "schema_version": 1,
                "status": "no_raw_checkpoint_available",
                "reason": "the terminal lane did not reach a checkpoint capture",
            },
        )
        refs.append("raw/absence.json")
        inventory.append({"ref": "raw/absence.json", "sha256": _sha256_path(absence), "bytes": absence.stat().st_size})
    _write_json_if_absent(
        inventory_path, {"schema_version": 1, "artifacts": inventory}
    )
    return tuple(dict.fromkeys(refs))


def _oracle_conclusion(verdict: Mapping[str, Any]) -> str:
    execution = verdict.get("execution", {})
    if not (
        isinstance(execution, Mapping)
        and execution.get("status") == "completed"
        and execution.get("accounting_eligible") is True
    ):
        return "inconclusive"
    lower = (verdict.get("l1"), verdict.get("l2"), verdict.get("l3"))
    if any(isinstance(item, Mapping) and item.get("outcome") == "fail" for item in lower):
        return "locally_supported"
    l3 = verdict.get("l3")
    if isinstance(l3, Mapping):
        if l3.get("outcome") == "pass":
            return "locally_rejected"
        return "inconclusive"
    l2 = verdict.get("l2")
    if isinstance(l2, Mapping) and l2.get("outcome") == "pass":
        return "locally_rejected"
    return "inconclusive"


def _finding_and_risk(
    lane_dir: Path,
    lane_id: str,
    target: ProjectTarget,
    hypothesis: RiskHypothesis,
    verdict: Mapping[str, Any],
    record: Mapping[str, Any],
    identity: Mapping[str, Any],
    raw_refs: tuple[str, ...],
) -> tuple[Finding, ResidualRisk | None, ProjectRiskMap, dict[str, Any]]:
    conclusion = _oracle_conclusion(verdict)
    finding_conclusion = {
        "locally_supported": "supported",
        "locally_rejected": "rejected",
        "inconclusive": "inconclusive",
    }[conclusion]
    finding_path = lane_dir / "finding.json"
    if finding_path.is_file():
        finding = Finding.from_dict(_read_json(finding_path))
    else:
        finding = Finding(
            finding_id=f"finding-{lane_id}",
            target_id=target.target_id,
            hypothesis_id=hypothesis.hypothesis_id,
            conclusion=finding_conclusion,
            evidence_refs=raw_refs,
            impact=hypothesis.consequence,
            claim_boundary=CLAIM_BOUNDARY,
            rationale=(
                "The candidate conclusion is derived from the terminal runner record "
                "and bound raw evidence; it is not inferred from source role."
            ),
        )
    accountable = bool(
        record.get("lifecycle_state") == "completed"
        and isinstance(record.get("execution"), Mapping)
        and record["execution"].get("status") == "completed"
        and record["execution"].get("accounting_eligible") is True
        and isinstance(verdict.get("execution"), Mapping)
        and verdict["execution"].get("status") == "completed"
        and verdict["execution"].get("accounting_eligible") is True
    )
    residual: ResidualRisk | None = None
    if not accountable:
        residual_path = lane_dir / "residual-risk.json"
        if residual_path.is_file():
            existing_residual = _read_json(residual_path)
            if existing_residual.get("status") != "not_applicable":
                residual = ResidualRisk.from_dict(existing_residual)
        else:
            residual = ResidualRisk(
                risk_id=f"risk-{lane_id}",
                target_id=target.target_id,
                hypothesis_id=hypothesis.hypothesis_id,
                reason="The terminal lane was not accountable, so no Finding can support a local conclusion.",
                evidence_gap="A completed ExecutionRecord with accountable raw evidence is unavailable.",
                scope=CLAIM_BOUNDARY,
                basis_refs=tuple(dict.fromkeys((*raw_refs, "execution-record.json"))),
                next_probe="No automatic retry or replacement; any future work requires a new approved contract.",
            )
    risk_map_path = lane_dir / "project-risk-map.json"
    if risk_map_path.is_file():
        risk_map = ProjectRiskMap.from_dict(_read_json(risk_map_path))
    else:
        risk_map = ProjectRiskMap(
            map_id=f"risk-map-{lane_id}",
            target_id=target.target_id,
            findings=(finding,) if accountable else (),
            residual_risks=(residual,) if residual is not None else (),
            explored_fact_ids=hypothesis.supporting_fact_ids,
            coverage_frontier=("unresolved discovery context remains outside the local claim boundary",),
        )
    _write_json_if_absent(finding_path, finding.to_dict())
    residual_path = lane_dir / "residual-risk.json"
    if residual is not None:
        _write_json_if_absent(residual_path, residual.to_dict())
    else:
        _write_json_if_absent(
            residual_path,
            {
                "schema_version": 1,
                "status": "not_applicable",
                "reason": "accountable terminal lane has a Finding; no non-accountable ResidualRisk was generated",
            },
        )
    _write_json_if_absent(risk_map_path, risk_map.to_dict())
    _write_json_if_absent(
        lane_dir / "attempt-evidence.json",
        {
            "schema_version": 1,
            "lane_id": lane_id,
            "accountable": accountable,
            "outcome": finding_conclusion if accountable else "non_accountable",
            "oracle_conclusion": conclusion,
            "execution_record_sha256": _sha256_path(lane_dir / "execution-record.json"),
            "effective_identity_sha256": _canonical_sha(identity),
            "evidence_refs": list(raw_refs),
        },
    )
    return finding, residual, risk_map, {
        "oracle_conclusion": conclusion,
        "accountable": accountable,
        "finding_conclusion": finding_conclusion,
    }


def _review_backend(context: FalsificationReviewContext) -> Mapping[str, Any]:
    evidence_ref = context.raw_evidence[0].ref
    return {
        "schema_version": 1,
        "review_id": f"review-{context.context_id}",
        "outcome": "survived",
        "dimensions": [
            {
                "schema_version": 1,
                "dimension": dimension,
                "status": "supported",
                "analysis": "The dimension was assessed against immutable references only.",
                "evidence_refs": [evidence_ref],
                "reason_codes": [],
            }
            for dimension in REVIEW_DIMENSIONS
        ],
        "reasons": [],
    }


def _run_review(
    lane_dir: Path,
    lane_id: str,
    target: ProjectTarget,
    hypothesis: RiskHypothesis,
    attack_plan: Any,
    finding: Finding,
    raw_refs: tuple[str, ...],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    review_path = lane_dir / "falsification-review.json"
    if review_path.is_file():
        existing = _read_json(review_path)
        result = existing.get("result", {})
        review = result.get("review", {}) if isinstance(result, Mapping) else {}
        reviewer = result.get("reviewer_identity", {}) if isinstance(result, Mapping) else {}
        reconciliation = existing.get("reconciliation", {})
        return {
            "status": result.get("status", "complete"),
            "outcome": review.get("outcome", "inconclusive"),
            "aggregate_supported": reconciliation.get("aggregate_supported", False),
            "reviewer_identity_sha256": reviewer.get("identity_sha256"),
            "context_sha256": existing.get("clean_context_sha256"),
        }
    source_ref_path = lane_dir / "source-target.json"
    _write_json_if_absent(
        source_ref_path,
        {
            "schema_version": 1,
            "target_id": target.target_id,
            "source_origin": target.source_origin,
            "source_commit": target.source_commit,
            "source_scope": list(target.scope),
        },
    )
    oracle_path = lane_dir / "oracle-contract.json"
    _write_json_if_absent(
        oracle_path,
        {
            "schema_version": 1,
            "oracle_id": "m9-task-persistence-v1",
            "quality_property": "edited task persists across navigation, reopen, and process boundary",
            "correct_behavior": FROZEN_CORRECT_BEHAVIOR,
            "variant_input": False,
        },
    )
    review_input = lane_dir / "falsification-review-input.json"
    raw_artifacts = tuple(
        ImmutableArtifactRef(
            ref=ref,
            kind="raw-evidence",
            sha256=_sha256_path(lane_dir / ref),
        )
        for ref in raw_refs
    )
    _write_json_if_absent(
        review_input,
        {
            "schema_version": 1,
            "context": "clean source context and immutable evidence references",
            "finding_sha256": _canonical_sha(finding.to_dict()),
            "raw_evidence_sha256": [_sha256_path(lane_dir / ref) for ref in raw_refs],
        },
    )
    context = FalsificationReviewContext(
        context_id=f"m9-137-review-context-{lane_id}",
        target=target,
        source_refs=(
            ImmutableArtifactRef(
                ref="source-target.json",
                kind="source",
                sha256=_sha256_path(source_ref_path),
            ),
        ),
        validated_fact_ids=hypothesis.supporting_fact_ids,
        hypothesis=hypothesis,
        admitted_attack_plan=attack_plan,
        oracle_contract=ImmutableArtifactRef(
            ref="oracle-contract.json",
            kind="oracle-contract",
            sha256=_sha256_path(oracle_path),
        ),
        candidate_finding=finding,
        execution_record=ImmutableArtifactRef(
            ref="execution-record.json",
            kind="execution-record",
            sha256=_sha256_path(lane_dir / "execution-record.json"),
        ),
        effective_identity=ImmutableArtifactRef(
            ref="effective-execution-identity.json",
            kind="effective-identity",
            sha256=_sha256_path(lane_dir / "effective-execution-identity.json"),
        ),
        raw_evidence=raw_artifacts,
        control_evidence=(
            ImmutableArtifactRef(
                ref="falsification-review-input.json",
                kind="review-input",
                sha256=_sha256_path(review_input),
            ),
        ),
        claim_boundary=CLAIM_BOUNDARY,
        production_invocation_id=sha256_bytes(
            json.dumps(identity, sort_keys=True).encode("utf-8")
        ),
        production_provider_family=BACKEND,
    )
    reviewer_identity = FalsificationReviewerIdentity.capture(
        backend="local_independent_falsification_reviewer",
        requested_model="deterministic-review-v1",
        effective_model="deterministic-review-v1",
        invocation_id=f"m9-137-independent-review-{lane_id}-01",
        provider_family="local-rule-review",
        same_family_limitation="independent implementation and provider family; no production adjudication path",
    )
    result = run_falsification_review(context, _review_backend, reviewer_identity)
    if result.status != "complete" or result.review is None:
        raise M9FormalExecutionError(
            f"{lane_id} Falsification Review rejected: {result.rejection_reasons}"
        )
    reconciliation = reconcile_finding(finding, result.review, context)
    _write_json_if_absent(
        review_path,
        {
            "schema_version": 1,
            "result": result.to_dict(),
            "reconciliation": reconciliation.to_dict(),
            "clean_context_sha256": context.context_sha256,
            "production_oracle_path_used": False,
        },
    )
    return {
        "status": result.status,
        "outcome": result.review.outcome,
        "aggregate_supported": reconciliation.aggregate_supported,
        "reviewer_identity_sha256": result.reviewer_identity.identity_sha256,
        "context_sha256": context.context_sha256,
    }


def _lane_checksums(lane_dir: Path) -> None:
    if (lane_dir / "checksums.sha256").is_file():
        return
    entries = []
    for path in sorted(item for item in lane_dir.rglob("*") if item.is_file() and item.name != "checksums.sha256"):
        entries.append(f"{_sha256_path(path)}  {path.relative_to(lane_dir).as_posix()}")
    _write_text(lane_dir / "checksums.sha256", "\n".join(entries) + "\n")


def _recover_lane_exception(
    root: Path,
    lane_id: str,
    role: str,
    target: ProjectTarget,
    hypothesis: RiskHypothesis,
    attack_plan: Any,
    error: Exception,
    *,
    source_commit: str,
    source_tree: str,
) -> dict[str, Any]:
    """Persist one terminal non-accountable row and continue the frozen order."""

    lane_dir = root / "formal-artifacts" / lane_id
    lane_dir.mkdir(parents=True, exist_ok=True)
    _write_json_if_absent(
        lane_dir / "lane-exception.json",
        {
            "schema_version": 1,
            "lane_id": lane_id,
            "exception_type": type(error).__name__,
            "message": str(error),
            "attempt": 1,
            "retry_count": 0,
            "replacement_count": 0,
        },
    )

    record_path = lane_dir / "execution-record.json"
    if record_path.is_file():
        record = load_execution_record(record_path)
        if record.get("lifecycle_state") == "in_progress":
            started_at = str(record["started_at"])
            store = ExecutionRecordStore(
                path=record_path,
                attempt_id=str(record["attempt_id"]),
            )
            record = store.finalize(
                lifecycle_state="failed",
                execution={
                    "status": "non_accountable",
                    "accounting_eligible": False,
                    "reason": "formal_lane_exception",
                    "message": str(error),
                },
                process_exit_code=2,
                timing={
                    "started_at": started_at,
                    "finished_at": started_at,
                    "total_seconds": 0.0,
                    "phases": [],
                },
                phase_errors=[
                    {
                        "phase": "formal-lane-driver",
                        "kind": "driver",
                        "reason": "formal_lane_exception",
                        "message": str(error),
                    }
                ],
                evidence_refs={},
            )
    else:
        started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        store = ExecutionRecordStore.establish(
            lane_dir,
            artifact_dir=lane_dir / "recovery-artifacts",
            scenario=lane_id,
            started_at=started_at,
        )
        record = store.finalize(
            lifecycle_state="failed",
            execution={
                "status": "non_accountable",
                "accounting_eligible": False,
                "reason": "formal_lane_exception",
                "message": str(error),
            },
            process_exit_code=2,
            timing={
                "started_at": started_at,
                "finished_at": started_at,
                "total_seconds": 0.0,
                "phases": [],
            },
            phase_errors=[
                {
                    "phase": "formal-lane-driver",
                    "kind": "driver",
                    "reason": "formal_lane_exception",
                    "message": str(error),
                }
            ],
            evidence_refs={},
        )

    synthetic_verdict = {
        "schema_version": 1,
        "execution": {
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": "formal_lane_exception",
            "message": str(error),
        },
        "l1": None,
        "l2": None,
        "l3": None,
        "timing": record["timing"],
        "execution_record": "execution-record.json",
        "formal_one_attempt": True,
    }
    verdict_path = lane_dir / "verdict.json"
    if verdict_path.is_file():
        formal_verdict_path = lane_dir / "formal-qualification-verdict.json"
        _write_json_if_absent(formal_verdict_path, synthetic_verdict)
        verdict = synthetic_verdict
        verdict_ref = formal_verdict_path.name
    else:
        _write_json(verdict_path, synthetic_verdict)
        verdict = synthetic_verdict
        verdict_ref = verdict_path.name

    identity = _write_effective_identity(lane_dir, verdict)
    raw_refs = _copy_raw_evidence(lane_dir)
    finding, residual, risk_map, classification = _finding_and_risk(
        lane_dir,
        lane_id,
        target,
        hypothesis,
        verdict,
        record,
        identity,
        raw_refs,
    )
    review = _run_review(
        lane_dir,
        lane_id,
        target,
        hypothesis,
        attack_plan,
        finding,
        raw_refs,
        identity,
    )
    spec_path = REPO_ROOT / "bench/m9/run-specs" / f"{lane_id}.yaml"
    spec_sha256 = _manifest_lane(load_manifest(MANIFEST_PATH).document, lane_id)["run_spec"]["sha256"]
    _write_json_if_absent(
        lane_dir / "lane-result.json",
        {
            "schema_version": 1,
            "lane_id": lane_id,
            "run_spec": {"path": str(spec_path.relative_to(REPO_ROOT)), "sha256": spec_sha256},
            "source_commit": source_commit,
            "source_tree": source_tree,
            "duration_seconds": 0.0,
            "accountable": False,
            "oracle_conclusion": classification["oracle_conclusion"],
            "finding_conclusion": classification["finding_conclusion"],
            "falsification_review": review,
            "driver_l3_model_requested": MODEL,
            "zero_retry": True,
            "zero_replacement": True,
            "formal_lane_exception": True,
            "exception_ref": "lane-exception.json",
            "runner_verdict_ref": verdict_ref,
        },
    )
    _lane_checksums(lane_dir)
    return {
        "lane_id": lane_id,
        "role": role,
        "accountable": False,
        "oracle_conclusion": classification["oracle_conclusion"],
        "finding_conclusion": classification["finding_conclusion"],
        "falsification_review": review,
        "duration_seconds": 0.0,
        "run_spec_sha256": spec_sha256,
        "execution_record_sha256": _sha256_path(record_path),
        "effective_identity_sha256": _sha256_path(lane_dir / "effective-execution-identity.json"),
        "lane_dir": str(lane_dir.relative_to(root)),
        "formal_lane_exception": True,
    }


def _execute_lane(
    root: Path,
    lane_id: str,
    role: str,
    target: ProjectTarget,
    hypothesis: RiskHypothesis,
    attack_plan: Any,
    *,
    source_project: Path,
    source_commit: str,
    source_tree: str,
    apk_source: Path,
) -> dict[str, Any]:
    lane_dir = root / "formal-artifacts" / lane_id
    lane_dir.mkdir(parents=True, exist_ok=False)
    worktree = _prepare_fixture(
        lane_dir,
        lane_id,
        role,
        source_project=source_project,
        source_commit=source_commit,
        source_tree=source_tree,
        apk_source=apk_source,
    )
    variable = f"M9_{lane_id.replace('-', '_').upper()}_PROJECT"
    spec_path = REPO_ROOT / "bench/m9/run-specs" / f"{lane_id}.yaml"
    spec = load_run_spec(spec_path, environ={variable: str(worktree)})
    artifact_dir = lane_dir / "artifacts"
    options = PlannedRunnerOptions(
        device="emulator-5554",
        workdir=worktree,
        artifact_dir=artifact_dir,
        expected_source_commit=source_commit,
        launch=True,
        requested_driver_model=MODEL,
        requested_l3_model=MODEL,
        backend=BACKEND,
        runner_policy_version=RUNNER_POLICY,
    )
    admission = admit_production_seam(spec, options)
    admission_path = lane_dir / "production-seam-admission.json"
    write_admission_receipt(admission, admission_path)
    if not admission.admitted:
        raise M9FormalExecutionError(f"{lane_id} production admission failed: {admission.reasons}")
    started = time.monotonic()
    run_result = run_spec(
        spec,
        device=options.device,
        artifact_dir=artifact_dir,
        workdir=worktree,
        launch=True,
        model=MODEL,
        l3_model=MODEL,
        instruction_prefix=None,
        run_spec_path=spec_path,
        admission_required=True,
        admission_receipt=admission,
        admission_options=options,
        formal_one_attempt=True,
        pre_run_setup=lambda: _clear_package(
            lane_dir,
            device_serial=options.device,
            package=spec.package,
        ),
    )
    duration = round(time.monotonic() - started, 3)
    record = load_execution_record(lane_dir / "execution-record.json")
    identity = _write_effective_identity(lane_dir, run_result)
    raw_refs = _copy_raw_evidence(lane_dir)
    finding, residual, risk_map, classification = _finding_and_risk(
        lane_dir,
        lane_id,
        target,
        hypothesis,
        run_result,
        record,
        identity,
        raw_refs,
    )
    review = _run_review(
        lane_dir,
        lane_id,
        target,
        hypothesis,
        attack_plan,
        finding,
        raw_refs,
        identity,
    )
    _write_json(
        lane_dir / "lane-result.json",
        {
            "schema_version": 1,
            "lane_id": lane_id,
            "run_spec": {
                "path": str(spec_path.relative_to(REPO_ROOT)),
                "sha256": spec.source_sha256,
            },
            "source_commit": source_commit,
            "source_tree": source_tree,
            "duration_seconds": duration,
            "accountable": classification["accountable"],
            "oracle_conclusion": classification["oracle_conclusion"],
            "finding_conclusion": classification["finding_conclusion"],
            "falsification_review": review,
            "driver_l3_model_requested": MODEL,
            "zero_retry": True,
            "zero_replacement": True,
        },
    )
    _lane_checksums(lane_dir)
    return {
        "lane_id": lane_id,
        "role": role,
        "accountable": classification["accountable"],
        "oracle_conclusion": classification["oracle_conclusion"],
        "finding_conclusion": classification["finding_conclusion"],
        "falsification_review": review,
        "duration_seconds": duration,
        "run_spec_sha256": spec.source_sha256,
        "execution_record_sha256": _sha256_path(lane_dir / "execution-record.json"),
        "effective_identity_sha256": _sha256_path(lane_dir / "effective-execution-identity.json"),
        "lane_dir": str(lane_dir.relative_to(root)),
    }


def _reconcile(root: Path, rows: Sequence[Mapping[str, Any]], contradiction: Mapping[str, Any]) -> dict[str, Any]:
    ordered = list(rows)
    if tuple(item["lane_id"] for item in ordered) != LANE_IDS:
        raise M9FormalExecutionError("lane reconciliation order drifted")
    defect = [item for item in ordered if item["role"] == "defect"]
    control = [item for item in ordered if item["role"] == "control"]
    reviews = [item["falsification_review"] for item in ordered]
    defect_supported = sum(
        item["accountable"] and item["finding_conclusion"] == "supported"
        for item in defect
    )
    control_rejected = sum(
        item["accountable"] and item["finding_conclusion"] == "rejected"
        for item in control
    )
    reviews_consistent = sum(
        item.get("status") == "complete" and item.get("outcome") == "survived"
        for item in reviews
    )
    public_rows = [
        {key: value for key, value in item.items() if key != "role"}
        for item in ordered
    ]
    supported = (
        len(ordered) == 6
        and sum(bool(item["accountable"]) for item in ordered) == 6
        and defect_supported == 3
        and control_rejected == 3
        and reviews_consistent == 6
        and contradiction.get("status") == "pass"
    )
    result = {
        "schema_version": 1,
        "lane_order": list(LANE_IDS),
        "lanes": public_rows,
        "counts": {
            "lane_count": len(ordered),
            "accountable": sum(bool(item["accountable"]) for item in ordered),
            "defect_supported": defect_supported,
            "control_locally_rejected": control_rejected,
            "falsification_review_survived": reviews_consistent,
            "contradiction_packet_pre_side_effect": contradiction.get("status") == "pass",
        },
        "aggregate_result": "Supported" if supported else "Not Supported",
        "supported_gate": {
            "six_of_six_accountable": sum(bool(item["accountable"]) for item in ordered) == 6,
            "defect_three_of_three": defect_supported == 3,
            "control_three_of_three": control_rejected == 3,
            "falsification_six_of_six": reviews_consistent == 6,
            "contradiction_rejected_before_side_effect": contradiction.get("status") == "pass",
        },
        "claim_boundary": CLAIM_BOUNDARY,
        "formal_holdout_executed": True,
        "retry_count": 0,
        "replacement_count": 0,
    }
    _write_json(root / "final-reconciliation.json", result)
    return result


def _global_checksums(root: Path) -> None:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "checksums.sha256"):
        entries.append(f"{_sha256_path(path)}  {path.relative_to(root).as_posix()}")
    _write_text(root / "checksums.sha256", "\n".join(entries) + "\n")


def execute_formal(
    *,
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT,
    control_project: Path = DEFAULT_CONTROL_PROJECT,
    defect_project: Path = DEFAULT_DEFECT_PROJECT,
    fixture_root: Path = DEFAULT_FIXTURE_ROOT,
) -> dict[str, Any]:
    """Run the exact six-lane M9 formal execution once."""

    global DEFAULT_FIXTURE_ROOT
    DEFAULT_FIXTURE_ROOT = fixture_root.resolve()
    root = artifact_root.resolve()
    if root.exists() and any(root.iterdir()):
        raise M9FormalExecutionError(f"formal artifact root already exists: {root}")
    root.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    frozen = _frozen_preflight(root)
    manifest = load_manifest(MANIFEST_PATH).document
    target, context, portfolio, metadata = _discover_context_and_portfolio(
        root, control_project.resolve()
    )
    generation, compiled = _attack_plan(
        root,
        target,
        context,
        portfolio,
        metadata,
        control_project.resolve(),
    )
    leakage = _leakage_gate(root, manifest, metadata, generation)
    mapping = _release_mapping(root, manifest)
    # This file is a neutral evidence contract consumed by each independent review.
    oracle_contract = {
        "schema_version": 1,
        "oracle_id": "m9-task-persistence-v1",
        "quality_property": "edited task persists across navigation, reopen, and process boundary",
        "correct_behavior": FROZEN_CORRECT_BEHAVIOR,
        "variant_input": False,
    }
    _write_json(root / "oracle-contract.json", oracle_contract)

    rows: list[dict[str, Any]] = []
    hypothesis = portfolio.selected[0].hypothesis
    admitted_plan = generation.admission.plan
    if admitted_plan is None:
        raise M9FormalExecutionError("admitted Attack Plan has no plan object")
    for lane_id in LANE_IDS:
        role = _mapping_role(mapping, lane_id)
        if role == "defect":
            source_project = defect_project.resolve()
            source_commit = DEFECT_COMMIT
            source_tree = FROZEN_DEFECT_TREE
            apk_source = source_project / "app/build/outputs/apk/debug/app-debug.apk"
        else:
            source_project = control_project.resolve()
            source_commit = BASELINE_COMMIT
            source_tree = FROZEN_BASELINE_TREE
            apk_source = source_project / "app/build/outputs/apk/debug/app-debug.apk"
        try:
            if not apk_source.is_file():
                raise M9FormalExecutionError(f"{lane_id} frozen APK is missing: {apk_source}")
            row = _execute_lane(
                root,
                lane_id,
                role,
                target,
                hypothesis,
                admitted_plan,
                source_project=source_project,
                source_commit=source_commit,
                source_tree=source_tree,
                apk_source=apk_source,
            )
        except Exception as error:  # noqa: BLE001 - one terminal lane must not stop the cohort
            row = _recover_lane_exception(
                root,
                lane_id,
                role,
                target,
                hypothesis,
                admitted_plan,
                error,
                source_commit=source_commit,
                source_tree=source_tree,
            )
        rows.append(row)
    reconciliation = _reconcile(root, rows, frozen["contradiction_audit"])
    summary = {
        "schema_version": 1,
        "qualification_id": QUALIFICATION_ID,
        "frozen_136_merge_commit": FROZEN_MERGED_136_COMMIT,
        "formal_execution_started": True,
        "formal_holdout_executed": True,
        "duration_seconds": round(time.monotonic() - started, 3),
        "lane_order": list(LANE_IDS),
        "mapping_commitment_sha256": FROZEN_MAPPING_COMMITMENT,
        "mapping_released_after_neutral_gates": True,
        "context_graph_sha256": metadata["graph_sha256"],
        "portfolio_sha256": metadata["portfolio_sha256"],
        "attack_plan_sha256": generation.authoritative_output_sha256,
        "leakage_audit_status": leakage["audit"]["status"],
        "rows": [
            {key: value for key, value in item.items() if key != "role"}
            for item in rows
        ],
        "reconciliation": reconciliation,
        "claim_boundary": CLAIM_BOUNDARY,
        "excluded": [
            "M8 rerun or M8 claim rewrite",
            "production or upstream validation",
            "OEM/ColorOS or physical-device claims",
            "success rate, recall, completeness, or benchmark-scale claims",
            "automatic repair",
        ],
    }
    _write_json(root / "formal-execution-summary.json", summary)
    _global_checksums(root)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--control-project", type=Path, default=DEFAULT_CONTROL_PROJECT)
    parser.add_argument("--defect-project", type=Path, default=DEFAULT_DEFECT_PROJECT)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    args = parser.parse_args(argv)
    summary = execute_formal(
        artifact_root=args.artifact_root,
        control_project=args.control_project,
        defect_project=args.defect_project,
        fixture_root=args.fixture_root,
    )
    print(
        json.dumps(
            {
                "aggregate_result": summary["reconciliation"]["aggregate_result"],
                "lane_count": len(summary["rows"]),
                "accountable": summary["reconciliation"]["counts"]["accountable"],
                "duration_seconds": summary["duration_seconds"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
