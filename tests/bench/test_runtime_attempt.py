"""Recording-device integration tests for one accountable Runtime Attempt.

The recording device is bounded test infrastructure: its layout, log, and
lifecycle lines are recorded simulation text, so every attempt below concludes
with the ``recorded_simulation`` evidence class and never claims real device
evidence.  The tests drive the public lane seam end to end and bind the frozen
phase order, the exactly-once device budget, the marker-bounded log window, the
delivered landscape event, the L1/L2 oracles, and the sealed receipt/record pair.
A table-driven pre-observation matrix additionally binds every material failure
before the product observation boundary to its exact phase prefix, canonical
reason, failure scope, and dispatched-mutation prefix, proving that prohibited
or repeated setup actions are unreachable.  A second table-driven matrix binds
every material failure after the boundary precondition to the same frozen shape,
and proves that the one rotation is dispatched once, the poll evidence is
retained, the post-cell identity is closed, and the terminal artifacts are sealed
exactly once.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import aiverify.runtime_attempt as compat_runtime_attempt
from aiverify.bench import runtime_attempt
from aiverify.bench.runtime_attempt import (
    ACCOUNTABLE_CONCLUDED,
    ALLOWED_ROTATION_SETTINGS,
    ATTEMPT_SETUP_OPERATIONS,
    ATTEMPT_SETUP_PLAN_ID,
    BOUNDARY_PRECONDITION_TEXT,
    EXPECTED_DEVICE_MUTATION_COUNTS,
    EXPECTED_DEVICE_READ_COUNTS,
    FAILURE_SCOPE_LANE_LOCAL,
    FAILURE_SCOPE_SHARED,
    FAILURE_SCOPE_UNKNOWN,
    FROZEN_TAP_TRAJECTORY,
    L1_OUTCOME_FAIL,
    L1_OUTCOME_INCONCLUSIVE,
    L2_OUTCOME_FAIL,
    L2_OUTCOME_INCONCLUSIVE,
    L2_OUTCOME_PASS,
    LANDSCAPE_ROTATION,
    LAYOUT_FAULTS,
    LIFECYCLE_END,
    LIFECYCLE_FAULTS,
    LIFECYCLE_POLL_BUDGET,
    LIFECYCLE_POLL_INTERVAL_SECONDS,
    LIFECYCLE_SIGNATURE_EVENTS,
    LIFECYCLE_SIGNATURE_ID,
    LIFECYCLE_SIGNATURE_STATUS,
    LIFECYCLE_START,
    LOG_DUMP_FAULTS,
    LOG_WINDOW_BUFFERS,
    LOG_WINDOW_FORMAT,
    MARKER_TAG,
    NON_ACCOUNTABLE,
    PORTRAIT_ROTATION,
    RECORDED_BOUNDARY_LAYOUT_READ,
    RECORDED_JOURNEY_LAYOUT_READS,
    RECORDED_POST_EVENT_LAYOUT_READ,
    REQUIRED_ACCOUNTABLE_COMPONENTS,
    SESSION_DRIFT_FAULTS,
    SESSION_IDENTITY_SETTINGS,
    SESSION_REQUIRED_FIELDS,
    SHARED_FAILURE_REASONS,
    TARGET_WINDOW_END,
    TARGET_WINDOW_START,
    AdbRuntimeDevice,
    RecordingDevicePolicy,
    RecordingRuntimeDevice,
    RuntimeAttemptError,
    RuntimeAttemptInputError,
    RuntimeAttemptReceipt,
    RuntimeAttemptRequest,
    RuntimeAttemptSetupPlan,
    RuntimeAttemptVerificationError,
    canonical_launch_vector,
    canonical_sha256,
    clear_log_buffers_vector,
    clear_package_data_vector,
    deployment_vector,
    execute_runtime_attempt,
    expected_device_mutation_order,
    expected_device_read_counts,
    failure_scope,
    launch_component,
    log_marker_vector,
    orientation_dispatch_vector,
    rotation_setting_vector,
    session_identity_drift,
    session_probe_vectors,
    verify_runtime_attempt,
)
from aiverify.runner.command import CommandResult, CommandRunner
from aiverify.runner.deterministic_backend import (
    DeterministicDriverPlan,
    load_deterministic_driver_plan,
)
from aiverify.runner.execution_record import load_execution_record
from aiverify.runner.run_spec import RunSpec, load_run_spec
from aiverify.runtime_preparation import (
    RuntimePreparationReceipt,
    _canonical_bytes,
    _identity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_ROOT = REPO_ROOT / "bench/runtime-calibration/opencalc-input-save-enabled-v1"
LANE_ROOT = CANDIDATE_ROOT / "runtime" / "lanes" / "lane-01"
LANE_ID = "ocrc-v1-lane-01"
RECORDING_SERIAL = "recording-device"
SEALED_APK_BYTES = b"sealed opencalc runtime apk bytes"

FROZEN_PHASES = (
    "prepare-inputs",
    "establish-execution-record",
    "device-session",
    "deploy-sealed-apk",
    "attempt-setup",
    "open-target-log-window",
    "canonical-launch",
    "journey",
    "boundary-precondition",
    "lifecycle-rotation",
    "collect-post-event-observation",
    "close-target-log-window",
    "close-post-cell-identity",
    "prove-lifecycle-transition",
    "evaluate-oracles",
    "finalize-receipt",
)

FROZEN_ARTIFACTS = {
    "journey_result": "artifacts/journey/deterministic-journey-result.json",
    "journey_events": "artifacts/journey/deterministic-observations.json",
    "journey_invocation": "artifacts/journey/deterministic-driver-invocation.json",
    "boundary_layout": "artifacts/boundary-layout.json",
    "post_event_layout": "artifacts/post-event-layout.json",
    "target_log_window": "artifacts/target-log-window.log",
    "lifecycle_window": "artifacts/lifecycle-window.log",
}

# The frozen lane-01 Driver Plan has six actions, so the attempt owes six Journey
# layout reads plus the boundary and post-event reads the runner owns, and one
# foreground read plus two settle polls.  The recording device binds its two
# layout faults to the frozen ordinals the runner owns, so the mirror is bound
# here and asserted in the frozen-table contract test at the end of this file.
JOURNEY_LAYOUT_READS = 8
FOREGROUND_READS = 3


def _lane_inputs() -> tuple[RunSpec, DeterministicDriverPlan]:
    spec = load_run_spec(LANE_ROOT / "run-spec.yaml")
    plan = load_deterministic_driver_plan(
        LANE_ROOT / "driver-plan.json",
        serialized_run_spec=(LANE_ROOT / "run-spec.yaml").read_bytes(),
        run_spec_path=LANE_ROOT / "run-spec.yaml",
        expected_actions=tuple(spec.scenario.user_actions),
    )
    return spec, plan


def _preparation_receipt(
    apk_path: Path, *, substitutes: bool = True
) -> RuntimePreparationReceipt:
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
            "test_substitutes": substitutes,
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


def _sealed_apk(root: Path, *, payload: bytes = SEALED_APK_BYTES) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    apk_path = root / "sealed-runtime.apk"
    if apk_path.exists():
        apk_path.chmod(0o644)
    apk_path.write_bytes(payload)
    apk_path.chmod(0o444)
    return apk_path


def _request(
    root: Path,
    *,
    policy: RecordingDevicePolicy | None = None,
    substitutes: bool = True,
    output_root: Path | None = None,
    device: object | None = None,
    lane_id: str = LANE_ID,
    session_fields: Mapping[str, object] | None = None,
) -> tuple[RuntimeAttemptRequest, object]:
    spec, plan = _lane_inputs()
    apk_path = _sealed_apk(root)
    bound_device = device or RecordingRuntimeDevice(
        policy=policy or RecordingDevicePolicy(),
        package=spec.package,
        activity=spec.activity,
        session_fields=session_fields,
    )
    request = RuntimeAttemptRequest(
        lane_id=lane_id,
        run_spec=spec,
        driver_plan=plan,
        setup_plan=RuntimeAttemptSetupPlan(
            family_id=plan.family_id,
            family_version=plan.family_version,
            package=spec.package,
        ),
        preparation_receipt=_preparation_receipt(apk_path, substitutes=substitutes),
        device=bound_device,
        output_root=output_root or root / "attempt",
        started_at="2026-09-28T00:00:00Z",
        clock=lambda: 1_000.0,
        sleeper=lambda _seconds: None,
    )
    return request, bound_device


class _RecordFirstProbe:
    """Recording-device proxy sampling the ExecutionRecord around each mutation."""

    def __init__(self, inner: object, root: Path) -> None:
        self._inner = inner
        self._root = root
        self.samples: list[tuple[str, str, object]] = []

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def _sample(self, operation: str) -> None:
        document = json.loads((self._root / "execution-record.json").read_text())
        self.samples.append(
            (operation, document["lifecycle_state"], document["finished_at"])
        )

    def deploy_apk(self, **kwargs: object) -> object:
        self._sample("deploy_apk")
        return self._inner.deploy_apk(**kwargs)

    def clear_package_data(self, package: str) -> object:
        self._sample("clear_package_data")
        return self._inner.clear_package_data(package)

    def write_rotation_setting(self, *, name: str, value: int) -> object:
        self._sample("write_rotation_setting")
        return self._inner.write_rotation_setting(name=name, value=value)

    def clear_log_buffers(self) -> object:
        self._sample("clear_log_buffers")
        return self._inner.clear_log_buffers()

    def write_log_marker(self, marker: str) -> object:
        self._sample("write_log_marker")
        return self._inner.write_log_marker(marker)

    def canonical_launch(self, *, package: str, activity: str) -> object:
        self._sample("canonical_launch")
        return self._inner.canonical_launch(package=package, activity=activity)

    def dispatch_orientation(self, rotation: int) -> object:
        self._sample("dispatch_orientation")
        return self._inner.dispatch_orientation(rotation)

    def tap(self, x: int, y: int) -> object:
        self._sample("tap")
        return self._inner.tap(x, y)


class _StubCommandRunner(CommandRunner):
    """Record every admitted vector and answer with empty successful output."""

    def __init__(self) -> None:
        self.commands: list[list[str]] = []

    def run(
        self,
        args: list[str],
        *,
        cwd: Path | None = None,
        timeout_seconds: int | None = None,
        input_text: str | None = None,
    ) -> CommandResult:
        self.commands.append(list(args))
        return CommandResult(args=list(args), stdout="", stderr="", returncode=0)


def _component(outcome: RuntimeAttemptReceipt, name: str) -> dict:
    value = outcome.components.get(name)
    assert isinstance(value, Mapping), name
    return dict(value)


def _record(output_root: Path) -> dict:
    return load_execution_record(output_root / "execution-record.json")


def _restamp_receipt(output_root: Path, mutate) -> None:
    """Re-sign one receipt and re-bind the record to its new bytes.

    The receipt and the ExecutionRecord bind each other: the record provenance
    carries the receipt file digest, and the receipt identity covers the whole
    receipt body.  A tamper that only rewrites receipt content is therefore
    caught by the record binding itself; re-signing both sides is what lets the
    verifier be pushed all the way into its recomputation paths.
    """
    path = output_root / runtime_attempt.RECEIPT_FILENAME
    document = json.loads(path.read_text())
    mutate(document)
    identity_body = dict(document)
    identity_body.pop("identity_sha256", None)
    document["identity_sha256"] = canonical_sha256(identity_body)
    path.write_text(_canonical_bytes(document).decode("utf-8"))

    record_path = output_root / runtime_attempt.RECORD_FILENAME
    record = json.loads(record_path.read_text())
    record["evidence_refs"]["execution_provenance"]["sha256"] = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()
    record_path.write_text(json.dumps(record, indent=2) + "\n")


def test_recording_lane_concludes_one_accountable_preserved_state(
    tmp_path: Path,
) -> None:
    request, device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == ACCOUNTABLE_CONCLUDED
    assert outcome.accountable_concluded is True
    assert outcome.reason is None
    assert outcome.relative_path == "attempt-receipt.json"
    assert set(outcome.components) == set(REQUIRED_ACCOUNTABLE_COMPONENTS)
    assert outcome.verdict == L1_OUTCOME_INCONCLUSIVE
    assert device.markers()[0].endswith(f":{TARGET_WINDOW_START}")

    document = outcome.document
    assert document["retries"] == 0
    assert document["seam"] == runtime_attempt.SEAM
    assert document["claim_boundary"] == runtime_attempt.CLAIM_BOUNDARY
    assert document["scenario"] == f"{LANE_ID}:opencalc-preserve-expression"
    assert document["evidence_class"] == "recorded_simulation"
    assert document["failure"] is None
    assert [entry["phase"] for entry in document["phases"]] == list(FROZEN_PHASES)
    assert {
        entry["kind"]: entry["path"] for entry in document["artifacts"]
    } == FROZEN_ARTIFACTS

    record = _record(request.output_root)
    assert record["schema_version"] == 2
    assert record["lifecycle_state"] == "completed"
    assert record["process_outcome"] == {"exit_code": 0}
    assert record["execution"] == {
        "status": "completed",
        "accounting_eligible": True,
        "reason": None,
        "message": None,
    }
    assert record["phase_errors"] == []
    assert record["attempt_id"] == document["attempt_id"]
    assert record["evidence_refs"]["attempt_receipt_path"] == "attempt-receipt.json"
    assert record["evidence_refs"]["execution_provenance"]["sha256"] == outcome.sha256
    assert record["evidence_refs"]["attempt_artifacts"] == list(FROZEN_ARTIFACTS.values())
    assert record["timing"]["started_at"] == "2026-09-28T00:00:00Z"

    oracles = _component(outcome, "oracles")
    assert oracles["l1"]["outcome"] == L1_OUTCOME_INCONCLUSIVE
    assert oracles["l1"]["attribution"] == "target_only"
    assert oracles["l1"]["attributed_event_count"] == 0
    assert oracles["l2"]["outcome"] == L2_OUTCOME_PASS
    assert oracles["l2"]["detail"] == "preserved_state"
    assert oracles["l2"]["input_text"] == BOUNDARY_PRECONDITION_TEXT
    assert oracles["l2"]["artifact_sha256"] == _component(
        outcome, "post_event_observation"
    )["artifact_sha256"]
    assert oracles["verdict"] == L1_OUTCOME_INCONCLUSIVE

    # The post-cell identity is a real second probe of the same cell: it binds
    # the pre-cell session fields as its reference and closes unchanged.
    identity_close = _component(outcome, "post_cell_identity")
    assert identity_close["operation"] == "probe_session"
    assert identity_close["closed"] is True
    assert identity_close["drifted_fields"] == []
    assert identity_close["reference_fields"] == _component(
        outcome, "device_session"
    )["fields"]
    assert identity_close["fields"] == identity_close["reference_fields"]
    assert device.operation_counts()["probe_session"] == 2

    verified = verify_runtime_attempt(request.output_root)
    assert verified["verified"] is True
    assert verified["attempt_id"] == document["attempt_id"]
    assert verified["terminal_state"] == ACCOUNTABLE_CONCLUDED
    assert verified["retries"] == 0
    assert verified["receipt_sha256"] == outcome.sha256
    assert "post-cell-identity" in verified["checks"]
    assert verified["recomputed"] == {
        "verdict": L1_OUTCOME_INCONCLUSIVE,
        "l1_outcome": L1_OUTCOME_INCONCLUSIVE,
        "l2_outcome": L2_OUTCOME_PASS,
        "window_sha256": _component(outcome, "target_log_window")["window_sha256"],
    }


def test_execution_record_predates_the_first_device_mutation(tmp_path: Path) -> None:
    request, inner = _request(tmp_path)
    probe = _RecordFirstProbe(inner, request.output_root)
    request = RuntimeAttemptRequest(
        lane_id=request.lane_id,
        run_spec=request.run_spec,
        driver_plan=request.driver_plan,
        setup_plan=request.setup_plan,
        preparation_receipt=request.preparation_receipt,
        device=probe,
        output_root=request.output_root,
        started_at=request.started_at,
        clock=request.clock,
        sleeper=request.sleeper,
    )

    outcome = execute_runtime_attempt(request)

    assert outcome.accountable_concluded is True
    assert [operation for operation, _state, _finished in probe.samples] == list(
        expected_device_mutation_order(tap_count=len(FROZEN_TAP_TRAJECTORY))
    )
    for operation, lifecycle_state, finished_at in probe.samples:
        assert lifecycle_state == "in_progress", operation
        assert finished_at is None, operation

    record = _record(request.output_root)
    assert record["lifecycle_state"] == "completed"
    assert record["finished_at"] == record["timing"]["finished_at"]
    assert sum(1 for _ in request.output_root.glob("execution-record.json")) == 1
    assert sum(1 for _ in request.output_root.glob("attempt-receipt.json")) == 1


def test_device_session_receipt_binds_the_selected_device(tmp_path: Path) -> None:
    request, _device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    session = _component(outcome, "device_session")
    assert session["device_kind"] == "recording"
    assert session["serial"] == RECORDING_SERIAL
    assert session["operation"] == "probe_session"
    probe_vectors = [list(vector) for vector in session_probe_vectors(RECORDING_SERIAL)]
    assert session["commands"] == probe_vectors
    assert session["returncodes"] == [0] * len(probe_vectors)

    fields = dict(session["fields"])
    for name in SESSION_REQUIRED_FIELDS:
        assert fields[name], name
    assert fields["package"] == request.run_spec.package
    assert fields["activity"] == request.run_spec.activity
    settings = dict(fields["settings"])
    for name in SESSION_IDENTITY_SETTINGS:
        assert name in settings, name


def test_sealed_apk_deployment_binds_installed_bytes_to_the_handoff(
    tmp_path: Path,
) -> None:
    request, _device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    sealed = _component(outcome, "sealed_apk")
    digest = hashlib.sha256(SEALED_APK_BYTES).hexdigest()
    assert sealed["sha256"] == digest
    assert sealed["installed_sha256"] == digest
    assert sealed["installed_bytes"] == len(SEALED_APK_BYTES)
    assert sealed["bytes"] == len(SEALED_APK_BYTES)
    assert sealed["deploy_operation"] == "deploy_apk"
    assert sealed["deploy_command"][:2] == ["android", "run"]
    assert f"--device={RECORDING_SERIAL}" in sealed["deploy_command"]
    assert sealed["deploy_stdout"].strip() == "Success"
    assert sealed["installed_paths"]

    identity = _component(outcome, "identity")
    assert identity["sealed_apk"]["sha256"] == digest
    assert identity["preparation"] == {
        "prepared": True,
        "receipt_sha256": request.preparation_receipt.receipt_sha256,
        "rejection_code": None,
        "test_substitutes": True,
    }
    assert identity["evidence_class"] == "recorded_simulation"
    assert identity["run_spec"]["canonical_sha256"] == json.loads(
        (LANE_ROOT / "driver-plan.json").read_text()
    )["run_spec_sha256"]
    assert identity["run_spec"]["sha256"] == hashlib.sha256(
        (LANE_ROOT / "run-spec.yaml").read_bytes()
    ).hexdigest()
    assert identity["driver_plan"]["sha256"] == hashlib.sha256(
        (LANE_ROOT / "driver-plan.json").read_bytes()
    ).hexdigest()


def test_attempt_setup_clears_package_data_and_forces_portrait_once(
    tmp_path: Path,
) -> None:
    request, _device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    setup = _component(outcome, "attempt_setup")
    assert setup["plan"] == {
        "id": ATTEMPT_SETUP_PLAN_ID,
        "operations": list(ATTEMPT_SETUP_OPERATIONS),
        "family_id": request.driver_plan.family_id,
        "family_version": request.driver_plan.family_version,
        "package": request.run_spec.package,
    }
    assert setup["package"] == request.run_spec.package
    assert setup["absence"]["pids"] == []
    assert setup["clear"]["returncode"] == 0
    assert setup["clear"]["stdout"].strip() == "Success"
    assert setup["settle_seconds"] > 0
    assert [write["name"] for write in setup["writes"]] == [
        "accelerometer_rotation",
        "user_rotation",
    ]
    assert [write["value"] for write in setup["writes"]] == [
        PORTRAIT_ROTATION,
        PORTRAIT_ROTATION,
    ]
    assert all(write["returncode"] == 0 for write in setup["writes"])
    assert setup["rotation"]["portrait"] is True
    assert setup["rotation"]["rotation"] == PORTRAIT_ROTATION
    assert setup["rotation"]["display_size"] == _component(
        outcome, "device_session"
    )["fields"]["display_size"]


def test_frozen_device_budget_is_spent_exactly_once_in_order(tmp_path: Path) -> None:
    request, device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    expected_counts = {
        **EXPECTED_DEVICE_MUTATION_COUNTS,
        "tap": len(FROZEN_TAP_TRAJECTORY),
        **EXPECTED_DEVICE_READ_COUNTS,
        "read_layout": JOURNEY_LAYOUT_READS,
        "read_foreground_state": FOREGROUND_READS,
    }
    assert dict(device.operation_counts()) == expected_counts
    assert [operation for operation, _vector in device.mutation_operations()] == list(
        expected_device_mutation_order(tap_count=len(FROZEN_TAP_TRAJECTORY))
    )
    assert device.mutation_commands()[0][:3] == (
        "android",
        "run",
        f"--device={RECORDING_SERIAL}",
    )
    assert dict(
        expected_device_read_counts(
            layout_reads=JOURNEY_LAYOUT_READS, foreground_reads=FOREGROUND_READS
        )
    ) == {
        "probe_session": 2,
        "read_installed_apk": 1,
        "target_process_ids": 1,
        "read_rotation_state": 1,
        "dump_all_buffers_epoch": 1,
        "read_layout": 8,
        "read_foreground_state": 3,
    }

    operations = _component(outcome, "device_operations")
    assert operations["counts"] == expected_counts
    assert operations["retries"] == 0
    assert operations["tap_count"] == len(FROZEN_TAP_TRAJECTORY)
    assert operations["poll_count"] == FOREGROUND_READS - 1
    assert operations["observed_mutation_order"] == list(
        expected_device_mutation_order(tap_count=len(FROZEN_TAP_TRAJECTORY))
    )
    assert operations["expected_mutation_counts"] == {
        **EXPECTED_DEVICE_MUTATION_COUNTS,
        "tap": len(FROZEN_TAP_TRAJECTORY),
    }


def test_adb_device_counts_admitted_operations_not_command_vectors() -> None:
    """The production device owes one count per admitted operation.

    The frozen budget is written in operation units, but a single operation
    fans out into many command vectors -- ``probe_session`` alone runs the
    whole identity probe plan.  A per-vector ledger would reject every real
    attempt, so the AdbRuntimeDevice must count each operation exactly once
    while still dispatching every admitted vector to the runner.
    """
    serial = "emulator-5554"
    package = "com.example.target"
    activity = "com.example.target.MainActivity"
    runner = _StubCommandRunner()
    device = AdbRuntimeDevice(
        serial, package=package, activity=activity, runner=runner
    )

    device.probe_session()
    device.read_installed_apk(package)
    device.read_rotation_state()
    device.read_foreground_state()
    device.read_layout()
    device.clear_package_data(package)
    device.write_rotation_setting(
        name="accelerometer_rotation", value=PORTRAIT_ROTATION
    )
    device.tap(540, 1200)

    assert dict(device.operation_counts()) == {
        "probe_session": 1,
        "read_installed_apk": 1,
        "read_rotation_state": 1,
        "read_foreground_state": 1,
        "read_layout": 1,
        "clear_package_data": 1,
        "write_rotation_setting": 1,
        "tap": 1,
    }
    assert [operation for operation, _vector in device.mutation_operations()] == [
        "clear_package_data",
        "write_rotation_setting",
        "tap",
    ]
    probe_vectors = len(session_probe_vectors(serial))
    assert probe_vectors > 1
    # One vector per session field, two installed-APK vectors, three
    # rotation-state vectors, three foreground vectors, one layout dump, and
    # one vector for each of the three mutations.
    assert len(runner.commands) == probe_vectors + 2 + 3 + 3 + 1 + 1 + 1 + 1
    assert runner.commands[-1] == list(device.mutation_commands()[-1])
    assert runner.commands[-1][-2:] == ["540", "1200"]


def test_driver_enters_the_boundary_precondition_through_the_frozen_trajectory(
    tmp_path: Path,
) -> None:
    request, _device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    journey = _component(outcome, "journey")
    assert journey["backend"] == "deterministic_android_v1"
    assert journey["action_count"] == 6
    assert journey["kinds"] == [
        "wait_for_resource_id",
        *(("tap_resource_id",) * len(FROZEN_TAP_TRAJECTORY)),
    ]
    assert journey["resource_ids"] == [
        FROZEN_TAP_TRAJECTORY[0],
        *FROZEN_TAP_TRAJECTORY,
    ]
    assert journey["statuses"] == ["PASSED"] * 6
    assert journey["tap_count"] == len(FROZEN_TAP_TRAJECTORY)
    assert journey["segment_id"] == runtime_attempt.JOURNEY_SEGMENT_ID
    assert journey["result_path"] == FROZEN_ARTIFACTS["journey_result"]
    assert journey["events_path"] == FROZEN_ARTIFACTS["journey_events"]
    assert journey["invocation_path"] == FROZEN_ARTIFACTS["journey_invocation"]

    boundary = _component(outcome, "boundary_precondition")
    assert boundary["input_text"] == BOUNDARY_PRECONDITION_TEXT
    assert boundary["input_node_count"] == 1
    assert boundary["artifact"] == FROZEN_ARTIFACTS["boundary_layout"]
    assert boundary["artifact_sha256"] == hashlib.sha256(
        (request.output_root / FROZEN_ARTIFACTS["boundary_layout"]).read_bytes()
    ).hexdigest()


def test_marker_bounded_window_starts_before_the_canonical_launch(
    tmp_path: Path,
) -> None:
    request, device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    order = [operation for operation, _vector in device.mutation_operations()]
    launch_index = order.index("canonical_launch")
    assert order.index("write_log_marker") < launch_index
    assert order.index("write_log_marker", launch_index) > order.index("tap")

    attempt_id = outcome.attempt_id
    markers = device.markers()
    assert markers == (
        f"aiverify-attempt:{LANE_ID}:{attempt_id}:{TARGET_WINDOW_START}",
        f"aiverify-attempt:{LANE_ID}:{attempt_id}:{LIFECYCLE_START}",
        f"aiverify-attempt:{LANE_ID}:{attempt_id}:{LIFECYCLE_END}",
        f"aiverify-attempt:{LANE_ID}:{attempt_id}:{TARGET_WINDOW_END}",
    )

    window = _component(outcome, "target_log_window")
    assert window["buffers"] == list(LOG_WINDOW_BUFFERS)
    assert window["format"] == LOG_WINDOW_FORMAT
    assert window["closed"] is True
    markers_by_kind = dict(window["markers"])
    assert set(markers_by_kind) == {
        TARGET_WINDOW_START,
        TARGET_WINDOW_END,
        LIFECYCLE_START,
        LIFECYCLE_END,
    }
    assert markers_by_kind[TARGET_WINDOW_START] == markers[0]
    assert markers_by_kind[TARGET_WINDOW_END] == markers[-1]
    assert markers_by_kind[LIFECYCLE_START] == markers[1]
    assert markers_by_kind[LIFECYCLE_END] == markers[2]
    assert window["start_line"] < window["end_line"]
    assert window["line_count"] > 0
    assert window["target_process_start_lines"]
    assert max(window["target_process_start_lines"]) <= window["line_count"]
    assert window["start_marker_command"][-1] == markers[0]
    assert window["end_marker_command"][-1] == markers[-1]
    assert window["capture_path"] == FROZEN_ARTIFACTS["target_log_window"]

    text = (request.output_root / FROZEN_ARTIFACTS["target_log_window"]).read_text()
    for marker in markers:
        assert f"{MARKER_TAG}: {marker}" in text
    slice_text = runtime_attempt._window_slice(
        text, window["start_line"], window["end_line"]
    )
    assert (
        hashlib.sha256(slice_text.encode("utf-8")).hexdigest()
        == window["window_sha256"]
    )

    launch = _component(outcome, "canonical_launch")
    assert launch["status_token"] == "Status: ok"
    assert launch["reported_component"] == launch_component(
        request.run_spec.package, request.run_spec.activity
    )
    assert launch["foreground"]["component"] == launch_component(
        request.run_spec.package, request.run_spec.activity
    )
    assert launch["foreground"]["pid"]
    assert launch["settle_seconds"] > 0


def test_landscape_event_and_lifecycle_transition_are_frozen(tmp_path: Path) -> None:
    request, _device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    lifecycle = _component(outcome, "lifecycle_transition")
    assert lifecycle["rotation"] == LANDSCAPE_ROTATION
    assert lifecycle["landscape"] is True
    assert lifecycle["dispatch_command"][-1] == str(LANDSCAPE_ROTATION)
    process = dict(lifecycle["process"])
    assert process["package"] == request.run_spec.package
    assert process["restart_evidence"] == []
    assert lifecycle["pid"] == lifecycle["after"]["pid"]
    assert lifecycle["task_id"] == lifecycle["after"]["task_id"]
    assert lifecycle["poll_budget"] == LIFECYCLE_POLL_BUDGET
    assert lifecycle["poll_interval_seconds"] == LIFECYCLE_POLL_INTERVAL_SECONDS
    assert 0 < lifecycle["poll_count"] <= LIFECYCLE_POLL_BUDGET
    assert len(lifecycle["observations"]) == lifecycle["poll_count"]
    assert lifecycle["observations"][-1]["poll"] == lifecycle["poll_count"]

    assert lifecycle["before"]["landscape"] is False
    assert lifecycle["after"]["landscape"] is True
    assert lifecycle["before"]["rotation"] == PORTRAIT_ROTATION
    assert lifecycle["after"]["rotation"] == LANDSCAPE_ROTATION
    assert lifecycle["before"]["component"] == lifecycle["after"]["component"]
    assert lifecycle["before"]["display_size"] != lifecycle["after"]["display_size"]

    assert lifecycle["signature_id"] == LIFECYCLE_SIGNATURE_ID
    assert lifecycle["signature_status"] == LIFECYCLE_SIGNATURE_STATUS
    assert tuple(lifecycle["signature_events"]) == LIFECYCLE_SIGNATURE_EVENTS
    signature = dict(lifecycle["signature"])
    assert signature["id"] == LIFECYCLE_SIGNATURE_ID
    assert signature["status"] == LIFECYCLE_SIGNATURE_STATUS
    assert tuple(signature["order"]) == LIFECYCLE_SIGNATURE_EVENTS
    assert signature["relaunch"]
    for name in LIFECYCLE_SIGNATURE_EVENTS:
        assert signature["events"][name][0]["line"] > 0
        assert signature["events"][name][0]["excerpt"]

    slice_text = (request.output_root / FROZEN_ARTIFACTS["lifecycle_window"]).read_text()
    assert hashlib.sha256(slice_text.encode("utf-8")).hexdigest() == lifecycle["slice_sha256"]
    assert lifecycle["slice_lines"][0] < lifecycle["slice_lines"][1]


def test_the_single_capture_serves_the_l1_window_and_the_lifecycle_slice(
    tmp_path: Path,
) -> None:
    request, device = _request(tmp_path)

    outcome = execute_runtime_attempt(request)

    window = _component(outcome, "target_log_window")
    lifecycle = _component(outcome, "lifecycle_transition")
    capture_text = (
        request.output_root / FROZEN_ARTIFACTS["target_log_window"]
    ).read_text()
    window_markers = dict(window["markers"])

    # One attempt-bound capture answers both evidence families: the L1 window and
    # the lifecycle slice are two windows of the same single dump, so no second
    # capture, no re-read, and no per-oracle instrument may exist.
    assert device.operation_counts()["dump_all_buffers_epoch"] == 1
    assert window["capture_path"] == FROZEN_ARTIFACTS["target_log_window"]
    assert _component(outcome, "oracles")["window_sha256"] == window["window_sha256"]
    assert (
        hashlib.sha256(
            runtime_attempt._window_slice(
                capture_text, window["start_line"], window["end_line"]
            ).encode("utf-8")
        ).hexdigest()
        == window["window_sha256"]
    )

    # Every marker is attempt-bound and unique in the one capture, and the pair
    # that bounds the L1 window is the same literal pair the lifecycle proof
    # reads: both evaluations share one instrument instead of owning one each.
    for kind in (LIFECYCLE_START, LIFECYCLE_END):
        assert window_markers[kind] == lifecycle["markers"][kind]
    for kind, marker in window_markers.items():
        assert capture_text.count(f"{MARKER_TAG}: {marker}") == 1, kind
    assert runtime_attempt._marker_indexes(
        capture_text, window_markers[TARGET_WINDOW_START]
    ) == [window["start_line"]]
    assert runtime_attempt._marker_indexes(
        capture_text, window_markers[TARGET_WINDOW_END]
    ) == [window["end_line"]]
    assert lifecycle["slice_lines"] == [
        runtime_attempt._marker_indexes(
            capture_text, window_markers[LIFECYCLE_START]
        )[0],
        runtime_attempt._marker_indexes(
            capture_text, window_markers[LIFECYCLE_END]
        )[0],
    ]
    assert window["start_line"] < lifecycle["slice_lines"][0]
    assert lifecycle["slice_lines"][1] < window["end_line"]

    # The lifecycle artifact is exactly the slice of that one capture.
    lifecycle_text = (
        request.output_root / FROZEN_ARTIFACTS["lifecycle_window"]
    ).read_text()
    assert lifecycle_text == runtime_attempt._window_slice(
        capture_text, *lifecycle["slice_lines"]
    )
    assert hashlib.sha256(lifecycle_text.encode("utf-8")).hexdigest() == lifecycle[
        "slice_sha256"
    ]


def test_the_unsettled_poll_retains_every_probe_without_compensating(
    tmp_path: Path,
) -> None:
    request, device = _request(
        tmp_path,
        policy=RecordingDevicePolicy(lifecycle_fault="landscape_not_resumed"),
    )

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason == "orientation_not_observed"
    assert outcome.document["failure"]["phase"] == "lifecycle-rotation"
    assert "oracles" not in outcome.components

    # The rejected poll is never shortened, replayed, or compensated: every
    # admitted probe was taken exactly once and all of them stay recorded.
    lifecycle = _component(outcome, "lifecycle_transition")
    assert lifecycle["poll_budget"] == LIFECYCLE_POLL_BUDGET
    assert lifecycle["poll_count"] == LIFECYCLE_POLL_BUDGET
    assert [entry["poll"] for entry in lifecycle["observations"]] == list(
        range(1, LIFECYCLE_POLL_BUDGET + 1)
    )
    assert all(
        entry["fields"]["landscape"] is False for entry in lifecycle["observations"]
    )
    assert lifecycle["after"]["landscape"] is False
    assert lifecycle["dispatch_command"] == list(
        orientation_dispatch_vector(device.serial, LANDSCAPE_ROTATION)
    )
    counts = device.operation_counts()
    assert counts["read_foreground_state"] == 1 + LIFECYCLE_POLL_BUDGET
    assert counts["dispatch_orientation"] == 1
    assert counts["probe_session"] == 2
    assert tuple(
        operation for operation, _vector in device.mutation_operations()
    ) == _COMPLETE_PREFIX
    _assert_admitted_mutation_vectors(device, request)

    # The abort owes the window close and the post-cell identity close, but it
    # never re-observes the product: no second layout read is claimed.
    assert "post_event_observation" not in outcome.components
    window = _component(outcome, "target_log_window")
    assert window["closed"] is True
    assert window["partial"] is True
    identity = _component(outcome, "post_cell_identity")
    assert identity["closed"] is True
    assert identity["drifted_fields"] == []
    assert verify_runtime_attempt(request.output_root)["verified"] is True


def test_state_loss_lane_concludes_accountable_with_a_failing_oracle(
    tmp_path: Path,
) -> None:
    request, _device = _request(
        tmp_path, policy=RecordingDevicePolicy(save_enabled=False)
    )

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == ACCOUNTABLE_CONCLUDED
    assert outcome.reason is None
    assert outcome.verdict == L1_OUTCOME_FAIL
    oracles = _component(outcome, "oracles")
    assert oracles["l1"]["outcome"] == L1_OUTCOME_INCONCLUSIVE
    assert oracles["l2"]["outcome"] == L2_OUTCOME_FAIL
    assert oracles["l2"]["detail"] == "state_loss"
    assert oracles["l2"]["defect_class"] == "state_loss"
    assert oracles["l2"]["input_text"] == ""

    record = _record(request.output_root)
    assert record["process_outcome"] == {"exit_code": 1}
    assert record["execution"]["status"] == "completed"
    assert record["phase_errors"] == []
    assert verify_runtime_attempt(request.output_root)["verified"] is True


def test_injected_target_crash_is_attributed_to_the_target_package(
    tmp_path: Path,
) -> None:
    request, _device = _request(
        tmp_path, policy=RecordingDevicePolicy(inject_target_crash=True)
    )

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == ACCOUNTABLE_CONCLUDED
    assert outcome.verdict == L1_OUTCOME_FAIL
    oracles = _component(outcome, "oracles")
    assert oracles["l1"]["outcome"] == L1_OUTCOME_FAIL
    assert oracles["l1"]["attribution"] == "target_only"
    assert oracles["l1"]["attributed_event_count"] >= 1
    assert oracles["l1"]["attributed_events"][0]["type"] == "crash"
    assert oracles["l1"]["attributed_events"][0]["stacktrace_lines"] >= 1
    assert oracles["l2"]["outcome"] == L2_OUTCOME_PASS
    assert oracles["l2"]["defect_class"] is None

    record = _record(request.output_root)
    assert record["process_outcome"] == {"exit_code": 1}
    assert verify_runtime_attempt(request.output_root)["verified"] is True


@pytest.mark.parametrize(
    "policy",
    [
        RecordingDevicePolicy(fail_operations=frozenset({"tap"})),
        RecordingDevicePolicy(fail_operations=frozenset({"canonical_launch"})),
        RecordingDevicePolicy(fail_operations=frozenset({"write_log_marker"})),
        RecordingDevicePolicy(fail_operations=frozenset({"dump_all_buffers_epoch"})),
        RecordingDevicePolicy(restart_target_process=True),
    ],
)
def test_device_failures_conclude_non_accountable_with_one_canonical_reason(
    tmp_path: Path, policy: RecordingDevicePolicy
) -> None:
    request, device = _request(tmp_path, policy=policy)

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason in SHARED_FAILURE_REASONS
    assert outcome.verdict == L1_OUTCOME_INCONCLUSIVE
    assert outcome.accountable_concluded is False
    assert "oracles" not in outcome.components

    failure = outcome.document["failure"]
    assert failure["reason"] == outcome.reason
    assert failure["phase"] in {entry["phase"] for entry in outcome.document["phases"]}
    assert failure["kind"] in {"device", "evidence", "harness"}
    assert failure["message"]
    assert failure["scope"] == failure_scope(outcome.reason)
    assert failure["scope"] in {
        FAILURE_SCOPE_LANE_LOCAL,
        FAILURE_SCOPE_SHARED,
        FAILURE_SCOPE_UNKNOWN,
    }

    # The abort never repeats, reorders, or compensates an operation: every
    # non-marker mutation is exactly the frozen prefix the attempt reached, and
    # the window markers are only the frozen ones plus at most the one terminal
    # end marker that closes an already open window.
    operations = [operation for operation, _vector in device.mutation_operations()]
    frozen = expected_device_mutation_order(tap_count=len(FROZEN_TAP_TRAJECTORY))
    observed = [
        operation for operation in operations if operation != "write_log_marker"
    ]
    assert observed == [
        operation for operation in frozen if operation != "write_log_marker"
    ][: len(observed)]
    assert operations.count("write_log_marker") <= frozen.count("write_log_marker")
    assert (
        sum(
            1
            for marker in device.markers()
            if marker.endswith(f":{TARGET_WINDOW_END}")
        )
        <= 1
    )
    _assert_admitted_mutation_vectors(device, request)

    record = _record(request.output_root)
    assert record["lifecycle_state"] == "failed"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["execution"]["status"] == "non_accountable"
    assert record["execution"]["accounting_eligible"] is False
    assert record["execution"]["reason"] == outcome.reason
    assert record["phase_errors"]
    assert record["phase_errors"][-1]["reason"] == outcome.reason
    assert record["evidence_refs"]["execution_provenance"]["terminal_state"] == (
        NON_ACCOUNTABLE
    )
    assert record["evidence_refs"]["execution_provenance"]["sha256"] == outcome.sha256

    verified = verify_runtime_attempt(request.output_root)
    assert verified["verified"] is True
    assert verified["terminal_state"] == NON_ACCOUNTABLE
    assert verified["reason"] == outcome.reason
    assert verified["recomputed"] is None


def test_pre_side_effect_rejections_leave_the_recording_device_untouched(
    tmp_path: Path,
) -> None:
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "leftover.txt").write_text("earlier work")
    request, device = _request(tmp_path, output_root=occupied)

    with pytest.raises(RuntimeAttemptInputError) as occupied_error:
        execute_runtime_attempt(request)

    assert occupied_error.value.code == "attempt_output_root_not_empty"
    assert dict(device.operation_counts()) == {}
    assert not (occupied / "execution-record.json").exists()

    lane_request, lane_device = _request(tmp_path, lane_id="ocrc-v1-lane-09")
    with pytest.raises(RuntimeAttemptInputError) as lane_error:
        execute_runtime_attempt(lane_request)
    assert lane_error.value.code == "attempt_lane_identity_mismatch"
    assert dict(lane_device.operation_counts()) == {}

    mismatch_request, mismatch_device = _request(tmp_path, substitutes=False)
    with pytest.raises(RuntimeAttemptInputError) as class_error:
        execute_runtime_attempt(mismatch_request)
    assert class_error.value.code == "attempt_evidence_class_mismatch"
    assert dict(mismatch_device.operation_counts()) == {}


def test_sealed_apk_drift_is_rejected_before_any_device_side_effect(
    tmp_path: Path,
) -> None:
    request, device = _request(tmp_path)
    drifted = tmp_path / "sealed-runtime.apk"
    drifted.chmod(0o644)
    drifted.write_bytes(SEALED_APK_BYTES + b"!")

    with pytest.raises(RuntimeAttemptInputError) as error:
        execute_runtime_attempt(request)

    assert error.value.code == "sealed_apk_bytes_drifted"
    assert dict(device.operation_counts()) == {}


def test_an_attempt_never_reuses_a_concluded_output_root(tmp_path: Path) -> None:
    request, _device = _request(tmp_path)
    first = execute_runtime_attempt(request)
    assert first.accountable_concluded is True

    with pytest.raises(RuntimeAttemptInputError) as error:
        execute_runtime_attempt(request)

    assert error.value.code == "attempt_output_root_not_empty"
    assert sum(1 for _ in request.output_root.glob("attempt-receipt.json")) == 1
    assert _record(request.output_root)["attempt_id"] == first.attempt_id


def test_verification_rejects_a_tampered_verdict_and_a_missing_artifact(
    tmp_path: Path,
) -> None:
    verdict_request, _device = _request(tmp_path / "verdict")
    verdict_outcome = execute_runtime_attempt(verdict_request)
    _restamp_receipt(
        verdict_outcome.output_root,
        lambda document: document.update({"verdict": L1_OUTCOME_FAIL}),
    )

    with pytest.raises(RuntimeAttemptVerificationError) as verdict_error:
        verify_runtime_attempt(verdict_request.output_root)

    assert verdict_error.value.code == "attempt_oracle_invalid"

    artifact_request, _device = _request(tmp_path / "artifact")
    execute_runtime_attempt(artifact_request)
    (artifact_request.output_root / FROZEN_ARTIFACTS["boundary_layout"]).unlink()

    with pytest.raises(RuntimeAttemptVerificationError) as artifact_error:
        verify_runtime_attempt(artifact_request.output_root)

    assert artifact_error.value.code == "attempt_artifact_missing"


def test_verification_recomputes_the_frozen_device_budget_and_log_window(
    tmp_path: Path,
) -> None:
    budget_request, _device = _request(tmp_path / "budget")
    budget_outcome = execute_runtime_attempt(budget_request)
    _restamp_receipt(
        budget_outcome.output_root,
        lambda document: document["components"]["device_operations"]["counts"].update(
            {"tap": len(FROZEN_TAP_TRAJECTORY) + 1}
        ),
    )

    with pytest.raises(RuntimeAttemptVerificationError) as budget_error:
        verify_runtime_attempt(budget_request.output_root)

    assert budget_error.value.code in {
        "attempt_device_budget_violated",
        "attempt_device_budget_invalid",
    }

    log_request, _device = _request(tmp_path / "log")
    log_outcome = execute_runtime_attempt(log_request)
    window_path = log_request.output_root / FROZEN_ARTIFACTS["target_log_window"]
    window_path.write_text(window_path.read_text() + "tampered\n")

    def drift_window(document: dict) -> None:
        digest = hashlib.sha256(window_path.read_bytes()).hexdigest()
        entries = iter(document["artifacts"])
        index = next(
            position
            for position, entry in enumerate(entries)
            if entry["path"] == FROZEN_ARTIFACTS["target_log_window"]
        )
        document["components"]["target_log_window"]["window_sha256"] = digest
        document["artifacts"][index]["sha256"] = digest
        document["artifacts"][index]["bytes"] = window_path.stat().st_size

    _restamp_receipt(log_outcome.output_root, drift_window)

    with pytest.raises(RuntimeAttemptVerificationError) as log_error:
        verify_runtime_attempt(log_request.output_root)

    assert log_error.value.code in {
        "attempt_log_window_digest_mismatch",
        "attempt_log_window_marker_error",
        "attempt_log_attribution_ambiguous",
        "attempt_oracle_invalid",
    }


def test_verification_rejects_a_duplicated_or_unknown_artifact_kind(
    tmp_path: Path,
) -> None:
    duplicate_request, _device = _request(tmp_path / "duplicate")
    duplicate_outcome = execute_runtime_attempt(duplicate_request)

    def duplicate_kind(document: dict) -> None:
        entries = document["artifacts"]
        boundary = next(
            entry for entry in entries if entry["kind"] == "boundary_layout"
        )
        entries.append(dict(boundary))

    _restamp_receipt(duplicate_outcome.output_root, duplicate_kind)

    with pytest.raises(RuntimeAttemptVerificationError) as duplicate_error:
        verify_runtime_attempt(duplicate_request.output_root)

    assert duplicate_error.value.code == "attempt_artifact_inventory_invalid"

    unknown_request, _device = _request(tmp_path / "unknown")
    unknown_outcome = execute_runtime_attempt(unknown_request)

    def unknown_kind(document: dict) -> None:
        entries = document["artifacts"]
        window = next(
            entry for entry in entries if entry["kind"] == "target_log_window"
        )
        shadow = dict(window)
        shadow["kind"] = "shadow_window"
        entries.append(shadow)

    _restamp_receipt(unknown_outcome.output_root, unknown_kind)

    with pytest.raises(RuntimeAttemptVerificationError) as unknown_error:
        verify_runtime_attempt(unknown_request.output_root)

    assert unknown_error.value.code == "attempt_artifact_inventory_invalid"


def test_verification_rejects_a_relabelled_evidence_class(tmp_path: Path) -> None:
    request, _device = _request(tmp_path)
    outcome = execute_runtime_attempt(request)
    _restamp_receipt(
        outcome.output_root,
        lambda document: document.update({"evidence_class": "device"}),
    )

    with pytest.raises(RuntimeAttemptVerificationError) as error:
        verify_runtime_attempt(request.output_root)

    assert error.value.code == "attempt_evidence_class_mismatch"


def test_verification_rejects_a_tampered_post_cell_identity(tmp_path: Path) -> None:
    def accountable(root: Path) -> RuntimeAttemptRequest:
        request, _device = _request(root)
        outcome = execute_runtime_attempt(request)
        assert outcome.terminal_state == ACCOUNTABLE_CONCLUDED
        return request

    def reject(request: RuntimeAttemptRequest, mutate) -> None:
        _restamp_receipt(request.output_root, mutate)
        with pytest.raises(RuntimeAttemptVerificationError) as error:
            verify_runtime_attempt(request.output_root)
        assert error.value.code == "attempt_post_cell_identity_mismatch"

    # The verifier recomputes the close from its two recorded probes instead of
    # trusting the recorded shape: an unclosed identity, a restated reference, a
    # claimed drift, and a real drift are each refused.
    unclosed = accountable(tmp_path / "unclosed")
    reject(
        unclosed,
        lambda document: document["components"]["post_cell_identity"].update(
            {"closed": False}
        ),
    )
    restated = accountable(tmp_path / "restated")
    reject(
        restated,
        lambda document: document["components"]["post_cell_identity"][
            "reference_fields"
        ].update({"boot_id": "another-boot"}),
    )
    claimed = accountable(tmp_path / "claimed")
    reject(
        claimed,
        lambda document: document["components"]["post_cell_identity"].update(
            {"drifted_fields": ["serial"]}
        ),
    )
    drifted = accountable(tmp_path / "drifted")

    def inject_drift(document: dict) -> None:
        post_cell = document["components"]["post_cell_identity"]
        post_cell["fields"]["boot_id"] = "another-boot"
        post_cell["drifted_fields"] = session_identity_drift(
            post_cell["reference_fields"], post_cell["fields"]
        )

    reject(drifted, inject_drift)

    # An accountable receipt without the close is incomplete, not verified.
    missing = accountable(tmp_path / "missing")
    _restamp_receipt(
        missing.output_root,
        lambda document: document["components"].pop("post_cell_identity"),
    )
    with pytest.raises(RuntimeAttemptVerificationError) as missing_error:
        verify_runtime_attempt(missing.output_root)
    assert missing_error.value.code == "attempt_component_invalid"


def test_public_lane_seam_is_exported_and_mirrored_by_the_compatibility_module() -> None:
    assert "execute_runtime_attempt" in runtime_attempt.__all__
    assert "verify_runtime_attempt" in runtime_attempt.__all__
    assert compat_runtime_attempt.execute_runtime_attempt is execute_runtime_attempt
    assert compat_runtime_attempt.verify_runtime_attempt is verify_runtime_attempt
    assert compat_runtime_attempt.RuntimeAttemptRequest is RuntimeAttemptRequest


def test_attempt_setup_plan_rejects_a_drifted_frozen_operation_set() -> None:
    spec, plan = _lane_inputs()

    with pytest.raises(RuntimeAttemptInputError) as error:
        RuntimeAttemptSetupPlan(
            family_id=plan.family_id,
            family_version=plan.family_version,
            package=spec.package,
            operations=("clear_package_data",),
        )

    assert error.value.code == "attempt_setup_plan_operations_invalid"
    assert ATTEMPT_SETUP_OPERATIONS == ("clear_package_data", "force_portrait")


# ---------------------------------------------------------------------------
# Pre-observation fail-closed matrix
# ---------------------------------------------------------------------------

# The frozen pre-launch mutation prefixes, written as literal operation names so
# a drift in the production table cannot hide behind a re-derived expectation.
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


def _admitted_vectors(
    request: RuntimeAttemptRequest,
) -> dict[str, set[tuple[str, ...]]]:
    """Return the exact vector set each admitted mutation may dispatch once."""
    sealed = json.loads(request.preparation_receipt.receipt_bytes)["sealed_apk"]
    package = request.run_spec.package
    activity = request.run_spec.activity
    return {
        "deploy_apk": {
            deployment_vector(
                RECORDING_SERIAL,
                apk_path=Path(sealed["path"]),
                package=package,
                activity=activity,
            )
        },
        "clear_package_data": {clear_package_data_vector(RECORDING_SERIAL, package)},
        "write_rotation_setting": {
            rotation_setting_vector(RECORDING_SERIAL, name, PORTRAIT_ROTATION)
            for name in ALLOWED_ROTATION_SETTINGS
        },
        "clear_log_buffers": {clear_log_buffers_vector(RECORDING_SERIAL)},
        "canonical_launch": {
            canonical_launch_vector(RECORDING_SERIAL, package, activity)
        },
        "dispatch_orientation": {
            orientation_dispatch_vector(RECORDING_SERIAL, LANDSCAPE_ROTATION)
        },
    }


def _assert_admitted_mutation_vectors(
    device: object, request: RuntimeAttemptRequest
) -> None:
    """Assert every dispatched mutation is admitted, unique, and frozen-shaped.

    A dispatched vector may appear at most once -- a repeated vector is exactly
    the retry or compensation the attempt contract forbids -- and every vector
    must be the one the frozen table derives for its operation.
    """
    admitted = _admitted_vectors(request)
    seen: set[tuple[str, ...]] = set()
    for operation, vector in device.mutation_operations():
        assert vector not in seen, f"{operation} dispatched one vector twice"
        seen.add(vector)
        if operation == "write_log_marker":
            assert vector == log_marker_vector(RECORDING_SERIAL, vector[-1])
            assert vector[-1].startswith(f"aiverify-attempt:{LANE_ID}:")
            continue
        if operation == "tap":
            assert vector[:6] == (
                "adb",
                "-s",
                RECORDING_SERIAL,
                "shell",
                "input",
                "tap",
            )
            assert vector[6:] and all(part.isdigit() for part in vector[6:])
            continue
        assert operation in admitted, operation
        assert vector in admitted[operation], (operation, vector)


def _session_fields_without(spec: RunSpec, *drop: str) -> dict[str, object]:
    """Return the recorded session identity with named fields or settings gone."""
    fields = dict(
        runtime_attempt._session_fields(
            serial=RECORDING_SERIAL, package=spec.package, activity=spec.activity
        )
    )
    for name in drop:
        if name in SESSION_IDENTITY_SETTINGS:
            settings = dict(fields["settings"])
            settings.pop(name)
            fields["settings"] = settings
            continue
        fields.pop(name)
    return fields


class _SealedApkDriftDevice:
    """Recording-device proxy that rewrites the sealed APK after admission."""

    def __init__(self, inner: object, *, apk_path: Path, payload: bytes) -> None:
        self._inner = inner
        self._apk_path = apk_path
        self._payload = payload
        self.drifted = False

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def probe_session(self) -> object:
        receipt = self._inner.probe_session()
        self._apk_path.chmod(0o644)
        self._apk_path.write_bytes(self._payload)
        self._apk_path.chmod(0o444)
        self.drifted = True
        return receipt


class _RetryTapDevice:
    """Recording-device proxy that dispatches one extra unadmitted tap."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.taps = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def tap(self, x: int, y: int) -> object:
        self.taps += 1
        if self.taps == 1:
            self._inner.tap(5, 5)
        return self._inner.tap(x, y)


