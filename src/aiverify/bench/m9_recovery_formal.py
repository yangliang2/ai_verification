"""One-shot formal consumer for the approved M9 recovery-v2 packet.

The consumer has two deliberately separate boundaries.  ``static_preflight``
is side-effect-free and is suitable for Phase A verification.  ``execute_formal``
first proves that the consumer itself is the clean merged ``origin/main``
revision, irreversibly claims the frozen formal namespace, rejects the
contradiction control, and then executes each of the six lanes exactly once.

No role assignment is placed in discovery, planning, runner, oracle, or review
inputs.  The released mapping is retained only by the auditor-side source
resolver and the later mechanical reconciliation input.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml

from aiverify.bench.m9_recovery_qualification import (
    ACTIVITY,
    APK_GLOB,
    BACKEND,
    CONTROL_APK_BYTES,
    CONTROL_APK_SHA256,
    CONTRADICTION_REQUIRED_FIELDS,
    DEFECT_APK_BYTES,
    DEFECT_APK_SHA256,
    DEFECT_COMMIT,
    DEFECT_TREE,
    DEVICE,
    FORMAL_ATTEMPT_ID,
    FORMAL_HYPOTHESIS_ID,
    LANE_IDS,
    LOCAL_CLAIM_BOUNDARY,
    PACKAGE,
    PROBE_TOKENS,
    PROJECT_TARGET_COMMIT,
    PROJECT_TARGET_ID,
    PROJECT_TARGET_TREE,
    QUALIFICATION_ID,
    R4_ARTIFACT_ROOT,
    R4_RUN_RECORD,
    RUNNER_POLICY,
    SOURCE_ORIGIN,
    audit_contradiction_packet,
    audit_neutral_packets,
    build_execution_review_summary,
    canonical_json_bytes,
    execute_falsification_review,
    load_auditor_mapping,
    load_manifest,
    sealed_source_binding_ref,
    sha256_bytes,
    sha256_file,
    validate_admission_receipts,
    validate_formal_attempt_row,
)
from aiverify.discovery import (
    AttackPlanGenerationRequest,
    AttackPlanProposal,
    FailureChain,
    HypothesisCandidate,
    HypothesisGenerationRequest,
    HypothesisGeneratorIdentity,
    OracleContract,
    PlanElement,
    PlannerIdentity,
    ProjectTarget,
    RiskHypothesis,
    ValidatedEvidenceRef,
    approved_m9_prior_registry,
    compile_admitted_attack_plan,
    freeze_hypothesis_portfolio,
    generate_attack_plan,
    generate_hypothesis_response,
)
from aiverify.discovery.acquisition import acquire_project_context
from aiverify.harness.device.controller import DeviceController
from aiverify.runner.admission import (
    AdmissionResult,
    PlannedRunnerOptions,
    admit_production_seam,
    write_admission_receipt,
)
from aiverify.runner.cli import run as run_spec
from aiverify.runner.execution_identity import ExecutionIdentityCollector
from aiverify.runner.execution_record import (
    ExecutionRecordStore,
    is_execution_record_accountable,
    load_execution_record,
    write_bytes_artifact,
    write_json_artifact,
)
from aiverify.runner.package_reset import PackageResetError, reset_package_data
from aiverify.runner.run_spec import RunSpec, load_run_spec


REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST_PATH = REPO_ROOT / "bench/m9/m9-recovery-project-qualification-v2.json"
MAPPING_PATH = REPO_ROOT / "bench/m9/recovery-v2/auditor/matched-pair.json"
R3_ROOT = (
    REPO_ROOT
    / "docs/runs/2026-08-07-issue-152-m9-r3-fresh-qualification-freeze"
)
FORMAL_ROOT = REPO_ROOT / R4_RUN_RECORD
FORMAL_ARTIFACT_ROOT = REPO_ROOT / R4_ARTIFACT_ROOT
R3_MERGE_COMMIT = "6ec408f1aec57adfcd90e0e25e2453a9eda05fc1"
FROZEN_MANIFEST_SHA256 = (
    "aa860f4b10144c2e6374912685ef914a420a234fc805d36cebb72b0c705629ad"
)
FROZEN_PACKET_COMMITMENT = (
    "a2ae1d8ca4902a500c67aa6107a0f42fe06a3948ca484305861d2d2670033225"
)
FROZEN_LEDGER_SHA256 = (
    "0d3b311387dae768cf361a1f7683605a97600851ccb1e38c8ce2632b3ee9dc47"
)
FROZEN_MAPPING_RAW_SHA256 = (
    "4da963ad23e5e8aca18e79328069a23a62a3071eb814d929246675fc7f4b84eb"
)
FROZEN_MAPPING_CANONICAL_SHA256 = (
    "d69c0421ed68bf7de020326043fcf787250abbdb9aa0c9a10ecc3a2cc1eba8a4"
)
FROZEN_CONTRADICTION_AUDIT_CANONICAL_SHA256 = (
    "ed594192326034c9a0eb576fbfa1fe76f29a0e5af5f1099074d2d187c9ab254e"
)
DEFAULT_PROJECT_TARGET = Path("/private/tmp/m9-r3-snapshot-b")
DEFAULT_CONTROL_APK = (
    DEFAULT_PROJECT_TARGET / "Jetchat/app/build/outputs/apk/debug/app-debug.apk"
)
DEFAULT_DEFECT_PROJECT = Path("/private/tmp/m9-r3-snapshot-a")
DEFAULT_DEFECT_APK = (
    DEFAULT_DEFECT_PROJECT / "Jetchat/app/build/outputs/apk/debug/app-debug.apk"
)
DEFAULT_SOURCE_ROOT = Path("/private/tmp/m9-r4-formal-sources")
SOURCE_SCOPE = (
    "Jetchat/app/src/main/java/com/example/compose/jetchat/conversation/UserInput.kt",
    "Jetchat/app/src/main/AndroidManifest.xml",
    "Jetchat/app/build.gradle.kts",
    "Jetchat/settings.gradle.kts",
    "Jetchat/gradle/libs.versions.toml",
    "LICENSE",
)
SAFETY_BOUNDARY = (
    "local public-project copy, local emulator, and declared evidence roots only"
)
_ROLE_LEAKAGE = re.compile(r"(?i)(?:\bdefect\b|\bcontrol\b|expected[_ ]result)")
_LAYOUT_CENTER = re.compile(r"^\[(\d+),(\d+)\]$")


class M9RecoveryFormalError(RuntimeError):
    """Raised when the one approved formal execution must fail closed."""


class FormalStage(IntEnum):
    """Irreversible ordering for the formal consumer's release gates."""

    CREATED = 0
    CONTRADICTION_REJECTED = 1
    CONTEXT_ACQUIRED = 2
    PORTFOLIO_FROZEN = 3
    PLAN_ADMITTED = 4
    LEAKAGE_AUDITED = 5
    MAPPING_RELEASED = 6
    ADMISSIONS_COMPLETE = 7
    EXECUTING = 8
    TERMINAL = 9


@dataclass
class FormalState:
    """In-memory monotonic guard against reordering, retry, or replacement."""

    stage: FormalStage = FormalStage.CREATED
    admitted_lanes: list[str] = field(default_factory=list)
    terminal_lanes: list[str] = field(default_factory=list)
    active_lane: str | None = None

    def advance(self, expected: FormalStage, target: FormalStage) -> None:
        if self.stage is not expected or target.value != expected.value + 1:
            raise M9RecoveryFormalError(
                f"formal stage transition rejected: {self.stage.name} -> {target.name}"
            )
        self.stage = target

    def admit(self, lane_id: str) -> None:
        if self.stage is not FormalStage.MAPPING_RELEASED:
            raise M9RecoveryFormalError("lane admission preceded mapping release")
        expected = LANE_IDS[len(self.admitted_lanes)]
        if lane_id != expected or lane_id in self.admitted_lanes:
            raise M9RecoveryFormalError("lane admission order/repetition drifted")
        self.admitted_lanes.append(lane_id)
        if tuple(self.admitted_lanes) == LANE_IDS:
            self.stage = FormalStage.ADMISSIONS_COMPLETE

    def start_lane(self, lane_id: str) -> None:
        if self.active_lane is not None:
            raise M9RecoveryFormalError("another formal lane is already active")
        if self.stage not in {FormalStage.ADMISSIONS_COMPLETE, FormalStage.EXECUTING}:
            raise M9RecoveryFormalError("formal lane started before all admissions")
        expected = LANE_IDS[len(self.terminal_lanes)]
        if lane_id != expected or lane_id in self.terminal_lanes:
            raise M9RecoveryFormalError("formal lane order/retry drifted")
        self.stage = FormalStage.EXECUTING
        self.active_lane = lane_id

    def finish_lane(self, lane_id: str) -> None:
        if self.active_lane != lane_id:
            raise M9RecoveryFormalError("terminal receipt does not match active lane")
        self.active_lane = None
        self.terminal_lanes.append(lane_id)
        if tuple(self.terminal_lanes) == LANE_IDS:
            self.stage = FormalStage.TERMINAL


@dataclass(frozen=True)
class FormalInputs:
    """External R3 products and the new R4 fixture namespace."""

    expected_consumer_commit: str
    project_target: Path = DEFAULT_PROJECT_TARGET
    control_apk: Path = DEFAULT_CONTROL_APK
    defect_project: Path = DEFAULT_DEFECT_PROJECT
    defect_apk: Path = DEFAULT_DEFECT_APK
    source_root: Path = DEFAULT_SOURCE_ROOT


@dataclass(frozen=True)
class SourceBinding:
    """One auditor-selected immutable source/APK pair without a role label."""

    project: Path
    commit: str
    tree: str
    apk: Path
    apk_bytes: int
    apk_sha256: str


@dataclass(frozen=True)
class AdmittedLane:
    """A neutral, production-admitted lane ready for one runner attempt."""

    frozen_path: Path
    spec: RunSpec
    options: PlannedRunnerOptions
    admission: AdmissionResult
    source: SourceBinding


@dataclass(frozen=True)
class EvidenceLineage:
    """The selected Risk Hypothesis and its acquired Context Facts."""

    hypothesis_id: str
    explored_fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.hypothesis_id != FORMAL_HYPOTHESIS_ID:
            raise M9RecoveryFormalError(
                "selected state-evolution hypothesis identity drifted"
            )
        if (
            not self.explored_fact_ids
            or len(set(self.explored_fact_ids)) != len(self.explored_fact_ids)
            or any(not fact_id.strip() for fact_id in self.explored_fact_ids)
        ):
            raise M9RecoveryFormalError(
                "selected state-evolution supporting facts are invalid"
            )


