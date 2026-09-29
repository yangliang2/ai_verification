"""Recording-device integration tests for one accountable Runtime Attempt.

The recording device is bounded test infrastructure: its layout, log, and
lifecycle lines are recorded simulation text, so every attempt below concludes
with the ``recorded_simulation`` evidence class and never claims real device
evidence.  The tests drive the public lane seam end to end and bind the frozen
phase order, the exactly-once device budget, the marker-bounded log window, the
delivered landscape event, the L1/L2 oracles, and the sealed receipt/record pair.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import pytest

import aiverify.runtime_attempt as compat_runtime_attempt
from aiverify.bench import runtime_attempt
from aiverify.bench.runtime_attempt import (
    ACCOUNTABLE_CONCLUDED,
    ATTEMPT_SETUP_OPERATIONS,
    ATTEMPT_SETUP_PLAN_ID,
    BOUNDARY_PRECONDITION_TEXT,
    EXPECTED_DEVICE_MUTATION_COUNTS,
    EXPECTED_DEVICE_READ_COUNTS,
    FROZEN_TAP_TRAJECTORY,
    L1_OUTCOME_FAIL,
    L1_OUTCOME_INCONCLUSIVE,
    L2_OUTCOME_FAIL,
    L2_OUTCOME_PASS,
    LANDSCAPE_ROTATION,
    LIFECYCLE_END,
    LIFECYCLE_POLL_BUDGET,
    LIFECYCLE_POLL_INTERVAL_SECONDS,
    LIFECYCLE_SIGNATURE_EVENTS,
    LIFECYCLE_SIGNATURE_ID,
    LIFECYCLE_SIGNATURE_STATUS,
    LIFECYCLE_START,
    LOG_WINDOW_BUFFERS,
    LOG_WINDOW_FORMAT,
    MARKER_TAG,
    NON_ACCOUNTABLE,
    PORTRAIT_ROTATION,
    REQUIRED_ACCOUNTABLE_COMPONENTS,
    SESSION_IDENTITY_SETTINGS,
    SESSION_REQUIRED_FIELDS,
    SHARED_FAILURE_REASONS,
    TARGET_WINDOW_END,
    TARGET_WINDOW_START,
    AdbRuntimeDevice,
    RecordingDevicePolicy,
    RecordingRuntimeDevice,
    RuntimeAttemptInputError,
    RuntimeAttemptReceipt,
    RuntimeAttemptRequest,
    RuntimeAttemptSetupPlan,
    RuntimeAttemptVerificationError,
    canonical_sha256,
    execute_runtime_attempt,
    expected_device_mutation_order,
    expected_device_read_counts,
    launch_component,
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

# The frozen lane-01 Driver Plan has six actions, so the attempt owes six plus
# two runner-owned layout reads, and one foreground read plus two settle polls.
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
) -> tuple[RuntimeAttemptRequest, object]:
    spec, plan = _lane_inputs()
    apk_path = _sealed_apk(root)
    bound_device = device or RecordingRuntimeDevice(
        policy=policy or RecordingDevicePolicy(),
        package=spec.package,
        activity=spec.activity,
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

    verified = verify_runtime_attempt(request.output_root)
    assert verified["verified"] is True
    assert verified["attempt_id"] == document["attempt_id"]
    assert verified["terminal_state"] == ACCOUNTABLE_CONCLUDED
    assert verified["retries"] == 0
    assert verified["receipt_sha256"] == outcome.sha256
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
        "probe_session": 1,
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
    request, _device = _request(tmp_path, policy=policy)

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
    assert failure["scope"] == "attempt"

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
