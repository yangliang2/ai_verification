"""Regenerate the issue-211 post-observation fail-closed evidence.

Run from the repository root:

    PYTHONPATH=src .venv/bin/python \
      docs/runs/2026-09-29-issue-211-post-observation-fail-closed/\
verification/generate_evidence.py

The script drives the public lane seam (``execute_runtime_attempt``) once per
matrix case on the recording device with a pinned clock, re-runs the
independent verifier (``verify_runtime_attempt``) over each committed attempt
root, and rewrites ``post-observation-matrix.json``.  Every case asserts the
reason, scope, terminal phase, dispatched-mutation prefix, and closure state it
is expected to produce, so the committed JSON can never silently drift from the
frozen contract.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
from pathlib import Path

from aiverify.bench import runtime_attempt as ra
from aiverify.runner.deterministic_backend import load_deterministic_driver_plan
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    RuntimePreparationReceipt,
    _canonical_bytes,
    _identity,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
RUN_ROOT = REPO_ROOT / "docs/runs/2026-09-29-issue-211-post-observation-fail-closed"
VERIFICATION = RUN_ROOT / "verification"
LANE_ROOT = (
    REPO_ROOT
    / "bench/runtime-calibration/opencalc-input-save-enabled-v1/runtime/lanes/lane-01"
)
LANE_ID = "ocrc-v1-lane-01"
RECORDING_SERIAL = "recording-device"
SEALED_APK_BYTES = b"sealed opencalc runtime apk bytes"
BASELINE_HEAD = "2a5d16b"
TARGET_LOG_WINDOW_ARTIFACT = (
    f"{ra.ARTIFACTS_DIRNAME}/{ra.TARGET_LOG_WINDOW_FILENAME}"
)

_SETUP_WRITES = (
    "deploy_apk",
    "clear_package_data",
    "write_rotation_setting",
    "write_rotation_setting",
)
_LAUNCH_PREFIX = (
    *_SETUP_WRITES,
    "clear_log_buffers",
    "write_log_marker",
    "canonical_launch",
)
_TAP_PREFIX = (*_LAUNCH_PREFIX, *("tap",) * len(ra.FROZEN_TAP_TRAJECTORY))
_BOUNDARY_PREFIX = (*_TAP_PREFIX, "write_log_marker")
_ROTATION_PREFIX = (*_BOUNDARY_PREFIX, "write_log_marker")
_COMPLETE_PREFIX = (
    *_TAP_PREFIX,
    "write_log_marker",
    "dispatch_orientation",
    "write_log_marker",
    "write_log_marker",
)


@dataclasses.dataclass(frozen=True)
class FailureCase:
    """One material post-boundary failure and its frozen fail-closed shape."""

    label: str
    reason: str
    scope: str
    phase: str
    policy: ra.RecordingDevicePolicy
    dispatched: tuple[str, ...]
    window: str
    identity: str = "closed"
    drifted: tuple[str, ...] = ()


@dataclasses.dataclass(frozen=True)
class ObservationCase:
    """One bounded post-event observation and its accountable L2 result."""

    label: str
    l2_outcome: str
    l2_detail: str
    verdict: str
    exit_code: int
    policy: ra.RecordingDevicePolicy = dataclasses.field(
        default_factory=ra.RecordingDevicePolicy
    )


FAILURE_CASES = (
    FailureCase(
        "boundary-input-missing",
        "boundary_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "boundary-precondition",
        ra.RecordingDevicePolicy(boundary_layout_fault="missing_input"),
        _BOUNDARY_PREFIX,
        "abort",
    ),
    FailureCase(
        "boundary-input-duplicated",
        "boundary_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "boundary-precondition",
        ra.RecordingDevicePolicy(boundary_layout_fault="duplicate_input"),
        _BOUNDARY_PREFIX,
        "abort",
    ),
    FailureCase(
        "boundary-input-geometry-invalid",
        "boundary_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "boundary-precondition",
        ra.RecordingDevicePolicy(boundary_layout_fault="invalid_geometry"),
        _BOUNDARY_PREFIX,
        "abort",
    ),
    FailureCase(
        "boundary-text-drifted",
        "boundary_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "boundary-precondition",
        ra.RecordingDevicePolicy(boundary_layout_fault="wrong_text"),
        _BOUNDARY_PREFIX,
        "abort",
    ),
    FailureCase(
        "boundary-text-omitted",
        "boundary_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "boundary-precondition",
        ra.RecordingDevicePolicy(boundary_layout_fault="omitted_text"),
        _BOUNDARY_PREFIX,
        "abort",
    ),
    FailureCase(
        "boundary-layout-malformed",
        "boundary_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "boundary-precondition",
        ra.RecordingDevicePolicy(boundary_layout_fault="malformed"),
        _BOUNDARY_PREFIX,
        "abort",
    ),
    FailureCase(
        "rotation-dispatch-refused",
        "orientation_dispatch_failed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "lifecycle-rotation",
        ra.RecordingDevicePolicy(
            fail_operations=frozenset({"dispatch_orientation"})
        ),
        _ROTATION_PREFIX,
        "abort",
    ),
    FailureCase(
        "rotation-not-observed",
        "orientation_not_observed",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "lifecycle-rotation",
        ra.RecordingDevicePolicy(lifecycle_fault="landscape_not_resumed"),
        _COMPLETE_PREFIX,
        "abort",
    ),
    FailureCase(
        "post-event-layout-malformed",
        "post_event_layout_unreadable",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "collect-post-event-observation",
        ra.RecordingDevicePolicy(post_event_layout_fault="malformed"),
        _COMPLETE_PREFIX,
        "abort",
    ),
    FailureCase(
        "log-dump-refused",
        "target_log_window_capture_failed",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(
            fail_operations=frozenset({"dump_all_buffers_epoch"})
        ),
        _COMPLETE_PREFIX,
        "refused",
    ),
    FailureCase(
        "log-dump-empty",
        "target_log_window_marker_error",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(log_dump_fault="empty_dump"),
        _COMPLETE_PREFIX,
        "unproven",
    ),
    FailureCase(
        "log-end-marker-missing",
        "target_log_window_marker_error",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(log_dump_fault="missing_end_marker"),
        _COMPLETE_PREFIX,
        "unproven",
    ),
    FailureCase(
        "log-markers-reversed",
        "target_log_window_marker_error",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(log_dump_fault="reversed_markers"),
        _COMPLETE_PREFIX,
        "unproven",
    ),
    FailureCase(
        "log-markers-duplicated",
        "target_log_window_marker_error",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(log_dump_fault="duplicated_markers"),
        _COMPLETE_PREFIX,
        "unproven",
    ),
    FailureCase(
        "log-window-truncated",
        "target_log_window_marker_error",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(log_dump_fault="truncated_dump"),
        _COMPLETE_PREFIX,
        "unproven",
    ),
    FailureCase(
        "log-window-incomplete",
        "target_log_window_capture_failed",
        ra.FAILURE_SCOPE_SHARED,
        "close-target-log-window",
        ra.RecordingDevicePolicy(log_dump_fault="incomplete_window"),
        _COMPLETE_PREFIX,
        "unproven",
    ),
    FailureCase(
        "log-lifecycle-marker-missing",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(log_dump_fault="missing_lifecycle_marker"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "log-lifecycle-marker-duplicated",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(log_dump_fault="duplicated_lifecycle_marker"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-events-reordered",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(lifecycle_fault="reordered_events"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-event-duplicated",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(lifecycle_fault="duplicated_event"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-event-missing",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(lifecycle_fault="missing_event"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-relaunch-missing",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(lifecycle_fault="relaunch_missing"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-task-changed",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(lifecycle_fault="task_changed"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-pid-changed",
        "lifecycle_transition_unproven",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(lifecycle_fault="pid_changed"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "lifecycle-target-restarted",
        "target_process_restarted",
        ra.FAILURE_SCOPE_LANE_LOCAL,
        "prove-lifecycle-transition",
        ra.RecordingDevicePolicy(restart_target_process=True),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "log-foreign-crash-unattributable",
        "log_attribution_ambiguous",
        ra.FAILURE_SCOPE_UNKNOWN,
        "evaluate-oracles",
        ra.RecordingDevicePolicy(log_dump_fault="foreign_crash"),
        _COMPLETE_PREFIX,
        "phase",
    ),
    FailureCase(
        "post-cell-probe-refused",
        "device_session_unavailable",
        ra.FAILURE_SCOPE_SHARED,
        "close-post-cell-identity",
        ra.RecordingDevicePolicy(session_drift_fault="refused"),
        _COMPLETE_PREFIX,
        "phase",
        identity="refused",
    ),
    FailureCase(
        "post-cell-serial-drifted",
        "device_session_identity_drifted",
        ra.FAILURE_SCOPE_SHARED,
        "close-post-cell-identity",
        ra.RecordingDevicePolicy(session_drift_fault="serial_changed"),
        _COMPLETE_PREFIX,
        "phase",
        identity="drifted",
        drifted=("serial",),
    ),
    FailureCase(
        "post-cell-field-missing",
        "device_session_identity_drifted",
        ra.FAILURE_SCOPE_SHARED,
        "close-post-cell-identity",
        ra.RecordingDevicePolicy(session_drift_fault="fields_missing"),
        _COMPLETE_PREFIX,
        "phase",
        identity="drifted",
        drifted=("boot_id",),
    ),
    FailureCase(
        "post-cell-setting-missing",
        "device_session_identity_drifted",
        ra.FAILURE_SCOPE_SHARED,
        "close-post-cell-identity",
        ra.RecordingDevicePolicy(session_drift_fault="settings_missing"),
        _COMPLETE_PREFIX,
        "phase",
        identity="drifted",
        drifted=("settings.font_scale",),
    ),
    FailureCase(
        "post-cell-setting-drifted",
        "device_session_identity_drifted",
        ra.FAILURE_SCOPE_SHARED,
        "close-post-cell-identity",
        ra.RecordingDevicePolicy(session_drift_fault="identity_drifted"),
        _COMPLETE_PREFIX,
        "phase",
        identity="drifted",
        drifted=("settings.font_scale",),
    ),
)

OBSERVATION_CASES = (
    ObservationCase(
        "post-event-text-exact",
        ra.L2_OUTCOME_PASS,
        "preserved_state",
        ra.L1_OUTCOME_INCONCLUSIVE,
        0,
    ),
    ObservationCase(
        "post-event-text-drifted",
        ra.L2_OUTCOME_FAIL,
        "state_loss",
        ra.L1_OUTCOME_FAIL,
        1,
        ra.RecordingDevicePolicy(post_event_layout_fault="wrong_text"),
    ),
    ObservationCase(
        "post-event-text-omitted",
        ra.L2_OUTCOME_FAIL,
        "state_loss",
        ra.L1_OUTCOME_FAIL,
        1,
        ra.RecordingDevicePolicy(post_event_layout_fault="omitted_text"),
    ),
    ObservationCase(
        "post-event-save-disabled",
        ra.L2_OUTCOME_FAIL,
        "state_loss",
        ra.L1_OUTCOME_FAIL,
        1,
        ra.RecordingDevicePolicy(save_enabled=False),
    ),
    ObservationCase(
        "post-event-input-missing",
        ra.L2_OUTCOME_INCONCLUSIVE,
        "post_event_input_missing",
        ra.L1_OUTCOME_INCONCLUSIVE,
        0,
        ra.RecordingDevicePolicy(post_event_layout_fault="missing_input"),
    ),
    ObservationCase(
        "post-event-input-duplicated",
        ra.L2_OUTCOME_INCONCLUSIVE,
        "post_event_input_duplicated",
        ra.L1_OUTCOME_INCONCLUSIVE,
        0,
        ra.RecordingDevicePolicy(post_event_layout_fault="duplicate_input"),
    ),
    ObservationCase(
        "post-event-input-unusable",
        ra.L2_OUTCOME_INCONCLUSIVE,
        "post_event_input_unusable",
        ra.L1_OUTCOME_INCONCLUSIVE,
        0,
        ra.RecordingDevicePolicy(post_event_layout_fault="invalid_geometry"),
    ),
)


def _preparation_receipt(apk_path: Path) -> RuntimePreparationReceipt:
    """Return one minimal, byte-exact prepared handoff for the sealed APK."""
    payload = apk_path.read_bytes()
    document: dict[str, object] = {
        "schema_version": 1,
        "status": "prepared",
        "prepared": True,
        "rejection_code": None,
        "claim_boundary": "local_source_build_preparation_only",
        "build": {
            "returncode": 0,
            "retry": False,
            "test_substitutes": True,
        },
        "sealed_apk": {
            "path": str(apk_path.resolve()),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "mode": "0444",
            "regular": True,
            "symlink": False,
            "hard_links": 1,
        },
        "runtime_effects": {
            "shell": False,
            "device": False,
            "android_deployment": False,
            "execution_record": False,
            "agent_or_model": False,
        },
    }
    document["receipt_identity_sha256"] = _identity(document)
    encoded = _canonical_bytes(document)
    return RuntimePreparationReceipt(
        prepared=True,
        receipt_bytes=encoded,
        receipt_sha256=hashlib.sha256(encoded).hexdigest(),
        rejection_code=None,
    )


def _lane_inputs() -> tuple[RunSpec, object]:
    spec = load_run_spec(LANE_ROOT / "run-spec.yaml")
    plan = load_deterministic_driver_plan(
        LANE_ROOT / "driver-plan.json",
        serialized_run_spec=(LANE_ROOT / "run-spec.yaml").read_bytes(),
        run_spec_path=LANE_ROOT / "run-spec.yaml",
        expected_actions=tuple(spec.scenario.user_actions),
    )
    return spec, plan


def _policy_document(policy: ra.RecordingDevicePolicy) -> dict[str, object]:
    document: dict[str, object] = {}
    for name, value in dataclasses.asdict(policy).items():
        document[name] = sorted(value) if isinstance(value, (set, frozenset)) else value
    return document


def _drive(
    label: str, policy: ra.RecordingDevicePolicy
) -> tuple[object, object, object, dict[str, object], dict[str, object]]:
    """Execute one labelled case through the public seam and verify it."""
    attempt_root = VERIFICATION / "attempts" / label
    handoff_root = VERIFICATION / "handoffs" / label
    for path in (attempt_root, handoff_root):
        shutil.rmtree(path, ignore_errors=True)
    handoff_root.mkdir(parents=True, exist_ok=True)
    apk_path = handoff_root / "sealed-runtime.apk"
    apk_path.write_bytes(SEALED_APK_BYTES)
    apk_path.chmod(0o444)

    spec, plan = _lane_inputs()
    device = ra.RecordingRuntimeDevice(
        policy=policy,
        package=spec.package,
        activity=spec.activity,
    )
    request = ra.RuntimeAttemptRequest(
        lane_id=LANE_ID,
        run_spec=spec,
        driver_plan=plan,
        setup_plan=ra.RuntimeAttemptSetupPlan(
            family_id=plan.family_id,
            family_version=plan.family_version,
            package=spec.package,
        ),
        preparation_receipt=_preparation_receipt(apk_path),
        device=device,
        output_root=attempt_root,
        started_at="2026-09-29T00:00:00Z",
        clock=lambda: 1_000.0,
        sleeper=lambda _seconds: None,
    )
    outcome = ra.execute_runtime_attempt(request)
    verified = ra.verify_runtime_attempt(attempt_root)
    record = load_execution_record(attempt_root / ra.RECORD_FILENAME)
    return device, request, outcome, verified, record


def _observe_window(
    case: FailureCase, outcome: object, request: object
) -> dict[str, object]:
    """Assert the one target log window state the aborted attempt owes."""
    window = dict(outcome.components["target_log_window"])
    capture_path = request.output_root / TARGET_LOG_WINDOW_ARTIFACT
    if case.window == "phase":
        assert window["closed"] is True, case.label
        assert "partial" not in window, case.label
        assert window["capture_path"] == TARGET_LOG_WINDOW_ARTIFACT, case.label
        assert window["line_count"] > 0, case.label
    elif case.window == "abort":
        assert window["closed"] is True, case.label
        assert window["partial"] is True, case.label
        assert window["capture"] == "partial", case.label
        assert window["capture_path"] == TARGET_LOG_WINDOW_ARTIFACT, case.label
    elif case.window == "refused":
        assert window["closed"] is False, case.label
        assert window["capture"] == "unavailable_after_abort", case.label
        assert window["capture_error"], case.label
        assert not capture_path.exists(), case.label
    else:
        assert window["closed"] is False, case.label
        assert "partial" not in window, case.label
        assert "capture_path" not in window, case.label
        assert not capture_path.exists(), case.label
    if case.window in {"phase", "abort"}:
        assert capture_path.is_file(), case.label
        assert (
            hashlib.sha256(capture_path.read_bytes()).hexdigest()
            == window["capture_sha256"]
        ), case.label
    return {
        "closed": window.get("closed"),
        "partial": window.get("partial"),
        "capture": window.get("capture"),
        "capture_path": window.get("capture_path"),
        "capture_sha256": window.get("capture_sha256"),
        "start_line": window.get("start_line"),
        "end_line": window.get("end_line"),
        "line_count": window.get("line_count"),
        "artifact_exists": capture_path.is_file(),
    }


def _observe_identity(
    case: FailureCase, outcome: object, device: object
) -> dict[str, object]:
    """Assert the post-cell identity close the aborted attempt still owes."""
    counts = device.operation_counts()
    identity = dict(outcome.components["post_cell_identity"])
    assert counts["probe_session"] == 2, case.label
    if case.identity == "refused":
        assert identity["closed"] is False, case.label
        assert "fields" not in identity, case.label
        return {
            "closed": identity["closed"],
            "drifted_fields": identity.get("drifted_fields"),
            "has_fields": False,
        }
    assert identity["closed"] is True, case.label
    reference = dict(outcome.components["device_session"]["fields"])
    assert identity["reference_fields"] == reference, case.label
    assert tuple(identity["drifted_fields"]) == case.drifted, case.label
    if case.drifted:
        assert identity["fields"] != identity["reference_fields"], case.label
    else:
        assert identity["fields"] == identity["reference_fields"], case.label
    return {
        "closed": identity["closed"],
        "drifted_fields": list(identity["drifted_fields"]),
        "has_fields": True,
        "reference_fields_sha256": hashlib.sha256(
            json.dumps(reference, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }


def _run_failure(case: FailureCase) -> dict[str, object]:
    device, request, outcome, verified, record = _drive(case.label, case.policy)
    failure = dict(outcome.document["failure"])

    assert outcome.terminal_state == ra.NON_ACCOUNTABLE, case.label
    assert outcome.accountable_concluded is False, case.label
    assert outcome.reason == case.reason, (case.label, outcome.reason, case.reason)
    assert outcome.verdict == ra.L1_OUTCOME_INCONCLUSIVE, case.label
    assert "oracles" not in outcome.components, case.label
    assert failure["phase"] == case.phase, (case.label, failure["phase"])
    assert failure["scope"] == case.scope, (case.label, failure["scope"])
    assert failure["reason"] == case.reason, case.label
    assert ra.failure_scope(case.reason) == case.scope, case.label
    assert verified["verified"] is True, case.label
    assert verified["reason"] == case.reason, case.label
    assert verified["recomputed"] is None, case.label
    assert record["process_outcome"] == {"exit_code": 2}, case.label
    assert record["lifecycle_state"] == "failed", case.label
    assert len(record["phase_errors"]) == 1, case.label

    phases = outcome.document["phases"]
    assert [entry["phase"] for entry in phases] == list(
        ra.FROZEN_PHASES[: ra.FROZEN_PHASES.index(case.phase) + 1]
    ), case.label
    assert phases[-1]["status"] == "failed", case.label
    assert all(entry["status"] == "ok" for entry in phases[:-1]), case.label

    operations = [operation for operation, _vector in device.mutation_operations()]
    assert tuple(operations) == case.dispatched, (case.label, operations)
    counts = device.operation_counts()
    assert counts.get("dispatch_orientation", 0) <= 1, case.label
    assert counts["probe_session"] == 2, case.label
    window = _observe_window(case, outcome, request)
    identity = _observe_identity(case, outcome, device)

    return {
        "label": case.label,
        "expected": {
            "reason": case.reason,
            "scope": case.scope,
            "phase": case.phase,
            "dispatched": list(case.dispatched),
            "window": case.window,
            "identity": case.identity,
            "drifted": list(case.drifted),
        },
        "policy": _policy_document(case.policy),
        "terminal_state": outcome.terminal_state,
        "reason": outcome.reason,
        "verdict": outcome.verdict,
        "failure": failure,
        "phases": [entry["phase"] for entry in phases],
        "phase_statuses": {
            entry["phase"]: entry["status"] for entry in phases
        },
        "components": sorted(outcome.components),
        "dispatched_mutations": operations,
        "operation_counts": dict(counts),
        "markers": list(device.markers()),
        "window": window,
        "post_cell_identity": identity,
        "record": {
            "lifecycle_state": record["lifecycle_state"],
            "process_outcome": record["process_outcome"],
            "execution": record["execution"],
            "phase_errors": record["phase_errors"],
            "attempt_artifacts": record["evidence_refs"]["attempt_artifacts"],
        },
        "verification": {
            "verified": verified["verified"],
            "reason": verified["reason"],
            "checks": verified["checks"],
            "recomputed": verified["recomputed"],
        },
        "receipt": {
            "path": f"attempts/{case.label}/attempt-receipt.json",
            "bytes": len(outcome.payload),
            "sha256": outcome.sha256,
        },
    }


def _run_observation(case: ObservationCase) -> dict[str, object]:
    device, _request, outcome, verified, record = _drive(case.label, case.policy)

    assert outcome.terminal_state == ra.ACCOUNTABLE_CONCLUDED, case.label
    assert outcome.reason is None, case.label
    assert outcome.verdict == case.verdict, (case.label, outcome.verdict)
    assert set(outcome.components) == set(ra.REQUIRED_ACCOUNTABLE_COMPONENTS), case.label
    observation = dict(outcome.components["post_event_observation"])
    assert observation["l2_outcome"] == case.l2_outcome, case.label
    assert observation["l2_detail"] == case.l2_detail, case.label
    oracles = dict(outcome.components["oracles"])
    assert oracles["l1"]["outcome"] == ra.L1_OUTCOME_INCONCLUSIVE, case.label
    assert oracles["l2"]["outcome"] == case.l2_outcome, case.label
    assert oracles["l2"]["detail"] == case.l2_detail, case.label
    assert oracles["l2"]["defect_class"] == (
        "state_loss" if case.l2_outcome == ra.L2_OUTCOME_FAIL else None
    ), case.label
    assert oracles["verdict"] == case.verdict, case.label
    assert verified["verified"] is True, case.label
    assert verified["terminal_state"] == ra.ACCOUNTABLE_CONCLUDED, case.label
    assert verified["recomputed"]["verdict"] == case.verdict, case.label
    assert verified["recomputed"]["l2_outcome"] == case.l2_outcome, case.label
    assert "post-cell-identity" in verified["checks"], case.label
    assert record["lifecycle_state"] == "completed", case.label
    assert record["process_outcome"] == {"exit_code": case.exit_code}, case.label
    assert record["execution"]["accounting_eligible"] is True, case.label
    assert record["phase_errors"] == [], case.label

    operations = [operation for operation, _vector in device.mutation_operations()]
    assert tuple(operations) == _COMPLETE_PREFIX, (case.label, operations)
    counts = device.operation_counts()
    assert counts["dispatch_orientation"] == 1, case.label
    assert counts["probe_session"] == 2, case.label
    identity = dict(outcome.components["post_cell_identity"])
    assert identity["closed"] is True, case.label
    assert identity["drifted_fields"] == [], case.label
    assert identity["fields"] == identity["reference_fields"], case.label

    return {
        "label": case.label,
        "expected": {
            "l2_outcome": case.l2_outcome,
            "l2_detail": case.l2_detail,
            "verdict": case.verdict,
            "exit_code": case.exit_code,
        },
        "policy": _policy_document(case.policy),
        "terminal_state": outcome.terminal_state,
        "reason": outcome.reason,
        "verdict": outcome.verdict,
        "phases": [entry["phase"] for entry in outcome.document["phases"]],
        "components": sorted(outcome.components),
        "dispatched_mutations": operations,
        "operation_counts": dict(counts),
        "markers": list(device.markers()),
        "post_event_observation": {
            "input_node_count": observation["input_node_count"],
            "input_text": observation["input_text"],
            "input_valid": observation["input_valid"],
            "l2_outcome": observation["l2_outcome"],
            "l2_detail": observation["l2_detail"],
        },
        "oracles": {
            "l1_outcome": oracles["l1"]["outcome"],
            "l1_attribution": oracles["l1"]["attribution"],
            "l2_outcome": oracles["l2"]["outcome"],
            "l2_detail": oracles["l2"]["detail"],
            "l2_defect_class": oracles["l2"]["defect_class"],
            "verdict": oracles["verdict"],
        },
        "post_cell_identity": {
            "closed": identity["closed"],
            "drifted_fields": list(identity["drifted_fields"]),
        },
        "record": {
            "lifecycle_state": record["lifecycle_state"],
            "process_outcome": record["process_outcome"],
            "execution": record["execution"],
        },
        "verification": {
            "verified": verified["verified"],
            "checks": verified["checks"],
            "recomputed": verified["recomputed"],
        },
        "receipt": {
            "path": f"attempts/{case.label}/attempt-receipt.json",
            "bytes": len(outcome.payload),
            "sha256": outcome.sha256,
        },
    }


def main() -> None:
    (VERIFICATION / "attempts").mkdir(parents=True, exist_ok=True)
    failures = [_run_failure(case) for case in FAILURE_CASES]
    observations = [_run_observation(case) for case in OBSERVATION_CASES]
    document = {
        "schema_version": 1,
        "seam": ra.SEAM,
        "claim_boundary": ra.CLAIM_BOUNDARY,
        "baseline_head": BASELINE_HEAD,
        "evidence_class": "recorded_simulation",
        "lane_id": LANE_ID,
        "device_serial": RECORDING_SERIAL,
        "frozen_phases": list(ra.FROZEN_PHASES),
        "failure_scopes": dict(ra.FAILURE_SCOPES),
        "post_launch_fault_vocabularies": {
            "layout": list(ra.LAYOUT_FAULTS),
            "log_dump": list(ra.LOG_DUMP_FAULTS),
            "lifecycle": list(ra.LIFECYCLE_FAULTS),
            "session_drift": list(ra.SESSION_DRIFT_FAULTS),
        },
        "recorded_layout_reads": {
            "journey": ra.RECORDED_JOURNEY_LAYOUT_READS,
            "boundary": ra.RECORDED_BOUNDARY_LAYOUT_READ,
            "post_event": ra.RECORDED_POST_EVENT_LAYOUT_READ,
        },
        "expected_device_read_counts": dict(ra.EXPECTED_DEVICE_READ_COUNTS),
        "failure_case_count": len(failures),
        "observation_case_count": len(observations),
        "cases": failures,
        "observations": observations,
    }
    target = VERIFICATION / "post-observation-matrix.json"
    target.write_text(json.dumps(document, indent=2) + "\n")
    print(
        f"wrote {target.relative_to(REPO_ROOT)} with "
        f"{len(failures)} failures and {len(observations)} observations"
    )


if __name__ == "__main__":
    main()