@dataclass(frozen=True)
class ExecutedLane:
    """Role-neutral material returned by one completed lane execution."""

    record: Mapping[str, Any]
    identity: Mapping[str, Any]
    finding_conclusion: str
    review: Mapping[str, Any]
    duration_seconds: float


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json_artifact(path, value)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_artifact(path, value.encode("utf-8"))


def _copy_artifact(source: Path, destination: Path) -> None:
    try:
        payload = source.read_bytes()
    except OSError as error:
        raise M9RecoveryFormalError(f"artifact cannot be read: {source}: {error}") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_artifact(destination, payload)


def _run(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    timeout: int = 300,
    check: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        receipt = {
            "command": list(args),
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": process.returncode,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": process.stdout,
            "stderr": process.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        receipt = {
            "command": list(args),
            "cwd": str(cwd) if cwd is not None else None,
            "returncode": None,
            "duration_seconds": round(time.monotonic() - started, 3),
            "stdout": "",
            "stderr": str(error),
            "error": type(error).__name__,
        }
    if check and receipt["returncode"] != 0:
        raise M9RecoveryFormalError(
            f"command failed: {' '.join(args)}: {str(receipt['stderr']).strip()}"
        )
    return receipt


def _git(root: Path, *args: str) -> str:
    return str(_run(["git", *args], cwd=root, timeout=60)["stdout"]).strip()


def _git_object_sha(commit: str, path: str) -> str:
    process = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
        timeout=60,
    )
    if process.returncode != 0:
        raise M9RecoveryFormalError(
            f"frozen git object is unavailable: {commit}:{path}"
        )
    return sha256_bytes(process.stdout)


def _verify_frozen_r3_ledger() -> dict[str, Any]:
    ledger = R3_ROOT / "checksums.sha256"
    if sha256_file(ledger) != FROZEN_LEDGER_SHA256:
        raise M9RecoveryFormalError("R3 checksum ledger bytes drifted")
    checked = 0
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        expected, separator, label = line.partition("  ")
        if separator != "  ":
            raise M9RecoveryFormalError("R3 checksum ledger is malformed")
        if label.startswith("../../../"):
            repository_path = label.removeprefix("../../../")
            actual = _git_object_sha(R3_MERGE_COMMIT, repository_path)
        else:
            path = (R3_ROOT / label).resolve()
            try:
                path.relative_to(REPO_ROOT)
            except ValueError as error:
                raise M9RecoveryFormalError("R3 ledger path escapes repository") from error
            actual = sha256_file(path)
        if actual != expected:
            raise M9RecoveryFormalError(f"R3 checksum mismatch: {label}")
        checked += 1
    return {"path": str(ledger.relative_to(REPO_ROOT)), "sha256": FROZEN_LEDGER_SHA256, "entries": checked}


def _repository_identity(expected_commit: str) -> dict[str, Any]:
    root = Path(_git(REPO_ROOT, "rev-parse", "--show-toplevel")).resolve()
    head = _git(REPO_ROOT, "rev-parse", "HEAD")
    upstream = _git(REPO_ROOT, "rev-parse", "origin/main")
    status = _git(REPO_ROOT, "status", "--porcelain=v1", "--untracked-files=all")
    if root != REPO_ROOT or head != expected_commit or upstream != expected_commit or status:
        raise M9RecoveryFormalError(
            "formal execution requires a clean worktree at the exact merged origin/main consumer commit"
        )
    return {
        "repository_root": str(root),
        "head": head,
        "origin_main": upstream,
        "status_sha256": sha256_bytes(status.encode("utf-8")),
        "consumer_path": str(Path(__file__).resolve().relative_to(REPO_ROOT)),
        "consumer_sha256": sha256_file(Path(__file__).resolve()),
    }


def static_preflight(*, require_formal_root_absent: bool = True) -> dict[str, Any]:
    """Validate the immutable R3 hand-off without device/model/runtime work."""

    manifest = load_manifest(MANIFEST_PATH, require_frozen=True)
    if manifest.source_sha256 != FROZEN_MANIFEST_SHA256:
        raise M9RecoveryFormalError("frozen manifest bytes drifted")
    if manifest.packet_commitment_sha256 != FROZEN_PACKET_COMMITMENT:
        raise M9RecoveryFormalError("frozen packet commitment drifted")
    if require_formal_root_absent and FORMAL_ROOT.exists():
        raise M9RecoveryFormalError("formal attempt namespace has already been claimed")
    ledger = _verify_frozen_r3_ledger()
    implementation = manifest.document.get("implementation", {})
    if implementation.get("formal_consumer_entrypoint") != (
        "python -m aiverify.bench.m9_recovery_formal"
    ):
        raise M9RecoveryFormalError("formal consumer entrypoint drifted")
    return {
        "schema_version": 1,
        "status": "passed",
        "side_effects": False,
        "device_calls": 0,
        "model_calls": 0,
        "formal_lane_attempts": 0,
        "manifest_sha256": manifest.source_sha256,
        "packet_commitment_sha256": manifest.packet_commitment_sha256,
        "mapping_raw_sha256": FROZEN_MAPPING_RAW_SHA256,
        "mapping_canonical_sha256": FROZEN_MAPPING_CANONICAL_SHA256,
        "r3_ledger": ledger,
    }


def _claim_formal_root(preflight: Mapping[str, Any], repository: Mapping[str, Any]) -> None:
    if FORMAL_ROOT.exists():
        raise M9RecoveryFormalError("formal attempt namespace already exists; retry is forbidden")
    FORMAL_ROOT.mkdir(parents=True, exist_ok=False)
    _write_json(
        FORMAL_ROOT / "formal-start.json",
        {
            "schema_version": 2,
            "formal_attempt_id": FORMAL_ATTEMPT_ID,
            "attempt_number": 1,
            "started_at": _utc_now(),
            "consumer": repository,
            "preflight": dict(preflight),
            "formal_execution_started": True,
            "lane_attempt_count_at_start": 0,
            "retry_count": 0,
            "replacement_count": 0,
            "discretionary_rerun_count": 0,
        },
    )


def _reject_contradiction(manifest: Mapping[str, Any]) -> dict[str, Any]:
    packet_path = R3_ROOT / "contradiction-packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    audit = audit_contradiction_packet(packet, observed_command_calls=[])
    expected = manifest["contradiction_packet"]["audit"]
    if audit != expected or tuple(audit.get("missing_fields", ())) != CONTRADICTION_REQUIRED_FIELDS:
        raise M9RecoveryFormalError("contradiction packet did not reproduce its frozen rejection")
    if sha256_bytes(canonical_json_bytes(audit)) != FROZEN_CONTRADICTION_AUDIT_CANONICAL_SHA256:
        raise M9RecoveryFormalError("contradiction audit canonical commitment drifted")
    _write_json(
        FORMAL_ROOT / "contradiction-rejection.json",
        {
            "schema_version": 2,
            "audit": audit,
            "packet": {
                "path": str(packet_path.relative_to(REPO_ROOT)),
                "sha256": sha256_file(packet_path),
            },
            "rejected_before_build_device_agent_runtime": True,
            "formal_denominator": False,
            "side_effects": False,
        },
    )
    return audit


def _verify_source(root: Path, *, commit: str, tree: str) -> dict[str, Any]:
    root = root.resolve()
    identity = {
        "path": str(root),
        "origin": _git(root, "remote", "get-url", "origin"),
        "commit": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "status": _git(root, "status", "--porcelain=v1", "--untracked-files=all"),
    }
    if (
        identity["origin"] != SOURCE_ORIGIN
        or identity["commit"] != commit
        or identity["tree"] != tree
        or identity["status"]
    ):
        raise M9RecoveryFormalError(f"source snapshot identity drifted: {root}")
    identity["status_sha256"] = sha256_bytes(b"")
    del identity["status"]
    return identity


def _make_target(project: Path) -> ProjectTarget:
    return ProjectTarget(
        target_id=PROJECT_TARGET_ID,
        source_origin=SOURCE_ORIGIN,
        source_commit=PROJECT_TARGET_COMMIT,
        worktree=str(project.resolve()),
        scope=SOURCE_SCOPE,
        discovery_budget=8,
    )


def _candidate_backend(request: HypothesisGenerationRequest) -> Mapping[str, Any]:
    facts = tuple(
        fact for fact in request.graph.facts if fact.status == "known" and fact.provenance
    )
    if len(facts) < 3:
        raise M9RecoveryFormalError("fresh Context Acquisition yielded fewer than three known facts")
    fact_ids = tuple(fact.fact_id for fact in facts[:3])
    definitions = approved_m9_prior_registry()
    qualities = (
        "bounded input responsiveness at the Jetchat composition boundary",
        "unsent draft-state continuity across configuration recreation",
        "lifecycle ownership continuity for the Jetchat input state",
    )
    candidates: list[dict[str, Any]] = []
    for index, definition in enumerate(definitions, start=1):
        hypothesis_id = f"hypothesis-m9-r4-portfolio-{index}"
        chain_id = f"chain-m9-r4-portfolio-{index}"
        quality = qualities[index - 1]
        hypothesis = RiskHypothesis(
            hypothesis_id=hypothesis_id,
            target_id=request.target.target_id,
            quality_property=quality,
            assumptions=(
                "the recorded source boundary remains the active local path",
                "the bounded observation stays inside the declared safety boundary",
            ),
            trigger=f"the recorded {facts[0].predicate} at {facts[0].subject} is exercised",
            mechanism=(
                f"the {definition.prior.name} path carries input state across the recorded boundary"
            ),
            consequence=quality,
            rationale=(
                "Three provenance-bound source facts connect the input boundary to this quality property; runtime evidence remains absent."
            ),
            required_evidence=(
                "source boundary identity",
                "bounded before/after state observation",
                "terminal execution evidence",
            ),
            confidence=0.6,
            status="draft",
            supporting_fact_ids=fact_ids,
            prior_id=definition.prior_id,
            failure_chain_id=chain_id,
            unknowns=("configuration-recreation runtime evidence remains unresolved",),
        )
        chain = FailureChain(
            chain_id=chain_id,
            steps=(
                "the Jetchat input boundary is entered",
                "one configuration recreation crosses the recorded state boundary",
                f"the quality property is exposed: {quality}",
            ),
            consequence=quality,
            fact_ids=fact_ids,
            causal_roles=("local_behavior", "dependency_propagation", "system_impact"),
        )
        candidates.append(
            HypothesisCandidate(
                candidate_id=f"candidate-m9-r4-portfolio-{index}",
                prior_id=definition.prior_id,
                operator_id=definition.operator_id,
                hypothesis=hypothesis,
                failure_chain=chain,
                uncertainty=("configuration-recreation runtime evidence remains unresolved",),
            ).to_dict()
        )
    return {"schema_version": 1, "candidates": candidates}


def _discover_context_and_portfolio(
    project: Path,
) -> tuple[ProjectTarget, Any, Any, dict[str, Any]]:
    target = _make_target(project)
    started = time.monotonic()
    context = acquire_project_context(target)
    context_seconds = round(time.monotonic() - started, 3)
    _write_json(
        FORMAL_ROOT / "context-acquisition.json",
        {
            "schema_version": 2,
            "duration_seconds": context_seconds,
            "result": context.to_dict(),
            "side_effects": False,
            "mapping_released": False,
        },
    )
    registry = approved_m9_prior_registry()
    request = HypothesisGenerationRequest(
        request_id="m9-r4-hypothesis-generation-01",
        target=target,
        graph=context.graph,
        approved_priors=tuple(item.prior for item in registry),
        budget=8,
    )
    identity = HypothesisGeneratorIdentity.capture(
        backend="local_deterministic_context_planner",
        requested_model="bounded-m9-recovery-generator-v1",
        effective_model="bounded-m9-recovery-generator-v1",
        invocation_id="m9-r4-hypothesis-generator-01",
    )
    response = generate_hypothesis_response(request, _candidate_backend, identity)
    portfolio = freeze_hypothesis_portfolio(request, response)
    if portfolio.status != "frozen" or len(portfolio.selected) != 3:
        raise M9RecoveryFormalError("fresh top-three hypothesis portfolio was not frozen")
    state_candidates = [
        item
        for item in portfolio.selected
        if item.prior_id == "prior-state-evolution-compatibility-v1"
    ]
    if len(state_candidates) != 1:
        raise M9RecoveryFormalError("state-evolution hypothesis is not uniquely selected")
    value = {
        "schema_version": 2,
        "request": request.to_dict(),
        "response": response.to_dict(),
        "portfolio": portfolio.to_dict(),
        "selected_probe_hypothesis_id": state_candidates[0].hypothesis.hypothesis_id,
        "duration_seconds": context_seconds,
        "side_effects": False,
        "mapping_released": False,
    }
    _write_json(FORMAL_ROOT / "hypothesis-portfolio.json", value)
    return target, context, portfolio, {
        "context_seconds": context_seconds,
        "graph_sha256": context.receipt.graph_sha256,
        "portfolio_sha256": sha256_bytes(canonical_json_bytes(portfolio.to_dict())),
        "registry": registry,
        "selected": state_candidates[0],
    }


def _attack_plan(
    target: ProjectTarget,
    context: Any,
    metadata: Mapping[str, Any],
    project: Path,
) -> Any:
    selected = metadata["selected"]
    definition = next(
        item
        for item in metadata["registry"]
        if item.prior_id == selected.prior_id
    )
    evidence_paths = {
        "build": R3_ROOT / "package-build.json",
        "package": R3_ROOT / "preflight.json",
        "launch": R3_ROOT / "preflight.json",
        "controllability": R3_ROOT / "source-context-inputs.json",
    }
    refs = tuple(
        ValidatedEvidenceRef(
            ref=path.relative_to(REPO_ROOT).as_posix(),
            kind=kind,
            sha256=sha256_file(path),
        )
        for kind, path in evidence_paths.items()
    )
    request = AttackPlanGenerationRequest(
        request_id="m9-r4-attack-plan-generation-01",
        target=target,
        graph=context.graph,
        hypothesis=selected.hypothesis,
        operator=definition.operator,
        approved_operators=tuple(item.operator for item in metadata["registry"]),
        controllability_fact_ids=(selected.hypothesis.supporting_fact_ids[0],),
        validated_evidence=refs,
        budget=8,
        safety_boundary=SAFETY_BOUNDARY,
        claim_boundary=LOCAL_CLAIM_BOUNDARY,
    )
    f1, f2, f3 = selected.hypothesis.supporting_fact_ids
    proposal = AttackPlanProposal(
        plan_id="plan-m9-r4-unsent-draft-configuration-recreation",
        target_id=target.target_id,
        hypothesis_id=selected.hypothesis.hypothesis_id,
        operator_id=definition.operator_id,
        trigger=PlanElement(
            element_id="m9-r4-trigger",
            kind="trigger",
            text="open the recorded Jetchat conversation input boundary once",
            fact_ids=(f1,),
            order=0,
        ),
        actions=(
            PlanElement(
                element_id="m9-r4-enter-draft",
                kind="action",
                text="enter one lane-scoped opaque token as an unsent draft exactly once",
                fact_ids=(f1,),
                operator_id=definition.operator_id,
                order=1,
            ),
            PlanElement(
                element_id="m9-r4-rotate",
                kind="system_event",
                text="cross one portrait-to-landscape configuration boundary",
                fact_ids=(f2,),
                operator_id=definition.operator_id,
                order=2,
                event="rotate",
            ),
        ),
        observations=(
            PlanElement(
                element_id="m9-r4-observe-draft",
                kind="observation",
                text="observe the same input without sending, retyping, repairing, navigating, or reopening",
                fact_ids=(f2,),
                order=3,
            ),
        ),
        evidence_expectations=(
            PlanElement(
                element_id="m9-r4-source-evidence",
                kind="evidence_expectation",
                text="source and deployment identity",
                fact_ids=(f3,),
                order=4,
            ),
            PlanElement(
                element_id="m9-r4-state-evidence",
                kind="evidence_expectation",
                text="portrait and landscape input-state observations",
                fact_ids=(f1,),
                order=5,
            ),
            PlanElement(
                element_id="m9-r4-terminal-evidence",
                kind="evidence_expectation",
                text="terminal ExecutionRecord and independent review",
                fact_ids=(f2,),
                order=6,
            ),
        ),
        oracle=OracleContract(
            oracle_id="m9-unsent-draft-config-recreation-v1",
            input_element_ids=(
                "m9-r4-observe-draft",
                "m9-r4-source-evidence",
                "m9-r4-state-evidence",
                "m9-r4-terminal-evidence",
            ),
            machine_check="compare the exact token before and after one rotation boundary using bound raw evidence",
            evidence_refs=(refs[0].ref, refs[-1].ref),
        ),
        fixture_refs=("fixture:android-emulator-api35-local",),
        abort_boundary="abort before an unbounded wait or external side effect",
        safety_boundary=SAFETY_BOUNDARY,
        claim_boundary=LOCAL_CLAIM_BOUNDARY,
    )
    planner = PlannerIdentity.capture(
        backend="local_deterministic_attack_planner",
        requested_model="bounded-m9-recovery-planner-v1",
        effective_model="bounded-m9-recovery-planner-v1",
        invocation_id="m9-r4-attack-planner-01",
    )
    generation = generate_attack_plan(
        request,
        lambda _request: {"schema_version": 1, "proposal": proposal.to_dict()},
        planner,
    )
    if not generation.admitted or generation.admission.plan is None:
        raise M9RecoveryFormalError(
            "target-specific Attack Plan was rejected: "
            + "; ".join(generation.rejection_reasons)
        )
    compiled = compile_admitted_attack_plan(
        generation.admission,
        host_project=project,
        apk_glob=APK_GLOB,
        package_name=PACKAGE,
        activity=ACTIVITY,
    )
    _write_json(
        FORMAL_ROOT / "attack-plan-generation.json",
        {
            "schema_version": 2,
            "request": request.to_dict(),
            "generation": generation.to_dict(),
            "compiled_neutral_plan": compiled.to_dict(),
            "side_effects": False,
            "mapping_released": False,
        },
    )
    return generation


def _leakage_gate(
    manifest: Mapping[str, Any],
    metadata: Mapping[str, Any],
    generation: Any,
) -> dict[str, Any]:
    packets = [
        {
            "schema_version": 2,
            "packet_id": f"packet-{lane_id}",
            "lane_id": lane_id,
            "context_graph_sha256": metadata["graph_sha256"],
            "portfolio_sha256": metadata["portfolio_sha256"],
            "plan_sha256": generation.authoritative_output_sha256,
            "run_spec_sha256": next(
                lane["run_spec"]["sha256"]
                for lane in manifest["lanes"]
                if lane["lane_id"] == lane_id
            ),
        }
        for lane_id in LANE_IDS
    ]
    if any(_ROLE_LEAKAGE.search(json.dumps(packet, sort_keys=True)) for packet in packets):
        raise M9RecoveryFormalError("neutral packet contains forbidden role material")
    audit = audit_neutral_packets(packets)
    if audit.get("status") != "pass":
        raise M9RecoveryFormalError("neutral verifier leakage audit failed")
    value = {
        "schema_version": 2,
        "packets": packets,
        "audit": audit,
        "mapping_released": False,
        "side_effects": False,
    }
    _write_json(FORMAL_ROOT / "leakage-audit.json", value)
    return value


def _release_mapping(manifest: Mapping[str, Any]) -> Mapping[str, Any]:
    commitment = manifest["cohort"]["mapping_commitment"]
    released = load_auditor_mapping(
        MAPPING_PATH,
        expected_raw_sha256=commitment["raw_artifact_sha256"],
        expected_canonical_sha256=commitment["sha256"],
    )
    if (
        released.raw_sha256 != FROZEN_MAPPING_RAW_SHA256
        or released.canonical_sha256 != FROZEN_MAPPING_CANONICAL_SHA256
    ):
        raise M9RecoveryFormalError("released mapping contradicts the frozen commitments")
    _write_json(
        FORMAL_ROOT / "auditor-mapping-release.json",
        {
            "schema_version": 2,
            "released_at": _utc_now(),
            "release_after": [
                "context_acquisition",
                "top_three_hypothesis_portfolio",
                "attack_plan_admission",
                "leakage_audit",
            ],
            "raw_sha256": released.raw_sha256,
            "canonical_sha256": released.canonical_sha256,
            "mapping": released.document,
        },
    )
    return released.document


def _mapping_roles(mapping: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(item["lane_id"]): str(item["role"])
        for item in mapping["assignments"]
    }


def _source_bindings(inputs: FormalInputs) -> dict[str, SourceBinding]:
    """Decode the two auditor roles exactly once at the mapping boundary."""

    return {
        "defect": SourceBinding(
            project=inputs.defect_project.resolve(),
            commit=DEFECT_COMMIT,
            tree=DEFECT_TREE,
            apk=inputs.defect_apk.resolve(),
            apk_bytes=DEFECT_APK_BYTES,
            apk_sha256=DEFECT_APK_SHA256,
        ),
        "control": SourceBinding(
            project=inputs.project_target.resolve(),
            commit=PROJECT_TARGET_COMMIT,
            tree=PROJECT_TARGET_TREE,
            apk=inputs.control_apk.resolve(),
            apk_bytes=CONTROL_APK_BYTES,
            apk_sha256=CONTROL_APK_SHA256,
        ),
    }


def _verify_apk(path: Path, *, expected_bytes: int, expected_sha256: str) -> None:
    if (
        not path.is_file()
        or path.stat().st_size != expected_bytes
        or sha256_file(path) != expected_sha256
    ):
        raise M9RecoveryFormalError(f"frozen R3 APK identity drifted: {path}")


def _validate_formal_inputs(
    inputs: FormalInputs,
    bindings: Mapping[str, SourceBinding],
) -> dict[str, Any]:
    """Verify all external identities before claiming the one-shot namespace."""

    source_root = inputs.source_root.resolve()
    if source_root.exists():
        raise M9RecoveryFormalError(
            f"fresh lane source namespace already exists: {source_root}"
        )
    receipts: list[dict[str, Any]] = []
    for index, binding in enumerate(bindings.values(), start=1):
        source = _verify_source(
            binding.project,
            commit=binding.commit,
            tree=binding.tree,
        )
        _verify_apk(
            binding.apk,
            expected_bytes=binding.apk_bytes,
            expected_sha256=binding.apk_sha256,
        )
        receipts.append(
            {
                "binding_id": f"source-binding-{index:02d}",
                "source": source,
                "apk": {
                    "path": str(binding.apk),
                    "bytes": binding.apk_bytes,
                    "sha256": binding.apk_sha256,
                },
            }
        )
    return {
        "schema_version": 2,
        "status": "passed",
        "side_effects": False,
        "verified_before_formal_root_claim": True,
        "source_root": str(source_root),
        "source_root_absent": True,
        "bindings": receipts,
    }


def _prepare_source_fixture(
    lane_id: str,
    binding: SourceBinding,
    inputs: FormalInputs,
) -> tuple[Path, dict[str, Any]]:
    _verify_source(binding.project, commit=binding.commit, tree=binding.tree)
    _verify_apk(
        binding.apk,
        expected_bytes=binding.apk_bytes,
        expected_sha256=binding.apk_sha256,
    )
    destination = inputs.source_root.resolve() / lane_id
    if destination.exists():
        raise M9RecoveryFormalError(f"fresh lane source already exists: {destination}")
    clone = _run(
        ["git", "clone", "--no-checkout", str(binding.project), str(destination)],
        timeout=300,
    )
    checkout = _run(
        ["git", "checkout", "--detach", binding.commit],
        cwd=destination,
        timeout=120,
    )
    remote = _run(["git", "remote", "set-url", "origin", SOURCE_ORIGIN], cwd=destination, timeout=60)
    target_apk = destination / APK_GLOB
    target_apk.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(binding.apk, target_apk)
    identity = _verify_source(
        destination,
        commit=binding.commit,
        tree=binding.tree,
    )
    _verify_apk(
        target_apk,
        expected_bytes=binding.apk_bytes,
        expected_sha256=binding.apk_sha256,
    )
    return destination, {
        "schema_version": 2,
        "lane_id": lane_id,
        "source": identity,
        "apk": {
            "path": str(target_apk),
            "bytes": binding.apk_bytes,
            "sha256": binding.apk_sha256,
        },
        "commands": [clone, checkout, remote],
        "fresh_fixture": True,
        "r1_r2_inputs_reused": False,
    }


def _load_frozen_spec(lane_id: str, workdir: Path) -> tuple[Path, RunSpec]:
    path = REPO_ROOT / "bench/m9/recovery-v2/run-specs" / f"{lane_id}.yaml"
    spec = load_run_spec(path, environ={}, host_project_override=workdir)
    if spec.scenario.id != lane_id or spec.source_sha256 is None:
        raise M9RecoveryFormalError(f"frozen Run Spec identity drifted: {lane_id}")
    return path, spec


def _admit_lanes(
    roles: Mapping[str, str],
    bindings: Mapping[str, SourceBinding],
    inputs: FormalInputs,
    state: FormalState,
) -> tuple[dict[str, AdmittedLane], list[dict[str, Any]]]:
    if inputs.source_root.exists():
        raise M9RecoveryFormalError("fresh source namespace already exists")
    inputs.source_root.mkdir(parents=True, exist_ok=False)
    admitted: dict[str, AdmittedLane] = {}
    fixture_receipts: list[dict[str, Any]] = []
    receipts: list[Mapping[str, Any]] = []
    expected_specs: dict[str, Mapping[str, Any]] = {}
    for lane_id in LANE_IDS:
        role = roles[lane_id]
        binding = bindings.get(role)
        if binding is None:
            raise M9RecoveryFormalError("released mapping contains an unknown role")
        workdir, fixture = _prepare_source_fixture(lane_id, binding, inputs)
        fixture_receipts.append(fixture)
        _write_json(
            FORMAL_ROOT / "source-fixtures" / f"{lane_id}.json",
            fixture,
        )
        spec_path, spec = _load_frozen_spec(lane_id, workdir)
        lane_root = FORMAL_ARTIFACT_ROOT / lane_id
        options = PlannedRunnerOptions(
            device=DEVICE,
            workdir=workdir,
            artifact_dir=lane_root / "artifacts",
            expected_source_commit=binding.commit,
            launch=True,
            requested_driver_model=None,
            requested_l3_model=None,
            backend=BACKEND,
            runner_policy_version=RUNNER_POLICY,
            allow_host_project_subdir=False,
        )
        result = admit_production_seam(spec, options)
        if not result.admitted:
            raise M9RecoveryFormalError(
                f"fresh production admission failed for {lane_id}: {'; '.join(result.reasons)}"
            )
        lane_root.mkdir(parents=True, exist_ok=False)
        write_admission_receipt(result, lane_root / "production-seam-admission.json")
        receipts.append(result.receipt)
        expected_specs[lane_id] = {
            "run_spec_sha256": spec.source_sha256,
            "commit": binding.commit,
        }
        admitted[lane_id] = AdmittedLane(
            frozen_path=spec_path,
            spec=spec,
            options=options,
            admission=result,
            source=binding,
        )
        state.admit(lane_id)
    audit = validate_admission_receipts(receipts, expected_run_specs=expected_specs)
    if audit.get("status") != "pass":
        raise M9RecoveryFormalError("fresh six-lane admission population failed validation")
    _write_json(FORMAL_ROOT / "source-fixtures.json", {"schema_version": 2, "fixtures": fixture_receipts})
    _write_json(FORMAL_ROOT / "admission-audit.json", audit)
    return admitted, fixture_receipts


def _adb_receipt(*args: str) -> dict[str, Any]:
    return _run(["adb", "-s", DEVICE, *args], timeout=60, check=False)


def _require_adb(receipt: Mapping[str, Any], label: str) -> None:
    if receipt.get("returncode") != 0:
        raise M9RecoveryFormalError(
            f"{label} failed: {str(receipt.get('stderr', '')).strip()}"
        )


def _pre_run_environment(lane_root: Path, ime_guard: dict[str, str]) -> None:
    """Reset package/state and bind the frozen device policy before deployment."""

    controller = DeviceController(serial=DEVICE)
    try:
        package_reset = reset_package_data(
            controller=controller,
            device_serial=DEVICE,
            package=PACKAGE,
        )
        package_payload = package_reset.to_dict()
    except PackageResetError as error:
        package_payload = error.result.to_dict()
        _write_json(lane_root / "package-reset.json", package_payload)
        raise
    _write_json(lane_root / "package-reset.json", package_payload)

    operations = {
        "activity_event_log_clear": _adb_receipt("logcat", "-b", "events", "-c"),
        "accelerometer_rotation_disable": _adb_receipt(
            "shell", "settings", "put", "system", "accelerometer_rotation", "0"
        ),
        "portrait_rotation": _adb_receipt(
            "shell", "settings", "put", "system", "user_rotation", "0"
        ),
        "wifi_disable": _adb_receipt("shell", "svc", "wifi", "disable"),
        "mobile_data_disable": _adb_receipt("shell", "svc", "data", "disable"),
        "accelerometer_rotation_observe": _adb_receipt(
            "shell", "settings", "get", "system", "accelerometer_rotation"
        ),
        "user_rotation_observe": _adb_receipt(
            "shell", "settings", "get", "system", "user_rotation"
        ),
        "wifi_observe": _adb_receipt(
            "shell", "settings", "get", "global", "wifi_on"
        ),
        "mobile_data_observe": _adb_receipt(
            "shell", "settings", "get", "global", "mobile_data"
        ),
        "input_method_observe": _adb_receipt(
            "shell", "settings", "get", "secure", "default_input_method"
        ),
    }
    for name, receipt in operations.items():
        _require_adb(receipt, name)
    expected_zero = (
        "accelerometer_rotation_observe",
        "user_rotation_observe",
        "wifi_observe",
        "mobile_data_observe",
    )
    if any(str(operations[name]["stdout"]).strip() != "0" for name in expected_zero):
        _write_json(
            lane_root / "environment-setup.json",
            {
                "schema_version": 2,
                "status": "failed",
                "device": DEVICE,
                "operations": operations,
            },
        )
        raise M9RecoveryFormalError("pre-lane orientation or network policy was not observed")
    ime = str(operations["input_method_observe"]["stdout"]).strip()
    if not ime:
        raise M9RecoveryFormalError("default input method identity is unavailable")
    if "value" not in ime_guard:
        ime_guard["value"] = ime
    elif ime_guard["value"] != ime:
        raise M9RecoveryFormalError("default input method drifted across formal lanes")
    _write_json(
        lane_root / "environment-setup.json",
        {
            "schema_version": 2,
            "status": "passed",
            "device": DEVICE,
            "package_reset_status": package_reset.status,
            "network_disabled": True,
            "orientation": "portrait",
            "default_input_method": ime,
            "operations": operations,
        },
    )


def _resolved_spec(
    lane_id: str,
    frozen_path: Path,
    workdir: Path,
    commit: str,
) -> tuple[Path, RunSpec]:
    document = yaml.safe_load(frozen_path.read_text(encoding="utf-8"))
    if not isinstance(document, dict) or not isinstance(document.get("host_project"), dict):
        raise M9RecoveryFormalError(f"frozen Run Spec is malformed: {lane_id}")
    document["host_project"]["commit"] = commit
    path = FORMAL_ARTIFACT_ROOT / lane_id / "identity/resolved-run-spec.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_bytes_artifact(
        path,
        yaml.safe_dump(document, allow_unicode=True, sort_keys=False).encode("utf-8"),
    )
    spec = load_run_spec(path, environ={}, host_project_override=workdir)
    return path, spec