class _CountingSessionDevice:
    """Recording-device proxy that tallies every session probe dispatched."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.probes = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def probe_session(self) -> object:
        self.probes += 1
        return self._inner.probe_session()


class _OccupiedReceiptDevice:
    """Recording-device proxy that occupies the receipt path after the last dump."""

    def __init__(self, inner: object, *, receipt_path: Path) -> None:
        self._inner = inner
        self._receipt_path = receipt_path

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def dump_all_buffers_epoch(self) -> object:
        receipt = self._inner.dump_all_buffers_epoch()
        self._receipt_path.mkdir()
        return receipt


@dataclass(frozen=True)
class _PreObservationFailure:
    """One material pre-observation failure and its frozen fail-closed shape."""

    label: str
    reason: str
    scope: str
    phase: str
    dispatched: tuple[str, ...]
    policy: RecordingDevicePolicy = field(default_factory=RecordingDevicePolicy)
    session_drop: tuple[str, ...] = ()
    drift_sealed_apk: bool = False


# Every material failure between admission and the canonical post-event
# observation, with the exact phase, canonical reason, failure scope, and
# dispatched-mutation prefix the attempt owes.  The prefix is literal: any extra
# device mutation on the abort path fails the case.
PRE_OBSERVATION_FAILURES = (
    _PreObservationFailure(
        label="session-probe-refused",
        reason="device_session_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="device-session",
        dispatched=(),
        policy=RecordingDevicePolicy(fail_operations=frozenset({"probe_session"})),
    ),
    _PreObservationFailure(
        label="session-serial-drift",
        reason="device_session_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="device-session",
        dispatched=(),
        policy=RecordingDevicePolicy(reported_serial="emulator-9999"),
    ),
    _PreObservationFailure(
        label="session-required-field-missing",
        reason="device_session_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="device-session",
        dispatched=(),
        session_drop=("boot_id",),
    ),
    _PreObservationFailure(
        label="session-settings-missing",
        reason="device_session_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="device-session",
        dispatched=(),
        session_drop=("default_input_method",),
    ),
    _PreObservationFailure(
        label="sealed-apk-drifted-after-admission",
        reason="sealed_apk_bytes_drifted",
        scope=FAILURE_SCOPE_SHARED,
        phase="deploy-sealed-apk",
        dispatched=(),
        drift_sealed_apk=True,
    ),
    _PreObservationFailure(
        label="deployment-refused",
        reason="sealed_apk_deployment_failed",
        scope=FAILURE_SCOPE_SHARED,
        phase="deploy-sealed-apk",
        dispatched=(),
        policy=RecordingDevicePolicy(fail_operations=frozenset({"deploy_apk"})),
    ),
    _PreObservationFailure(
        label="installed-read-refused",
        reason="sealed_apk_deployment_failed",
        scope=FAILURE_SCOPE_SHARED,
        phase="deploy-sealed-apk",
        dispatched=("deploy_apk",),
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"read_installed_apk"})
        ),
    ),
    _PreObservationFailure(
        label="installed-bytes-drifted",
        reason="sealed_apk_bytes_drifted",
        scope=FAILURE_SCOPE_SHARED,
        phase="deploy-sealed-apk",
        dispatched=("deploy_apk",),
        policy=RecordingDevicePolicy(installed_digest_override="f" * 64),
    ),
    _PreObservationFailure(
        label="package-clear-refused",
        reason="attempt_setup_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="attempt-setup",
        dispatched=("deploy_apk",),
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"clear_package_data"})
        ),
    ),
    _PreObservationFailure(
        label="package-clear-contradicted",
        reason="attempt_setup_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="attempt-setup",
        dispatched=("deploy_apk", "clear_package_data"),
        policy=RecordingDevicePolicy(clear_output="Failure"),
    ),
    _PreObservationFailure(
        label="target-process-residual",
        reason="attempt_setup_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="attempt-setup",
        dispatched=("deploy_apk", "clear_package_data"),
        policy=RecordingDevicePolicy(residual_target_process=True),
    ),
    _PreObservationFailure(
        label="setting-write-refused",
        reason="attempt_setup_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="attempt-setup",
        dispatched=("deploy_apk", "clear_package_data"),
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"write_rotation_setting"})
        ),
    ),
    _PreObservationFailure(
        label="rotation-read-refused",
        reason="attempt_setup_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="attempt-setup",
        dispatched=_SETUP_WRITES,
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"read_rotation_state"})
        ),
    ),
    _PreObservationFailure(
        label="portrait-contradicted",
        reason="attempt_setup_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="attempt-setup",
        dispatched=_SETUP_WRITES,
        policy=RecordingDevicePolicy(reported_rotation=LANDSCAPE_ROTATION),
    ),
    _PreObservationFailure(
        label="log-clear-refused",
        reason="target_log_window_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="open-target-log-window",
        dispatched=_SETUP_WRITES,
        policy=RecordingDevicePolicy(fail_operations=frozenset({"clear_log_buffers"})),
    ),
    _PreObservationFailure(
        label="start-marker-refused",
        reason="target_log_window_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="open-target-log-window",
        dispatched=(*_SETUP_WRITES, "clear_log_buffers"),
        policy=RecordingDevicePolicy(fail_operations=frozenset({"write_log_marker"})),
    ),
    _PreObservationFailure(
        label="canonical-launch-refused",
        reason="canonical_launch_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="canonical-launch",
        dispatched=(*_SETUP_WRITES, "clear_log_buffers", "write_log_marker"),
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"canonical_launch"})
        ),
    ),
    _PreObservationFailure(
        label="foreground-read-refused",
        reason="canonical_launch_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="canonical-launch",
        dispatched=_LAUNCH_PREFIX,
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"read_foreground_state"})
        ),
    ),
    _PreObservationFailure(
        label="foreground-component-contradicted",
        reason="canonical_launch_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="canonical-launch",
        dispatched=_LAUNCH_PREFIX,
        policy=RecordingDevicePolicy(reported_foreground_component="com.other/.Main"),
    ),
)


@pytest.mark.parametrize(
    "case",
    PRE_OBSERVATION_FAILURES,
    ids=[case.label for case in PRE_OBSERVATION_FAILURES],
)
def test_pre_observation_failures_fail_closed_at_the_canonical_phase(
    tmp_path: Path, case: _PreObservationFailure
) -> None:
    spec, _plan = _lane_inputs()
    inner = RecordingRuntimeDevice(
        policy=case.policy,
        package=spec.package,
        activity=spec.activity,
        session_fields=(
            _session_fields_without(spec, *case.session_drop)
            if case.session_drop
            else None
        ),
    )
    device: object = inner
    if case.drift_sealed_apk:
        device = _SealedApkDriftDevice(
            inner,
            apk_path=tmp_path / "sealed-runtime.apk",
            payload=SEALED_APK_BYTES + b"!",
        )
    request, _bound = _request(tmp_path, device=device)

    outcome = execute_runtime_attempt(request)

    # One canonical reason, one derived scope, and no authoritative oracle.
    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.accountable_concluded is False
    assert outcome.reason == case.reason
    assert outcome.verdict == L1_OUTCOME_INCONCLUSIVE
    assert "oracles" not in outcome.components

    failure = outcome.document["failure"]
    assert failure["phase"] == case.phase
    assert failure["reason"] == case.reason
    assert failure["scope"] == case.scope
    assert failure["kind"] in {"device", "evidence", "harness"}
    assert failure["message"]
    assert failure_scope(case.reason) == case.scope

    # The terminal failure is the last phase the attempt entered: no later
    # phase runs, every earlier phase ran once, and none of them is repeated.
    phases = outcome.document["phases"]
    assert [entry["phase"] for entry in phases] == list(
        FROZEN_PHASES[: FROZEN_PHASES.index(case.phase) + 1]
    )
    assert phases[-1]["status"] == "failed"
    assert all(entry["status"] == "ok" for entry in phases[:-1])

    # Only the admitted prefix of the frozen mutation table was dispatched, and
    # an open window is closed by exactly one terminal end marker.
    operations = [operation for operation, _vector in device.mutation_operations()]
    expected_dispatched = case.dispatched
    if "write_log_marker" in case.dispatched:
        expected_dispatched = (*case.dispatched, "write_log_marker")
    assert tuple(operations) == expected_dispatched
    assert "tap" not in operations
    assert "dispatch_orientation" not in operations
    _assert_admitted_mutation_vectors(device, request)

    markers = device.markers()
    counts = device.operation_counts()
    if "write_log_marker" in case.dispatched:
        # The window opened, so the terminal finalization owes exactly one end
        # marker and exactly one capture of the partial window it really has.
        window = _component(outcome, "target_log_window")
        assert window["closed"] is True
        assert window["partial"] is True
        assert window["end_marker_dispatched"] is True
        assert window["start_line"] < window["end_line"] <= window["line_count"]
        assert counts["write_log_marker"] == (
            case.dispatched.count("write_log_marker") + 1
        )
        assert counts["dump_all_buffers_epoch"] == 1
        assert [
            marker for marker in markers if marker.endswith(f":{TARGET_WINDOW_END}")
        ] == [markers[-1]]
        window_path = request.output_root / FROZEN_ARTIFACTS["target_log_window"]
        assert window_path.is_file()
        assert hashlib.sha256(window_path.read_bytes()).hexdigest() == (
            window["capture_sha256"]
        )
    else:
        # No window was opened, so no marker, dump, artifact, or component may
        # exist: a failure before the start marker must not fabricate a window.
        assert "target_log_window" not in outcome.components
        assert markers == ()
        assert "write_log_marker" not in counts
        assert "dump_all_buffers_epoch" not in counts
        assert not (
            request.output_root / FROZEN_ARTIFACTS["target_log_window"]
        ).exists()

    # The already established record is finalized exactly once.
    record = _record(request.output_root)
    assert record["lifecycle_state"] == "failed"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["execution"]["status"] == "non_accountable"
    assert record["execution"]["accounting_eligible"] is False
    assert record["execution"]["reason"] == case.reason
    assert len(record["phase_errors"]) == 1
    assert record["phase_errors"][0]["phase"] == case.phase
    assert record["phase_errors"][0]["reason"] == case.reason
    assert record["phase_errors"][0]["scope"] == case.scope
    assert record["evidence_refs"]["attempt_receipt_path"] == (
        runtime_attempt.RECEIPT_FILENAME
    )
    assert sum(1 for _ in request.output_root.glob("execution-record.json")) == 1
    assert sum(1 for _ in request.output_root.glob("attempt-receipt.json")) == 1

    verified = verify_runtime_attempt(request.output_root)
    assert verified["verified"] is True
    assert verified["terminal_state"] == NON_ACCOUNTABLE
    assert verified["reason"] == case.reason
    assert verified["recomputed"] is None
    assert {"phase-ledger", "failure-scope", "no-authoritative-oracle"} <= set(
        verified["checks"]
    )


def test_terminal_finalization_closes_the_marker_window_exactly_once(
    tmp_path: Path,
) -> None:
    request, device = _request(
        tmp_path,
        policy=RecordingDevicePolicy(fail_operations=frozenset({"canonical_launch"})),
    )

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason == "canonical_launch_failed"
    assert outcome.document["failure"]["phase"] == "canonical-launch"
    assert outcome.document["failure"]["kind"] == "device"

    markers = device.markers()
    assert len(markers) == 2
    assert markers[0].endswith(f":{TARGET_WINDOW_START}")
    assert markers[1].endswith(f":{TARGET_WINDOW_END}")
    assert device.operation_counts()["write_log_marker"] == 2
    assert device.operation_counts()["dump_all_buffers_epoch"] == 1

    window = _component(outcome, "target_log_window")
    assert window["closed"] is True
    assert window["partial"] is True
    assert window["end_marker_dispatched"] is True
    assert window["capture"] == "partial"
    assert window["capture_path"] == FROZEN_ARTIFACTS["target_log_window"]

    text = (request.output_root / FROZEN_ARTIFACTS["target_log_window"]).read_text()
    slice_text = runtime_attempt._window_slice(
        text, window["start_line"], window["end_line"]
    )
    assert (
        hashlib.sha256(slice_text.encode("utf-8")).hexdigest()
        == window["window_sha256"]
    )
    # The partial window holds only the marker pair: nothing that belongs to
    # the launch, the Journey, or the lifecycle may be claimed as captured.
    assert text.count(MARKER_TAG) == 2
    assert f":{LIFECYCLE_START}" not in text
    assert f":{LIFECYCLE_END}" not in text

    record = _record(request.output_root)
    assert record["evidence_refs"]["attempt_artifacts"] == [
        FROZEN_ARTIFACTS["target_log_window"]
    ]
    assert verify_runtime_attempt(request.output_root)["verified"] is True


def test_a_failed_window_capture_never_dispatches_a_second_end_marker(
    tmp_path: Path,
) -> None:
    request, device = _request(
        tmp_path,
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"dump_all_buffers_epoch"})
        ),
    )

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason == "target_log_window_capture_failed"

    window = _component(outcome, "target_log_window")
    assert window["closed"] is False
    assert window["end_marker_dispatched"] is False
    assert window["capture"] == "unavailable_after_abort"
    assert window["capture_error"]

    markers = device.markers()
    assert len(markers) == EXPECTED_DEVICE_MUTATION_COUNTS["write_log_marker"]
    assert [
        marker for marker in markers if marker.endswith(f":{TARGET_WINDOW_END}")
    ] == [markers[-1]]
    assert device.operation_counts()["write_log_marker"] == (
        EXPECTED_DEVICE_MUTATION_COUNTS["write_log_marker"]
    )
    assert "dump_all_buffers_epoch" not in device.operation_counts()
    # The aborted capture is not silently replaced by an empty artifact.
    assert FROZEN_ARTIFACTS["target_log_window"] not in _record(
        request.output_root
    )["evidence_refs"]["attempt_artifacts"]
    assert not (
        request.output_root / FROZEN_ARTIFACTS["target_log_window"]
    ).exists()
    assert verify_runtime_attempt(request.output_root)["verified"] is True


def test_a_refused_session_identity_is_never_re_probed_on_the_abort_path(
    tmp_path: Path,
) -> None:
    spec, _plan = _lane_inputs()
    inner = RecordingRuntimeDevice(
        policy=RecordingDevicePolicy(fail_operations=frozenset({"probe_session"})),
        package=spec.package,
        activity=spec.activity,
    )
    device = _CountingSessionDevice(inner)
    request, _bound = _request(tmp_path, device=device)

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason == "device_session_unavailable"
    assert outcome.document["failure"]["phase"] == "device-session"
    # The one refused probe stays the whole session history of the attempt: the
    # abort never re-probes a session it never established, and never records a
    # close it cannot support, so a refusal cannot become a retry.
    assert "device_session" not in outcome.components
    assert "post_cell_identity" not in outcome.components
    assert device.probes == 1
    assert "probe_session" not in inner.operation_counts()

    record = _record(request.output_root)
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["execution"]["reason"] == "device_session_unavailable"
    assert outcome.document["retries"] == 0
    assert sum(1 for _ in request.output_root.glob("attempt-receipt.json")) == 1
    assert sum(1 for _ in request.output_root.glob("execution-record.json")) == 1
    assert verify_runtime_attempt(request.output_root)["verified"] is True


def test_a_receipt_write_failure_finalizes_the_record_exactly_once(
    tmp_path: Path,
) -> None:
    spec, _plan = _lane_inputs()
    output_root = tmp_path / "attempt"
    inner = RecordingRuntimeDevice(package=spec.package, activity=spec.activity)
    device = _OccupiedReceiptDevice(
        inner, receipt_path=output_root / runtime_attempt.RECEIPT_FILENAME
    )
    request, _bound = _request(tmp_path, device=device, output_root=output_root)

    with pytest.raises(RuntimeAttemptError) as error:
        execute_runtime_attempt(request)

    assert error.value.code == "attempt_receipt_already_exists"

    record = _record(output_root)
    assert record["lifecycle_state"] == "failed"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["execution"]["status"] == "non_accountable"
    assert record["execution"]["accounting_eligible"] is False
    assert record["execution"]["reason"] == "attempt_receipt_write_failed"
    assert len(record["phase_errors"]) == 1
    failure = record["phase_errors"][0]
    assert failure["phase"] == "finalize-receipt"
    assert failure["kind"] == "evidence"
    assert failure["reason"] == "attempt_receipt_write_failed"
    assert failure["scope"] == FAILURE_SCOPE_SHARED
    # A handled path never abandons the record: it is finalized once, with no
    # receipt provenance it cannot have.
    assert "attempt_receipt_path" not in record["evidence_refs"]
    assert "execution_provenance" not in record["evidence_refs"]
    assert record["evidence_refs"]["attempt_artifacts"] == list(
        FROZEN_ARTIFACTS.values()
    )
    phases = record["timing"]["phases"]
    assert [entry["phase"] for entry in phases] == list(FROZEN_PHASES)
    assert phases[-1]["phase"] == "finalize-receipt"
    assert phases[-1]["status"] == "failed"
    assert all(entry["status"] == "ok" for entry in phases[:-1])
    assert sum(1 for _ in output_root.glob("execution-record.json")) == 1
    assert not (output_root / runtime_attempt.RECEIPT_FILENAME).is_file()

    with pytest.raises(RuntimeAttemptVerificationError) as verify_error:
        verify_runtime_attempt(output_root)

    assert verify_error.value.code == "attempt_receipt_unreadable"


def test_a_post_oracle_failure_seals_a_receipt_without_an_authoritative_oracle(
    tmp_path: Path,
) -> None:
    spec, _plan = _lane_inputs()
    inner = RecordingRuntimeDevice(package=spec.package, activity=spec.activity)
    device = _RetryTapDevice(inner)
    request, _bound = _request(tmp_path, device=device)

    outcome = execute_runtime_attempt(request)

    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason == "device_operation_budget_violated"
    assert outcome.document["failure"]["phase"] == "finalize-receipt"
    assert outcome.document["failure"]["scope"] == FAILURE_SCOPE_SHARED
    assert "oracles" not in outcome.components
    assert "device_operations" not in outcome.components

    # The raw pre-verdict evidence survives; only the authoritative oracle is
    # dropped, and the exactly-once violation stays visible in real counts.
    observation = _component(outcome, "post_event_observation")
    assert observation["l2_outcome"] == L2_OUTCOME_PASS
    assert device.taps == len(FROZEN_TAP_TRAJECTORY)
    assert inner.operation_counts()["tap"] == len(FROZEN_TAP_TRAJECTORY) + 1

    phases = outcome.document["phases"]
    assert [entry["phase"] for entry in phases] == list(FROZEN_PHASES)
    assert phases[-1]["phase"] == "finalize-receipt"
    assert phases[-1]["status"] == "failed"
    assert all(entry["status"] == "ok" for entry in phases[:-1])

    record = _record(request.output_root)
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["execution"]["reason"] == "device_operation_budget_violated"
    assert len(record["phase_errors"]) == 1
    assert record["phase_errors"][0]["phase"] == "finalize-receipt"
    assert verify_runtime_attempt(request.output_root)["verified"] is True


def _non_accountable_receipt(tmp_path: Path) -> tuple[RuntimeAttemptRequest, dict]:
    """Execute one non-accountable attempt whose window never opened."""
    request, _device = _request(
        tmp_path,
        policy=RecordingDevicePolicy(fail_operations=frozenset({"clear_log_buffers"})),
    )
    outcome = execute_runtime_attempt(request)
    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.reason == "target_log_window_unavailable"
    return request, outcome.document


def test_verification_rejects_a_drifted_failure_scope_and_ledger(
    tmp_path: Path,
) -> None:
    scope_request, scope_document = _non_accountable_receipt(tmp_path / "scope")
    assert scope_document["failure"]["scope"] == FAILURE_SCOPE_SHARED

    def drift_scope(document: dict) -> None:
        document["failure"]["scope"] = "attempt"

    _restamp_receipt(scope_request.output_root, drift_scope)
    with pytest.raises(RuntimeAttemptVerificationError) as scope_error:
        verify_runtime_attempt(scope_request.output_root)
    assert scope_error.value.code == "attempt_failure_scope_invalid"

    phase_request, _ = _non_accountable_receipt(tmp_path / "phase")

    def drift_phase(document: dict) -> None:
        document["failure"]["phase"] = "device-session"

    _restamp_receipt(phase_request.output_root, drift_phase)
    with pytest.raises(RuntimeAttemptVerificationError) as phase_error:
        verify_runtime_attempt(phase_request.output_root)
    assert phase_error.value.code == "attempt_failure_invalid"

    ledger_request, _ = _non_accountable_receipt(tmp_path / "ledger")

    def duplicate_phase(document: dict) -> None:
        document["phases"].append(dict(document["phases"][-1]))

    _restamp_receipt(ledger_request.output_root, duplicate_phase)
    with pytest.raises(RuntimeAttemptVerificationError) as ledger_error:
        verify_runtime_attempt(ledger_request.output_root)
    assert ledger_error.value.code == "attempt_phase_ledger_invalid"


def test_verification_rejects_an_authoritative_oracle_on_a_non_accountable_receipt(
    tmp_path: Path,
) -> None:
    request, document = _non_accountable_receipt(tmp_path)

    def claim_oracle(document: dict) -> None:
        document["components"]["oracles"] = {
            "l1": {"outcome": L1_OUTCOME_INCONCLUSIVE},
            "l2": {"outcome": L2_OUTCOME_PASS},
            "verdict": L1_OUTCOME_INCONCLUSIVE,
        }

    _restamp_receipt(request.output_root, claim_oracle)
    with pytest.raises(RuntimeAttemptVerificationError) as error:
        verify_runtime_attempt(request.output_root)

    assert error.value.code == "attempt_non_accountable_oracle_invalid"
    assert "oracles" not in document["components"]


# ---------------------------------------------------------------------------
# Post-observation fail-closed matrix
# ---------------------------------------------------------------------------

# The frozen post-launch mutation prefixes, written as literal operation names.
# The Journey dispatches one tap per frozen trajectory entry after the launch
# prefix, and the boundary read closes the Journey.
_TAP_PREFIX = (*_LAUNCH_PREFIX, *("tap",) * len(FROZEN_TAP_TRAJECTORY))
# A boundary rejection aborts before the rotation and closes the already open
# window with its one terminal end marker.
_BOUNDARY_PREFIX = (*_TAP_PREFIX, "write_log_marker")
# A refused rotation dispatch writes its lifecycle start marker first, and the
# abort path then closes the window.
_ROTATION_PREFIX = (*_BOUNDARY_PREFIX, "write_log_marker")
# The complete frozen order: two lifecycle markers around the one rotation, and
# the one terminal end marker that closes the target log window.  The closing
# phase and the abort path dispatch the same order, so one literal prefix binds
# both and a second dispatch anywhere would break it.
_COMPLETE_PREFIX = (
    *_TAP_PREFIX,
    "write_log_marker",
    "dispatch_orientation",
    "write_log_marker",
    "write_log_marker",
)


@dataclass(frozen=True)
class _PostObservationFailure:
    """One material post-observation failure and its frozen fail-closed shape.

    ``window`` names the target log window state the abort owes: ``phase`` when
    the closing phase delivered it, ``abort`` when the terminal finalization had
    to close an open window, ``refused`` when the dump itself was refused, and
    ``unproven`` when the capture ran but never proved a usable window.
    ``identity`` names the post-cell close the abort owes: ``closed``,
    ``drifted`` for a recorded drift, or ``refused`` for a refused re-probe.
    """

    label: str
    reason: str
    scope: str
    phase: str
    dispatched: tuple[str, ...]
    window: str
    identity: str = "closed"
    drifted: tuple[str, ...] = ()
    policy: RecordingDevicePolicy = field(default_factory=RecordingDevicePolicy)


# Every material failure from the boundary precondition to the sealed receipt,
# with the exact phase, canonical reason, failure scope, dispatched-mutation
# prefix, and closure state the attempt owes.  The prefixes are literal: any
# extra dispatch, retry, reverse rotation, or compensation fails the case.
POST_OBSERVATION_FAILURES = (
    # -- the boundary precondition rejects before the rotation ---------------
    _PostObservationFailure(
        label="boundary-input-missing",
        reason="boundary_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="boundary-precondition",
        dispatched=_BOUNDARY_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(boundary_layout_fault="missing_input"),
    ),
    _PostObservationFailure(
        label="boundary-input-duplicated",
        reason="boundary_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="boundary-precondition",
        dispatched=_BOUNDARY_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(boundary_layout_fault="duplicate_input"),
    ),
    _PostObservationFailure(
        label="boundary-input-geometry-invalid",
        reason="boundary_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="boundary-precondition",
        dispatched=_BOUNDARY_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(boundary_layout_fault="invalid_geometry"),
    ),
    _PostObservationFailure(
        label="boundary-text-drifted",
        reason="boundary_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="boundary-precondition",
        dispatched=_BOUNDARY_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(boundary_layout_fault="wrong_text"),
    ),
    _PostObservationFailure(
        label="boundary-text-omitted",
        reason="boundary_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="boundary-precondition",
        dispatched=_BOUNDARY_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(boundary_layout_fault="omitted_text"),
    ),
    _PostObservationFailure(
        label="boundary-layout-malformed",
        reason="boundary_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="boundary-precondition",
        dispatched=_BOUNDARY_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(boundary_layout_fault="malformed"),
    ),
    # -- the one rotation is dispatched once, never retried or reversed ------
    _PostObservationFailure(
        label="rotation-dispatch-refused",
        reason="orientation_dispatch_failed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="lifecycle-rotation",
        dispatched=_ROTATION_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"dispatch_orientation"})
        ),
    ),
    _PostObservationFailure(
        label="rotation-not-observed",
        reason="orientation_not_observed",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="lifecycle-rotation",
        dispatched=_COMPLETE_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(lifecycle_fault="landscape_not_resumed"),
    ),
    # -- the post-event observation ----------------------------------------
    _PostObservationFailure(
        label="post-event-layout-malformed",
        reason="post_event_layout_unreadable",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="collect-post-event-observation",
        dispatched=_COMPLETE_PREFIX,
        window="abort",
        policy=RecordingDevicePolicy(post_event_layout_fault="malformed"),
    ),
    # -- the one target log window: refusal, marker, and window integrity ----
    _PostObservationFailure(
        label="log-dump-refused",
        reason="target_log_window_capture_failed",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="refused",
        policy=RecordingDevicePolicy(
            fail_operations=frozenset({"dump_all_buffers_epoch"})
        ),
    ),
    _PostObservationFailure(
        label="log-dump-empty",
        reason="target_log_window_marker_error",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="unproven",
        policy=RecordingDevicePolicy(log_dump_fault="empty_dump"),
    ),
    _PostObservationFailure(
        label="log-end-marker-missing",
        reason="target_log_window_marker_error",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="unproven",
        policy=RecordingDevicePolicy(log_dump_fault="missing_end_marker"),
    ),
    _PostObservationFailure(
        label="log-markers-reversed",
        reason="target_log_window_marker_error",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="unproven",
        policy=RecordingDevicePolicy(log_dump_fault="reversed_markers"),
    ),
    _PostObservationFailure(
        label="log-markers-duplicated",
        reason="target_log_window_marker_error",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="unproven",
        policy=RecordingDevicePolicy(log_dump_fault="duplicated_markers"),
    ),
    _PostObservationFailure(
        label="log-window-truncated",
        reason="target_log_window_marker_error",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="unproven",
        policy=RecordingDevicePolicy(log_dump_fault="truncated_dump"),
    ),
    _PostObservationFailure(
        label="log-window-incomplete",
        reason="target_log_window_capture_failed",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-target-log-window",
        dispatched=_COMPLETE_PREFIX,
        window="unproven",
        policy=RecordingDevicePolicy(log_dump_fault="incomplete_window"),
    ),
    _PostObservationFailure(
        label="log-lifecycle-marker-missing",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(log_dump_fault="missing_lifecycle_marker"),
    ),
    _PostObservationFailure(
        label="log-lifecycle-marker-duplicated",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(
            log_dump_fault="duplicated_lifecycle_marker"
        ),
    ),
    # -- the frozen destruction, creation, and resume signature -------------
    _PostObservationFailure(
        label="lifecycle-events-reordered",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(lifecycle_fault="reordered_events"),
    ),
    _PostObservationFailure(
        label="lifecycle-event-duplicated",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(lifecycle_fault="duplicated_event"),
    ),
    _PostObservationFailure(
        label="lifecycle-event-missing",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(lifecycle_fault="missing_event"),
    ),
    _PostObservationFailure(
        label="lifecycle-relaunch-missing",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(lifecycle_fault="relaunch_missing"),
    ),
    _PostObservationFailure(
        label="lifecycle-task-changed",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(lifecycle_fault="task_changed"),
    ),
    _PostObservationFailure(
        label="lifecycle-pid-changed",
        reason="lifecycle_transition_unproven",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(lifecycle_fault="pid_changed"),
    ),
    _PostObservationFailure(
        label="lifecycle-target-restarted",
        reason="target_process_restarted",
        scope=FAILURE_SCOPE_LANE_LOCAL,
        phase="prove-lifecycle-transition",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(restart_target_process=True),
    ),
    # -- the ambiguous attribution and the closed post-cell identity ---------
    _PostObservationFailure(
        label="log-foreign-crash-unattributable",
        reason="log_attribution_ambiguous",
        scope=FAILURE_SCOPE_UNKNOWN,
        phase="evaluate-oracles",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        policy=RecordingDevicePolicy(log_dump_fault="foreign_crash"),
    ),
    _PostObservationFailure(
        label="post-cell-probe-refused",
        reason="device_session_unavailable",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-post-cell-identity",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        identity="refused",
        policy=RecordingDevicePolicy(session_drift_fault="refused"),
    ),
    _PostObservationFailure(
        label="post-cell-serial-drifted",
        reason="device_session_identity_drifted",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-post-cell-identity",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        identity="drifted",
        drifted=("serial",),
        policy=RecordingDevicePolicy(session_drift_fault="serial_changed"),
    ),
    _PostObservationFailure(
        label="post-cell-field-missing",
        reason="device_session_identity_drifted",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-post-cell-identity",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        identity="drifted",
        drifted=("boot_id",),
        policy=RecordingDevicePolicy(session_drift_fault="fields_missing"),
    ),
    _PostObservationFailure(
        label="post-cell-setting-missing",
        reason="device_session_identity_drifted",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-post-cell-identity",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        identity="drifted",
        drifted=("settings.font_scale",),
        policy=RecordingDevicePolicy(session_drift_fault="settings_missing"),
    ),
    _PostObservationFailure(
        label="post-cell-setting-drifted",
        reason="device_session_identity_drifted",
        scope=FAILURE_SCOPE_SHARED,
        phase="close-post-cell-identity",
        dispatched=_COMPLETE_PREFIX,
        window="phase",
        identity="drifted",
        drifted=("settings.font_scale",),
        policy=RecordingDevicePolicy(session_drift_fault="identity_drifted"),
    ),
)


def _assert_aborted_window(
    case: _PostObservationFailure,
    outcome: RuntimeAttemptReceipt,
    request: RuntimeAttemptRequest,
) -> None:
    """Assert the one target log window state the aborted attempt owes."""
    window = _component(outcome, "target_log_window")
    capture_path = request.output_root / FROZEN_ARTIFACTS["target_log_window"]
    if case.window == "phase":
        assert window["closed"] is True
        assert "partial" not in window
        assert window["capture_path"] == FROZEN_ARTIFACTS["target_log_window"]
        assert window["line_count"] > 0
    elif case.window == "abort":
        assert window["closed"] is True
        assert window["partial"] is True
        assert window["capture"] == "partial"
        assert window["capture_path"] == FROZEN_ARTIFACTS["target_log_window"]
    elif case.window == "refused":
        assert window["closed"] is False
        assert window["capture"] == "unavailable_after_abort"
        assert window["capture_error"]
        assert not capture_path.exists()
    else:
        assert window["closed"] is False
        assert "partial" not in window
        assert "capture_path" not in window
        assert not capture_path.exists()
    if case.window in {"phase", "abort"}:
        assert capture_path.is_file()
        assert hashlib.sha256(capture_path.read_bytes()).hexdigest() == (
            window["capture_sha256"]
        )


def _assert_closed_identity(
    case: _PostObservationFailure,
    outcome: RuntimeAttemptReceipt,
    device: object,
) -> None:
    """Assert the post-cell identity close the aborted attempt still owes."""
    counts = device.operation_counts()
    identity = _component(outcome, "post_cell_identity")
    # The close is attempted exactly once: the pre-cell probe plus its one
    # post-cell re-probe are the whole session budget of this attempt.
    assert counts["probe_session"] == 2
    if case.identity == "refused":
        assert identity["closed"] is False
        assert "fields" not in identity
        return
    assert identity["closed"] is True
    assert identity["reference_fields"] == _component(outcome, "device_session")[
        "fields"
    ]
    assert tuple(identity["drifted_fields"]) == case.drifted
    if case.drifted:
        assert identity["fields"] != identity["reference_fields"]
    else:
        assert identity["fields"] == identity["reference_fields"]


@pytest.mark.parametrize(
    "case",
    POST_OBSERVATION_FAILURES,
    ids=[case.label for case in POST_OBSERVATION_FAILURES],
)
def test_post_observation_failures_fail_closed_at_the_canonical_phase(
    tmp_path: Path, case: _PostObservationFailure
) -> None:
    spec, _plan = _lane_inputs()
    device = RecordingRuntimeDevice(
        policy=case.policy, package=spec.package, activity=spec.activity
    )
    request, _bound = _request(tmp_path, device=device)

    outcome = execute_runtime_attempt(request)

    # One canonical reason, one derived scope, and no authoritative oracle: a
    # capture, parse, identity, or lifecycle-proof failure never becomes an
    # L1/L2 result.
    assert outcome.terminal_state == NON_ACCOUNTABLE
    assert outcome.accountable_concluded is False
    assert outcome.reason == case.reason
    assert outcome.verdict == L1_OUTCOME_INCONCLUSIVE
    assert "oracles" not in outcome.components

    failure = outcome.document["failure"]
    assert failure["phase"] == case.phase
    assert failure["reason"] == case.reason
    assert failure["scope"] == case.scope
    assert failure["kind"] in {"device", "evidence", "harness"}
    assert failure["message"]
    assert failure_scope(case.reason) == case.scope

    # The terminal failure is the last phase the attempt entered, so no later
    # phase runs, no earlier phase repeats, and the attempt is never replaced.
    phases = outcome.document["phases"]
    assert [entry["phase"] for entry in phases] == list(
        FROZEN_PHASES[: FROZEN_PHASES.index(case.phase) + 1]
    )
    assert phases[-1]["status"] == "failed"
    assert all(entry["status"] == "ok" for entry in phases[:-1])

    # Only the admitted prefix of the frozen mutation table was dispatched: the
    # one rotation is dispatched at most once, and a boundary rejection never
    # rotates at all.
    operations = [operation for operation, _vector in device.mutation_operations()]
    counts = device.operation_counts()
    assert tuple(operations) == case.dispatched
    _assert_admitted_mutation_vectors(device, request)
    if case.phase == "boundary-precondition":
        assert "dispatch_orientation" not in counts
    assert counts.get("dispatch_orientation", 0) <= 1
    assert counts["write_log_marker"] <= EXPECTED_DEVICE_MUTATION_COUNTS[
        "write_log_marker"
    ]

    _assert_aborted_window(case, outcome, request)
    _assert_closed_identity(case, outcome, device)

    # The terminal artifacts are sealed exactly once, with the failure recorded
    # where it happened and no second attempt behind it.
    record = _record(request.output_root)
    assert record["lifecycle_state"] == "failed"
    assert record["process_outcome"] == {"exit_code": 2}
    assert record["execution"]["status"] == "non_accountable"
    assert record["execution"]["accounting_eligible"] is False
    assert record["execution"]["reason"] == case.reason
    assert len(record["phase_errors"]) == 1
    assert record["phase_errors"][0]["phase"] == case.phase
    assert record["phase_errors"][0]["reason"] == case.reason
    assert record["phase_errors"][0]["scope"] == case.scope
    assert record["evidence_refs"]["execution_provenance"]["terminal_state"] == (
        NON_ACCOUNTABLE
    )
    assert record["evidence_refs"]["execution_provenance"]["sha256"] == outcome.sha256
    assert outcome.document["retries"] == 0
    assert sum(1 for _ in request.output_root.glob("execution-record.json")) == 1
    assert sum(1 for _ in request.output_root.glob("attempt-receipt.json")) == 1

    verified = verify_runtime_attempt(request.output_root)
    assert verified["verified"] is True
    assert verified["terminal_state"] == NON_ACCOUNTABLE
    assert verified["reason"] == case.reason
    assert verified["recomputed"] is None


@dataclass(frozen=True)
class _PostEventObservation:
    """One bounded post-event observation and the frozen accountable outcome.

    Every row is accountable: the attempt still proves its exactly-once evidence
    and seals one receipt, and still yields exactly one bounded L2 result.  A
    drifted or emptied cell is a real ``state_loss`` fail, while a structurally
    ambiguous surface stays accountable and inconclusive -- it is never repaired,
    re-observed, or turned into an L1/L2 result it cannot support.
    """

    label: str
    l2_outcome: str
    l2_detail: str
    verdict: str
    exit_code: int
    policy: RecordingDevicePolicy = field(default_factory=RecordingDevicePolicy)


POST_EVENT_OBSERVATIONS = (
    _PostEventObservation(
        label="post-event-text-exact",
        l2_outcome=L2_OUTCOME_PASS,
        l2_detail="preserved_state",
        verdict=L1_OUTCOME_INCONCLUSIVE,
        exit_code=0,
    ),
    _PostEventObservation(
        label="post-event-text-drifted",
        l2_outcome=L2_OUTCOME_FAIL,
        l2_detail="state_loss",
        verdict=L1_OUTCOME_FAIL,
        exit_code=1,
        policy=RecordingDevicePolicy(post_event_layout_fault="wrong_text"),
    ),
    _PostEventObservation(
        label="post-event-text-omitted",
        l2_outcome=L2_OUTCOME_FAIL,
        l2_detail="state_loss",
        verdict=L1_OUTCOME_FAIL,
        exit_code=1,
        policy=RecordingDevicePolicy(post_event_layout_fault="omitted_text"),
    ),
    _PostEventObservation(
        label="post-event-save-disabled",
        l2_outcome=L2_OUTCOME_FAIL,
        l2_detail="state_loss",
        verdict=L1_OUTCOME_FAIL,
        exit_code=1,
        policy=RecordingDevicePolicy(save_enabled=False),
    ),
    _PostEventObservation(
        label="post-event-input-missing",
        l2_outcome=L2_OUTCOME_INCONCLUSIVE,
        l2_detail="post_event_input_missing",
        verdict=L1_OUTCOME_INCONCLUSIVE,
        exit_code=0,
        policy=RecordingDevicePolicy(post_event_layout_fault="missing_input"),
    ),
    _PostEventObservation(
        label="post-event-input-duplicated",
        l2_outcome=L2_OUTCOME_INCONCLUSIVE,
        l2_detail="post_event_input_duplicated",
        verdict=L1_OUTCOME_INCONCLUSIVE,
        exit_code=0,
        policy=RecordingDevicePolicy(post_event_layout_fault="duplicate_input"),
    ),
    _PostEventObservation(
        label="post-event-input-unusable",
        l2_outcome=L2_OUTCOME_INCONCLUSIVE,
        l2_detail="post_event_input_unusable",
        verdict=L1_OUTCOME_INCONCLUSIVE,
        exit_code=0,
        policy=RecordingDevicePolicy(post_event_layout_fault="invalid_geometry"),
    ),
)


@pytest.mark.parametrize(
    "case",
    POST_EVENT_OBSERVATIONS,
    ids=[case.label for case in POST_EVENT_OBSERVATIONS],
)
def test_post_event_observation_yields_the_frozen_l2_result(
    tmp_path: Path, case: _PostEventObservation
) -> None:
    spec, _plan = _lane_inputs()
    device = RecordingRuntimeDevice(
        policy=case.policy, package=spec.package, activity=spec.activity
    )
    request, _bound = _request(tmp_path, device=device)

    outcome = execute_runtime_attempt(request)

    # The bounded observation never un-concludes the attempt: the evidence is
    # proven exactly once, and the receipt is still sealed with one verdict.
    assert outcome.terminal_state == ACCOUNTABLE_CONCLUDED
    assert outcome.accountable_concluded is True
    assert outcome.reason is None
    assert set(outcome.components) == set(REQUIRED_ACCOUNTABLE_COMPONENTS)
    assert outcome.verdict == case.verdict

    observation = _component(outcome, "post_event_observation")
    assert observation["l2_outcome"] == case.l2_outcome
    assert observation["l2_detail"] == case.l2_detail

    oracles = _component(outcome, "oracles")
    assert oracles["l2"]["outcome"] == case.l2_outcome
    assert oracles["l2"]["detail"] == case.l2_detail
    assert oracles["l2"]["defect_class"] == (
        "state_loss" if case.l2_outcome == L2_OUTCOME_FAIL else None
    )
    assert oracles["verdict"] == case.verdict

    # The one rotation and the one post-cell re-probe stand exactly once: a
    # bounded L2 result never triggers a compensating or repeated action.
    operations = [operation for operation, _vector in device.mutation_operations()]
    counts = device.operation_counts()
    assert tuple(operations) == _COMPLETE_PREFIX
    assert counts["dispatch_orientation"] == 1
    assert counts["probe_session"] == 2
    _assert_admitted_mutation_vectors(device, request)

    record = _record(request.output_root)
    assert record["lifecycle_state"] == "completed"
    assert record["process_outcome"] == {"exit_code": case.exit_code}
    assert record["execution"]["status"] == "completed"
    assert record["execution"]["accounting_eligible"] is True
    assert record["phase_errors"] == []

    verified = verify_runtime_attempt(request.output_root)
    assert verified["verified"] is True
    assert verified["terminal_state"] == ACCOUNTABLE_CONCLUDED
    assert verified["recomputed"]["verdict"] == case.verdict
    assert verified["recomputed"]["l2_outcome"] == case.l2_outcome
    assert "post-cell-identity" in verified["checks"]


def test_frozen_phase_and_scope_tables_are_the_frozen_contract() -> None:
    assert runtime_attempt.FROZEN_PHASES == FROZEN_PHASES
    assert set(runtime_attempt.FAILURE_SCOPES) == set(SHARED_FAILURE_REASONS)
    assert set(runtime_attempt.FAILURE_SCOPES.values()) == {
        FAILURE_SCOPE_LANE_LOCAL,
        FAILURE_SCOPE_SHARED,
        FAILURE_SCOPE_UNKNOWN,
    }
    for reason, scope in runtime_attempt.FAILURE_SCOPES.items():
        assert failure_scope(reason) == scope
    assert failure_scope("no_table_entry") == FAILURE_SCOPE_UNKNOWN
    with pytest.raises(RuntimeAttemptError):
        failure_scope("")

    # The post-cell identity and the two layout ordinals are one frozen
    # contract: the recording device binds each named fault to the read the
    # runner declares, so a drifted mirror cannot silently move a fault onto
    # the Journey's own reads.
    assert RECORDED_JOURNEY_LAYOUT_READS == 6
    assert runtime_attempt.RECORDED_JOURNEY_LAYOUT_READS == RECORDED_JOURNEY_LAYOUT_READS
    assert JOURNEY_LAYOUT_READS == RECORDED_JOURNEY_LAYOUT_READS + 2
    assert RECORDED_BOUNDARY_LAYOUT_READ == RECORDED_JOURNEY_LAYOUT_READS + 1
    assert RECORDED_POST_EVENT_LAYOUT_READ == RECORDED_JOURNEY_LAYOUT_READS + 2
    assert runtime_attempt.RECORDED_BOUNDARY_LAYOUT_READ == (
        RECORDED_BOUNDARY_LAYOUT_READ
    )
    assert runtime_attempt.RECORDED_POST_EVENT_LAYOUT_READ == (
        RECORDED_POST_EVENT_LAYOUT_READ
    )
    assert EXPECTED_DEVICE_READ_COUNTS["probe_session"] == 2
    assert runtime_attempt.EXPECTED_DEVICE_READ_COUNTS["probe_session"] == 2
    assert "post_cell_identity" in REQUIRED_ACCOUNTABLE_COMPONENTS
    assert "close-post-cell-identity" in FROZEN_PHASES
    assert SHARED_FAILURE_REASONS >= {
        "device_session_identity_drifted",
        "log_attribution_ambiguous",
    }
    assert failure_scope("device_session_identity_drifted") == FAILURE_SCOPE_SHARED

    # Each closed fault vocabulary is exactly the set of names the recording
    # policy admits, and the tables mirror the matrix below one for one.
    for field_name, vocabulary in (
        ("boundary_layout_fault", LAYOUT_FAULTS),
        ("post_event_layout_fault", LAYOUT_FAULTS),
        ("log_dump_fault", LOG_DUMP_FAULTS),
        ("lifecycle_fault", LIFECYCLE_FAULTS),
        ("session_drift_fault", SESSION_DRIFT_FAULTS),
    ):
        assert vocabulary
        for name in vocabulary:
            RecordingDevicePolicy(**{field_name: name})
        with pytest.raises(RuntimeAttemptError) as invalid:
            RecordingDevicePolicy(**{field_name: "unadmitted_fault"})
        assert invalid.value.code == "recording_device_fault_invalid"
    mirrored: set[str] = set()
    for case in (*POST_OBSERVATION_FAILURES, *POST_EVENT_OBSERVATIONS):
        mirrored |= {
            fault
            for fault in (
                case.policy.boundary_layout_fault,
                case.policy.post_event_layout_fault,
                case.policy.log_dump_fault,
                case.policy.lifecycle_fault,
                case.policy.session_drift_fault,
            )
            if fault is not None
        }
    assert mirrored == (
        set(LAYOUT_FAULTS)
        | set(LOG_DUMP_FAULTS)
        | set(LIFECYCLE_FAULTS)
        | set(SESSION_DRIFT_FAULTS)
    )