def _identity_factory(
    *,
    lane_id: str,
    frozen_path: Path,
    effective_path: Path,
    effective_spec: RunSpec,
    workdir: Path,
    artifact_dir: Path,
):
    def factory(attempt_id: str) -> ExecutionIdentityCollector:
        return ExecutionIdentityCollector(
            run_dir=artifact_dir.parent,
            artifact_dir=artifact_dir,
            attempt_id=attempt_id,
            spec=effective_spec,
            run_spec_path=effective_path,
            workdir=workdir,
            device=DEVICE,
            requested_driver_model=None,
            requested_l3_model=None,
            run_spec_snapshot_path=effective_path,
            run_spec_identity_annotations={
                "frozen_source_sha256": sha256_file(frozen_path),
                "source_binding_ref": sealed_source_binding_ref(lane_id),
            },
            authoritative_role_identity_dir=(
                artifact_dir.parent / "production-identities"
            ),
        )

    return factory


def _artifact_ref(path: Path) -> dict[str, str]:
    try:
        relative = path.resolve().relative_to(REPO_ROOT)
    except ValueError as error:
        raise M9RecoveryFormalError(f"evidence path escapes repository: {path}") from error
    return {"path": relative.as_posix(), "sha256": sha256_file(path)}


def _identity_invocation(receipt_path: Path, role: str) -> dict[str, Any]:
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    source = receipt.get("effective_model_source", {})
    thread_id = source.get("thread_id")
    turn_id = source.get("turn_id")
    model = receipt.get("effective_model")
    if not all(isinstance(item, str) and item for item in (thread_id, turn_id, model)):
        raise M9RecoveryFormalError("authoritative production identity is incomplete")
    reference = _artifact_ref(receipt_path)
    return {
        "role": role,
        "invocation_id": f"{thread_id}:{turn_id}",
        "identity_sha256": reference["sha256"],
        "effective_model": model,
        "identity_receipt": reference,
    }


def _write_effective_identity(lane_id: str, record: Mapping[str, Any]) -> dict[str, Any]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    provenance = json.loads((lane_root / "execution-provenance.json").read_text(encoding="utf-8"))
    invocations: list[dict[str, Any]] = []
    for role in ("journey_driver", "l3_semantic_judge"):
        role_payload = provenance["roles"][role]
        if role_payload.get("status") != "invoked":
            continue
        for reference in role_payload["invocations"]:
            invocations.append(
                _identity_invocation(lane_root / reference["path"], role)
            )
    journey = [item for item in invocations if item["role"] == "journey_driver"]
    if not journey:
        raise M9RecoveryFormalError("journey-driver identity is absent")
    identity = {
        "schema_version": 2,
        "status": "complete",
        "backend": BACKEND,
        "selection_policy": "codex_cli_default",
        "requested_model": None,
        "model_override_present": False,
        "execution_record_attempt_id": record["attempt_id"],
        "production_invocation_id": journey[0]["invocation_id"],
        "invocations": invocations,
    }
    _write_json(lane_root / "effective-execution-identity.json", identity)
    return identity


def _layout_center(node: Mapping[str, Any]) -> tuple[int, int] | None:
    value = node.get("center")
    match = _LAYOUT_CENTER.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _observe_text_input_token(layout: object, token: str) -> dict[str, Any]:
    """Bind an exact token observation to Jetchat's Text input semantics."""

    if not isinstance(layout, list):
        raise M9RecoveryFormalError("Android layout evidence is not a node list")
    nodes = [item for item in layout if isinstance(item, Mapping)]
    anchors = [
        item
        for item in nodes
        if item.get("content-desc", item.get("contentDesc")) == "Text input"
    ]
    exact_nodes = [item for item in nodes if item.get("text") == token]
    editable_exact_nodes = []
    for item in exact_nodes:
        interactions = item.get("interactions")
        if (
            isinstance(interactions, list)
            and {"focusable", "long-clickable"}.issubset(interactions)
        ):
            editable_exact_nodes.append(item)
    bound_exact_nodes = []
    for item in editable_exact_nodes:
        item_center = _layout_center(item)
        if item_center is None:
            continue
        if any(
            anchor_center is not None
            and abs(anchor_center[1] - item_center[1]) <= 96
            for anchor_center in (_layout_center(anchor) for anchor in anchors)
        ):
            bound_exact_nodes.append(item)
    field_present = len(anchors) == 1
    token_visible = (
        field_present
        and len(exact_nodes) == 1
        and len(editable_exact_nodes) == 1
        and len(bound_exact_nodes) == 1
    )
    return {
        "field_semantics": "content-desc:Text input",
        "input_field_anchor_count": len(anchors),
        "exact_token_node_count": len(exact_nodes),
        "editable_exact_token_node_count": len(editable_exact_nodes),
        "bound_exact_token_node_count": len(bound_exact_nodes),
        "input_field_present": field_present,
        "exact_token_visible_in_input": token_visible,
    }


def _png_dimensions(path: Path) -> tuple[int, int]:
    payload = path.read_bytes()
    if len(payload) < 24 or payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise M9RecoveryFormalError(f"invalid PNG evidence: {path}")
    width, height = struct.unpack(">II", payload[16:24])
    if width < 1 or height < 1:
        raise M9RecoveryFormalError(f"invalid PNG dimensions: {path}")
    return width, height


def _filtered_rotation_logcat(source: Path) -> str:
    text = source.read_text(encoding="utf-8")
    terms = (
        "jetchat",
        "NavActivity",
        "ActivityTaskManager",
        "ActivityManager",
        "configuration",
        "relaunch",
        "WindowManager",
    )
    selected = [line for line in text.splitlines() if any(term in line for term in terms)]
    if not selected:
        selected = text.splitlines()
    result = "\n".join(selected).strip()
    if not result:
        raise M9RecoveryFormalError("rotation logcat evidence is empty")
    return result + "\n"


def _activity_recreation_lines(event_logcat: str) -> tuple[list[str], bool]:
    lifecycle = [
        line
        for line in event_logcat.splitlines()
        if ACTIVITY in line
        and any(
            marker in line
            for marker in (
                "am_on_create_called",
                "am_on_destroy_called",
                "am_relaunch_resume_activity",
            )
        )
    ]
    destroy_indexes = [
        index
        for index, line in enumerate(lifecycle)
        if "am_on_destroy_called" in line
    ]
    create_indexes = [
        index
        for index, line in enumerate(lifecycle)
        if "am_on_create_called" in line
    ]
    relaunched = any("am_relaunch_resume_activity" in line for line in lifecycle)
    destroy_then_create = any(
        destroy < create for destroy in destroy_indexes for create in create_indexes
    )
    return lifecycle, relaunched or destroy_then_create


def _normalize_raw_evidence(
    lane_id: str,
    token: str,
) -> tuple[dict[str, dict[str, str]], str]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    before_root = lane_root / "artifacts/after-segment-0"
    after_root = lane_root / "artifacts/after-event-0"
    event_source = lane_root / "artifacts/system-event-0/event.json"
    before_screen = before_root / "screen.png"
    after_screen = after_root / "screen.png"
    before_layout_source = before_root / "layout.json"
    after_layout_source = after_root / "layout.json"
    before_layout = json.loads(before_layout_source.read_text(encoding="utf-8"))
    after_layout = json.loads(after_layout_source.read_text(encoding="utf-8"))
    event = json.loads(event_source.read_text(encoding="utf-8"))
    event_logcat_receipt = _adb_receipt(
        "logcat", "-b", "events", "-d", "-v", "threadtime"
    )
    _require_adb(event_logcat_receipt, "activity lifecycle event log capture")
    lifecycle_lines, lifecycle_recreated = _activity_recreation_lines(
        str(event_logcat_receipt["stdout"])
    )
    _write_json(
        lane_root / "raw/logcat/events-command.json",
        event_logcat_receipt,
    )
    before_dimensions = _png_dimensions(before_screen)
    after_dimensions = _png_dimensions(after_screen)
    if before_dimensions[0] >= before_dimensions[1] or after_dimensions[0] <= after_dimensions[1]:
        raise M9RecoveryFormalError("raw screenshots do not prove portrait-to-landscape order")
    before_observation = _observe_text_input_token(before_layout, token)
    after_observation = _observe_text_input_token(after_layout, token)
    before_visible = before_observation["exact_token_visible_in_input"] is True
    after_visible = after_observation["exact_token_visible_in_input"] is True

    before_out = lane_root / "raw/screenshots/before.png"
    after_out = lane_root / "raw/screenshots/after.png"
    _copy_artifact(before_screen, before_out)
    _copy_artifact(after_screen, after_out)
    before_summary = {
        "schema_version": 1,
        "lane_id": lane_id,
        "checkpoint": "before",
        "orientation": "portrait",
        "probe_token": token,
        "token_visible": before_visible,
        "text_input_observation": before_observation,
        "source_path": before_screen.relative_to(lane_root).as_posix(),
        "source_layout_sha256": sha256_file(before_layout_source),
        "screenshot_dimensions": list(before_dimensions),
    }
    after_summary = {
        "schema_version": 1,
        "lane_id": lane_id,
        "checkpoint": "after",
        "orientation": "landscape",
        "probe_token": token,
        "token_visible": after_visible,
        "text_input_observation": after_observation,
        "source_path": after_screen.relative_to(lane_root).as_posix(),
        "source_layout_sha256": sha256_file(after_layout_source),
        "screenshot_dimensions": list(after_dimensions),
    }
    before_layout_out = lane_root / "raw/layout/before.json"
    after_layout_out = lane_root / "raw/layout/after.json"
    _write_json(before_layout_out, before_summary)
    _write_json(after_layout_out, after_summary)
    logcat_out = lane_root / "raw/logcat/rotation.txt"
    checkpoint_logcat = _filtered_rotation_logcat(after_root / "logcat.txt")
    lifecycle_logcat = "\n".join(lifecycle_lines).strip()
    _write_text(
        logcat_out,
        (
            "# activity lifecycle event buffer\n"
            + (lifecycle_logcat or "<no matching lifecycle events>")
            + "\n# after-rotation checkpoint buffers\n"
            + checkpoint_logcat
        ),
    )
    event_evidence = event.get("evidence", {})
    recreation_observed = (
        event.get("status") == "passed"
        and event.get("event") == "rotate"
        and event_evidence.get("accelerometer_rotation") == "0"
        and event_evidence.get("user_rotation") == "1"
        and lifecycle_recreated
    )
    if (
        not recreation_observed
        or not before_visible
        or after_observation["input_field_present"] is not True
        or (
            not after_visible
            and after_observation["exact_token_node_count"] != 0
        )
    ):
        conclusion = "inconclusive"
    elif after_visible:
        conclusion = "locally_rejected"
    else:
        conclusion = "locally_supported"
    rotation = {
        "schema_version": 1,
        "lane_id": lane_id,
        "status": "passed" if recreation_observed else "failed",
        "event": "rotate",
        "rotation_count": 1,
        "before": "user_rotation=0",
        "after": f"user_rotation={event_evidence.get('user_rotation')}",
        "accelerometer_rotation": event_evidence.get("accelerometer_rotation"),
        "activity_recreation_observed": recreation_observed,
        "activity_recreation_basis": [
            "artifacts/system-event-0/event.json",
            "raw/screenshots/before.png",
            "raw/screenshots/after.png",
            "raw/logcat/events-command.json",
            "a NavActivity destroy-then-create sequence or explicit relaunch callback",
        ],
        "retyped_after_boundary": False,
        "repaired_after_boundary": False,
    }
    rotation_out = lane_root / "rotation-event.json"
    _write_json(rotation_out, rotation)
    refs = {
        "screenshot_before": _artifact_ref(before_out),
        "screenshot_after": _artifact_ref(after_out),
        "layout_before": _artifact_ref(before_layout_out),
        "layout_after": _artifact_ref(after_layout_out),
        "filtered_logcat": _artifact_ref(logcat_out),
        "rotation_event": _artifact_ref(rotation_out),
    }
    return refs, conclusion


def _write_semantic_evidence(
    lane_id: str,
    token: str,
    record: Mapping[str, Any],
    raw_refs: Mapping[str, Mapping[str, str]],
    conclusion: str,
    lineage: EvidenceLineage,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    accountable = bool(
        conclusion in {"locally_supported", "locally_rejected"}
        and record.get("lifecycle_state") == "completed"
        and is_execution_record_accountable(record)
    )
    oracle = {
        "schema_version": 2,
        "oracle_id": "m9-unsent-draft-config-recreation-v1",
        "status": "complete" if accountable else "inconclusive",
        "lane_id": lane_id,
        "accountable": accountable,
        "conclusion": conclusion,
        "hypothesis_id": lineage.hypothesis_id,
        "explored_fact_ids": list(lineage.explored_fact_ids),
        "probe_token": token,
        "sent": False,
        "retyped_after_boundary": False,
        "repaired_after_boundary": False,
        "evidence_refs": dict(raw_refs),
    }
    _write_json(lane_root / "oracle-receipt.json", oracle)
    finding: dict[str, Any] | None = None
    if accountable:
        finding = {
            "schema_version": 1,
            "finding_id": f"finding-{lane_id}",
            "target_id": PROJECT_TARGET_ID,
            "hypothesis_id": lineage.hypothesis_id,
            "conclusion": {
                "locally_supported": "supported",
                "locally_rejected": "rejected",
            }[conclusion],
            "evidence_refs": [
                "execution-record.json",
                "effective-execution-identity.json",
                "oracle-receipt.json",
                "raw/screenshots/before.png",
                "raw/screenshots/after.png",
                "raw/layout/before.json",
                "raw/layout/after.json",
                "raw/logcat/rotation.txt",
                "rotation-event.json",
            ],
            "impact": "an unsent Jetchat draft may be lost across activity recreation",
            "claim_boundary": LOCAL_CLAIM_BOUNDARY,
            "rationale": (
                "Derived only from the terminal checksum-bound lane observations."
            ),
        }
    residual = {
        "schema_version": 1,
        "risk_id": f"residual-{lane_id}",
        "target_id": PROJECT_TARGET_ID,
        "hypothesis_id": lineage.hypothesis_id,
        "reason": (
            "The local probe does not establish behavior outside the frozen boundary."
            if accountable
            else "The terminal lane is non-accountable, so it cannot create a Finding."
        ),
        "evidence_gap": (
            "Other devices, releases, and lifecycle boundaries remain unexplored."
            if accountable
            else "Accountable terminal oracle evidence is unavailable."
        ),
        "scope": LOCAL_CLAIM_BOUNDARY,
        "basis_refs": ["execution-record.json", "oracle-receipt.json"],
        "next_probe": "Any next probe requires a new approved contract.",
        "status": "accepted",
    }
    risk_map = {
        "schema_version": 1,
        "map_id": f"risk-map-{lane_id}",
        "target_id": PROJECT_TARGET_ID,
        "findings": [finding] if finding is not None else [],
        "residual_risks": [residual],
        "explored_fact_ids": list(lineage.explored_fact_ids),
        "coverage_frontier": [
            "production, upstream, OEM, ColorOS, and physical-device behavior remains unexplored"
        ],
    }
    claim_boundary = {
        "schema_version": 2,
        "lane_id": lane_id,
        "scope": LOCAL_CLAIM_BOUNDARY,
        "local_only": True,
        "preserved_runtime_result": "#137 remains Not Supported and is never rerun or rewritten",
        "excluded_claims": [
            "production",
            "upstream",
            "OEM",
            "ColorOS",
            "physical-device",
        ],
    }
    if finding is not None:
        _write_json(lane_root / "finding.json", finding)
    _write_json(lane_root / "residual-risk.json", residual)
    _write_json(lane_root / "project-risk-map.json", risk_map)
    _write_json(lane_root / "claim-boundary.json", claim_boundary)
    return oracle, finding


_REVIEW_INPUT_SOURCES: tuple[tuple[str, str | None], ...] = (
    ("execution-summary.json", None),
    ("effective-execution-identity.json", "effective-execution-identity.json"),
    ("raw/screenshots/before.png", "raw/screenshots/before.png"),
    ("raw/screenshots/after.png", "raw/screenshots/after.png"),
    ("raw/layout/before.json", "raw/layout/before.json"),
    ("raw/layout/after.json", "raw/layout/after.json"),
    ("raw/logcat/rotation.txt", "raw/logcat/rotation.txt"),
    ("rotation-event.json", "rotation-event.json"),
    ("oracle-receipt.json", "oracle-receipt.json"),
    ("finding.json", "finding.json"),
    ("claim-boundary.json", "claim-boundary.json"),
)


def _prepare_review_context(lane_id: str, record: Mapping[str, Any]) -> None:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    review_root = lane_root / "review-input"
    for name, source in _REVIEW_INPUT_SOURCES:
        destination = review_root / name
        if source is None:
            _write_json(destination, build_execution_review_summary(record))
        else:
            _copy_artifact(lane_root / source, destination)
        payload = destination.read_bytes()
        if _ROLE_LEAKAGE.search(payload.decode("utf-8", errors="ignore")):
            raise M9RecoveryFormalError(f"review input leaked role material: {name}")
        for forbidden in (
            DEFECT_COMMIT,
            PROJECT_TARGET_COMMIT,
            DEFECT_TREE,
            PROJECT_TARGET_TREE,
        ):
            if forbidden.encode("utf-8") in payload:
                raise M9RecoveryFormalError(f"review input leaked source assignment: {name}")
    context = {
        "schema_version": 2,
        "lane_id": lane_id,
        "clean_context": True,
        "source_role_disclosed": False,
        "expected_result_disclosed": False,
        "production_oracle_path_used": False,
        "workdir": str(review_root.resolve()),
        "input_artifacts": [
            _artifact_ref(review_root / name) for name, _source in _REVIEW_INPUT_SOURCES
        ],
    }
    _write_json(lane_root / "falsification-review-context.json", context)


def _lane_ledger(lane_root: Path) -> dict[str, str]:
    ledger = lane_root / "checksums.sha256"
    if ledger.exists():
        raise M9RecoveryFormalError(f"lane evidence is already sealed: {lane_root.name}")
    entries = [
        path
        for path in sorted(lane_root.rglob("*"))
        if path.is_file()
        and path.name not in {"checksums.sha256", "attempt-evidence-validation.json"}
    ]
    _write_text(
        ledger,
        "".join(
            f"{sha256_file(path)}  {path.relative_to(lane_root).as_posix()}\n"
            for path in entries
        ),
    )
    return _artifact_ref(ledger)


def _attempt_refs(lane_id: str) -> dict[str, dict[str, str]]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    required = load_manifest(MANIFEST_PATH, require_frozen=True).document[
        "evidence"
    ]["attempt_evidence_validation"]["required_refs"]
    return {
        key: _artifact_ref(lane_root / filename)
        for key, filename in required.items()
    }


def _seal_successful_lane(
    lane_id: str,
    role: str,
    record: Mapping[str, Any],
    identity: Mapping[str, Any],
    finding_conclusion: str,
    review: Mapping[str, Any],
    duration_seconds: float,
) -> dict[str, Any]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    ledger_ref = _lane_ledger(lane_root)
    refs = _attempt_refs(lane_id)
    refs["lane_ledger"] = ledger_ref
    identity_path = lane_root / "effective-execution-identity.json"
    identity_sha = sha256_file(identity_path)
    validator_ids = load_manifest(MANIFEST_PATH, require_frozen=True).document[
        "evidence"
    ]["attempt_evidence_validation"]["validator_check_ids"]
    review_survived = (
        review.get("status") == "complete" and review.get("outcome") == "survived"
    )
    validator_checks = {name: True for name in validator_ids}
    if not review_survived:
        validator_checks["falsification_review_bound"] = False
        validator_checks["falsification_review_output_bound"] = False
    attempt = {
        "schema_version": 2,
        "validation_version": "m9-recovery-attempt-evidence-v2",
        "status": "validated" if review_survived else "rejected",
        "lane_id": lane_id,
        "formal_attempt_id": FORMAL_ATTEMPT_ID,
        "terminal_lifecycle": "terminal",
        "execution_record_attempt_id": record["attempt_id"],
        "accountable": True,
        "finding_conclusion": finding_conclusion,
        "production_invocation_id": identity["production_invocation_id"],
        "production_identity_sha256": identity_sha,
        "refs": refs,
        "evidence_refs_sha256": sha256_bytes(canonical_json_bytes(refs)),
        "validator_checks": validator_checks,
    }
    validation_path = lane_root / "attempt-evidence-validation.json"
    _write_json(validation_path, attempt)
    row = {
        "lane_id": lane_id,
        "role": role,
        "accountable": True,
        "terminal": True,
        "formal_attempt_id": FORMAL_ATTEMPT_ID,
        "execution_record_attempt_id": record["attempt_id"],
        "lane_attempt_count": 1,
        "retry_count": 0,
        "replacement_count": 0,
        "discretionary_rerun_count": 0,
        "production_invocation_id": identity["production_invocation_id"],
        "production_identity_sha256": identity_sha,
        "finding_conclusion": finding_conclusion,
        "attempt_evidence": attempt,
        "attempt_evidence_receipt": _artifact_ref(validation_path),
        "falsification_review": {
            "path": refs["falsification_review"]["path"],
            "sha256": refs["falsification_review"]["sha256"],
            **review,
        },
        "duration_seconds": duration_seconds,
    }
    valid = validate_formal_attempt_row(row, evidence_repository_root=REPO_ROOT)
    _write_json(
        FORMAL_ROOT / "self-checks" / f"{lane_id}.json",
        {
            "schema_version": 1,
            "lane_id": lane_id,
            "valid": valid,
            "validator": "validate_formal_attempt_row",
        },
    )
    row["attempt_evidence_validated"] = valid
    return row


def _terminal_record(lane_id: str, error: Exception) -> Mapping[str, Any]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    path = lane_root / "execution-record.json"
    if path.is_file():
        record = load_execution_record(path)
        if record.get("lifecycle_state") != "in_progress":
            return record
        store = ExecutionRecordStore(path=path, attempt_id=str(record["attempt_id"]))
        started_at = str(record["started_at"])
    else:
        started_at = _utc_now()
        store = ExecutionRecordStore.establish(
            lane_root,
            artifact_dir=lane_root / "recovery-artifacts",
            scenario=lane_id,
            started_at=started_at,
        )
    return store.finalize(
        lifecycle_state="failed",
        execution={
            "status": "non_accountable",
            "accounting_eligible": False,
            "reason": "formal_lane_exception",
            "message": f"{type(error).__name__}: {error}",
        },
        process_exit_code=2,
        timing={
            "started_at": started_at,
            "finished_at": _utc_now(),
            "total_seconds": 0.0,
            "phases": [],
        },
        phase_errors=[
            {
                "phase": "formal-lane-consumer",
                "kind": "consumer",
                "reason": "formal_lane_exception",
                "message": f"{type(error).__name__}: {error}",
            }
        ],
        evidence_refs={},
    )


def _absent_required_artifacts(
    lane_root: Path,
    required: Sequence[str],
) -> list[str]:
    absent: list[str] = []
    for item in required:
        if any(marker in item for marker in ("*", "?", "[")):
            if not any(path.is_file() for path in lane_root.glob(item)):
                absent.append(item)
        elif not (lane_root / item).is_file():
            absent.append(item)
    return absent


def _seal_failed_lane(
    lane_id: str,
    role: str | None,
    error: Exception,
    *,
    duration_seconds: float,
) -> dict[str, Any]:
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    lane_root.mkdir(parents=True, exist_ok=True)
    record = _terminal_record(lane_id, error)
    existing_ledger = lane_root / "checksums.sha256"
    if existing_ledger.exists():
        _write_json(
            FORMAL_ROOT / "terminal-failures" / f"{lane_id}.json",
            {
                "schema_version": 2,
                "kind": "post_seal_terminal_failure",
                "lane_id": lane_id,
                "formal_attempt_id": FORMAL_ATTEMPT_ID,
                "terminal": True,
                "reason": f"{type(error).__name__}: {error}",
                "sealed_lane_ledger": _artifact_ref(existing_ledger),
                "retry_permitted": False,
                "replacement_permitted": False,
                "discretionary_rerun_permitted": False,
            },
        )
        return {
            "lane_id": lane_id,
            "role": role,
            "accountable": False,
            "execution_record_accountable": is_execution_record_accountable(record),
            "terminal": True,
            "formal_attempt_id": FORMAL_ATTEMPT_ID,
            "execution_record_attempt_id": record["attempt_id"],
            "lane_attempt_count": 1,
            "retry_count": 0,
            "replacement_count": 0,
            "discretionary_rerun_count": 0,
            "production_invocation_id": None,
            "production_identity_sha256": None,
            "finding_conclusion": "inconclusive",
            "attempt_evidence": {},
            "attempt_evidence_receipt": {},
            "falsification_review": {"status": "unknown", "outcome": "inconclusive"},
            "duration_seconds": duration_seconds,
            "terminal_error": f"{type(error).__name__}: {error}",
        }
    required = load_manifest(MANIFEST_PATH, require_frozen=True).document["evidence"][
        "required_artifacts"
    ]
    absent = _absent_required_artifacts(lane_root, required)
    _write_json(
        lane_root / "typed-absence.json",
        {
            "schema_version": 2,
            "kind": "terminal_formal_lane_absence",
            "lane_id": lane_id,
            "formal_attempt_id": FORMAL_ATTEMPT_ID,
            "terminal": True,
            "reason": f"{type(error).__name__}: {error}",
            "execution_record_accountable": is_execution_record_accountable(record),
            "absent_artifacts": absent,
            "retry_permitted": False,
            "replacement_permitted": False,
            "discretionary_rerun_permitted": False,
        },
    )
    _lane_ledger(lane_root)
    return {
        "lane_id": lane_id,
        "role": role,
        "accountable": False,
        "execution_record_accountable": is_execution_record_accountable(record),
        "terminal": True,
        "formal_attempt_id": FORMAL_ATTEMPT_ID,
        "execution_record_attempt_id": record["attempt_id"],
        "lane_attempt_count": 1,
        "retry_count": 0,
        "replacement_count": 0,
        "discretionary_rerun_count": 0,
        "production_invocation_id": None,
        "production_identity_sha256": None,
        "finding_conclusion": "inconclusive",
        "attempt_evidence": {},
        "attempt_evidence_receipt": {},
        "falsification_review": {
            "status": "not_run",
            "outcome": "inconclusive",
            "typed_absence": "typed-absence.json",
        },
        "duration_seconds": duration_seconds,
        "terminal_error": f"{type(error).__name__}: {error}",
    }


def _execute_lane_once(
    lane_id: str,
    admitted: AdmittedLane,
    *,
    ime_guard: dict[str, str],
    lineage: EvidenceLineage,
) -> ExecutedLane:
    frozen_path = admitted.frozen_path
    spec = admitted.spec
    options = admitted.options
    admission = admitted.admission
    lane_root = FORMAL_ARTIFACT_ROOT / lane_id
    token = PROBE_TOKENS[LANE_IDS.index(lane_id)]
    _verify_source(
        options.workdir,
        commit=admitted.source.commit,
        tree=admitted.source.tree,
    )
    _verify_apk(
        options.workdir / APK_GLOB,
        expected_bytes=admitted.source.apk_bytes,
        expected_sha256=admitted.source.apk_sha256,
    )
    effective_path, effective_spec = _resolved_spec(
        lane_id,
        frozen_path,
        options.workdir,
        admitted.source.commit,
    )
    started = time.monotonic()
    result = run_spec(
        spec,
        device=options.device,
        artifact_dir=options.artifact_dir,
        workdir=options.workdir,
        launch=options.launch,
        model=None,
        l3_model=None,
        instruction_prefix=None,
        pre_run_setup=lambda: _pre_run_environment(lane_root, ime_guard),
        run_spec_path=frozen_path,
        identity_collector_factory=_identity_factory(
            lane_id=lane_id,
            frozen_path=frozen_path,
            effective_path=effective_path,
            effective_spec=effective_spec,
            workdir=options.workdir,
            artifact_dir=options.artifact_dir,
        ),
        admission_required=True,
        admission_receipt=admission,
        admission_options=options,
        formal_one_attempt=True,
    )
    duration = round(time.monotonic() - started, 3)
    record = load_execution_record(lane_root / "execution-record.json")
    if record.get("lifecycle_state") != "completed" or not is_execution_record_accountable(record):
        reason = result.get("execution", {}).get("reason", "non_accountable")
        raise M9RecoveryFormalError(f"{lane_id} runner terminated non-accountably: {reason}")
    identity = _write_effective_identity(lane_id, record)
    raw_refs, conclusion = _normalize_raw_evidence(
        lane_id,
        token,
    )
    oracle, _finding = _write_semantic_evidence(
        lane_id,
        token,
        record,
        raw_refs,
        conclusion,
        lineage,
    )
    if oracle["accountable"] is not True:
        raise M9RecoveryFormalError(f"{lane_id} oracle evidence is inconclusive")
    _prepare_review_context(lane_id, record)
    identity_sha = sha256_file(lane_root / "effective-execution-identity.json")
    review = execute_falsification_review(
        lane_id=lane_id,
        repository_root=REPO_ROOT,
        production_invocation_id=identity["production_invocation_id"],
        production_identity_sha256=identity_sha,
        timeout_seconds=900,
    )
    return ExecutedLane(
        record=record,
        identity=identity,
        finding_conclusion=conclusion,
        review=review,
        duration_seconds=duration,
    )


def _execute_or_preserve_terminal(
    lane_id: str,
    admitted: AdmittedLane,
    role: str,
    *,
    ime_guard: dict[str, str],
    lineage: EvidenceLineage,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        executed = _execute_lane_once(
            lane_id,
            admitted,
            ime_guard=ime_guard,
            lineage=lineage,
        )
        return _seal_successful_lane(
            lane_id,
            role,
            executed.record,
            executed.identity,
            executed.finding_conclusion,
            executed.review,
            executed.duration_seconds,
        )
    except Exception as error:  # noqa: BLE001 - every lane must receive one terminal row
        return _seal_failed_lane(
            lane_id,
            role,
            error,
            duration_seconds=round(time.monotonic() - started, 3),
        )


def _write_attempt_inventory(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    execution_records = []
    for row in rows:
        lane_id = str(row["lane_id"])
        path = FORMAL_ARTIFACT_ROOT / lane_id / "execution-record.json"
        execution_records.append(
            {
                "lane_id": lane_id,
                "execution_record_attempt_id": row["execution_record_attempt_id"],
                **_artifact_ref(path),
            }
        )
    attempts = [
        {
            "formal_attempt_id": FORMAL_ATTEMPT_ID,
            "attempt_number": 1,
            "lane_order": list(LANE_IDS),
            "lane_count": 6,
            "terminal_lane_count": sum(row.get("terminal") is True for row in rows),
            "retry_count": 0,
            "replacement_count": 0,
            "discretionary_rerun_count": 0,
            "execution_records": execution_records,
        }
    ]
    path = FORMAL_ROOT / "formal-attempt-inventory.json"
    _write_json(path, {"schema_version": 2, "formal_attempts": attempts})
    return attempts, _artifact_ref(path)


def _root_ledger() -> dict[str, str]:
    path = FORMAL_ROOT / "checksums.sha256"
    entries = [
        item
        for item in sorted(FORMAL_ROOT.rglob("*"))
        if item.is_file() and item != path
    ]
    _write_text(
        path,
        "".join(
            f"{sha256_file(item)}  {item.relative_to(FORMAL_ROOT).as_posix()}\n"
            for item in entries
        ),
    )
    return _artifact_ref(path)


def _seal_remaining_lanes(
    rows: list[dict[str, Any]],
    roles: Mapping[str, str] | None,
    error: Exception,
) -> None:
    completed = {str(row["lane_id"]) for row in rows}
    for lane_id in LANE_IDS:
        if lane_id in completed:
            continue
        rows.append(
            _seal_failed_lane(
                lane_id,
                roles.get(lane_id) if roles is not None else None,
                error,
                duration_seconds=0.0,
            )
        )


def _finalize_formal_attempt(
    *,
    rows: Sequence[Mapping[str, Any]],
    inputs: FormalInputs,
    contradiction: Mapping[str, Any] | None,
    mapping: Mapping[str, Any] | None,
    leakage: Mapping[str, Any] | None,
    fixtures: Sequence[Mapping[str, Any]],
    ime_guard: Mapping[str, str],
    started: float,
    state: FormalState,
    terminal_error: str | None,
) -> dict[str, Any]:
    attempts, inventory_ref = _write_attempt_inventory(rows)
    auditor_input = {
        "schema_version": 2,
        "qualification_id": QUALIFICATION_ID,
        "formal_attempt_id": FORMAL_ATTEMPT_ID,
        "consumer_commit": inputs.expected_consumer_commit,
        "lane_order": list(LANE_IDS),
        "rows": list(rows),
        "contradiction": contradiction,
        "contradiction_canonical_sha256": (
            sha256_bytes(canonical_json_bytes(contradiction))
            if contradiction is not None
            else None
        ),
        "mapping": mapping,
        "mapping_released": mapping is not None,
        "mapping_canonical_sha256": (
            sha256_bytes(canonical_json_bytes(mapping))
            if mapping is not None
            else None
        ),
        "formal_attempt_inventory": attempts,
        "formal_attempt_inventory_receipt": inventory_ref,
        "terminal_error": terminal_error,
        "aggregate_interpretation_reserved_for": "M9-R5",
    }
    _write_json(FORMAL_ROOT / "auditor-reconciliation-input.json", auditor_input)
    if terminal_error is not None:
        _write_json(
            FORMAL_ROOT / "formal-attempt-terminal-failure.json",
            {
                "schema_version": 2,
                "kind": "formal_attempt_terminal_failure",
                "formal_attempt_id": FORMAL_ATTEMPT_ID,
                "terminal": True,
                "stage": state.stage.name,
                "reason": terminal_error,
                "mapping_released": mapping is not None,
                "retry_permitted": False,
                "replacement_permitted": False,
                "discretionary_rerun_permitted": False,
            },
        )
    summary = {
        "schema_version": 2,
        "status": "completed" if terminal_error is None else "terminal_failed",
        "qualification_id": QUALIFICATION_ID,
        "formal_attempt_id": FORMAL_ATTEMPT_ID,
        "formal_execution_started": True,
        "formal_holdout_executed": state.stage >= FormalStage.EXECUTING,
        "consumer_commit": inputs.expected_consumer_commit,
        "duration_seconds": round(time.monotonic() - started, 3),
        "lane_order": list(LANE_IDS),
        "terminal_lane_count": len(rows),
        "execution_accountable_count": sum(
            row["accountable"] is True for row in rows
        ),
        "attempt_evidence_validated_count": sum(
            row.get("attempt_evidence_validated") is True for row in rows
        ),
        "review_survived_count": sum(
            row.get("falsification_review", {}).get("outcome") == "survived"
            for row in rows
        ),
        "retry_count": 0,
        "replacement_count": 0,
        "discretionary_rerun_count": 0,
        "mapping_released_after_neutral_gates": mapping is not None,
        "leakage_audit_status": (
            leakage["audit"]["status"] if leakage is not None else "not_completed"
        ),
        "source_fixture_count": max(
            len(fixtures),
            len(list((FORMAL_ROOT / "source-fixtures").glob("*.json"))),
        ),
        "default_input_method": ime_guard.get("value"),
        "terminal_error": terminal_error,
        "aggregate_result": "reserved_for_M9_R5",
        "claim_boundary": LOCAL_CLAIM_BOUNDARY,
        "r1_r2_inputs_reused": False,
        "preserved_runtime_result": (
            "#137 remains Not Supported and is never rerun or rewritten"
        ),
    }
    _write_json(FORMAL_ROOT / "formal-execution-summary.json", summary)
    summary["root_ledger"] = _root_ledger()
    return summary


def execute_formal(inputs: FormalInputs) -> dict[str, Any]:
    """Execute the approved recovery-v2 packet once and stop before R5 reduction."""

    if not re.fullmatch(r"[0-9a-f]{40}", inputs.expected_consumer_commit):
        raise M9RecoveryFormalError("expected consumer commit must be a Git SHA-1")
    preflight = static_preflight(require_formal_root_absent=True)
    repository = _repository_identity(inputs.expected_consumer_commit)
    bindings = _source_bindings(inputs)
    input_preflight = _validate_formal_inputs(inputs, bindings)
    _claim_formal_root(preflight, repository)
    state = FormalState()
    started = time.monotonic()
    contradiction: Mapping[str, Any] | None = None
    leakage: Mapping[str, Any] | None = None
    mapping: Mapping[str, Any] | None = None
    roles: dict[str, str] | None = None
    fixtures: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    ime_guard: dict[str, str] = {}
    try:
        _write_json(FORMAL_ROOT / "formal-input-preflight.json", input_preflight)
        manifest = load_manifest(MANIFEST_PATH, require_frozen=True).document
        contradiction = _reject_contradiction(manifest)
        state.advance(FormalStage.CREATED, FormalStage.CONTRADICTION_REJECTED)
        target, context, _portfolio, metadata = _discover_context_and_portfolio(
            inputs.project_target.resolve()
        )
        lineage = EvidenceLineage(
            hypothesis_id=metadata["selected"].hypothesis.hypothesis_id,
            explored_fact_ids=tuple(
                metadata["selected"].hypothesis.supporting_fact_ids
            ),
        )
        state.advance(
            FormalStage.CONTRADICTION_REJECTED,
            FormalStage.CONTEXT_ACQUIRED,
        )
        state.advance(FormalStage.CONTEXT_ACQUIRED, FormalStage.PORTFOLIO_FROZEN)
        generation = _attack_plan(
            target,
            context,
            metadata,
            inputs.project_target.resolve(),
        )
        state.advance(FormalStage.PORTFOLIO_FROZEN, FormalStage.PLAN_ADMITTED)
        leakage = _leakage_gate(manifest, metadata, generation)
        state.advance(FormalStage.PLAN_ADMITTED, FormalStage.LEAKAGE_AUDITED)
        mapping = _release_mapping(manifest)
        roles = _mapping_roles(mapping)
        state.advance(FormalStage.LEAKAGE_AUDITED, FormalStage.MAPPING_RELEASED)
        admitted, fixtures = _admit_lanes(
            roles,
            bindings,
            inputs,
            state,
        )
        for lane_id in LANE_IDS:
            state.start_lane(lane_id)
            row = _execute_or_preserve_terminal(
                lane_id,
                admitted[lane_id],
                roles[lane_id],
                ime_guard=ime_guard,
                lineage=lineage,
            )
            rows.append(row)
            state.finish_lane(lane_id)
        if state.stage is not FormalStage.TERMINAL:
            raise M9RecoveryFormalError(
                "formal cohort did not reach six terminal lanes"
            )
    except Exception as error:  # noqa: BLE001 - claimed attempts must be terminal
        _seal_remaining_lanes(rows, roles, error)
        return _finalize_formal_attempt(
            rows=rows,
            inputs=inputs,
            contradiction=contradiction,
            mapping=mapping,
            leakage=leakage,
            fixtures=fixtures,
            ime_guard=ime_guard,
            started=started,
            state=state,
            terminal_error=f"{type(error).__name__}: {error}",
        )
    return _finalize_formal_attempt(
        rows=rows,
        inputs=inputs,
        contradiction=contradiction,
        mapping=mapping,
        leakage=leakage,
        fixtures=fixtures,
        ime_guard=ime_guard,
        started=started,
        state=state,
        terminal_error=None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--static-preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-consumer-commit")
    parser.add_argument("--project-target", type=Path, default=DEFAULT_PROJECT_TARGET)
    parser.add_argument("--control-apk", type=Path, default=DEFAULT_CONTROL_APK)
    parser.add_argument("--defect-project", type=Path, default=DEFAULT_DEFECT_PROJECT)
    parser.add_argument("--defect-apk", type=Path, default=DEFAULT_DEFECT_APK)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    args = parser.parse_args(argv)
    if args.static_preflight:
        result = static_preflight()
    else:
        if args.expected_consumer_commit is None:
            parser.error("--execute requires --expected-consumer-commit")
        result = execute_formal(
            FormalInputs(
                expected_consumer_commit=args.expected_consumer_commit,
                project_target=args.project_target,
                control_apk=args.control_apk,
                defect_project=args.defect_project,
                defect_apk=args.defect_apk,
                source_root=args.source_root,
            )
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("status") == "terminal_failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
